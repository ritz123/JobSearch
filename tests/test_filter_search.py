"""Regression: keyword filter via API/database must not crash."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import query_jobs  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

client = TestClient(app)


def test_query_jobs_seo_returns_rows():
    rows = query_jobs(keyword="SEO", limit=100)
    assert rows, "Expected SEO jobs in jobs.db for this regression test"
    assert rows[0]["title"] is not None


def test_api_jobs_seo_filter():
    res = client.get("/api/jobs", params={"keyword": "SEO", "limit": 100})
    assert res.status_code == 200
    jobs = res.json()["jobs"]
    assert jobs, "Expected SEO jobs via API"
    assert any("seo" in str(j.get("title", "")).lower() or "seo" in str(j.get("description", "")).lower() for j in jobs)
