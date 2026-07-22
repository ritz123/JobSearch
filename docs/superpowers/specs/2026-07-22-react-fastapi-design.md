# React SPA + FastAPI — Design

## Goal

Replace Streamlit with a client-rendered React UI. Python remains for scraping, SQLite, and City Careers pipeline, exposed via FastAPI.

## Decisions

| Topic | Choice |
|---|---|
| Frontend | Vite + React + TypeScript SPA (`web/`) |
| Backend | FastAPI (`api/`) wrapping existing modules |
| Streamlit | Delete immediately |
| DB | Same `jobs.db` |
| Long jobs (v1) | Synchronous request/response |

## Architecture

```text
Browser (React :5173) ──► FastAPI (:8000) ──► database / scraper / city_pipeline
```

## API

- `GET /api/health`
- `GET /api/jobs` — filters
- `GET /api/stats`
- `GET /api/searches`
- `POST /api/scrape` — LinkedIn/Naukri
- `GET /api/ollama/models`
- `POST /api/city-runs`
- `GET /api/city-runs`
- `GET /api/companies`

## UI routes

- `/` Jobs explorer
- `/scraper` Run scraper
- `/city-careers` City careers

## Run

`./run_web.sh` starts API + Vite. CLI `scraper.py` / `query.py` unchanged.

## Out of scope (v1)

Auth, production deploy, Google Places, SSE progress streaming.
