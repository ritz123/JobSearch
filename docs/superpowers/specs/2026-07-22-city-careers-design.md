# City Careers Pipeline — Design

## Goal

Accept a city name, discover companies in that city via OpenStreetMap (Overpass), find each company’s careers page, extract openings with a local Ollama model, and store results in the existing SQLite database for browsing in Streamlit.

## Decisions

| Topic | Choice |
|---|---|
| Company discovery | OSM / Overpass (+ Nominatim); Google Places later |
| Job extraction | Generic careers crawl + Ollama (local) |
| Company filter | Configurable; default tech/corporate-leaning |
| UI | New Streamlit page |
| Recency | Keep history; UI defaults to jobs seen in last N days |
| Scale (v1 default) | Cap ~15 companies per run |
| Storage | Same `jobs.db`; `source=company_site` |

## Architecture

```text
[Streamlit: City Careers]
        │
        ▼
  city_pipeline.run(city, filters, max_companies)
        │
        ├─► overpass.find_companies(city)
        ├─► careers.find_careers_url(website)
        ├─► fetch page text
        ├─► ollama.extract_jobs(text)
        └─► database.save_* (companies, jobs, city_runs)
```

### Modules

- `sources/overpass.py` — city → companies (name, website, lat/lon, tags)
- `careers/` — careers URL discovery, HTTP fetch, Ollama JSON extract, normalize
- `city_pipeline.py` — orchestration + progress callbacks
- `pages/3_City_Careers.py` — Streamlit UI

LinkedIn/Naukri Apify scrapers unchanged. Google Places deferred.

## Data model

### `city_runs`

One row per city scrape: `id`, `city`, `filters` (JSON), `max_companies`, `companies_found`, `jobs_found`, `ran_at`, `status` (`running` / `succeeded` / `partial` / `failed`), `notes`.

### `companies`

Deduped by normalized website (fallback OSM id): `id`, `osm_id`, `name`, `website`, `city`, `lat`, `lon`, `tags` (JSON), `careers_url`, `last_seen_at`, `created_at`.

### `jobs` (existing)

- `source = 'company_site'`
- `job_id = company_site:<hash of company_id + job_url or title>`
- Optional `city_run_id` column
- Re-scrape bumps `scraped_at` (soft-recent filter)

Soft-recent UI: default `scraped_at >= now - N days` (default N=14).

## Pipeline behavior

1. Nominatim geocode city → Overpass query for office/company-ish tags with a website.
2. Apply filter preset; take up to `max_companies` (default 15).
3. Upsert companies; try careers paths (`/careers`, `/jobs`, `/join-us`, homepage “careers” links).
4. Fetch HTML → text (truncated for Ollama).
5. Ollama returns JSON list: `{title, location, url, posted_at?, description?}`.
6. Upsert jobs; bump `scraped_at` on re-see.

### Streamlit page

Inputs: city, filter preset, max companies, Ollama model, recent-days. Live progress. Tabs: companies | recent jobs | past runs. Jobs Explorer gains `company_site` source filter.

### Config

`OLLAMA_BASE_URL` (default `http://localhost:11434`), `OLLAMA_MODEL` (default e.g. `llama3.2`).

## Errors

Per-company isolation. Fail early if Nominatim/Overpass empty or Ollama unreachable. Skip missing website/careers/HTTP errors. Retry invalid Ollama JSON once. Partial success → `status=partial`. Polite crawl: short delays, identifiable User-Agent, shallow crawl only.

## Testing

Unit: Overpass query builder, website normalize, careers URL heuristics, Ollama JSON parse, job_id hash, last-N-days query. Integration with mocked HTTP/Ollama. Manual: one city with Ollama, ~15 companies.

## Out of scope (v1)

Google Places, ATS-specific scrapers, explicit “job closed” tracking beyond soft-recent, deep multi-page crawls.
