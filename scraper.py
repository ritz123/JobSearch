"""
LinkedIn Job Scraper — powered by Apify
Scrapes LinkedIn job listings, stores them in a local SQLite database,
and optionally exports to CSV / JSON.

Usage:
    python scraper.py --keywords "machine learning engineer" --location "Remote" --max-jobs 50
    python scraper.py --keywords "data analyst" --location "New York" --job-type full_time --workplace remote
    python scraper.py --keywords "backend developer" --company "Stripe,Airbnb" --output jobs.csv
"""

import argparse
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd
from apify_client import ApifyClient
from dotenv import load_dotenv

# Suppress the noisy TimeoutException traceback from apify_client's internal
# log-streaming thread — it's cosmetic only and does not affect scraper results.
_original_excepthook = threading.excepthook

def _thread_excepthook(args):
    if "TimeoutException" in type(args.exc_value).__name__:
        return
    _original_excepthook(args)

threading.excepthook = _thread_excepthook

from database import DEFAULT_DB, init_db, save_jobs, save_search

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTOR_ID = "automation-lab/linkedin-jobs-scraper"

JOB_TYPE_MAP = {
    "full_time": "F",
    "part_time": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
    "volunteer": "V",
    "other": "O",
}

WORKPLACE_MAP = {
    "on_site": "1",
    "remote": "2",
    "hybrid": "3",
}

DATE_POSTED_MAP = {
    "any": "all",
    "day": "r86400",
    "week": "r604800",
    "month": "r2592000",
}

EXPERIENCE_MAP = {
    "internship": "1",
    "entry": "2",
    "associate": "3",
    "mid_senior": "4",
    "director": "5",
    "executive": "6",
}

# Fields to keep (in order) for display / export
# These match the actual field names returned by the automation-lab/linkedin-jobs-scraper actor.
OUTPUT_FIELDS = [
    "title",
    "companyName",
    "location",
    "workplaceType",
    "employmentType",
    "postedAt",
    "salary",
    "url",
    "companyLinkedinUrl",
    "descriptionText",
]

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def build_run_input(args: argparse.Namespace) -> dict:
    run_input: dict = {
        "searchQuery": args.keywords,
        "location": args.location,
        "maxJobs": args.max_jobs,
        "scrapeJobDetails": args.details,
        "sortBy": "DD" if args.sort_recent else "R",
    }

    if args.job_type:
        run_input["jobType"] = JOB_TYPE_MAP[args.job_type]

    if args.workplace:
        run_input["workplaceType"] = WORKPLACE_MAP[args.workplace]

    if args.date_posted != "any":
        run_input["datePosted"] = DATE_POSTED_MAP[args.date_posted]

    if args.experience:
        run_input["experienceLevel"] = EXPERIENCE_MAP[args.experience]

    if args.company:
        run_input["companyName"] = args.company

    return run_input


def run_scraper(token: str, run_input: dict) -> list[dict]:
    client = ApifyClient(token)

    print(f"\n  Actor   : {ACTOR_ID}")
    print(f"  Query   : {run_input.get('searchQuery')} @ {run_input.get('location')}")
    print(f"  Max jobs: {run_input.get('maxJobs')}")
    print("\nStarting Apify actor run — this may take 1-3 minutes...\n")

    run = client.actor(ACTOR_ID).call(run_input=run_input)

    # apify-client >= 1.0 returns a Pydantic Run object; fall back to dict access for older versions
    status = run.status if hasattr(run, "status") else run.get("status")
    dataset_id = run.default_dataset_id if hasattr(run, "default_dataset_id") else run["defaultDatasetId"]

    if status != "SUCCEEDED":
        print(f"[ERROR] Actor run finished with status: {status}", file=sys.stderr)
        sys.exit(1)

    items = list(client.dataset(dataset_id).iterate_items())

    print(f"Fetched {len(items)} job listings from dataset {dataset_id}")
    return items


def flatten_item(item: dict) -> dict:
    """Pick and rename fields for a cleaner output row."""
    flat = {}
    for field in OUTPUT_FIELDS:
        value = item.get(field, "")
        # Truncate description to 300 chars for readability in table view
        if field == "descriptionText" and isinstance(value, str):
            value = value[:300].replace("\n", " ").strip() + ("..." if len(value) > 300 else "")
        flat[field] = value if value is not None else ""
    return flat


def save_to_db(items: list[dict], keywords: str, location: str, filters: dict, db_path: Path) -> None:
    init_db(db_path)
    search_id = save_search(keywords, location, filters, len(items), db_path)
    inserted, skipped = save_jobs(items, search_id, db_path)
    print(f"Database     → {db_path.resolve()}")
    print(f"  Inserted   : {inserted} new jobs")
    if skipped:
        print(f"  Skipped    : {skipped} duplicates (already in DB)")


def export_results(items: list[dict], output_path: str | None) -> pd.DataFrame:
    rows = [flatten_item(item) for item in items]
    df = pd.DataFrame(rows, columns=OUTPUT_FIELDS)

    if output_path:
        path = Path(output_path)
        suffix = path.suffix.lower()
        if suffix == ".json":
            df.to_json(path, orient="records", indent=2, force_ascii=False)
        else:
            path = path.with_suffix(".csv")
            df.to_csv(path, index=False)
        print(f"File export  → {path.resolve()}")

    return df


def print_summary(df: pd.DataFrame) -> None:
    """Print a readable table of the top results to the terminal."""
    display_cols = ["title", "companyName", "location", "workplaceType", "employmentType", "postedAt", "salary"]
    subset = df[display_cols].copy()
    subset.index = range(1, len(subset) + 1)

    try:
        from tabulate import tabulate
        print("\n" + tabulate(subset, headers="keys", tablefmt="rounded_outline", maxcolwidths=30))
    except ImportError:
        print(subset.to_string())

    # Quick stats
    print(f"\n{'─'*60}")
    print(f"  Total jobs found : {len(df)}")
    if "workplaceType" in df.columns:
        wt_counts = df["workplaceType"].value_counts()
        for wt, count in wt_counts.items():
            if wt:
                print(f"  {wt:<20}: {count}")
    print(f"{'─'*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="LinkedIn Job Scraper — fetches job listings via Apify",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py --keywords "data engineer" --location "San Francisco"
  python scraper.py --keywords "ML engineer" --location "Remote" --workplace remote --max-jobs 100
  python scraper.py --keywords "backend engineer" --company "Stripe" --details --output stripe_jobs.json
  python scraper.py --keywords "intern" --job-type internship --date-posted week --sort-recent
        """,
    )

    # Required
    parser.add_argument("--keywords", required=True, help='Job title or keyword, e.g. "software engineer"')
    parser.add_argument("--location", required=True, help='Location, e.g. "New York", "Remote", "India"')

    # Filters
    parser.add_argument("--max-jobs", type=int, default=25, metavar="N", help="Maximum number of jobs to fetch (default: 25)")
    parser.add_argument(
        "--job-type",
        choices=list(JOB_TYPE_MAP.keys()),
        default=None,
        help="Filter by employment type",
    )
    parser.add_argument(
        "--workplace",
        choices=list(WORKPLACE_MAP.keys()),
        default=None,
        help="Filter by workplace type (on_site / remote / hybrid)",
    )
    parser.add_argument(
        "--date-posted",
        choices=list(DATE_POSTED_MAP.keys()),
        default="any",
        help="Filter by how recently the job was posted (default: any)",
    )
    parser.add_argument(
        "--experience",
        choices=list(EXPERIENCE_MAP.keys()),
        default=None,
        help="Filter by experience level",
    )
    parser.add_argument("--company", default=None, help='Filter by company name, e.g. "Google" or "Google,Meta"')

    # Behaviour
    parser.add_argument("--details", action="store_true", help="Fetch full job description (slower, more data)")
    parser.add_argument("--sort-recent", action="store_true", help="Sort results by most recent (default: relevance)")

    # Output
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help="Also export to a file (.csv or .json). Optional — results always go to the DB.",
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB),
        metavar="PATH",
        help=f"SQLite database file (default: {DEFAULT_DB.name})",
    )
    parser.add_argument("--token", default=None, help="Apify API token (overrides APIFY_TOKEN env var)")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    load_dotenv()
    args = parse_args()

    token = args.token or os.getenv("APIFY_TOKEN")
    if not token:
        print(
            "[ERROR] Apify token not found.\n"
            "  Set it via: export APIFY_TOKEN=apify_api_...\n"
            "  Or copy .env.example → .env and fill in your token.\n"
            "  Get your token at: https://console.apify.com/account/integrations",
            file=sys.stderr,
        )
        sys.exit(1)

    run_input = build_run_input(args)
    items = run_scraper(token, run_input)

    if not items:
        print("No jobs found. Try broadening your search filters.")
        sys.exit(0)

    # Build the filters dict for the search log (excludes keyword/location)
    filters = {
        k: v for k, v in vars(args).items()
        if k not in ("keywords", "location", "token", "output", "db", "max_jobs", "details")
        and v is not None
    }

    print()
    db_path = Path(args.db)
    save_to_db(items, args.keywords, args.location, filters, db_path)

    df = export_results(items, args.output)
    print_summary(df)


if __name__ == "__main__":
    main()
