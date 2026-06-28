---
phase: 06-cheap-factors-sector
verified: 2026-06-28T12:10:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 6: Cheap Factors + Sector — Verification Report

**Phase Goal:** Add the GICS sector field to every row and fold the high-evidence cheap factors (52w/5y distance + recency, FCF yield, EV/EBIT + earnings yield, ROIC, shareholder yield) into the 4-pillar composite.
**Verified:** 2026-06-28T12:10:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Each row carries a `Sector` field fetched per ticker (GICS) and threaded through the pipeline | VERIFIED | `stock_screener.py:990` — `t.info.get("sector")` inside guarded try/except; `get_combined_data` returns `"sector": yf_data["sector"]` (line 1161); `process_ticker` emits `row["Sector"] = fund["sector"]` (line 1635) |
| 2 | New price-based signals appear per ticker: dist below 52w high, dist above 52w low, dist above 5y low, weeks-since-52w-low / weeks-since-5y-low recency | VERIFIED | `_compute_price_signals` (line 819) computes all 5 signals from the 5y weekly history fetch (`t.history(period="5y", interval="1wk")`). All 5 emitted as flat columns in `process_ticker` (lines 1641-1645). 33-test suite covers full/short/empty/at-the-low cases — all pass |
| 3 | New fundamental factors appear per ticker: FCF yield, EV/EBIT + earnings yield, ROIC, shareholder yield with low-coverage flag | VERIFIED | Six pure helpers (`_yf_row`, `_compute_price_signals`, `_compute_fcf_yield`, `_compute_ev_ebit`, `_compute_roic`, `_compute_shareholder_yield`) verified at lines 805-942. All 13 new row-dict columns emitted in `process_ticker` (lines 1635-1654). `shareholder_yield_partial` coverage flag always present on row |
| 4 | Each new metric folded into the appropriate pillar via the Phase 5 threshold engine; VALUE has 3 equal sub-groups; ROIC in QUALITY; `all_sub_scores` has 15 leaves; `write_json` emits 3 nested sub-group keys | VERIFIED | `overall_score()` (line 381) has 9 new None-defaulted params, no `ev_ebit` param. VALUE = `_avg_present([discount_group, yield_group, price_group])` (lines 462-496). ROIC→Quality: `score_quality = _avg_present([def_sub, de_sub, cr_sub, roic_sub])` (line 529). `all_sub_scores` list has exactly 15 entries (lines 576-583). `write_json` emits `value_discount`, `value_yield`, `value_price` nested keys (lines 1706-1708). `test_coverage_grows_to_15` passes confirming 15/15 = 100% |

**Score:** 4/4 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `stock_screener.py` | Modified: sector + price signals + factor helpers + scoring fold | VERIFIED | 1750 lines; all 6 pure helpers present; all 13 new `process_ticker` columns emitted; `overall_score()` extended with 9 new params; `write_json` emits 3 nested sub-group keys |
| `diagnose_finnhub.py` | 8 `[VERIFY]` field names added to `fields_of_interest` | VERIFIED | Lines 61-68: `evToEbit`, `ebitAnnual`, `enterpriseValue`, `roiAnnual`, `dividendYieldAnnual`, `sharesBuybackRatioAnnual`, `totalDebtAnnual`, `cashAnnual` — all present under `# Phase 6 [VERIFY]` comment |
| `tests/test_factors_phase6.py` | Created: 33 offline vanilla-assert tests for the 6 pure helpers | VERIFIED | File exists; 33 tests registered in `run_all()`; env vars set before import; no network calls |
| `tests/test_scoring_phase6.py` | Created: 11 offline tests for the scoring layer extensions | VERIFIED | File exists; 11 tests registered in `run_all()`; env vars set before import |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `get_yf_price_and_history` | `_compute_price_signals` | `hist["Close"]`, `price` | WIRED | Line 1018: `signals = _compute_price_signals(hist["Close"], price)` |
| `get_yf_price_and_history` | `t.info.get("sector")` | guarded try/except | WIRED | Lines 989-992: separate guard so `.info` raise on delisted tickers doesn't abort the fetch |
| `get_combined_data` | `_compute_fcf_yield` | `ocf`, `capex`, `mkt_cap_b * 1e9` | WIRED | Lines 1110-1115 (visible in context around line 1140 return) |
| `get_combined_data` | `_compute_ev_ebit` | `ebit`, `total_debt`, `cash`, `market_cap` | WIRED | Called before the return dict; result stored as `ev_ebit`, `earnings_yield` |
| `get_combined_data` | `_compute_roic` | `ebit`, `total_debt`, `equity`, `cash` | WIRED | Result stored as `roic` in return dict (line 1172) |
| `get_combined_data` | `_compute_shareholder_yield` | `div_yield_pct`, `shares_now`, `shares_prev` | WIRED | Lines 1141-1145 |
| `process_ticker` → `overall_score` | 9 new Phase-6 params | keyword args | WIRED | Lines 1610-1618: `fcf_yield`, `earnings_yield`, `shareholder_yield`, `roic`, `dist_52w_low`, `dist_52w_high`, `dist_5y_low`, `weeks_since_52w_low`, `weeks_since_5y_low` all passed |
| `overall_score` return | `process_ticker` flat columns | `scores["value_discount"]` etc. | WIRED | Lines 1624-1626: `row["score_value_discount"]`, `row["score_value_yield"]`, `row["score_value_price"]` |
| `process_ticker` flat columns | `write_json` nested scores | `row.get("score_value_*")` | WIRED | Lines 1706-1708: `value_discount`, `value_yield`, `value_price` in `scores` object |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `overall_score()` — VALUE yield sub-group | `fcf_sub`, `earny_sub`, `shy_sub` | `_compute_fcf_yield`, `_compute_ev_ebit`, `_compute_shareholder_yield` via `get_combined_data` → yfinance cashflow/income/balance_sheet | Real computation with `_yf_row` label scan; None when data absent (average-over-present contract) | FLOWING |
| `overall_score()` — VALUE price-position sub-group | `s_52w_lo`, `s_52w_hi`, `s_5y_lo` | `_compute_price_signals` via `t.history(period="5y", interval="1wk")` | Real 5y weekly close series; short_history flag when bars < 52 | FLOWING |
| `overall_score()` — QUALITY ROIC | `roic_sub` | `_compute_roic` via yfinance balance_sheet + income_stmt | Real NOPAT/invested computation; None when invested ≤ 0 | FLOWING |
| `process_ticker` row dict | `Sector` | `t.info.get("sector")` | Real yfinance GICS-like string; None on delisted | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 33 factor helper tests pass offline | `python tests/test_factors_phase6.py` | 33 passed, 0 failed | PASS |
| 11 scoring layer tests pass offline | `python tests/test_scoring_phase6.py` | 11 passed, 0 failed | PASS |
| Prior 33 scoring tests pass (regression) | `python tests/test_scoring.py` | 33 passed, 0 failed | PASS |
| Prior 12 growth/trap tests pass (regression) | `python tests/test_growth_trap_fixes.py` | 12 passed, 0 failed | PASS |
| `ev_ebit` NOT a param of `overall_score` | `grep "ev_ebit" overall_score signature` | No match — EV/EBIT is diagnostic-only per D-05 decision | PASS |
| `SCORE_EV_EBIT_BANDS` constant does NOT exist | `grep "SCORE_EV_EBIT"` | No match — earnings_yield (EBIT/EV) is scored instead | PASS |
| `all_sub_scores` has 15 entries | `test_coverage_grows_to_15` asserts `coverage_pct == 100.0` | PASS — confirmed by test | PASS |
| 3 nested sub-group keys in `write_json` | `grep "value_discount\|value_yield\|value_price" write_json` | Lines 1706-1708 — all 3 keys present | PASS |

---

### Probe Execution

Step 7c: SKIPPED — no conventional `scripts/*/tests/probe-*.sh` probes exist for this phase. The offline test suites serve as the phase's executable verification (run above).

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SECTOR-01 | 06-01-PLAN | GICS sector per ticker as row field | SATISFIED | `row["Sector"] = fund["sector"]` at line 1635; `t.info.get("sector")` at line 990 |
| SIGNAL-01 | 06-01-PLAN | Distance below 52w high / above 52w low (%) | SATISFIED | `Dist_52w_High_Pct`, `Dist_52w_Low_Pct` emitted at lines 1641-1642; `_compute_price_signals` computes both |
| SIGNAL-02 | 06-01-PLAN | Distance above 5-year low (%) | SATISFIED | `Dist_5y_Low_Pct` emitted at line 1643 |
| SIGNAL-03 | 06-01-PLAN | Weeks-since-52w-low / weeks-since-5y-low recency | SATISFIED | `Weeks_Since_52w_Low`, `Weeks_Since_5y_Low` emitted at lines 1644-1645; used as `_recency_multiplier` inputs in scoring |
| SIGNAL-04 | 06-01-PLAN | FCF yield (FCF / market cap) | SATISFIED | `FCF_Yield_Pct` emitted at line 1649; yfinance cashflow fallback per D-01; folded into VALUE yield sub-group |
| SIGNAL-05 | 06-01-PLAN | EV/EBIT (Acquirer's Multiple) + earnings yield (EBIT/EV) | SATISFIED | `EV_EBIT` diagnostic at line 1650; `Earnings_Yield_Pct` scored at line 1651; `earny_sub` in yield_group; no `SCORE_EV_EBIT_BANDS` (per D-05 plan-checker resolution) |
| SIGNAL-06 | 06-01-PLAN | ROIC as absolute Quality input (not Greenblatt rank-sum) | SATISFIED | `ROIC_Pct` emitted at line 1652; `roic_sub` in `score_quality = _avg_present([def_sub, de_sub, cr_sub, roic_sub])` at line 529 |
| SIGNAL-07 | 06-01-PLAN | Shareholder yield (dividend + net buyback) + low-coverage flag | SATISFIED | `Shareholder_Yield_Pct` + `shareholder_yield_partial` emitted at lines 1653-1654; `sh_partial` flag always on row |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `stock_screener.py` | 190, 201, 212, 226, 237, 249, 259, 260, 266 | `[ASSUMED]` comments on SCORE_* band constants | INFO | Intentional — these are tunable config constants explicitly marked as starting values, pending Phase 7 `stats.html` calibration. Not a debt marker (no TBD/FIXME/XXX); documented design pattern from Phase 5. |
| `diagnose_finnhub.py` | 41 in 06-01-SUMMARY | `[VERIFY]` tag on Finnhub field names | INFO | Intentional staging pattern — field names added to `fields_of_interest` so the next live Actions run prints their presence/absence. No offline verification possible without API keys. Live coverage confirmation is deferred to next GitHub Actions run. |

No `TBD`, `FIXME`, or `XXX` markers found in any of the four files touched by this phase.

---

### Human Verification Required

None. All must-haves are verifiable from the codebase.

The one deferred item (live Finnhub field coverage confirmation) does not block phase completion — it was explicitly deferred by decision D-01/D-41 to the next Actions run, and the `diagnose_finnhub.py` staging mechanism is in place.

---

### Gaps Summary

No gaps. All 4 roadmap success criteria verified at all four levels (exists, substantive, wired, data flowing). All 89 tests pass (33 + 11 + 33 + 12). No debt markers. Requirements SECTOR-01 and SIGNAL-01 through SIGNAL-07 all have codebase evidence.

---

_Verified: 2026-06-28T12:10:00Z_
_Verifier: Claude (gsd-verifier)_
