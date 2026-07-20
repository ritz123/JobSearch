# Re-run Past Search — Design

## Goal

Let the user reload a past scrape’s parameters into the Run Scraper form, edit them, then start a new run.

## Behavior

- Recent Searches lists recent runs with a **Load** button per row.
- **Load** prefills the form; it does **not** start scraping.
- Show a short confirmation after load.
- Missing fields on older rows (no `max_jobs` / `details` in filters JSON) use current defaults.

## Data

- `searches` already stores `keywords`, `location`, and `filters` (JSON).
- Going forward, `filters` also includes `max_jobs` and `details`.
- History query returns `id`, keywords, location, filters, job_count, ran_at (limit 10).

## UI / Flow

1. User clicks **Load** on a history row.
2. Params are written to `st.session_state` and the page reruns.
3. Form widgets (keyed) show the loaded values.
4. User edits as needed and clicks **Start Scraping** (existing path unchanged).

## Out of scope

- One-click immediate re-run without form review
- Bookmarkable / query-param deep links
- Editing or deleting history rows
