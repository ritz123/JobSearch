"""
query.py — Browse, filter and export jobs stored in the local SQLite database.

Usage:
    python query.py stats
    python query.py list
    python query.py list --keyword "data engineer" --workplace remote --limit 20
    python query.py list --company "Google" --location "New York"
    python query.py export --keyword "ML" --output ml_jobs.csv
    python query.py export --output all_jobs.json
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

from database import DEFAULT_DB, get_stats, init_db, query_jobs

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_stats(db_path: Path) -> None:
    stats = get_stats(db_path)

    print(f"\n{'═'*55}")
    print(f"  Database : {db_path.resolve()}")
    print(f"{'─'*55}")
    print(f"  Total jobs stored : {stats['total_jobs']}")
    print(f"  Total searches run: {stats['total_searches']}")

    if stats["workplace_distribution"]:
        print(f"\n  Workplace breakdown:")
        for row in stats["workplace_distribution"]:
            label = row["workplace_type"] or "Unknown"
            print(f"    {label:<20} {row['n']}")

    if stats["top_companies"]:
        print(f"\n  Top companies:")
        for row in stats["top_companies"]:
            print(f"    {row['company']:<35} {row['n']}")

    if stats["top_locations"]:
        print(f"\n  Top locations:")
        for row in stats["top_locations"]:
            print(f"    {row['location']:<35} {row['n']}")

    if stats["recent_searches"]:
        print(f"\n  Recent searches:")
        for row in stats["recent_searches"]:
            print(f"    [{row['ran_at'][:19]}]  \"{row['keywords']}\" @ {row['location']}  ({row['job_count']} jobs)")

    print(f"{'═'*55}\n")


def print_jobs(rows, limit: int) -> None:
    if not rows:
        print("No jobs matched your filters.")
        return

    display = ["title", "company", "location", "workplace_type", "contract_type", "published_at", "salary"]
    data = [{col: (row[col] or "") for col in display} for row in rows]
    df = pd.DataFrame(data)
    df.index = range(1, len(df) + 1)

    try:
        from tabulate import tabulate
        print("\n" + tabulate(df, headers="keys", tablefmt="rounded_outline", maxcolwidths=28))
    except ImportError:
        print(df.to_string())

    print(f"\n  Showing {len(rows)} job(s){' (limit reached)' if len(rows) == limit else ''}.\n")


def export_jobs(rows, output_path: str) -> None:
    if not rows:
        print("No jobs matched your filters — nothing exported.")
        return

    cols = [
        "id", "job_id", "title", "company", "location", "workplace_type",
        "contract_type", "published_at", "salary", "job_url", "company_url",
        "description", "scraped_at", "search_keywords", "search_location",
    ]
    data = [{col: row[col] for col in cols if col in row.keys()} for row in rows]
    df = pd.DataFrame(data)

    path = Path(output_path)
    if path.suffix.lower() == ".json":
        df.to_json(path, orient="records", indent=2, force_ascii=False)
    else:
        path = path.with_suffix(".csv")
        df.to_csv(path, index=False)

    print(f"\nExported {len(df)} jobs → {path.resolve()}\n")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query the local LinkedIn jobs database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  stats   Show database summary (total jobs, top companies, recent searches)
  list    Print a table of matching jobs in the terminal
  export  Export matching jobs to a CSV or JSON file

Examples:
  python query.py stats
  python query.py list --keyword "python" --workplace remote
  python query.py list --company "Stripe" --limit 50
  python query.py export --keyword "data scientist" --output ds_jobs.csv
  python query.py export --output all_jobs.json
        """,
    )

    parser.add_argument(
        "command",
        choices=["stats", "list", "export"],
        help="Action to perform",
    )

    # Shared filters
    parser.add_argument("--keyword", default=None, help="Filter by keyword in title or description")
    parser.add_argument("--company", default=None, help="Filter by company name")
    parser.add_argument("--location", default=None, help="Filter by location")
    parser.add_argument("--workplace", default=None, help="Filter by workplace type (remote, on_site, hybrid)")
    parser.add_argument("--limit", type=int, default=50, help="Max rows to return (default: 50)")

    # Export-only
    parser.add_argument("--output", default="export.csv", metavar="FILE", help="Output file for export command (.csv or .json)")

    # DB path
    parser.add_argument("--db", default=str(DEFAULT_DB), metavar="PATH", help=f"Database file (default: {DEFAULT_DB.name})")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)

    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path.resolve()}")
        print("Run scraper.py first to populate it.")
        sys.exit(1)

    init_db(db_path)

    if args.command == "stats":
        print_stats(db_path)

    elif args.command in ("list", "export"):
        rows = query_jobs(
            keyword=args.keyword,
            company=args.company,
            location=args.location,
            workplace=args.workplace,
            limit=args.limit,
            db_path=db_path,
        )

        if args.command == "list":
            print_jobs(rows, args.limit)
        else:
            export_jobs(rows, args.output)


if __name__ == "__main__":
    main()
