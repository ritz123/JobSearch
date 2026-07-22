# JobSearch — Apify scrapers + React dashboard

Scrapes LinkedIn / Naukri job listings via [Apify](https://apify.com), stores them in local SQLite, and provides a **React** web UI (FastAPI backend) plus CLI tools.

## Features

- **Apify-powered scraping** — LinkedIn and Naukri
- **SQLite storage with deduplication**
- **React dashboard** — Jobs explorer, Run Scraper, City Careers (OSM + Ollama)
- **CLI tools** — `query.py`, `scraper.py`
- **One-command web launch** — `./run_web.sh` (or `./run.sh`)

## Prerequisites

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv)
- Node.js 18+
- Apify API token → [console.apify.com/account/integrations](https://console.apify.com/account/integrations)
- Optional: [Ollama](https://ollama.com) for City Careers extraction

## Quick Start

```bash
cp .env.example .env
# Set APIFY_TOKEN=...

./run_web.sh
```

- UI: http://127.0.0.1:5173  
- API: http://127.0.0.1:8000  

`run_web.sh` runs `uv sync` via setup if needed, starts FastAPI, then the Vite React app.

## Runner Scripts

| Script | Purpose |
|---|---|
| `run_web.sh` / `run.sh` | FastAPI + React UI |
| `run_scraper.sh` | CLI scraper |
| `query_db.sh` | Query local DB |
| `setup.sh` | Install uv + Python deps |

## API (selected)

| Method | Path |
|---|---|
| GET | `/api/jobs` |
| GET | `/api/stats` |
| POST | `/api/scrape` |
| GET | `/api/ollama/models` |
| POST | `/api/city-runs` |

## CLI

```bash
./run_scraper.sh --source linkedin --keywords "data engineer" --location "Remote"
./query_db.sh list --keyword "python" --limit 20
```

See `scraper.py --help` and `query.py --help` for full flags.
