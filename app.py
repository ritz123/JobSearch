"""
app.py — Streamlit dashboard for browsing LinkedIn jobs stored in jobs.db.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from database import DEFAULT_DB, get_stats, query_jobs

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="LinkedIn Jobs Explorer",
    page_icon="💼",
    layout="wide",
)

DB_PATH = DEFAULT_DB

# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def load_jobs(
    keyword: str,
    company: str,
    location: str,
    workplace: str | None,
    limit: int,
) -> pd.DataFrame:
    rows = query_jobs(
        keyword=keyword or None,
        company=company or None,
        location=location or None,
        workplace=workplace or None,
        limit=limit,
        db_path=DB_PATH,
    )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([dict(r) for r in rows])


@st.cache_data(ttl=60)
def load_stats() -> dict:
    return get_stats(db_path=DB_PATH)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def db_exists() -> bool:
    return DB_PATH.exists() and DB_PATH.stat().st_size > 0


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


# ---------------------------------------------------------------------------
# Sidebar — filters
# ---------------------------------------------------------------------------

st.sidebar.title("🔍 Filters")

kw_input = st.sidebar.text_input("Keyword (title / description)", placeholder="e.g. data engineer")
company_input = st.sidebar.text_input("Company", placeholder="e.g. Google, Meta, Stripe")
st.sidebar.caption("Comma-separated: Google, Meta, Stripe")
location_input = st.sidebar.text_input("Location", placeholder="e.g. San Francisco")
workplace_options = ["All", "Remote", "On-site", "Hybrid"]
workplace_input = st.sidebar.selectbox("Workplace type", workplace_options)
st.sidebar.caption("Filters results already in the database.")
max_results = st.sidebar.number_input("Max results", min_value=1, max_value=500, value=100, step=10)
apply_btn = st.sidebar.button("Apply Filters", type="primary", use_container_width=True)

st.sidebar.info(
    "**Why no multi-select for job type or experience?**  \n"
    "The `automation-lab/linkedin-jobs-scraper` actor only accepts a single enum value "
    "for `jobType`, `workplaceType`, and `experienceLevel`. Run multiple searches to "
    "cover different filter combinations.",
    icon="ℹ️",
)

# Store filter state in session so we only re-query on button press
if "filters" not in st.session_state:
    st.session_state.filters = {
        "keyword": "",
        "company": "",
        "location": "",
        "workplace": None,
        "limit": 100,
    }

if apply_btn:
    st.session_state.filters = {
        "keyword": kw_input,
        "company": company_input,
        "location": location_input,
        "workplace": None if workplace_input == "All" else workplace_input,
        "limit": int(max_results),
    }

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("💼 LinkedIn Jobs Explorer")

if not db_exists():
    st.info(
        "No data yet. Run **scraper.py** first to populate the database.",
        icon="ℹ️",
    )
    st.stop()

f = st.session_state.filters
jobs_df = load_jobs(
    keyword=f["keyword"],
    company=f["company"],
    location=f["location"],
    workplace=f["workplace"],
    limit=f["limit"],
)
stats = load_stats()

tab1, tab2, tab3 = st.tabs(["📋 Jobs Table", "📊 Stats & Charts", "🔎 Job Detail"])

# ===========================================================================
# Tab 1 — Jobs Table
# ===========================================================================

with tab1:
    st.subheader("Job Listings")

    if jobs_df.empty:
        st.warning("No jobs match the current filters.")
    else:
        display_cols = [
            "title", "company", "location", "workplace_type",
            "contract_type", "published_at", "salary", "job_url",
        ]
        # Keep only columns that exist (defensive)
        display_cols = [c for c in display_cols if c in jobs_df.columns]
        display_df = jobs_df[display_cols].copy()

        st.caption(f"**{len(display_df):,}** job(s) found")

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "title": st.column_config.TextColumn("Title", width="large"),
                "company": st.column_config.TextColumn("Company"),
                "location": st.column_config.TextColumn("Location"),
                "workplace_type": st.column_config.TextColumn("Workplace"),
                "contract_type": st.column_config.TextColumn("Contract"),
                "published_at": st.column_config.TextColumn("Published"),
                "salary": st.column_config.TextColumn("Salary"),
                "job_url": st.column_config.LinkColumn("Link", display_text="Open ↗"),
            },
        )

        st.download_button(
            label="⬇ Download CSV",
            data=to_csv_bytes(display_df),
            file_name="linkedin_jobs.csv",
            mime="text/csv",
        )

# ===========================================================================
# Tab 2 — Stats & Charts
# ===========================================================================

with tab2:
    st.subheader("Database Overview")

    unique_companies = len(jobs_df["company"].dropna().unique()) if not jobs_df.empty else 0
    unique_locations = len(jobs_df["location"].dropna().unique()) if not jobs_df.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Jobs", f"{stats['total_jobs']:,}")
    col2.metric("Total Searches", f"{stats['total_searches']:,}")
    col3.metric("Unique Companies", f"{unique_companies:,}")
    col4.metric("Unique Locations", f"{unique_locations:,}")

    st.divider()

    chart_col1, chart_col2 = st.columns(2)

    # Top companies
    with chart_col1:
        st.markdown("**Top 10 Companies by Job Count**")
        if stats["top_companies"]:
            comp_df = pd.DataFrame(stats["top_companies"])
            fig_comp = px.bar(
                comp_df,
                x="n",
                y="company",
                orientation="h",
                labels={"n": "Jobs", "company": "Company"},
                color="n",
                color_continuous_scale="Blues",
            )
            fig_comp.update_layout(
                showlegend=False,
                coloraxis_showscale=False,
                yaxis={"categoryorder": "total ascending"},
                margin={"l": 0, "r": 0, "t": 10, "b": 0},
            )
            st.plotly_chart(fig_comp, use_container_width=True)
        else:
            st.info("No company data available.")

    # Top locations
    with chart_col2:
        st.markdown("**Top 10 Locations by Job Count**")
        if stats["top_locations"]:
            loc_df = pd.DataFrame(stats["top_locations"])
            fig_loc = px.bar(
                loc_df,
                x="n",
                y="location",
                orientation="h",
                labels={"n": "Jobs", "location": "Location"},
                color="n",
                color_continuous_scale="Greens",
            )
            fig_loc.update_layout(
                showlegend=False,
                coloraxis_showscale=False,
                yaxis={"categoryorder": "total ascending"},
                margin={"l": 0, "r": 0, "t": 10, "b": 0},
            )
            st.plotly_chart(fig_loc, use_container_width=True)
        else:
            st.info("No location data available.")

    st.divider()

    pie_col, search_col = st.columns([1, 1])

    # Workplace distribution
    with pie_col:
        st.markdown("**Workplace Type Distribution**")
        if stats["workplace_distribution"]:
            wp_df = pd.DataFrame(stats["workplace_distribution"])
            fig_pie = px.pie(
                wp_df,
                names="workplace_type",
                values="n",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(
                showlegend=True,
                margin={"l": 0, "r": 0, "t": 10, "b": 0},
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No workplace distribution data available.")

    # Recent searches
    with search_col:
        st.markdown("**Recent Searches**")
        if stats["recent_searches"]:
            rs_df = pd.DataFrame(stats["recent_searches"])
            rs_df = rs_df.rename(columns={
                "keywords": "Keywords",
                "location": "Location",
                "job_count": "Jobs",
                "ran_at": "Timestamp",
            })
            # Trim timestamp to readable format
            if "Timestamp" in rs_df.columns:
                rs_df["Timestamp"] = rs_df["Timestamp"].str[:19].str.replace("T", " ")
            st.dataframe(rs_df, use_container_width=True, hide_index=True)
        else:
            st.info("No search history yet.")

# ===========================================================================
# Tab 3 — Job Detail View
# ===========================================================================

with tab3:
    st.subheader("Job Detail")

    if jobs_df.empty:
        st.warning("No jobs to display. Adjust your filters or run the scraper first.")
    else:
        job_labels = (
            jobs_df["title"].fillna("(no title)")
            + " — "
            + jobs_df["company"].fillna("(no company)")
        ).tolist()

        selected_label = st.selectbox("Select a job", job_labels)
        selected_idx = job_labels.index(selected_label)
        job = jobs_df.iloc[selected_idx]

        # Card layout
        st.markdown("---")
        detail_col1, detail_col2 = st.columns([2, 1])

        with detail_col1:
            st.markdown(f"## {job.get('title', 'N/A')}")
            st.markdown(f"**🏢 Company:** {job.get('company', 'N/A')}")
            st.markdown(f"**📍 Location:** {job.get('location', 'N/A')}")
            st.markdown(f"**🖥 Workplace:** {job.get('workplace_type', 'N/A')}")
            st.markdown(f"**📄 Contract:** {job.get('contract_type', 'N/A')}")

        with detail_col2:
            st.markdown(f"**📅 Published:** {job.get('published_at', 'N/A')}")
            salary = job.get("salary")
            st.markdown(f"**💰 Salary:** {salary if salary else 'Not listed'}")
            job_url = job.get("job_url")
            if job_url:
                st.link_button("Open on LinkedIn ↗", job_url)

        description = job.get("description", "")
        with st.expander("📝 Full Job Description", expanded=False):
            if description:
                st.markdown(description)
            else:
                st.info("No description available.")
