"""City → companies (OSM) → careers pages → Ollama → SQLite."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from careers.extract import (
    check_ollama,
    extract_jobs_with_ollama,
    find_careers_url,
    html_to_text,
    normalize_extracted_jobs,
    fetch_url,
)
from database import (
    DEFAULT_DB,
    create_city_run,
    finish_city_run,
    init_db,
    save_company_site_jobs,
    set_company_careers_url,
    upsert_company,
)
from sources.overpass import find_companies

ProgressCb = Callable[[str], None]


def run_city_pipeline(
    city: str,
    *,
    preset: str = "tech_corporate",
    max_companies: int = 15,
    ollama_base_url: str | None = None,
    ollama_model: str | None = None,
    db_path: Path = DEFAULT_DB,
    progress: ProgressCb | None = None,
    crawl_delay_s: float = 0.5,
) -> dict:
    """
    Run a full city careers scrape.

    Returns a summary dict with run_id, status, companies_found, jobs_found, notes.
    """
    log = progress or (lambda _m: None)
    base_url = (ollama_base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip(
        "/"
    )
    model = ollama_model or os.getenv("OLLAMA_MODEL") or "llama3.2"

    init_db(db_path)
    log(f"Checking Ollama at {base_url} (model={model})…")
    check_ollama(base_url)

    filters = {"preset": preset, "ollama_model": model}
    run_id = create_city_run(city, filters, max_companies, db_path=db_path)

    companies_saved = 0
    jobs_inserted = 0
    jobs_refreshed = 0
    skip_notes: list[str] = []

    try:
        companies = find_companies(
            city,
            preset=preset,
            max_companies=max_companies,
            progress=progress,
        )
    except Exception as exc:
        finish_city_run(
            run_id,
            status="failed",
            companies_found=0,
            jobs_found=0,
            notes=str(exc),
            db_path=db_path,
        )
        raise

    total = len(companies)
    for idx, company in enumerate(companies, start=1):
        name = company.get("name") or "unknown"
        log(f"[{idx}/{total}] {name} — {company.get('website')}")
        try:
            company_id = upsert_company(company, db_path=db_path)
            companies_saved += 1
        except Exception as exc:
            skip_notes.append(f"{name}: upsert failed ({exc})")
            continue

        try:
            careers_url = find_careers_url(company["website"], delay_s=crawl_delay_s)
        except Exception as exc:
            skip_notes.append(f"{name}: careers discovery error ({exc})")
            continue

        if not careers_url:
            skip_notes.append(f"{name}: no careers URL")
            set_company_careers_url(company_id, None, db_path=db_path)
            continue

        set_company_careers_url(company_id, careers_url, db_path=db_path)
        log(f"  Careers: {careers_url}")

        try:
            _status, _final, body = fetch_url(careers_url)
            time.sleep(crawl_delay_s)
            page_text = html_to_text(body)
        except Exception as exc:
            skip_notes.append(f"{name}: fetch failed ({exc})")
            continue

        if len(page_text) < 40:
            skip_notes.append(f"{name}: empty careers page")
            continue

        log("  Extracting jobs with Ollama…")
        raw_jobs = extract_jobs_with_ollama(
            page_text,
            name,
            careers_url,
            base_url=base_url,
            model=model,
        )
        items = normalize_extracted_jobs(
            raw_jobs,
            company_name=name,
            company_url=company["website"],
            careers_url=careers_url,
            company_id=company_id,
            city=city,
        )
        if not items:
            skip_notes.append(f"{name}: no jobs extracted")
            continue

        inserted, refreshed = save_company_site_jobs(
            items, run_id, db_path=db_path
        )
        jobs_inserted += inserted
        jobs_refreshed += refreshed
        log(f"  Jobs: +{inserted} new, {refreshed} refreshed")

    jobs_found = jobs_inserted + jobs_refreshed
    if jobs_found == 0 and companies_saved == 0:
        status = "failed"
    elif skip_notes and jobs_found == 0:
        status = "partial"
    elif skip_notes:
        status = "partial"
    else:
        status = "succeeded"

    notes = "; ".join(skip_notes[:40]) if skip_notes else None
    finish_city_run(
        run_id,
        status=status,
        companies_found=companies_saved,
        jobs_found=jobs_found,
        notes=notes,
        db_path=db_path,
    )
    summary = {
        "run_id": run_id,
        "status": status,
        "companies_found": companies_saved,
        "jobs_found": jobs_found,
        "jobs_inserted": jobs_inserted,
        "jobs_refreshed": jobs_refreshed,
        "notes": notes,
    }
    log(
        f"Done. status={status} companies={companies_saved} "
        f"jobs={jobs_found} (new={jobs_inserted}, refreshed={jobs_refreshed})"
    )
    return summary
