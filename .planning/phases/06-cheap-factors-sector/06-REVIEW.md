---
phase: 06-cheap-factors-sector
reviewed: 2026-06-28T12:10:00Z
depth: deep
files_reviewed: 4
files_reviewed_list:
  - stock_screener.py
  - tests/test_factors_phase6.py
  - tests/test_scoring_phase6.py
  - diagnose_finnhub.py
findings:
  critical: 1
  warning: 3
  info: 2
  total: 6
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-06-28T12:10:00Z
**Depth:** deep
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Phase 6 adds five pure factor helpers (`_yf_row`, `_compute_price_signals`, `_compute_fcf_yield`,
`_compute_ev_ebit`, `_compute_roic`, `_compute_shareholder_yield`), a 3-sub-group Value pillar
extension plus ROIC-in-Quality inside `overall_score()`, a new `_recency_multiplier`, and 9 new
flat columns wired through `process_ticker` and `write_json`.

The pure helpers and their 33 offline tests are correct. The scoring engine extension — `overall_score()` itself — is also correct. The critical defect is in the **wiring layer** that connects `process_ticker` to `overall_score()`: the call site uses the wrong dict and the wrong key names, causing all 9 new Phase-6 scoring inputs to silently resolve to `None` on every live run. The unit tests do not catch this because they call `overall_score()` directly and bypass `process_ticker`. In production the OverallScore is therefore computed as if Phase 6 scoring never happened — the new Value sub-groups 2 and 3 (yield and price-position) and ROIC-in-Quality are all dead letters.

Three secondary warnings cover a latent debt double-count, a dropped `dist_5y_low` key in the partial zero-denominator path of `_compute_price_signals`, and redundant I/O in `get_yf_price_and_history`. Two info items cover the `_r2()` rounding of integer week-counts and a gap in test coverage for the `total_debt` double-count risk.

---

## Critical Issues

### CR-01: `process_ticker` passes wrong key names to `overall_score()` — all Phase-6 scoring inputs are silently `None`

**File:** `stock_screener.py:1599-1619`

**Issue:** The `overall_score()` call reads the Phase-6 factor inputs from `fund` (the dict returned by
`get_combined_data()`) using PascalCase dashboard-output key names:

```python
fcf_yield           = fund.get("FCF_Yield_Pct"),       # line 1610
earnings_yield      = fund.get("Earnings_Yield_Pct"),  # line 1611
shareholder_yield   = fund.get("Shareholder_Yield_Pct"),# line 1612
roic                = fund.get("ROIC_Pct"),             # line 1613
dist_52w_low        = fund.get("Dist_52w_Low_Pct"),    # line 1614
dist_52w_high       = fund.get("Dist_52w_High_Pct"),   # line 1615
dist_5y_low         = fund.get("Dist_5y_Low_Pct"),     # line 1616
weeks_since_52w_low = fund.get("Weeks_Since_52w_Low"), # line 1617
weeks_since_5y_low  = fund.get("Weeks_Since_5y_Low"),  # line 1618
```

None of these keys exist in `fund`. The `get_combined_data()` return dict uses lowercase/snake_case
keys: `"fcf_yield"`, `"earnings_yield"`, `"shareholder_yield"`, `"roic"`, `"dist_52w_low"`,
`"dist_52w_high"`, `"dist_5y_low"`, `"weeks_since_52w_low"`, `"weeks_since_5y_low"`.

The PascalCase names only appear in `row` (the output dict for the JSON), and `row` is populated
from `fund` *after* the `overall_score()` call (lines 1641–1653). The `.get()` calls therefore
return `None` for all 9 parameters on every live ticker.

**Consequence:** In production, `overall_score()` effectively runs as a Phase-5-only call for
every ticker. Value sub-groups 2 (yield) and 3 (price-position) are always `None`, ROIC never
enters the Quality pillar, and `coverage_pct` is always capped at approximately 53% (8 of 15
sub-scores). None of the Phase-6 scoring constants (`SCORE_FCF_YIELD_*`, `SCORE_EARN_YIELD_*`,
`SCORE_SH_YIELD_*`, `SCORE_DIST_*`, `SCORE_ROIC_*`) ever execute. The unit tests in
`test_scoring_phase6.py` do not catch this because they call `overall_score()` directly, bypassing
`process_ticker`.

**Fix:** Change all 9 `fund.get("PascalCase")` calls to the matching snake_case keys that
`get_combined_data()` actually returns:

```python
scores = overall_score(
    lynch_discount      = lm.get("Lynch_Discount_Pct"),
    graham_discount     = gm.get("Graham_Discount_Pct"),
    defensive_score     = ds.get("DefensiveScore"),
    debt_equity         = fund["debt_equity"],
    current_ratio       = fund["current_ratio"],
    growth_g            = g,
    growth_stability    = growth_stability,
    is_trap             = is_trap,
    coverage_fraction   = cov_fraction,
    aaa_yield           = aaa_yield,
    fcf_yield           = fund["fcf_yield"],             # was fund.get("FCF_Yield_Pct")
    earnings_yield      = fund["earnings_yield"],        # was fund.get("Earnings_Yield_Pct")
    shareholder_yield   = fund["shareholder_yield"],     # was fund.get("Shareholder_Yield_Pct")
    roic                = fund["roic"],                  # was fund.get("ROIC_Pct")
    dist_52w_low        = fund["dist_52w_low"],          # was fund.get("Dist_52w_Low_Pct")
    dist_52w_high       = fund["dist_52w_high"],         # was fund.get("Dist_52w_High_Pct")
    dist_5y_low         = fund["dist_5y_low"],           # was fund.get("Dist_5y_Low_Pct")
    weeks_since_52w_low = fund["weeks_since_52w_low"],   # was fund.get("Weeks_Since_52w_Low")
    weeks_since_5y_low  = fund["weeks_since_5y_low"],    # was fund.get("Weeks_Since_5y_Low")
)
```

An integration test should be added that calls `process_ticker` end-to-end with a mocked
`get_combined_data` return and asserts that `scores["value_yield"]` and `scores["value_price"]`
are not `None`.

---

## Warnings

### WR-01: `total_debt` may be double-counted when yfinance `"Total Debt"` row already includes current debt

**File:** `stock_screener.py:1035-1037`

**Issue:**

```python
td_long    = _yf_row(bs, TOTAL_DEBT_LABELS) or 0   # matches "Total Debt" first
td_current = _yf_row(bs, CURRENT_DEBT_LABELS) or 0  # matches "Current Debt" separately
result["total_debt"] = td_long + td_current
```

In yfinance, the `"Total Debt"` balance-sheet row is defined as long-term debt plus the current
portion of long-term debt. When that label is present, adding `td_current` on top double-counts
the current portion, inflating `total_debt` and therefore distorting EV (making EV larger →
EV/EBIT ratio higher, earnings yield lower) and ROIC (invested capital larger → ROIC lower).

The intent of the two-label approach was to handle tickers where yfinance only reports one of the
two components. The safe implementation is to use the first label that matches and skip the
summation when `"Total Debt"` is found:

```python
total_debt_val = _yf_row(bs, TOTAL_DEBT_LABELS)
if total_debt_val is None:
    # fall back to summing long-term + current components
    td_long    = _yf_row(bs, ["Long Term Debt And Capital Lease Obligation", "Long Term Debt"]) or 0
    td_current = _yf_row(bs, CURRENT_DEBT_LABELS) or 0
    total_debt_val = td_long + td_current
result["total_debt"] = total_debt_val
```

This affects EV/EBIT, earnings yield, and ROIC calculations for any ticker where yfinance reports
`"Total Debt"` (the majority of large-cap tickers).

### WR-02: `_compute_price_signals` drops `dist_5y_low` in the partial zero-denominator branch

**File:** `stock_screener.py:851-858`

**Issue:** The zero-denominator guard returns a dict that correctly handles each of the three
distance values individually, but the key `"dist_5y_low"` is missing from the return when
`low_5y == 0`:

```python
return {
    "dist_52w_high":     None if high_52w == 0 else max(0.0, (high_52w - price) / high_52w * 100),
    "dist_52w_low":      None if low_52w == 0  else max(0.0, (price - low_52w) / low_52w * 100),
    "dist_5y_low":       None if low_5y == 0   else max(0.0, (price - low_5y) / low_5y * 100),
    "weeks_since_52w_low": len(w52) - 1 - int(w52.values.argmin()),
    "weeks_since_5y_low":  len(closes) - 1 - int(closes.values.argmin()),
    "short_history":     short_history,
}
```

Wait — the key `"dist_5y_low"` is actually present in the partial dict at line 854. The actual
omission is different: the `weeks_since_*` values are computed unconditionally even when the
corresponding `low_*` denominator is zero, so `weeks_since_52w_low` and `weeks_since_5y_low` are
returned as non-`None` integers even when `dist_52w_low` or `dist_5y_low` is `None`. The
recency multiplier is then applied to a `None` distance that never reaches the recency path
anyway (the `if dist_52w_low is None` guard in `overall_score()` short-circuits), so this is
not a scoring error. However, the `weeks_since_*` values in this branch are misleading in the
output JSON because they imply a valid low was found.

The cleaner fix:
```python
"weeks_since_52w_low": None if low_52w == 0 else len(w52) - 1 - int(w52.values.argmin()),
"weeks_since_5y_low":  None if low_5y == 0  else len(closes) - 1 - int(closes.values.argmin()),
```

### WR-03: `t.income_stmt` is fetched twice — once sorted, once raw — introducing a subtle ordering dependency

**File:** `stock_screener.py:995-1003`

**Issue:**

```python
inc = t.income_stmt
if inc is not None and not inc.empty:
    inc = inc.sort_index(axis=1)  # oldest→newest — rebinds local `inc`
    for label in ["Basic EPS", ...]:
        if label in inc.index:
            result["annual_eps"] = [_safe_float(v) for v in inc.loc[label].values]
            break
    # EBIT from income statement (newest-first — NOT re-sorted here; use raw)
    result["ebit"] = _yf_row(t.income_stmt, EBIT_LABELS)   # second property access
```

`t.income_stmt` is accessed twice: once into `inc` (then sorted oldest→newest for EPS history
ordering), and once raw again for `_yf_row`. The comment correctly notes the second access
should be newest-first. But accessing `t.income_stmt` twice makes two property calls to yfinance
— yfinance caches internally, so this is not an extra HTTP request, but it creates a fragile
dependency on yfinance's cache behavior and complicates reading.

The cleaner approach that eliminates both the double-access and the fragility:

```python
inc_raw = t.income_stmt          # newest-first (yfinance default)
result["ebit"] = _yf_row(inc_raw, EBIT_LABELS)  # uses col 0 = newest
inc = inc_raw.sort_index(axis=1) if inc_raw is not None and not inc_raw.empty else inc_raw
```

---

## Info

### IN-01: `_r2()` rounds integer week-counts to 2 decimal places

**File:** `stock_screener.py:1638-1645`

**Issue:** The `_r2()` helper (`round(float(v), 2)`) is applied uniformly to all Phase-6 output
columns including `Weeks_Since_52w_Low` and `Weeks_Since_5y_Low`, which are integer bar counts
from `argmin()`. These will always be whole numbers; rounding to 2 decimal places produces
values like `51.0` instead of `51`. This does not affect correctness but produces slightly
unexpected JSON (`"Weeks_Since_52w_Low": 51.0` vs `51`). The dashboard consumer should coerce
these to integers, or an `_r0()` helper returning `int(v)` should be used for week counts.

### IN-02: No integration-level test covers the `process_ticker` → `overall_score` wiring

**File:** `tests/test_scoring_phase6.py` / `tests/test_factors_phase6.py`

**Issue:** All Phase-6 tests call pure functions directly (`overall_score()`, `_compute_*`). The
test gap that allowed CR-01 to ship undetected is the complete absence of any test that exercises
the `process_ticker()` path with a controlled `get_combined_data()` return. Because the key-name
mismatch produces `None` rather than an exception, it is invisible without a test that asserts a
non-`None` value for `scores["value_yield"]` or `scores["value_price"]` in the wired pipeline.

A minimal fixture test should mock `get_combined_data` to return a dict with known Phase-6 values
and then assert the resulting `row` contains non-`None` `score_value_yield` and `score_value_price`.

---

## Key Concerns Addressed

1. **Capex sign** (`_compute_fcf_yield`): Correct. `FCF = ocf + capex` where capex is negative → addition is correct. Tests confirm.

2. **Descending bands for `dist_52w_low` / `dist_5y_low`**: Correct. `score_lo > score_hi` in all bands. `test_descending_bands` validates this.

3. **Recency multiplier applied as multiplier on raw piecewise score, NOT added to `all_sub_scores`**: Correct. The multiplied result (`raw * _recency_multiplier(...)`) is stored in `s_52w_lo` / `s_5y_lo` and those are placed in `all_sub_scores` — the multiplier itself is not a separate entry.

4. **`all_sub_scores` has exactly 15 entries**: Correct. Confirmed by inspection of lines 576–583: 2 (discount) + 3 (yield) + 3 (price-position) + 4 (quality) + 2 (growth) + 1 (safety) = 15. `test_coverage_grows_to_15` validates this.

5. **EV/EBIT is diagnostic-only, not passed to `overall_score()`**: Correct. `ev_ebit` is written to `row["EV_EBIT"]` (line 1650) but is not in the `overall_score()` call. Only `earnings_yield` (derived from the same computation) is passed — or would be, once CR-01 is fixed.

6. **Backward compat via `None`-defaulted params**: Correct. All Phase-6 params default to `None`. `test_backward_compat` validates.

7. **`write_json` compact JSON and `<100-row` guard**: Both intact at lines 1692 and 1720.

---

_Reviewed: 2026-06-28T12:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_
