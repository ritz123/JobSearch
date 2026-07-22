"""Indeed jobs via borderline/indeed-scraper."""

from __future__ import annotations

import re
from typing import Any

ACTOR_ID = "borderline/indeed-scraper"

# Shared UI workplace → Indeed remote filter
WORKPLACE_MAP = {
    "remote": "remote",
    "hybrid": "hybrid",
}

JOB_TYPE_MAP = {
    "full_time": "fulltime",
    "part_time": "parttime",
    "contract": "contract",
    "temporary": "temporary",
    "internship": "internship",
}

DATE_POSTED_MAP = {
    "day": "1",
    "week": "7",
    "month": "14",
}

# Common country aliases → Indeed country codes used by the actor
COUNTRY_ALIASES = {
    "india": "in",
    "in": "in",
    "us": "us",
    "usa": "us",
    "united states": "us",
    "uk": "uk",
    "gb": "uk",
    "united kingdom": "uk",
    "canada": "ca",
    "ca": "ca",
    "australia": "au",
    "au": "au",
    "germany": "de",
    "de": "de",
    "singapore": "sg",
    "sg": "sg",
    "uae": "ae",
    "ae": "ae",
}


def _first(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def normalize_indeed_country(raw: str | None, default: str = "in") -> str:
    text = (raw or "").strip().lower()
    if not text:
        return default
    return COUNTRY_ALIASES.get(text, text)


def _location_text(item: dict) -> str | None:
    loc = item.get("location")
    if isinstance(loc, dict):
        return _first(
            loc.get("formattedAddressShort"),
            loc.get("formattedAddressLong"),
            loc.get("city"),
            loc.get("fullAddress"),
        )
    if isinstance(loc, str):
        return loc
    return None


def _salary(item: dict) -> str | None:
    salary = item.get("salary")
    if isinstance(salary, dict):
        return _first(salary.get("salaryText"), salary.get("text"))
    if isinstance(salary, str):
        return salary
    return None


def _job_key(item: dict, url: str | None) -> str | None:
    key = _first(item.get("jobKey"), item.get("id"), item.get("key"))
    if key:
        return str(key)
    if url:
        match = re.search(r"[?&]jk=([a-fA-F0-9]+)", url)
        if match:
            return match.group(1)
    return None


def _workplace(item: dict) -> str | None:
    if item.get("isRemote") is True:
        return "remote"
    job_type = item.get("jobType")
    if isinstance(job_type, list):
        joined = " ".join(str(x).lower() for x in job_type)
        if "remote" in joined:
            return "remote"
        if "hybrid" in joined:
            return "hybrid"
    return None


def _employment_type(item: dict) -> str | None:
    job_type = item.get("jobType")
    if isinstance(job_type, list) and job_type:
        return ", ".join(str(x) for x in job_type)
    if isinstance(job_type, str):
        return job_type
    return None


class IndeedSource:
    name = "indeed"
    actor_id = ACTOR_ID

    def build_input(self, args: Any) -> dict:
        country = normalize_indeed_country(getattr(args, "country", None))
        run_input: dict = {
            "country": country,
            "query": args.keywords,
            "location": args.location,
            "maxRows": int(args.max_jobs),
            "enableUniqueJobs": True,
        }

        workplace = getattr(args, "workplace", None)
        if workplace and workplace in WORKPLACE_MAP:
            run_input["remote"] = WORKPLACE_MAP[workplace]

        job_type = getattr(args, "job_type", None)
        if job_type and job_type in JOB_TYPE_MAP:
            run_input["jobType"] = JOB_TYPE_MAP[job_type]

        date_posted = getattr(args, "date_posted", "any") or "any"
        if date_posted in DATE_POSTED_MAP:
            run_input["fromDays"] = DATE_POSTED_MAP[date_posted]

        if getattr(args, "sort_recent", False):
            run_input["sort"] = "date"
        else:
            run_input["sort"] = "relevance"

        return run_input

    def normalize_items(self, items: list[dict]) -> list[dict]:
        normalized = []
        for item in items:
            url = _first(item.get("jobUrl"), item.get("url"), item.get("applyUrl"))
            job_id = _job_key(item, url if isinstance(url, str) else None)
            location = _location_text(item)
            normalized.append(
                {
                    "id": job_id,
                    "source": self.name,
                    "title": item.get("title") or item.get("jobTitle"),
                    "companyName": _first(
                        item.get("companyName"),
                        item.get("company"),
                        item.get("source"),
                    ),
                    "location": location,
                    "workplaceType": _workplace(item),
                    "employmentType": _employment_type(item),
                    "postedAt": _first(
                        item.get("datePublished"),
                        item.get("age"),
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
