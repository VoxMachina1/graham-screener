---
phase: 07-distress-signals-dcf-stats-snapshots
verified: 2026-06-30T22:50:00Z
status: gaps_found
score: 2/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "Piotroski F-Score and Altman Z'' are computed per ticker and replace/augment the interim gate as the Safety-pillar driver"
    status: partial
    reason: "is_trap is structurally removed from overall_score()'s signature and Safety is now driven by Piotroski+Altman+defensive/de/cr (17-leaf coverage) as designed. However, the Piotroski F5 criterion ('leverage decreased') has an inverted fail-safe default: when long_term_debt_curr cannot be located (a known, common yfinance label-mismatch case called out elsewhere in the same file), the code defaults the numerator to 0, which makes the '<' comparison against the prior-year ratio almost always True — silently AWARDING the point instead of failing it. This is the opposite of the fail-safe direction used by the two structurally identical criteria (F6, F8) three lines away in the same function. This inflates the Piotroski F-Score (and therefore the Safety pillar) on missing data with no diagnostic signal. Confirmed by direct code inspection of stock_screener.py:1230-1237 — unfixed as of HEAD (574ee13)."
    artifacts:
      - path: "stock_screener.py"
        issue: "Lines 1230-1237 (_compute_piotroski, F5 criterion): `ltd_ratio_curr = (long_term_debt_curr / avg_assets) if long_term_debt_curr is not None else 0` combined with `if ltd_ratio_curr < ltd_ratio_prev: score += 1` biases toward a false PASS on missing current-year long-term-debt data."
    missing:
      - "Guard long_term_debt_curr is not None in the F5 if-condition (matching F1/F2/F4's 'missing -> fail, still counted' convention) instead of defaulting the ratio to 0."
  - truth: "Forward two-stage DCF intrinsic value + discount % appear per ticker, sector-guarded (financials excluded, cyclicals flagged), asserting terminal-growth < discount-rate, with the bounded reverse solver emitting None on non-convergence — never a silent default"
    status: failed
    reason: "Two independent defects verified: (1) The reconciled growth rate 'g' fed into _compute_dcf_forward has no lower bound (only `g = min(g, GROWTH_CAP)` — upper cap only). Reproduced live: _compute_dcf_forward(eps=2.0, g_cagr_pct=-150.0, aaa_yield_pct=5.0, price=10.0) returns intrinsic=-0.62 (negative, nonsensical) and discount_pct=1705% — which after winsorization scores as the strongest possible 'deep value' DCF signal for exactly the distressed-EPS population Phase 7 was built to flag as risky. (2) The 'cyclicals flagged' half of the sector guard (D-10: Energy/Materials get DCF with a visible [CYCLICAL] coverage flag) was never implemented anywhere in the codebase — grep for DCF_Cyclical_Flag/Cyclical_Flag across *.py/*.html/*.js returns zero matches, despite being explicitly specified in 07-CONTEXT.md D-10 and 07-RESEARCH.md Pitfall 7. The bounded reverse solver's None-on-non-convergence behavior IS correctly implemented and tested (test_dcf_reverse_no_root_returns_none_false passes), and the terminal<WACC assert IS correctly implemented and tested — those two sub-parts of this truth are fine."
    artifacts:
      - path: "stock_screener.py"
        issue: "Lines 2024-2025 (`g = min(g, GROWTH_CAP)`) and line 2132 (DCF forward call site) — no floor on g before it reaches _compute_dcf_forward/_compute_dcf_reverse; _compute_dcf_forward (~1362-1389) has no eps/g sanity guard analogous to its eps<=0 guard."
      - path: "stock_screener.py / docs/methodology.html / docs/top.html"
        issue: "No DCF_Cyclical_Flag field, column, or UI indicator exists anywhere for Energy/Materials sectors, despite D-10 explicitly requiring it."
    missing:
      - "Clamp g to a sane floor (e.g. -99%) before DCF calls, or add an explicit guard in _compute_dcf_forward/_compute_dcf_reverse rejecting g_cagr_pct <= -100.0."
      - "Implement the cyclical-sector coverage flag (Energy/Materials -> DCF_Cyclical_Flag=True) and surface it somewhere the user can see (row column and/or UI badge), per D-10."
  - truth: "The Actions workflow commits periodic (monthly, first-weekday) snapshots of results.json under docs/data/snapshots/ (with the .gitignore exception and the reused min-row guard)"
    status: failed
    reason: "The .gitignore exceptions, snapshot-copy logic, manifest writer, and first-weekday detection are all structurally present and correct. However, the 'Commit monthly snapshot' step in .github/workflows/screener.yml (lines 61-69) invokes `python -c \"import stock_screener; ...\"` with NO env: block. stock_screener.py reads FRED_API_KEY/FINNHUB_API_KEY at module import time via `os.environ[\"...\"]` (bracket access, not .get()), which raises KeyError immediately if the variable is absent. GitHub Actions step-level env: is not inherited by later steps, so this step's shell will not have these variables set in production CI. Reproduced live in an isolated subprocess (no .env file, no env vars): `import stock_screener` raised `KeyError: 'FRED_API_KEY'` with exit code 1. This means the monthly snapshot step will crash on every first-weekday-of-month CI run; docs/data/snapshots/index.json will never be created/updated in production, and history.html will always show 'No snapshots yet.' The bug is invisible locally because .env persists for the whole local shell session (load_dotenv() masks it), which is exactly why the code review flagged it as a CI-only failure mode."
    artifacts:
      - path: ".github/workflows/screener.yml"
        issue: "Lines 61-69 ('Commit monthly snapshot' step) has no env: block providing FRED_API_KEY/FINNHUB_API_KEY, so `python -c \"import stock_screener; ...\"` crashes with KeyError before update_snapshot_manifest ever runs."
    missing:
      - "Add an env: block to the 'Commit monthly snapshot' step providing FRED_API_KEY and FINNHUB_API_KEY from secrets, mirroring the 'Run screener' step's env: block."
deferred:
  - truth: "DATA-03 (30-day fundamentals cache)"
    addressed_in: "Future phase (explicitly out of scope for Phase 7)"
    evidence: "07-CONTEXT.md 'Out of scope (defer)' and 'Claude's Discretion' sections explicitly defer DATA-03 per user decision; REQUIREMENTS.md correctly lists it as '[ ] (Optional)' / 'Pending'. Not flagged as a gap per verification instructions."
---

# Phase 7: Distress Signals, DCF, Stats & Snapshots Verification Report

**Phase Goal:** Piotroski F-Score and Altman Z'' upgrade the interim trap-gate into the real Safety-pillar driver; forward + reverse DCF give per-stock intrinsic value and an expectations gap; a per-metric sector applicability matrix keeps sector-invalid signals out of the score; stats.html plus committed historic snapshots make the universe observable and comparable over time.

**Verified:** 2026-06-30T22:50:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Piotroski F-Score (0-9) and Altman Z'' computed per ticker, replace/augment interim gate as Safety-pillar driver | ⚠️ PARTIAL / FAILED | `is_trap` correctly removed from `overall_score()` signature (confirmed: signature ends `piotroski_f=None, altman_z=None, dcf_discount_pct=None`, no `is_trap` param). BUT Piotroski F5 criterion has a verified, reproduced-by-inspection inverted fail-safe (stock_screener.py:1230-1237) that silently inflates the F-Score — and therefore Safety — on missing current-year long-term-debt data. |
| 2 | Forward + reverse DCF, sector-guarded (financials excluded, cyclicals flagged), terminal<discount assert, bounded solver -> None never silent default | ✗ FAILED | Terminal<WACC assert and bounded-solver-emits-None behavior both correctly implemented and unit-tested. BUT (a) growth rate `g` has no lower bound before DCF calls — reproduced live: g=-150% produces a negative intrinsic value (-0.62) and a 1705% discount_pct, which scores as a false "deep value" BUY for a collapsing-EPS company; (b) the "cyclicals flagged" requirement (D-10, `DCF_Cyclical_Flag` for Energy/Materials) was never implemented anywhere — zero matches in the codebase. |
| 3 | Per-metric sector applicability matrix; invalid signals treated as missing, never zero | ✓ VERIFIED | `_sector_allows(fund, metric)` (stock_screener.py:310+) correctly gates dcf/altman/earnings_yield/ev_ebit by sector; Financial Services excludes altman+dcf+earnings_yield+ev_ebit, Real Estate excludes dcf only, unknown sector excludes nothing. 6 dedicated unit tests pass (`test_sector_allows_*`). All exclusions route to `None`, never `0`, confirmed at call sites (stock_screener.py:2130-2141). |
| 4 | docs/stats.html presents universe overview; methodology.html documents new signals/scoring/sector guards | ✓ VERIFIED | stats.html (161 lines) fetches `data/stats.json` cache-busted, renders score_distribution (5 buckets), pillar_averages, sector_breakdown table, coverage_stats table — no charting library. methodology.html contains substantive new sections (Piotroski F-Score, Altman Z'', two-stage DCF forward/reverse, sector applicability matrix table) while retaining prior Lynch/Graham content. Human-verify checkpoint (07-03 Task 4) was approved by the user for visual rendering. |
| 5 | Actions workflow commits periodic monthly (first-weekday) snapshots under docs/data/snapshots/, reusing min-row guard; DATA-03 correctly deferred | ✗ FAILED | `.gitignore` exceptions present and correct. Snapshot copy/manifest/first-weekday-detection logic all structurally correct. BUT the "Commit monthly snapshot" step (screener.yml:61-69) has no `env:` block; `stock_screener.py` reads `os.environ["FRED_API_KEY"]`/`["FINNHUB_API_KEY"]` at import time (bracket access, raises KeyError if absent). Reproduced live in an isolated subprocess with no `.env` and no env vars: `import stock_screener` → `KeyError: 'FRED_API_KEY'`, exit code 1. This step will crash every month in production CI, so snapshots will never actually land. DATA-03 deferral correctly honored (not flagged as a gap). |

**Score:** 2/5 truths verified (Truth 3 and Truth 4 fully pass; Truths 1, 2, 5 have verified, reproducible defects)

### Deferred Items

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | DATA-03 (30-day fundamentals cache) | Future phase (explicit out-of-scope) | 07-CONTEXT.md explicitly defers DATA-03 per user decision; REQUIREMENTS.md marks it `[ ]`/Pending correctly. Per verification instructions, its absence is NOT a gap. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `stock_screener.py::_compute_piotroski` | 0-9 F-Score pure helper | ✓ EXISTS, ✗ CORRECTNESS DEFECT | F5 inverted fail-safe (see gap 1) |
| `stock_screener.py::_compute_altman_z` | Z'' pure helper | ✓ VERIFIED | Formula matches spec; tested |
| `stock_screener.py::_compute_dcf_forward` | Forward DCF | ✓ EXISTS, ✗ CORRECTNESS DEFECT | No growth floor (see gap 2) |
| `stock_screener.py::_compute_dcf_reverse` | Reverse DCF via brentq | ✓ VERIFIED | Bounded, tested, correct None-on-no-root behavior |
| `stock_screener.py::_sector_allows` | Sector applicability gate | ✓ VERIFIED | Wired and tested |
| `docs/data/stats.json` (via `_compute_stats`) | Universe overview JSON | ✓ VERIFIED | Schema matches SUMMARY; write_json calls it |
| `docs/stats.html` | Universe overview page | ✓ VERIFIED | Substantive, no charting lib |
| `docs/history.html` | Snapshot list page | ✓ VERIFIED | Fetches manifest, graceful empty state |
| `.github/workflows/screener.yml` snapshot step | Monthly commit step | ✓ STRUCTURALLY EXISTS, ✗ RUNTIME CRASH | Missing `env:` block (see gap 3) |
| `docs/methodology.html` | Updated methodology | ✓ VERIFIED | New sections present, prior content retained |
| DCF cyclical flag | `[CYCLICAL]` coverage flag for Energy/Materials | ✗ MISSING | Zero occurrences anywhere in codebase |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `process_ticker()` | `overall_score(piotroski_f=, altman_z=, dcf_discount_pct=)` | kwarg pass | ✓ WIRED | Confirmed at stock_screener.py call site |
| `write_json()` | `docs/data/stats.json` | `_compute_stats(df)` + write_text | ✓ WIRED | Confirmed |
| `docs/stats.html` | `docs/data/stats.json` | cache-busted fetch | ✓ WIRED | Confirmed |
| `docs/history.html` | `docs/data/snapshots/index.json` | manifest fetch | ✓ WIRED | Confirmed |
| `screener.yml` "Commit monthly snapshot" step | `stock_screener.update_snapshot_manifest()` | `python -c "import stock_screener; ..."` | ✗ NOT WIRED (crashes) | No env: block — KeyError on import, reproduced live |
| `process_ticker()` growth `g` | `_compute_dcf_forward(eps, g, ...)` | direct pass, no floor | ✗ PARTIAL (unsafe) | Reproduced sign-flip/negative-intrinsic defect |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `import stock_screener` fails without env vars (as in the unguarded CI step) | Isolated subprocess, no `.env`, no `FRED_API_KEY`/`FINNHUB_API_KEY` | `KeyError: 'FRED_API_KEY'`, exit 1 | ✓ CONFIRMS GAP 3 |
| Severely negative growth produces nonsensical DCF intrinsic value | `_compute_dcf_forward(eps=2.0, g_cagr_pct=-150.0, aaa_yield_pct=5.0, price=10.0)` | `intrinsic=-0.62, discount_pct=1705%` | ✓ CONFIRMS GAP 2 |
| `tests/test_distress_phase7.py` full suite | `python tests/test_distress_phase7.py` | 38 passed, 0 failed | ✓ PASS (does not cover the undocumented edge cases above) |
| `tests/test_dcf_phase7.py` full suite | `python tests/test_dcf_phase7.py` | 14 passed, 0 failed | ✓ PASS (does not cover the growth-floor edge case) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SIGNAL-08 | 07-01, 07-02 | Piotroski F-Score (0-9) | ⚠️ BLOCKED (defect) | F5 inverted fail-safe inflates score on missing data |
| SIGNAL-09 | 07-01, 07-02 | Altman Z'' with distress zones | ✓ SATISFIED | No defects found |
| TRAP-03 | 07-02, 07-03 | Piotroski/Altman replace interim gate as Safety driver | ⚠️ BLOCKED (defect) | Structurally correct, but SIGNAL-08 defect flows into Safety |
| DCF-01 | 07-01, 07-02 | Forward two-stage DCF intrinsic value + discount % | ✗ BLOCKED | Unbounded growth rate produces nonsensical values for distressed stocks |
| DCF-02 | 07-01, 07-02 | Reverse DCF implied-growth gap | ✓ SATISFIED | Bounded solver correct and tested; reverse solve does not consume the unbounded g directly (dead param per review WR-02) |
| DCF-03 | 07-01, 07-02 | Sector-guarded, terminal<discount assert, bounded solver -> None | ✗ BLOCKED | Cyclical flag never implemented; assert + bounded-solver sub-parts are correct |
| SECTOR-02 | 07-02 | Per-metric sector applicability matrix | ✓ SATISFIED | `_sector_allows` verified and tested. Note: REQUIREMENTS.md checkbox is stale (`[ ]`/"Pending") despite the feature being implemented — documentation staleness, not a functional gap. |
| PAGE-02 | 07-02, 07-03 | docs/stats.html universe overview | ✓ SATISFIED | Verified substantive |
| DATA-01 | 07-03 | Periodic snapshots under docs/data/snapshots/ | ✗ BLOCKED | Workflow step crashes before ever committing a snapshot in CI |
| DATA-02 | 07-03 | Snapshot step reuses min-row guard; vintage caveat documented | ✗ BLOCKED | Moot — the step never runs successfully due to DATA-01's blocker; vintage caveat text itself is present in history.html |
| DATA-03 | (none — explicitly deferred) | 30-day fundamentals cache | — DEFERRED | Correctly out of scope per 07-CONTEXT.md; not a gap |
| METH-01 | 07-03 | methodology.html documents new signals/scoring/guards | ✓ SATISFIED | Verified substantive, prior content retained |

**Orphaned requirements:** None. All 11 in-scope requirement IDs from the phase requirement list (excluding the explicitly-deferred DATA-03) are claimed by at least one plan's frontmatter `requirements:` field.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `.github/workflows/screener.yml` | 61-69 | Missing `env:` block on a step that imports a module requiring env vars at import time | 🛑 Blocker | Monthly snapshot step crashes every run in CI (Gap 3) |
| `stock_screener.py` | 1230-1237 | Inverted fail-safe default (missing-data biases toward PASS instead of FAIL) | 🛑 Blocker | Silently inflates Piotroski F-Score / Safety pillar (Gap 1) |
| `stock_screener.py` | 2024-2025, 1362-1389, 2132-2137 | No lower bound / guard on growth rate before feeding a formula with `(1+g)^n` | 🛑 Blocker | Sign-flip / negative intrinsic values scored as false "deep value" BUY signals (Gap 2) |
| `stock_screener.py` | 2132-2137 | Unguarded call to a function documented to `raise ValueError` | ⚠️ Warning | An unusual AAA-yield reading or a future config edit could abort the entire multi-hundred-ticker batch run (review WR-01, not independently reproduced here but code-confirmed) |
| `stock_screener.py` | 1392-1442 | `g_stage1_pct` parameter accepted but never used in `_compute_dcf_reverse` | ⚠️ Warning | Misleading signature; no functional impact (review WR-02, confirmed by reading the function body) |
| `stock_screener.py` | 449, 2104-2109, 2155 | `coverage_fraction` param threaded through but unused inside `overall_score()` after the Safety rewrite | ℹ️ Info | Orphaned plumbing, no functional impact (review WR-03) |
| `stock_screener.py` | 1124-1271 | Raw Piotroski score not rescaled when `criteria_counted < 9`; F1 silently skipped (not failed) when `net_income_curr` is entirely absent | ⚠️ Warning | Thin-history tickers may be penalized vs. the documented contract (review WR-04) |
| `.gitignore` | 7-8 | Redundant negation pattern for `docs/data/snapshots/index.json` | ℹ️ Info | Cosmetic only |

Debt-marker scan (`TBD`/`FIXME`/`XXX`) on files modified this phase: none found.

### Human Verification Required

None additional. The one human-verify checkpoint required by this phase's plans (07-03 Task 4, frontend rendering) was already completed and approved during execution — re-verification here confirmed the underlying artifacts (stats.html, history.html, top.html, methodology.html) are still substantively present and correctly wired. No new items require human judgment; all outstanding gaps are objectively reproducible via code inspection and live execution.

### Gaps Summary

Three of the five roadmap success criteria have verified, reproducible defects that the 07-REVIEW.md code review (committed 574ee13) correctly identified as Critical/blocker-severity, and none of them have been fixed since that review:

1. **Piotroski F5 inverted fail-safe** (stock_screener.py:1230-1237) silently inflates the F-Score — and therefore the Safety pillar — whenever current-year long-term-debt data can't be located, which directly undermines Success Criterion 1's claim that Piotroski is a reliable "Safety-pillar driver."

2. **DCF growth rate has no lower bound** (stock_screener.py:2024-2025, 1362-1389, 2132-2137). Reproduced live: a -150% growth input produces a negative, meaningless intrinsic value that scores as the single strongest "deep value" BUY signal — the exact opposite of Phase 7's stated purpose of flagging distressed stocks as risky. Additionally, the "cyclicals flagged" half of Success Criterion 2's sector guard (D-10's `[CYCLICAL]` coverage flag for Energy/Materials) was never implemented anywhere in the codebase.

3. **Monthly snapshot workflow step crashes on every run** (.github/workflows/screener.yml:61-69) because it lacks the `env:` block providing FRED_API_KEY/FINNHUB_API_KEY that `stock_screener.py`'s module-level `os.environ[...]` access requires. Reproduced live: importing the module without these env vars set raises `KeyError` and exits non-zero. This means Success Criterion 5 (committed periodic snapshots) is not actually achievable as shipped — the workflow YAML has the right shape, but will never successfully commit a snapshot in production CI.

Success Criteria 3 (sector applicability matrix) and 4 (stats.html + methodology.html) are fully and correctly implemented with no defects found.

These three gaps directly mirror 07-REVIEW.md's CR-01/CR-02/CR-03 findings — the review was accurate and none of its Critical findings have been addressed since it was written. Recommend routing back through `/gsd-plan-phase 07 --gaps` for a closure plan targeting these three specific fixes (all three are small, localized, well-understood changes per the review's suggested fixes) before considering Phase 7 complete.

---

*Verified: 2026-06-30T22:50:00Z*
*Verifier: Claude (gsd-verifier)*
