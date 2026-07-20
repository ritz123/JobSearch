"""
pages/2_Run_Scraper.py — Streamlit UI for running the LinkedIn job scraper.
"""

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
from dotenv import dotenv_values

# Add project root to path so database can be imported when running as a page
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import database  # noqa: E402

st.set_page_config(page_title="Run Scraper", layout="wide")

st.title("Run Job Scraper")

# ---------------------------------------------------------------------------
# Prefill store + form remount nonce
# ---------------------------------------------------------------------------
# Load sets pending_load_id (non-widget key) then reruns. Prefs are applied
# at the top of the next run — before form widgets exist — which avoids the
# Streamlit error of mutating widget state after instantiation.

_PREF = {
    "source": "linkedin",
    "keywords": "",
    "location": "",
    "max_jobs": 25,
    "workplace": "Any",
    "job_type": "Any",
    "date_posted": "any",
    "experience": "Any",
    "company": "",
    "fetch_details": False,
    "sort_recent": False,
}

if "scraper_prefs" not in st.session_state:
    st.session_state["scraper_prefs"] = dict(_PREF)
else:
    for _k, _v in _PREF.items():
        st.session_state["scraper_prefs"].setdefault(_k, _v)
if "scraper_form_nonce" not in st.session_state:
    st.session_state["scraper_form_nonce"] = 0


def _apply_search_to_prefs(search: dict) -> None:
    filters = search.get("filters") or {}
    max_jobs = int(filters.get("max_jobs") or 25)
    max_jobs = max(5, min(200, round(max_jobs / 5) * 5))

    st.session_state["scraper_prefs"] = {
        "source": filters.get("source") or "linkedin",
        "keywords": search.get("keywords") or "",
        "location": search.get("location") or "",
        "max_jobs": max_jobs,
        "workplace": filters.get("workplace") or "Any",
        "job_type": filters.get("job_type") or "Any",
        "date_posted": filters.get("date_posted") or "any",
        "experience": filters.get("experience") or "Any",
        "company": filters.get("company") or "",
        "fetch_details": bool(filters.get("details", False)),
        "sort_recent": bool(filters.get("sort_recent", False)),
    }
    st.session_state["scraper_form_nonce"] = st.session_state.get("scraper_form_nonce", 0) + 1
    st.session_state["scraper_loaded_flash"] = (
        f"Loaded search #{search['id']} into the form. "
        "Review the fields above, then click Start Scraping."
    )


# Apply a pending Load request before any form widgets are created.
if "pending_load_id" in st.session_state:
    pending_id = st.session_state.pop("pending_load_id")
    try:
        match = next(
            (s for s in database.get_recent_searches(limit=50) if s["id"] == pending_id),
            None,
        )
        if match:
            _apply_search_to_prefs(match)
        else:
            st.session_state["scraper_loaded_flash"] = (
                f"Could not find search #{pending_id} in history."
            )
    except Exception as exc:
        st.session_state["scraper_loaded_flash"] = f"Failed to load search: {exc}"

# ---------------------------------------------------------------------------
# Environment / token check
# ---------------------------------------------------------------------------

_dotenv_vars = dotenv_values(ROOT / ".env")
_env = {**os.environ.copy(), **_dotenv_vars}

if not _env.get("APIFY_TOKEN"):
    st.warning(
        "**APIFY_TOKEN is not set.**  \n"
        "To use the scraper you need an Apify API token.  \n"
        "1. Get your token at [console.apify.com/account/integrations](https://console.apify.com/account/integrations).  \n"
        "2. Create a `.env` file in the project root with:  \n"
        "   `APIFY_TOKEN=apify_api_xxxxxxxxxxxx`  \n"
        "3. Restart the Streamlit app."
    )

if "scraper_loaded_flash" in st.session_state:
    st.success(st.session_state.pop("scraper_loaded_flash"))

# ---------------------------------------------------------------------------
# Search form
# ---------------------------------------------------------------------------

prefs = st.session_state["scraper_prefs"]
nonce = st.session_state["scraper_form_nonce"]

with st.form(f"scraper_form_{nonce}"):
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("Required & Main Filters")
        source_opts = ["linkedin", "naukri"]
        source = st.selectbox(
            "Source *",
            source_opts,
            index=source_opts.index(prefs.get("source", "linkedin"))
            if prefs.get("source", "linkedin") in source_opts
            else 0,
            help="LinkedIn or Naukri.com — one source per run",
        )
        keywords = st.text_input(
            "Keywords *",
            value=prefs["keywords"],
            placeholder="e.g. data engineer / python developer",
        )
        location = st.text_input(
            "Location *",
            value=prefs["location"],
            placeholder="e.g. bangalore (Naukri: one city)",
        )
        st.caption(
            "Naukri needs a single city (e.g. bangalore). "
            "LinkedIn-style values like “Bangalore, remote” are cleaned automatically."
        )
        max_jobs = st.slider(
            "Max Jobs",
            min_value=5,
            max_value=200,
            value=prefs["max_jobs"],
            step=5,
        )
        workplace_opts = ["Any", "remote", "on_site", "hybrid"]
        workplace = st.selectbox(
            "Workplace",
            workplace_opts,
            index=workplace_opts.index(prefs["workplace"])
            if prefs["workplace"] in workplace_opts
            else 0,
        )
        st.caption("Mapped per source (LinkedIn workplaceType / Naukri workMode).")
        job_type_options = [
            "Any", "full_time", "part_time", "contract", "internship", "temporary",
        ]
        job_type = st.selectbox(
            "Job Type (LinkedIn)",
            job_type_options,
            index=job_type_options.index(prefs["job_type"])
            if prefs["job_type"] in job_type_options
            else 0,
        )
        st.caption("Used for LinkedIn only.")

    with right_col:
        st.subheader("Advanced Filters")
        date_options = ["any", "day", "week", "month"]
        date_posted = st.selectbox(
            "Date Posted (LinkedIn)",
            date_options,
            index=date_options.index(prefs["date_posted"])
            if prefs["date_posted"] in date_options
            else 0,
        )
        exp_options = [
            "Any", "internship", "entry", "associate", "mid_senior", "director", "executive",
        ]
        experience = st.selectbox(
            "Experience Level (LinkedIn)",
            exp_options,
            index=exp_options.index(prefs["experience"])
            if prefs["experience"] in exp_options
            else 0,
        )
        st.caption("LinkedIn experience enums; ignored for Naukri.")
        company = st.text_input(
            "Company Filter (LinkedIn)",
            value=prefs["company"],
            placeholder="e.g. Google, Meta, Stripe",
        )
        st.caption("Comma-separated; LinkedIn only.")
        fetch_details = st.checkbox(
            "Fetch full job descriptions (LinkedIn)",
            value=prefs["fetch_details"],
        )
        sort_recent = st.checkbox(
            "Sort by most recent",
            value=prefs["sort_recent"],
        )

    submitted = st.form_submit_button("▶ Start Scraping", type="primary", width="stretch")

# ---------------------------------------------------------------------------
# Run scraper on submit
# ---------------------------------------------------------------------------

if submitted:
    errors = []
    if not keywords.strip():
        errors.append("Keywords are required.")
    if not location.strip():
        errors.append("Location is required.")

    if errors:
        for msg in errors:
            st.error(msg)
    else:
        st.session_state["scraper_prefs"] = {}  # no-op placeholder removed below
        st.session_state["scraper_prefs"] = {
            "source": source,
            "keywords": keywords.strip(),
            "location": location.strip(),
            "max_jobs": max_jobs,
            "workplace": workplace,
            "job_type": job_type,
            "date_posted": date_posted,
            "experience": experience,
            "company": company,
            "fetch_details": fetch_details,
            "sort_recent": sort_recent,
        }

        scraper_path = ROOT / "scraper.py"
        cmd = [
            sys.executable,
            str(scraper_path),
            "--source", source,
            "--keywords", keywords.strip(),
            "--location", location.strip(),
            "--max-jobs", str(max_jobs),
            "--date-posted", date_posted,
        ]
        if workplace != "Any":
            cmd += ["--workplace", workplace]
        if source == "linkedin":
            if job_type != "Any":
                cmd += ["--job-type", job_type]
            if experience != "Any":
                cmd += ["--experience", experience]
            if company.strip():
                cmd += ["--company", company.strip()]
            if fetch_details:
                cmd.append("--details")
        if sort_recent:
            cmd.append("--sort-recent")

        with st.status("Running scraper...", expanded=True) as status_box:
            output_placeholder = st.empty()
            accumulated = ""

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=_env,
                cwd=str(ROOT),
            )

            for line in process.stdout:
                accumulated += line
                output_placeholder.code(accumulated, language="")

            process.wait()
            status_box.update(state="complete" if process.returncode == 0 else "error")

        if process.returncode == 0:
            st.success("Scrape complete! Switch to the Jobs Dashboard page to view results.")
        else:
            st.error("Scraper failed. Check the output above.")

# ---------------------------------------------------------------------------
# Scraper history
# ---------------------------------------------------------------------------

st.divider()
st.subheader("Recent Searches")

try:
    recent = database.get_recent_searches(limit=10)
except Exception as exc:
    recent = []
    st.warning(f"Could not load search history: {exc}")

if recent:
    for search in recent:
        col_info, col_btn = st.columns([5, 1])
        with col_info:
            ran_at = (search.get("ran_at") or "")[:19].replace("T", " ")
            filters = search.get("filters") or {}
            src = filters.get("source") or "linkedin"
            st.markdown(
                f"**{search.get('keywords', '')}** @ {search.get('location', '')}  \n"
                f"`{src}` · {search.get('job_count', 0)} jobs · {ran_at}"
            )
        with col_btn:
            if st.button("Load", key=f"load_search_{search['id']}", width="stretch"):
                # Only set a non-widget key here; prefs are applied on the next run.
                st.session_state["pending_load_id"] = search["id"]
                st.rerun()
else:
    st.info("No searches yet. Run the scraper above to get started.")

if st.button("Refresh"):
    st.rerun()
