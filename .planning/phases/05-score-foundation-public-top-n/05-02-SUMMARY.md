---
phase: 05-score-foundation-public-top-n
plan: "02"
subsystem: scoring-engine
tags: [scoring, trap-gate, pillar-scores, json-schema, sort-swap]
dependency_graph:
  requires: [05-01]
  provides: [overall_score, trap_gate, OverallScore-column, nested-scores-json]
  affects: [stock_screener.py, tests/test_scoring.py, results.json-schema]
tech_stack:
  added: []
  patterns: [piecewise-linear-scoring, winsorize-clamp, avg-over-present, trap-gate]
key_files:
  created:
    - tests/test_scoring.py
  modified:
    - stock_screener.py
decisions:
  - "D-01 negative-input worst-score path is distinct from D-01b genuinely-None path in all sub-scores"
  - "growth_stability computed as fraction-of-positive-EPS-years (Open Question 2 resolution)"
  - "nested scores object built post-serialization in write_json() to avoid pandas dict-column edge cases (Pitfall 3)"
  - "is_trap flag does not exclude a row — it sets score_safety=0 and sinks OverallScore"
metrics:
  duration_minutes: ~35
  completed: "2026-06-19"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 2
---

# Phase 05 Plan 02: Score Foundation Summary

**One-liner:** 4-pillar absolute OverallScore engine (Value/Quality/Growth/Safety, 0–100) with piecewise-linear bands, both-tail winsorization, avg-over-present missing data, and interim value-trap gate wired into process_ticker/run_screener/write_json.

---

## What Was Built

### Config Constants Added (stock_screener.py lines ~82–155)

All constants live in the existing loud SCREAMING_SNAKE_CASE block per D-02b. These have **no empirical anchor yet** — they are first-pass estimates, monitored via stats.html in Phase 7.

| Constant | Value | Purpose |
|---|---|---|
| `SCORE_AAA_REFERENCE` | 4.4 | Graham's 1963 reference yield for rate-relativization |
| `SCORE_DISC_WIN_LO` | -100.0 | Discount winsorize floor (below = 2× fair value premium) |
| `SCORE_DISC_WIN_HI` | 60.0 | Discount winsorize cap (matches legacy CombinedScore clip) |
| `SCORE_DISC_BANDS` | 5-band | (-100→-30: 0–10), (-30→0: 10–40), (0→15: 40–70), (15→30: 70–90), (30→60: 90–100) |
| `SCORE_DEF_BANDS` | 4-band | DefensiveScore 0–8 → 0–100 |
| `SCORE_DE_WIN_HI` | 5.0 | D/E winsorize cap |
| `SCORE_DE_BANDS` | 4-band | D/E 0–5 → 100–0 (inverted: lower D/E = better) |
| `SCORE_CR_WIN_HI` | 8.0 | Current ratio winsorize cap |
| `SCORE_CR_BANDS` | 5-band | CR 0–8 → 0–100 (hoarding > 8 slightly penalized) |
| `SCORE_G_BANDS` | 5-band | Growth g 0–25% → 0–100 |
| `SCORE_GSTAB_BANDS` | 4-band | Growth stability 0–1.0 → 0–100 |
| `SCORE_SAFETY_TRAP_PENALTY` | 0 | Safety floor when trap tripped (D-03) |
| `SCORE_SAFETY_NOTRAP_BASE` | 60 | Interim non-trapped baseline (Phase 7 will replace) |
| `TRAP_MAX_DE` | 2.0 | D/E threshold for trap gate |
| `TRAP_MIN_CR` | 1.0 | Current ratio threshold for trap gate |
| `PILLAR_WEIGHTS` | {value:0.35, quality:0.30, growth:0.20, safety:0.15} | D-02 weights |

### Pure Helpers Added

| Function | Signature | Behaviour |
|---|---|---|
| `_piecewise_score(value, bands)` | float → float | Linear interpolation to [0,100]; clamps t to [0,1]; above-last → score_hi |
| `_winsorize(value, lo, hi)` | float → float | Both-tail clamp |
| `_avg_present(values)` | list → float\|None | Average over non-None; None if all absent (D-01b) |
| `trap_gate(de, cr, eps_stab, fcf)` | 4 inputs → (bool, float) | Returns (is_trap, coverage_fraction=count_present/4) |
| `overall_score(...)` | 10 inputs → dict | Returns {overall, value, quality, growth, safety, coverage_pct} |

### overall_score() Pillar Design

**VALUE (weight 0.35):**
- Rate-relativized discount bands: `SCORE_DISC_BANDS` breakpoints × `SCORE_AAA_REFERENCE/aaa_yield`
- WORST_DISCOUNT sentinel → sub-score 0 checked **before** winsorize (D-01)
- Two-level grouping (SCORE-07): Lynch + Graham → discount_group avg → score_value avg
  Phase 6 adds a second sub-group (FCF yield, EV-EBIT) at the same level

**QUALITY (weight 0.30):**
- DefensiveScore (0–8), debt/equity (inverted), current_ratio → _avg_present
- Negative D/E → sub-score 0 (D-01 negative-equity path)

**GROWTH (weight 0.20):**
- Growth g (capped at GROWTH_CAP=25%): non-positive → 0 (D-01)
- Growth stability: fraction of positive-EPS years in annual_eps history
  None when fewer than 3 years available (D-01b)

**SAFETY (weight 0.15):**
- Tripped gate → score_safety = 0 (D-03), regardless of coverage
- All trap inputs None (coverage=0.0) → score_safety = None ("unknown", never safe, D-01b)
- Non-trapped with coverage: score_safety = 60 × coverage_fraction (interim; Phase 7 upgrades)
- Intentional double-use: debt_equity and current_ratio feed BOTH Quality (graded) and Safety (distress gate) — per 05-CONTEXT.md D-02, do not "clean up"

**OVERALL:** Renormalized weighted average over present pillars (D-02 avg-over-present)

### Growth Stability Formula (Open Question 2 Resolution)

Resolution: `growth_stability = count(positive_eps_years) / len(available_years)` (None if < 3 years).

This reuses the same EPS history already consumed by `graham_defensive_score` and avoids introducing a new formula. It captures "does this company consistently earn positive EPS" which is the core stability signal Lynch cares about for Stalwarts. The ±20% YoY decline variant from RESEARCH.md Open Question 2 was deferred — the fraction-positive formula is simpler and measurable with the available data.

### JSON Schema (SCORE-05)

**Flat columns added to each row (additive — no existing keys removed):**
- `OverallScore` — float (0–100) or null
- `score_value`, `score_quality`, `score_growth`, `score_safety` — float (0–100) or null
- `is_trap` — boolean
- `coverage_pct` — float (0–100)

**Nested `scores` object (built post-serialization in write_json):**
```json
{
  "scores": {
    "overall": 37.7,
    "value": 0.0,
    "quality": 49.0,
    "growth": 70.0,
    "safety": 60.0,
    "coverage_pct": 100.0,
    "trap": false
  }
}
```

### Sort Key Swap (SCORE-08)

`run_screener()` now sorts by `OverallScore` descending (`na_position="last"`). Falls back to `CombinedScore` if `OverallScore` column is absent. `CombinedScore` column is retained (additive schema, D-02c).

---

## Sample Scored Row — KO-like Inputs

Inputs derived from the test_valuation_fixture.py snapshot (price=70, eps=2.50, g=7%, dy=3%, aaa=5.5%):

| Field | Value | Notes |
|---|---|---|
| Lynch_Discount_Pct | -273.3% | Below -100% winsorize floor → Value sub-score = 0 |
| Graham_Discount_Pct | -150.0% | Below -100% winsorize floor → Value sub-score = 0 |
| DefensiveScore | 5/8 | Quality franchise but some criterion misses |
| debt_equity | 1.8 | Below TRAP_MAX_DE=2.0, above mid bands → Quality drag |
| current_ratio | 1.1 | Above TRAP_MIN_CR=1.0, weak liquidity → Quality drag |
| growth_g | 7.0% | Moderate Slow Grower |
| growth_stability | 0.9 | 90% positive-EPS years |
| is_trap | False | No gate trip (CR just above threshold) |
| coverage_fraction | 1.0 | All 4 gate inputs present |
| **score_value** | **0.0** | Large negative discounts below winsorize floor |
| **score_quality** | **49.0** | DefensiveScore 5, moderate D/E+CR |
| **score_growth** | **70.0** | Decent g + stable EPS history |
| **score_safety** | **60.0** | Non-trapped, full coverage × base 60 |
| **OverallScore** | **37.7** | Dragged down by Value=0 (expensive relative to models) |

KO at $70 is correctly ranked low — the models flag it as expensive relative to conservative fair-value targets. This is expected model behavior, not a defect (confirmed by test_valuation_fixture.py).

---

## Test Coverage

`tests/test_scoring.py` — 33 tests, all pass. Vanilla assert only, no pytest.

| Category | Tests |
|---|---|
| `_piecewise_score` | 8 (below/at/boundary/above/interior ×2, inverted) |
| `_winsorize` | 5 (within, at lo, at hi, below lo, above hi) |
| `_avg_present` | 5 (all values, with None, single, all None, empty) |
| `trap_gate` | 8 (each of 4 inputs trips; all-clear; all-None; partial coverage ×2) |
| `overall_score` | 7 (high-quality row; WORST_DISCOUNT→value=0; all-Safety-None; trap→safety=0; pillar renorm; coverage_pct; neg D/E) |

---

## Deviations from Plan

None — plan executed exactly as written.

Minor implementation notes (not deviations):
- Task 1 (RED commit) and Task 2 (GREEN commit) were combined into a single git commit because `test_scoring.py` imports both `trap_gate` and `overall_score` at module level — a partial import would fail before any test ran. The RED→GREEN→feat sequence is preserved in the commit message and the implementation order.
- `growth_stability` formula (Open Question 2): chose `fraction_positive_eps_years` over the `±20% YoY decline` variant. Rationale: simpler, reuses existing data, measurable. The more complex variant is not lost — the Phase 7 stats.html monitoring pass can compare both.

---

## Known Stubs

None. All scoring logic is fully wired. No hardcoded empty values, placeholders, or TODO stubs in the implemented functions.

Note: `SCORE_SAFETY_NOTRAP_BASE = 60` is an interim constant (documented as such) — it will be replaced by Altman Z / Piotroski F scores in Phase 7 (TRAP-03). This is intentional and documented in the constant's comment, not a stub.

---

## Threat Flags

No new threat surface introduced. All scoring is pure computation over already-fetched data. The threat register entries T-05-04 and T-05-05 are mitigated:
- T-05-04: `_winsorize` bounds every metric; a glitch value cannot dominate a sub-score.
- T-05-05: D-01b missing-Safety-as-unknown is implemented — all-None trap inputs yield `score_safety=None` (never the full 60-point baseline).

---

## Self-Check: PASSED

- `tests/test_scoring.py` exists: FOUND
- `tests/test_valuation_fixture.py` still passes: FOUND (6/6 assertions pass)
- Commit 55488d2 (test RED + implementation): FOUND
- Commit ee09d40 (Task 3 wiring): FOUND
- `overall_score(` appears in stock_screener.py: FOUND
- `sort_values("OverallScore"` appears in stock_screener.py: FOUND
- `"scores"` appears in write_json: FOUND
- `CombinedScore` column assignment NOT removed: CONFIRMED (git diff shows no deletion of the assignment line)
- `requirements.txt` unchanged (no pytest): CONFIRMED
