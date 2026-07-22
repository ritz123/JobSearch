"""Tests for purge_old_jobs."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import (  # noqa: E402
    get_conn,
    init_db,
    purge_old_jobs,
    save_search,
)
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402


def test_purge_old_jobs_keeps_recent(tmp_path):
    db = tmp_path / "purge.db"
    init_db(db)
    sid = save_search("seo", "bangalore", {}, 2, db_path=db)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(days=10)).isoformat()
    fresh = (now - timedelta(days=2)).isoformat()

    with get_conn(db) as conn:
        conn.execute(
            """
            INSERT INTO jobs
                (job_id, source, title, company, published_at, scraped_at, search_id)
            VALUES
                ('linkedin:old', 'linkedin', 'Old', 'A', ?, ?, ?),
                ('linkedin:new', 'linkedin', 'New', 'B', ?, ?, ?)
            """,
            (old, now.isoformat(), sid, fresh, now.isoformat(), sid),
        )

    deleted = purge_old_jobs(older_than_days=7, db_path=db)
    assert deleted == 1
    with get_conn(db) as conn:
        titles = [r[0] for r in conn.execute("SELECT title FROM jobs").fetchall()]
    assert titles == ["New"]


def test_api_purge_endpoint():
    client = TestClient(app)
    res = client.post("/api/jobs/purge", json={"older_than_days": 7})
    assert res.status_code == 200
    body = res.json()
    assert "deleted" in body
    assert body["older_than_days"] == 7
