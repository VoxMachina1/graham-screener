---
phase: 06-cheap-factors-sector
plan: "02"
subsystem: scoring-layer
tags: [scoring, value-sub-groups, roic, price-position, recency, fcf-yield, earnings-yield]
requires: ["06-01"]
provides:
  - SCORE_FCF_YIELD_*, SCORE_EARN_YIELD_*, SCORE_SH_YIELD_* constants
  - SCORE_DIST_52W_LOW_*, SCORE_DIST_52W_HIGH_*, SCORE_DIST_5Y_LOW_* constants (two descending)
  - SCORE_RECENCY_FLOOR=0.70, SCORE_RECENCY_FULL_WK=26
  - SCORE_ROIC_* constants
  - _recency_multiplier() helper
  - overall_score() extended with 9 new None-defaulted params + 3-subgroup Value + ROIC in Quality
  - value_discount / value_yield / value_price sub-group scores in return dict
  - score_value_discount / score_value_yield / score_value_price flat columns in process_ticker
  - value_discount / value_yield / value_price nested keys in write_json scores object
  - coverage_pct denominator grown from 8 to 15 leaf sub-scores
affects:
  - stock_screener.py (SCORE_* block, _recency_multiplier, overall_score, process_ticker, write_json)
  - tests/test_scoring_phase6.py (new)
key-files:
  created:
    - tests/test_scoring_phase6.py
  modified:
    - stock_screener.py
decisions:
  - "VALUE = _avg_present of 3 equal sub-groups: discount (Lynch/Graham), yield (FCF+earnings+shareholder), price-position (dist_52w_low + dist_52w_high + dist_5y_low) — SCORE-07/D-05"
  - "EV/EBIT stays diagnostic-only — scoring earnings_yield (its reciprocal) avoids double-count; no SCORE_EV_EBIT_* constant, no ev_ebit param, no evebit_sub (plan-checker resolution)"
  - "Inverted metrics (dist_52w_low, dist_5y_low) encoded via DESCENDING band tables (score_lo > score_hi), not an invert param on _piecewise_score"
  - "Recency is a multiplier on the two distance-from-low sub-scores, never a standalone sub-score"
  - "ROIC <= 0 → sub-score 0.0 (D-01); ROIC None → Quality average-over-present over remaining 3 inputs (D-01b)"
  - "GROWTH, SAFETY, and PILLAR_WEIGHTS (35/30/20/15) unchanged (D-05)"
metrics:
  completed: "2026-06-28"
  tasks_completed: 2
  files_changed: 2
  tests_added: 11
  total_tests_passing: 89
---

# Phase 06 Plan 02: SCORING Layer — 3-Subgroup Value + ROIC in Quality Summary

**One-liner:** Folds the 9 Phase-6 raw factor fields into the 4-pillar composite via three equal Value sub-groups and ROIC in Quality, with descending bands encoding price-position inversion and a recency multiplier modulating distance-from-low scores.

---

## Final `overall_score()` Signature

```python
overall_score(
    lynch_discount, graham_discount,       # Value sub-group 1 (discount)
    defensive_score, debt_equity,          # Quality inputs
    current_ratio,
    growth_g, growth_stability,            # Growth inputs
    is_trap, coverage_fraction, aaa_yield, # Safety / meta
    # Phase-6 additions (all default None — backward-compat):
    fcf_yield=None, earnings_yield=None, shareholder_yield=None,  # Value sub-group 2
    roic=None,                                                     # Quality
    dist_52w_low=None, dist_52w_high=None, dist_5y_low=None,      # Value sub-group 3
    weeks_since_52w_low=None, weeks_since_5y_low=None,            # Recency multipliers
) -> dict
```

**No `ev_ebit` param** — EV/EBIT is diagnostic-only.

---

## New SCORE_* Constants

| Group | Constants | Direction |
|---|---|---|
| Value yield | `SCORE_FCF_YIELD_WIN_LO/HI + BANDS` | ascending |
| Value yield | `SCORE_EARN_YIELD_WIN_LO/HI + BANDS` | ascending |
| Value yield | `SCORE_SH_YIELD_WIN_LO/HI + BANDS` | ascending |
| Value price | `SCORE_DIST_52W_LOW_WIN_LO/HI + BANDS` | **descending** (nearer low → higher score) |
| Value price | `SCORE_DIST_52W_HIGH_WIN_LO/HI + BANDS` | ascending |
| Value price | `SCORE_DIST_5Y_LOW_WIN_LO/HI + BANDS` | **descending** |
| Value price | `SCORE_RECENCY_FLOOR = 0.70`, `SCORE_RECENCY_FULL_WK = 26` | — |
| Quality | `SCORE_ROIC_WIN_LO/HI + BANDS` | ascending |

`SCORE_EV_EBIT_BANDS` does **not** exist.

---

## Value Pillar Architecture

```
VALUE = _avg_present([discount_group, yield_group, price_group])

discount_group = _avg_present([lynch_sub, graham_sub])

yield_group    = _avg_present([fcf_sub, earny_sub, shy_sub])
                 each: None→None, ≤0→0.0, else piecewise ascending

price_group    = _avg_present([s_52w_lo, s_52w_hi, s_5y_lo])
  s_52w_lo = piecewise_DESCENDING(dist_52w_low) * _recency_multiplier(weeks_since_52w_low)
  s_52w_hi = piecewise_ascending(dist_52w_high)          # no recency
  s_5y_lo  = piecewise_DESCENDING(dist_5y_low) * _recency_multiplier(weeks_since_5y_low)
```

---

## Coverage Leaf Count: 15

`lynch, graham, fcf, earny, shy, s_52w_lo, s_52w_hi, s_5y_lo, def, de, cr, roic, growth_g, growth_stab, safety`

Excluded from `all_sub_scores`: evebit_sub (not scored), recency values (multipliers only), sub-group aggregates (discount_group, yield_group, price_group).

A Phase-5-only row (no Phase-6 inputs) now shows `coverage_pct = 8/15 ≈ 0.53` — lower than before, by design (more leaves, same inputs).

---

## New Columns Emitted

**Flat (process_ticker):**
- `score_value_discount`, `score_value_yield`, `score_value_price`

**Nested (write_json `scores` object):**
- `value_discount`, `value_yield`, `value_price`

Existing columns/keys untouched. Compact JSON (`separators=(",",":")`) and `<100-row` guard preserved.

---

## Test Results

| Suite | Tests | Result |
|---|---|---|
| test_scoring.py | 33 | ✅ all pass |
| test_growth_trap_fixes.py | 12 | ✅ all pass |
| test_factors_phase6.py | 33 | ✅ all pass |
| test_scoring_phase6.py | 11 | ✅ all pass |
| **Total** | **89** | **✅** |

`test_scoring_phase6.py` covers: backward compat (existing 10 positional args → 3 new value_* keys present), band direction assertions, higher-yield-scores-higher, nearer-low-scores-higher, 3-subgroup equality, ROIC into Quality, ROIC≤0 worst, recency multiplier endpoints, recency modulates score, negative yield → worst (0.0), coverage grows to 15.

---

## Deviations from Plan

None. All tasks executed exactly as planned.
