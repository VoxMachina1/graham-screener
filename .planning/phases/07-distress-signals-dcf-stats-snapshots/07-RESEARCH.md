# Phase 7: Distress Signals, DCF, Stats & Snapshots — Research

**Researched:** 2026-06-28
**Domain:** Python financial computation — Piotroski F-Score, Altman Z'', two-stage DCF, GitHub Actions scheduling, vanilla JS stats page
**Confidence:** HIGH (codebase verified directly; external claims tagged)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01** — Drop is_trap gate entirely. Piotroski + Altman are scored Safety sub-scores (no binary veto).
- **D-02** — Piotroski F-Score (0–9) → piecewise Safety sub-score. Absent → 50.0.
- **D-03** — Altman Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4. Distress < 1.1 → 0; safe > 2.6 → high. Absent → 50.0.
- **D-04** — Absent Safety inputs (Piotroski + Altman specifically) → neutral 50.0, not average-over-present. Defensive, debt_equity, current_ratio retain D-01b average-over-present.
- **D-05** — Replace trap badge on top.html with a Safety pillar score chip.
- **D-06** — WACC = live FRED AAA yield + 5.5% equity risk premium (config-overridable `DCF_ERP = 5.5`). Assert terminal_growth < WACC at compute time.
- **D-07** — Two-stage DCF: 5-year high-growth stage (realized 5yr EPS CAGR) + terminal value (Gordon Growth Model).
- **D-08** — Terminal growth = min(realized_5yr_cagr, 3.0%). Config constant `DCF_TERMINAL_GROWTH_CAP = 3.0`.
- **D-09** — Reverse DCF non-convergence → None + `dcf_reverse_converged=False` sentinel. Never a silent default.
- **D-10** — Financial Services + Real Estate excluded from DCF.
- **D-11** — Sector applicability matrix: Financial Services excluded from DCF, EV/EBIT, Altman Z''. Real Estate excluded from DCF. Invalid metric → None, never zero.
- **D-12** — Monthly snapshots on first weekday of each month. Actions workflow detects date and conditionally commits to `docs/data/snapshots/YYYY-MM-DD.json`.
- **D-13** — Simple `docs/history.html` snapshot list page, 5th nav link. Dead-simple: dated list/table + download links. Fetches a manifest JSON.
- **D-14** — stats.html: stat cards + simple tables. 5-bucket score distribution. No charting library.
- **D-15** — stats.json computed in Python, written by screener. stats.html fetches and renders it. Cache-busted.

### Claude's Discretion

- Exact Piotroski 9-criterion variable implementation
- Altman Z'' variable definitions and distress-zone thresholds (1.1 / 2.6) as loud `[ASSUMED]` config constants
- Equity risk premium constant default (5.5%) as loud `[ASSUMED]` config entry `DCF_ERP`
- stats.json schema and exact field names
- history.html page design details
- methodology.html update scope (add Piotroski, Altman Z'', DCF, sector matrix sections; retain all existing content)

### Deferred Ideas (OUT OF SCOPE)

- DATA-03 (30-day fundamentals cache) — defer entirely
- Archive-browsing UI with date picker
- Threshold re-tuning (calibrate bands after observing distribution in stats.html)
- Backtest harness
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SIGNAL-08 | Piotroski F-Score (0–9) from 2yr financial statements | §Piotroski section: yfinance fields, 9-criterion map, two-year pattern |
| SIGNAL-09 | Altman Z-Score (Z'' variant) with distress zones | §Altman section: X1–X4 field mapping, distress-zone thresholds |
| TRAP-03 | Altman Z + Piotroski upgrade interim gate as Safety pillar driver | §Safety Pillar Restructure: how is_trap is retired and the new sub-score architecture replaces it |
| DCF-01 | Forward two-stage DCF intrinsic value + discount % | §DCF section: EPS-FCF proxy, two-stage formula, WACC derivation |
| DCF-02 | Reverse DCF implied-vs-actual-growth gap | §Reverse DCF section: scipy.optimize.brentq, bounds, non-convergence handling |
| DCF-03 | Sector-guarded DCF; terminal-g < discount-rate assert; bounded solver → None | §DCF sector guard, §Config constants |
| SECTOR-02 | Per-metric sector applicability matrix; invalid = missing, never zero | §Sector Applicability Matrix section |
| PAGE-02 | docs/stats.html universe overview | §stats.json schema, §stats.html implementation |
| DATA-01 | Periodic snapshots under docs/data/snapshots/ + .gitignore exception | §Snapshot workflow section |
| DATA-02 | Snapshot reuses min-row guard; data-vintage caveat documented | §Snapshot workflow section |
| METH-01 | methodology.html updated with new signals, scoring, thresholds, guards | §methodology.html section |
</phase_requirements>

---

## Summary

Phase 7 is the heaviest computation phase in the project. It lands three new sub-systems on top of the existing `overall_score()` architecture: (1) distress signals — Piotroski F-Score and Altman Z'' computed from yfinance financial statements, folded into the Safety pillar as scored sub-scores; (2) forward + reverse two-stage DCF giving per-stock intrinsic value and an expectations gap, sector-guarded and solver-bounded; and (3) three new outputs — a `stats.json` computed by Python, a `stats.html` universe overview page, and a `docs/history.html` snapshot list page with a monthly snapshot workflow in GitHub Actions.

The codebase is well-prepared for this phase. The `_compute_*` pure-helper pattern from Phase 6 provides the structural template. The yfinance `Ticker` object is already fetching `income_stmt`, `cashflow`, and `balance_sheet` in `get_yf_price_and_history()` — Piotroski and Altman need two years of those statements, which requires only a minor change from the current single-year read. The FRED AAA yield is already fetched and passed through the pipeline — WACC reuses it directly. The `overall_score()` signature extension pattern (adding None-defaulted params) is the same as Phase 6. The `NAV_ENTRIES` array in `app.js` already has a comment placeholder for Stats; History needs one more entry.

The main planning risks are: (a) yfinance statement column names are inconsistent across tickers and must be covered by candidate-label lists; (b) the reverse DCF solver requires careful bounding to avoid spurious convergence; (c) `is_trap` is currently threaded to `overall_score()` and `write_json()` — retiring it touches three sites plus `top.html`; and (d) the first-weekday-of-month logic in GitHub Actions requires a shell date calculation, not just cron.

**Primary recommendation:** Follow the Phase 6 decomposition pattern exactly — add `_compute_piotroski()`, `_compute_altman_z()`, `_compute_dcf_forward()`, `_compute_dcf_reverse()` as pure helpers; extend `get_yf_price_and_history()` to return two years of statement data; extend `overall_score()` with new None-defaulted params; extend `process_ticker()` and `write_json()` additively; add the snapshot step to `screener.yml`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Piotroski F-Score computation | Python (stock_screener.py) | — | Pure numeric transform on yfinance statement data; no I/O at compute time |
| Altman Z'' computation | Python (stock_screener.py) | — | Same pattern as Piotroski; all inputs from balance sheet / income stmt |
| Forward DCF intrinsic value | Python (stock_screener.py) | — | Requires live FRED AAA yield (already in scope); no new HTTP calls |
| Reverse DCF solver | Python (stock_screener.py) | — | scipy.optimize.brentq is a pure numeric solver; no side effects |
| Sector applicability matrix | Python (stock_screener.py) | — | Gate applied in `process_ticker()` before passing to `overall_score()` |
| Safety pillar sub-scores | Python (stock_screener.py) `overall_score()` | — | Extends existing pillar architecture; Piotroski + Altman join defensive/de/cr |
| stats.json computation | Python (stock_screener.py) `write_json()` or standalone | — | All stats derivable from the final DataFrame; computed once at write time |
| Monthly snapshot commit | GitHub Actions (screener.yml) | — | Conditional shell logic; Python only writes the file, Actions commits it |
| stats.html rendering | Browser (static JS) | — | Fetches stats.json, no server-side computation; consistent with no-build-step constraint |
| history.html rendering | Browser (static JS) | — | Fetches snapshots/index.json manifest; same no-build pattern |
| Safety chip on top.html | Browser (static JS) | — | Replaces is_trap badge; reads `scores.safety` from results.json |
| Nav update (Stats + History) | Browser (app.js NAV_ENTRIES) | All pages | One-line additions to existing array-driven nav; all pages re-render from it |

---

## Standard Stack

### Core (all already in requirements.txt or stdlib)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yfinance | >=0.2.40 | Two-year statement fetch (income_stmt, balance_sheet, cashflow) | Already used; Phase 6 confirms t.income_stmt / t.balance_sheet / t.cashflow available |
| scipy | 1.15.3 (installed) | `scipy.optimize.brentq` for reverse DCF root-finding | Only numerically robust bounded solver available without adding a dependency; already installed [VERIFIED: installed locally] |
| fredapi | >=0.5.1 | FRED AAA yield for WACC | Already used in `fetch_aaa_yield()`; no new code needed |
| pandas | >=2.0.0 | DataFrame manipulation for stats computation | Already used throughout |

### No New Dependencies

Phase 7 adds **zero** new pip packages. All required capabilities are covered:
- Piotroski / Altman: yfinance statements (already fetched) + arithmetic
- DCF: stdlib math + scipy.optimize.brentq (already installed)
- stats.json: pandas aggregations on the final DataFrame
- history.html / stats.html: vanilla JS (consistent with no-build-step constraint)

**Installation:** none required.

**Version verification:** scipy 1.15.3 confirmed installed via `python -c "import scipy; print(scipy.__version__)"` [VERIFIED: installed locally].

---

## Package Legitimacy Audit

No new packages are introduced in Phase 7. scipy is already installed and is a well-established scientific computing library maintained by the scipy community [VERIFIED: installed locally]. No legitimacy audit needed.

| Package | Registry | Status | Disposition |
|---------|----------|--------|-------------|
| scipy | PyPI | Already installed (1.15.3); not a new dependency | Approved — no new install |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
yfinance Ticker (one object per ticker)
  ├── income_stmt  (newest + prior year)  ──► _compute_piotroski()
  ├── balance_sheet (newest + prior year) ──► _compute_piotroski()
  │                                       ──► _compute_altman_z()
  └── cashflow     (newest year)          ──► [already in Phase 6]

FRED AAA yield (already fetched, passed through)
  └──────────────────────────────────────► _compute_dcf_forward(wacc = aaa + DCF_ERP)
                                         ► _compute_dcf_reverse(scipy.optimize.brentq)

Sector string (fund["sector"], Phase 6)
  └──► sector_applicability_gate()
         ├── Financial Services → exclude DCF, Altman, EV/EBIT
         └── Real Estate        → exclude DCF

process_ticker()
  ├── calls _compute_piotroski(inc_curr, inc_prev, bs_curr, bs_prev, cf_curr, cf_prev)
  │         → piotroski_f (int 0–9) | None
  ├── calls _compute_altman_z(bs, inc)
  │         → altman_z (float) | None
  ├── applies sector gate → None if sector excludes signal
  ├── calls _compute_dcf_forward(eps, g_cagr, aaa_yield)
  │         → (dcf_intrinsic, dcf_discount_pct) | (None, None)
  ├── calls _compute_dcf_reverse(price, eps, aaa_yield, g_stage1)
  │         → (dcf_implied_growth, dcf_reverse_converged)
  └── calls overall_score(..., piotroski=..., altman_z=..., dcf_discount_pct=...)
            └── Safety pillar:
                  _compute_piotroski_sub(piotroski_f)  → 0–100 | 50.0 (absent)
                  _compute_altman_sub(altman_z)         → 0–100 | 50.0 (absent)
                  defensive_sub, de_sub, cr_sub (avg-over-present)
                  Safety = _avg_present([piotroski_sub, altman_sub, defensive_sub, de_sub, cr_sub])

write_json(df)
  ├── adds piotroski/altman/dcf sub-scores to nested scores object
  ├── emits flat columns: Piotroski_F, Altman_Z, DCF_Intrinsic, DCF_Discount_Pct,
  │                       DCF_Implied_Growth, dcf_reverse_converged
  └── computes stats.json from df and writes docs/data/stats.json

screener.yml
  ├── (existing) commits docs/data/results.json
  ├── (new) if first weekday of month: commits docs/data/snapshots/YYYY-MM-DD.json
  └── (new) updates docs/data/snapshots/index.json manifest
```

### Recommended Project Structure (additions only)

```
docs/
├── data/
│   ├── results.json          # existing
│   ├── stats.json            # new (Phase 7) — .gitignore exception needed
│   └── snapshots/            # new (Phase 7)
│       ├── index.json        # manifest — .gitignore exception needed
│       └── YYYY-MM-DD.json   # monthly snapshots — .gitignore exception needed
├── stats.html                # new (Phase 7)
├── history.html              # new (Phase 7)
└── app.js                    # modified: +Stats +History in NAV_ENTRIES
tests/
├── test_distress_phase7.py   # new: Piotroski + Altman pure-helper tests
└── test_dcf_phase7.py        # new: forward DCF + reverse DCF solver tests
```

---

## Piotroski F-Score — Implementation Details

### The 9 Criteria [ASSUMED — standard Piotroski 2000 formulation]

The F-Score sums 9 binary signals (0 or 1 each). Requires **two consecutive annual periods** of financial statements.

| # | Signal | Category | Formula | yfinance Source |
|---|--------|----------|---------|-----------------|
| F1 | ROA > 0 | Profitability | Net Income / Total Assets (year 0) | income_stmt: Net Income; balance_sheet: Total Assets |
| F2 | OCF > 0 | Profitability | Operating Cash Flow (year 0) | cashflow: `OCF_LABELS` (already defined) |
| F3 | ROA improved | Profitability | ROA(year 0) > ROA(year 1) | Needs two income_stmt years |
| F4 | Accruals (CFO-based) | Profitability | OCF / Total Assets > ROA | cashflow + balance_sheet |
| F5 | Leverage decreased | Leverage | Long-term debt / Avg Total Assets (year 0) < (year 1) | balance_sheet |
| F6 | Liquidity improved | Leverage | Current Ratio (year 0) > Current Ratio (year 1) | balance_sheet |
| F7 | No dilution | Leverage | Shares Outstanding (year 0) <= (year 1) | balance_sheet: `SHARES_LABELS` (already defined) |
| F8 | Gross margin improved | Operating | Gross Profit / Revenue (year 0) > (year 1) | income_stmt: Gross Profit, Total Revenue |
| F9 | Asset turnover improved | Operating | Revenue / Total Assets (year 0) > (year 1) | income_stmt + balance_sheet |

**Score interpretation → piecewise sub-score:** [ASSUMED]
```
SCORE_PIOTROSKI_BANDS = [
    (0, 2,   0,  20),   # distressed
    (2, 4,  20,  40),   # weak
    (4, 6,  40,  65),   # average
    (6, 8,  65,  85),   # strong
    (8, 9,  85, 100),   # very strong (9/9 rare)
]
```

### yfinance Column Names for Piotroski Inputs

The following label lists need to be added (same pattern as `OCF_LABELS`, `EQUITY_LABELS`, etc.):

```python
NET_INCOME_LABELS = [
    "Net Income",
    "Net Income Common Stockholders",
    "Net Income Including Noncontrolling Interests",
]

TOTAL_ASSETS_LABELS = [
    "Total Assets",
]

GROSS_PROFIT_LABELS = [
    "Gross Profit",
]

REVENUE_LABELS = [
    "Total Revenue",
    "Revenue",
    "Operating Revenue",
]

CURRENT_ASSETS_LABELS = [
    "Current Assets",
    "Total Current Assets",
]

CURRENT_LIABILITIES_LABELS = [
    "Current Liabilities",
    "Total Current Liabilities",
    "Current Liabilities Net Minority Interest",
]

LONG_TERM_DEBT_LABELS = [
    "Long Term Debt",
    "Long Term Debt And Capital Lease Obligation",
]
```

[ASSUMED — based on Phase 6 precedent where OCF_LABELS / EQUITY_LABELS were established by inspection; exact names vary by ticker. Planner should note that a live validation run after implementation will confirm coverage.]

### Two-Year Statement Read Pattern

Currently `_yf_row()` reads only `df.columns[0]` (newest year). For Piotroski, the prior year is `df.columns[1]`. A new helper:

```python
def _yf_row_prev(df, labels) -> float | None:
    """Return the prior-year (second column) value for the first matching label."""
    if df is None or df.empty or df.shape[1] < 2:
        return None
    for label in labels:
        if label in df.index:
            return _safe_float(df.loc[label, df.columns[1]])
    return None
```

[VERIFIED: pattern confirmed from inspection of `get_yf_price_and_history()` which already uses `df.columns[0]` and `df.columns[1]` for shares_now/shares_prev]

### Absent-Data Strategy for Piotroski

If any of the required financial statement rows are missing, the individual criterion returns 0 (conservative — failing the check is safer than skipping it), **except** for the two-year comparison criteria: if the prior year is unavailable for a comparison criterion, that criterion is skipped (treated as absent, not failed). If **all** criteria are absent (no statements at all), `_compute_piotroski()` returns `None` and the sub-score becomes 50.0 per D-04.

Practically, yfinance returns statements for the vast majority of S&P 500 / Dow / Nasdaq-100 tickers. Absent statements are most common for foreign-listed ADRs and very recent IPOs.

---

## Altman Z'' — Implementation Details

### Formula [ASSUMED — standard Altman 1983 Z'' for non-manufacturers, non-financials]

```
Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4

X1 = Working Capital / Total Assets
     WC = Current Assets - Current Liabilities
     Sources: balance_sheet CURRENT_ASSETS_LABELS, CURRENT_LIABILITIES_LABELS, TOTAL_ASSETS_LABELS

X2 = Retained Earnings / Total Assets
     Sources: balance_sheet: "Retained Earnings" / TOTAL_ASSETS_LABELS

X3 = EBIT / Total Assets
     Sources: income_stmt EBIT_LABELS (already defined), balance_sheet TOTAL_ASSETS_LABELS

X4 = Book Value of Equity / Total Liabilities
     BVE = stockholders equity (EQUITY_LABELS, already defined)
     TL  = Total Liabilities (balance_sheet)
     Sources: balance_sheet EQUITY_LABELS, TOTAL_LIABILITIES_LABELS
```

New label list needed:

```python
RETAINED_EARNINGS_LABELS = [
    "Retained Earnings",
    "Retained Earnings Deficit",
]

TOTAL_LIABILITIES_LABELS = [
    "Total Liabilities Net Minority Interest",
    "Total Liabilities",
]
```

[ASSUMED — label names based on Phase 6 precedent pattern. Verify on live data.]

### Distress Zones → Piecewise Sub-Score [ASSUMED]

```
SCORE_ALTMAN_DISTRESS = 1.1   # [ASSUMED] below this = distress zone
SCORE_ALTMAN_SAFE     = 2.6   # [ASSUMED] above this = safe zone

SCORE_ALTMAN_BANDS = [
    # Z'' < 1.1 → sub-score 0 (pure distress)
    (   -999.0,  1.1,   0,   0),   # distress zone (flat at 0)
    (      1.1,  2.6,   0,  70),   # grey zone (interpolated)
    (      2.6, 10.0,  70, 100),   # safe zone
]
```

Negative Z'' is possible (negative equity) and maps to 0.

### Sector Exclusion (D-11)

Altman Z'' is excluded for Financial Services tickers (the Z'' formula was designed for non-financial companies). When sector = "Financial Services", `_compute_altman_z()` is not called and the result is `None`. Per D-04, None → 50.0 in the Safety pillar.

---

## Safety Pillar Restructure — Integration Details

### Current Safety Architecture (to be replaced)

The current `overall_score()` Safety block (lines 549–561):
```python
if is_trap:
    score_safety = float(SCORE_SAFETY_TRAP_PENALTY)   # = 0
elif coverage_fraction == 0.0:
    score_safety = None
else:
    score_safety = round(SCORE_SAFETY_NOTRAP_BASE * coverage_fraction, 2)  # ~60 * fraction
```

`is_trap` is a bool, `coverage_fraction` is a float computed by `trap_gate()`.

### New Safety Architecture (Phase 7)

The `is_trap` parameter is **removed** from `overall_score()`. The Safety pillar becomes an `_avg_present` of five sub-scores:

```
piotroski_sub   — D-04: None → 50.0; else _piecewise_score(piotroski_f, SCORE_PIOTROSKI_BANDS)
altman_sub      — D-04: None → 50.0; else _piecewise_score(z, SCORE_ALTMAN_BANDS)
defensive_sub   — D-01b: None → avg-over-present (existing behavior)
de_sub          — D-01b: None → avg-over-present (existing behavior)
cr_sub          — D-01b: None → avg-over-present (existing behavior)

score_safety = _avg_present([piotroski_sub, altman_sub, defensive_sub, de_sub, cr_sub])
```

**Coverage leaf count change:** The current `all_sub_scores` list has `score_safety` as one leaf (15 total). Phase 7 replaces that single leaf with 2 new leaves (`piotroski_sub`, `altman_sub`) while the de/cr/defensive subs are already counted in Quality — resulting in **17 total leaves**: lynch, graham, fcf, earny, shy, s_52w_lo, s_52w_hi, s_5y_lo, def, de, cr, roic, growth_g, growth_stab, piotroski_sub, altman_sub, dcf_discount_sub.

Wait — architectural note: per the existing code, `def_sub`, `de_sub`, `cr_sub` are in `all_sub_scores` as Quality leaves and also feed Safety. The Safety leaf in `all_sub_scores` is currently `score_safety` (aggregate). In Phase 7, replacing `score_safety` with `piotroski_sub + altman_sub` as the Safety-specific leaves (while de/cr/def remain in Quality) gives **16 leaves** total (replacing 1 safety leaf with 2 new ones, adding 1 dcf_discount_sub = net +2, total 17). The planner should confirm the exact leaf count when implementing.

### Removing is_trap

`is_trap` appears in four places:
1. `trap_gate()` — retained (the underlying inputs are still useful for Quality, just not the boolean result consumed by Safety)
2. `overall_score()` signature — remove the `is_trap` and `coverage_fraction` parameters; remove `SCORE_SAFETY_TRAP_PENALTY` / `SCORE_SAFETY_NOTRAP_BASE` config constants (or keep them as deprecated, annotated)
3. `process_ticker()` call site — stop passing `is_trap` / `coverage_fraction` to `overall_score()`; retain the `row["is_trap"]` flat column in the output (the user still wants visibility into which tickers trip the old gate)
4. `write_json()` `scores` object — `"trap": row.get("is_trap", False)` can be retained for backward compat; the Safety sub-score now carries the real information
5. `top.html` — remove `⚠ TRAP` badge HTML; add Safety chip

### New overall_score() Signature (Phase 7)

```python
overall_score(
    lynch_discount, graham_discount,
    defensive_score, debt_equity, current_ratio,
    growth_g, growth_stability,
    coverage_fraction, aaa_yield,   # coverage_fraction still used for Quality coverage
    # Phase 6 (existing None-defaulted):
    fcf_yield=None, earnings_yield=None, shareholder_yield=None,
    roic=None,
    dist_52w_low=None, dist_52w_high=None, dist_5y_low=None,
    weeks_since_52w_low=None, weeks_since_5y_low=None,
    # Phase 7 additions:
    piotroski_f=None,     # int 0–9 | None
    altman_z=None,        # float | None
    dcf_discount_pct=None, # float | None — for an optional DCF Value sub-score
) -> dict
```

Note: `is_trap` is removed. `coverage_fraction` is retained (it still informs the overall sub-score count). `dcf_discount_pct` is included as an optional Value input (see DCF section below).

---

## DCF — Implementation Details

### Forward Two-Stage DCF

**EPS-based approach (no FCF statement needed):**

The codebase uses EPS as its fundamental earnings signal throughout (Lynch, Graham). For Phase 7, the DCF uses EPS as a proxy for owner earnings per share:

```
Stage 1: Sum of PV(EPS_year_t) for t = 1..5
  EPS_t = EPS_0 * (1 + g_stage1)^t
  where g_stage1 = realized 5yr CAGR (from compute_growth_5yr_cagr, already in pipeline)
  PV discount: WACC = (aaa_yield + DCF_ERP) / 100

Stage 2: Terminal value
  g_terminal = min(g_stage1, DCF_TERMINAL_GROWTH_CAP / 100)  [in decimal]
  TV = EPS_5 * (1 + g_terminal) / (WACC - g_terminal)       # Gordon Growth
  PV(TV) = TV / (1 + WACC)^5

DCF_Intrinsic_Value = PV(Stage 1) + PV(TV)
DCF_Discount_Pct = (1 - price / DCF_Intrinsic) * 100        # positive = cheap
```

**WACC derivation:**
```python
DCF_ERP = 5.5   # [ASSUMED] equity risk premium; config constant

def _dcf_wacc(aaa_yield_pct: float) -> float:
    """WACC as a decimal: (AAA yield % + ERP %) / 100."""
    return (aaa_yield_pct + DCF_ERP) / 100.0
```

**Assert terminal_growth < WACC:**
```python
if g_terminal >= wacc:
    raise ValueError(
        f"DCF config error: terminal_growth ({g_terminal:.3f}) >= WACC ({wacc:.3f}). "
        f"Increase DCF_ERP or reduce DCF_TERMINAL_GROWTH_CAP."
    )
```

This assert fires loudly at compute time (not silently defaulted).

**DCF Discount as a Value sub-score (discretionary):** The planner may choose to add `dcf_discount_pct` as a fourth Value sub-group or leave it as a diagnostic column only. If added to scoring, it would join the Value pillar as a fourth optional sub-group, keeping the existing three sub-groups intact (discount, yield, price-position). Research recommends adding it — it makes the DCF actionable in ranking, not just informational. This is marked Claude's Discretion in CONTEXT.md.

### Reverse DCF

**Goal:** Given the current price, what growth rate is implied?

```
price = f(g_implied) = sum_5yr PV(EPS_0 * (1+g_impl)^t) + PV(TV(g_impl))
Root: f(g_implied) - price = 0

DCF_Implied_Growth — the root in percent
DCF_Reverse_Gap   = DCF_Implied_Growth - realized_g_cagr
```

**scipy.optimize.brentq** is the correct tool — it requires a sign change bracket and is guaranteed to converge if one exists:

```python
from scipy.optimize import brentq

def _compute_dcf_reverse(
    price: float,
    eps: float,
    aaa_yield_pct: float,
    g_stage1_pct: float,
) -> tuple:
    """Returns (implied_growth_pct | None, converged: bool)."""
    wacc = _dcf_wacc(aaa_yield_pct)

    def _dcf_value(g_pct: float) -> float:
        g = g_pct / 100.0
        g_term = min(g, DCF_TERMINAL_GROWTH_CAP / 100.0)
        # Guard: terminal growth must be < WACC
        if g_term >= wacc:
            g_term = wacc - 0.001
        pv = 0.0
        eps_t = eps
        for t in range(1, 6):
            eps_t *= (1 + g)
            pv += eps_t / (1 + wacc) ** t
        tv = eps_t * (1 + g_term) / (wacc - g_term)
        pv += tv / (1 + wacc) ** 5
        return pv - price

    try:
        lo, hi = -50.0, 100.0   # search bounds: -50% to +100% growth [ASSUMED]
        if _dcf_value(lo) * _dcf_value(hi) > 0:
            # No sign change → no root in this bracket
            return (None, False)
        root = brentq(_dcf_value, lo, hi, xtol=1e-4, maxiter=100)
        return (round(root, 2), True)
    except (ValueError, RuntimeError):
        return (None, False)
```

**Bounds rationale [ASSUMED]:** `-50%` to `+100%` covers all economically plausible implied-growth scenarios for large-cap equities. At -50%, EPS halves annually (extreme decline). At +100%, EPS doubles annually (beyond any realistic terminal state). Brentq only needs a bracket where the function changes sign — the wide bounds ensure we find it if a root exists.

**Non-convergence:** When `brentq` raises `ValueError` (no sign change in bracket) or the bracket test fails, `dcf_reverse_converged = False` and `DCF_Implied_Growth = None` per D-09.

---

## Sector Applicability Matrix — Implementation Details

### Current Sector String Values (from yfinance `t.info["sector"]`)

Phase 6 already reads `sector` into `fund["sector"]` via `get_yf_price_and_history()`. The values are GICS sector strings exactly as yfinance returns them. Known values for the S&P 500 universe include: "Technology", "Healthcare", "Financial Services", "Consumer Cyclical", "Industrials", "Consumer Defensive", "Basic Materials", "Energy", "Real Estate", "Communication Services", "Utilities". [ASSUMED — verified for major tickers in prior phases; exact set not enumerated in codebase]

### Gate Implementation

```python
# Sector exclusion constants
DCF_EXCLUDED_SECTORS   = {"Financial Services", "Real Estate"}
ALTMAN_EXCLUDED_SECTORS = {"Financial Services"}

def _sector_allows(fund: dict, metric: str) -> bool:
    """Return False if the sector excludes this metric."""
    sector = fund.get("sector") or ""
    if metric == "dcf" and sector in DCF_EXCLUDED_SECTORS:
        return False
    if metric == "altman" and sector in ALTMAN_EXCLUDED_SECTORS:
        return False
    return True
```

Applied in `process_ticker()` before calling the compute helpers:
```python
piotroski_f = _compute_piotroski(...) if True else None        # no sector exclusion
altman_z    = _compute_altman_z(...) if _sector_allows(fund, "altman") else None
dcf_result  = _compute_dcf_forward(...) if _sector_allows(fund, "dcf") else (None, None)
```

EV/EBIT sector exclusion: Per D-11, Financial Services is excluded from EV/EBIT. However, EV/EBIT is already computed in Phase 6 and the scoring uses `earnings_yield` (not `ev_ebit` directly). The planner should add a gate in `process_ticker()` to set `ev_ebit = None` and `earnings_yield = None` when sector = "Financial Services". This was a Phase 6 item technically, but is gated to Phase 7 per D-11's scope.

---

## Snapshot Workflow — Implementation Details

### First-Weekday-of-Month Detection in GitHub Actions

The existing cron runs Monday–Friday at 11:00 UTC (`0 11 * * 1-5`). A snapshot should commit only on the first weekday of each month. This cannot be done with cron alone — it requires a shell date check:

```yaml
- name: Check if first weekday of month
  id: check-date
  run: |
    DAY=$(date +%d)
    DOW=$(date +%u)  # 1=Monday ... 7=Sunday
    # First weekday = earliest Mon-Fri that falls on day 1-7
    # Condition: day <= 7 AND it's Mon-Fri (1-5)
    if [ "$DAY" -le 7 ] && [ "$DOW" -le 5 ]; then
      echo "is_first_weekday=true" >> "$GITHUB_OUTPUT"
    else
      echo "is_first_weekday=false" >> "$GITHUB_OUTPUT"
    fi

- name: Commit monthly snapshot
  if: steps.check-date.outputs.is_first_weekday == 'true'
  run: |
    SNAP_DATE=$(date +%Y-%m-%d)
    SNAP_FILE="docs/data/snapshots/${SNAP_DATE}.json"
    cp docs/data/results.json "$SNAP_FILE"
    # Update index.json manifest
    python - <<'EOF'
    import json, os, pathlib
    idx_path = pathlib.Path("docs/data/snapshots/index.json")
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else {"snapshots": []}
    date = os.environ["SNAP_DATE"]
    fname = f"{date}.json"
    if fname not in idx["snapshots"]:
        idx["snapshots"].append(fname)
    idx_path.write_text(json.dumps(idx, separators=(",", ":")))
    EOF
    git add "docs/data/snapshots/${SNAP_DATE}.json" docs/data/snapshots/index.json
    if ! git diff --cached --quiet; then
      git commit -m "chore: monthly snapshot ${SNAP_DATE}"
      git push
    fi
  env:
    SNAP_DATE: $(date +%Y-%m-%d)
```

[ASSUMED — shell date syntax for Ubuntu (GitHub Actions ubuntu-latest). `date +%d` returns zero-padded day, arithmetic comparison works with `-le`. `date +%u` returns ISO weekday. This approach is well-established for GitHub Actions first-weekday detection.]

**Alternative simpler approach:** The screener Python script itself can detect the date and write the snapshot file. The Actions workflow just commits whatever new files appeared. This avoids embedding Python in the YAML heredoc. The planner may prefer this approach.

### gitignore Exceptions Needed

Three lines added to `.gitignore`:
```
!docs/data/stats.json
!docs/data/snapshots/*.json
!docs/data/snapshots/index.json
```

The current `.gitignore` has `*.json` with only `!docs/data/results.json` as an exception. [VERIFIED: read .gitignore directly]

### Minimum-Row Guard Reuse (DATA-02)

The snapshot copy should only happen if `results.json` was successfully written (the existing Python `write_json()` already exits non-zero if < 100 rows). The Actions job fails fast on non-zero exits, so the snapshot step never runs after a failed screener run. No additional guard needed at the snapshot step itself — the guard is upstream.

### index.json Manifest Schema [ASSUMED]

```json
{
  "snapshots": [
    "2026-07-01.json",
    "2026-08-01.json"
  ]
}
```

Simple array of filenames, newest-last. `history.html` fetches this to build its list. No metadata in the manifest — the date is derivable from the filename. Download link = `data/snapshots/{filename}`.

---

## stats.json Schema [ASSUMED — Claude's Discretion per CONTEXT.md]

All fields computed from the final DataFrame in `write_json()` (or a separate `_compute_stats(df)` helper called from `write_json`).

```json
{
  "generated_at": "2026-07-01T11:00:00Z",
  "universe_count": 550,
  "buy_signal_count": 42,
  "low_safety_count": 87,
  "score_distribution": {
    "0_20": 23,
    "20_40": 98,
    "40_60": 187,
    "60_80": 201,
    "80_100": 41
  },
  "pillar_averages": {
    "value": 48.2,
    "quality": 52.1,
    "growth": 44.8,
    "safety": 51.3
  },
  "sector_breakdown": [
    {
      "sector": "Technology",
      "count": 72,
      "avg_score": 53.4,
      "buy_signal_count": 8
    }
  ],
  "coverage_stats": {
    "avg_coverage_pct": 71.3,
    "tickers_with_piotroski": 498,
    "tickers_with_altman": 421,
    "tickers_with_dcf": 389,
    "tickers_with_fcf_yield": 501
  }
}
```

**Definition of `low_safety_count`:** tickers with `score_safety < 30` (threshold [ASSUMED] — this replaces the old `is_trap` count).

**`sector_breakdown`** is an array sorted by `count` descending. Null sector tickers are grouped under "Unknown".

---

## Common Pitfalls

### Pitfall 1: yfinance Statement Column Ordering

**What goes wrong:** `income_stmt`, `balance_sheet`, and `cashflow` return columns in newest-first order by default in some yfinance versions, oldest-first in others depending on `sort_index(axis=1)` calls.

**Why it happens:** The current code calls `inc.sort_index(axis=1)` (oldest→newest) for EPS extraction but reads `income_stmt` raw (newest-first) for EBIT via `_yf_row(t.income_stmt, EBIT_LABELS)`. This asymmetry works because `_yf_row` always reads `df.columns[0]` (newest-first = most recent, which is correct for a spot reading). For Piotroski, reading `columns[0]` and `columns[1]` from the **unsorted** statement gives newest + second-newest — which is what we want.

**How to avoid:** Do NOT sort the statement dataframe when reading it for Piotroski. Use `df.columns[0]` = newest, `df.columns[1]` = prior year. Verify with a single test assertion: `assert df.columns[0] > df.columns[1]` (yfinance timestamps are datetime, newest = largest).

**Warning signs:** Piotroski F-scores all equal 4–5 (near-flat) or all criteria pass/fail together — suggests both years are the same data.

### Pitfall 2: Altman Z'' Negative Z Scores

**What goes wrong:** Negative equity (X4) or negative retained earnings (X2) produce negative Z'', which is less than the distress threshold and correctly maps to sub-score 0. But if the band table bottom is `-999.0` (a sentinel) rather than negative infinity, a very negative Z'' might fall below the band and get the wrong score.

**How to avoid:** The bottom of `SCORE_ALTMAN_BANDS` must start at a value lower than any realistic Z'' (e.g., -999.0). The `_piecewise_score()` implementation already handles below-first-band by returning `score_lo` of the first band — so as long as the first band starts low enough, extreme negative Z'' correctly maps to 0.

### Pitfall 3: DCF Terminal Growth >= WACC

**What goes wrong:** If `aaa_yield` is very low (e.g., 3.5%) and `DCF_ERP = 5.5%`, WACC = 9.0%. A stock with realized 5yr CAGR of 15% gets terminal_growth = min(15%, 3%) = 3%, which is safely below 9%. However, if `DCF_TERMINAL_GROWTH_CAP` is misconfigured (e.g., set to 10%), terminal_growth could approach or exceed WACC, causing the Gordon Growth denominator to approach zero or go negative.

**How to avoid:** The assert `terminal_growth < WACC` fires at compute time and raises a loud `ValueError` with a config-diagnostic message. The planner should also add a unit test that triggers this condition.

### Pitfall 4: Reverse DCF No-Root Edge Cases

**What goes wrong:** For very cheap stocks (low P, high EPS), even at -50% implied growth the DCF value exceeds the price. For very expensive stocks (high P, low EPS), even at +100% growth the DCF value falls short of the price. In both cases, `_dcf_value(lo) * _dcf_value(hi) > 0` (no sign change), and `brentq` cannot be called.

**How to avoid:** The bracket test `if _dcf_value(lo) * _dcf_value(hi) > 0: return (None, False)` correctly handles this. Do not expand the bounds further (e.g., to -90% or +500%) — at extreme growth rates the Gordon Growth terminal value becomes numerically unstable and can produce spuriously large values.

### Pitfall 5: is_trap Removal Creates Subtle Backward-Compat Breaks

**What goes wrong:** `is_trap` is currently in the `scores` nested object as `"trap"` and as a flat column `is_trap`. If the planner removes it entirely from the JSON schema, any external user who built a tool against `results.json` would break.

**How to avoid:** Keep `is_trap` as a flat column (its value is still computed by `trap_gate()`) and keep `"trap": row.get("is_trap")` in the nested scores object. The Safety pillar now computes its score from Piotroski + Altman instead of the trap gate — `is_trap` becomes diagnostic metadata rather than a gate.

### Pitfall 6: stats.json Missing .gitignore Exception

**What goes wrong:** The `*.json` rule in `.gitignore` excludes all JSON files. `docs/data/results.json` already has an exception. If `stats.json`, `snapshots/*.json`, and `snapshots/index.json` are not also excepted, the Actions commit step silently fails to include them.

**How to avoid:** Add all three exceptions to `.gitignore` in Wave 0 before the snapshot/stats workflow is wired up.

### Pitfall 7: sector=None Bypasses All Sector Gates

**What goes wrong:** If `fund["sector"]` is `None` (data unavailable), `sector in DCF_EXCLUDED_SECTORS` evaluates to False — meaning a ticker with no sector data gets DCF computed. This is actually **correct** behavior (no known exclusion → include), but it could be surprising.

**How to avoid:** Document this explicitly as intentional: sector=None means "sector unknown, no exclusion applied." The `DCF_Cyclical_Flag` field should be set to True only when sector is known to be in {"Energy", "Materials"} — not when sector is None.

---

## Code Examples

### Pattern 1: _compute_piotroski() Pure Helper

```python
# Source: codebase inspection of Phase 6 _compute_* pattern
def _compute_piotroski(
    inc_curr, inc_prev,   # income_stmt DataFrames (newest year, prior year)
    bs_curr, bs_prev,     # balance_sheet DataFrames
    cf_curr,              # cashflow DataFrame (newest year)
) -> int | None:
    """
    Compute Piotroski F-Score (0–9).
    Returns None if no statement data available.
    internal — for tests only.
    """
    def _get(df, labels, col=0):
        if df is None or df.empty or df.shape[1] <= col:
            return None
        for label in labels:
            if label in df.index:
                return _safe_float(df.loc[label, df.columns[col]])
        return None

    # All nine binary signals
    # ... (implementation in plan)
    pass
```

### Pattern 2: NAV_ENTRIES Extension in app.js

```javascript
// Source: docs/app.js inspection (lines 107–112)
// Current:
var NAV_ENTRIES = [
  { label: "Dashboard",   href: "index.html",       key: "dashboard" },
  { label: "Top Picks",   href: "top.html",          key: "top" },
  { label: "Methodology", href: "methodology.html",  key: "methodology" }
  // Phase 7: { label: "Stats", href: "stats.html", key: "stats" }
];

// Phase 7 addition (uncomment + add History):
var NAV_ENTRIES = [
  { label: "Dashboard",   href: "index.html",       key: "dashboard" },
  { label: "Top Picks",   href: "top.html",          key: "top" },
  { label: "Stats",       href: "stats.html",        key: "stats" },
  { label: "History",     href: "history.html",      key: "history" },
  { label: "Methodology", href: "methodology.html",  key: "methodology" }
];
```

### Pattern 3: stats.html Fetch Pattern (matches results.json pattern)

```javascript
// Source: docs/app.js and docs/top.html fetch pattern
fetch("data/stats.json?v=" + Date.now())
  .then(function(r) { return r.json(); })
  .then(function(data) {
    updateFreshnessUI(data.generated_at);
    renderStats(data);
  })
  .catch(function(err) {
    document.getElementById("stats-container").innerHTML =
      '<p>Could not load stats data.</p>';
  });
```

### Pattern 4: Safety Chip on top.html (replacing trap badge)

```javascript
// Source: docs/top.html signalChipHtml() pattern (inspected)
// New Safety chip:
function safetyChipHtml(safetyScore) {
  var s = (safetyScore === null || safetyScore === undefined) ? -1 : safetyScore;
  var bg, fg;
  if (s >= 60)      { bg = "#a3be8c"; fg = "#2e3440"; }  // green
  else if (s >= 35) { bg = "#ebcb8b"; fg = "#2e3440"; }  // yellow
  else              { bg = "#bf616a"; fg = "#eceff4"; }  // red (distressed)
  var label = s < 0 ? "Safety: —" : "Safety: " + s.toFixed(0);
  return '<span class="signal-chip" style="background:' + bg +
         ';color:' + fg + ';">' + label + '</span>';
}
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bounded root-finding for reverse DCF | A custom bisection loop | `scipy.optimize.brentq` | scipy's brentq is already installed, tested, handles edge cases (tolerance, maxiter, non-convergence), and is 3 lines vs 40 |
| Date arithmetic for first-weekday detection | Complex Python date logic | Shell `date +%d` + `date +%u` comparison in YAML | One-liner shell check; no Python needed in the YAML (or Python `datetime.date.today()` in the screener) |
| Stats computation in JS | Client-side aggregation of results.json rows | Python computes stats.json at write time | Client must download 550 rows of data to compute stats; Python does it once per run at negligible cost |
| Charting library for stats.html | Chart.js, D3, Plotly | Plain HTML tables + number cards | Consistent with no-build-step, no CDN dependency for stats; 5-bucket text distribution is readable without charts |

---

## State of the Art

| Old Approach | Current Approach | Impact for Phase 7 |
|--------------|-----------------|-------------------|
| `is_trap` binary Safety gate (floors to 0) | Piotroski F-Score + Altman Z'' as continuous sub-scores | Retirement of is_trap param from overall_score(); Safety becomes proportional, not binary |
| Single-year statement reads via `_yf_row()` | Two-year reads via `_yf_row()` + `_yf_row_prev()` | New helper needed; data already fetched by `get_yf_price_and_history()` |
| 3-link nav (Dashboard, Top Picks, Methodology) | 5-link nav (+ Stats, + History) | One array edit in `app.js` NAV_ENTRIES |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Piotroski 9-criterion formulation matches Piotroski (2000) paper | Piotroski section | Low — standard formulation; worst case a criterion is slightly wrong, fixable in Phase 8 threshold tuning |
| A2 | Altman Z'' thresholds: distress < 1.1, safe > 2.6 | Altman section | Low — well-cited; Altman himself documents these in the 1983 paper |
| A3 | Equity risk premium default of 5.5% | DCF section | Medium — ERP is time-varying; 5.5% is a common mid-range estimate. Wrong ERP shifts all DCF intrinsic values but does not break the relative ranking |
| A4 | DCF terminal growth cap of 3.0% | DCF section | Low — approximately matches long-run nominal GDP growth; only affects stocks with CAGR > 3% |
| A5 | Reverse DCF bounds of -50% to +100% | Reverse DCF section | Low — covers all economically plausible scenarios for large-cap equities in this universe |
| A6 | yfinance label names for Piotroski (NET_INCOME_LABELS, etc.) | Piotroski section | Medium — yfinance label names are known to vary by ticker. Label lists mitigate this; a live validation run will confirm coverage |
| A7 | Altman label names (RETAINED_EARNINGS_LABELS, TOTAL_LIABILITIES_LABELS) | Altman section | Medium — same risk as A6 |
| A8 | Shell date logic `date +%d` / `date +%u` works on ubuntu-latest | Snapshot workflow | Low — standard GNU coreutils; ubuntu-latest has not changed this in years |
| A9 | SCORE_PIOTROSKI_BANDS breakpoints | Piotroski section | Medium — no empirical anchor yet; monitor in stats.html and tune in Phase 8 |
| A10 | SCORE_ALTMAN_BANDS breakpoints and grey-zone interpolation | Altman section | Medium — same calibration caveat as A9 |
| A11 | `low_safety_count` threshold of score_safety < 30 for stats.json | stats.json schema | Low — this is a display heuristic, not a gate; easily adjusted |
| A12 | EV/EBIT exclusion for Financial Services was Phase 6 work deferred to Phase 7 | Sector gate | Low — confirmed from CONTEXT.md D-11 scope; just needs to be added in process_ticker |

---

## Open Questions

1. **DCF as a Value sub-score or diagnostic only?**
   - What we know: D-06–D-09 define the DCF computation; D-07 feeds Stage 1 growth from the Phase 5.1 realized CAGR. The CONTEXT.md marks it as Claude's Discretion.
   - What's unclear: Should `dcf_discount_pct` be folded into the Value pillar as a fourth sub-group, or emitted as a flat column for user inspection only?
   - Recommendation: Add it as a fourth Value sub-group (alongside discount, yield, price-position). This makes the DCF actionable in the OverallScore without requiring a user to read a separate column. The planner should confirm this in Wave planning.

2. **_compute_piotroski() gets pre-fetched DataFrames or re-fetches?**
   - What we know: `get_yf_price_and_history()` currently fetches `t.income_stmt`, `t.balance_sheet`, `t.cashflow` but reads only specific rows from them. The DataFrames themselves are not returned.
   - What's unclear: Should `get_yf_price_and_history()` return the raw DataFrames for Piotroski / Altman to use, or should the Piotroski/Altman helpers be called inside the function while the Ticker object is in scope?
   - Recommendation: Pass the raw DataFrames back in the return dict (add `income_stmt_df`, `balance_sheet_df`, `cashflow_df` keys, value = the DataFrame | None). This keeps all yfinance I/O in one function and makes the compute helpers fully testable offline with fixture DataFrames. The planner should verify memory implications (DataFrames for 550 tickers are not kept simultaneously — each is processed and discarded).

3. **Coverage leaf count after Phase 7 changes?**
   - What we know: Phase 6 established 15 leaves. Phase 7 removes the `score_safety` aggregate leaf and adds `piotroski_sub` and `altman_sub`. Optionally adds `dcf_discount_sub`.
   - What's unclear: Exact count depends on whether DCF discount is scored (17 leaves) or just diagnostic (16 leaves).
   - Recommendation: If DCF discount is added as a Value sub-group → 17 leaves. Document the new count in a comment in `overall_score()` matching the Phase 6 pattern.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| scipy | Reverse DCF solver | Yes | 1.15.3 | — (no install needed) |
| yfinance | Statement fetches | Yes | >=0.2.40 | — |
| fredapi | WACC computation | Yes | >=0.5.1 | — |
| Python 3.11 | All computation | Yes (local + Actions) | 3.11 | — |

**Missing dependencies with no fallback:** none.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Vanilla assert + `run_all()` (no pytest — matches existing test_scoring.py pattern) |
| Config file | none |
| Quick run command | `python tests/test_distress_phase7.py && python tests/test_dcf_phase7.py` |
| Full suite command | `python tests/test_scoring.py && python tests/test_growth_trap_fixes.py && python tests/test_factors_phase6.py && python tests/test_scoring_phase6.py && python tests/test_distress_phase7.py && python tests/test_dcf_phase7.py` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIGNAL-08 | `_compute_piotroski()` returns 0–9 for fixture data | unit | `python tests/test_distress_phase7.py` | No — Wave 0 |
| SIGNAL-08 | Absent statements → None | unit | same | No — Wave 0 |
| SIGNAL-09 | `_compute_altman_z()` returns Z'' for fixture inputs | unit | same | No — Wave 0 |
| SIGNAL-09 | Distress zone Z'' < 1.1 → sub-score 0 | unit | same | No — Wave 0 |
| TRAP-03 | `overall_score()` Safety pillar uses Piotroski + Altman, not is_trap | unit | `python tests/test_scoring.py` (modified) | Yes — modify |
| DCF-01 | `_compute_dcf_forward()` returns intrinsic value + discount % | unit | `python tests/test_dcf_phase7.py` | No — Wave 0 |
| DCF-02 | `_compute_dcf_reverse()` returns implied growth for known fixture | unit | same | No — Wave 0 |
| DCF-03 | terminal_growth >= WACC raises ValueError | unit | same | No — Wave 0 |
| DCF-03 | No-root bracket → (None, False) | unit | same | No — Wave 0 |
| SECTOR-02 | Financial Services → altman_z = None in process_ticker | unit | `python tests/test_distress_phase7.py` | No — Wave 0 |
| DCF-03 | Real Estate → dcf_intrinsic = None | unit | same | No — Wave 0 |

### Sampling Rate

- **Per task commit:** `python tests/test_distress_phase7.py && python tests/test_dcf_phase7.py`
- **Per wave merge:** full suite (all 6 test files, expecting ~105+ tests pass)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_distress_phase7.py` — covers SIGNAL-08, SIGNAL-09, TRAP-03, SECTOR-02 pure helpers
- [ ] `tests/test_dcf_phase7.py` — covers DCF-01, DCF-02, DCF-03 pure helpers

*(Existing `tests/test_scoring.py` will need modification in Wave 2 when `is_trap` is removed from `overall_score()` signature — the backward-compat tests for the old `is_trap` param become invalid.)*

---

## Security Domain

Security enforcement is not a primary concern for this phase — no new user input surfaces, no new network endpoints, no authentication. The phase adds read-only static pages (`stats.html`, `history.html`) and extends existing Python computation. The existing `escHtml()` in `app.js` already covers any ticker strings that appear in the new pages. No ASVS categories newly applicable.

---

## Sources

### Primary (HIGH confidence — codebase directly verified)

- `stock_screener.py` (full read) — `overall_score()` signature, `_compute_*` pattern, `_yf_row()`, label lists, `write_json()`, `trap_gate()`, `SCORE_*` config block, `process_ticker()`, `get_yf_price_and_history()`, `fetch_aaa_yield()`
- `docs/app.js` (read) — `NAV_ENTRIES` array, `buildNav()`, `escHtml()`, `updateFreshnessUI()`, `signalChipHtml()` pattern
- `docs/top.html` (read) — trap badge location, Safety chip integration point
- `.github/workflows/screener.yml` (read) — existing commit pattern, cron schedule, conditional commit logic
- `.gitignore` (read) — existing exceptions, `*.json` rule
- `requirements.txt` (read) — confirmed no scipy listed (it's installed but not in requirements.txt)
- `.planning/phases/06-cheap-factors-sector/06-02-SUMMARY.md` (read) — final `overall_score()` signature, 15-leaf coverage count
- `tests/test_scoring.py` (read) — offline test pattern, env var setup, vanilla assert convention

### Secondary (MEDIUM confidence)

- scipy 1.15.3 installed — confirmed via `python -c "import scipy; print(scipy.__version__)"` [VERIFIED: installed locally]; `brentq` exists in `scipy.optimize` [ASSUMED — standard scipy API, present in all versions >= 0.10]

### Tertiary (LOW confidence — training knowledge, marked [ASSUMED])

- Piotroski (2000) F-Score 9-criterion formulation
- Altman (1983) Z'' formula coefficients and distress-zone thresholds
- yfinance financial statement column name candidates (risk: vary by ticker)
- DCF equity risk premium value (5.5%) and reverse DCF bounds

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all computation uses already-installed libraries
- Architecture: HIGH — patterns verified directly from codebase; integration points are explicit
- Piotroski/Altman formulas: MEDIUM — standard academic formulations, but yfinance column names are [ASSUMED]
- DCF implementation: MEDIUM — formula is standard; solver bounds and ERP are [ASSUMED]
- Snapshot workflow: MEDIUM — shell date logic is standard; not verified against live Actions

**Research date:** 2026-06-28
**Valid until:** 2026-07-28 (yfinance column names are stable across minor versions; scipy API is stable)
