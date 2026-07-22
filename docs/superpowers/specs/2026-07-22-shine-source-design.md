# Shine.com source — Design

## Goal

Add **Shine.com** as a scrape source via Apify, same adapter pattern as LinkedIn / Naukri / Indeed.

## Actor

- **ID:** `unfenced-group/shine-scraper`
- Auth: existing `APIFY_TOKEN`

## Behavior

- Scraper UI / CLI / `POST /api/scrape`: source option `shine`.
- Shared filters:
  - `keywords` → `searchQuery`
  - `location` → `location` (strip LinkedIn-style work-mode tokens like Naukri so `"Bangalore, remote"` → city `Bangalore`)
  - `max_jobs` → `maxItems` (OpenAPI field; actor max results)
  - `date_posted` → `daysOld`: `day`→1, `week`→7, `month`→30; `any`/unset → omit or `0`
  - `workplace` → **post-filter** after normalize (actor has no workMode input): keep jobs whose `workMode` matches (`remote` / `hybrid` / `on_site` ↔ Remote / Hybrid / On-site). Also treat employmentType `Work from Home` as remote when filtering remote.
  - `details` → `fetchDetails` (optional full JD pages)
- LinkedIn-only filters (job_type enums, experience, company) ignored for Shine.
- Jobs Explorer source filter includes `shine`.
- Job ids: `shine:<id>`; `source` column = `shine`.

## Normalize (shared job shape)

Map actor fields → existing dict keys used by `save_jobs`:

| Shared | Actor |
|--------|--------|
| id | `id` |
| source | `"shine"` |
| title | `title` |
| companyName | `company` |
| location | `city` or join `locations` |
| workplaceType | lowercased `workMode` (`on-site`→`on_site`) |
| employmentType | `jobType` or `employmentType` |
| postedAt | `publishDateISO` or `publishDate` |
| salary | `salaryRaw` or min–max INR |
| url | `url` |
| companyUrl | none (actor excludes) |
| descriptionText | `descriptionText` |

## Out of scope

- Custom Shine start URLs in the UI
- Google/other boards
- Changing Apify billing / skipReposts (leave actor defaults)

## Testing

- Unit: `get_adapter("shine")`, `build_input` mappings, `normalize_items`, workplace post-filter, location sanitize.
- No live Apify call in CI.
