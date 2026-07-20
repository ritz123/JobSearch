"""Tests for multi-source adapters and namespaced job ids."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import _namespaced_job_id, init_db, query_jobs, save_jobs, save_search  # noqa: E402
from sources import get_adapter  # noqa: E402
from sources.naukri import NaukriSource, sanitize_naukri_location  # noqa: E402


def test_get_adapter_linkedin_and_naukri():
    assert get_adapter("linkedin").name == "linkedin"
    assert get_adapter("naukri").name == "naukri"
    assert "naukri" in get_adapter("naukri").actor_id


def test_sanitize_naukri_location_strips_linkedin_style():
    city, mode = sanitize_naukri_location("Bangalore, remote")
    assert city == "Bangalore"
    assert mode == "remote"
    city, mode = sanitize_naukri_location("Bangalore, India, Anywhere")
    assert city == "Bangalore"
    assert mode is None
    city, mode = sanitize_naukri_location("remote")
    assert city == ""
    assert mode == "remote"


def test_naukri_build_input_maps_workplace():
    args = SimpleNamespace(
        keywords="python developer",
        location="bangalore",
        max_jobs=20,
        workplace="remote",
        sort_recent=True,
    )
    run_input = NaukriSource().build_input(args)
    assert run_input["keyword"] == "python developer"
    assert run_input["location"] == "bangalore"
    assert run_input["maxJobs"] == 20
    assert run_input["workMode"] == "remote"
    assert run_input["sortBy"] == "date"


def test_naukri_build_input_cleans_linkedin_location():
    args = SimpleNamespace(
        keywords="SEO",
        location="Bangalore, remote",
        max_jobs=10,
        workplace=None,
        sort_recent=False,
    )
    run_input = NaukriSource().build_input(args)
    assert run_input["location"] == "Bangalore"
    assert run_input["workMode"] == "remote"
    assert "," not in run_input["location"]


def test_naukri_normalize_items():
    raw = [
        {
            "jobId": "12345",
            "title": "Python Dev",
            "company": "Acme",
            "location": "Bengaluru",
            "workMode": "hybrid",
            "postedAt": "2 days ago",
            "salary": "10-15 Lacs",
            "jobUrl": "https://www.naukri.com/job-listings-python-dev-12345",
            "description": "Build things",
        },
        {
            "jobId": "999",
            "title": "Remote SEO",
            "companyName": "Remote Co",
            "location": "Remote",
            "jobUrl": "https://www.naukri.com/job-listings-remote-seo-999",
        },
    ]
    items = NaukriSource().normalize_items(raw)
    assert len(items) == 2
    assert items[0]["source"] == "naukri"
    assert items[0]["id"] == "12345"
    assert items[0]["companyName"] == "Acme"
    assert items[0]["workplaceType"] == "hybrid"
    assert items[0]["url"].endswith("12345")
    assert items[1]["workplaceType"] == "remote"


def test_namespaced_job_id():
    assert _namespaced_job_id("naukri", "99", "") == "naukri:99"
    assert _namespaced_job_id("linkedin", "4370317193", "") == "linkedin:4370317193"
    assert _namespaced_job_id("linkedin", "linkedin:1", "") == "linkedin:1"


def test_query_jobs_bangalore_matches_bengaluru(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    sid = save_search("SEO", "bangalore", {"source": "naukri"}, 1, db)
    save_jobs(
        [
            {
                "id": "1",
                "source": "naukri",
                "title": "SEO Manager",
                "companyName": "Acme",
                "location": "Bengaluru",
                "workplaceType": None,
                "employmentType": None,
                "postedAt": "2026-07-17T00:00:00+00:00",
                "salary": None,
                "url": "https://www.naukri.com/job-listings-1",
                "companyUrl": None,
                "descriptionText": "SEO",
            }
        ],
        sid,
        db,
    )
    rows = query_jobs(location="Bangalore", source="naukri", db_path=db)
    assert len(rows) == 1
    rows_remote = query_jobs(workplace="Remote", source="naukri", db_path=db)
    assert len(rows_remote) == 0  # location is Bengaluru, not Remote


def test_query_jobs_posted_within_filters_recent(tmp_path):
    from datetime import datetime, timedelta, timezone

    db = tmp_path / "recent.db"
    init_db(db)
    sid = save_search("SEO", "bangalore", {}, 2, db)
    now = datetime.now(timezone.utc)
    save_jobs(
        [
            {
                "id": "new",
                "source": "linkedin",
                "title": "Fresh SEO",
                "companyName": "NewCo",
                "location": "Remote",
                "workplaceType": "Remote",
                "employmentType": None,
                "postedAt": (now - timedelta(hours=12)).isoformat(),
                "salary": None,
                "url": "https://linkedin.com/jobs/view/111",
                "companyUrl": None,
                "descriptionText": "SEO",
            },
            {
                "id": "old",
                "source": "linkedin",
                "title": "Old SEO",
                "companyName": "OldCo",
                "location": "Remote",
                "workplaceType": "Remote",
                "employmentType": None,
                "postedAt": (now - timedelta(days=10)).isoformat(),
                "salary": None,
                "url": "https://linkedin.com/jobs/view/222",
                "companyUrl": None,
                "descriptionText": "SEO",
            },
        ],
        sid,
        db,
    )
    recent = query_jobs(posted_within="24h", db_path=db)
    assert len(recent) == 1
    assert recent[0]["title"] == "Fresh SEO"
    week = query_jobs(posted_within="week", db_path=db)
    assert len(week) == 1
    month = query_jobs(posted_within="month", db_path=db)
    assert len(month) == 2
