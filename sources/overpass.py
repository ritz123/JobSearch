"""Discover companies in a city via Nominatim + Overpass (OpenStreetMap)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

import certifi

USER_AGENT = "JobSearchCityCareers/0.1 (local research; contact: local)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Filter presets → Overpass tag selectors (OR'd inside bbox)
FILTER_PRESETS: dict[str, list[str]] = {
    "tech_corporate": [
        'node["office"~"company|it|coworking|software|yes"]["website"]',
        'way["office"~"company|it|coworking|software|yes"]["website"]',
        'relation["office"~"company|it|coworking|software|yes"]["website"]',
        'node["office"]["contact:website"]',
        'way["office"]["contact:website"]',
    ],
    # Marketing / SEO agencies (OSM tags + name keyword pass in find_companies)
    "seo_marketing": [
        'node["office"~"advertising_agency|advertising|marketing|graphic_design"]["website"]',
        'way["office"~"advertising_agency|advertising|marketing|graphic_design"]["website"]',
        'relation["office"~"advertising_agency|advertising|marketing|graphic_design"]["website"]',
        'node["office"~"company|it|yes"]["website"]',
        'way["office"~"company|it|yes"]["website"]',
        'node["office"]["contact:website"]',
        'way["office"]["contact:website"]',
    ],
    "broad_with_website": [
        'node["website"]["name"]',
        'way["website"]["name"]',
        'node["contact:website"]["name"]',
        'way["contact:website"]["name"]',
    ],
}

# Optional name/website keyword filters applied after Overpass (lowercase substrings).
NAME_KEYWORDS: dict[str, list[str]] = {
    "seo_marketing": [
        "seo",
        "digital marketing",
        "digital agency",
        "marketing agency",
        "advertising",
        "ad agency",
        "media agency",
        "content marketing",
        "social media",
        "performance marketing",
        "growth marketing",
        "sem ",
        "ppc",
        "inbound marketing",
        "branding agency",
    ],
}

# OSM office values that always count as marketing even without name keywords.
MARKETING_OFFICE_TAGS = {
    "advertising_agency",
    "advertising",
    "marketing",
    "graphic_design",
}

ProgressCb = Callable[[str], None]


def _ssl_context() -> ssl.SSLContext:
    """Use certifi CA bundle (fixes CERTIFICATE_VERIFY_FAILED on many hosts)."""
    return ssl.create_default_context(cafile=certifi.where())


def _http_json(url: str, data: bytes | None = None, timeout: int = 60) -> Any:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="POST" if data is not None else "GET",
    )
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode_city(city: str, timeout: int = 30) -> dict[str, float]:
    """Return Nominatim bounding box: south, west, north, east."""
    params = urllib.parse.urlencode({"q": city, "format": "json", "limit": 1})
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
        results = json.loads(resp.read().decode("utf-8"))
    if not results:
        raise ValueError(f"Could not geocode city: {city!r}")
    bb = results[0].get("boundingbox")
    if not bb or len(bb) != 4:
        raise ValueError(f"No bounding box for city: {city!r}")
    # Nominatim: [south, north, west, east]
    south, north, west, east = map(float, bb)
    return {"south": south, "west": west, "north": north, "east": east}


def build_overpass_query(bbox: dict[str, float], preset: str = "tech_corporate") -> str:
    tags = FILTER_PRESETS.get(preset) or FILTER_PRESETS["tech_corporate"]
    s, w, n, e = bbox["south"], bbox["west"], bbox["north"], bbox["east"]
    bbox_str = f"{s},{w},{n},{e}"
    parts = []
    for selector in tags:
        kind = selector.split("[", 1)[0]
        rest = selector[len(kind) :]
        parts.append(f"  {kind}{rest}({bbox_str});")
    body = "\n".join(parts)
    return f"[out:json][timeout:60];\n(\n{body}\n);\nout center tags;"


def _pick_website(tags: dict[str, str]) -> str | None:
    for key in ("website", "contact:website", "url"):
        val = (tags.get(key) or "").strip()
        if val:
            if not val.startswith("http"):
                val = "https://" + val
            return val.rstrip("/")
    return None


def _element_to_company(el: dict, city: str) -> dict | None:
    tags = el.get("tags") or {}
    name = (tags.get("name") or tags.get("brand") or "").strip()
    website = _pick_website(tags)
    if not name or not website:
        return None
    if "lat" in el and "lon" in el:
        lat, lon = el["lat"], el["lon"]
    else:
        center = el.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
    osm_type = el.get("type", "node")
    osm_id = f"{osm_type}/{el.get('id')}"
    return {
        "osm_id": osm_id,
        "name": name,
        "website": website,
        "city": city,
        "lat": lat,
        "lon": lon,
        "tags": tags,
    }


def _matches_name_filter(company: dict, keywords: list[str]) -> bool:
    tags = company.get("tags") or {}
    office = str(tags.get("office") or "").lower()
    if office in MARKETING_OFFICE_TAGS:
        return True
    haystack = " ".join(
        [
            str(company.get("name") or ""),
            str(company.get("website") or ""),
            str(tags.get("description") or ""),
            str(tags.get("brand") or ""),
        ]
    ).lower()
    return any(kw in haystack for kw in keywords)


def find_companies(
    city: str,
    preset: str = "tech_corporate",
    max_companies: int = 15,
    progress: ProgressCb | None = None,
) -> list[dict]:
    """Geocode city and query Overpass for companies with websites."""
    log = progress or (lambda _m: None)
    log(f"Geocoding {city!r} via Nominatim…")
    try:
        bbox = geocode_city(city)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Nominatim request failed: {exc}") from exc

    query = build_overpass_query(bbox, preset=preset)
    log("Querying Overpass for companies with websites…")
    try:
        payload = urllib.parse.urlencode({"data": query}).encode("utf-8")
        data = _http_json(OVERPASS_URL, data=payload, timeout=90)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Overpass request failed: {exc}") from exc

    elements = data.get("elements") or []
    # Pull a larger pool when name-filtering so we can still fill max_companies.
    keywords = NAME_KEYWORDS.get(preset) or []
    pool_limit = max_companies * 8 if keywords else max_companies

    candidates: list[dict] = []
    seen_websites: set[str] = set()
    for el in elements:
        company = _element_to_company(el, city)
        if not company:
            continue
        key = company["website"].lower()
        if key in seen_websites:
            continue
        seen_websites.add(key)
        candidates.append(company)
        if len(candidates) >= pool_limit:
            break

    if keywords:
        companies = [c for c in candidates if _matches_name_filter(c, keywords)]
        log(
            f"Name-filter ({preset}): {len(companies)}/{len(candidates)} "
            f"matched SEO/marketing keywords."
        )
    else:
        companies = candidates

    companies = companies[:max_companies]
    log(f"Found {len(companies)} companies (cap {max_companies}).")
    if not companies:
        raise ValueError(
            f"No companies with websites found in {city!r} for preset {preset!r}."
        )
    return companies
