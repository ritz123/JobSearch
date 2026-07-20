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

from posted_dates import relative_age_seconds, to_absolute_published

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


def migrate_relative_published_at(db_path: Path = DEFAULT_DB) -> int:
    """Convert frozen 'N days ago' strings into absolute ISO timestamps.

    Uses each row's scraped_at as the reference time. Safe to run repeatedly.
    """
    updated = 0
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, published_at, scraped_at FROM jobs "
            "WHERE published_at IS NOT NULL AND published_at != ''"
        ).fetchall()
        for row in rows:
            if relative_age_seconds(row["published_at"]) is None:
                continue
            absolute = to_absolute_published(row["published_at"], row["scraped_at"])
            if absolute is None:
                continue
            conn.execute(
                "UPDATE jobs SET published_at = ? WHERE id = ?",
                (absolute.isoformat(), row["id"]),
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

            published = to_absolute_published(item.get("postedAt"), scraped_at)
            published_value = published.isoformat() if published else item.get("postedAt")

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
    limit: int = 50,
    db_path: Path = DEFAULT_DB,
) -> list[sqlite3.Row]:
    """Return jobs matching the given filters.

    ``posted_within`` is one of POSTED_WITHIN_OPTIONS keys (``any`` / ``24h`` /
    ``3d`` / ``week`` / ``month``), or None for no recency filter.
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

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    order = "j.published_at DESC, j.id DESC" if hours else "j.id DESC"
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
