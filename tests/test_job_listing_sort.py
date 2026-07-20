"""Tests for published-date resolution and Job Listings sorting."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app as dashboard  # noqa: E402
from posted_dates import (  # noqa: E402
    format_published_display,
    relative_age_seconds,
    to_absolute_published,
)


def test_relative_age_seconds_orders_relative_dates():
    assert relative_age_seconds("50 minutes ago") < relative_age_seconds("1 hour ago")
    assert relative_age_seconds("1 hour ago") < relative_age_seconds("10 hours ago")
    assert relative_age_seconds("10 hours ago") < relative_age_seconds("1 day ago")
    assert relative_age_seconds("1 day ago") < relative_age_seconds("6 days ago")
    assert relative_age_seconds("just now") == 0.0
    assert relative_age_seconds("") is None
    assert relative_age_seconds(None) is None


def test_to_absolute_published_from_relative_and_scrape_time():
    scraped = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
    absolute = to_absolute_published("2 days ago", scraped)
    assert absolute == datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


def test_to_absolute_published_keeps_iso():
    absolute = to_absolute_published("2026-07-18T12:00:00+00:00")
    assert absolute == datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)


def test_format_published_display_shows_calendar_and_live_relative():
    scraped = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
    text = format_published_display("2 days ago", scraped, now=now)
    assert text.startswith("2026-07-18")
    assert "2 days ago" in text


def test_sort_jobs_by_published_newest_first():
    df = pd.DataFrame(
        {
            "Title": ["A", "B", "C", "D"],
            "Published": ["x", "x", "x", "x"],
            "_published_raw": ["6 days ago", "1 hour ago", "2 days ago", "50 minutes ago"],
            "_scraped_at": ["2026-07-20T12:00:00+00:00"] * 4,
        }
    )
    sorted_df = dashboard.sort_jobs_df(df, "Published", ascending=True)
    assert sorted_df["_published_raw"].tolist() == [
        "50 minutes ago",
        "1 hour ago",
        "2 days ago",
        "6 days ago",
    ]


def test_sort_jobs_by_published_oldest_first():
    df = pd.DataFrame(
        {
            "Title": ["A", "B", "C"],
            "Published": ["x", "x", "x"],
            "_published_raw": ["1 day ago", "6 days ago", "2 hours ago"],
            "_scraped_at": ["2026-07-20T12:00:00+00:00"] * 3,
        }
    )
    sorted_df = dashboard.sort_jobs_df(df, "Published", ascending=False)
    assert sorted_df["_published_raw"].tolist() == [
        "6 days ago",
        "1 day ago",
        "2 hours ago",
    ]
