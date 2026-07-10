"""
pages/2_Run_Scraper.py — Streamlit UI for running the LinkedIn job scraper.
"""

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import dotenv_values

# Add project root to path so database can be imported when running as a page
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import database  # noqa: E402

st.set_page_config(page_title="Run Scraper", layout="wide")

st.title("Run LinkedIn Job Scraper")

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

# ---------------------------------------------------------------------------
# Search form
# ---------------------------------------------------------------------------

with st.form("scraper_form"):
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("Required & Main Filters")
        keywords = st.text_input("Keywords *", placeholder="e.g. data engineer")
        location = st.text_input("Location *", placeholder="e.g. Remote, New York, India")
        max_jobs = st.slider("Max Jobs", min_value=5, max_value=200, value=25, step=5)
        workplace = st.selectbox(
            "Workplace",
            ["Any", "remote", "on_site", "hybrid"],
        )
        st.caption("Actor API accepts one workplace type per run.")
        job_type = st.selectbox(
            "Job Type",
            ["Any", "full_time", "part_time", "contract", "internship", "temporary"],
        )
        st.caption("Actor API accepts one job type per run.")

    with right_col:
        st.subheader("Advanced Filters")
        date_posted = st.selectbox(
            "Date Posted",
            ["any", "day", "week", "month"],
        )
        experience = st.selectbox(
            "Experience Level",
            ["Any", "internship", "entry", "associate", "mid_senior", "director", "executive"],
        )
        st.caption("Actor API accepts one experience level per run.")
        company = st.text_input(
            "Company Filter",
            placeholder="e.g. Google, Meta, Stripe",
        )
        st.caption("Comma-separated: Google, Meta, Stripe")
        fetch_details = st.checkbox("Fetch full job descriptions (slower, more data)")
        sort_recent = st.checkbox("Sort by most recent")

    submitted = st.form_submit_button("▶ Start Scraping", type="primary", use_container_width=True)

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
        # Build command
        scraper_path = ROOT / "scraper.py"
        cmd = [
            sys.executable,
            str(scraper_path),
            "--keywords", keywords.strip(),
            "--location", location.strip(),
            "--max-jobs", str(max_jobs),
            "--date-posted", date_posted,
        ]
        if workplace != "Any":
            cmd += ["--workplace", workplace]
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
    stats = database.get_stats()
    recent = stats.get("recent_searches", [])

    if recent:
        df_history = pd.DataFrame(recent, columns=["keywords", "location", "job_count", "ran_at"])
        st.dataframe(df_history, use_container_width=True, hide_index=True)
    else:
        st.info("No searches yet. Run the scraper above to get started.")
except Exception as exc:
    st.warning(f"Could not load search history: {exc}")

if st.button("Refresh"):
    st.rerun()
