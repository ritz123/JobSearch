"""Tests for published-date resolution and sorting helpers."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from posted_dates import (  # noqa: E402
    format_published_ago,
    format_published_display,
    normalize_published_for_storage,
    relative_age_seconds,
    sort_key_published,
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


def test_format_published_ago_days_only():
    scraped = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert format_published_ago("2 days ago", scraped, now=now) == "2 days ago"
    assert format_published_ago("Just posted", scraped, now=now) == "just now"


def test_normalize_storage_clears_non_dates_and_keeps_iso():
    scraped = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
    assert normalize_published_for_storage("Starts within 1 month", scraped) is None
    iso = normalize_published_for_storage("1 year ago", scraped)
    assert iso is not None
    assert iso.startswith("2025-07-")
    assert relative_age_seconds("1 year ago") == 31536000.0


def test_sort_key_published_orders_newest_first():
    scraped = "2026-07-20T12:00:00+00:00"
    rows = [
        ("6 days ago", scraped),
        ("1 hour ago", scraped),
        ("2 days ago", scraped),
        ("50 minutes ago", scraped),
    ]
    ordered = sorted(rows, key=lambda r: sort_key_published(r[0], r[1]), reverse=True)
    assert [r[0] for r in ordered] == [
        "50 minutes ago",
        "1 hour ago",
        "2 days ago",
        "6 days ago",
    ]
