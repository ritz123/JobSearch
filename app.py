"""
app.py — Streamlit dashboard for browsing LinkedIn jobs stored in jobs.db.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from database import DEFAULT_DB, get_stats, init_db, query_jobs
from posted_dates import format_published_display, sort_key_published

# Pandas 3 defaults to Arrow-backed strings; building DataFrames from sqlite rows
# can segfault in string_arrow._from_sequence (seen when filtering e.g. "SEO").
pd.options.future.infer_string = False

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="LinkedIn Jobs Explorer",
    page_icon="💼",
    layout="wide",
)

DB_PATH = DEFAULT_DB
init_db(DB_PATH)  # ensures schema + migrates stale relative published_at values

# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------


@st.cache_data(ttl=60)
def load_jobs(
    keyword: str,
    company: str,
    location: str,
    workplace: str | None,
    source: str | None,
    posted_within: str | None,
    limit: int,
) -> pd.DataFrame:
    rows = query_jobs(
        keyword=keyword or None,
        company=company or None,
        location=location or None,
        workplace=workplace or None,
        source=source,
        posted_within=posted_within,
        limit=limit,
        db_path=DB_PATH,
    )
    if not rows:
        return pd.DataFrame()
    # dtype=object avoids Arrow string arrays (pandas 3 segfault risk).
    return pd.DataFrame([dict(r) for r in rows], dtype=object)


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


def stringify_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with every cell as a plain Python str (no Arrow dtypes)."""
    if df.empty:
        return df
    out = pd.DataFrame(index=df.index)
    for col in df.columns:
        out[col] = [
            "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)
            for v in df[col].tolist()
        ]
    return out


def sort_jobs_df(df: pd.DataFrame, sort_by: str, ascending: bool) -> pd.DataFrame:
    """Sort display rows; Published sorts by absolute post time.

    For Published, ``ascending=True`` means Newest first (UI convention).
    """
    if df.empty or sort_by not in df.columns:
        return df
    out = df.copy()
    if sort_by == "Published":
        scraped = out["_scraped_at"] if "_scraped_at" in out.columns else [None] * len(out)
        keys = [
            sort_key_published(pub, ref)
            for pub, ref in zip(out["_published_raw"].tolist(), scraped.tolist())
        ]
        # UI ascending=True (Newest first) => larger epoch first
        out = out.assign(_epoch=keys).sort_values(
            by="_epoch",
            ascending=not ascending,
            kind="mergesort",
        ).drop(columns=["_epoch"])
        return out.reset_index(drop=True)
    return out.sort_values(
        by=sort_by,
        ascending=ascending,
        kind="mergesort",
        key=lambda s: s.astype(str).str.lower(),
    ).reset_index(drop=True)


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
source_input = st.sidebar.selectbox("Source", ["All", "linkedin", "naukri"])
posted_labels = {
    "Any": "any",
    "Past 24 hours": "24h",
    "Past 3 days": "3d",
    "Past week": "week",
    "Past month": "month",
}
posted_input = st.sidebar.selectbox("Posted", list(posted_labels.keys()))
st.sidebar.caption("Filters results already in the database.")
max_results = st.sidebar.number_input("Max results", min_value=1, max_value=500, value=100, step=10)
apply_btn = st.sidebar.button("Apply Filters", type="primary", width="stretch")

st.sidebar.info(
    "**Sources:** LinkedIn and Naukri scrapes share this database. "
    "Use the Source filter to view one board, or All for both.",
    icon="ℹ️",
)

# Store filter state in session so we only re-query on button press
if "filters" not in st.session_state:
    st.session_state.filters = {
        "keyword": "",
        "company": "",
        "location": "",
        "workplace": None,
        "source": None,
        "posted_within": None,
        "limit": 100,
    }

if apply_btn:
    posted_key = posted_labels[posted_input]
    st.session_state.filters = {
        "keyword": kw_input,
        "company": company_input,
        "location": location_input,
        "workplace": None if workplace_input == "All" else workplace_input,
        "source": None if source_input == "All" else source_input,
        "posted_within": None if posted_key == "any" else posted_key,
        "limit": int(max_results),
    }

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("💼 Jobs Explorer")

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
    source=f.get("source"),
    posted_within=f.get("posted_within"),
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
            "source", "title", "company", "location", "workplace_type",
            "contract_type", "published_at", "salary", "job_url",
        ]
        # Keep only columns that exist (defensive)
        display_cols = [c for c in display_cols if c in jobs_df.columns]
        display_df = stringify_df(jobs_df[display_cols]).rename(columns={
            "source": "Source",
            "title": "Title",
            "company": "Company",
            "location": "Location",
            "workplace_type": "Workplace",
            "contract_type": "Contract",
            "published_at": "Published",
            "salary": "Salary",
            "job_url": "Link",
        })
        # Keep raw values for absolute-date sort / display (relative strings are stale).
        display_df["_published_raw"] = jobs_df["published_at"].tolist()
        display_df["_scraped_at"] = (
            jobs_df["scraped_at"].tolist()
            if "scraped_at" in jobs_df.columns
            else [None] * len(display_df)
        )
        display_df["Published"] = [
            format_published_display(pub, ref)
            for pub, ref in zip(
                display_df["_published_raw"].tolist(),
                display_df["_scraped_at"].tolist(),
            )
        ]

        sort_cols = [c for c in (
            "Published", "Source", "Title", "Company", "Location", "Workplace", "Contract", "Salary",
        ) if c in display_df.columns]

        sort_left, sort_right = st.columns(2)
        with sort_left:
            sort_by = st.selectbox(
                "Sort by",
                sort_cols,
                index=sort_cols.index("Published") if "Published" in sort_cols else 0,
                key="jobs_sort_by",
            )
        with sort_right:
            if sort_by == "Published":
                order_label = st.selectbox(
                    "Order",
                    ["Newest first", "Oldest first"],
                    key="jobs_sort_order_published",
                )
                ascending = order_label == "Newest first"
            else:
                order_label = st.selectbox(
                    "Order",
                    ["A → Z", "Z → A"],
                    key="jobs_sort_order_alpha",
                )
                ascending = order_label == "A → Z"

        display_df = sort_jobs_df(display_df, sort_by, ascending)
        export_df = display_df.drop(
            columns=[c for c in ("_published_raw", "_scraped_at") if c in display_df.columns]
        )

        st.caption(f"**{len(export_df):,}** job(s) found")

        # Avoid st.dataframe/st.table: both marshal via pyarrow and can SIGSEGV
        # with pandas 3 + pyarrow 25 on this environment when filtering (e.g. SEO).
        html_df = export_df.copy()
        if "Link" in html_df.columns:
            html_df["Link"] = [
                f'<a href="{url}" target="_blank" rel="noopener">Open</a>' if url else ""
                for url in html_df["Link"]
            ]
        st.markdown(
            html_df.to_html(escape=False, index=False),
            unsafe_allow_html=True,
        )

        st.download_button(
            label="⬇ Download CSV",
            data=to_csv_bytes(export_df),
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
            st.plotly_chart(fig_comp, width="stretch")
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
            st.plotly_chart(fig_loc, width="stretch")
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
            st.plotly_chart(fig_pie, width="stretch")
        else:
            st.info("No workplace distribution data available.")

    # Recent searches
    with search_col:
        st.markdown("**Recent Searches**")
        if stats["recent_searches"]:
            rs_df = stringify_df(pd.DataFrame(stats["recent_searches"], dtype=object))
            keep = [c for c in ("keywords", "location", "job_count", "ran_at") if c in rs_df.columns]
            rs_df = rs_df[keep]
            rs_df = rs_df.rename(columns={
                "keywords": "Keywords",
                "location": "Location",
                "job_count": "Jobs",
                "ran_at": "Timestamp",
            })
            if "Timestamp" in rs_df.columns:
                rs_df["Timestamp"] = [t[:19].replace("T", " ") for t in rs_df["Timestamp"]]
            st.markdown(rs_df.to_html(escape=True, index=False), unsafe_allow_html=True)
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
            st.markdown(
                f"**📅 Published:** "
                f"{format_published_display(job.get('published_at'), job.get('scraped_at'))}"
            )
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
