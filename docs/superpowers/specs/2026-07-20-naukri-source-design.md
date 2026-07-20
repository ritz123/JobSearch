# Multi-source scraping (LinkedIn + Naukri) — Design

## Goal

Allow choosing **LinkedIn** or **Naukri** per scrape run, store both in the same DB/dashboard.

## Behavior

- Run Scraper: **Source** dropdown (`linkedin` | `naukri`).
- Shared fields: keywords, location, max jobs, workplace (mapped per source), sort recent when supported.
- LinkedIn-only filters (job type, experience enums, company, details) still apply for LinkedIn; Naukri uses what the actor supports.
- Same `APIFY_TOKEN`.
- Load past search restores `source`.

## Data

- `jobs.source` TEXT (`linkedin` / `naukri`)
- `job_id` namespaced: `linkedin:…` / `naukri:…`
- Existing rows migrated to `source=linkedin` and prefixed ids.

## Architecture

- `sources/linkedin.py`, `sources/naukri.py` — actor id, `build_input()`, `normalize_items()`
- `scraper.py` — selects adapter by `--source`
- Dashboard: show Source; optional sidebar filter

## Actors

- LinkedIn: `automation-lab/linkedin-jobs-scraper`
- Naukri: `automation-lab/naukri-scraper` (same org; input: keyword, location, maxJobs, …)
