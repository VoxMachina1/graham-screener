---
phase: 06-cheap-factors-sector
plan: "01"
subsystem: data-pipeline
tags: [yfinance, factors, sector, price-signals, fcf, ev-ebit, roic, shareholder-yield]
requires: []
provides:
  - _yf_row (pure helper)
  - _compute_price_signals (pure helper)
  - _compute_fcf_yield (pure helper)
  - _compute_ev_ebit (pure helper)
  - _compute_roic (pure helper)
  - _compute_shareholder_yield (pure helper)
  - Sector field on every row dict
  - Dist_52w_High_Pct, Dist_52w_Low_Pct, Dist_5y_Low_Pct, Weeks_Since_52w_Low, Weeks_Since_5y_Low
  - short_history coverage flag
  - FCF_Yield_Pct, EV_EBIT, Earnings_Yield_Pct, ROIC_Pct, Shareholder_Yield_Pct
  - shareholder_yield_partial coverage flag
affects:
  - stock_screener.py (get_yf_price_and_history, get_combined_data, process_ticker)
  - diagnose_finnhub.py (fields_of_interest list)
  - tests/test_factors_phase6.py (new)
tech-stack:
  added: []
  patterns:
    - "yfinance candidate-label lists (OCF/CAPEX/EBIT/DEBT/CASH/EQUITY/SHARES_LABELS)"
    - "ONE reused yf.Ticker per ticker for all fetches (D-03/D-05)"
    - "vanilla-assert offline test pattern mirroring test_growth_trap_fixes.py"
key-files:
  created:
    - tests/test_factors_phase6.py
  modified:
    - stock_screener.py
    - diagnose_finnhub.py
decisions:
  - "FCF sourced from yfinance cashflow (OCF + negative capex), not Finnhub (confirmed absent free tier, D-01)"
  - "ONE yf.Ticker per ticker reused for .info, .history, .cashflow, .income_stmt, .balance_sheet (D-03)"
  - "EBIT read from t.income_stmt (newest-first, not re-sorted local inc) to preserve column[0]=newest contract"
  - "invested<=0 in ROIC → None (data anomaly, not worst-score per Slice A §3d)"
  - "shareholder_yield_partial=True when shares data absent (div-only fallback); always present on row"
  - "[VERIFY] Finnhub field names staged in diagnose_finnhub.py; live coverage deferred to next Actions run"
metrics:
  duration: "6 minutes"
  completed: "2026-06-22"
  tasks_completed: 3
  files_changed: 3
---

# Phase 06 Plan 01: DATA Layer — Sector + Price Signals + 4 Fundamental Factors Summary

**One-liner:** yfinance sector, 5y-weekly distance/recency signals, and FCF/EV-EBIT/ROIC/shareholder-yield added as additive row-dict fields with per-field coverage handling via six testable pure helpers.

---

## What Was Built

### Pure helpers added to stock_screener.py

All helpers are marked "internal — for tests only" per CLAUDE.md §B. No new public surface.

| Helper | Purpose |
|---|---|
| `_yf_row(df, labels)` | First-matching label scan; newest column (index 0) value |
| `_compute_price_signals(closes, price)` | 5 distance/recency signals + short_history from a Close Series |
| `_compute_fcf_yield(ocf, capex, market_cap)` | FCF = OCF + capex (capex negative) / market_cap * 100 |
| `_compute_ev_ebit(ebit, total_debt, cash, market_cap)` | Returns (ev_ebit, earnings_yield) tuple |
| `_compute_roic(ebit, total_debt, equity, cash)` | NOPAT / invested * 100; invested<=0 → None |
| `_compute_shareholder_yield(div_yield, shares_now, shares_prev)` | Returns (yield, partial_flag) |

### Module-level candidate label lists added

`OCF_LABELS`, `CAPEX_LABELS`, `EBIT_LABELS`, `TOTAL_DEBT_LABELS`, `CURRENT_DEBT_LABELS`, `CASH_LABELS`, `EQUITY_LABELS`, `SHARES_LABELS` — mirrors the existing label-scan pattern at stock_screener.py:608.

### get_yf_price_and_history extended

Reuses the SAME `t = yf.Ticker(ticker)` (D-03/D-05) for:
- `t.info.get("sector")` — guarded separately (`.info` can raise independently)
- `t.history(period="5y", interval="1wk")` → passed to `_compute_price_signals`
- `t.cashflow` → OCF + capex via `_yf_row`
- `t.income_stmt` → EBIT via `_yf_row` (newest-first, un-re-sorted)
- `t.balance_sheet` → total_debt (long+current), cash, equity, shares_now/prev

### get_combined_data extended

Calls the pure helpers with raw components from `yf_data`, using `mkt_cap_b * 1e9` as the market cap denominator. The existing `fcf_per_share` Finnhub field path is untouched (still feeds the Plan 02 trap gate sign).

### process_ticker extended

Emits 13 new additive flat columns (exact key names for Plan 06-02 to consume):

| Row-dict key | Type | Notes |
|---|---|---|
| `Sector` | str \| None | yfinance `.info['sector']` (GICS-like) |
| `Dist_52w_High_Pct` | float \| None | % below 52-week high; clamped ≥ 0 |
| `Dist_52w_Low_Pct` | float \| None | % above 52-week low; clamped ≥ 0 |
| `Dist_5y_Low_Pct` | float \| None | % above 5-year low; clamped ≥ 0 |
| `Weeks_Since_52w_Low` | float \| None | Bars since 52-week low |
| `Weeks_Since_5y_Low` | float \| None | Bars since 5-year low |
| `short_history` | bool | True when 8 ≤ weekly bars < 52 |
| `FCF_Yield_Pct` | float \| None | FCF/market_cap*100; may be negative |
| `EV_EBIT` | float \| None | EV/EBIT multiple (diagnostic) |
| `Earnings_Yield_Pct` | float \| None | EBIT/EV*100; None if EBIT≤0 or EV≤0 |
| `ROIC_Pct` | float \| None | NOPAT/invested*100; None if invested≤0 |
| `Shareholder_Yield_Pct` | float \| None | div + buyback yield; may be negative (dilution) |
| `shareholder_yield_partial` | bool | True when buyback component absent (div-only) |

All floats rounded to 2dp via a local `_r2()` helper; None stays None.

### diagnose_finnhub.py extended

Added 8 `[VERIFY]` field names to `fields_of_interest`:
`evToEbit`, `ebitAnnual`, `enterpriseValue`, `roiAnnual`, `dividendYieldAnnual`, `sharesBuybackRatioAnnual`, `totalDebtAnnual`, `cashAnnual`.
Request logic, ticker list, and statement-dump sections are unchanged.

**Live coverage confirmation is deferred to the next GitHub Actions run.** The executor has no API keys and cannot run `diagnose_finnhub.py` offline. The field names are staged so the next live run prints their presence/absence per ticker (the confirmed absent FCF fields were already in the list from Phase 5).

### Offline tests (tests/test_factors_phase6.py)

33 vanilla-assert tests, no network calls, no pytest. Pattern mirrors `test_growth_trap_fixes.py` exactly (env vars set before import, `_REPO_ROOT` sys.path insert, `run_all()` with PASS/FAIL + sys.exit(1)). Coverage:

- `_compute_fcf_yield`: 6 cases (positive, negative, OCF-only, None when ocf/mktcap None/zero)
- `_compute_ev_ebit`: 6 cases (happy path, ebit≤0, ev≤0, mktcap None, debt/cash default to 0)
- `_compute_roic`: 6 cases (happy path, invested≤0, negative EBIT, missing components, cash defaults)
- `_compute_shareholder_yield`: 5 cases (div-only partial, div+buyback, dilution negative, both None, zero div)
- `_compute_price_signals`: 5 cases (n≥52 full, 8≤n<52 short, n<8 all None, empty series, at-the-low)
- `_yf_row`: 5 cases (first label match, second label fallback, no match, empty df, None df)

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Floating-point equality in test_fcf_yield_positive**

- **Found during:** Task 1 verification run
- **Issue:** `100 + (-30) = 70` followed by `70/1000*100` produces `7.000000000000001` due to float arithmetic, causing `assert result == 7.0` to fail
- **Fix:** Changed to `assert abs(result - 7.0) < 1e-9` (consistent with the other numeric tests in the same file)
- **Files modified:** `tests/test_factors_phase6.py`
- **Commit:** `abdc56b` (same task commit; fix applied before the task commit)

No other deviations. All three tasks executed exactly as planned.

---

## yfinance Fallback Formulas Used

| Factor | Formula | Fallback path |
|---|---|---|
| FCF | `OCF + capex` (capex negative in yf) | capex absent → OCF proxy; both absent → None |
| EV | `market_cap + total_debt - cash` | total_debt/cash default to 0 when None |
| EBIT | `_yf_row(income_stmt, EBIT_LABELS)` | First matching label from 4-item list |
| ROIC | `EBIT*(1-0.21) / (total_debt + equity - cash) * 100` | None if invested≤0 |
| Shareholder yield | `div_yield + (shares_prev-shares_now)/shares_prev*100` | div-only when shares absent |

---

## Stub Tracking

No stubs. All new fields have real computation paths; None is a first-class coverage value (not a placeholder) flowing through the average-over-present contract from Plan 06-02.

---

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. The new `t.info`, `t.history`, `t.cashflow`, `t.balance_sheet` calls are all within the existing yfinance HTTP pattern, covered by T-06-02 (accepted latency) and the existing try/except fail-safe contract. Output to the public `results.json` is market-data-only (T-06-03 accepted).

---

## Self-Check: PASSED

Files exist:
- `stock_screener.py` — modified
- `diagnose_finnhub.py` — modified
- `tests/test_factors_phase6.py` — created

Commits verified:
- `abdc56b` — Task 1: pure helpers + tests
- `d043aeb` — Task 2: fetch wiring + process_ticker columns
- `a9e6a05` — Task 3: diagnose_finnhub.py [VERIFY] fields

All test suites pass (78 total: 33 new + 33 scoring + 12 growth_trap).
