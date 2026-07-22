"""Helpers for job postedAt values (relative strings and absolute ISO dates)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_RELATIVE_PUBLISHED = re.compile(
    r"^\s*(\d+)\s+(minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)\s+ago\s*$",
    re.IGNORECASE,
)

_UNIT_SECONDS = {
    "minute": 60,
    "minutes": 60,
    "hour": 3600,
    "hours": 3600,
    "day": 86400,
    "days": 86400,
    "week": 604800,
    "weeks": 604800,
    "month": 2592000,  # ~30 days — boards round coarsely
    "months": 2592000,
    "year": 31536000,
    "years": 31536000,
}

_JUST_POSTED = frozenset(
    {
        "just now",
        "now",
        "today",
        "just posted",
        "posted today",
    }
)

# Naukri/etc. hiring-window phrases — not a publish date
_NON_PUBLISHED = re.compile(
    r"^\s*starts?\s+(in|within)\b",
    re.IGNORECASE,
)


def _parse_iso(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    # Date-only YYYY-MM-DD
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def relative_age_seconds(value: object) -> float | None:
    """Parse board-style '2 days ago' into age in seconds. None if not relative."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in _JUST_POSTED:
        return 0.0
    match = _RELATIVE_PUBLISHED.match(text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    return float(amount * _UNIT_SECONDS[unit])


def to_absolute_published(
    posted_at: object,
    reference: datetime | str | None = None,
) -> datetime | None:
    """Resolve postedAt to an absolute UTC datetime.

    - ISO timestamps / YYYY-MM-DD are parsed directly.
    - Relative strings ('3 days ago', 'Just posted') are subtracted from
      ``reference`` (scrape time).
    - Non-date phrases ('Starts within 1 month') return None.
    """
    if posted_at is None:
        return None
    text = str(posted_at).strip()
    if not text:
        return None

    if _NON_PUBLISHED.match(text):
        return None

    absolute = _parse_iso(text)
    if absolute is not None:
        return absolute

    age = relative_age_seconds(text)
    if age is None:
        return None

    if reference is None:
        ref = datetime.now(timezone.utc)
    elif isinstance(reference, str):
        ref = _parse_iso(reference) or datetime.now(timezone.utc)
    else:
        ref = reference if reference.tzinfo else reference.replace(tzinfo=timezone.utc)
        ref = ref.astimezone(timezone.utc)

    return ref - timedelta(seconds=age)


def normalize_published_for_storage(
    posted_at: object,
    reference: datetime | str | None = None,
) -> str | None:
    """Store-only form: UTC ISO-8601 string, or None if unknown."""
    absolute = to_absolute_published(posted_at, reference)
    if absolute is None:
        return None
    return absolute.isoformat()


def format_published_ago(
    posted_at: object,
    reference: datetime | str | None = None,
    *,
    now: datetime | None = None,
) -> str:
    """UI-friendly relative age only, e.g. '3 days ago'."""
    absolute = to_absolute_published(posted_at, reference)
    if absolute is None:
        return "Unknown"
    now = now or datetime.now(timezone.utc)
    age = max(0.0, (now - absolute).total_seconds())
    return _format_relative(age)


def format_published_display(
    posted_at: object,
    reference: datetime | str | None = None,
    *,
    now: datetime | None = None,
) -> str:
    """Human-readable published date: '2026-07-17 · 3 days ago'."""
    absolute = to_absolute_published(posted_at, reference)
    if absolute is None:
        text = "" if posted_at is None else str(posted_at).strip()
        if text and not _NON_PUBLISHED.match(text):
            return text
        return "Unknown"

    now = now or datetime.now(timezone.utc)
    age = max(0.0, (now - absolute).total_seconds())
    relative = _format_relative(age)
    return f"{absolute.date().isoformat()} · {relative}"


def _format_relative(age_seconds: float) -> str:
    if age_seconds < 60:
        return "just now"
    minutes = int(age_seconds // 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = int(age_seconds // 3600)
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(age_seconds // 86400)
    if days < 14:
        return f"{days} day{'s' if days != 1 else ''} ago"
    weeks = int(days // 7)
    if weeks < 8:
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    months = max(1, int(days // 30))
    if months < 24:
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = max(1, int(days // 365))
    return f"{years} year{'s' if years != 1 else ''} ago"


def sort_key_published(
    posted_at: object,
    reference: datetime | str | None = None,
) -> float:
    """Sort key: epoch seconds (newer = larger). Missing dates sort last when reversed."""
    absolute = to_absolute_published(posted_at, reference)
    if absolute is None:
        return float("-inf")
    return absolute.timestamp()
