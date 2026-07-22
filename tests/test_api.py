"""API smoke tests (no Apify / Ollama)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_jobs_list():
    res = client.get("/api/jobs", params={"limit": 5})
    assert res.status_code == 200
    assert "jobs" in res.json()


def test_stats():
    res = client.get("/api/stats")
    assert res.status_code == 200
    body = res.json()
    assert "total_jobs" in body
