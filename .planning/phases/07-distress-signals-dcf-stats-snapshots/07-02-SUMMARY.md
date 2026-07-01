---
phase: 07-distress-signals-dcf-stats-snapshots
plan: "02"
subsystem: scoring
tags: [piotroski, altman-z, dcf, sector-gate, stats-json, scoring-engine]

# Dependency graph
requires:
  - phase: 07-distress-signals-dcf-stats-snapshots (plan 01)
    provides: "_compute_piotroski, _compute_altman_z, _compute_dcf_forward, _compute_dcf_reverse pure helpers; income_stmt_df/balance_sheet_df/cashflow_df on get_yf_price_and_history(); DCF_EXCLUDED_SECTORS/ALTMAN_EXCLUDED_SECTORS constants"
provides:
  - "overall_score() Safety pillar rewritten: Piotroski + Altman + defensive/de/cr, is_trap removed from signature, 17-leaf coverage"
  - "_sector_allows(fund, metric) sector applicability gate (dcf/altman/earnings_yield/ev_ebit)"
  - "process_ticker() wiring: sector-gated Piotroski/Altman/DCF-forward/DCF-reverse, 6 new flat columns, 3 sub-score columns"
  - "write_json() nested scores object extended (piotroski/altman/dcf_discount); docs/data/stats.json writer via _compute_stats(df)"
affects: [07-03-PLAN.md (stats.html/history.html consume docs/data/stats.json; top.html Safety chip replaces trap badge)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_sector_allows(fund, metric) unified sector gate for D-10 (dcf/altman) and D-11 (earnings_yield/ev_ebit); sector=None applies no exclusion (Pitfall 7)"
    - "_prev_frame(df) = df.iloc[:, 1:] — slices a raw newest-first multi-year statement into the 'prev' argument _compute_piotroski expects (prev.columns[0] becomes prior year)"
    - "_compute_stats(df) pure DataFrame transform, tolerant of missing columns (used directly by unit tests with partial fixtures)"

key-files:
  created: []
  modified:
    - "stock_screener.py (_sector_allows, get_combined_data DataFrame threading, process_ticker distress/DCF wiring, _compute_stats + STATS_PATH, write_json scores + stats.json write)"
    - "tests/test_distress_phase7.py (_sector_allows tests, _compute_stats tests, sector-exclusion-constant tests, run_all() registration)"

key-decisions:
  - "get_combined_data() was missing income_stmt_df/balance_sheet_df/cashflow_df in its return dict despite get_yf_price_and_history() providing them (Wave 1 gap) — added as a Rule 3 blocking-issue fix so process_ticker can reach the raw statements via fund.get(...)"
  - "_sector_allows() extended beyond RESEARCH.md's dcf/altman scope to also cover D-11's earnings_yield/ev_ebit exclusion, unifying all sector-gate logic into one testable pure function instead of an inline Financial-Services conditional"
  - "low_safety_count threshold = score_safety < 30.0, stored as LOW_SAFETY_THRESHOLD constant, tagged [ASSUMED] per RESEARCH.md"
  - "_compute_stats() tolerates DataFrames missing expected columns (checks 'col in df.columns' before access) so it works against both the full production df and narrow unit-test fixtures"

requirements-completed: [TRAP-03, SECTOR-02, SIGNAL-08, SIGNAL-09, DCF-01, DCF-02, DCF-03, PAGE-02]

# Metrics
duration: 35min
completed: 2026-06-30
---

# Phase 07 Plan 02: Distress + DCF Scoring Integration Summary

**Sector-gated Piotroski/Altman/DCF wired into process_ticker() and overall_score() (17-leaf coverage, is_trap demoted to diagnostic), plus a new `_compute_stats(df)` writer producing `docs/data/stats.json` for the Wave 3 stats page.**

## Performance

- **Duration:** ~35 min (continuation session; Task 1 was already complete from a prior session)
- **Tasks:** 2 (Task 1 completed in prior session — commits c2c57cd/2964df6; Task 2 completed this session)
- **Files modified:** 2 (stock_screener.py, tests/test_distress_phase7.py)

## Accomplishments

- `overall_score()` Safety pillar rewritten in a prior session (Task 1): `is_trap` parameter removed entirely; Safety = average of Piotroski + Altman (absent → 50.0 neutral, D-04) + defensive/debt-equity/current-ratio; DCF discount scored as a 4th Value sub-group; coverage denominator is now 17 leaves.
- This session (Task 2): wired the Wave 1 pure helpers into `process_ticker()` with sector gating, added the 6 new flat columns + 3 sub-score columns, extended `write_json()`'s nested `scores` object, and implemented `_compute_stats()` + `docs/data/stats.json` output.
- Discovered and fixed a Wave 1 gap: `get_combined_data()` never threaded `income_stmt_df`/`balance_sheet_df`/`cashflow_df` from `get_yf_price_and_history()` into the `fund` dict `process_ticker()` actually receives — fixed as part of this task (see Deviations).
- Added `_sector_allows(fund, metric)` as a single testable gate covering both the DCF/Altman sector exclusions (D-10) and the Financial-Services EV/EBIT + earnings-yield exclusion (D-11).

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite the Safety pillar in overall_score()** (prior session) — `c2c57cd` (test: failing tests for Safety rewrite), `2964df6` (feat: Safety pillar rewrite, 17-leaf coverage)
2. **Task 2: Wire DCF + distress into process_ticker(), compute stats.json** (this session) — `410344a` (test: sector-gate, distress/DCF wiring, stats.json tests), `91b6ebb` (feat: process_ticker wiring + `_compute_stats` + `write_json` extension)

## Files Created/Modified

- `stock_screener.py`:
  - `_sector_allows(fund, metric)` — new gate helper (near `DCF_EXCLUDED_SECTORS`/`ALTMAN_EXCLUDED_SECTORS`)
  - `get_combined_data()` — now threads `income_stmt_df`/`balance_sheet_df`/`cashflow_df` into its return dict
  - `process_ticker()` — sector-gated Piotroski/Altman/DCF-forward/DCF-reverse block after `trap_gate()`; D-11 earnings_yield/ev_ebit gating; `overall_score()` call extended with `piotroski_f`/`altman_z`/`dcf_discount_pct`; 6 new flat columns + 3 sub-score columns
  - `_compute_stats(df)` + `STATS_PATH` + `LOW_SAFETY_THRESHOLD` — new universe-stats pure helper and its output path
  - `write_json()` — nested `scores` object gains `piotroski`/`altman`/`dcf_discount`; writes `docs/data/stats.json` after `results.json`
- `tests/test_distress_phase7.py`:
  - `_sector_allows` tests (Financial Services excludes altman/dcf/earnings_yield/ev_ebit; Real Estate excludes dcf only; sector=None/other allows all)
  - `_compute_stats` tests (bucket-sum invariant, low_safety_count<30, sector_breakdown grouping incl. None→"Unknown", buy_signal_count, required-keys schema) — these were present as an uncommitted draft from the interrupted session and matched Task 2's spec, so kept as-is
  - `DCF_EXCLUDED_SECTORS`/`ALTMAN_EXCLUDED_SECTORS` constant tests (also from the draft)
  - All of the above (plus the previously-drafted-but-unregistered tests) added to `run_all()`

## Final `overall_score()` Signature (Task 1, confirmed unchanged this session)

```python
def overall_score(
    lynch_discount, graham_discount, defensive_score, debt_equity, current_ratio,
    growth_g, growth_stability, coverage_fraction, aaa_yield,
    fcf_yield=None, earnings_yield=None, shareholder_yield=None, roic=None,
    dist_52w_low=None, dist_52w_high=None, dist_5y_low=None,
    weeks_since_52w_low=None, weeks_since_5y_low=None,
    piotroski_f: int | None = None,
    altman_z: float | None = None,
    dcf_discount_pct: float | None = None,
) -> dict
```

`is_trap` is **not** a parameter — passing it raises `TypeError`. Coverage leaf count: **17** (`lynch_sub, graham_sub, fcf_sub, earny_sub, shy_sub, s_52w_lo, s_52w_hi, s_5y_lo, dcf_sub, def_sub, de_sub, cr_sub, roic_sub, growth_g_sub, growth_stab_sub, piotroski_sub, altman_sub`).

## Sector Applicability Matrix (this session)

```python
def _sector_allows(fund: dict, metric: str) -> bool:
    sector = fund.get("sector") or ""
    if metric == "dcf" and sector in DCF_EXCLUDED_SECTORS: return False
    if metric == "altman" and sector in ALTMAN_EXCLUDED_SECTORS: return False
    if metric in ("earnings_yield", "ev_ebit") and sector == "Financial Services": return False
    return True
```

- Financial Services → `altman_z=None`, DCF=None, `earnings_yield=None`, `ev_ebit=None`; Piotroski still computed.
- Real Estate → DCF=None only; Altman and EV/EBIT/earnings_yield still computed.
- `sector=None`/`""` → no exclusion applied (intentional per RESEARCH.md Pitfall 7).

## `docs/data/stats.json` Schema (produced by `_compute_stats(df)`)

```json
{
  "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
  "universe_count": <int>,
  "buy_signal_count": <int>,
  "low_safety_count": <int>,
  "score_distribution": {"0_20": <int>, "20_40": <int>, "40_60": <int>, "60_80": <int>, "80_100": <int>},
  "pillar_averages": {"value": <float|null>, "quality": <float|null>, "growth": <float|null>, "safety": <float|null>},
  "sector_breakdown": [{"sector": <str>, "count": <int>, "avg_score": <float|null>, "buy_signal_count": <int>}, ...],
  "coverage_stats": {
    "avg_coverage_pct": <float|null>,
    "tickers_with_piotroski": <int>,
    "tickers_with_altman": <int>,
    "tickers_with_dcf": <int>,
    "tickers_with_fcf_yield": <int>
  }
}
```

- **`low_safety_count` threshold:** `score_safety < 30.0` (module constant `LOW_SAFETY_THRESHOLD`, `[ASSUMED]` — no empirical anchor yet).
- `score_distribution` buckets are right-open on the OverallScore axis (`v < 20` → `0_20`, ..., `v >= 80` → `80_100`); bucket counts always sum to `universe_count` for non-null `OverallScore` values.
- `sector_breakdown` groups `None`/`""` sector as `"Unknown"`, sorted by `count` descending.
- `_compute_stats()` gracefully treats any column absent from the input DataFrame as entirely missing (returns 0/null for that metric) rather than raising — this lets the unit tests exercise it with narrow fixtures (only `OverallScore`/`score_safety`/`Sector`/`Show` populated) as well as the full production DataFrame.

## `is_trap` Status: Diagnostic-Only (confirmed)

- Still computed by `trap_gate()` in `process_ticker()`.
- Still emitted as the flat column `row["is_trap"]`.
- Still emitted as `scores.trap` in the nested `write_json()` object (backward compat).
- **Does not** appear in the `overall_score()` signature or influence `score_safety` in any way — it is pure diagnostic metadata per Pitfall 5.

## Decisions Made

- **Threaded `income_stmt_df`/`balance_sheet_df`/`cashflow_df` through `get_combined_data()`** — Wave 1 added these keys to `get_yf_price_and_history()`'s return dict but never propagated them into `get_combined_data()`'s return dict, which is the `fund` dict `process_ticker()` actually consumes. Without this fix, `fund.get("income_stmt_df")` would always be `None` and Piotroski/Altman would never compute for any real ticker. Classified as a Rule 3 (blocking issue) auto-fix.
- **Unified sector gate helper** — extended `_sector_allows()` to cover D-11 (`earnings_yield`/`ev_ebit`) in addition to RESEARCH.md's originally-scoped D-10 (`dcf`/`altman`), rather than leaving D-11 as an untestable inline conditional in `process_ticker()`. This kept the sector-exclusion logic in one place and directly unit-testable without mocking `process_ticker()`'s network calls.
- **`_prev_frame(df) = df.iloc[:, 1:]`** — the wiring pattern for splitting a single raw newest-first multi-year statement DataFrame into the `(curr, prev)` pair `_compute_piotroski()` expects, confirmed against the Wave 1 test fixtures (`inc_prev`'s `columns[0]` value equals `inc_curr`'s `columns[1]` value in every fixture).
- **`.planning/config.json`** — a pre-existing uncommitted line-ending-only change (CRLF normalization, no content diff) was present in the working tree at session start from the interrupted prior session. Verified via `git diff` that it carries zero content changes; left untouched as it is unrelated GSD state bookkeeping, not part of this plan's scope.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `get_combined_data()` did not thread the raw statement DataFrames into `fund`**
- **Found during:** Task 2, before writing the Piotroski/Altman wiring block
- **Issue:** Wave 1 added `income_stmt_df`/`balance_sheet_df`/`cashflow_df` to `get_yf_price_and_history()`'s return dict, but `get_combined_data()` (which merges yfinance + Finnhub data into the `fund` dict `process_ticker()` receives) never copied those three keys through. `fund.get("income_stmt_df")` would always resolve to `None`, making Piotroski/Altman uncomputable for every real ticker despite the Wave 1 helpers being fully functional.
- **Fix:** Added the three keys to `get_combined_data()`'s return dict, sourced from the already-fetched `yf_data` dict.
- **Files modified:** stock_screener.py
- **Verification:** `python -c "import stock_screener"` succeeds; full offline suite green (141 tests).
- **Committed in:** `91b6ebb` (Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for Piotroski/Altman to function on real data — without this fix the feature would silently no-op for every ticker in production while all unit tests still passed (unit tests pass DataFrames directly, bypassing `get_combined_data()`). No scope creep — a direct prerequisite for the plan's stated behavior.

## Issues Encountered

- The interrupted prior session had left a draft addition to `tests/test_distress_phase7.py` (RED-phase `_compute_stats` tests) uncommitted and unregistered in `run_all()`. Reviewed the draft against Task 2's spec — it matched exactly (bucket sums, low_safety_count<30, sector grouping, required keys) — so it was kept, registered in `run_all()`, and extended with `_sector_allows` tests.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `docs/data/stats.json` is now produced by every screener run (once `write_json()` executes) — Wave 3 (`07-03-PLAN.md`) can build `stats.html`/`history.html` against a real, populated schema.
- `is_trap` is confirmed diagnostic-only; Wave 3's `top.html` Safety-chip replacement (removing the TRAP badge) has no scoring-side blockers.
- `.gitignore` still lacks the `!docs/data/stats.json` / `!docs/data/snapshots/*.json` / `!docs/data/snapshots/index.json` exceptions — this is explicitly Wave 3's Task 1 responsibility (confirmed in `07-03-PLAN.md`), not a gap in this plan.
- No blockers for Wave 3.

---
*Phase: 07-distress-signals-dcf-stats-snapshots*
*Completed: 2026-06-30*

## Self-Check: PASSED

- FOUND: stock_screener.py
- FOUND: tests/test_distress_phase7.py
- FOUND: .planning/phases/07-distress-signals-dcf-stats-snapshots/07-02-SUMMARY.md
- FOUND commit: 410344a
- FOUND commit: 91b6ebb
- FOUND commit: c2c57cd
- FOUND commit: 2964df6
