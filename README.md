# LinkedIn Job Scraper — Powered by Apify

Scrapes LinkedIn job listings via [Apify](https://apify.com), stores them in a local SQLite database, and provides both a web dashboard and CLI tools to browse the data.

## Features

- **Apify-powered scraping** — no LinkedIn API credentials needed
- **SQLite storage with deduplication** — re-running the same search never duplicates rows
- **Streamlit web dashboard** — filter, sort, and visualise your job database in the browser
- **In-browser scraper controls** — run searches and watch live output without touching the terminal
- **CLI tools** — query and export jobs from the command line (`query.py`)
- **One-command setup** — `run_dashboard.sh` uses `uv` to install dependencies automatically on first launch

## Prerequisites

- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) for package and environment management — installed automatically by `setup.sh` if not present
- Node.js v18+ *(required by the Apify MCP server — not the scraper itself)*
- An Apify account + API token → [console.apify.com/account/integrations](https://console.apify.com/account/integrations)

## Quick Start

```bash
# 1. Clone or enter the project directory
git clone <repo-url> && cd Apify   # or just: cd Apify

# 2. Add your Apify token
cp .env.example .env
# Edit .env and set: APIFY_TOKEN=apify_api_...

# 3. Launch the dashboard (setup runs automatically on first launch)
./run_dashboard.sh
```

`run_dashboard.sh` creates the virtual environment and installs dependencies if they aren't already present — no need to run `setup.sh` manually. Dependencies are managed by `uv` via `pyproject.toml`.

## Runner Scripts

| Script | Purpose | Example |
|---|---|---|
| `run_dashboard.sh` | Start the Streamlit web dashboard (auto-setup on first run) | `./run_dashboard.sh` |
| `run_scraper.sh` | Run the CLI scraper via `uv run` (auto-setup on first run) | `./run_scraper.sh --keywords "data engineer" --location "Remote"` |
| `query_db.sh` | Query the local database (defaults to `stats` with no args) | `./query_db.sh list --keyword "python"` |
| `setup.sh` | One-time setup: install `uv` if needed, `uv sync`, copy `.env.example` | `./setup.sh` |

## Web Dashboard

### Jobs Explorer (`app.py`) — `http://localhost:8501`

The main dashboard page.

- **Sidebar filters** — keyword (searches title + description), company, location, workplace type, max results; changes apply on "Apply Filters"
- **Jobs Table tab** — sortable dataframe with clickable LinkedIn links and a one-click CSV download
- **Stats & Charts tab** — four headline metrics (total jobs, total searches, unique companies, unique locations), top-10 companies bar chart, top-10 locations bar chart, workplace-type donut chart, and a recent-searches table
- **Job Detail tab** — select any job from a dropdown to see the full card: title, company, location, workplace, contract type, salary, publication date, LinkedIn link, and the full job description in an expandable panel

### Run Scraper (`pages/2_Run_Scraper.py`) — sidebar nav

Run new scrapes without leaving the browser.

- **Form fields** — keywords, location, max jobs slider, workplace, job type, date posted, experience level, company filter, fetch-descriptions checkbox, sort-by-recent checkbox
- **Live output** — progress streams into the page in real time while the actor runs
- **Scraper history** — table of recent searches (timestamp, keywords, location, jobs fetched) shown below the form; "Refresh" button reloads it
- **APIFY_TOKEN warning** — a banner appears at the top if the token is not set, with setup instructions

## CLI Reference

### `scraper.py`

Fetches jobs from LinkedIn via Apify and saves them to the database.

```bash
python scraper.py --keywords "machine learning engineer" --location "Remote" --max-jobs 50
```

| Flag | Default | Description |
|---|---|---|
| `--keywords` | **required** | Job title or keyword |
| `--location` | **required** | City, country, or "Remote" |
| `--max-jobs N` | `25` | Maximum number of listings to fetch |
| `--job-type` | any | `full_time`, `part_time`, `contract`, `temporary`, `internship`, `volunteer`, `other` |
| `--workplace` | any | `on_site`, `remote`, `hybrid` |
| `--date-posted` | `any` | `day`, `week`, `month` |
| `--experience` | any | `internship`, `entry`, `associate`, `mid_senior`, `director`, `executive` |
| `--company` | any | Company name(s), comma-separated |
| `--details` | off | Fetch full job descriptions (slower, more data) |
| `--sort-recent` | off | Sort by most recent (default: relevance) |
| `--output FILE` | none | Also export to `.csv` or `.json`; results always go to the DB |
| `--db PATH` | `jobs.db` | Path to the SQLite database file |
| `--token` | env var | Apify API token (overrides `APIFY_TOKEN` in `.env`) |

### `query.py`

Browse and export jobs already stored in the database.

```bash
python query.py <command> [filters]
```

| Command | Description | Example |
|---|---|---|
| `stats` | Print a summary: total jobs/searches, top companies, top locations, recent searches | `python query.py stats` |
| `list` | Print a formatted table of matching jobs | `python query.py list --keyword "python" --workplace remote --limit 20` |
| `export` | Export matching jobs to CSV or JSON | `python query.py export --keyword "data scientist" --output ds_jobs.csv` |

**Shared filters** (apply to `list` and `export`):

| Flag | Description |
|---|---|
| `--keyword TEXT` | Filter by keyword in title or description |
| `--company TEXT` | Filter by company name (partial match) |
| `--location TEXT` | Filter by location (partial match) |
| `--workplace TEXT` | Filter by workplace type (`remote`, `on_site`, `hybrid`) |
| `--limit N` | Max rows to return (default: `50`) |
| `--db PATH` | Database file path (default: `jobs.db`) |

**Export-only**:

| Flag | Description |
|---|---|
| `--output FILE` | Output file (`.csv` or `.json`, default: `export.csv`) |

## Configuration

Set your Apify API token using either method:

**Option A — `.env` file (recommended)**

```bash
cp .env.example .env
# Edit .env:
APIFY_TOKEN=apify_api_xxxxxxxxxxxxxxxxxxxx
```

**Option B — shell environment variable**

```bash
export APIFY_TOKEN=apify_api_xxxxxxxxxxxxxxxxxxxx
```

The token can also be passed directly per-run with `--token apify_api_...`.

## Database

The SQLite database (`jobs.db`) contains two tables:

| Table | Description |
|---|---|
| `searches` | One row per actor run — stores keywords, location, filters (JSON), job count, and timestamp |
| `jobs` | One row per unique LinkedIn job — deduplicated by the numeric job ID extracted from the job URL |

**Deduplication** is handled by `INSERT OR IGNORE` on the `job_id` column. Running the same search multiple times will only insert new listings; existing ones are counted as skipped and reported in the terminal output.

To use a custom database path, pass `--db /path/to/custom.db` to either `scraper.py` or `query.py`.

## Project Structure

```
Apify/
├── app.py                  # Streamlit dashboard — Jobs Explorer (main page)
├── pages/
│   └── 2_Run_Scraper.py    # Streamlit page — in-browser scraper controls
├── scraper.py              # CLI scraper — fetches jobs via Apify, saves to DB
├── query.py                # CLI query tool — browse and export the database
├── database.py             # SQLite persistence layer (schema, read/write helpers)
├── pyproject.toml          # Project metadata and dependencies (uv)
├── requirements.txt        # Reference only — project uses uv + pyproject.toml
├── .env.example            # Token template — copy to .env and fill in
├── setup.sh                # One-time setup: uv venv + uv sync + .env copy
├── run_dashboard.sh        # Launch Streamlit dashboard (auto-setup on first run)
├── run_scraper.sh          # Run scraper.py via uv run
└── query_db.sh             # Run query.py via uv run
```

## Cost

LinkedIn scraping on Apify costs roughly **$0.002–$0.01 per job listing**.
The free tier includes enough credits to run several searches. Monitor usage at [console.apify.com/billing](https://console.apify.com/billing).
