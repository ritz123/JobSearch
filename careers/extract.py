"""Careers page discovery, fetch, and Ollama job extraction."""

from __future__ import annotations

import hashlib
import html
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import certifi

USER_AGENT = "JobSearchCityCareers/0.1 (local research; contact: local)"
CAREERS_PATHS = (
    "/careers",
    "/careers/",
    "/jobs",
    "/jobs/",
    "/join-us",
    "/join",
    "/work-with-us",
    "/opportunities",
    "/about/careers",
    "/company/careers",
)
CAREERS_LINK_RE = re.compile(
    r'href=["\']([^"\']*(?:career|job|join[-_]?us|work[-_]?with[-_]?us)[^"\']*)["\']',
    re.I,
)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
MAX_TEXT_CHARS = 12_000


def _ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def normalize_website(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    host = (parsed.netloc or "").lower().removeprefix("www.")
    path = (parsed.path or "").rstrip("/")
    return f"https://{host}{path}" if path else f"https://{host}"


def company_site_job_id(company_id: int, title: str, job_url: str) -> str:
    raw = f"{company_id}|{(job_url or '').strip().lower()}|{(title or '').strip().lower()}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
    return f"company_site:{digest}"


def html_to_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw_html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = WS_RE.sub(" ", text).strip()
    return text[:MAX_TEXT_CHARS]


def fetch_url(url: str, timeout: int = 20) -> tuple[int, str, str]:
    """Return (status, final_url, body_text_or_html). Raises on network errors."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        status = getattr(resp, "status", 200) or 200
        final = resp.geturl()
        charset = resp.headers.get_content_charset() or "utf-8"
        body = resp.read().decode(charset, errors="replace")
        return int(status), final, body


def _abs_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base if base.endswith("/") else base + "/", href)


def find_careers_url(website: str, delay_s: float = 0.4) -> str | None:
    """Try common careers paths, then scan homepage for careers-like links."""
    base = normalize_website(website)
    if not base:
        return None

    for path in CAREERS_PATHS:
        candidate = urllib.parse.urljoin(base + "/", path.lstrip("/"))
        try:
            status, final, body = fetch_url(candidate)
            time.sleep(delay_s)
            if status < 400 and len(body) > 200:
                lower = body.lower()
                if any(k in lower for k in ("career", "job", "opening", "position", "apply")):
                    return final.rstrip("/")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            continue

    try:
        status, final, body = fetch_url(base)
        time.sleep(delay_s)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return None

    for match in CAREERS_LINK_RE.finditer(body):
        href = match.group(1)
        if href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        return _abs_url(final, href).rstrip("/")
    return None


def list_ollama_models(base_url: str, timeout: int = 5) -> list[str]:
    """Return model names from Ollama ``GET /api/tags``. Raises if unreachable."""
    raw = (base_url or "").strip() or "http://127.0.0.1:11434"
    # Avoid localhost → IPv6 (::1) hangs when Ollama only listens on IPv4.
    raw = raw.replace("://localhost", "://127.0.0.1")
    url = raw.rstrip("/") + "/api/tags"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(1_000_000)  # cap read size
            data = json.loads(body.decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Ollama unreachable at {raw}. "
            "Start Ollama (`ollama serve`) and pull a model first."
        ) from exc
    models = data.get("models") or []
    names = []
    for m in models:
        if not isinstance(m, dict):
            continue
        name = (m.get("name") or m.get("model") or "").strip()
        if name:
            names.append(name)
    return sorted(set(names))


def check_ollama(base_url: str, timeout: int = 5) -> list[str]:
    """Ensure Ollama responds; return installed model names (may be empty)."""
    return list_ollama_models(base_url, timeout=timeout)


def _parse_jobs_json(raw: str) -> list[dict]:
    text = raw.strip()
    # Strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    # Find first JSON array/object
    start_arr = text.find("[")
    start_obj = text.find("{")
    if start_arr == -1 and start_obj == -1:
        raise ValueError("No JSON found in model output")
    if start_arr != -1 and (start_obj == -1 or start_arr < start_obj):
        payload = json.loads(text[start_arr:])
    else:
        payload = json.loads(text[start_obj:])
    if isinstance(payload, dict):
        for key in ("jobs", "openings", "positions", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("Expected a JSON list of jobs")
    return [p for p in payload if isinstance(p, dict)]


def extract_jobs_with_ollama(
    page_text: str,
    company_name: str,
    careers_url: str,
    *,
    base_url: str = "http://localhost:11434",
    model: str = "llama3.2",
    timeout: int = 120,
) -> list[dict]:
    """Ask Ollama to extract job listings as JSON."""
    prompt = (
        "Extract current job openings from this careers page text. "
        "Return ONLY a JSON array. Each item: "
        '{"title": string, "location": string|null, "url": string|null, '
        '"posted_at": string|null, "description": string|null}. '
        "If none found, return []. No markdown.\n\n"
        f"Company: {company_name}\nCareers URL: {careers_url}\n\n"
        f"PAGE TEXT:\n{page_text}"
    )
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "format": "json",
            "prompt": prompt,
            "options": {"temperature": 0},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/generate",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )

    def _once() -> list[dict]:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return _parse_jobs_json(data.get("response") or "")

    try:
        return _once()
    except (ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError, OSError):
        # Stricter retry
        retry_body = json.dumps(
            {
                "model": model,
                "stream": False,
                "format": "json",
                "prompt": (
                    "Return a JSON array of jobs with keys title, location, url, "
                    "posted_at, description. Empty array if none.\n\n" + page_text[:6000]
                ),
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        retry_req = urllib.request.Request(
            base_url.rstrip("/") + "/api/generate",
            data=retry_body,
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            method="POST",
        )
        try:
            with urllib.request.urlopen(retry_req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return _parse_jobs_json(data.get("response") or "")
        except Exception:
            return []


def normalize_extracted_jobs(
    raw_jobs: list[dict],
    *,
    company_name: str,
    company_url: str,
    careers_url: str,
    company_id: int,
    city: str,
) -> list[dict]:
    """Map Ollama output into the shared scraper job shape."""
    items: list[dict] = []
    for raw in raw_jobs:
        title = (raw.get("title") or "").strip()
        if not title:
            continue
        job_url = (raw.get("url") or "").strip() or careers_url
        if job_url and not job_url.startswith("http"):
            job_url = urllib.parse.urljoin(careers_url + "/", job_url)
        job_id = company_site_job_id(company_id, title, job_url)
        items.append(
            {
                "id": job_id,
                "source": "company_site",
                "title": title,
                "companyName": company_name,
                "location": (raw.get("location") or city or "").strip() or city,
                "workplaceType": None,
                "employmentType": None,
                "postedAt": raw.get("posted_at"),
                "salary": None,
                "url": job_url,
                "companyUrl": company_url,
                "descriptionText": raw.get("description"),
                "company_id": company_id,
            }
        )
    return items
