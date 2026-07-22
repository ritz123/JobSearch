# Shine.com Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Shine.com via `unfenced-group/shine-scraper` as a first-class Apify source.

**Architecture:** New `ShineSource` adapter; register in `get_adapter`; wire CLI choices + React dropdowns; tests mirror Indeed.

**Tech Stack:** Python adapters, Apify actor, FastAPI (passthrough), React Scraper/Jobs pages.

## Global Constraints

- Actor ID: `unfenced-group/shine-scraper`
- Source name: `shine`
- Workplace: post-filter only (no actor input)
- date_posted → daysOld: day=1, week=7, month=30
- max_jobs → maxItems
- details → fetchDetails
- TDD: failing tests before production code
- No live Apify in tests

---

### Task 1: Shine adapter + tests

**Files:**
- Create: `sources/shine.py`
- Modify: `sources/__init__.py`
- Modify: `tests/test_sources.py`
- Modify: `scraper.py` (CLI choices + help text)

- [ ] Write failing tests for adapter registration, `build_input`, normalize, workplace filter, location sanitize
- [ ] Run tests — confirm fail
- [ ] Implement `ShineSource` and register it
- [ ] Add `shine` to CLI `--source` choices
- [ ] Run tests — confirm pass

### Task 2: UI + README

**Files:**
- Modify: `web/src/pages/ScraperPage.tsx`
- Modify: `web/src/pages/JobsPage.tsx`
- Modify: `README.md` (mention Shine)

- [ ] Add `shine` to source `<option>`s; tweak scrape blurb
- [ ] Mention Shine in README sources list
- [ ] Smoke: `python -c "from sources import get_adapter; print(get_adapter('shine').actor_id)"`
