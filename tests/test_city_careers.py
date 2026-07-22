"""Tests for city careers helpers (no live network/Ollama)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from careers.extract import (  # noqa: E402
    company_site_job_id,
    html_to_text,
    normalize_extracted_jobs,
    normalize_website,
)
from database import (  # noqa: E402
    create_city_run,
    finish_city_run,
    init_db,
    query_jobs,
    save_company_site_jobs,
    upsert_company,
)
from sources.overpass import build_overpass_query  # noqa: E402


def test_normalize_website():
    assert normalize_website("example.com") == "https://example.com"
    assert normalize_website("https://www.Example.com/careers/") == "https://example.com/careers"
    assert normalize_website("") == ""


def test_company_site_job_id_stable():
    a = company_site_job_id(1, "Engineer", "https://x.com/jobs/1")
    b = company_site_job_id(1, "Engineer", "https://x.com/jobs/1")
    c = company_site_job_id(1, "Engineer", "https://x.com/jobs/2")
    assert a.startswith("company_site:")
    assert a == b
    assert a != c


def test_html_to_text_strips_tags():
    text = html_to_text("<html><script>bad()</script><body><h1>Jobs</h1><p>Open role</p></body></html>")
    assert "Jobs" in text
    assert "Open role" in text
    assert "bad()" not in text
    assert "<" not in text


def test_build_overpass_query_contains_bbox():
    bbox = {"south": 12.0, "west": 77.0, "north": 13.0, "east": 78.0}
    q = build_overpass_query(bbox, preset="tech_corporate")
    assert "12.0,77.0,13.0,78.0" in q
    assert '["office"' in q
    assert "out center tags" in q


def test_seo_marketing_preset_and_name_filter():
    from sources.overpass import NAME_KEYWORDS, _matches_name_filter, build_overpass_query

    bbox = {"south": 12.0, "west": 77.0, "north": 13.0, "east": 78.0}
    q = build_overpass_query(bbox, preset="seo_marketing")
    assert "advertising_agency" in q or "marketing" in q
    assert "seo" in NAME_KEYWORDS["seo_marketing"]

    hit = {
        "name": "Bright SEO Labs",
        "website": "https://brightseo.example",
        "tags": {"office": "company"},
    }
    miss = {
        "name": "Acme Hardware",
        "website": "https://acme.example",
        "tags": {"office": "company"},
    }
    agency = {
        "name": "Local Ads Co",
        "website": "https://ads.example",
        "tags": {"office": "advertising_agency"},
    }
    kws = NAME_KEYWORDS["seo_marketing"]
    assert _matches_name_filter(hit, kws)
    assert not _matches_name_filter(miss, kws)
    assert _matches_name_filter(agency, kws)


def test_normalize_extracted_jobs():
    items = normalize_extracted_jobs(
        [{"title": "SWE", "location": "Remote", "url": "/jobs/swe"}],
        company_name="Acme",
        company_url="https://acme.test",
        careers_url="https://acme.test/careers",
        company_id=9,
        city="Bangalore",
    )
    assert len(items) == 1
    assert items[0]["source"] == "company_site"
    assert items[0]["companyName"] == "Acme"
    assert items[0]["url"].startswith("https://")
    assert items[0]["id"].startswith("company_site:")


def test_save_company_site_jobs_refresh(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    run_id = create_city_run("Testville", {"preset": "tech_corporate"}, 5, db_path=db)
    company_id = upsert_company(
        {
            "osm_id": "node/1",
            "name": "Acme",
            "website": "https://acme.test",
            "city": "Testville",
        },
        db_path=db,
    )
    item = {
        "id": company_site_job_id(company_id, "SWE", "https://acme.test/jobs/1"),
        "title": "SWE",
        "companyName": "Acme",
        "location": "Testville",
        "url": "https://acme.test/jobs/1",
        "companyUrl": "https://acme.test",
        "descriptionText": "Build things",
        "company_id": company_id,
    }
    inserted, refreshed = save_company_site_jobs([item], run_id, db_path=db)
    assert inserted == 1 and refreshed == 0
    inserted2, refreshed2 = save_company_site_jobs([item], run_id, db_path=db)
    assert inserted2 == 0 and refreshed2 == 1

    rows = query_jobs(source="company_site", scraped_within_days=14, limit=10, db_path=db)
    assert len(rows) == 1
    assert rows[0]["title"] == "SWE"

    finish_city_run(
        run_id,
        status="succeeded",
        companies_found=1,
        jobs_found=1,
        db_path=db,
    )
