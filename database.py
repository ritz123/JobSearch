"""
database.py — SQLite persistence layer for scraped LinkedIn jobs.

Schema
------
searches  : one row per actor run (keywords, location, filters, result count)
jobs      : one row per unique LinkedIn job (deduplicated by job_id from the URL)
"""

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from posted_dates import normalize_published_for_storage, to_absolute_published

DEFAULT_DB = Path(__file__).parent / "jobs.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE IF NOT EXISTS searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    keywords     TEXT    NOT NULL,
    location     TEXT    NOT NULL,
    filters      TEXT,           -- JSON blob (workplace, job_type, etc.)
    job_count    INTEGER,
    ran_at       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id         TEXT    UNIQUE,   -- namespaced id, e.g. linkedin:123 / naukri:456
    source         TEXT    NOT NULL DEFAULT 'linkedin',
    title          TEXT,
    company        TEXT,
    location       TEXT,
    workplace_type TEXT,
    contract_type  TEXT,
    published_at   TEXT,
    salary         TEXT,
    job_url        TEXT,
    company_url    TEXT,
    description    TEXT,
    search_id      INTEGER REFERENCES searches(id),
    scraped_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_title    ON jobs(title);
CREATE INDEX IF NOT EXISTS idx_jobs_company  ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_search   ON jobs(search_id);

CREATE TABLE IF NOT EXISTS city_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    city             TEXT    NOT NULL,
    filters          TEXT,
    max_companies    INTEGER,
    companies_found  INTEGER,
    jobs_found       INTEGER,
    ran_at           TEXT    NOT NULL,
    status           TEXT    NOT NULL,
    notes            TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    osm_id        TEXT,
    name          TEXT    NOT NULL,
    website       TEXT    NOT NULL UNIQUE,
    city          TEXT,
    lat           REAL,
    lon           REAL,
    tags          TEXT,
    careers_url   TEXT,
    last_seen_at  TEXT,
    created_at    TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_companies_city ON companies(city);
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);
"""

# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def get_conn(db_path: Path = DEFAULT_DB):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path = DEFAULT_DB) -> None:
    """Create tables and indexes if they don't exist yet."""
    with get_conn(db_path) as conn:
        conn.executescript(DDL)
    migrate_relative_published_at(db_path)
    migrate_job_source(db_path)
    migrate_city_careers(db_path)


def migrate_job_source(db_path: Path = DEFAULT_DB) -> None:
    """Add source column and namespace legacy LinkedIn job_ids."""
    with get_conn(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "source" not in cols:
            conn.execute(
                "ALTER TABLE jobs ADD COLUMN source TEXT NOT NULL DEFAULT 'linkedin'"
            )
        conn.execute(
            "UPDATE jobs SET source = 'linkedin' "
            "WHERE source IS NULL OR source = ''"
        )
        # Prefix bare LinkedIn ids once so they don't collide with Naukri ids.
        conn.execute(
            "UPDATE jobs SET job_id = 'linkedin:' || job_id "
            "WHERE source = 'linkedin' "
            "AND job_id IS NOT NULL "
            "AND job_id NOT LIKE 'linkedin:%' "
            "AND job_id NOT LIKE 'naukri:%'"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source)"
        )


def migrate_city_careers(db_path: Path = DEFAULT_DB) -> None:
    """Add city_run_id / company_id columns for company-site jobs."""
    with get_conn(db_path) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "city_run_id" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN city_run_id INTEGER")
        if "company_id" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN company_id INTEGER")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_city_run ON jobs(city_run_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_company_id ON jobs(company_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at)"
        )


def migrate_relative_published_at(db_path: Path = DEFAULT_DB) -> int:
    """Normalize published_at to UTC ISO (or NULL for non-dates).

    Converts relative strings and date-only values using scraped_at as reference.
    Clears values that are not publish dates (e.g. 'Starts within 1 month').
    Safe to run repeatedly.
    """
    updated = 0
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, published_at, scraped_at FROM jobs "
            "WHERE published_at IS NOT NULL AND published_at != ''"
        ).fetchall()
        for row in rows:
            raw = row["published_at"]
            # Already uniform ISO with timezone — leave alone.
            if isinstance(raw, str) and re.match(
                r"^\d{4}-\d{2}-\d{2}T.*([+-]\d{2}:\d{2}|Z)$", raw.strip()
            ):
                continue
            normalized = normalize_published_for_storage(raw, row["scraped_at"])
            if normalized == raw:
                continue
            conn.execute(
                "UPDATE jobs SET published_at = ? WHERE id = ?",
                (normalized, row["id"]),
            )
            updated += 1
    return updated

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_job_id(url: str) -> str | None:
    """Pull a numeric job ID from a LinkedIn or Naukri job URL."""
    if not url:
        return None
    # Naukri: .../job-listings-...-<id> or jobId query param
    match = re.search(r"[?&]jobId=(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"-(\d+)(?:[/?#]|$)", url)
    if match:
        return match.group(1)
    match = re.search(r"/jobs/view/(\d+)", url)
    return match.group(1) if match else None


def _namespaced_job_id(source: str, raw_id: str | None, url: str) -> str | None:
    job_id = str(raw_id) if raw_id is not None else None
    if not job_id:
        job_id = _extract_job_id(url)
    if not job_id:
        return None
    if ":" in job_id:
        return job_id
    return f"{source}:{job_id}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def save_search(
    keywords: str,
    location: str,
    filters: dict,
    job_count: int,
    db_path: Path = DEFAULT_DB,
) -> int:
    """Insert a search record and return its id."""
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO searches (keywords, location, filters, job_count, ran_at) VALUES (?, ?, ?, ?, ?)",
            (keywords, location, json.dumps(filters), job_count, _now()),
        )
        return cur.lastrowid


def save_jobs(items: list[dict], search_id: int, db_path: Path = DEFAULT_DB) -> tuple[int, int]:
    """
    Upsert job listings.
    Returns (inserted, skipped) counts.
    Duplicates (same namespaced job_id) are skipped via INSERT OR IGNORE.

    Each item should be source-normalized with keys:
    id, source, title, companyName, location, workplaceType, employmentType,
    postedAt, salary, url, companyUrl, descriptionText.
    """
    inserted = 0
    skipped = 0
    scraped_at = _now()

    with get_conn(db_path) as conn:
        for item in items:
            source = item.get("source") or "linkedin"
            job_url = item.get("url") or item.get("jobUrl") or ""
            job_id = _namespaced_job_id(source, item.get("id"), job_url)

            published_value = normalize_published_for_storage(
                item.get("postedAt"), scraped_at
            )

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO jobs
                    (job_id, source, title, company, location, workplace_type, contract_type,
                     published_at, salary, job_url, company_url, description,
                     search_id, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    source,
                    item.get("title"),
                    item.get("companyName"),
                    item.get("location"),
                    item.get("workplaceType"),
                    item.get("employmentType"),
                    published_value,
                    item.get("salary"),
                    job_url,
                    item.get("companyUrl") or item.get("companyLinkedinUrl"),
                    item.get("descriptionText"),
                    search_id,
                    scraped_at,
                ),
            )
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1

    return inserted, skipped


def create_city_run(
    city: str,
    filters: dict,
    max_companies: int,
    db_path: Path = DEFAULT_DB,
) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO city_runs
                (city, filters, max_companies, companies_found, jobs_found, ran_at, status, notes)
            VALUES (?, ?, ?, 0, 0, ?, 'running', NULL)
            """,
            (city, json.dumps(filters), max_companies, _now()),
        )
        return cur.lastrowid


def finish_city_run(
    run_id: int,
    *,
    status: str,
    companies_found: int,
    jobs_found: int,
    notes: str | None = None,
    db_path: Path = DEFAULT_DB,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE city_runs
            SET status = ?, companies_found = ?, jobs_found = ?, notes = ?
            WHERE id = ?
            """,
            (status, companies_found, jobs_found, notes, run_id),
        )


def upsert_company(company: dict, db_path: Path = DEFAULT_DB) -> int:
    """Insert or update a company by normalized website; return row id."""
    from careers.extract import normalize_website

    website = normalize_website(company.get("website") or "")
    if not website:
        raise ValueError("company website is required")
    now = _now()
    tags = company.get("tags")
    tags_json = json.dumps(tags) if isinstance(tags, (dict, list)) else tags
    with get_conn(db_path) as conn:
        existing = conn.execute(
            "SELECT id FROM companies WHERE website = ?", (website,)
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE companies
                SET osm_id = COALESCE(?, osm_id),
                    name = ?,
                    city = COALESCE(?, city),
                    lat = COALESCE(?, lat),
                    lon = COALESCE(?, lon),
                    tags = COALESCE(?, tags),
                    careers_url = COALESCE(?, careers_url),
                    last_seen_at = ?
                WHERE id = ?
                """,
                (
                    company.get("osm_id"),
                    company.get("name"),
                    company.get("city"),
                    company.get("lat"),
                    company.get("lon"),
                    tags_json,
                    company.get("careers_url"),
                    now,
                    existing["id"],
                ),
            )
            return int(existing["id"])
        cur = conn.execute(
            """
            INSERT INTO companies
                (osm_id, name, website, city, lat, lon, tags, careers_url, last_seen_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company.get("osm_id"),
                company.get("name"),
                website,
                company.get("city"),
                company.get("lat"),
                company.get("lon"),
                tags_json,
                company.get("careers_url"),
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def set_company_careers_url(
    company_id: int, careers_url: str | None, db_path: Path = DEFAULT_DB
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE companies SET careers_url = ?, last_seen_at = ? WHERE id = ?",
            (careers_url, _now(), company_id),
        )


def save_company_site_jobs(
    items: list[dict],
    city_run_id: int,
    db_path: Path = DEFAULT_DB,
) -> tuple[int, int]:
    """Insert new company-site jobs or bump scraped_at on duplicates."""
    inserted = 0
    refreshed = 0
    scraped_at = _now()

    with get_conn(db_path) as conn:
        for item in items:
            job_url = item.get("url") or ""
            job_id = item.get("id") or _namespaced_job_id(
                "company_site", None, job_url
            )
            published_value = normalize_published_for_storage(
                item.get("postedAt"), scraped_at
            )
            company_id = item.get("company_id")

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO jobs
                    (job_id, source, title, company, location, workplace_type, contract_type,
                     published_at, salary, job_url, company_url, description,
                     search_id, scraped_at, city_run_id, company_id)
                VALUES (?, 'company_site', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
                """,
                (
                    job_id,
                    item.get("title"),
                    item.get("companyName"),
                    item.get("location"),
                    item.get("workplaceType"),
                    item.get("employmentType"),
                    published_value,
                    item.get("salary"),
                    job_url,
                    item.get("companyUrl"),
                    item.get("descriptionText"),
                    scraped_at,
                    city_run_id,
                    company_id,
                ),
            )
            if cur.rowcount:
                inserted += 1
            else:
                conn.execute(
                    """
                    UPDATE jobs
                    SET scraped_at = ?,
                        city_run_id = ?,
                        title = COALESCE(?, title),
                        location = COALESCE(?, location),
                        description = COALESCE(?, description),
                        job_url = COALESCE(?, job_url)
                    WHERE job_id = ?
                    """,
                    (
                        scraped_at,
                        city_run_id,
                        item.get("title"),
                        item.get("location"),
                        item.get("descriptionText"),
                        job_url or None,
                        job_id,
                    ),
                )
                refreshed += 1

    return inserted, refreshed


def query_companies(
    city: str | None = None,
    limit: int = 100,
    db_path: Path = DEFAULT_DB,
) -> list[sqlite3.Row]:
    clauses = []
    params: list = []
    if city:
        clauses.append("city LIKE ?")
        params.append(f"%{city}%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM companies {where} ORDER BY last_seen_at DESC LIMIT ?"
    params.append(limit)
    with get_conn(db_path) as conn:
        return conn.execute(sql, params).fetchall()


def get_recent_city_runs(limit: int = 20, db_path: Path = DEFAULT_DB) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, city, filters, max_companies, companies_found, jobs_found,
                   ran_at, status, notes
            FROM city_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    results = []
    for row in rows:
        item = dict(row)
        raw = item.get("filters")
        try:
            item["filters"] = json.loads(raw) if raw else {}
        except (TypeError, json.JSONDecodeError):
            item["filters"] = {}
        results.append(item)
    return results


def purge_old_jobs(
    older_than_days: int = 7,
    db_path: Path = DEFAULT_DB,
) -> int:
    """Delete jobs whose posting date (or scrape date fallback) is older than N days.

    Uses ``published_at`` when it can be resolved to an absolute timestamp;
    otherwise falls back to ``scraped_at`` so undated rows still age out.
    """
    if older_than_days < 1:
        raise ValueError("older_than_days must be >= 1")

    cutoff = datetime.now(timezone.utc) - timedelta(days=int(older_than_days))
    to_delete: list[int] = []

    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, published_at, scraped_at FROM jobs"
        ).fetchall()
        for row in rows:
            absolute = to_absolute_published(row["published_at"], row["scraped_at"])
            if absolute is None:
                scraped_raw = row["scraped_at"] or ""
                try:
                    absolute = datetime.fromisoformat(
                        scraped_raw.replace("Z", "+00:00")
                    )
                except ValueError:
                    continue
                if absolute.tzinfo is None:
                    absolute = absolute.replace(tzinfo=timezone.utc)
            if absolute < cutoff:
                to_delete.append(int(row["id"]))

        for job_id in to_delete:
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    return len(to_delete)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

# Sidebar / CLI labels → max age in hours (None = no filter)
POSTED_WITHIN_OPTIONS = {
    "any": None,
    "24h": 24,
    "3d": 72,
    "week": 168,
    "month": 720,  # 30 days
}


def query_jobs(
    keyword: str | None = None,
    company: str | None = None,
    location: str | None = None,
    workplace: str | None = None,
    source: str | None = None,
    posted_within: str | None = None,
    scraped_within_days: int | None = None,
    limit: int = 50,
    db_path: Path = DEFAULT_DB,
) -> list[sqlite3.Row]:
    """Return jobs matching the given filters.

    ``posted_within`` is one of POSTED_WITHIN_OPTIONS keys (``any`` / ``24h`` /
    ``3d`` / ``week`` / ``month``), or None for no recency filter.

    ``scraped_within_days`` filters by when the job was last seen/scraped
    (used by the city-careers soft-recent UI).
    """
    clauses = []
    params: list = []

    if keyword:
        clauses.append("(j.title LIKE ? OR j.description LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if company:
        clauses.append("j.company LIKE ?")
        params.append(f"%{company}%")
    if location:
        # Naukri uses "Bengaluru"; LinkedIn often "Bangalore" — treat as aliases.
        loc_l = location.lower()
        if "bangalore" in loc_l or "bengaluru" in loc_l:
            clauses.append(
                "(j.location LIKE ? OR j.location LIKE ? OR j.location LIKE ?)"
            )
            params += [f"%{location}%", "%Bangalore%", "%Bengaluru%"]
        else:
            clauses.append("j.location LIKE ?")
            params.append(f"%{location}%")
    if workplace:
        # Naukri often puts Remote in location with null workplace_type.
        clauses.append("(j.workplace_type LIKE ? OR j.location LIKE ?)")
        params += [f"%{workplace}%", f"%{workplace}%"]
    if source and source.lower() != "all":
        clauses.append("j.source = ?")
        params.append(source.lower())

    hours = None
    if posted_within:
        key = posted_within.lower().strip()
        if key in POSTED_WITHIN_OPTIONS:
            hours = POSTED_WITHIN_OPTIONS[key]
        elif key.isdigit():
            hours = int(key)
    if hours:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        # Absolute ISO published_at values compare lexicographically.
        clauses.append("j.published_at IS NOT NULL AND j.published_at >= ?")
        params.append(cutoff)

    if scraped_within_days and scraped_within_days > 0:
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=int(scraped_within_days))
        ).isoformat()
        clauses.append("j.scraped_at >= ?")
        params.append(cutoff)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    if scraped_within_days and scraped_within_days > 0:
        # City-careers soft-recent browse: last seen first.
        order = "j.scraped_at DESC, j.id DESC"
    else:
        # Jobs Explorer default: newest published first; unknowns last.
        order = (
            "CASE WHEN j.published_at IS NULL OR j.published_at = '' "
            "THEN 1 ELSE 0 END ASC, "
            "j.published_at DESC, j.id DESC"
        )
    sql = f"""
        SELECT j.*, s.keywords AS search_keywords, s.location AS search_location
        FROM jobs j
        LEFT JOIN searches s ON j.search_id = s.id
        {where}
        ORDER BY {order}
        LIMIT ?
    """
    params.append(limit)

    with get_conn(db_path) as conn:
        return conn.execute(sql, params).fetchall()


def get_stats(db_path: Path = DEFAULT_DB) -> dict:
    """Return high-level stats about the database contents."""
    with get_conn(db_path) as conn:
        total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        total_searches = conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
        top_companies = conn.execute(
            "SELECT company, COUNT(*) AS n FROM jobs WHERE company IS NOT NULL "
            "GROUP BY company ORDER BY n DESC LIMIT 10"
        ).fetchall()
        top_locations = conn.execute(
            "SELECT location, COUNT(*) AS n FROM jobs WHERE location IS NOT NULL "
            "GROUP BY location ORDER BY n DESC LIMIT 10"
        ).fetchall()
        workplace_dist = conn.execute(
            "SELECT workplace_type, COUNT(*) AS n FROM jobs WHERE workplace_type IS NOT NULL "
            "GROUP BY workplace_type ORDER BY n DESC"
        ).fetchall()
        recent_searches = conn.execute(
            "SELECT id, keywords, location, filters, job_count, ran_at "
            "FROM searches ORDER BY id DESC LIMIT 5"
        ).fetchall()

    return {
        "total_jobs": total_jobs,
        "total_searches": total_searches,
        "top_companies": [dict(r) for r in top_companies],
        "top_locations": [dict(r) for r in top_locations],
        "workplace_distribution": [dict(r) for r in workplace_dist],
        "recent_searches": [dict(r) for r in recent_searches],
    }


def get_recent_searches(limit: int = 10, db_path: Path = DEFAULT_DB) -> list[dict]:
    """Return recent search runs with parsed filters for UI reload."""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, keywords, location, filters, job_count, ran_at "
            "FROM searches ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        raw = item.get("filters")
        try:
            item["filters"] = json.loads(raw) if raw else {}
        except (TypeError, json.JSONDecodeError):
            item["filters"] = {}
        results.append(item)
    return results
