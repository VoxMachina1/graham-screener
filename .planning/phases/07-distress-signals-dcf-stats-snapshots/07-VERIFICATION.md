---
phase: 07-distress-signals-dcf-stats-snapshots
verified: 2026-07-01T23:25:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 2/5
  gaps_closed:
    - "Piotroski F5 inverted fail-safe on missing current-year long-term-debt (CR-02)"
    - "DCF growth rate unbounded (sign-flip/negative intrinsic) + missing D-10 cyclical flag (CR-03)"
    - "Monthly snapshot workflow step missing env: block causing KeyError in CI (CR-01)"
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "DATA-03 (30-day fundamentals cache)"
    addressed_in: "Future phase (explicitly out of scope for Phase 7)"
    evidence: "07-CONTEXT.md 'Out of scope (defer)' and 'Claude's Discretion' sections explicitly defer DATA-03 per user decision; REQUIREMENTS.md correctly lists it as '[ ] (Optional)' / 'Pending'. Not flagged as a gap per verification instructions."
---

# Phase 7: Distress Signals, DCF, Stats & Snapshots Verification Report

**Phase Goal:** Piotroski F-Score and Altman Z'' upgrade the interim trap-gate into the real Safety-pillar driver; forward + reverse DCF give per-stock intrinsic value and an expectations gap; a per-metric sector applicability matrix keeps sector-invalid signals out of the score; stats.html plus committed historic snapshots make the universe observable and comparable over time.

**Verified:** 2026-07-01T23:25:00Z
**Status:** passed
**Re-verification:** Yes — after 07-04 gap-closure plan (fixes CR-01/CR-02/CR-03)

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Piotroski F-Score (0-9) and Altman Z'' computed per ticker, replace/augment interim gate as Safety-pillar driver | ✓ VERIFIED | `is_trap` remains structurally removed from `overall_score()`'s scoring signature (Safety driven by Piotroski+Altman+defensive/de/cr). **Gap 1 closed:** F5 criterion (stock_screener.py:1241-1247) now guards `long_term_debt_curr is not None` in the same if-condition as the other four LTD/CR/GM criteria, and the inline `... if long_term_debt_curr is not None else 0` default was removed entirely — `ltd_ratio_curr = long_term_debt_curr / avg_assets` is unconditional inside the guarded block, exactly mirroring F6/F8's fail-safe pattern. Confirmed by direct read of the current code (not the SUMMARY). New regression test `test_piotroski_f5_fails_safe_on_missing_ltd_curr` (tests/test_distress_phase7.py:317) builds a fixture with prior-year LTD present but current-year LTD absent and asserts the score is exactly 1 point lower than the legitimate-pass fixture; ran directly — passes (39 passed, 0 failed in the full suite). |
| 2 | Forward + reverse DCF, sector-guarded (financials excluded, cyclicals flagged), terminal<discount assert, bounded solver -> None never silent default | ✓ VERIFIED | **Gap 2 closed, two parts:** (a) `DCF_GROWTH_FLOOR = -50.0` added to the DCF config block (stock_screener.py:313); at the DCF call site (line 2146) `g_dcf = max(g, DCF_GROWTH_FLOOR)` is computed and passed to both `_compute_dcf_forward` and `_compute_dcf_reverse` (lines 2147-2148); the shared, unfloored `g` still flows to Lynch/Graham's WORST_DISCOUNT routing unchanged. Reproduced live: `_compute_dcf_forward(eps=2.0, g_cagr_pct=max(-150.0, DCF_GROWTH_FLOOR), aaa_yield_pct=5.0, price=10.0)` now returns `intrinsic=1.65` (positive, finite) instead of the previously-reproduced `-0.62` (negative/nonsensical). (b) `CYCLICAL_SECTORS = {"Energy", "Basic Materials"}` (line 316) and `dcf_cyclical_flag = (fund.get("sector") in CYCLICAL_SECTORS) and _sector_allows(fund, "dcf")` (line 2152), emitted as `row["DCF_Cyclical_Flag"]` (line 2205) — confirmed by reading `_sector_allows`: Energy/Basic Materials are not in `DCF_EXCLUDED_SECTORS`, so the flag correctly evaluates True only when DCF was actually computed for those two sectors, and `None in CYCLICAL_SECTORS` is False so `sector=None` never sets the flag (matches 07-RESEARCH.md Pitfall 7). The terminal<WACC assert and bounded-solver-emits-None behaviors remain correctly implemented (unchanged, still tested). New regression tests `test_dcf_growth_floor_constant_is_sane` and `test_dcf_forward_growth_floor_prevents_sign_flip` (tests/test_dcf_phase7.py:171,184) pass; `_compute_dcf_forward`/`_compute_dcf_reverse` internals are untouched — all 14 pre-existing DCF tests still pass (16/16 total). |
| 3 | Per-metric sector applicability matrix; invalid signals treated as missing, never zero | ✓ VERIFIED (regression check) | `_sector_allows(fund, metric)` (stock_screener.py:319-336) unchanged since prior verification; still correctly gates dcf/altman/earnings_yield/ev_ebit by sector, returns True (no exclusion) for unknown sector. All 6 dedicated unit tests (`test_sector_allows_*`) re-ran and pass; no regression. |
| 4 | docs/stats.html presents universe overview; methodology.html documents new signals/scoring/sector guards | ✓ VERIFIED (regression check) | `docs/stats.html` (161 lines), `docs/methodology.html` (492 lines), `docs/history.html` (100 lines), `docs/data/stats.json` all still present on disk and unchanged by 07-04 (07-04 touched only `stock_screener.py`, two test files, and `screener.yml` per its file_modified list — confirmed via `git show a7766e4 --stat` equivalent file list). No regression. |
| 5 | Actions workflow commits periodic monthly (first-weekday) snapshots under docs/data/snapshots/, reusing min-row guard; DATA-03 correctly deferred | ✓ VERIFIED | **Gap 3 closed:** the "Commit monthly snapshot" step in `.github/workflows/screener.yml` (lines 55-72) now has an `env:` block (lines 57-59) with `FRED_API_KEY: ${{ secrets.FRED_API_KEY }}` and `FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}`, matching the "Run screener" step's env block (lines 29-31) key-for-key, same secret names, same indentation. Confirmed structurally via `yaml.safe_load` (`OK: snapshot step env block present: ['FINNHUB_API_KEY', 'FRED_API_KEY']`). Functionally confirmed by reproducing the underlying failure mode in a clean subprocess isolated from the repo's `.env` file (cwd outside the git tree, `.env`-masking `find_dotenv()` upward search defeated): `import stock_screener` without `FRED_API_KEY`/`FINNHUB_API_KEY` in the environment raises `KeyError: 'FRED_API_KEY'` — proving the module genuinely requires these vars at import time, and that the new `env:` block (which supplies them from GitHub Actions secrets in CI) is what prevents the crash. `.gitignore` snapshot exceptions (`!docs/data/snapshots/*.json`, `!docs/data/snapshots/index.json`) still present and untouched. Min-row guard is still upstream in `write_json()` (unchanged). DATA-03 deferral correctly honored (not flagged as a gap). |

**Score:** 5/5 truths verified (all three prior gaps closed and independently re-confirmed by direct code inspection + live execution, not SUMMARY.md claims; Truths 3 and 4 re-confirmed with no regression)

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | DATA-03 (30-day fundamentals cache) | Future phase (explicit out-of-scope) | 07-CONTEXT.md explicitly defers DATA-03 per user decision; REQUIREMENTS.md marks it `[ ]`/Pending correctly. Per verification instructions, its absence is NOT a gap. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `stock_screener.py::_compute_piotroski` (F5 block) | Fails safe on missing current-year LTD | ✓ VERIFIED | Lines 1239-1247; guard includes `and long_term_debt_curr is not None`, no default-to-0 |
| `stock_screener.py::DCF_GROWTH_FLOOR` | Floor constant, applied at DCF call site | ✓ VERIFIED | Line 313 (`-50.0`); applied at line 2146 (`g_dcf = max(g, DCF_GROWTH_FLOOR)`), consumed by both forward (2147) and reverse (2148) calls |
| `stock_screener.py::CYCLICAL_SECTORS` / `DCF_Cyclical_Flag` | D-10 cyclical coverage flag | ✓ VERIFIED | Lines 316, 2152, 2205; correct boolean logic confirmed by reading `_sector_allows` |
| `.github/workflows/screener.yml` snapshot step | env: block with FRED_API_KEY/FINNHUB_API_KEY | ✓ VERIFIED | Lines 57-59; matches "Run screener" step key-for-key; `yaml.safe_load` assertion passes |
| `tests/test_distress_phase7.py::test_piotroski_f5_fails_safe_on_missing_ltd_curr` | F5 regression test | ✓ VERIFIED | Present, registered, passes (39/39 suite) |
| `tests/test_dcf_phase7.py::test_dcf_forward_growth_floor_prevents_sign_flip` / `test_dcf_growth_floor_constant_is_sane` | DCF floor regression tests | ✓ VERIFIED | Present, registered, pass (16/16 suite) |
| `stock_screener.py::_compute_altman_z` | Z'' pure helper | ✓ VERIFIED (unchanged) | Formula matches spec; tested |
| `stock_screener.py::_compute_dcf_forward` / `_compute_dcf_reverse` internals | Untouched by gap closure | ✓ VERIFIED | 14 pre-existing tests unchanged and passing |
| `stock_screener.py::_sector_allows` | Sector applicability gate | ✓ VERIFIED (unchanged) | Wired and tested |
| `docs/data/stats.json` / `docs/stats.html` / `docs/history.html` / `docs/methodology.html` | Universe overview + docs | ✓ VERIFIED (unchanged) | Present, substantive, not touched by 07-04 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `process_ticker()` growth `g` | `_compute_dcf_forward` / `_compute_dcf_reverse` | `g_dcf = max(g, DCF_GROWTH_FLOOR)` | ✓ WIRED | Confirmed at stock_screener.py:2146-2148; live-reproduced sign-flip is prevented |
| `process_ticker()` sector + `_sector_allows` | `row["DCF_Cyclical_Flag"]` | boolean AND of sector membership + DCF-allowed | ✓ WIRED | Confirmed at stock_screener.py:2152, 2205 |
| `screener.yml` "Commit monthly snapshot" step | `stock_screener` module import | step-level `env:` block | ✓ WIRED | Confirmed via `yaml.safe_load`; underlying KeyError-on-missing-vars behavior independently reproduced in an isolated subprocess |
| `process_ticker()` | `overall_score(piotroski_f=, altman_z=, dcf_discount_pct=)` | kwarg pass | ✓ WIRED (unchanged) | Confirmed at stock_screener.py:2181-2183 |
| `docs/stats.html` / `docs/history.html` | `docs/data/stats.json` / `docs/data/snapshots/index.json` | cache-busted fetch | ✓ WIRED (unchanged) | Not touched by 07-04 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Floored growth produces a positive, finite DCF intrinsic (was negative pre-fix) | `_compute_dcf_forward(eps=2.0, g_cagr_pct=max(-150.0, DCF_GROWTH_FLOOR), aaa_yield_pct=5.0, price=10.0)` | `intrinsic=1.65, discount_pct=-505.0` (positive intrinsic, no sign flip) | ✓ PASS — confirms Gap 2 closed |
| `import stock_screener` fails without env vars, isolated from repo `.env` | Subprocess with `cwd` outside git tree, `FRED_API_KEY`/`FINNHUB_API_KEY` stripped, `PYTHONPATH` pointing at worktree | `KeyError: 'FRED_API_KEY'`, exit 1 | ✓ PASS — confirms the module genuinely needs the env block (proves why Gap 3's fix matters) |
| `.github/workflows/screener.yml` "Commit monthly snapshot" step has required env keys | `yaml.safe_load` + key assertion | `OK: snapshot step env block present: ['FINNHUB_API_KEY', 'FRED_API_KEY']` | ✓ PASS — confirms Gap 3 closed |
| `tests/test_distress_phase7.py` full suite | `python tests/test_distress_phase7.py` | 39 passed, 0 failed | ✓ PASS |
| `tests/test_dcf_phase7.py` full suite | `python tests/test_dcf_phase7.py` | 16 passed, 0 failed | ✓ PASS |
| `tests/test_scoring.py` | `python tests/test_scoring.py` | 33 passed, 0 failed | ✓ PASS (no regression) |
| `tests/test_scoring_phase6.py` | `python tests/test_scoring_phase6.py` | 11 passed, 0 failed | ✓ PASS (no regression) |
| `tests/test_factors_phase6.py` | `python tests/test_factors_phase6.py` | 33 passed, 0 failed | ✓ PASS (no regression) |
| `tests/test_growth_trap_fixes.py` | `python tests/test_growth_trap_fixes.py` | 12 passed, 0 failed | ✓ PASS (no regression) |

Total across all 6 suites: 144 passed, 0 failed — matches 07-04-SUMMARY.md's claim, independently re-run (not trusted from SUMMARY alone).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SIGNAL-08 | 07-01, 07-02, 07-04 | Piotroski F-Score (0-9) | ✓ SATISFIED | F5 fail-safe defect closed; no other defects found |
| SIGNAL-09 | 07-01, 07-02 | Altman Z'' with distress zones | ✓ SATISFIED | Unchanged, no defects |
| TRAP-03 | 07-02, 07-03, 07-04 | Piotroski/Altman replace interim gate as Safety driver | ✓ SATISFIED | F5 defect closed; Safety pillar no longer inflated on missing data |
| DCF-01 | 07-01, 07-02, 07-04 | Forward two-stage DCF intrinsic value + discount % | ✓ SATISFIED | Growth floor closes the sign-flip defect; live-reproduced fix |
| DCF-02 | 07-01, 07-02 | Reverse DCF implied-growth gap | ✓ SATISFIED | Bounded solver correct and tested (unchanged) |
| DCF-03 | 07-01, 07-02, 07-04 | Sector-guarded, terminal<discount assert, bounded solver -> None | ✓ SATISFIED | Cyclical flag (D-10) implemented and verified; assert + bounded-solver sub-parts unchanged and correct |
| SECTOR-02 | 07-02 | Per-metric sector applicability matrix | ✓ SATISFIED | `_sector_allows` verified and tested (unchanged). Note: REQUIREMENTS.md checkbox is still stale (`[ ]`/"Pending") despite the feature being implemented and marked Complete in the requirement-map table below it — pre-existing documentation staleness, not a functional gap, not introduced by 07-04. |
| PAGE-02 | 07-02, 07-03 | docs/stats.html universe overview | ✓ SATISFIED | Verified substantive (unchanged) |
| DATA-01 | 07-03, 07-04 | Periodic snapshots under docs/data/snapshots/ | ✓ SATISFIED | Workflow step no longer crashes before committing; env block fix verified structurally + functionally |
| DATA-02 | 07-03, 07-04 | Snapshot step reuses min-row guard; vintage caveat documented | ✓ SATISFIED | Min-row guard logic unchanged and upstream; step now actually reaches it in CI |
| DATA-03 | (none — explicitly deferred) | 30-day fundamentals cache | — DEFERRED | Correctly out of scope per 07-CONTEXT.md; not a gap |
| METH-01 | 07-03 | methodology.html documents new signals/scoring/guards | ✓ SATISFIED | Verified substantive (unchanged) |

**Orphaned requirements:** None. All 11 in-scope requirement IDs (excluding the explicitly-deferred DATA-03) are claimed by at least one plan's frontmatter `requirements:` field, including 07-04's `[SIGNAL-08, TRAP-03, DCF-01, DCF-03, DATA-01, DATA-02]`.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `stock_screener.py` | 2154-2157, 2210-2211 (unchanged) | `coverage_fraction` param threaded through but unused inside `overall_score()` after the Safety rewrite | ℹ️ Info (pre-existing, not introduced by 07-04) | Orphaned plumbing, no functional impact (review WR-03, carried forward) |
| `stock_screener.py` | 1124-1271 (unchanged) | Raw Piotroski score not rescaled when `criteria_counted < 9`; F1 silently skipped (not failed) when `net_income_curr` is entirely absent | ⚠️ Warning (pre-existing, not introduced by 07-04, not one of the 3 closed gaps) | Thin-history tickers may be penalized vs. the documented contract (review WR-04, carried forward — out of scope for this gap-closure plan) |
| `stock_screener.py` | ~2160-2165 (unchanged) | Unguarded call to a function documented to `raise ValueError` on terminal-growth >= WACC | ⚠️ Warning (pre-existing, carried forward) | An unusual AAA-yield reading could abort the batch run (review WR-01, not independently reproduced, code-confirmed only) |
| `.gitignore` | 7-8 | Redundant negation pattern for `docs/data/snapshots/index.json` | ℹ️ Info (pre-existing, explicitly out of scope for 07-04 per its Task 3 action text) | Cosmetic only |

Debt-marker scan (`TBD`/`FIXME`/`XXX`) on files modified in 07-04 (`stock_screener.py`, `tests/test_distress_phase7.py`, `tests/test_dcf_phase7.py`, `.github/workflows/screener.yml`): none found.

None of the carried-forward Warning/Info items are among the 3 gaps this re-verification cycle was scoped to confirm, and none block any of the 5 roadmap success criteria — they were already present (and already non-blocking) at the time of the prior `gaps_found` verification, and the 07-04 gap-closure plan explicitly and correctly declined to touch them ("does NOT replan or re-touch any correctly-implemented Phase 7 work").

### Human Verification Required

None. All three previously-identified gaps were closed with objectively reproducible evidence (direct code inspection of the guard conditions, live execution of the floored-growth DCF call, isolated-subprocess reproduction of the pre-fix KeyError, and a structural YAML assertion). No new items require human judgment. The one human-check called out in 07-04-PLAN.md Task 3 (visually diffing the two `env:` blocks) was independently satisfied by direct reading of both step definitions — key-for-key match confirmed.

### Gaps Summary

All three gaps from the prior verification pass are closed and independently re-confirmed against the actual codebase (not SUMMARY.md claims):

1. **Piotroski F5 inverted fail-safe (CR-02) — CLOSED.** stock_screener.py:1241-1247 now guards `long_term_debt_curr is not None` in the F5 if-condition, removing the inline default-to-0, exactly mirroring F6/F8. Verified by direct read and a passing regression test that isolates the missing-current-year-LTD case.

2. **DCF growth rate unbounded + missing D-10 cyclical flag (CR-03) — CLOSED.** `DCF_GROWTH_FLOOR = -50.0` is applied at the DCF call site (`g_dcf = max(g, DCF_GROWTH_FLOOR)`), confirmed to turn a previously-reproduced negative intrinsic (-0.62) into a positive one (1.65) for the same -150% growth input. `CYCLICAL_SECTORS = {"Energy", "Basic Materials"}` and `DCF_Cyclical_Flag` are implemented with correct boolean logic (never True for `sector=None`, only True when DCF was actually computed for a cyclical sector).

3. **Monthly snapshot workflow step missing env: block (CR-01) — CLOSED.** The "Commit monthly snapshot" step now carries the same `FRED_API_KEY`/`FINNHUB_API_KEY` env block as the working "Run screener" step. The underlying failure mode (module-level `os.environ[...]` bracket access raising `KeyError` without these vars) was independently reproduced in a subprocess isolated from the repo's local `.env` masking, confirming the fix addresses a real, not hypothetical, CI crash.

All 5 roadmap success criteria are now verified. All 11 in-scope Phase 7 requirement IDs are satisfied (DATA-03 correctly remains deferred, not a gap). No regressions across the full 144-test, 6-suite Phase 5/6/7 regression run (independently re-executed here, not taken on SUMMARY.md's word). A small set of pre-existing, non-blocking Warning/Info items (WR-01, WR-03, WR-04, IN-02) remain from the original code review — none were in scope for this gap-closure cycle and none block phase completion.

Phase 7 goal is achieved. Ready to proceed.

---

*Verified: 2026-07-01T23:25:00Z*
*Verifier: Claude (gsd-verifier)*
