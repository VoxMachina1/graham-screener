# Phase 7: Distress Signals, DCF, Stats & Snapshots - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Add Piotroski F-Score and Altman Z'' as proper Safety pillar sub-scores (replacing the interim `is_trap` boolean gate), forward + reverse two-stage DCF with sector guards, a per-metric sector applicability matrix, a `stats.html` universe overview page backed by Python-computed stats, monthly snapshots under `docs/data/snapshots/`, a minimal History nav page listing snapshots, and a refreshed `methodology.html`.

**In scope:** SIGNAL-08, SIGNAL-09, TRAP-03, DCF-01, DCF-02, DCF-03, SECTOR-02, PAGE-02, DATA-01, DATA-02, METH-01 — plus a simple `docs/history.html` snapshot list page (user decision, extends DATA-01).
**Out of scope (defer):** DATA-03 (optional fundamentals cache), archive-browsing UI with date picker, backtest harness, threshold re-tuning.

</domain>

<decisions>
## Implementation Decisions

### Safety Pillar Upgrade (TRAP-03, SIGNAL-08, SIGNAL-09)
- **D-01 — Drop the interim `is_trap` gate entirely.** The boolean `is_trap` and the hard Safety floor-to-0 it produces are retired. Piotroski F-Score and Altman Z'' are scored sub-scores within the Safety pillar — a distressed stock naturally scores low, dragging Safety and OverallScore down proportionally. No binary veto remains.
- **D-02 — Piotroski F-Score (0–9) as a piecewise Safety sub-score.** Use the standard 9-criterion Piotroski (2000) formulation from two years of financial statements. Maps to a 0–100 sub-score via piecewise bands (loud `[ASSUMED]` config constants). Absent → 50.0 (neutral, see D-04).
- **D-03 — Altman Z'' as a piecewise Safety sub-score.** Use the Z'' variant (non-financial, non-manufacturer): Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4. Maps to a 0–100 sub-score: distress zone (Z'' < 1.1) → 0.0; safe zone (Z'' > 2.6) → high score; grey zone interpolated. Absent → 50.0 (neutral, see D-04).
- **D-04 — Absent Safety inputs → neutral 50.0 (USER OVERRIDE of D-01b).** For Piotroski and Altman specifically, when data is unavailable (financials/REITs excluded, or missing statements), contribute 50.0 to the Safety pillar average rather than skipping (D-01b average-over-present). This prevents sector-excluded stocks from unfairly inheriting Safety scores from the remaining inputs. The existing defensive_score, debt_equity, current_ratio inputs retain D-01b (average-over-present) behaviour.
- **D-05 — Trap badge on `top.html` replaced with a Safety pillar score chip.** Remove the `is_trap` badge. Add a Safety chip (like the existing Value/Quality/Growth chips) so low-Safety stocks are visibly flagged by score, not by binary flag. User evaluates distress from the chip + the raw Piotroski/Altman columns in `results.json`.

### DCF (DCF-01, DCF-02, DCF-03)
- **D-06 — WACC = live FRED AAA yield + 5.5% equity risk premium.** Rate-relativized (consistent with the Phase 5 yield-threshold pattern). Config-overridable (`DCF_ERP = 5.5`). Asserts terminal growth < WACC at compute time; raises a loud config error if violated.
- **D-07 — Two-stage DCF: 5-year high-growth stage + terminal value.** Stage 1: apply the stock's realized 5yr EPS CAGR (from Phase 5.1) for 5 years. Terminal: Gordon Growth Model using terminal growth rate (D-08).
- **D-08 — Terminal growth = `min(realized_5yr_cagr, 3.0%)`.** Caps terminal growth at roughly long-run nominal GDP. Uses the stock's own CAGR but never assumes indefinite above-economy growth.
- **D-09 — Reverse DCF non-convergence → `None` + sentinel flag.** Emit `dcf_reverse_converged=False` on the row alongside `None` for the implied-growth field when the solver doesn't find a root. Never a silent default or clipped value.
- **D-10 — DCF sector guard: Financial Services + REITs excluded.** yfinance returns "Financial Services" and "Real Estate" as sector strings. Both are treated as `missing` (None), not zero — consistent with SECTOR-02. Cyclicals (Energy, Materials) get DCF with a visible `[CYCLICAL]` coverage flag; user interprets with caution.

### Sector Applicability Matrix (SECTOR-02)
- **D-11 — Per-metric exclusion table, missing = None (never zero).** When a sector renders a metric inapplicable, the metric is `None` — average-over-present handles it. Proposed exclusions (Claude's discretion to finalize):
  - Financial Services: DCF, EV/EBIT, Altman Z'' (Z'' designed for non-financials)
  - Real Estate (REITs): DCF (FFO-based, not FCF-based)
  - All other sectors: no exclusions (Piotroski applies universally)

### Historic Snapshots (DATA-01, DATA-02)
- **D-12 — Monthly cadence: first weekday of each month.** The Actions workflow detects the date and commits `docs/data/snapshots/YYYY-MM-DD.json` only when the condition is met. Reuses the min-row guard (`< 100 rows → skip`). `.gitignore` gets `!docs/data/snapshots/*.json` exception.
- **D-13 — Simple `docs/history.html` snapshot list page.** A minimal static page (consistent with the Nord theme and `buildNav` pattern from `app.js`) listing available snapshots with dates and download links. Added as the 4th nav link (Dashboard / Top Picks / Stats / History / Methodology). Stats takes the PAGE-04 slot; History is additive.

### stats.html (PAGE-02)
- **D-14 — Stat cards + simple tables; no charting library.** Score distribution shown as 5-bucket summary (0–20 / 20–40 / 40–60 / 60–80 / 80–100) in text/number cards. Buy-signal counts, sector breakdown, and coverage stats as HTML tables. No external charting dependency — consistent with the no-build-step constraint.
- **D-15 — Read-only: stats computed in Python, emitted to JSON.** Python computes all stats during the screener run and writes a `docs/data/stats.json` (with a corresponding `.gitignore` exception `!docs/data/stats.json`). `stats.html` fetches and renders it — no client-side computation. Cache-busted fetch like `results.json`.

### Claude's Discretion
- Exact Piotroski 9-criterion variable implementation (ROA, CFO/Assets, accruals, leverage, liquidity, dilution, gross margin, asset turnover — planner may verify against Piotroski 2000)
- Altman Z'' variable definitions (X1=WC/TA, X2=RE/TA, X3=EBIT/TA, X4=BVE/TL) and distress-zone boundary thresholds (1.1 / 2.6) as loud `[ASSUMED]` config constants
- Equity risk premium constant default (5.5%) as loud `[ASSUMED]` config entry `DCF_ERP`
- `stats.json` schema and exact field names
- `history.html` page design details (table or list, date formatting, download link format)
- `methodology.html` update scope — add sections for Piotroski, Altman Z'', DCF, sector matrix; retain all existing content
- DATA-03 (fundamentals cache) — defer to a follow-up phase; do NOT implement in Phase 7

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase context & scoring contracts
- `.planning/ROADMAP.md` (Phase 7 section) — goal, success criteria, requirement list
- `.planning/REQUIREMENTS.md` — SIGNAL-08/09, TRAP-03, DCF-01/02/03, SECTOR-02, PAGE-02, DATA-01/02/03, METH-01
- `.planning/phases/05-score-foundation-public-top-n/05-CONTEXT.md` — Phase 5 scoring contract (absolute thresholds, winsorization, average-over-present, D-01 negative-routing)
- `.planning/phases/06-cheap-factors-sector/06-CONTEXT.md` — Phase 6 decisions (D-04 Safety absent→neutral override context, sector from yfinance)
- `.planning/phases/06-cheap-factors-sector/06-02-SUMMARY.md` — final `overall_score()` signature, 15-leaf coverage count, Value sub-group architecture to extend

### Existing code to extend
- `stock_screener.py` — read the SCORE_* config block, `overall_score()`, `process_ticker()`, `write_json()`, `get_combined_data()`, `get_yf_price_and_history()`, and `get_finnhub_metrics()` before planning
- `docs/app.js` — `buildNav()` pattern, freshness logic, formatters — extend for History/Stats nav
- `docs/top.html` — pillar chip pattern to replicate for Safety chip (replacing trap badge)
- `.planning/research/v2-METHODOLOGY-EXPANSION.md` — original signal evidence tiers and the 4-pillar design intent

### Methodology research context
- `.planning/phases/05-score-foundation-public-top-n/05.1-FIXES-SUMMARY.md` — Phase 5.1 growth CAGR anchoring (feeds DCF Stage 1 growth input)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_yf_price_and_history()` — already fetches `t.cashflow`, `t.income_stmt`, `t.balance_sheet` for Phase 6 factors; Piotroski needs two years of these statements — reuse the same Ticker object
- `get_finnhub_metrics()` — fetches the full `metric=all` bundle; Altman inputs (total debt, equity, retained earnings, EBIT, working capital) may partially overlap with already-fetched fields
- `_piecewise_score()`, `_winsorize()`, `_avg_present()`, `_recency_multiplier()` — the scoring primitives; Piotroski and Altman sub-scores use the same pattern
- `SCORE_*` config block (~82–191) — extend with `SCORE_PIOTROSKI_*`, `SCORE_ALTMAN_*`, `SCORE_DCF_*` bands
- `overall_score()` current signature has 19 params (10 original + 9 Phase-6); Phase 7 adds Piotroski, Altman, DCF discount % as new None-defaulted params
- `write_json()` — already emits nested `scores` object; extend with Safety sub-group keys
- `buildNav()` in `app.js` — takes a string key; extend to support `"stats"` and `"history"` nav states with a 5-link nav

### Established Patterns
- Phase 6 pure-helper pattern: `_compute_*` functions are pure numeric → add `_compute_piotroski()`, `_compute_altman_z()`, `_compute_dcf()` following the same signature (inputs → float|None)
- Candidate-label lists (`OCF_LABELS`, `EBIT_LABELS`, etc.) for yfinance statement reads — Piotroski needs retained earnings, working capital → add label lists
- Offline test pattern: `os.environ.setdefault` before import, vanilla assert, `run_all()` with PASS/FAIL — new `tests/test_distress_phase7.py` and `tests/test_dcf_phase7.py` follow this
- Sector guard: use `fund.get("Sector")` already on the row dict (Phase 6) to gate metrics; "Financial Services" / "Real Estate" are the yfinance strings to match

### Integration Points
- `process_ticker()` — passes factor fields to `overall_score()` using `fund.get(key)` (snake_case keys confirmed by CR-01 fix); Phase 7 adds Piotroski score, Altman Z'', DCF discount %, DCF intrinsic value as new flat columns
- `write_json()` — emit Piotroski_F, Altman_Z, DCF_Intrinsic_Value, DCF_Discount_Pct, DCF_Implied_Growth, dcf_reverse_converged as new flat columns; add piotroski/altman/dcf_discount sub-scores to nested `scores` object
- `screener.yml` — snapshot step: add conditional block that commits to `docs/data/snapshots/YYYY-MM-DD.json` on first-weekday-of-month; reuses `< 100 row` guard logic

</code_context>

<specifics>
## Specific Ideas

- **Dropping is_trap** is a deliberate design choice: the user explicitly wants to evaluate distress from numbers (Piotroski, Altman, Safety chip) rather than a binary filter. Do not re-introduce an automatic exclusion mechanism.
- **Safety chip on top.html** mirrors the Value/Quality/Growth chips — same styling, just labelled "Safety". The old "⚠ TRAP" badge is removed.
- **History page** should be dead-simple: a dated list/table of snapshot files with download links. No data visualisation, no Tabulator. It fetches a `snapshots/index.json` or similar manifest; the Python writer maintains the manifest.
- **stats.json** should include: score distribution buckets, buy-signal count, trap-count (now "low Safety" count), sector breakdown (count + avg score per sector), and coverage stats (avg coverage_pct, pct of tickers with each signal present).

</specifics>

<deferred>
## Deferred Ideas

- **DATA-03** (30-day fundamentals cache) — adds meaningful engineering complexity; defer to a follow-up phase once Phase 7 runtime is benchmarked
- **Archive-browsing UI** — date picker or page to browse historical snapshots — deferred per existing REQUIREMENTS.md note; `history.html` is the minimal stub
- **Threshold re-tuning** — calibrate Piotroski/Altman/DCF bands after observing the live distribution in `stats.html`; deferred to Phase 8 / monitored tuning
- **Backtest harness** — validate composite against historic snapshots; locked decision, deferred

</deferred>

---

*Phase: 7-distress-signals-dcf-stats-snapshots*
*Context gathered: 2026-06-28*
