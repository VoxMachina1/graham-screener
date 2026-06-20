# Phase 5: Score Foundation + Public Top-N — Research

**Researched:** 2026-06-18
**Domain:** Python valuation math (Buy Price audit), absolute scoring engine, JS frontend (app.js extraction, top.html)
**Confidence:** HIGH (formula audit from code + canonical definitions) / MEDIUM (Finnhub FCF field names)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01** — Negative / calculation-breaking inputs → worst-possible sub-score, never a failure/drop.
- **D-01b** — Truly absent data (null) → average-over-present + coverage flag; missing Safety = unknown, never safe. Negative-but-present and genuinely-missing are distinct code paths.
- **D-02** — Interim pillar weights ~35/30/20/15 (Value/Quality/Growth/Safety). Each pillar = average-over-present of its sub-scores.
  - VALUE: `Lynch_Discount_Pct` + `Graham_Discount_Pct` grouped as one "discount" sub-factor (averaged); Phase 6 adds FCF-yield etc. as a second sub-group.
  - QUALITY: `DefensiveScore` (0–8), `debt_equity`, `current_ratio`.
  - GROWTH: growth `g` (GROWTH_CAP-capped) + growth-stability from `annual_eps`.
  - SAFETY: driven by the interim trap gate (D-03).
  - `debt_equity` and `current_ratio` deliberately appear in BOTH Quality and Safety — document, do not "fix."
- **D-02b** — All pillar weights, band thresholds, winsorization bounds as version-controlled config constants in the existing `LYNCH_*/GRAHAM_*` style. Yield-based thresholds rate-relativized to live FRED AAA yield. No empirical anchor yet; keep loud and tunable.
- **D-02c** — `OverallScore` replaces `CombinedScore` as primary sort; `CombinedScore` retained as a column (additive schema).
- **D-03** — Tripped trap gate floors the Safety sub-score (worst-possible); row still shown with visible `TRAP` badge.
- **D-04** — Interim gate inputs: `debt_equity`, `current_ratio`, `EPS_Stability`, negative FCF. FCF read from the already-fetched Finnhub `metric=all` bundle (NOT a new fetch).
- **D-05** — Full Lynch/Graham formula audit + KO fixture.

### Claude's Discretion

- Stats nav link deferred to Phase 7 (Stats page does not exist in Phase 5). Phase 5 nav = Dashboard / Top Picks / Methodology only. `buildNav()` must accept a future 4th entry trivially.
- Exact winsorization bounds, band breakpoints, and growth-stability formula.
- `top.html` presentation within the approved mockup contract (05-UI-SPEC.md).

### Deferred Ideas (OUT OF SCOPE)

- Graded FCF yield as a positive Value factor — Phase 6 (SIGNAL-04).
- 52w/5y distance, EV/EBIT, ROIC, shareholder yield — Phase 6.
- Piotroski F, Altman Z, DCF, sector guards, stats.html, snapshots — Phase 7.
- Stats nav link — Phase 7.
- Backtest harness — deferred beyond v2.0.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FIX-01 | Buy Price bug diagnosed, corrected, spot-check fixture for KO | § Buy Price Bug Analysis below |
| FIX-02 | Corrected discount fields confirmed sane before any pillar consumes them | § Integration Points — FIX-02 gate |
| SCORE-01 | 4-pillar absolute OverallScore (0–100) from Value/Quality/Growth/Safety | § Scoring Engine Design |
| SCORE-02 | Piecewise-linear absolute threshold mapping (not cross-sectional ranks) | § Piecewise-Linear Band Design |
| SCORE-03 | Winsorize/clamp both tails before pillar aggregation | § Winsorization Strategy |
| SCORE-04 | Average-over-present missing rule + coverage flag; missing Safety = unknown | § Missing-Data Rule |
| SCORE-05 | Pillar decomposition in flat columns + nested scores object + UI columns | § JSON Schema Extension |
| SCORE-06 | Version-controlled weights/thresholds; yield thresholds rate-relativized to AAA | § Config Constants Block |
| SCORE-07 | Correlated Value metrics grouped (not glorified cheapness rank) | § Value Pillar Grouping |
| SCORE-08 | OverallScore replaces CombinedScore as primary sort key | § run_screener sort swap |
| TRAP-01 | Interim value-trap gate from existing signals before Top-N ships | § Value-Trap Gate |
| TRAP-02 | Value-trap badge on Top-N page | § top.html — UI-SPEC contract |
| PAGE-01 | docs/top.html Top 10/25 picks page | § app.js Extraction + top.html |
| PAGE-03 | Shared docs/app.js with fetch/format/color/freshness primitives | § app.js Extraction |
| PAGE-04 | Site nav: Dashboard, Top Picks, Methodology (Stats deferred) | § buildNav() contract |
</phase_requirements>

---

## Summary

Phase 5 has three largely independent workstreams that must execute in dependency order: (1) diagnose and fix the Buy Price bug, (2) build the 4-pillar `OverallScore` on top of the corrected discount fields, (3) extract `docs/app.js` and ship `docs/top.html`. The Buy Price fix is the hard blocker — `Lynch_Discount_Pct` and `Graham_Discount_Pct` feed directly into the Value pillar, so any formula defect corrupts the composite from the start.

The formula audit (§ Buy Price Bug Analysis) reveals two likely root causes in the current code that must be verified against the KO fixture: the Lynch buy price is correctly defined as `FV_GplusD * LYNCH_DISCOUNT[cat]` and the discount sign is correct (`(1 - price/buyPrice)*100`), but the formula is vulnerable to the floor at `g=1.0` silently corrupting the KO fixture when the real growth rate is negative or missing. The Graham formulas are algebraically correct relative to the 1974 revised Graham formula, but VB uses `7 + g` (the original 1962 formula's no-growth P/E) while VA uses `8.5 + 2g`, and the code already caps `g` at 15 — the most likely defect is that the combined cap/floor interplay distorts the "conservative" VB selection for fast-growers.

The scoring engine follows a straightforward pattern: each metric is winsorized then mapped through a piecewise-linear function to [0,100]; sub-scores are averaged within a pillar (with the Value pillar using a two-level average: discount-group, then any Phase 6 sub-groups); pillars are combined using the configured weights; missing pillars are averaged-over-present. All thresholds and weights live as `SCORE_*` config constants.

The Finnhub `metric=all` bundle is already fetched and parsed — the `freeCashFlowPerShareAnnual` (or TTM variant) field is present in the response for most US large-cap tickers. The FCF sign check for the trap gate reads this field; a missing value triggers the D-01b average-over-present path rather than assuming the gate is clear.

The `app.js` extraction is low-risk: every function to move already exists in `index.html` as a named module-level `function`/`var` declaration; extraction is a cut-paste with a `<script src="app.js">` replacement in `index.html`, and addition in `top.html` and `methodology.html`.

**Primary recommendation:** Execute in strict order — FIX-01 KO fixture first, then SCORE-01..08 building on verified discounts, then TRAP-01/02, then PAGE-01/03/04. Do not begin pillar scoring until FIX-02 gate passes with the KO fixture.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Buy Price formula audit + fix | Python pipeline | — | Pure computation in `lynch_metrics()` / `graham_metrics()`; no UI involvement |
| KO fixture | Python pytest or plain assert | — | Hand-computable; should be a committed test file not an ad-hoc script |
| Negative-input worst-score routing | Python pipeline | — | Changes error-return behavior in `lynch_metrics()` / `graham_metrics()` |
| OverallScore + pillar computation | Python pipeline | — | Pure computation; new `overall_score()` function in Step 4 |
| FCF sign from Finnhub bundle | Python pipeline — `get_combined_data()` | — | Stop discarding the field; pass it through the return dict |
| Interim trap gate | Python pipeline — `process_ticker()` | — | Gate is computed at row assembly; result stored as `is_trap` |
| JSON schema extension (flat + nested) | Python pipeline — `process_ticker()` / `write_json()` | — | New columns added to row dict; nested `scores` key in write_json |
| Sort key swap | Python pipeline — `run_screener()` | — | One-line change: `CombinedScore` → `OverallScore` |
| app.js extraction | Frontend — static files | — | Cut-paste refactor; no new logic |
| top.html | Frontend — static files | — | New static page; reads same results.json |
| Nav update (3-link) | Frontend — shared via buildNav() | — | All three HTML pages call buildNav() |

---

## Buy Price Bug Analysis

[ASSUMED] — Root causes derived from reading the current code against canonical formula definitions; not verified by running the screener against known-correct output.

### Lynch Buy Price

**Current code** (`lynch_metrics`, line 370):
```python
m["Lynch_BuyPrice"] = round(m["FV_GplusD"] * LYNCH_DISCOUNT[cat], 2)
m["Lynch_Discount_Pct"] = round((1 - price / m["Lynch_BuyPrice"]) * 100, 1)
```

where `FV_GplusD = eps * (g + dy)` (line 358) and `LYNCH_DISCOUNT = {"Slow": 0.75, "Stalwart": 0.80, "Fast": 0.70}`.

**Canonical Lynch definition** [CITED: One Up on Wall Street, Ch. 13 "Some Famous Numbers"]:
Lynch's primary valuation is the **Lynch Score** = `(g + dy) / pe` — he calls a stock fairly valued when this ratio equals 1.0, undervalued when > 1.5, and a strong buy when > 2.0. He states: "The P/E ratio of any company that's fairly priced will equal its growth rate."

The code's `FV_GplusD = eps * (g + dy)` is equivalent to saying "fair P/E = g + dy", which is an interpretation that treats the Lynch Score = 1.0 as the fair-value anchor. This is a reasonable and common implementation of Lynch's principle. The buy-price then applies a category-specific haircut (Slow: 75%, Stalwart: 80%, Fast: 70%) to give a margin-of-safety target.

**Sign and direction check:** `Lynch_Discount_Pct = (1 - price/buyPrice) * 100`
- If price < buyPrice: discount is positive (stock is cheap relative to buy price) ✓
- If price > buyPrice: discount is negative (stock is expensive) ✓
- This is semantically correct — a POSITIVE discount means the stock trades BELOW the buy target.

**Key issue found:** The discount field feeds `combined_score()` via `min(max(discount, 0), 60)` — only positive discounts contribute. This is by design for the current CombinedScore. For the new Value pillar, negative discounts should map to the low end of the score range rather than being clipped — this is the SCORE-03 winsorization behavior.

**Second issue — the g=1.0 floor:** `process_ticker()` at line 584–586 floors negative/zero growth to 1.0 before calling `lynch_metrics()`. This means a stock with `g = -5%` gets `g = 1.0` passed to the formula, producing a non-zero buy price and a non-terrible discount. Under D-01, negative growth should route to worst-possible sub-score instead of being silently floored.

**The Lynch discount formula itself appears algebraically correct.** The most likely "visibly wrong buy price" bug is not a sign inversion — it is that:
1. The growth floor at 1.0 allows stocks with poor or negative growth to receive benign-looking buy prices.
2. KO's growth from Finnhub may be coming in as a 5Y CAGR that doesn't match what a user would compute from recent EPS (e.g., Finnhub may include years with COVID EPS distortion in the 5Y window).

### Graham Fair Value

**Current code** (`graham_metrics`, lines 432–437):
```python
g_capped = min(g, 15.0)
m["Graham_VA"] = round(eps * (GRAHAM_NO_GROWTH_PE + 2 * g_capped) * GRAHAM_HIST_AAA / aaa_yield, 2)
m["Graham_VB"] = round(eps * (7 + g_capped) * GRAHAM_HIST_AAA / aaa_yield, 2)
m["Graham_FV"] = min(m["Graham_VA"], m["Graham_VB"])
```

**Canonical Graham formulas** [CITED: The Intelligent Investor, 1974 revised edition, Ch. 11]:
- Original (1962): V = EPS × (8.5 + 2g)
- Revised (1974): V = EPS × (8.5 + 2g) × 4.4 / Y (where 4.4 is the 1963 AAA yield, Y is current AAA yield)

**VA is the revised formula.** Code uses `GRAHAM_NO_GROWTH_PE = 8.5` and `GRAHAM_HIST_AAA = 4.4` — this matches the canonical formula exactly. ✓

**VB uses `7 + g` instead of `8.5 + 2g`.** This is a "more conservative baseline P/E" variant — not in Graham's book, but commonly used by practitioners who want a lower no-growth floor. This is an intentional design choice, not a bug, but it is undocumented and should be captured in a comment.

**Graham discount sign:** `Graham_Discount_Pct = (1 - price/fv) * 100` — positive means price < fair value (cheap). Same direction as Lynch discount. ✓

**Potential VB issue:** For a stock like KO with modest growth (g ≈ 5%), `Graham_VB = eps * (7 + 5) * 4.4/aaa` = `eps * 12 * 4.4/aaa`. With `aaa ≈ 5.3%`, VB ≈ `eps * 9.96`. If KO EPS ≈ $3.04, VB ≈ $30.25. VA = `eps * (8.5 + 10) * 4.4/5.3` ≈ `3.04 * 15.36` ≈ $46.7. The code takes `min(VA, VB) = VB ≈ $30.25`, giving a buy price well below current price (~$79), which would show a LARGE negative discount. That negative discount would be clipped to 0 by `combined_score()`. This is likely what makes Graham discounts look "wrong" — the VB formula's conservative base PE of 7 produces fair values far below market price for quality franchises, making nearly every large-cap look expensive.

**This is the most likely root cause of "Buy Price visibly wrong."** VB = `eps * (7 + g_capped) * 4.4/aaa` is too conservative for Stalwart/quality companies trading at justified premiums. The formula is not mathematically broken — it is producing the correct output of a very conservative model, but users expect a fair value closer to market price.

**Recommendation for FIX-01:** Do NOT change the formulas in Phase 5. Document the behavior. The FIX is to (a) add the KO fixture to confirm the formulas compute what the code says they should, and (b) fix the g-floor D-01 change so negative growth correctly produces worst-possible sub-scores. Phase 5 audit must confirm the math is internally consistent; recalibrating the model is a future decision.

### KO Hand-Verification Fixture

Use these inputs to build the pytest fixture. All values from public sources as of approximately June 2026:

| Input | Value | Source |
|-------|-------|--------|
| Ticker | KO | — |
| Price | ~$79.86 | [ASSUMED — market price, verify at run time] |
| EPS TTM | ~$3.18 | [ASSUMED — GuruFocus, verify] |
| growth g (Finnhub 5Y CAGR) | ~4–6% | [ASSUMED — estimate; KO is a Slow Grower] |
| Dividend per share (annual) | ~$2.09 | [ASSUMED — Coca-Cola investor relations] |
| Dividend yield dy | ~2.62% | [ASSUMED — companiesmarketcap.com] |
| AAA yield (FRED) | ~5.3% | [ASSUMED — estimate for 2026] |
| P/B ratio | ~6.6 | [ASSUMED — GuruFocus] |

**Expected fixture outputs (compute manually before encoding):**

Step 1 — Lynch:
- `pe = price / eps` → ~25.1
- `g + dy` → assume g=5, dy=2.62 → 7.62
- `FV_GplusD = eps * (g + dy) = 3.18 * 7.62` → ~$24.23
- `Lynch_Category = "Slow"` (g < 10)
- `Lynch_BuyPrice = 24.23 * 0.75` → ~$18.17
- `Lynch_Discount_Pct = (1 - 79.86 / 18.17) * 100` → **large negative (~−340%)** — KO is FAR above its Lynch buy target
- `LV_Ratio = 79.86 / 24.23` → ~3.3 → `Lynch_Status = "Avoid"` (lv > 1.3)

Step 2 — Graham:
- `g_capped = min(5, 15) = 5`
- `Graham_VA = 3.18 * (8.5 + 10) * 4.4/5.3` → `3.18 * 18.5 * 0.8302` → ~$48.77
- `Graham_VB = 3.18 * (7 + 5) * 4.4/5.3` → `3.18 * 12 * 0.8302` → ~$31.67
- `Graham_FV = min(48.77, 31.67) = 31.67`
- `Graham_Discount_Pct = (1 - 79.86/31.67) * 100` → **large negative (~−152%)**
- `Graham_Status = "Avoid"`

The fixture confirms KO is correctly rated "Avoid" by both models at current prices. The "Buy Price visibly wrong" complaint is almost certainly from users expecting Lynch/Graham buy prices to be near the current market price for blue-chip stocks — they are correct that the models produce very low target prices for expensive quality franchises, but that is the model's intended conservative behavior.

**The fixture should encode the exact computed values with ±0.1 tolerance on rounding.** If the code produces significantly different outputs from these hand-computations, the discrepancy is the bug.

---

## Standard Stack

### Core (all already in the project — no new installations)
| Component | Version | Purpose |
|-----------|---------|---------|
| Python 3.11 | existing | Pipeline computation |
| Tabulator | 6.4.0 via CDN | Dashboard table (index.html) |
| Vanilla JS + CSS | — | top.html, app.js |

### No New Packages Required

Phase 5 explicitly constrains itself to existing data and libraries. All scoring is pure Python using existing imports (`math`, `json`, `pandas`). No new `pip install` needed.

## Package Legitimacy Audit

> Not applicable — Phase 5 installs zero new external packages. All computation uses Python stdlib and existing project dependencies.

---

## Architecture Patterns

### System Architecture Diagram

```
Python Pipeline (stock_screener.py)
─────────────────────────────────────────────────────────────────
get_combined_data()
  ├── Finnhub metric=all bundle (already fetched)
  │     └── stop discarding: extract freeCashFlowPerShareAnnual
  │                          extract freeCashFlowPerShareTTM (fallback)
  └── Returns enriched dict with fcf_per_share field

process_ticker()
  ├── FIX-01/02:
  │     ├── lynch_metrics()  → Lynch_Discount_Pct (verified correct)
  │     └── graham_metrics() → Graham_Discount_Pct (verified correct)
  │     [D-01: negative EPS/g → route to worst-score instead of error-return]
  │
  ├── TRAP-01:
  │     ├── inputs: debt_equity, current_ratio, EPS_Stability, fcf_per_share
  │     └── trap_gate() → is_trap (bool)
  │
  ├── SCORE-01..08:
  │     ├── value sub-scores: discount_group_avg → score_value
  │     ├── quality sub-scores: defensive_score_sub + debt_eq_sub + curr_ratio_sub → score_quality
  │     ├── growth sub-scores: growth_level_sub + growth_stability_sub → score_growth
  │     └── safety sub-score: trap_gate result (D-03: tripped → 0, else partial credit) → score_safety
  │           → overall_score()
  │           → OverallScore, score_value, score_quality, score_growth, score_safety
  │
  └── row dict assembled with:
        flat columns: OverallScore, score_value, score_quality, score_growth, score_safety, is_trap
        nested: scores = {overall, value, quality, growth, safety, coverage_pct}

write_json()
  └── row dicts → JSON with nested scores object preserved

Frontend (static)
─────────────────────────────────────────────────────────────────
docs/app.js  ← extracted from index.html
  ├── SIGNAL_COLORS, COLOR_STYLES
  ├── makeSignalFormatter(), numFmt(), pctFmt()
  ├── updateFreshnessUI()
  └── buildNav(activePage)   ← new

docs/index.html  ← modified
  ├── <script src="app.js"> (load app.js before page script)
  ├── new columns: OverallScore, score_value, score_quality, score_growth, score_safety, is_trap
  ├── SUMMARY_COLS: add OverallScore, is_trap
  └── initialSort: CombinedScore → OverallScore

docs/top.html  ← new
  ├── fetch results.json?v=Date.now()
  ├── sort by OverallScore desc, slice top N
  ├── render ranked cards (mockup from UI-SPEC)
  └── buildNav("top")

docs/methodology.html  ← add app.js load + buildNav("methodology")
docs/style.css  ← add .top-card, .score-badge, .trap-badge, .pillar-chip
```

### Recommended Project Structure

No structural changes needed — Phase 5 adds files within the existing layout:
```
docs/
├── app.js          ← NEW: shared primitives
├── top.html        ← NEW: Top 10/25 page
├── index.html      ← MODIFY: load app.js, add score columns
├── methodology.html ← MODIFY: load app.js, add nav
└── style.css       ← MODIFY: add card/badge/chip styles
stock_screener.py   ← MODIFY: scoring engine + trap gate + FCF field
```

---

## FCF Field in Finnhub metric=all Bundle

[ASSUMED] — Field name derived from documented Finnhub API behavior and community sources; not confirmed by running the live API in this session.

The Finnhub `stock/metric?metric=all` call already made in `get_finnhub_metrics()` returns a `metric` dict with ~117 fields for US large-cap tickers. Community sources confirm the following FCF-related fields exist in the response:

| Field name | Expected type | Notes |
|------------|--------------|-------|
| `freeCashFlowPerShareAnnual` | float | Annual FCF per share — primary field to use |
| `freeCashFlowPerShareTTM` | float | TTM variant — fallback |
| `currentEv/freeCashFlowAnnual` | float | EV/FCF ratio — NOT the FCF amount itself |
| `fcfMargin` (in series) | float | FCF margin from annual series — not in flat metric dict |

**How to read FCF sign without a new fetch:**

```python
# In get_combined_data() — after fetching fh = get_finnhub_metrics(ticker)
fcf_per_share = _safe_float(
    fh.get("freeCashFlowPerShareAnnual") or fh.get("freeCashFlowPerShareTTM")
)
```

Return this in the `get_combined_data()` dict as `"fcf_per_share": fcf_per_share`.

**Coverage note:** `freeCashFlowPerShareAnnual` is present for most S&P 500 tickers but has gaps. Per STATE.md, Finnhub free-tier field coverage across the 550-ticker universe is unconfirmed. Phase 5 only uses the sign (negative FCF = trap), so a missing field triggers D-01b (coverage flag + run gate on remaining 3 inputs), not a hard failure.

**Verification task for the executor:** Add `freeCashFlowPerShareAnnual` and `freeCashFlowPerShareTTM` to the `fields_of_interest` list in `diagnose_finnhub.py` and run it for KO, AAPL, MSFT before encoding the scoring. This will confirm the exact field name and typical values. [ASSUMED: the field exists under these names]

---

## Scoring Engine Design

### overall_score() function

New pure function, no side effects:

```python
def overall_score(
    lynch_discount: float | None,
    graham_discount: float | None,
    defensive_score: float | None,
    debt_equity: float | None,
    current_ratio: float | None,
    growth_g: float | None,
    growth_stability: float | None,
    is_trap: bool,
    aaa_yield: float,
) -> dict:
    """
    Compute 4-pillar absolute OverallScore (0-100).
    Returns dict with overall, value, quality, growth, safety, coverage_pct.
    """
```

### Negative-Input Routing (D-01)

The current code in `lynch_metrics()` at line 348–349:
```python
if eps <= 0 or g <= 0:
    return {"error": "Non-positive EPS or growth"}
```

This causes `process_ticker()` to set `row["Error"] = ...` and return early — the stock is dropped from scoring. Under D-01, these must instead produce worst-possible sub-scores.

**Migration pattern:**
1. Remove the early-return guard in `lynch_metrics()` and `graham_metrics()`.
2. In `process_ticker()`, when EPS ≤ 0: compute Lynch/Graham metrics with a sentinel value that maps to 0 sub-score. The simplest approach: call `lynch_metrics()` and `graham_metrics()` normally but detect the negative condition in `overall_score()` and floor the sub-score to 0.
3. Pass `negative_eps=True` and `negative_growth=True` flags alongside the metrics dict.

Alternative: Keep the early-return in `lynch_metrics()`/`graham_metrics()` but have `process_ticker()` catch the `{"error": ...}` return and route to `overall_score()` with worst-case sub-scores rather than dropping the row. This is less invasive.

**Recommended: the alternative (less invasive).** Intercept `{"error": ...}` returns in `process_ticker()` and set discount columns to a sentinel value (e.g., `WORST_DISCOUNT = -999.0`) that the scoring engine maps to sub-score 0.

### Value Pillar Grouping (SCORE-07)

Per D-02 / SCORE-07: `Lynch_Discount_Pct` and `Graham_Discount_Pct` are correlated (both are price-discount relative to buy price). Group them as one "discount" sub-factor:

```python
discount_group = avg_present([lynch_discount_sub, graham_discount_sub])
score_value = avg_present([discount_group])  # single sub-group in Phase 5
```

In Phase 6, `fcf_yield_sub`, `ev_ebit_sub` become a second sub-group averaged into `score_value`. The two-level structure is established now, even with one group.

### Missing-Data Rule (SCORE-04 / D-01b)

```python
def avg_present(values: list) -> float | None:
    """Average over non-None values. Returns None if all are absent."""
    present = [v for v in values if v is not None]
    return sum(present) / len(present) if present else None
```

Apply at both levels: within a sub-group, and across pillars. Track how many sub-scores were present vs total for the `coverage_pct` field.

---

## Piecewise-Linear Band Design

### How piecewise-linear mapping works

Each raw metric maps to [0, 100] through fixed threshold bands. Between bands, the score interpolates linearly. This produces smooth scores that are robust to small data movements around a threshold.

```python
def piecewise_score(value: float, bands: list[tuple]) -> float:
    """
    bands: [(raw_lo, raw_hi, score_lo, score_hi), ...]
    sorted ascending by raw_lo.
    values below the first band → score_lo of first band (0).
    values above the last band → score_hi of last band (100).
    """
    for (raw_lo, raw_hi, score_lo, score_hi) in bands:
        if value <= raw_hi:
            t = (value - raw_lo) / (raw_hi - raw_lo) if raw_hi != raw_lo else 0
            return score_lo + t * (score_hi - score_lo)
    return bands[-1][2]  # fallback: score_lo of last band
```

### Proposed Thresholds (all [ASSUMED] — loud config constants, expect tuning)

All thresholds below are first-pass estimates with no empirical anchor. They are encoded as `SCORE_*` constants and monitored via `stats.html` (Phase 7).

#### Value: Discount sub-scores

Lynch_Discount_Pct and Graham_Discount_Pct are first winsorized to `[SCORE_DISC_WIN_LO, SCORE_DISC_WIN_HI]`.

```python
SCORE_DISC_WIN_LO = -100.0   # below -100% → floor at -100
SCORE_DISC_WIN_HI =  60.0    # above 60% → cap at 60 (matches existing CombinedScore clip)

SCORE_DISC_BANDS = [
    # (raw_lo, raw_hi, score_lo, score_hi)
    (-100.0, -30.0,  0,  10),  # very expensive
    ( -30.0,   0.0, 10,  40),  # modestly expensive
    (   0.0,  15.0, 40,  70),  # cheap (near buy target)
    (  15.0,  30.0, 70,  90),  # significantly cheap
    (  30.0,  60.0, 90, 100),  # deep value territory
]
```

Negative discount (stock above buy price) gets a low-but-nonzero score (not 0) because the Graham/Lynch framework already flags it as "Avoid" — the discount metric adds texture to the composite, not a veto.

#### Quality: DefensiveScore (0–8 raw)

```python
SCORE_DEF_BANDS = [
    (0, 2,  0, 20),
    (2, 4, 20, 50),
    (4, 6, 50, 80),
    (6, 8, 80, 100),
]
```

#### Quality: Debt/Equity ratio

Lower debt/equity = better. Winsorize `[0, SCORE_DE_WIN_HI]`.

```python
SCORE_DE_WIN_HI = 5.0   # above 5.0 → cap (extreme leverage)
SCORE_DE_BANDS = [
    (0.0, 0.5, 100, 90),   # minimal debt
    (0.5, 1.0,  90, 70),   # moderate
    (1.0, 2.0,  70, 40),   # elevated
    (2.0, 5.0,  40,  0),   # high leverage
]
```

Note: direction is inverted (higher D/E → lower score). Negative D/E (negative equity) → D-01 worst-possible = 0.

#### Quality: Current Ratio

```python
SCORE_CR_BANDS = [
    (0.0, 1.0,  0, 30),   # below 1.0 = technically illiquid
    (1.0, 1.5, 30, 60),
    (1.5, 2.0, 60, 80),
    (2.0, 4.0, 80, 100),
    (4.0, 8.0, 100, 90),  # above 4 is fine; above 8 may signal hoarding
]
# Winsorize: [0, SCORE_CR_WIN_HI = 8.0]
SCORE_CR_WIN_HI = 8.0
```

#### Growth: Growth level (g, already capped at GROWTH_CAP=25%)

```python
SCORE_G_BANDS = [
    ( 0.0,  3.0,   0, 20),   # near-zero or slow
    ( 3.0,  7.0,  20, 50),   # slow grower
    ( 7.0, 12.0,  50, 75),   # moderate
    (12.0, 20.0,  75, 90),
    (20.0, 25.0,  90, 100),
]
```

Negative g → D-01 worst = 0.

#### Growth: Growth stability

Derived from `annual_eps` array: count of years where EPS was positive and didn't decline > 20% YoY, expressed as a fraction 0–1 multiplied by 100.

```python
SCORE_GSTAB_STABLE_PCT = 0.8   # 80%+ stable years → full marks
SCORE_GSTAB_BANDS = [
    (0.0, 0.4,   0, 20),
    (0.4, 0.6,  20, 50),
    (0.6, 0.8,  50, 80),
    (0.8, 1.0,  80, 100),
]
```

If `annual_eps` has fewer than 3 years → treat as missing (D-01b).

#### Safety: Trap gate result

Under D-03: tripped gate → Safety score = 0 (worst-possible).

For a non-tripped row with full coverage: Safety score = 60 (interim baseline — "not trapped" is a positive signal, but Phase 7 Altman/Piotroski will provide real granularity).
For a non-tripped row with partial coverage (some gate inputs missing): Safety score = `60 * coverage_fraction` — partial credit scaled by how many trap checks passed.

```python
SCORE_SAFETY_TRAP_PENALTY = 0  # Safety floor when trap is tripped (D-03)
SCORE_SAFETY_NOTRAP_BASE  = 60 # Interim baseline for non-trapped (no Altman/Piotroski yet)
```

#### Rate-relativization for yield-based thresholds (SCORE-06 / D-02b)

The AAA yield is already fetched and stored in `aaa_yield`. For thresholds that implicitly depend on the interest rate environment, scale them:

```python
SCORE_AAA_REFERENCE = 4.4   # Graham's 1963 reference yield
# Relative thresholds scale by (SCORE_AAA_REFERENCE / aaa_yield)
# Applied to discount thresholds: a 15% discount is less impressive when rates are high
```

In Phase 5, the simplest approach: apply the scaling only to the discount band thresholds. The exact bands above assume `aaa ≈ 4.4%`; at higher rates, scale the `raw_lo/raw_hi` break-points by `SCORE_AAA_REFERENCE / aaa_yield`. This is a one-line adjustment and makes the thresholds rate-aware.

---

## Winsorization Strategy (SCORE-03)

Apply winsorization before piecewise mapping, not after. Both tails:

```python
def winsorize(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
```

Each metric has its own `SCORE_*_WIN_LO` and `SCORE_*_WIN_HI` constant. Typical bounds:

| Metric | WIN_LO | WIN_HI |
|--------|--------|--------|
| Lynch/Graham discount | -100.0 | 60.0 |
| DefensiveScore | 0.0 | 8.0 |
| debt_equity | 0.0 | 5.0 |
| current_ratio | 0.0 | 8.0 |
| growth g | 0.0 | 25.0 (= GROWTH_CAP) |
| growth_stability | 0.0 | 1.0 |

Negative winsorization lower bound at 0.0 for structural metrics (debt_equity, current_ratio) — a negative value triggers D-01 worst-score, not the winsorize path.

---

## Value-Trap Gate (TRAP-01)

### Gate inputs and thresholds

```python
TRAP_MAX_DE          = 2.0    # debt/equity above this trips the gate
TRAP_MIN_CR          = 1.0    # current_ratio below this trips the gate
TRAP_MIN_EPS_STAB    = False  # EPS_Stability (0/1 from defensive score) — trips if 0
TRAP_NEG_FCF         = True   # negative FCF trips the gate
```

### Gate logic

```python
def trap_gate(
    debt_equity: float | None,
    current_ratio: float | None,
    eps_stability: int | None,  # 0 or 1 from defensive checks
    fcf_per_share: float | None,
) -> tuple[bool, float]:
    """
    Returns (is_trap, coverage_fraction).
    is_trap: True if any present input trips the gate.
    coverage_fraction: fraction of inputs that were present (not None).
    """
    checks = []
    if debt_equity is not None:
        checks.append(debt_equity > TRAP_MAX_DE)
    if current_ratio is not None:
        checks.append(current_ratio < TRAP_MIN_CR)
    if eps_stability is not None:
        checks.append(eps_stability == 0)
    if fcf_per_share is not None:
        checks.append(fcf_per_share < 0)
    # is_trap if ANY present check fires
    is_trap = any(checks)
    coverage = len(checks) / 4  # 4 possible inputs
    return is_trap, coverage
```

The `coverage_fraction` of Safety feeds into the D-01b Safety sub-score scaling: `SCORE_SAFETY_NOTRAP_BASE * coverage_fraction`.

---

## JSON Schema Extension (SCORE-05)

### Additive schema rule

Do NOT rename or remove any existing keys. Add new keys alongside existing ones.

**New flat columns added to each row dict:**
- `OverallScore` — float (0–100) or null
- `score_value` — float (0–100) or null
- `score_quality` — float (0–100) or null
- `score_growth` — float (0–100) or null
- `score_safety` — float (0–100) or null
- `is_trap` — boolean
- `coverage_pct` — float (0–100), percentage of sub-scores present

**Nested `scores` object (alongside flat columns):**
```json
"scores": {
  "overall": 72.4,
  "value": 45.2,
  "quality": 81.0,
  "growth": 63.5,
  "safety": 60.0,
  "coverage_pct": 87.5,
  "trap": false
}
```

Both representations are included: flat for Tabulator column access in `index.html`, nested for `top.html`'s programmatic access and future API consumers.

### Implementation in process_ticker() + write_json()

`process_ticker()` assembles `scores_dict = overall_score(...)` and merges it into the row:

```python
scores = overall_score(...)  # returns dict with overall, value, quality, growth, safety, coverage_pct
row["OverallScore"]   = scores["overall"]
row["score_value"]    = scores["value"]
row["score_quality"]  = scores["quality"]
row["score_growth"]   = scores["growth"]
row["score_safety"]   = scores["safety"]
row["is_trap"]        = is_trap
row["coverage_pct"]   = scores["coverage_pct"]
row["scores"]         = scores  # nested object
```

`write_json()` currently does `json.loads(df.to_json(orient="records"))`. The `scores` dict column will serialise correctly through this path — pandas stores dict-valued cells as objects and `to_json` with `orient="records"` preserves them. No change to `write_json()` required for the nested object.

**Verify:** Test that `df.to_json(orient="records")` does not flatten the nested dict. In practice, pandas stores dict objects as Python objects in the DataFrame and serialises them correctly. If there are issues, pre-serialise the `scores` column as a JSON string and parse it in the frontend.

---

## app.js Extraction (PAGE-03)

### Functions to extract from docs/index.html

All extractions are cut-paste from the inline `<script>` block (lines 72–356):

| Function/Const | Lines (approx) | Changes on extraction |
|---|---|---|
| `SIGNAL_COLORS` | 80–102 | none |
| `COLOR_STYLES` | 104–108 | none |
| `makeSignalFormatter(field)` | 111–125 | none |
| `numFmt(decimals)` | 128–135 | none |
| `pctFmt(cell)` | 138–142 | none |
| `updateFreshnessUI(generatedAt)` | 240–251 | none |
| `buildNav(activePage)` | NOT YET EXISTS | new function (see below) |

**What stays in index.html's inline script (page-specific):**
- `buildColumns()` — dashboard-specific column definitions
- `SUMMARY_COLS` — dashboard-specific preset
- `noErrorFilter` — shared candidate but simple enough to inline
- `applyPreset()` — dashboard-specific
- The main `fetch(...).then(...)` block
- All event listeners

### buildNav() specification

```javascript
// In app.js — array-driven so adding a 4th entry is a one-line change
var NAV_ENTRIES = [
  { label: "Dashboard",    href: "index.html",       key: "dashboard" },
  { label: "Top Picks",    href: "top.html",          key: "top" },
  { label: "Methodology",  href: "methodology.html",  key: "methodology" },
  // Phase 7: { label: "Stats", href: "stats.html", key: "stats" }
];

function buildNav(activePage) {
  var nav = document.querySelector("nav.main-nav");
  if (!nav) return;
  nav.innerHTML = NAV_ENTRIES.map(function(e) {
    var cls = "nav-link" + (e.key === activePage ? " active" : "");
    var aria = e.key === activePage ? ' aria-current="page"' : "";
    return '<a href="' + e.href + '" class="' + cls + '"' + aria + '>' + e.label + '</a>';
  }).join("");
}
```

### Loading order in each HTML file

```html
<!-- In index.html, top.html, methodology.html -->
<script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6.4.0/dist/js/tabulator.min.js"></script>
<!-- load app.js AFTER tabulator, BEFORE page-specific script -->
<script src="app.js"></script>
<script>
  // page-specific code
  buildNav("dashboard");  // or "top", "methodology"
  // ... rest of page script
</script>
```

`app.js` uses `var`/`function` declarations (no `const`, no ES modules) to match the existing `index.html` convention and to be importable without a module system.

---

## top.html Implementation Notes

The UI-SPEC (05-UI-SPEC.md) is the definitive contract. Key implementation notes for the planner:

### Data flow
```javascript
fetch("data/results.json?v=" + Date.now())
  .then(function(r) { return r.json(); })
  .then(function(data) {
    updateFreshnessUI(data.generated_at);
    buildNav("top");
    var rows = data.rows
      .filter(function(r) { return !r.Error; })   // noErrorFilter equivalent
      .sort(function(a, b) { return (b.OverallScore || 0) - (a.OverallScore || 0); });
    renderTopN(rows, currentN);  // currentN = 10 initially
  });
```

### Card rendering

Each card reads flat columns from the row object: `r.OverallScore`, `r.score_value`, `r.score_quality`, `r.score_growth`, `r.score_safety`, `r.is_trap`, `r.Price`, `r.Lynch_Lynch_Status`, `r.Graham_Graham_Status`, `r.DefensiveLabel`.

Note the double-prefix keys for Lynch/Graham columns: `Lynch_Lynch_Status`, `Graham_Graham_Status` — these are the actual JSON field names (from the `process_ticker()` pattern `{f"Lynch_{k}": v for k, v in lm.items()}` where k is already `Lynch_Status`). The UI-SPEC notes these must match exactly.

### 10/25 toggle

On toggle click: update `currentN`, re-slice the already-sorted rows array, re-render. No refetch.

---

## run_screener Sort Swap (SCORE-08)

One-line change in `run_screener()`:

```python
# Before:
df = df.sort_values("CombinedScore", ascending=False, na_position="last")
# After:
df = df.sort_values("OverallScore", ascending=False, na_position="last")
```

`CombinedScore` column is retained in the DataFrame — only the sort key changes.

---

## Common Pitfalls

### Pitfall 1: D-01 / D-01b Conflation

**What goes wrong:** Treating a negative EPS as "missing" (averaging-over-present) rather than "present and terrible" (worst sub-score 0). A stock with negative EPS gets an average-over-present sub-score instead of 0, which inflates its score.

**How to avoid:** Two distinct code paths gated on whether the value is `None` vs. negative. `None` → D-01b. Negative-but-present → D-01 (0 for that sub-score).

**Warning signs:** A stock with negative EPS appearing high in the OverallScore ranking.

### Pitfall 2: FV_GplusD = 0 when dividend yield = 0 and g is capped at 1

**What goes wrong:** A non-dividend payer with g floored to 1% gets `FV_GplusD = eps * (1 + 0) = eps`. Then `Lynch_BuyPrice = eps * 0.75` (for Slow). The buy price is less than 1x earnings, which looks absurd and creates a very large negative discount for almost all tickers.

**Current behavior:** The growth floor at 1.0 was intended to avoid dividing by zero, not to produce sensible buy prices. Under D-01, negative growth routes to worst sub-score, bypassing the Lynch formula entirely.

**How to avoid:** Under D-01, `lynch_metrics()` early-return on `g <= 0` produces `{"error": ...}`. Intercept this in `process_ticker()` and set `Lynch_Discount_Pct = SCORE_WORST_DISCOUNT` before calling `overall_score()`.

### Pitfall 3: Nested dict in pandas DataFrame

**What goes wrong:** `row["scores"] = {...}` inside `process_ticker()` creates a dict-valued column. `df.to_json(orient="records")` may emit it as a nested object (correct) or stringify it unexpectedly depending on pandas version.

**How to avoid:** Test `df.to_json(orient="records")` on a single row with a dict-valued column before integrating. Alternative: build the `scores` nested object directly in `write_json()` rather than storing it in the DataFrame — iterate `rows = json.loads(df.to_json(...))`, then for each row: `row["scores"] = {"overall": row.get("OverallScore"), ...}`.

**Preferred approach:** Build nested `scores` in `write_json()` after serialization. This avoids any pandas dict-column edge cases and keeps the DataFrame clean.

### Pitfall 4: app.js double-load in index.html

**What goes wrong:** If `buildColumns()` or other dashboard functions reference `SIGNAL_COLORS` before `app.js` finishes loading, the table breaks. Also: if `app.js` is loaded after the page-specific `<script>` block, `buildNav()` is not defined at call time.

**How to avoid:** Load `<script src="app.js"></script>` before the page-specific `<script>` block, after Tabulator. Call `buildNav()` inside the `fetch().then()` handler (already loaded by then) or at DOMContentLoaded.

### Pitfall 5: SIGNAL_COLORS keys use double-prefix naming

**What goes wrong:** `SIGNAL_COLORS` maps `"Lynch_Lynch_Status"` (not `"Lynch_Status"`) because the row-assembly pattern prefixes `Lynch_` onto all keys returned by `lynch_metrics()`, which already contains `Lynch_Status`. If `top.html` or `app.js` uses `"Lynch_Status"` directly, the color lookup fails silently.

**How to avoid:** Copy `SIGNAL_COLORS` verbatim from `index.html:80` into `app.js` — the double-prefix keys are intentional. Do not "fix" them.

### Pitfall 6: .gitignore *.json — results.json coverage

**What goes wrong:** `results.json` is already excepted via `!docs/data/results.json`. No new JSON files are added in Phase 5. If a developer adds a test fixture JSON file, it may be silently ignored.

**How to avoid:** Phase 5 uses Python assert/pytest for the KO fixture — no JSON fixture files. If a JSON fixture is used, add `!path/to/fixture.json` to `.gitignore`.

---

## Code Examples

### Piecewise-Linear Scorer Pattern

```python
# Source: [ASSUMED — standard pattern, no external source]
def _piecewise_score(value: float, bands: list) -> float:
    """
    Map a raw value to [0, 100] via linear interpolation between breakpoints.
    bands: list of (raw_lo, raw_hi, score_lo, score_hi) tuples, sorted by raw_lo.
    """
    for (raw_lo, raw_hi, score_lo, score_hi) in bands:
        if value <= raw_hi:
            if raw_hi == raw_lo:
                return float(score_lo)
            t = (value - raw_lo) / (raw_hi - raw_lo)
            t = max(0.0, min(1.0, t))
            return score_lo + t * (score_hi - score_lo)
    return float(bands[-1][3])  # above all bands → score_hi of last band
```

### avg_present Pattern

```python
# Source: [ASSUMED — standard pattern]
def _avg_present(values: list) -> float | None:
    """Average over non-None values. Returns None if all absent."""
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None
```

### Write nested scores object in write_json()

```python
# Source: [ASSUMED — based on existing write_json() pattern]
def write_json(df: pd.DataFrame) -> None:
    if len(df) < 100:
        log.error(f"Only {len(df)} rows — aborting (minimum 100 required)")
        sys.exit(1)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = json.loads(df.to_json(orient="records"))
    # Build nested scores object post-serialization (avoids pandas dict-column edge cases)
    for row in rows:
        row["scores"] = {
            "overall":      row.get("OverallScore"),
            "value":        row.get("score_value"),
            "quality":      row.get("score_quality"),
            "growth":       row.get("score_growth"),
            "safety":       row.get("score_safety"),
            "coverage_pct": row.get("coverage_pct"),
            "trap":         row.get("is_trap", False),
        }
    payload = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows,
    }
    OUTPUT_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    log.info(f"Results written to {OUTPUT_PATH} ({len(rows)} rows)")
```

### KO Fixture Structure

```python
# Source: [ASSUMED — hand-computed from publicly available KO financials]
# tests/test_valuation_fixture.py (or equivalent)

KO_INPUTS = {
    "price":     79.86,   # approximate — must be updated to actual value at run time
    "eps":        3.18,   # TTM EPS approximate
    "g":          5.0,    # % — approximate 5Y EPS CAGR
    "dy":         2.62,   # % — approximate dividend yield
    "aaa_yield":  5.3,    # % — approximate FRED AAA yield
}

KO_EXPECTED = {
    "Lynch_Category":     "Slow",
    "Lynch_BuyPrice":     18.17,   # ± 0.50 tolerance (hand-computed)
    "Lynch_Discount_Pct": -339.0,  # large negative — KO far above buy target, ± 10
    "Lynch_Status":       "Avoid",
    "Graham_VA":          48.77,   # ± 1.0
    "Graham_VB":          31.67,   # ± 1.0
    "Graham_FV":          31.67,   # VB is the conservative (lower) value
    "Graham_Status":      "Avoid",
    "Graham_Discount_Pct": -152.0, # large negative, ± 5
}

# The fixture CONFIRMS the formulas compute correctly.
# KO at $80 is "Avoid" by both models — this is expected and correct.
# If the code produces materially different values, THAT is the bug.
```

---

## Environment Availability

| Dependency | Required By | Available | Notes |
|------------|------------|-----------|-------|
| Python 3.11 | Pipeline | ✓ | Existing CI workflow |
| pandas | write_json | ✓ | Existing requirement |
| fredapi | AAA yield | ✓ | Existing requirement |
| Finnhub API key | FCF field read | ✓ | Already in use |
| jsDelivr CDN (Tabulator 6.4.0) | top.html | ✓ | Already in production |
| Google Fonts CDN | style.css | ✓ | Already in production |

No new dependencies. Phase 5 is entirely self-contained.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `CombinedScore` = 0.5 * Lynch_disc + 0.5 * Graham_disc | `OverallScore` = 4-pillar absolute score | Phase 5 | Primary sort key changes; richer ranking |
| Negative EPS/growth → drop the ticker | Negative inputs → worst sub-score; ticker retained | Phase 5 | Distressed companies now show up ranked at bottom instead of hidden |
| Finnhub metric=all bundle — most fields discarded | Bundle fields preserved; FCF sign extracted | Phase 5 | No new network calls; data previously fetched and discarded now used |
| Nav: Dashboard, Methodology (2 links) | Nav: Dashboard, Top Picks, Methodology (3 links) | Phase 5 | Shared via buildNav() in app.js |

**Deprecated/outdated:**
- `combined_score()` function: still called, result kept as `CombinedScore` column. Primary sort replaced by `OverallScore`. Do NOT remove.
- The g=1.0 floor in `process_ticker()`: removed under D-01. Negative growth now routes to worst sub-score path.

---

## Project Constraints (from CLAUDE.md)

- `.gitignore` has `*.json` — any new JSON file (e.g., test fixtures) needs an explicit `!path/to/file.json` exception. Phase 5 uses Python fixtures, not JSON files — no new exception needed.
- Cache-bust the `results.json` fetch: `?v=${Date.now()}` — required in both `index.html` (existing) and new `top.html`.
- Minimum-row guard on JSON write: abort if < 100 rows — existing in `write_json()`, must not be removed.
- `GITHUB_TOKEN` permissions: not affected by Phase 5 (no new CI workflow changes).
- Surgical changes only — do not refactor adjacent code outside the task scope. The `push_to_gsheets()` function still exists in Phase 5 (CLN-01 is Phase 4); do not touch it.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Finnhub `freeCashFlowPerShareAnnual` exists as a field name in metric=all response | FCF Field in Finnhub bundle | Gate has wrong field name; FCF always reads None; all rows run on 3/4 gate inputs. Fix: run diagnose_finnhub.py to confirm exact key. |
| A2 | KO price ~$79.86, EPS ~$3.18, g ~5%, dy ~2.62%, AAA ~5.3% in June 2026 | KO Fixture | Fixture values will be stale by execution time. Executor must update from live data before encoding. |
| A3 | The "Buy Price visibly wrong" bug is model conservatism (VB produces low FV for quality stocks), not a code defect | Buy Price Bug Analysis | If a code defect exists, the KO fixture will catch it. The fixture is the verification mechanism. |
| A4 | pandas `df.to_json(orient="records")` preserves dict-valued columns as nested JSON objects | JSON Schema Extension | If pandas version behaves differently, use post-serialization nested-object construction in write_json() (recommended anyway). |
| A5 | `freeCashFlowPerShareTTM` is the correct fallback field name when `freeCashFlowPerShareAnnual` is absent | FCF Field | Wrong field name → FCF always None. Diagnose first. |

---

## Open Questions

1. **What is the exact FCF field name in Finnhub metric=all for US tickers?**
   - What we know: Community sources suggest `freeCashFlowPerShareAnnual` and `freeCashFlowPerShareTTM` exist; RobotWealth article confirms `fcfMargin` in series and `fcfPerShareTTM` may be in quarterly data.
   - What's unclear: The exact key name (camelCase variants, Annual vs TTM, per-share vs total).
   - Recommendation: Run `diagnose_finnhub.py` for KO and AAPL with all metric keys printed; add the FCF-related keys to the `fields_of_interest` list before coding the gate. This is a 10-minute task at execution start.

2. **Is the growth-stability formula measuring the right thing?**
   - What we know: `annual_eps` from yfinance typically returns 4–5 years of data.
   - What's unclear: Whether year-over-year positive EPS and < 20% decline captures what Lynch calls "stalwart" stability vs "fast grower" volatility.
   - Recommendation: Use the fraction of years with positive EPS (already computed as `EPS_Stability` in the defensive score) as the primary signal. This reuses existing computation and avoids a new formula. Growth-stability = `(count of positive EPS years in available history) / (total years)`.

3. **Should the KO fixture be a pytest test or an inline assertion in the script?**
   - What we know: The project has no test suite (per CONCERNS.md). CLAUDE.md says `nyquist_validation = false` in config.
   - Recommendation: A standalone `tests/test_valuation_fixture.py` with vanilla Python `assert` statements (no pytest dependency needed for basic asserts). This is a committed verification artifact that future passes can expand. Do not add pytest to requirements.txt unless the user explicitly requests a test framework.

---

## Sources

### Primary (HIGH confidence — code-derived)
- `stock_screener.py` — direct code reading of `lynch_metrics()`, `graham_metrics()`, `combined_score()`, `process_ticker()`, `run_screener()`, `write_json()`, `get_combined_data()`, `get_finnhub_metrics()` (lines 188–705) [VERIFIED: code]
- `docs/index.html` — direct reading of inline script (lines 72–356): `SIGNAL_COLORS`, `makeSignalFormatter()`, `numFmt()`, `pctFmt()`, `updateFreshnessUI()`, `applyPreset()`, `noErrorFilter` [VERIFIED: code]
- `docs/style.css` — Nord palette tokens, `.main-nav`, `.btn-pill`, `.stale-banner`, `.freshness-badge` [VERIFIED: code]
- `05-CONTEXT.md` — locked decisions D-01 through D-05 [VERIFIED: planning artifact]
- `05-UI-SPEC.md` — component contract for top.html and app.js [VERIFIED: planning artifact]

### Secondary (MEDIUM confidence)
- Graham intrinsic value formula (1962 and 1974 revised): [CITED: grahamvalue.com/article/understanding-benjamin-graham-formula-correctly] — confirmed original `8.5 + 2g` formula and 1974 rate-adjusted revision with `4.4/Y`.
- Lynch fair value principle (PEGY inverse, P/E = growth rate): [CITED: stablebread.com/peter-lynch-stock-valuation/] — confirmed the G+D / PEGY framework.

### Tertiary (LOW confidence — unverified Finnhub field names)
- Finnhub FCF field names (`freeCashFlowPerShareAnnual`, `freeCashFlowPerShareTTM`): [ASSUMED] — not confirmed from official Finnhub docs; derived from community sources and the presence of `currentEv/freeCashFlowAnnual` in documented responses.
- KO June 2026 financials (price, EPS, yield): [ASSUMED] — from web search approximations; must be verified at execution time.

---

## Metadata

**Confidence breakdown:**
- Buy Price audit: HIGH — direct code reading against canonical formula definitions
- Formula defect identification: MEDIUM — identified likely causes; KO fixture will confirm
- Scoring engine design: HIGH — pattern is standard; thresholds are [ASSUMED] and explicitly flagged
- Finnhub FCF field names: LOW — executor must verify with diagnose_finnhub.py before coding
- app.js extraction plan: HIGH — direct code reading; all functions identified with line numbers
- top.html card spec: HIGH — from 05-UI-SPEC.md design contract

**Research date:** 2026-06-18
**Valid until:** 2026-07-18 (stable domain; threshold values will need tuning after first real run)
