"""FastAPI backend for the JobSearch React SPA."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from careers.extract import list_ollama_models  # noqa: E402
from city_pipeline import run_city_pipeline  # noqa: E402
from database import (  # noqa: E402
    DEFAULT_DB,
    get_recent_city_runs,
    get_recent_searches,
    get_stats,
    init_db,
    purge_old_jobs,
    query_companies,
    query_jobs,
)
from exports import build_jobs_xlsx  # noqa: E402
from posted_dates import format_published_ago  # noqa: E402
from scraper import run_actor, save_to_db  # noqa: E402
from sources import get_adapter  # noqa: E402

app = FastAPI(title="JobSearch API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db(DEFAULT_DB)


def _row_to_dict(row: Any) -> dict:
    return {k: row[k] for k in row.keys()}


def _job_to_dict(row: Any) -> dict:
    item = _row_to_dict(row)
    item["published_ago"] = format_published_ago(
        item.get("published_at"), item.get("scraped_at")
    )
    return item


class ScrapeRequest(BaseModel):
    source: str = "linkedin"
    keywords: str
    location: str
    country: str = "in"
    max_jobs: int = Field(25, ge=1, le=200)
    workplace: str | None = None
    job_type: str | None = None
    date_posted: str = "any"
    experience: str | None = None
    company: str | None = None
    details: bool = False
    sort_recent: bool = False


class CityRunRequest(BaseModel):
    city: str
    preset: str = "tech_corporate"
    max_companies: int = Field(15, ge=1, le=50)
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/jobs")
def api_jobs(
    keyword: str | None = None,
    company: str | None = None,
    location: str | None = None,
    workplace: str | None = None,
    source: str | None = None,
    posted_within: str | None = None,
    scraped_within_days: int | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    rows = query_jobs(
        keyword=keyword or None,
        company=company or None,
        location=location or None,
        workplace=workplace or None,
        source=source or None,
        posted_within=posted_within or None,
        scraped_within_days=scraped_within_days,
        limit=limit,
        db_path=DEFAULT_DB,
    )
    return {"jobs": [_job_to_dict(r) for r in rows]}


@app.get("/api/jobs/export.xlsx")
def api_jobs_export_xlsx(
    keyword: str | None = None,
    company: str | None = None,
    location: str | None = None,
    workplace: str | None = None,
    source: str | None = None,
    posted_within: str | None = None,
    limit: int = Query(2000, ge=1, le=5000),
):
    """Download filtered jobs as Excel (.xlsx) with clickable URL hyperlinks."""
    rows = query_jobs(
        keyword=keyword or None,
        company=company or None,
        location=location or None,
        workplace=workplace or None,
        source=source or None,
        posted_within=posted_within or None,
        limit=limit,
        db_path=DEFAULT_DB,
    )
    records = []
    for row in rows:
        item = _job_to_dict(row)
        records.append(
            {
                "Source": item.get("source"),
                "Title": item.get("title"),
                "Company": item.get("company"),
                "Location": item.get("location"),
                "Workplace": item.get("workplace_type"),
                "Contract": item.get("contract_type"),
                "Published": item.get("published_ago"),
                "Published (ISO)": item.get("published_at"),
                "Salary": item.get("salary"),
                "Job URL": item.get("job_url"),
                "Company URL": item.get("company_url"),
            }
        )
    buf = io.BytesIO(build_jobs_xlsx(records))
    headers = {
        "Content-Disposition": 'attachment; filename="jobs_export.xlsx"',
    }
    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers=headers,
    )


class PurgeRequest(BaseModel):
    older_than_days: int = Field(7, ge=1, le=365)


@app.post("/api/jobs/purge")
def api_purge_jobs(body: PurgeRequest) -> dict:
    deleted = purge_old_jobs(older_than_days=body.older_than_days, db_path=DEFAULT_DB)
    return {"deleted": deleted, "older_than_days": body.older_than_days}


@app.get("/api/stats")
def api_stats() -> dict:
    return get_stats(db_path=DEFAULT_DB)


@app.get("/api/searches")
def api_searches(limit: int = Query(20, ge=1, le=100)) -> dict:
    return {"searches": get_recent_searches(limit=limit, db_path=DEFAULT_DB)}


@app.post("/api/scrape")
def api_scrape(body: ScrapeRequest) -> dict:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise HTTPException(status_code=400, detail="APIFY_TOKEN is not set in .env")

    workplace = None if not body.workplace or body.workplace.lower() == "any" else body.workplace
    job_type = None if not body.job_type or body.job_type.lower() == "any" else body.job_type
    experience = (
        None if not body.experience or body.experience.lower() == "any" else body.experience
    )

    args = SimpleNamespace(
        source=body.source,
        keywords=body.keywords.strip(),
        location=body.location.strip(),
        country=body.country,
        max_jobs=body.max_jobs,
        workplace=workplace,
        job_type=job_type,
        date_posted=body.date_posted or "any",
        experience=experience,
        company=body.company or None,
        details=body.details,
        sort_recent=body.sort_recent,
    )
    if not args.keywords or not args.location:
        raise HTTPException(status_code=400, detail="keywords and location are required")

    try:
        adapter = get_adapter(body.source)
        run_input = adapter.build_input(args)
        raw_items = run_actor(token, adapter.actor_id, run_input, adapter.name)
        items = adapter.normalize_items(raw_items)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    filters = {
        "source": body.source,
        "country": body.country,
        "max_jobs": body.max_jobs,
        "workplace": workplace,
        "job_type": job_type,
        "date_posted": body.date_posted,
        "experience": experience,
        "company": body.company,
        "details": body.details,
        "sort_recent": body.sort_recent,
    }
    save_to_db(items, args.keywords, args.location, filters, DEFAULT_DB)
    return {"fetched": len(items), "keywords": args.keywords, "location": args.location}

@app.get("/api/ollama/models")
def api_ollama_models(base_url: str = "http://127.0.0.1:11434") -> dict:
    try:
        models = list_ollama_models(base_url, timeout=3)
        return {"ok": True, "models": models}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/city-runs")
def api_city_run(body: CityRunRequest) -> dict:
    if not body.city.strip():
        raise HTTPException(status_code=400, detail="city is required")
    try:
        summary = run_city_pipeline(
            body.city.strip(),
            preset=body.preset,
            max_companies=body.max_companies,
            ollama_base_url=body.ollama_base_url,
            ollama_model=body.ollama_model,
            db_path=DEFAULT_DB,
        )
        return summary
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/city-runs")
def api_list_city_runs(limit: int = Query(30, ge=1, le=100)) -> dict:
    return {"runs": get_recent_city_runs(limit=limit, db_path=DEFAULT_DB)}


@app.get("/api/companies")
def api_companies(
    city: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    rows = query_companies(city=city or None, limit=limit, db_path=DEFAULT_DB)
    return {"companies": [_row_to_dict(r) for r in rows]}
