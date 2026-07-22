"""Shine.com jobs via unfenced-group/shine-scraper."""

from __future__ import annotations

import re
from typing import Any

ACTOR_ID = "unfenced-group/shine-scraper"

DATE_POSTED_MAP = {
    "day": 1,
    "week": 7,
    "month": 30,
}

# Shared UI workplace → Shine workMode labels (for post-filter)
WORKPLACE_FILTER = {
    "remote": {"remote", "work from home"},
    "hybrid": {"hybrid"},
    "on_site": {"on-site", "onsite", "on site", "office"},
}

_WORK_MODE_TOKENS = {
    "remote": "remote",
    "work from home": "remote",
    "wfh": "remote",
    "hybrid": "hybrid",
    "on site": "on_site",
    "onsite": "on_site",
    "office": "on_site",
    "in office": "on_site",
}
_SKIP_LOCATION_TOKENS = frozenset({"india", "anywhere", "any", "all", "n/a", "na"})


def _first(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _norm_token(value: str) -> str:
    return re.sub(r"[\s_\-]+", " ", value.strip().lower())


def sanitize_shine_location(raw: str | None) -> tuple[str, str | None]:
    """Split LinkedIn-style locations into a Shine city + optional workplace.

    Returns (location, inferred_workplace). Empty location = all India.
    """
    text = (raw or "").strip()
    if not text:
        return "", None

    parts = [p.strip() for p in re.split(r"[,/|]", text) if p.strip()]
    cities: list[str] = []
    inferred: str | None = None
    for part in parts:
        token = _norm_token(part)
        if token in _WORK_MODE_TOKENS:
            inferred = inferred or _WORK_MODE_TOKENS[token]
            continue
        if token in _SKIP_LOCATION_TOKENS:
            continue
        cities.append(part)

    return (cities[0] if cities else ""), inferred


def _normalize_work_mode(raw: str | None) -> str | None:
    if not raw:
        return None
    token = _norm_token(str(raw))
    if token in {"remote", "work from home", "wfh"}:
        return "remote"
    if token == "hybrid":
        return "hybrid"
    if token in {"on-site", "onsite", "on site", "office", "in office"}:
        return "on_site"
    return token.replace(" ", "_")


def _location_text(item: dict) -> str | None:
    city = item.get("city")
    if isinstance(city, str) and city.strip():
        return city
    locations = item.get("locations")
    if isinstance(locations, list) and locations:
        return ", ".join(str(x) for x in locations if x)
    if isinstance(locations, str) and locations.strip():
        return locations
    return None


def _salary(item: dict) -> str | None:
    raw = item.get("salaryRaw")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    low = item.get("salaryMin")
    high = item.get("salaryMax")
    if low is not None or high is not None:
        currency = item.get("salaryCurrency") or "INR"
        period = item.get("salaryPeriod") or ""
        period_suffix = f"/{period}" if period else ""
        return f"{currency} {low or '?'} - {high or '?'}{period_suffix}"
    return None


def _matches_workplace(item: dict, workplace: str) -> bool:
    allowed = WORKPLACE_FILTER.get(workplace)
    if not allowed:
        return True
    mode = _norm_token(str(item.get("workMode") or ""))
    if mode in allowed:
        return True
    emp = _norm_token(str(item.get("employmentType") or ""))
    if workplace == "remote" and emp in {"work from home", "wfh", "remote"}:
        return True
    return False


class ShineSource:
    name = "shine"
    actor_id = ACTOR_ID

    def __init__(self) -> None:
        self._filter_workplace: str | None = None

    def build_input(self, args: Any) -> dict:
        location, inferred = sanitize_shine_location(getattr(args, "location", "") or "")
        workplace = getattr(args, "workplace", None) or inferred
        self._filter_workplace = workplace if workplace in WORKPLACE_FILTER else None

        run_input: dict = {
            "searchQuery": args.keywords,
            "maxItems": int(args.max_jobs),
        }
        if location:
            run_input["location"] = location

        date_posted = getattr(args, "date_posted", "any") or "any"
        if date_posted in DATE_POSTED_MAP:
            run_input["daysOld"] = DATE_POSTED_MAP[date_posted]

        if getattr(args, "details", False):
            run_input["fetchDetails"] = True

        return run_input

    def normalize_items(self, items: list[dict]) -> list[dict]:
        normalized = []
        for item in items:
            if self._filter_workplace and not _matches_workplace(item, self._filter_workplace):
                continue
            url = _first(item.get("url"), item.get("jobUrl"))
            job_id = _first(item.get("id"), item.get("jobId"))
            if job_id is not None:
                job_id = str(job_id)
            normalized.append(
                {
                    "id": job_id,
                    "source": self.name,
                    "title": item.get("title") or item.get("jobTitle"),
                    "companyName": _first(item.get("company"), item.get("companyName")),
                    "location": _location_text(item),
                    "workplaceType": _normalize_work_mode(
                        _first(item.get("workMode"), item.get("workplaceType"))
                    ),
                    "employmentType": _first(item.get("jobType"), item.get("employmentType")),
                    "postedAt": _first(
                        item.get("publishDateISO"),
                        item.get("publishDate"),
                        item.get("postedAt"),
                    ),
                    "salary": _salary(item),
                    "url": url,
                    "companyUrl": item.get("companyUrl"),
                    "descriptionText": _first(
                        item.get("descriptionText"),
                        item.get("description"),
                    ),
                }
            )
        return normalized
