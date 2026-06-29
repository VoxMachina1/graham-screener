---
phase: "07-distress-signals-dcf-stats-snapshots"
plan: "01"
subsystem: "data-layer"
tags: [piotroski, altman-z, dcf, scipy, yfinance, pure-helpers]
dependency_graph:
  requires:
    - "06-02-SUMMARY.md (overall_score signature, 15-leaf count, _compute_* pattern)"
    - "requirements.txt (scipy>=1.10 added)"
  provides:
    - "_compute_piotroski (0-9 F-Score pure helper)"
    - "_compute_altman_z (Z'' pure helper)"
    - "_compute_dcf_forward (intrinsic + discount% tuple)"
    - "_compute_dcf_reverse (implied growth via brentq)"
    - "_yf_row_prev (prior-year label reader)"
    - "_dcf_wacc (WACC decimal)"
    - "income_stmt_df / balance_sheet_df / cashflow_df keys on get_yf_price_and_history()"
  affects:
    - "07-02-PLAN.md (Wave 2 wires these helpers into overall_score / process_ticker)"
tech_stack:
  added:
    - "scipy>=1.10 (brentq bounded solver for reverse DCF)"
  patterns:
    - "_compute_* pure-helper pattern (no I/O, float|None return, 'internal — for tests only.' docstring)"
    - "two-year statement read via _yf_row_prev (df.columns[1] with df.shape[1]<2 guard)"
    - "[ASSUMED] config constants for all band thresholds"
key_files:
  created:
    - "tests/test_distress_phase7.py"
    - "tests/test_dcf_phase7.py"
  modified:
    - "stock_screener.py (scipy import, 9 label lists, config constants, 6 helpers, 3 get_yf_price_and_history keys)"
    - "requirements.txt (scipy>=1.10)"
decisions:
  - "All band thresholds tagged [ASSUMED] — no empirical anchor; calibrate after stats.html shows live distribution (Phase 7 plan 03)"
  - "_compute_piotroski absent prior-year DataFrames skip (not fail) comparison criteria per RESEARCH.md §absent-data"
  - "_compute_altman_z returns negative Z'' for negative-equity firms (not clamped); SCORE_ALTMAN_BANDS starts at -999.0"
  - "Reverse DCF bracket guard: no sign change in [-50,100] -> (None, False) per D-09; never a numeric default"
  - "DCF_TERMINAL_GROWTH_CAP=3.0%, DCF_ERP=5.5% as [ASSUMED] config constants"
  - "overall_score() and process_ticker() are UNCHANGED — Wave 2 wires the helpers in"
metrics:
  duration: "~45 minutes"
  completed: "2026-06-29"
  tasks: 3
  files_modified: 4
  tests_added: 32
---

# Phase 07 Plan 01: Distress Signals + DCF Data Layer Summary

**One-liner:** Six pure numeric helpers (Piotroski F-Score, Altman Z'', forward DCF, reverse DCF via scipy brentq, _yf_row_prev, _dcf_wacc) with nine new label lists, complete DCF/Altman/Piotroski SCORE_* config constants, raw DataFrame threading through get_yf_price_and_history(), and two new offline test files — all additive; overall_score() untouched.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | scipy dep, 9 label lists, DCF/Altman/Piotroski config, _yf_row_prev + _dcf_wacc | e106f5a | requirements.txt, stock_screener.py, tests/test_distress_phase7.py |
| 2 | _compute_piotroski + _compute_altman_z + raw DataFrame keys on get_yf_price_and_history() | 3de99e6 | stock_screener.py, tests/test_distress_phase7.py |
| 3 | _compute_dcf_forward + _compute_dcf_reverse + brentq import | dba7cc1 | stock_screener.py, tests/test_dcf_phase7.py |

## Final Helper Signatures

```python
def _yf_row_prev(df, labels) -> float | None:
    """Prior-year (columns[1]) reader; None when df.shape[1] < 2 or no label match."""

def _dcf_wacc(aaa_yield_pct: float) -> float:
    """Returns (aaa_yield_pct + DCF_ERP) / 100.0  (DCF_ERP=5.5 default)."""

def _compute_piotroski(
    inc_curr, inc_prev,    # income_stmt DataFrames (curr year, prior year)
    bs_curr, bs_prev,      # balance_sheet DataFrames
    cf_curr, cf_prev,      # cashflow DataFrames
) -> int | None:
    """9-criterion Piotroski F-Score. None when all curr statements absent."""

def _compute_altman_z(bs_curr, inc_curr) -> float | None:
    """Z'' = 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4. None on missing inputs or zero denominators."""

def _compute_dcf_forward(
    eps, g_cagr_pct: float, aaa_yield_pct: float, price: float
) -> tuple:
    """Returns (intrinsic_value, discount_pct) or (None, None) when eps<=0/None.
    Raises ValueError when terminal_growth >= WACC (config diagnostic)."""

def _compute_dcf_reverse(
    price: float, eps, aaa_yield_pct: float, g_stage1_pct: float
) -> tuple:
    """Returns (implied_growth_pct, True) or (None, False). Never a silent default."""
```

## DCF Discount Sign Convention

`discount_pct = (1 - price / intrinsic) * 100`

- **Positive** = price below intrinsic = cheap signal
- **Negative** = price above intrinsic = overpriced signal
- Consistent with Lynch/Graham discount convention throughout the codebase

## Final Config Constants

### Piotroski F-Score Bands [ASSUMED]

```python
SCORE_PIOTROSKI_BANDS = [
    (0, 2,   0,  20),   # distressed
    (2, 4,  20,  40),   # weak
    (4, 6,  40,  65),   # average
    (6, 8,  65,  85),   # strong
    (8, 9,  85, 100),   # very strong
]
```

### Altman Z'' Bands [ASSUMED]

```python
SCORE_ALTMAN_DISTRESS = 1.1   # below = distress zone
SCORE_ALTMAN_SAFE     = 2.6   # above = safe zone
SCORE_ALTMAN_BANDS = [
    (-999.0,  1.1,   0,   0),  # distress zone (flat at 0)
    (   1.1,  2.6,   0,  70),  # grey zone (interpolated)
    (   2.6, 10.0,  70, 100),  # safe zone
]
```

Starts at -999.0 to handle negative-equity tickers (negative Z'' maps to 0 correctly).

### DCF Discount Bands [ASSUMED]

```python
SCORE_DCF_DISCOUNT_WIN_LO = -100.0
SCORE_DCF_DISCOUNT_WIN_HI =   60.0
SCORE_DCF_DISCOUNT_BANDS = [
    (-100.0, -30.0,   0,  10),  # deeply overpriced by DCF
    ( -30.0,   0.0,  10,  40),  # modestly overpriced
    (   0.0,  15.0,  40,  70),  # near fair value
    (  15.0,  30.0,  70,  90),  # meaningful discount
    (  30.0,  60.0,  90, 100),  # deep value
]
```

### DCF Config

```python
DCF_ERP                 = 5.5   # [ASSUMED] equity risk premium %
DCF_TERMINAL_GROWTH_CAP = 3.0   # [ASSUMED] cap terminal growth %
DCF_EXCLUDED_SECTORS    = {"Financial Services", "Real Estate"}
ALTMAN_EXCLUDED_SECTORS = {"Financial Services"}
```

## New Keys on get_yf_price_and_history()

```python
result["income_stmt_df"]   = t.income_stmt    # raw, newest-first
result["balance_sheet_df"] = t.balance_sheet  # raw, newest-first
result["cashflow_df"]      = t.cashflow       # raw, newest-first
```

These are stored UNSORTED (newest-first column ordering). Wave 2 slices them into curr/prev DataFrames before passing to `_compute_piotroski`.

## New Label Lists

Nine new module-level candidate-label lists placed after SHARES_LABELS:
`NET_INCOME_LABELS`, `TOTAL_ASSETS_LABELS`, `GROSS_PROFIT_LABELS`, `REVENUE_LABELS`,
`CURRENT_ASSETS_LABELS`, `CURRENT_LIABILITIES_LABELS`, `LONG_TERM_DEBT_LABELS`,
`RETAINED_EARNINGS_LABELS`, `TOTAL_LIABILITIES_LABELS`.

All tagged `[ASSUMED — yfinance label names vary by ticker; validated on a live Actions run]`.

## overall_score() Status

**UNCHANGED.** `overall_score()`, `process_ticker()`, and `write_json()` are unmodified by this plan. Wave 2 (plan 07-02) wires in the new helpers.

## Test Coverage

| File | Tests | Status |
|------|-------|--------|
| tests/test_distress_phase7.py | 18 | All PASS |
| tests/test_dcf_phase7.py | 14 | All PASS |
| tests/test_scoring.py | 33 | All PASS (no regression) |
| tests/test_growth_trap_fixes.py | 12 | All PASS (no regression) |
| tests/test_factors_phase6.py | 33 | All PASS (no regression) |
| tests/test_scoring_phase6.py | 11 | All PASS (no regression) |
| **Total** | **121** | **All PASS** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Piotroski all-pass fixture had coincidental equal asset turnover**

- **Found during:** Task 2 GREEN phase
- **Issue:** The initial all-pass fixture had `rev_c/ta_c == rev_p/ta_p == 0.5` (F9 not strictly greater than — ties do not pass), and the all-fail fixture had `rev_c/ta_c > rev_p/ta_p` accidentally (F9 passed when it should fail).
- **Fix:** Adjusted `ta_p=25000` in all-pass fixture (making AT_prev=9000/25000=0.36 < AT_curr=0.50) and adjusted `rev_curr=9000` in all-fail fixture (making AT_curr=9000/20000=0.45 < AT_prev=9000/19000=0.47) to ensure both fixtures correctly exercise their intended criterion outcomes.
- **Files modified:** tests/test_distress_phase7.py
- **Commit:** 3de99e6

## Known Stubs

None. All helpers are fully implemented with correct numeric behavior. No placeholder values.

## Threat Flags

No new network endpoints, auth paths, or user-input surfaces introduced. Phase is purely additive pure-computation helpers + test files.

## Self-Check: PASSED
