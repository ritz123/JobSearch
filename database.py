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
from datetime import datetime, timezone
from pathlib import Path

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
    job_id         TEXT    UNIQUE,   -- extracted from LinkedIn job URL
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_job_id(url: str) -> str | None:
    """Pull the numeric job ID from a LinkedIn job URL.

    The automation-lab actor returns URLs in slug form
    (e.g. /jobs/view/software-engineer-...-4370317193), so we match the
    trailing digit sequence rather than expecting only digits after /jobs/view/.
    """
    if not url:
        return None
    # Match trailing digits at the end of the URL path (handles slug-style URLs)
    match = re.search(r"-(\d+)(?:[/?#]|$)", url)
    if match:
        return match.group(1)
    # Fallback: classic /jobs/view/<id> format
    match = re.search(r"/jobs/view/(\d+)", url)
    return match.group(1) if match else None


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
    Duplicates (same job_id) are skipped via INSERT OR IGNORE.
    """
    inserted = 0
    skipped = 0
    scraped_at = _now()

    with get_conn(db_path) as conn:
        for item in items:
            # The actor returns the job ID directly; fall back to URL extraction.
            job_id = str(item["id"]) if item.get("id") else None
            job_url = item.get("url") or item.get("jobUrl") or ""
            if not job_id:
                job_id = _extract_job_id(job_url)

            cur = conn.execute(
                """
                INSERT OR IGNORE INTO jobs
                    (job_id, title, company, location, workplace_type, contract_type,
                     published_at, salary, job_url, company_url, description,
                     search_id, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    item.get("title"),
                    item.get("companyName"),
                    item.get("location"),
                    item.get("workplaceType"),
                    item.get("employmentType"),
                    item.get("postedAt"),
                    item.get("salary"),
                    job_url,
                    item.get("companyLinkedinUrl"),
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

def query_jobs(
    keyword: str | None = None,
    company: str | None = None,
    location: str | None = None,
    workplace: str | None = None,
    limit: int = 50,
    db_path: Path = DEFAULT_DB,
) -> list[sqlite3.Row]:
    """Return jobs matching the given filters."""
    clauses = []
    params: list = []

    if keyword:
        clauses.append("(title LIKE ? OR description LIKE ?)")
        params += [f"%{keyword}%", f"%{keyword}%"]
    if company:
        clauses.append("company LIKE ?")
        params.append(f"%{company}%")
    if location:
        clauses.append("location LIKE ?")
        params.append(f"%{location}%")
    if workplace:
        clauses.append("workplace_type LIKE ?")
        params.append(f"%{workplace}%")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT j.*, s.keywords AS search_keywords, s.location AS search_location
        FROM jobs j
        LEFT JOIN searches s ON j.search_id = s.id
        {where}
        ORDER BY j.id DESC
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
            "SELECT keywords, location, job_count, ran_at FROM searches ORDER BY id DESC LIMIT 5"
        ).fetchall()

    return {
        "total_jobs": total_jobs,
        "total_searches": total_searches,
        "top_companies": [dict(r) for r in top_companies],
        "top_locations": [dict(r) for r in top_locations],
        "workplace_distribution": [dict(r) for r in workplace_dist],
        "recent_searches": [dict(r) for r in recent_searches],
    }
