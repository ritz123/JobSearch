"""
Job Scraper — LinkedIn & Naukri via Apify.

Usage:
    python scraper.py --source linkedin --keywords "data engineer" --location "Remote"
    python scraper.py --source naukri --keywords "python developer" --location "bangalore" --max-jobs 50
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

import pandas as pd
from apify_client import ApifyClient
from dotenv import load_dotenv

_original_excepthook = threading.excepthook


def _thread_excepthook(args):
    if "TimeoutException" in type(args.exc_value).__name__:
        return
    _original_excepthook(args)


threading.excepthook = _thread_excepthook

from database import DEFAULT_DB, init_db, save_jobs, save_search  # noqa: E402
from sources import get_adapter  # noqa: E402
from sources.linkedin import (  # noqa: E402
    DATE_POSTED_MAP,
    EXPERIENCE_MAP,
    JOB_TYPE_MAP,
    WORKPLACE_MAP,
)

OUTPUT_FIELDS = [
    "title",
    "companyName",
    "location",
    "workplaceType",
    "employmentType",
    "postedAt",
    "salary",
    "url",
    "companyUrl",
    "descriptionText",
    "source",
]


def run_actor(token: str, actor_id: str, run_input: dict, source: str) -> list[dict]:
    client = ApifyClient(token)

    print(f"\n  Source  : {source}")
    print(f"  Actor   : {actor_id}")
    query = run_input.get("searchQuery") or run_input.get("keyword")
    print(f"  Query   : {query} @ {run_input.get('location')}")
    print(f"  Max jobs: {run_input.get('maxJobs')}")
    print("\nStarting Apify actor run — this may take 1-3 minutes...\n")

    run = client.actor(actor_id).call(run_input=run_input)

    status = run.status if hasattr(run, "status") else run.get("status")
    dataset_id = (
        run.default_dataset_id
        if hasattr(run, "default_dataset_id")
        else run["defaultDatasetId"]
    )

    if status != "SUCCEEDED":
        print(f"[ERROR] Actor run finished with status: {status}", file=sys.stderr)
        sys.exit(1)

    items = list(client.dataset(dataset_id).iterate_items())
    print(f"Fetched {len(items)} job listings from dataset {dataset_id}")
    return items


def flatten_item(item: dict) -> dict:
    flat = {}
    for field in OUTPUT_FIELDS:
        value = item.get(field, "")
        if field == "descriptionText" and isinstance(value, str):
            value = value[:300].replace("\n", " ").strip() + ("..." if len(value) > 300 else "")
        flat[field] = value if value is not None else ""
    return flat


def save_to_db(
    items: list[dict],
    keywords: str,
    location: str,
    filters: dict,
    db_path: Path,
) -> None:
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
    display_cols = [
        "source", "title", "companyName", "location",
        "workplaceType", "employmentType", "postedAt", "salary",
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    subset = df[display_cols].copy()
    subset.index = range(1, len(subset) + 1)

    try:
        from tabulate import tabulate
        print("\n" + tabulate(subset, headers="keys", tablefmt="rounded_outline", maxcolwidths=30))
    except ImportError:
        print(subset.to_string())

    print(f"\n{'─'*60}")
    print(f"  Total jobs found : {len(df)}")
    if "source" in df.columns:
        for src, count in df["source"].value_counts().items():
            print(f"  {src:<20}: {count}")
    print(f"{'─'*60}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Job Scraper — LinkedIn & Naukri via Apify",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py --source linkedin --keywords "data engineer" --location "San Francisco"
  python scraper.py --source naukri --keywords "python developer" --location "bangalore" --max-jobs 50
  python scraper.py --source naukri --keywords "SEO" --location "bangalore" --workplace remote
        """,
    )

    parser.add_argument(
        "--source",
        choices=["linkedin", "naukri"],
        default="linkedin",
        help="Job board to scrape (default: linkedin)",
    )
    parser.add_argument("--keywords", required=True, help='Job title or keyword, e.g. "software engineer"')
    parser.add_argument("--location", required=True, help='Location, e.g. "bangalore", "Remote", "India"')
    parser.add_argument("--max-jobs", type=int, default=25, metavar="N", help="Maximum jobs to fetch (default: 25)")
    parser.add_argument("--job-type", choices=list(JOB_TYPE_MAP.keys()), default=None, help="LinkedIn: employment type")
    parser.add_argument(
        "--workplace",
        choices=list(WORKPLACE_MAP.keys()),
        default=None,
        help="Workplace type (on_site / remote / hybrid)",
    )
    parser.add_argument(
        "--date-posted",
        choices=list(DATE_POSTED_MAP.keys()),
        default="any",
        help="LinkedIn: recency filter (default: any)",
    )
    parser.add_argument(
        "--experience",
        choices=list(EXPERIENCE_MAP.keys()),
        default=None,
        help="LinkedIn: experience level",
    )
    parser.add_argument("--company", default=None, help="LinkedIn: company filter")
    parser.add_argument("--details", action="store_true", help="LinkedIn: fetch full descriptions")
    parser.add_argument("--sort-recent", action="store_true", help="Prefer newest listings when supported")
    parser.add_argument("--output", default=None, metavar="FILE", help="Also export .csv / .json")
    parser.add_argument("--db", default=str(DEFAULT_DB), metavar="PATH", help=f"SQLite DB (default: {DEFAULT_DB.name})")
    parser.add_argument("--token", default=None, help="Apify API token (overrides APIFY_TOKEN)")

    return parser.parse_args()


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

    adapter = get_adapter(args.source)
    run_input = adapter.build_input(args)
    raw_items = run_actor(token, adapter.actor_id, run_input, adapter.name)
    items = adapter.normalize_items(raw_items)

    if not items:
        print("No jobs found. Try broadening your search filters.")
        sys.exit(0)

    filters = {
        k: v for k, v in vars(args).items()
        if k not in ("keywords", "location", "token", "output", "db")
        and v is not None
    }

    print()
    db_path = Path(args.db)
    save_to_db(items, args.keywords, args.location, filters, db_path)

    df = export_results(items, args.output)
    print_summary(df)


if __name__ == "__main__":
    main()
