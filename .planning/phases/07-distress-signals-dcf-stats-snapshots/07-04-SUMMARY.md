---
phase: 07-distress-signals-dcf-stats-snapshots
plan: 04
subsystem: scoring
tags: [piotroski, altman, dcf, github-actions, gap-closure]

# Dependency graph
requires:
  - phase: 07-distress-signals-dcf-stats-snapshots (plans 01-03)
    provides: Piotroski F-Score, Altman Z'', forward/reverse DCF, sector applicability matrix, stats.html, snapshot workflow
provides:
  - Piotroski F5 fail-safe fix (no longer awards leverage-decreased point on missing current-year LTD)
  - DCF_GROWTH_FLOOR constant floors reconciled growth before every DCF call (no sign-flip/negative intrinsic)
  - CYCLICAL_SECTORS constant + DCF_Cyclical_Flag column (D-10)
  - env: block on the "Commit monthly snapshot" workflow step (CI no longer crashes on import)
affects: [phase-08, future-tuning-phases]

# Tech tracking
tech-stack:
  added: []
  patterns: ["fail-safe missing-data guards mirrored across Piotroski criteria (F5/F6/F8)", "floor-at-call-site (not inside pure helper) to keep shared g intact for other consumers"]

key-files:
  created: []
  modified:
    - stock_screener.py
    - tests/test_distress_phase7.py
    - tests/test_dcf_phase7.py
    - .github/workflows/screener.yml

key-decisions:
  - "F5 guard now requires long_term_debt_curr is not None to even be counted, rather than counting-and-defaulting-to-0 like F6/F8 — chosen per 07-REVIEW.md CR-02's explicit recommended fix (removes the inline default entirely instead of picking a fail-biased default for a '<' comparison)."
  - "Growth floor applied ONLY at the DCF call site (g_dcf = max(g, DCF_GROWTH_FLOOR)), never to the shared g used by Lynch/Graham, preserving the existing WORST_DISCOUNT routing for negative growth (D-01)."
  - "DCF_Cyclical_Flag is a flat boolean column only (no UI badge) — explicitly out of scope for this gap-closure plan per the plan's Task 2 instructions."

patterns-established: []

requirements-completed: [SIGNAL-08, TRAP-03, DCF-01, DCF-03, DATA-01, DATA-02]

# Metrics
duration: 10min
completed: 2026-07-01
---

# Phase 07 Plan 04: Gap Closure (F5 fail-safe, DCF growth floor + cyclical flag, snapshot env block) Summary

**Fixed Piotroski F5's inverted fail-safe, floored DCF growth to prevent sign-flipped intrinsic values, added the D-10 cyclical flag, and gave the monthly snapshot workflow step its missing env: block — closing all three CR-01/CR-02/CR-03 defects from 07-VERIFICATION.md.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-07-01T19:09:06-04:00 (plan commit)
- **Completed:** 2026-07-01T19:13:58-04:00 (final task commit)
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Piotroski F5 ("leverage decreased") now fails safe on missing current-year long-term-debt, matching F6/F8's convention — no more silent F-Score/Safety-pillar inflation on missing data.
- Reconciled growth `g` is floored to `DCF_GROWTH_FLOOR = -50.0` before every DCF call, so severely negative growth (e.g. -150%) can no longer sign-flip `(1+g)` into a negative/nonsensical intrinsic value that scored as a false "deep value" BUY.
- `CYCLICAL_SECTORS = {"Energy", "Basic Materials"}` and `row["DCF_Cyclical_Flag"]` implement D-10's cyclical-sector coverage flag, true only when sector is cyclical AND DCF was actually computed.
- The "Commit monthly snapshot" GitHub Actions step now has an `env:` block with `FRED_API_KEY`/`FINNHUB_API_KEY`, so `import stock_screener` no longer raises `KeyError` in CI — monthly snapshots can actually land.

## Task Commits

Each task followed RED (failing test) → GREEN (fix) TDD for Tasks 1-2; Task 3 was a non-TDD YAML fix.

1. **Task 1: Fix Piotroski F5 inverted fail-safe + regression test**
   - `a399c7d` (test) — RED: `test_piotroski_f5_fails_safe_on_missing_ltd_curr` added, confirmed failing against buggy code (both fixtures scored 9, no 1-point delta).
   - `2d0aedc` (fix) — GREEN: guarded F5 block on `long_term_debt_curr is not None`, removed the inline default-to-0. Confirmed 39/39 tests pass.
2. **Task 2: Floor DCF growth rate + implement D-10 cyclical flag + regression test**
   - `8da8267` (test) — RED: `test_dcf_growth_floor_constant_is_sane` and `test_dcf_forward_growth_floor_prevents_sign_flip` added, importing `DCF_GROWTH_FLOOR` which did not yet exist — confirmed `ImportError`.
   - `83995e6` (fix) — GREEN: added `DCF_GROWTH_FLOOR`/`CYCLICAL_SECTORS` constants, floored `g_dcf` at the DCF call site for both forward/reverse calls, emitted `row["DCF_Cyclical_Flag"]`. Confirmed 16/16 DCF tests + 39/39 distress tests pass.
3. **Task 3: Add env: block to the monthly snapshot workflow step**
   - `9434baa` (fix) — added `env:` block (FRED_API_KEY/FINNHUB_API_KEY) to the "Commit monthly snapshot" step, copied key-for-key from "Run screener". Confirmed via `yaml.safe_load` assertion: `OK: snapshot step env block present: ['FINNHUB_API_KEY', 'FRED_API_KEY']`.

**Plan metadata:** (this commit, made after this Summary)

## Files Created/Modified
- `stock_screener.py` — F5 fail-safe guard (lines ~1230-1237), `DCF_GROWTH_FLOOR`/`CYCLICAL_SECTORS` config constants (lines ~303-315), growth-floor applied at DCF call site, `DCF_Cyclical_Flag` column emitted in `process_ticker()`.
- `tests/test_distress_phase7.py` — new `test_piotroski_f5_fails_safe_on_missing_ltd_curr` regression test, registered in `run_all()`.
- `tests/test_dcf_phase7.py` — new `test_dcf_growth_floor_constant_is_sane` and `test_dcf_forward_growth_floor_prevents_sign_flip` regression tests, `DCF_GROWTH_FLOOR` added to imports, both registered in `run_all()`.
- `.github/workflows/screener.yml` — `env:` block added to the "Commit monthly snapshot" step.

## Decisions Made
- Matched 07-REVIEW.md CR-02's exact recommended fix for F5 (guard on presence, remove the inline default) rather than inventing a new fail-biased default value — keeps the fix minimal and auditable against the review.
- Floored growth only at the two DCF call sites, not the shared `g` variable, to avoid touching the intentional D-01 WORST_DISCOUNT routing for Lynch/Graham on negative growth (explicitly called out as a risk in the plan).
- Did not touch `_compute_dcf_forward`/`_compute_dcf_reverse` internals — their 14 pre-existing tests needed to stay green untouched, confirming the fix's blast radius is exactly the call site.

## Deviations from Plan

None - plan executed exactly as written. All three tasks matched their `<action>` and `<behavior>` specifications; no scope creep beyond the three named defects.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. (The `env:` block references pre-existing `FRED_API_KEY`/`FINNHUB_API_KEY` GitHub Actions secrets already configured for the "Run screener" step in earlier phases.)

## Next Phase Readiness

- All three CR-01/CR-02/CR-03 gaps from 07-VERIFICATION.md are closed with passing regression coverage for the two unit-testable defects (F5, DCF growth floor). The workflow YAML fix (Gap 3) is verified via a `yaml.safe_load` structural assertion since no local CI runner is available — full confirmation requires the next first-weekday-of-month scheduled run in production.
- Full six-suite regression run (`test_distress_phase7.py`, `test_dcf_phase7.py`, `test_scoring.py`, `test_scoring_phase6.py`, `test_factors_phase6.py`, `test_growth_trap_fixes.py`) reports 144 passed, 0 failed — no regressions introduced.
- Phase 7 is now ready to be marked complete; recommend re-running `/gsd-verify-phase 07` to confirm all 5 roadmap success criteria now pass.

---
*Phase: 07-distress-signals-dcf-stats-snapshots*
*Completed: 2026-07-01*
