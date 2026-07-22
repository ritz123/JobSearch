# React + FastAPI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace Streamlit with Vite React TS + FastAPI using existing Python modules.

**Architecture:** `api/main.py` exposes REST; `web/` SPA calls it; delete Streamlit entrypoints.

**Tech Stack:** FastAPI, uvicorn, Vite, React, TypeScript, react-router-dom.

---

### Task 1: FastAPI backend

- [ ] Add `fastapi`, `uvicorn` to `pyproject.toml`; remove `streamlit`, `plotly`
- [ ] Create `api/main.py` with health, jobs, stats, searches, scrape, ollama, city-runs, companies
- [ ] CORS for Vite origin
- [ ] `pytest` smoke for `/api/health` and `/api/jobs`

### Task 2: React SPA

- [ ] Scaffold `web/` with Vite React-TS
- [ ] Pages: Jobs, Scraper, CityCareers + shared `api.ts` + layout nav
- [ ] Proxy `/api` to `:8000` in vite.config

### Task 3: Remove Streamlit + runners

- [ ] Delete `app.py`, `pages/`, `.streamlit/`, `run_dashboard.sh`
- [ ] Add `run_web.sh`; point `run.sh` at it
- [ ] Update README briefly

### Task 4: Verify

- [ ] `uv sync`, API boots, `web` builds, unit tests pass
