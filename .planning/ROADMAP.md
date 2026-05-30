# Roadmap: Lynch & Graham Screener — GitHub Pages Migration

## Overview

A brownfield output-layer swap: replace Google Sheets push with a JSON writer, wire it into GitHub Actions, and publish a static interactive dashboard on GitHub Pages. The Python pipeline is already working. The work is sequenced so Google Sheets remains a safety net until the new pipeline is confirmed live and verified end-to-end.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Security & Pipeline Prerequisites** - Fix the hardcoded API key, audit git history, and configure the Actions workflow so the repo is safe to publish and the CI commit chain is correct
- [x] **Phase 2: JSON Output Pipeline** - Replace `push_to_gsheets()` with a JSON writer and verify the full Actions → commit → Pages publish loop with `workflow_dispatch`
- [ ] **Phase 3: Interactive Dashboard** - Build the complete GitHub Pages frontend: Tabulator table with all columns, color coding, filters, Top 20 panel, methodology page, and nav
- [ ] **Phase 4: Google & Tiingo Cleanup** - Remove all Google dependencies and dead Tiingo config from the codebase now that the new pipeline is confirmed

## Phase Details

### Phase 1: Security & Pipeline Prerequisites
**Goal:** The repo is safe to make public and the Actions workflow has correct permissions, git identity, and commit guards in place before any new code runs
**Mode:** mvp
**Depends on:** Nothing (first phase)
**Requirements:** SEC-01, SEC-02, CI-01, CI-02, CI-03, CI-04, CI-05, CI-06
**Success Criteria** (what must be TRUE):
  1. `diagnose_finnhub.py` reads the API key from `os.environ["FINNHUB_API_KEY"]` — no hardcoded string remains
  2. Git history audit confirms no credentials are present; repo can be made public without risk
  3. `screener.yml` declares `permissions: contents: write` and configures `github-actions[bot]` identity before any commit step
  4. `screener.yml` commits only `docs/data/results.json` using a conditional pattern that skips commit when data is unchanged
  5. `docs/.nojekyll` exists and `.gitignore` has a `!docs/data/results.json` exception so the data file can be tracked
**Plans:** 01-01-PLAN.md (1 plan, Wave 1, 5 tasks) ✓ Complete 2026-05-30

### Phase 2: JSON Output Pipeline
**Goal:** The screener writes `results.json` to `docs/data/` on every run and the Actions workflow commits and pushes it — verifiable by triggering `workflow_dispatch` and seeing the file appear on Pages
**Mode:** mvp
**Depends on:** Phase 1
**Requirements:** PY-01, PY-02, PY-03, PY-04
**Success Criteria** (what must be TRUE):
  1. `stock_screener.py` writes `docs/data/results.json` with all screener rows plus a `generated_at` ISO timestamp — `push_to_gsheets()` is no longer called on this code path
  2. The script exits non-zero and skips the write if fewer than 100 rows were produced
  3. A manual `workflow_dispatch` run succeeds: Actions commits `docs/data/results.json` and GitHub Pages serves it at the public URL within ~5 minutes
  4. The JSON file uses compact encoding and is fetchable directly in a browser at `https://<user>.github.io/<repo>/data/results.json`
**Plans:** 1 plan (Wave 1)
Plans:
- [ ] 02-01-PLAN.md — Add write_json() to stock_screener.py and verify end-to-end via workflow_dispatch

### Phase 3: Interactive Dashboard
**Goal:** A user opening the GitHub Pages URL sees a fully functional, color-coded, filterable Lynch/Graham dashboard with a Top 20 panel and a linked methodology page
**Mode:** mvp
**Depends on:** Phase 2
**Requirements:** FE-01, FE-02, FE-03, FE-04, FE-05, FE-06, FE-07, FE-08, FE-09, FE-10, FE-11, FE-12, FE-13, FE-14, FE-15, FE-16, FE-17, DOC-01, DOC-02
**UI hint:** yes
**Success Criteria** (what must be TRUE):
  1. The dashboard loads from the Pages URL, shows a "Data as of [date]" freshness badge, and displays a yellow stale-data banner if data is more than 3 days old
  2. The Tabulator table renders all screener columns sorted by Score descending, with the Ticker column frozen, sticky header, nulls shown as `—`, and error rows hidden by default
  3. Signal columns (Lynch_Status, Graham_Status, Defensive, Lynch_PEG_Band, Status_Combined) show green/yellow/red background colors matching the existing `SIGNAL_COLORS` mapping
  4. "Buy Signals Only" toggle, per-column header filters, ticker search box, and Summary/Full column preset toggle all work client-side with no page reload
  5. The collapsible Top 20 panel is open by default, persists its state in `localStorage`, and clicking a ticker scrolls to and highlights that row in the main table
  6. `methodology.html` presents the Lynch/Graham documentation and the two-item nav header links correctly between Dashboard and Methodology
**Plans:** TBD

### Phase 4: Google & Tiingo Cleanup
**Goal:** All Google Sheets code, dependencies, credentials, and dead Tiingo config are removed from the codebase — the screener has no vestigial output code
**Mode:** mvp
**Depends on:** Phase 3
**Requirements:** CLN-01, CLN-02, CLN-03, CLN-04
**Success Criteria** (what must be TRUE):
  1. `push_to_gsheets()` and its private helpers (`_apply_color_coding`, `_write_docs_tab`, `_write_markdown_tab`) no longer exist in `stock_screener.py`
  2. `gspread` and `google-auth` are absent from `requirements.txt` and `screener.yml` has no `GSHEET_*` environment variable references
  3. Dead Tiingo config (`TIINGO_API_KEYS`, `TIINGO_DELAY_SEC`, related comments) is removed from `stock_screener.py`
  4. A `workflow_dispatch` run after cleanup completes successfully with no import errors or missing-variable failures
**Plans:** TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Security & Pipeline Prerequisites | 1/1 | Complete | 2026-05-30 |
| 2. JSON Output Pipeline | 1/1 | Complete | 2026-05-30 |
| 3. Interactive Dashboard | 0/? | Not started | - |
| 4. Google & Tiingo Cleanup | 0/? | Not started | - |
