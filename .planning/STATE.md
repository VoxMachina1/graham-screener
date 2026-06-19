---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: — Methodology Expansion & Scoring
status: planning
stopped_at: Phase 5 UI-SPEC approved
last_updated: "2026-06-19T04:13:32.773Z"
last_activity: 2026-06-17 — v2.0 roadmap created (Phases 5–7), 35 requirements mapped
progress:
  total_phases: 7
  completed_phases: 4
  total_plans: 5
  completed_plans: 5
  percent: 57
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-17)

**Core value:** A public, shareable URL that shows today's Lynch/Graham buy signals — no Google account, no friction, just open the link.
**Current focus:** Phase 5 — Score Foundation + Public Top-N (roadmap just created, awaiting planning)

## Current Position

Phase: 5 — Score Foundation + Public Top-N (not started)
Plan: —
Status: Roadmap created for v2.0; ready to plan Phase 5
Last activity: 2026-06-17 — v2.0 roadmap created (Phases 5–7), 35 requirements mapped

Milestone v1.0 (Phases 1–4) complete. v2.0 adds three phases (5, 6, 7) under a research-prescribed, dependency-forced ordering:

- **Phase 5 (A):** Buy Price fix → 4-pillar composite from existing metrics → interim trap-gate → public Top-N (`top.html`, `app.js`, nav). Self-contained, no new data fetches.
- **Phase 6 (B):** GICS sector field + cheap high-evidence factors (52w/5y distance + recency, FCF yield, EV/EBIT, ROIC, shareholder yield), mostly mined from the already-fetched Finnhub bundle + one new 5y history fetch.
- **Phase 7 (C):** Piotroski/Altman distress signals, forward + reverse DCF, sector applicability matrix, `stats.html`, snapshots + cache, methodology refresh.

## Performance Metrics

**Velocity:**

- Total plans completed: 2 (v1.0)
- Average duration: —
- Total execution time: —

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 03 | 2 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 03-interactive-dashboard P02 | 15m | 1 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table. v2.0 locked decisions are in `.planning/research/v2-METHODOLOGY-EXPANSION.md`.
Recent decisions affecting current work:

- **Absolute thresholds, not percentile ranks** — comparability across snapshots; thresholds live as version-controlled config constants, yield-based ones rate-relativized to live FRED AAA yield.
- **Additive JSON schema** — leave existing flat keys (and the `Lynch_Lynch_`/`Graham_Graham_` double-prefix wart) untouched; add `OverallScore`, flat pillar scores, and a nested `scores` object.
- **Dependency-forced ordering** — Buy Price fix BEFORE composite; interim trap-gate BEFORE public Top-N ships; sector field (Phase 6) BEFORE DCF/distress guards (Phase 7).
- **Magic Formula rank-sum is an anti-feature** — ship EBIT/EV + ROIC as absolute inputs, not the Greenblatt rank.
- **Backtest harness deferred** (locked decision 3) — Phase 7 snapshots are the future substrate.

### Pending Todos

None.

### Blockers/Concerns

- **Buy Price root cause not yet diagnosed** — STATE.md only records "visibly wrong across all tickers." Phase 5 task 1 must diagnose the root cause (sign/inversion, target-vs-buy-below) and verify against a hand-computed fixture ticker BEFORE the composite consumes any discount field. Blocking for the whole milestone.
- **Finnhub free-tier field coverage unconfirmed** — `freeCashFlowAnnual`, EV/EBIT inputs, `roicTTM`, `roeAnnual` populate inconsistently across the 550-ticker universe. Validate coverage in Phase 6 before scoring math depends on these fields (average-over-present handles gaps, but weighting needs real coverage).
- **Absolute threshold calibration has no empirical anchor** (no backtest) — keep thresholds as loud config constants and monitor the distribution in `stats.html` (Phase 7); expect tuning iterations.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| bug | Formula audit — Buy Price is visibly wrong across all tickers, calling all Lynch/Graham math into question. Audit every formula implementation against source definitions (Lynch PEG/PEGY buy price, Graham VA/VB/FV, combined score) and add a spot-check fixture for at least one ticker with known manually-verified values. | **Scheduled — Phase 5 (FIX-01/02)** | 2026-05-31 |
| bug | BRK-B data sourcing — audit complete (2026-06-02). Root causes found and fixed: (1) `/1500` EPS scaling was applied unconditionally in process_ticker(), including to yfinance fallback EPS which is already in Class B terms — fixed by moving scaling into get_combined_data() immediately after the Finnhub fetch. (2) results.json was stale (generated 13 min before the GROWTH_CAP fix commit). All other fields (price, P/B, market cap, current_ratio, debt_equity) confirmed correct. Annual EPS from yfinance confirmed to be in Class B terms. Finnhub growth (1179%) is garbage data capped at 25% by existing GROWTH_CAP — growth signal for BRK-B remains unreliable due to GAAP EPS volatility from mark-to-market. | Fixed | 2026-06-02 |
| v2 | Advanced numeric range filter sliders | Deferred | Roadmap init |
| v2 | Historical results archive browsing UI — date picker / archive page to view past snapshots (snapshots themselves are produced in v2.0 by DATA-01; browsing them is deferred) | Deferred | Phase 3 |
| v2 | Dark mode toggle | Deferred | Roadmap init |
| v2 | Column visibility picker | Deferred | Roadmap init |
| v2 | Methodology sourcing — add citations to original Lynch/Graham writings and interviews for each criterion on methodology.html (e.g. One Up on Wall Street for Lynch PEG thresholds, The Intelligent Investor chapters for Graham formulas and defensive checklist) | Deferred | Phase 3 |
| v2 | BRK-B share class ratio — config-driven /1500 scaling mechanism for non-standard tickers (Class B shares, ADRs). Blocked on BRK-B data sourcing bug above. | Deferred | Phase 4 |
| v2+ | Backtest harness (Phase D) — validate the composite against historic snapshots; locked decision 3, deferred. Phase 7 snapshots are the substrate. | Deferred | v2.0 research |

## Session Continuity

Last session: 2026-06-18T22:32:54.887Z
Stopped at: Phase 5 UI-SPEC approved
Resume file: .planning/phases/05-score-foundation-public-top-n/05-UI-SPEC.md
Next: `/gsd-plan-phase 5`
