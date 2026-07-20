"""LinkedIn jobs via automation-lab/linkedin-jobs-scraper."""

from __future__ import annotations

from typing import Any

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


class LinkedInSource:
    name = "linkedin"
    actor_id = ACTOR_ID

    def build_input(self, args: Any) -> dict:
        run_input: dict = {
            "searchQuery": args.keywords,
            "location": args.location,
            "maxJobs": args.max_jobs,
            "scrapeJobDetails": bool(getattr(args, "details", False)),
            "sortBy": "DD" if getattr(args, "sort_recent", False) else "R",
        }
        job_type = getattr(args, "job_type", None)
        if job_type:
            run_input["jobType"] = JOB_TYPE_MAP[job_type]
        workplace = getattr(args, "workplace", None)
        if workplace:
            run_input["workplaceType"] = WORKPLACE_MAP[workplace]
        date_posted = getattr(args, "date_posted", "any") or "any"
        if date_posted != "any":
            run_input["datePosted"] = DATE_POSTED_MAP[date_posted]
        experience = getattr(args, "experience", None)
        if experience:
            run_input["experienceLevel"] = EXPERIENCE_MAP[experience]
        company = getattr(args, "company", None)
        if company:
            run_input["companyName"] = company
        return run_input

    def normalize_items(self, items: list[dict]) -> list[dict]:
        return [
            {
                "id": item.get("id"),
                "source": self.name,
                "title": item.get("title"),
                "companyName": item.get("companyName"),
                "location": item.get("location"),
                "workplaceType": item.get("workplaceType"),
                "employmentType": item.get("employmentType"),
                "postedAt": item.get("postedAt"),
                "salary": item.get("salary"),
                "url": item.get("url") or item.get("jobUrl"),
                "companyUrl": item.get("companyLinkedinUrl"),
                "descriptionText": item.get("descriptionText"),
            }
            for item in items
        ]
