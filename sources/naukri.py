"""Naukri.com jobs via automation-lab/naukri-scraper."""

from __future__ import annotations

import re
from typing import Any

ACTOR_ID = "automation-lab/naukri-scraper"

# Shared UI workplace values → Naukri workMode
WORKPLACE_MAP = {
    "on_site": "office",
    "remote": "remote",
    "hybrid": "hybrid",
}

# LinkedIn-style multi-value locations must not be passed through literally —
# "Bangalore, remote" becomes naukri.com/.../bangalore,-remote (0 useful hits).
_WORK_MODE_TOKENS = {
    "remote": "remote",
    "work from home": "remote",
    "wfh": "remote",
    "hybrid": "hybrid",
    "on site": "office",
    "onsite": "office",
    "office": "office",
    "in office": "office",
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


def sanitize_naukri_location(raw: str | None) -> tuple[str, str | None]:
    """Split LinkedIn-style locations into a Naukri city + optional workMode.

    Returns (location, inferred_work_mode). Empty location = all India.
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


def _salary(item: dict) -> str | None:
    salary = _first(item.get("salary"), item.get("salaryLabel"), item.get("salaryDisplay"))
    if salary:
        text = str(salary).strip()
        if text.lower() in {"not disclosed", "na", "n/a", "-", "none"}:
            pass
        else:
            return text
    low = item.get("salaryMin") or item.get("minSalary")
    high = item.get("salaryMax") or item.get("maxSalary")
    if low or high:
        return f"{low or '?'} - {high or '?'}"
    return None


def _infer_workplace(explicit: str | None, location: str | None) -> str | None:
    if explicit:
        return explicit
    loc = (location or "").strip().lower()
    if not loc:
        return None
    if loc in {"remote", "work from home", "wfh"} or loc.startswith("remote"):
        return "remote"
    if loc == "hybrid" or loc.startswith("hybrid"):
        return "hybrid"
    return None


class NaukriSource:
    name = "naukri"
    actor_id = ACTOR_ID

    def build_input(self, args: Any) -> dict:
        # Actor example: {"keyword": "python developer", "location": "bangalore", "maxJobs": 20}
        location, inferred_mode = sanitize_naukri_location(getattr(args, "location", "") or "")
        run_input: dict = {
            "keyword": args.keywords,
            "maxJobs": args.max_jobs,
        }
        if location:
            run_input["location"] = location

        workplace = getattr(args, "workplace", None)
        if workplace and workplace in WORKPLACE_MAP:
            run_input["workMode"] = WORKPLACE_MAP[workplace]
        elif inferred_mode:
            run_input["workMode"] = inferred_mode

        if getattr(args, "sort_recent", False):
            run_input["sortBy"] = "date"
        return run_input

    def normalize_items(self, items: list[dict]) -> list[dict]:
        normalized = []
        for item in items:
            job_id = _first(
                item.get("jobId"),
                item.get("id"),
                item.get("job_id"),
            )
            url = _first(item.get("url"), item.get("jobUrl"), item.get("jdURL"), item.get("jdUrl"))
            company = _first(item.get("companyName"), item.get("company"), item.get("company_name"))
            location = item.get("location") or item.get("placeholders") or item.get("place")
            workplace = _infer_workplace(
                _first(
                    item.get("workMode"),
                    item.get("workplaceType"),
                    item.get("workType"),
                ),
                location if isinstance(location, str) else None,
            )
            posted = _first(
                item.get("postedAt"),
                item.get("postedDate"),
                item.get("createdDate"),
                item.get("postedDateRelative"),
                item.get("footerPlaceholderLabel"),
            )
            description = _first(
                item.get("descriptionText"),
                item.get("description"),
                item.get("jobDescription"),
            )
            normalized.append(
                {
                    "id": job_id,
                    "source": self.name,
                    "title": item.get("title") or item.get("jobTitle"),
                    "companyName": company,
                    "location": location,
                    "workplaceType": workplace,
                    "employmentType": item.get("employmentType") or item.get("jobType"),
                    "postedAt": posted,
                    "salary": _salary(item),
                    "url": url,
                    "companyUrl": _first(
                        item.get("companyUrl"),
                        item.get("companyLinkedinUrl"),
                        item.get("ambitionBoxUrl"),
                    ),
                    "descriptionText": description,
                }
            )
        return normalized
