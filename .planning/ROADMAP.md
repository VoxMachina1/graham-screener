# Roadmap: Lynch & Graham Screener — GitHub Pages Migration

## Overview

A brownfield output-layer swap: replace Google Sheets push with a JSON writer, wire it into GitHub Actions, and publish a static interactive dashboard on GitHub Pages. The Python pipeline is already working. The work is sequenced so Google Sheets remains a safety net until the new pipeline is confirmed live and verified end-to-end.

**Milestone v2.0 — Methodology Expansion & Scoring (Phases 5–7):** Move the screener from binary Lynch/Graham buy-signals to a multi-factor, absolute 0–100 ranking (4-pillar composite: Value/Quality/Growth/Safety), add new valuation signals (distance-from-low, FCF yield, EV/EBIT, Piotroski, Altman, forward + reverse DCF), and ship dedicated Top-Picks and Stats pages plus periodic historic snapshots. Phases follow a research-prescribed, dependency-forced ordering: fix the Buy Price denominator first, build the composite from existing metrics behind an interim trap-gate, then layer in cheap factors + sector, then the heavy distress/DCF signals.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

### Milestone v1.0 — GitHub Pages Migration (complete)

- [x] **Phase 1: Security & Pipeline Prerequisites** - Fix the hardcoded API key, audit git history, and configure the Actions workflow so the repo is safe to publish and the CI commit chain is correct
- [x] **Phase 2: JSON Output Pipeline** - Replace `push_to_gsheets()` with a JSON writer and verify the full Actions → commit → Pages publish loop with `workflow_dispatch`
- [x] **Phase 3: Interactive Dashboard** - Build the complete GitHub Pages frontend: Tabulator table with all columns, color coding, filters, Top 20 panel, methodology page, and nav (completed 2026-05-31)
- [x] **Phase 4: Google & Tiingo Cleanup** - Remove all Google dependencies and dead Tiingo config from the codebase now that the new pipeline is confirmed (completed 2026-05-31)

### Milestone v2.0 — Methodology Expansion & Scoring

- [x] **Phase 5: Score Foundation + Public Top-N** - Fix the Buy Price bug (fixture-verified), build the 4-pillar absolute composite from existing metrics behind an interim value-trap gate, and ship `top.html` with shared `app.js` and full-site nav (completed 2026-06-19)
  - [x] **Phase 5.1 (INSERTED): Corrective fixes** - Post-live-validation: anchored growth to the realized EPS CAGR (Finnhub `epsGrowth5Y` was inflated → fake 25% growers) and made the trap gate's EPS-stability check window-aware (8-of-10 rule was structurally 0 on 4-yr data → trap tripped for 100% of tickers / dead Safety pillar). See `phases/05-score-foundation-public-top-n/05.1-FIXES-SUMMARY.md` (completed 2026-06-20)
- [x] **Phase 6: Cheap Factors + Sector** - Add the GICS sector field and the high-evidence factors that mostly already live in the Finnhub bundle (52w/5y distance + recency, FCF yield, EV/EBIT + earnings yield, ROIC, shareholder yield) and fold them into the composite
- [ ] **Phase 7: Distress Signals, DCF, Stats & Snapshots** - Add Piotroski/Altman distress signals (upgrading the trap-gate), forward + reverse DCF with sector guards, the sector applicability matrix, `stats.html`, historic snapshots + cache, and refreshed methodology docs

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

**Goal:** A user opening the GitHub Pages URL sees a fully functional, color-coded, filterable Lynch/Graham dashboard with a linked methodology page
**Mode:** mvp
**Depends on:** Phase 2
**Requirements:** FE-01, FE-02, FE-03, FE-04, FE-05, FE-06, FE-07, FE-08, FE-09, FE-10, FE-11, FE-12, FE-13, FE-14, DOC-01, DOC-02
**UI hint:** yes
**Success Criteria** (what must be TRUE):

  1. The dashboard loads from the Pages URL, shows a "Data as of [date]" freshness badge, and displays a yellow stale-data banner if data is more than 3 days old
  2. The Tabulator table renders all screener columns sorted by Score descending, with the Ticker column frozen, sticky header, nulls shown as `—`, and error rows hidden by default
  3. Signal columns (Lynch_Status, Graham_Status, Defensive, Lynch_PEG_Band, Lynch_PEG_Status, Lynch_PEGY_Status) show green/yellow/red background colors matching the SIGNAL_COLORS mapping
  4. "Buy Signals Only" toggle, per-column header filters, ticker search box, and Summary/Full column preset toggle all work client-side with no page reload
  5. `methodology.html` presents the Lynch/Graham documentation and the two-item nav header links correctly between Dashboard and Methodology

**Plans:** 2/2 plans complete

### Phase 4: Google & Tiingo Cleanup

**Goal:** All Google Sheets code, dependencies, credentials, and dead Tiingo config are removed from the codebase — the screener has no vestigial output code
**Mode:** mvp
**Depends on:** Phase 3 — including **03-02-PLAN.md** (`docs/methodology.html`) which must be executed before Phase 4 begins
**Requirements:** CLN-01, CLN-02, CLN-03, CLN-04
**Success Criteria** (what must be TRUE):

  1. `push_to_gsheets()` and its private helpers (`_apply_color_coding`, `_write_docs_tab`, `_write_markdown_tab`) no longer exist in `stock_screener.py`
  2. `gspread` and `google-auth` are absent from `requirements.txt` and `screener.yml` has no `GSHEET_*` environment variable references
  3. Dead Tiingo config (`TIINGO_API_KEYS`, `TIINGO_DELAY_SEC`, related comments) is removed from `stock_screener.py`
  4. A `workflow_dispatch` run after cleanup completes successfully with no import errors or missing-variable failures

**Plans:** TBD

### Phase 5: Score Foundation + Public Top-N

**Goal:** The screener ranks stocks by an absolute 0–100 `OverallScore` (4-pillar Value/Quality/Growth/Safety) built on a corrected, hand-verified Buy Price, and a public `docs/top.html` page surfaces the Top 10/25 — with every cheap-but-dying stock caught by an interim value-trap gate before it can top a public list. This is the locked first executable phase: self-contained, built entirely from metrics that already exist, no new data fetches.
**Depends on:** Phase 4 (clean pipeline, no vestigial output code)
**Requirements:** FIX-01, FIX-02, SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05, SCORE-06, SCORE-07, SCORE-08, TRAP-01, TRAP-02, PAGE-01, PAGE-03, PAGE-04
**Success Criteria** (what must be TRUE):

  1. The Buy Price root cause is diagnosed and fixed across Lynch buy price and Graham fair value; a committed spot-check fixture for at least one hand-verified ticker (e.g. JNJ/KO) passes, and `Lynch_Discount_Pct` / `Graham_Discount_Pct` read as sane before any pillar consumes them
  2. Each row carries an `OverallScore` (0–100) that decomposes into Value/Quality/Growth/Safety pillar sub-scores, exposed in `results.json` as flat columns plus a nested `scores` object and surfaced in the UI; `OverallScore` is the primary sort key, replacing `CombinedScore`
  3. Raw metrics map to sub-scores via version-controlled absolute thresholds (piecewise-linear bands, yield-based ones rate-relativized to the live FRED AAA yield) with both-tail winsorization, so no single glitch (e.g. a 1179% growth episode) can dominate a sub-score
  4. Missing metrics are averaged over present metrics within a pillar and a per-row coverage flag is emitted; a missing Safety input is treated as "unknown," never "safe"; correlated Value metrics are grouped so the Value pillar is not a single cheapness rank
  5. `docs/top.html` shows the Top 10/25 (toggle) ranked by `OverallScore` with pillar sub-scores and headline signals, every row carries a value-trap badge driven by an interim gate (debt/equity, current ratio, EPS stability, negative FCF), and the shared `docs/app.js` powers fetch/format/color/freshness across Dashboard, Top Picks, and Methodology nav links

**Plans:** 3 plans (Wave 1 -> 2 -> 3)
Plans:
**Wave 1**

- [x] 05-01-PLAN.md - Buy Price audit + KO fixture + negative-input routing + FCF passthrough (FIX-01/02) — Complete 2026-06-19

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 05-02-PLAN.md - 4-pillar OverallScore engine + config constants + interim trap gate + JSON schema + sort swap (SCORE-01..08, TRAP-01) — Complete 2026-06-19

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 05-03-PLAN.md - docs/app.js + docs/top.html (Top 10/25, trap badge) + dashboard score columns + 3-link nav (PAGE-01/03/04, TRAP-02) — Complete 2026-06-19

**UI hint:** yes

### Phase 6: Cheap Factors + Sector

**Goal:** The GICS sector field is threaded through every row (a prerequisite for Phase 7's DCF/distress guards), and the high-evidence factors that mostly already live in the discarded Finnhub `metric=all` bundle — plus one new 5-year price-history fetch — deepen the Value/Quality/Safety pillars at near-zero new I/O.
**Depends on:** Phase 5 (composite engine + thresholds + winsorization contract must exist to fold new factors into)
**Requirements:** SECTOR-01, SIGNAL-01, SIGNAL-02, SIGNAL-03, SIGNAL-04, SIGNAL-05, SIGNAL-06, SIGNAL-07
**Success Criteria** (what must be TRUE):

  1. Each row carries a `Sector` field fetched per ticker (GICS) and threaded through the pipeline, ready to gate the Phase 7 DCF/distress signals
  2. New price-based signals appear per ticker: distance below 52-week high / above 52-week low (%), distance above 5-year low (%), and weeks-since-52w-low / weeks-since-5y-low recency — driven by a new 5-year history fetch
  3. New fundamental factors appear per ticker: FCF yield (FCF / market cap), EV/EBIT + earnings yield (EBIT/EV), ROIC as an absolute Quality input (not a Greenblatt rank-sum), and shareholder yield (dividend + net buyback) with a low-coverage flag where share-count data is sparse
  4. Each new metric is clamped/winsorized as it is added and folded into the appropriate pillar via the Phase 5 threshold engine, so the composite deepens without any single new factor able to dominate

**Plans:** 2 plans (chunked: data layer + scoring fold)Plans:
**Wave 1**

- [ ] 06-01-PLAN.md — Data layer: Sector + 5y-weekly distance/recency signals + 4 cheap-factor fundamentals (FCF yield, EV/EBIT + earnings yield, ROIC, shareholder yield) emitted as additive row-dict fields with coverage flags

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 06-02-PLAN.md — Scoring fold: thread the new fields into the Phase 5 4-pillar composite (Value sub-groups, ROIC→Quality, winsorize/bands, overall_score) — TBD

### Phase 7: Distress Signals, DCF, Stats & Snapshots

**Goal:** The heaviest fetches land last — Piotroski F-Score and Altman Z'' upgrade the interim trap-gate into the real Safety-pillar driver, forward + reverse DCF give per-stock intrinsic value and an expectations gap, a per-metric sector applicability matrix keeps sector-invalid signals out of the score, and `stats.html` plus committed historic snapshots make the universe observable and comparable over time.
**Depends on:** Phase 6 (the `Sector` field gates DCF/EV-EBIT/Altman/Piotroski applicability; the finalized schema makes snapshots comparable)
**Requirements:** SIGNAL-08, SIGNAL-09, TRAP-03, DCF-01, DCF-02, DCF-03, SECTOR-02, PAGE-02, DATA-01, DATA-02, DATA-03, METH-01
**Success Criteria** (what must be TRUE):

  1. Piotroski F-Score (0–9, from two years of statements) and Altman Z'' (with distress zones, used as a penalty/veto) are computed per ticker and replace/augment the interim gate as the Safety-pillar driver
  2. Forward two-stage DCF intrinsic value + discount % and reverse-DCF implied-vs-actual-growth gap appear per ticker, sector-guarded (financials excluded, cyclicals flagged), asserting terminal-growth < discount-rate, with the bounded reverse solver emitting `None` on non-convergence — never a silent default
  3. A per-metric sector applicability matrix governs which signals are valid per sector; invalid signals (e.g. DCF/EV-EBIT/Altman/Piotroski for financials) are treated as missing, never zero
  4. `docs/stats.html` presents the universe overview — score distribution, buy-signal counts, sector breakdown, and data-coverage stats — and `methodology.html` is updated to document the new signals, the 4-pillar absolute scoring, the thresholds, and the sector guards
  5. The Actions workflow commits periodic (weekly/monthly) snapshots of `results.json` under `docs/data/snapshots/` (with the `!docs/data/snapshots/*.json` `.gitignore` exception and the reused min-row guard so no empty/partial snapshot lands), and an optional 30-day fundamentals cache bounds runtime/rate-limit for the heavy statement fetches

**Note on DATA-03:** The optional 30-day fundamentals cache is **deferred out of Phase 7** per user decision (CONTEXT.md Deferred Ideas) — it adds engineering complexity and is best added once Phase 7 runtime is benchmarked. All other Phase 7 requirements are planned below.

**Plans:** 3 plans (Wave 1 -> 2 -> 3)
Plans:
**Wave 1**

- [ ] 07-01-PLAN.md — Data layer: _compute_piotroski / _compute_altman_z / _compute_dcf_forward / _compute_dcf_reverse pure helpers + two-year statement threading + label lists + scipy dependency + offline tests (SIGNAL-08/09, DCF-01/02/03)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 07-02-PLAN.md — Scoring fold: rewrite Safety pillar (drop is_trap, Piotroski+Altman subs, D-04 absent→50) + sector applicability gate + DCF as 4th Value sub-group + new flat columns + stats.json writer (TRAP-03, SECTOR-02, PAGE-02 data half)

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 07-03-PLAN.md — Pages + pipeline: 5-link nav + stats.html + history.html + top.html Safety chip + .gitignore exceptions + screener.yml monthly snapshot step + methodology refresh + human-verify (PAGE-02, DATA-01/02, METH-01, TRAP-03 UI)

**UI hint:** yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Security & Pipeline Prerequisites | 1/1 | Complete | 2026-05-30 |
| 2. JSON Output Pipeline | 1/1 | Complete | 2026-05-30 |
| 3. Interactive Dashboard | 2/2 | Complete | 2026-05-31 |
| 4. Google & Tiingo Cleanup | 1/1 | Complete | 2026-05-31 |
| 5. Score Foundation + Public Top-N | 3/3 | Complete | 2026-06-19 |
| 6. Cheap Factors + Sector | 2/2 | Complete | 2026-06-28 |
| 7. Distress Signals, DCF, Stats & Snapshots | 0/3 | Planned | - |
