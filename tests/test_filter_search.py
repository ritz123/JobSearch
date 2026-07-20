"""Regression tests: filter-based search must not crash the app/server."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_load_jobs_seo_uses_object_dtype():
    """SEO results must build a DataFrame without Arrow string columns."""
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    # Import after chdir so DB relative paths resolve like the app.
    import app as dashboard

    df = dashboard.load_jobs(
        keyword="SEO",
        company="",
        location="",
        workplace=None,
        source=None,
        posted_within=None,
        limit=100,
    )
    assert not df.empty, "Expected SEO jobs in jobs.db for this regression test"
    assert "title" in df.columns
    # Arrow-backed string dtype is what segfaulted; object is the safe path.
    assert str(df["title"].dtype) == "object"


def test_filter_seo_apptest_does_not_segfault():
    """
    Typing a keyword and applying filters previously SIGSEGV'd in
    pandas string_arrow._from_sequence during load_jobs.
    Run in a subprocess so a segfault is a failed test, not a hung runner.
    """
    script = r"""
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest

root = Path(%r)
sys.path.insert(0, str(root))
os_chdir = __import__("os").chdir
os_chdir(root)

at = AppTest.from_file(str(root / "app.py"), default_timeout=60)
at.run()
assert not at.exception, at.exception

kw = next(t for t in at.text_input if "Keyword" in (t.label or ""))
kw.set_value("SEO")
at.run()
assert not at.exception, at.exception

apply = next(b for b in at.button if "Apply" in (b.label or ""))
apply.click()
at.run()
assert not at.exception, at.exception

captions = [c.value for c in at.caption]
assert any("job(s) found" in c for c in captions), captions
print("FILTER_SEO_OK")
""" % str(ROOT)

    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "PYTHONFAULTHANDLER": "1"},
    )
    assert proc.returncode != -signal.SIGSEGV, (
        "Filter search segfaulted (SIGSEGV). stderr:\n" + (proc.stderr or "")
    )
    assert proc.returncode == 0, (
        f"exit={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert "FILTER_SEO_OK" in proc.stdout
