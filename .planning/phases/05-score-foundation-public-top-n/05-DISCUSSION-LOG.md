# Phase 5: Score Foundation + Public Top-N - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-18
**Phase:** 5-Score Foundation + Public Top-N
**Areas discussed:** Negative-input handling (user-raised), Interim pillar weighting, Value-trap gate teeth, Trap-gate FCF input, Buy Price fix scope

---

## Negative / calculation-breaking input handling (user-raised)

User added this as freeform direction during area selection.

**User's choice:** "Anything that has a negative value that would otherwise prevent calculation, assume it is the worst possible value for that calculation. I do not want them to fail, but I do want them to stand out as terrible choices."

**Notes:** Captured as D-01/D-01b. Distinct from absent-data handling (SCORE-04 avg-over-present). Negative-but-present → worst-possible sub-score (stock still ranks, sinks to bottom, badged). Reshapes the existing `return {"error": ...}` guards in `lynch_metrics`/`graham_metrics`.

---

## Interim pillar weighting

| Option | Description | Selected |
|--------|-------------|----------|
| Target weights + avg-over-present | Keep research ~35/30/20/15; each pillar = avg of present sub-scores; no re-tuning churn | ✓ |
| Explicit interim weights | Phase-5-specific weights tuned to sparse metrics, re-tuned each phase | |
| Equal pillar + equal metric | 25/25/25/25, equal per metric | |

**User's choice:** Target weights + avg-over-present
**Notes:** All 4 pillars already have ≥1 existing input, so target weights are meaningful now. Captured as D-02.

---

## Value-trap gate teeth

| Option | Description | Selected |
|--------|-------------|----------|
| Safety-pillar penalty + badge | Tripped gate floors Safety sub-score, sinks OverallScore; row still shown + badged | ✓ |
| Hard-exclude from Top-N + badge | Tripped traps never appear in Top 10/25 | |
| Badge-only, still ranks | Flag shown, no score effect | |

**User's choice:** Safety-pillar penalty + badge
**Notes:** Consistent with the negative-value philosophy (worst Safety → stands out as terrible). Captured as D-03.

---

## Trap-gate FCF input

| Option | Description | Selected |
|--------|-------------|----------|
| Reuse FCF from existing bundle | FCF already in the discarded Finnhub metric=all response; not a new fetch | ✓ |
| Defer FCF to Phase 6 | Gate on debt/equity, current ratio, EPS stability only until SIGNAL-04 | |

**User's choice:** Reuse FCF from existing bundle
**Notes:** Honors the Phase 5 no-new-fetch constraint (reading an already-fetched field is not a fetch). Negative FCF trips gate + scores worst; coverage-flag where absent. Captured as D-04.

---

## Buy Price fix scope

| Option | Description | Selected |
|--------|-------------|----------|
| Full audit + KO fixture | Audit all Lynch/Graham formulas vs source defs; hand-verified KO fixture | ✓ |
| Denominators-only + KO fixture | Fix only the discount denominators; defer broader audit | |
| Full audit + JNJ fixture | Full audit but JNJ as fixture | |

**User's choice:** Full audit + KO fixture
**Notes:** Matches the deferred-bug note's documented intent ("audit every formula implementation against source definitions"). FIX-02 is a hard gate before the composite. Captured as D-05.

## Claude's Discretion

- Stats nav link deferred to Phase 7 (avoids a 404 to a not-yet-existing stats.html); build app.js nav so adding it later is one line.
- Winsorization bounds, band breakpoints, growth-stability formula — discretion within "loud tunable config constants" (D-02b).
- top.html layout details within the 2026-06-17 approved mockup.

## Deferred Ideas

- Graded FCF yield (positive Value factor) — Phase 6 (SIGNAL-04).
- 52w/5y distance, EV/EBIT, ROIC, shareholder yield — Phase 6.
- Piotroski, Altman, DCF, sector matrix, stats.html, snapshots, methodology refresh — Phase 7.
- Backtest harness — beyond v2.0.
