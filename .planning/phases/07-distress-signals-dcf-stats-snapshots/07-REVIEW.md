---
phase: 07-distress-signals-dcf-stats-snapshots
reviewed: 2026-06-30T22:40:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - stock_screener.py
  - requirements.txt
  - .gitignore
  - .github/workflows/screener.yml
  - docs/app.js
  - docs/history.html
  - docs/methodology.html
  - docs/stats.html
  - docs/top.html
  - tests/test_dcf_phase7.py
  - tests/test_distress_phase7.py
findings:
  critical: 3
  warning: 4
  info: 2
  total: 9
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-06-30T22:40:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Reviewed the Phase 7 additions to `stock_screener.py` (Piotroski F-Score, Altman Z'', forward/reverse DCF, the sector applicability gate, the rewritten Safety pillar, `process_ticker`'s new distress/DCF block, and `_compute_stats`), plus the supporting workflow, gitignore, tests, and new/updated dashboard pages (`stats.html`, `history.html`, `top.html`, `methodology.html`).

The unit tests are thorough for the "happy path" and documented edge cases, and pass. However, tracing the new code against the *undocumented* edge cases surfaced three BLOCKER-level defects:

1. The monthly-snapshot GitHub Actions step will crash every time it runs, because it imports `stock_screener` without the API-key env vars the module requires at import time — this silently breaks the entire History/snapshot feature that Phase 7 introduces.
2. The Piotroski F5 criterion has an asymmetric missing-data default that biases toward a false "leverage decreased" pass, inconsistent with the fail-safe pattern used by the two adjacent criteria (F6, F8) in the same function.
3. The reconciled growth rate fed into the new DCF helpers has no lower bound, so severely distressed companies (exactly Phase 7's target population) can produce mathematically nonsensical (sign-oscillating, potentially negative) DCF intrinsic values — which then score as a "deep value" BUY signal rather than being flagged as risky.

Several further WARNING-level robustness/dead-code issues were found in the DCF and Safety-pillar plumbing.

## Critical Issues

### CR-01: Monthly snapshot workflow step will crash — missing required env vars

**File:** `.github/workflows/screener.yml:55-69`
**Issue:**
`stock_screener.py` reads its API keys at *module import time* using dict-style bracket access (not `.get()`):
```python
FRED_API_KEY     = os.environ["FRED_API_KEY"]
FINNHUB_API_KEY  = os.environ["FINNHUB_API_KEY"]
```
This raises `KeyError` immediately if either variable is absent from the process environment.

The "Run screener" step (lines 28-32) correctly scopes these secrets via its own `env:` block. But the "Commit monthly snapshot" step (lines 55-69) invokes:
```bash
python -c "import stock_screener; stock_screener.update_snapshot_manifest('${SNAP_DATE}.json')"
```
with **no `env:` block at all**. GitHub Actions step-level `env:` is not inherited by later steps, so `FRED_API_KEY`/`FINNHUB_API_KEY` are unset in this step's shell. `import stock_screener` will raise `KeyError` before `update_snapshot_manifest` ever runs, failing the step on every first-weekday-of-month run. This means `docs/data/snapshots/index.json` is never created/updated in production, and `docs/history.html` (which depends on that manifest) will always show "No snapshots yet."

This will not be caught by local testing or by the existing test suite, because locally `.env` variables persist for the whole shell session and mask the bug — it is a CI-only failure mode.

**Fix:**
```yaml
      - name: Commit monthly snapshot
        if: steps.check-date.outputs.is_first_weekday == 'true'
        env:
          FRED_API_KEY:        ${{ secrets.FRED_API_KEY }}
          FINNHUB_API_KEY:     ${{ secrets.FINNHUB_API_KEY }}
        run: |
          ...
```

---

### CR-02: Piotroski F5 "leverage decreased" criterion has an inverted fail-safe default

**File:** `stock_screener.py:1230-1237`
**Issue:**
```python
# F5: Leverage decreased (long_term_debt / avg_total_assets) — skip if prev absent
if long_term_debt_prev is not None and total_assets_prev and total_assets_curr:
    criteria_counted += 1
    avg_assets = (total_assets_curr + total_assets_prev) / 2.0
    ltd_ratio_curr = (long_term_debt_curr / avg_assets) if long_term_debt_curr is not None else 0
    ltd_ratio_prev = long_term_debt_prev / total_assets_prev
    if ltd_ratio_curr < ltd_ratio_prev:
        score += 1
```
When `long_term_debt_curr` is missing (e.g. yfinance's label doesn't match `LONG_TERM_DEBT_LABELS` for that ticker — explicitly called out elsewhere in this file as `[ASSUMED — yfinance label names vary by ticker]`), `ltd_ratio_curr` defaults to `0`. Since `0` is almost always less than any positive prior-year ratio, the comparison `ltd_ratio_curr < ltd_ratio_prev` is then almost always **True**, silently awarding the "leverage decreased" point despite the data being absent, not actually zero.

This is the *opposite* fail-safe direction used by the two structurally identical criteria in the same function:
- F6 (`stock_screener.py:1240-1245`): `cr_curr = ... if current_assets_curr is not None else 0` — defaulting the numerator to 0 makes `cr_curr > cr_prev` **False**, correctly biasing toward FAIL when data is missing.
- F8 (`stock_screener.py:1253-1259`): same pattern, same correct fail-safe bias.

F5's comparison direction (`<` instead of `>`) means the identical "default missing numerator to 0" trick flips into a bias toward PASS. This silently inflates the Piotroski F-Score (and therefore the Safety pillar, per the Phase 7 Safety-pillar rewrite) whenever current-year long-term-debt data can't be located — with no logging or diagnostic signal that this happened.

**Fix:** Treat a missing `long_term_debt_curr` as a fail (don't award the point), matching F1/F2/F4's "missing → fail" convention:
```python
if long_term_debt_prev is not None and total_assets_prev and total_assets_curr and long_term_debt_curr is not None:
    criteria_counted += 1
    avg_assets = (total_assets_curr + total_assets_prev) / 2.0
    ltd_ratio_curr = long_term_debt_curr / avg_assets
    ltd_ratio_prev = long_term_debt_prev / total_assets_prev
    if ltd_ratio_curr < ltd_ratio_prev:
        score += 1
```

---

### CR-03: No lower bound on growth rate before DCF — distressed stocks can produce a false "deep value" BUY signal

**File:** `stock_screener.py:1362-1389` (`_compute_dcf_forward`), `stock_screener.py:2024-2037` (growth reconciliation), `stock_screener.py:2132-2137` (DCF call site)
**Issue:**
`g` is capped only on the *upper* bound before being passed into the DCF helpers:
```python
g = _reconcile_growth(fund["growth_pct"], compute_growth_5yr_cagr(fund["annual_eps"]))
...
g = min(g, GROWTH_CAP)   # upper cap only — no floor
...
if _sector_allows(fund, "dcf"):
    dcf_intrinsic, dcf_discount_pct = _compute_dcf_forward(eps, g, aaa_yield, price)
```
`_reconcile_growth` (`stock_screener.py:1721-1738`) takes `min(g_finnhub, g_cagr)`. `g_cagr` (from realized EPS history) is mathematically bounded above -100%, but `g_finnhub` (Finnhub's raw `epsGrowth5Y`) is an externally-sourced value with no such guarantee — for a company whose EPS collapsed deeply into negative territory, Finnhub can report growth below -100%. Since `_reconcile_growth` takes the *minimum* of the two, a sufficiently negative `g_finnhub` propagates straight through, unbounded, into `g`.

Inside `_compute_dcf_forward` (`stock_screener.py:1376-1387`):
```python
eps_t = eps
for t in range(1, 6):
    eps_t = eps_t * (1 + g)
    pv_stage1 += eps_t / (1 + wacc) ** t
...
tv = eps_t * (1 + g_terminal) / (wacc - g_terminal)
```
If `g < -100%`, `(1 + g)` is negative, so `eps_t` **alternates sign** each of the 5 projection years, and the resulting `intrinsic` value can itself be negative or otherwise nonsensical. There is no guard analogous to the `eps <= 0` check at the top of the function.

This is not merely a cosmetic display bug: a negative `intrinsic` combined with a positive `price` produces
`discount_pct = (1 - price/intrinsic) * 100` that is strongly **positive** (e.g. intrinsic=-50, price=80 → discount ≈ +260%). After winsorization in `overall_score()`'s `_score_dcf_discount` (`stock_screener.py:568-579`), this reads as a **deep DCF discount (score 90-100)** — i.e. exactly the population Phase 7 was built to flag as risky (companies with collapsing EPS) can instead surface as the *strongest* DCF buy signal, and `DCF_Intrinsic_Value` is written to `docs/data/results.json` and rendered on the dashboard as a plausible-looking (but meaningless, possibly negative) per-share value with no sanity check.

**Fix:** Clamp `g` to a sane floor before DCF calls (e.g. -99%, matching the intuition that a company can't shrink more than 100%/year), or add an explicit guard in `_compute_dcf_forward`/`_compute_dcf_reverse`:
```python
if eps is None or eps <= 0 or g_cagr_pct <= -100.0:
    return (None, None)
```

## Warnings

### WR-01: Unhandled `ValueError` from `_compute_dcf_forward` can crash the entire batch run

**File:** `stock_screener.py:2132-2137`
**Issue:** `_compute_dcf_forward` is documented to `raise ValueError` when `terminal_growth >= WACC` (`stock_screener.py:1369-1373`). `process_ticker` calls it directly with no `try/except`:
```python
if _sector_allows(fund, "dcf"):
    dcf_intrinsic, dcf_discount_pct = _compute_dcf_forward(eps, g, aaa_yield, price)
    dcf_implied_growth, dcf_reverse_converged = _compute_dcf_reverse(price, eps, aaa_yield, g)
```
Every other external-data failure mode in this file degrades gracefully (e.g. `get_finnhub_metrics` wraps its request in `try/except` and returns `{}}` on failure, `get_yf_price_and_history` wraps the whole yfinance fetch in `try/except`). This new Phase 7 path has no equivalent protection. `aaa_yield` is fetched once per run and shared across every ticker, so if the guard condition is ever met (e.g. an unusually low/negative AAA reading from FRED, or a future edit to `DCF_ERP`/`DCF_TERMINAL_GROWTH_CAP`), the exception propagates out of `run_screener`'s per-ticker loop and aborts the *entire* multi-hundred-ticker run, rather than failing just the offending ticker.
**Fix:**
```python
try:
    dcf_intrinsic, dcf_discount_pct = _compute_dcf_forward(eps, g, aaa_yield, price)
    dcf_implied_growth, dcf_reverse_converged = _compute_dcf_reverse(price, eps, aaa_yield, g)
except ValueError as e:
    log.error(f"{ticker}: DCF config error: {e}")
    dcf_intrinsic, dcf_discount_pct = None, None
    dcf_implied_growth, dcf_reverse_converged = None, False
```

### WR-02: `_compute_dcf_reverse`'s `g_stage1_pct` parameter is dead — never used

**File:** `stock_screener.py:1392-1442`
**Issue:** The function signature accepts `g_stage1_pct: float`, and both `process_ticker` (`stock_screener.py:2134`, passing `g`) and `tests/test_dcf_phase7.py` explicitly pass it, but it is never referenced anywhere in the function body. The solve is a pure function of `price`, `eps`, `aaa_yield_pct`, and the internal `[-50, 100]` bracket — `g_stage1_pct` has zero effect on the result. This is misleading: a maintainer reading the call site or the docstring would reasonably assume the reverse solve anchors on (or is influenced by) the realized growth rate, when it does not.
**Fix:** Remove the unused parameter from the signature (and update the two call sites/tests), or, if some anchoring behavior was intended, implement it.

### WR-03: `overall_score()`'s `coverage_fraction` parameter is orphaned after the Safety-pillar rewrite

**File:** `stock_screener.py:449`, `stock_screener.py:2104-2109`, `stock_screener.py:2155`
**Issue:** `coverage_fraction` is still computed via `trap_gate()` in `process_ticker` and threaded into `overall_score(coverage_fraction=cov_fraction, ...)`, but it is never referenced inside `overall_score()`'s body. The Phase 7 comment block at `stock_screener.py:633-643` explicitly notes that `SCORE_SAFETY_TRAP_PENALTY`/`SCORE_SAFETY_NOTRAP_BASE` are "retained... but no longer drive the Safety calculation," but doesn't mention that `coverage_fraction` — which previously multiplied `SCORE_SAFETY_NOTRAP_BASE` in the pre-Phase-7 design — is now equally dead. This is orphaned plumbing left over from the old trap-gate design.
**Fix:** Either drop `coverage_fraction` from `overall_score()`'s signature (and the `process_ticker` call site) or add an explicit comment next to the parameter noting it is vestigial/unused, kept only for call-site compatibility.

### WR-04: `_compute_piotroski`'s raw score is not rescaled when comparison criteria are skipped, and contradicts its own docstring for F1

**File:** `stock_screener.py:1124-1271`
**Issue:** The docstring states: *"Missing single-year input → criterion fails (contributes 0)"* and *"Missing prior-year input for a comparison criterion → criterion skipped (not counted)."* `criteria_counted` is tracked precisely to reflect this, but it is **never used** to rescale the returned `score` — `_compute_piotroski` always returns a raw count out of a theoretical 9, regardless of how many criteria were actually evaluable. `SCORE_PIOTROSKI_BANDS` (`stock_screener.py:286-292`) then maps this raw score assuming a full 0-9 scale. For a ticker with only 2 years of statement history (comparison criteria F3/F5-F9 all skipped), the maximum achievable score is 3 — which lands in the "distressed" (0-2 → 0-20) or "weak" (2-4 → 20-40) band even if the company passed every evaluable criterion, systematically penalizing thin-history tickers (e.g. recent IPOs) rather than routing them to the D-04 neutral-50 "absent" path the way sector-excluded/fully-missing tickers are handled elsewhere.

Separately, F1 (`stock_screener.py:1195-1202`) doesn't actually honor the "missing single-year input → fails" contract: when `net_income_curr` is `None` entirely, *neither* branch fires, so F1 contributes to neither `score` nor `criteria_counted` (silently skipped, not failed) — inconsistent with F2's unconditional `else: criteria_counted += 1` fail-on-missing pattern three lines later.
**Fix:** Either return `None` (routing to the D-04 neutral-50 path) when `criteria_counted` falls below a minimum threshold (e.g. < 9, or < 5), or rescale: `return round(score / criteria_counted * 9)`. Also align F1's missing-data branch with F2/F4's explicit "count as evaluated, fail" pattern.

## Info

### IN-01: `coverage_pct` always treats Piotroski/Altman as "present," inflating the user-facing "Avg Coverage %" metric

**File:** `stock_screener.py:676-687`, `docs/stats.html:131`
**Issue:** Per the D-04 design (explicitly documented as intentional in-code), `piotroski_sub`/`altman_sub` always return a float (50.0 when the underlying data is absent or the sector is excluded), so `coverage_pct`'s `all_sub_scores` list always counts these 2 of 17 leaves as "present" — even for a ticker with zero real distress data (e.g. a Financial Services stock excluded from Altman with no Piotroski statements available). This is a reasonable scoring-neutrality design choice, but it means the "Avg Coverage %" figure surfaced on `stats.html` (`docs/stats.html:131`, labeled without qualification as a general data-completeness metric) is not a faithful measure of actual data completeness for those two leaves — it will read a few percentage points higher than the ticker's true distress-data coverage.
**Fix:** No code change required; consider a footnote on `stats.html` clarifying that Piotroski/Altman always count as "covered" due to the neutral-50 fallback, to avoid misleading interpretation of the coverage metric.

### IN-02: Redundant `.gitignore` negation pattern for snapshot manifest

**File:** `.gitignore:7-8`
**Issue:** `!docs/data/snapshots/*.json` (line 7) already un-ignores `docs/data/snapshots/index.json`; the separate `!docs/data/snapshots/index.json` (line 8) is fully redundant.
**Fix:** Remove line 8 (cosmetic only — no functional impact).

---

_Reviewed: 2026-06-30T22:40:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
