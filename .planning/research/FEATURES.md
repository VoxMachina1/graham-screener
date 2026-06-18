# Feature Research

**Domain:** Multi-factor value-stock screener (valuation signals + absolute 0–100 composite scoring) for a static GitHub Pages dashboard
**Researched:** 2026-06-17
**Confidence:** HIGH (canonical factor formulas are textbook-stable; project design constraints are locked in `v2-METHODOLOGY-EXPANSION.md`)

> Scope note: This file covers ONLY the v2.0 NEW capabilities (new valuation factors + the 4-pillar absolute composite). Existing Lynch/Graham/defensive/CombinedScore behavior is treated as a given dependency, not re-researched. Each factor below carries a concrete formula, standard inputs, threshold conventions, failure modes, a table-stakes/differentiator/anti-feature classification for THIS screener, complexity, and its dependency on existing outputs.

---

## Canonical Factor Definitions

This section is the implementable spec each requirement should be written against. All factors map to a bounded **0–100 sub-score** downstream (see "Absolute-Threshold Scoring Mechanics").

### 1. Piotroski F-Score (0–9)

**What it predicts:** Fundamental-trend quality / value-trap filter. Piotroski (2000) showed that, within the cheapest book-to-market quintile, buying high-F (8–9) and shorting low-F (0–1) earned ~23%/yr. It is the single best *quality cross-check* for a value screen — it separates "cheap and improving" from "cheap and dying."

**Inputs:** Requires **two consecutive fiscal years** of income statement, balance sheet, and cash-flow statement. This is the heaviest data dependency in the milestone.

**The 9 binary tests (1 point each):**

Profitability (4):
1. **ROA > 0** — Net income (before extraordinary items) / total assets, current year positive.
2. **CFO > 0** — Operating cash flow positive, current year.
3. **ΔROA > 0** — ROA this year > ROA last year.
4. **Accruals: CFO/Assets > ROA** — operating cash flow exceeds net income (earnings backed by cash, not accruals).

Leverage / Liquidity / Source-of-funds (3):
5. **ΔLeverage < 0** — long-term-debt / total-assets ratio *lower* than prior year (less leverage).
6. **ΔCurrent ratio > 0** — current ratio higher than prior year (improving liquidity).
7. **No new shares** — shares outstanding did not increase vs prior year (no dilution).

Operating efficiency (2):
8. **ΔGross margin > 0** — gross margin (gross profit / sales) higher than prior year.
9. **ΔAsset turnover > 0** — asset turnover (sales / total assets) higher than prior year.

**Interpretation:** 8–9 = strong; 0–2 = weak. Maps cleanly to QUALITY pillar.

**Failure modes / guards:**
- **Financials (banks, insurers):** "gross margin," "asset turnover," and "current ratio" are meaningless for banks. Piotroski explicitly excludes financials. → **sector guard: skip tests 6/8/9 (or the whole score) for the Financials sector; treat as missing-data, do not zero.**
- yfinance only reliably exposes ~4 yrs of annual statements; quarterly restatements and missing line items are common on free tier → expect coverage gaps, flag low-coverage rows.
- "Shares issued" is noisy on free data; small buyback/SBC swings flip test 7.

**Classification:** **TABLE STAKES** (any serious value screener built post-2010 is expected to carry it). **Complexity: HIGH** (heaviest fetch — 2 yrs of 3 statements × ~550 tickers; rate-limit risk).
**Dependency:** Independent of Lynch/Graham; feeds QUALITY pillar.

---

### 2. Altman Z-Score (distress / bankruptcy proxy)

**What it predicts:** Probability of financial distress within ~2 years. Use as a **penalty/veto in the SAFETY pillar, never as a positive contributor** (per locked decision) — a high Z does not make a stock a buy; a low Z should drag the composite down and flag a value trap.

**Three models — pick by sector:**

**(A) Original (public manufacturers):**
`Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5`
- X1 = Working capital / Total assets
- X2 = Retained earnings / Total assets
- X3 = EBIT / Total assets
- X4 = Market value of equity / Total liabilities
- X5 = Sales / Total assets
- Zones: **Z > 2.99 safe · 1.81–2.99 grey · < 1.81 distress.**

**(B) Z'' for non-manufacturers / mixed universe (recommended default for this broad S&P/Nasdaq universe):**
`Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4` (drops X5 sales-turnover term, which varies wildly by industry)
- X1 = (Current assets − Current liabilities) / Total assets
- X2 = Retained earnings / Total assets
- X3 = EBIT / Total assets
- X4 = **Book** value of equity / Total liabilities
- Zones: **Z'' > 2.6 safe · 1.1–2.6 grey · < 1.1 distress.**
- (Emerging-markets variant adds a +3.25 constant; not needed here.)

**(C) Z' (private firms):** replaces X4 market-cap with book equity and reweights; **not needed** — this universe is all public.

**Recommendation for THIS screener:** Use **Z''** as the universe default (the universe is tech-heavy and mixed, where X5 distorts the original); optionally use the original model only for clearly-industrial sectors. Simpler still: ship Z'' everywhere in Phase C and note the limitation.

**Failure modes / guards:**
- **Financials:** Z-score is invalid for banks/insurers (their balance sheets are leverage by design — X4 and X1 break). → **sector guard: do not compute/penalize Financials.**
- Negative retained earnings (young high-growth Nasdaq names) tank X2 → many legitimately-fine growth stocks score "distress." Document this; don't hard-veto on Z alone.

**Classification:** **TABLE STAKES** for a value screen (value-trap insurance). **Complexity: MEDIUM** (needs working capital, retained earnings, total liabilities, EBIT — partly in the Finnhub `metric=all` bundle; some line items need statements).
**Dependency:** Independent; SAFETY pillar (penalty side).

---

### 3. Acquirer's Multiple (EV/EBIT) & Greenblatt Magic Formula

These share inputs (EV, EBIT, invested capital) — implement the data layer once.

**Acquirer's Multiple = EV / EBIT** (lower = cheaper; it's the inverse of earnings yield).
- EV = market cap + total debt + preferred + minority interest − cash & equivalents.
- EBIT = operating income.
- Includes debt (unlike P/E), so it doesn't reward balance-sheet leverage the way P/E does — this is the deep-value rationale. Tobias Carlisle: cheapest decile ~17.9%/yr 1973–2017 (per locked-decisions source). Standard "cheap" heuristic: EV/EBIT in the lowest cross-sectional decile; for an **absolute** band, EV/EBIT ≤ ~8 is cheap, ≥ ~20 is expensive (tune as config).

**Magic Formula (Greenblatt) = rank-combine two factors:**
- **Earnings yield = EBIT / EV** (the reciprocal of the Acquirer's Multiple).
- **Return on capital (ROIC) = EBIT / (Net working capital + Net fixed assets)** (Greenblatt's specific denominator, not plain ROA/ROE).
- Greenblatt's original method **ranks** each factor across the universe and sums ranks. **This conflicts with the locked "absolute thresholds, not percentile ranks" decision.** → For this screener, do NOT ship Greenblatt's percentile-rank combination as the score; instead expose **earnings yield (EBIT/EV)** and **ROIC** as two **absolute** sub-score inputs (VALUE + QUALITY pillars respectively). This preserves the *signals* Greenblatt identified while honoring the absolute-scoring decision.

**Failure modes / guards:**
- **Financials:** EBIT and EV are ill-defined for banks (no meaningful operating income / enterprise value). → **sector guard.**
- **Negative EBIT** (loss-makers): EV/EBIT goes negative/undefined → treat as missing or worst-band, not a "cheap" negative.
- Cash-rich companies (e.g. mega-cap tech) get artificially low EV; EV can even go negative for net-cash names → clamp.

**Classification:** EV/EBIT + earnings yield = **TABLE STAKES**. ROIC = **TABLE STAKES** (quality core). Full Greenblatt rank-formula as a *score* = **ANTI-FEATURE here** (conflicts with absolute-scoring decision; use the underlying factors instead).
**Complexity: MEDIUM** (EV components largely in Finnhub bundle currently discarded).
**Dependency:** Independent; VALUE (earnings yield) + QUALITY (ROIC).

---

### 4. FCF Yield & Shareholder Yield

**FCF Yield = Free Cash Flow / Market Cap** (or FCF / EV for a leverage-neutral variant).
- FCF = Operating cash flow − capital expenditures.
- Cash-based value signal; harder to manipulate than EPS. **Absolute bands:** ≥ ~8% full marks, ~0% zero, negative = worst (per locked-decisions example).

**Shareholder Yield = Dividend Yield + Net Buyback Yield (+ Net Debt-Paydown Yield, optional 3rd leg).**
- Dividend yield = TTM dividends / price (already computed: `DivYield_Pct`).
- **Buyback yield = (shares outstanding 1yr ago − shares now) / market cap**, i.e. **net** reduction in share count. Net is the key word: gross buybacks offset by SBC/dilution can be ~zero or negative. Standard literature (Meb Faber) uses net change in shares outstanding.
- Optional 3rd leg: net debt reduction / market cap.

**Failure modes / guards:**
- **Negative FCF** (capex-heavy or growth phase) → many fine companies score 0; expected, not a bug.
- Buyback yield from free data is noisy — share-count series jump on splits/restatements → winsorize.
- Dividend yield already exists; reuse it rather than recompute.

**Classification:** FCF yield = **TABLE STAKES** (cash-based value is expected). Shareholder yield = **DIFFERENTIATOR** (most free screeners show dividend yield only, not net buyback). **Complexity: LOW–MEDIUM** (FCF + shares-outstanding-history; partly in Finnhub bundle).
**Dependency:** Reuses existing `DivYield_Pct`; VALUE pillar.

---

### 5. Forward 2-Stage DCF & Reverse DCF

**Forward 2-stage DCF → `DCF_FV`, `DCF_Discount_Pct`:**
- **Stage 1 (explicit, 5 yr):** project current FCF (or FCF-per-share × shares) growing at `min(g, growth_cap)` — reuse the existing capped growth `g`.
- **Stage 2 (terminal):** Gordon growth, terminal g ≈ **2.0–2.5%** (long-run GDP/inflation). Terminal value = `FCF_year5·(1+g_term) / (WACC − g_term)`.
- **Discount rate (WACC proxy):** reuse the **FRED AAA yield already fetched** + an equity risk premium (~4.5–5.5%). E.g. `WACC ≈ AAA_yield + ERP`. Keep ERP a tunable config constant. (Full CAPM/beta WACC is overkill for this tool — the AAA+ERP proxy is the right complexity level and reuses existing data.)
- Intrinsic value per share = (Σ discounted Stage-1 FCF + discounted terminal value) / shares outstanding. `DCF_Discount_Pct = (1 − price/DCF_FV)·100`.

**Reverse DCF → implied growth (the assumption-light headline):**
- Hold price, WACC, terminal g fixed; **solve for the Stage-1 growth rate that makes DCF_FV = current price.** Numerically (bisection/Newton on g).
- Compare **implied g vs actual g**: implied < actual ⇒ market is pricing in *less* growth than the company has shown ⇒ "margin of safety in expectations" (bullish). This is the most defensible DCF output because it makes the market's assumption explicit rather than asserting a fair value.

**Failure modes / guards (CRITICAL — flag prominently for roadmapper):**
- **Financials (banks/insurers): DCF is invalid.** FCF (OCF − capex) is meaningless for banks. → **hard sector guard: do not compute DCF for Financials; emit null + flag.**
- **Cyclicals / negative or lumpy FCF:** a single down-year FCF base produces garbage; consider a normalized/averaged FCF base (3-yr avg) to stabilize. **Flag cyclical FCF as unreliable.**
- Terminal value typically = 60–80% of the DCF — output is extremely sensitive to `WACC − g_term`; clamp so `WACC − g_term ≥ ~3%` to avoid blow-ups.
- Reverse-DCF solver must bound the search (e.g. g ∈ [−10%, +40%]) and handle no-solution (price already implies negative growth) gracefully.

**Classification:** Forward DCF = **DIFFERENTIATOR** (few free screeners show a per-stock DCF). Reverse DCF = **DIFFERENTIATOR** (rare, high-trust headline). **Complexity: HIGH** (numerical solver, sector guards, FCF normalization, sensitivity clamps).
**Dependency:** Reuses existing `g` (capped growth) and `AAA_Yield`; feeds VALUE pillar (forward discount) + GROWTH pillar (reverse implied-vs-actual gap).

---

### 6. 52-Week-High Proximity vs Distance-From-Low + Recency

**Three related but distinct signals — the literature says they predict *opposite* things, so ship both as cross-checks, not one blended number:**

- **Distance from 52-week low / 5-year low** = `(price − low) / low`. **Contrarian-value reading:** near the low = statistically cheap. Feeds SAFETY/VALUE positively *only when paired with quality/distress checks* — near-low + low Piotroski + low Z = falling knife, not bargain.
- **52-week-high proximity** = `price / 52w_high` (closeness to high). **Academic (George & Hwang 2004):** proximity to the 52-week high *subsumes momentum* and **predicts continued outperformance** — i.e., near-high tends to keep winning; far-from-high tends to keep losing (anchoring/underreaction). This is the **opposite** of the naive value read. Use it as a **value-trap cross-check**: deep discount + very far from 52w-high = anchoring red flag.
- **Recency framing — `Weeks_Since_52w_Low` / `Weeks_Since_5y_Low`:** distinguishes **falling-knife** (low set *this* week, still declining) from **basing/recovering** (low set many weeks ago, price stabilizing). More weeks since the low at similar distance = healthier (basing) setup.

**Net design (per locked decision):** use distance-from-low as a contrarian VALUE input AND 52w-high proximity as a SAFETY trap-flag; expose recency to separate falling-knife from basing. **Do not** collapse the contradictory readings into a single direction silently.

**Failure modes / guards:**
- Requires **5-year daily/weekly price history** (new yfinance fetch — heaviest new price pull).
- Splits/dividends must use adjusted-close or highs/lows are wrong.
- IPOs / recent additions lack 5y history → flag low-coverage, don't zero.

**Classification:** Distance-from-low + recency = **DIFFERENTIATOR** (recency "weeks since low" framing is uncommon and genuinely useful). 52w-high proximity trap-check = **DIFFERENTIATOR**. **Complexity: MEDIUM** (extra 5y price history fetch + windowed min/argmin).
**Dependency:** Independent of fundamentals; SAFETY pillar (+ value-trap flag).

---

## Absolute-Threshold Scoring Mechanics (the core new capability)

This is the heart of v2.0 and must be spelled out as testable requirements. Per locked decision: **absolute fixed thresholds (0–100), NOT cross-sectional percentile ranks** — comparable across weekly/monthly snapshots.

### Raw-metric → 0–100 sub-score (piecewise-linear band mapping)

Each raw metric maps to a sub-score via a **fixed-threshold piecewise-linear ramp**, defined by config constants (mirroring the existing `LYNCH_*` / `GRAHAM_*` blocks so they're easy to tune):

```
subscore(x) :
  if higher-is-better metric (e.g. FCF yield, earnings yield, F-score):
     x <= LO_THRESH        -> 0
     x >= HI_THRESH        -> 100
     else                  -> 100 * (x - LO_THRESH) / (HI_THRESH - LO_THRESH)   # linear ramp
  if lower-is-better metric (e.g. EV/EBIT, debt/equity):
     mirror the ramp (x <= GOOD -> 100, x >= BAD -> 0)
```

- **Winsorize / clamp inputs FIRST** so one data glitch (the documented 1179% growth episode, negative EV, BRK-B EPS) cannot dominate. Clamp raw metric to a sane domain before the ramp; the LO/HI thresholds effectively act as the clamp for monotonic metrics.
- Integer/bounded metrics (Piotroski 0–9, Graham defensive 0–8, Altman zones) map via a **lookup table** rather than a ramp (e.g. F-score 9→100, 8→89, … 0→0; or banded). Altman maps by zone: safe→full, grey→partial, distress→0 (penalty).
- Thresholds are **config constants**, version-controlled, documented on `methodology.html`. Their arbitrariness is the accepted tradeoff of the absolute approach (locked decision 1).

### Pillar aggregation

```
OverallScore (0–100)
├── VALUE   ~35%  : Graham disc, Lynch disc, FCF yield, earnings yield (EBIT/EV), EV/EBIT, reverse-DCF gap, forward-DCF disc
├── QUALITY ~30%  : Piotroski F, ROIC, ROE, Graham defensive score, debt/equity, current ratio
├── GROWTH  ~20%  : EPS growth g, growth stability, reverse-DCF implied-vs-actual gap
└── SAFETY  ~15%  : Altman Z (penalty), distance-from-52w-low + recency, 52w-high proximity (trap flag)
```

- **Within a pillar:** average the available sub-scores (optionally weighted per-metric). **Pillar score = mean of present sub-scores.**
- **Across pillars:** `OverallScore = Σ (pillar_weight × pillar_score)`. Weights set by judgment (no backtest yet — locked decision 3); keep tunable config.
- **Decomposable (locked, essential):** dashboard exposes the 4 pillar sub-scores per stock (anti-black-box; required for a public-trust tool). `top.html` cards show overall + 4 pillars.

### Missing-data handling (per pillar)

- **Rule (locked):** average over the metrics that are *present* within a pillar; **do NOT zero a stock for a missing metric** (zeroing would unfairly bury names with one data gap).
- **Coverage flag:** track per-row data coverage; flag low-coverage rows (e.g. "scored on 3/7 value metrics") rather than silently. Optionally apply a small confidence haircut or exclude from Top-N if coverage below a threshold.
- If an entire pillar is unavailable (e.g. Financials with no DCF/F-score/Z), score on remaining pillars and flag — do not crash or zero.

**Classification:** The absolute composite + decomposable pillars + missing-data rule = **TABLE STAKES for THIS milestone** (it IS the milestone's core value). Winsorization + coverage flag = **TABLE STAKES** (data is free-tier noisy — the 1179% episode proves it). Per-metric tunable weights = **TABLE STAKES** (config-driven, like existing blocks). **Complexity: MEDIUM** (mechanics are simple; the work is choosing/justifying ~20 threshold constants and wiring decomposition into JSON + UI).
**Dependency:** Consumes ALL existing Lynch/Graham/defensive outputs as VALUE+QUALITY inputs; replaces naive `CombinedScore`. **Blocked by the deferred Buy Price formula bug** — fix that first (new VALUE sub-scores build on those discount denominators).

---

## Feature Landscape

### Table Stakes (expected in a credible v2 value screener)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Piotroski F-Score | Standard value-trap quality filter; the canonical companion to a cheapness screen | HIGH | Heaviest fetch (2yr × 3 statements); skip for Financials |
| Altman Z-Score (Z'' default) | Distress insurance; prevents top-ranking distressed deep-discount names | MEDIUM | Penalty/veto only, never positive; invalid for Financials |
| EV/EBIT + earnings yield (EBIT/EV) | Debt-aware deep-value standard; doesn't reward leverage like P/E | MEDIUM | EV components mostly in discarded Finnhub bundle |
| ROIC (Greenblatt denominator) | Quality core; "good business" half of Magic Formula | MEDIUM | Pair with earnings yield as ABSOLUTE inputs, not ranks |
| FCF yield | Cash-based value, manipulation-resistant | LOW–MED | FCF = OCF − capex; absolute bands |
| 4-pillar absolute composite (0–100) | THE milestone deliverable; replaces naive CombinedScore | MEDIUM | Piecewise-linear bands + config thresholds |
| Decomposable pillar sub-scores in JSON + UI | Anti-black-box; required for public-trust tool | LOW–MED | Exposed on dashboard + top.html |
| Winsorize/clamp + missing-data averaging + coverage flag | Free-tier data is noisy (1179% growth glitch) | MEDIUM | Clamp before ramp; average present metrics; flag low coverage |
| Sector guards (Financials/cyclicals) | DCF/EV-EBIT/Z/Piotroski all break on banks | MEDIUM | Detect sector; null+flag, don't zero |

### Differentiators (uncommon in free screeners; align with Core Value)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Reverse DCF (implied vs actual growth) | Makes the market's growth assumption explicit; high-trust, assumption-light headline | HIGH | Numerical solver; bound search; the standout signal |
| Forward 2-stage DCF | Per-stock intrinsic value few free tools show | HIGH | Reuses AAA yield + capped g; terminal-value sensitivity clamp |
| Distance-from-low + "weeks since low" recency | Separates falling-knife from basing — uncommon framing | MEDIUM | Needs 5y price history |
| 52w-high proximity trap-check (George & Hwang) | Cross-checks the naive "near low = cheap" read against anchoring evidence | MEDIUM | Deliberately opposite signal; trap flag |
| Shareholder yield (net buyback) | Most free screeners show dividend yield only | LOW–MED | Net share-count change, not gross |
| Top-N picks page + historic snapshots | Shareable "what to look at now" + future trend/backtest substrate | MEDIUM | top.html (mockup approved); weekly/monthly snapshot commit |

### Anti-Features (seem good, problematic for THIS screener)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Greenblatt percentile-rank Magic Formula as the score | It's the famous published method | Directly conflicts with locked "absolute, not percentile" decision; not comparable across snapshots | Use EBIT/EV + ROIC as absolute sub-score inputs |
| Cross-sectional percentile/z-score normalization | Statistically cleaner, self-calibrating | Locked out — not comparable over time; the whole point of snapshots is absolute comparability | Fixed config thresholds + winsorization |
| DCF/Z/EV-EBIT applied uniformly to banks | "Score everything consistently" | Garbage outputs; banks have no meaningful FCF/EBIT/EV; would mis-rank financials | Sector guard: null + flag, score on remaining pillars |
| Zeroing a pillar/stock on any missing metric | Simple, "fair" | Buries good names with one data gap; free-tier gaps are common | Average present metrics + coverage flag |
| Pure technical indicators (RSI/MACD/MA crossovers), analyst price targets | Look sophisticated | Low evidence (locked "skip"); off-mission for a value screen | Stick to fundamental + the evidence-backed 52w anchors |
| Hard veto on low Altman Z for growth names | "Distress = avoid" | Negative retained earnings tank Z for legitimately-fine young Nasdaq growth stocks | Penalty (drag score) + flag, not absolute veto |

## Feature Dependencies

```
Buy Price formula-bug FIX
    └──blocks──> 4-pillar absolute composite (VALUE pillar uses discount denominators)
                     ├──requires──> existing Lynch/Graham discounts (VALUE)
                     ├──requires──> existing Graham defensive score (QUALITY)
                     ├──requires──> EBIT/EV + ROIC + FCF yield (VALUE/QUALITY)
                     ├──requires──> Piotroski F + Altman Z (QUALITY/SAFETY)
                     └──requires──> 52w/5y distance + recency (SAFETY)

EV data layer (EV, EBIT) ──shared by──> EV/EBIT, earnings yield, Magic Formula ROIC
2-stage forward DCF ──enables──> Reverse DCF (same engine, solve for g)
5y price-history fetch ──enables──> distance-from-low, weeks-since-low, 52w-high proximity
Decomposable pillar scores ──enables──> top.html cards + stats.html aggregates
4-pillar composite ──enables──> Top-N page + historic snapshots (need a stable score to rank/track)
```

### Dependency Notes

- **Composite is blocked by the Buy Price bug:** new VALUE sub-scores reuse existing discount denominators; fix first (locked, STATE.md).
- **DCF reuses existing data:** `AAA_Yield` (already fetched from FRED) → WACC proxy; capped `g` → Stage-1 growth. Low marginal data cost; high logic cost.
- **One EV/EBIT data layer feeds three factors** (Acquirer's Multiple, earnings yield, Greenblatt ROIC) — build once.
- **Forward and reverse DCF share one engine** — reverse is the forward valuation with a root-solver wrapped around growth.
- **Snapshots depend on a stable absolute score** — only meaningful because the score is absolute (locked decision 1b ↔ 1).

## MVP Definition

### Launch With (Phase A — first milestone, locked)

- [ ] Fix the deferred Buy Price formula bug — unblocks every VALUE sub-score
- [ ] 4-pillar absolute composite from **existing** metrics (Lynch/Graham/defensive) + piecewise-linear band mapping + winsorization + missing-data averaging + coverage flag
- [ ] Decomposable pillar sub-scores in `results.json` (nested `scores` object)
- [ ] `docs/top.html` — Top 10/25 by OverallScore (mockup approved)

### Add After Validation (Phase B — cheap, high-evidence, mostly in Finnhub bundle)

- [ ] FCF yield, EV/EBIT + earnings yield, ROIC (deepen VALUE/QUALITY)
- [ ] Distance-from-52w/5y-low + weeks-since-low + 52w-high proximity (5y price fetch) — SAFETY
- [ ] Shareholder yield (net buyback)

### Future Consideration (Phase C — heaviest)

- [ ] Piotroski F-Score (2yr statements) + Altman Z'' — QUALITY/SAFETY
- [ ] Forward + reverse DCF (solver, sector guards, FCF normalization) — VALUE/GROWTH
- [ ] `docs/stats.html` universe aggregates
- [ ] Historic weekly/monthly snapshot mechanism
- [ ] (Phase D, deferred) backtest harness

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Buy Price bug fix | HIGH | LOW | P1 |
| 4-pillar absolute composite + decomposition | HIGH | MEDIUM | P1 |
| top.html Top-N | HIGH | LOW–MED | P1 |
| FCF yield / EV-EBIT / earnings yield / ROIC | HIGH | MEDIUM | P2 |
| 52w/5y distance + recency + high-proximity | HIGH | MEDIUM | P2 |
| Shareholder yield | MEDIUM | LOW–MED | P2 |
| Piotroski F-Score | HIGH | HIGH | P2/P3 |
| Altman Z'' | MEDIUM | MEDIUM | P3 |
| Reverse DCF | HIGH | HIGH | P3 |
| Forward DCF | MEDIUM | HIGH | P3 |
| stats.html | MEDIUM | MEDIUM | P3 |
| Historic snapshots | MEDIUM | MEDIUM | P3 |
| Backtest harness | HIGH | HIGH | P3 (deferred) |

## Competitor Feature Analysis

| Feature | Stockopedia StockRanks | Greenblatt Magic Formula site | Our Approach |
|---------|------------------------|-------------------------------|--------------|
| Composite score | Relative percentile (0–100 rank vs market) | Rank-sum of 2 factors | **Absolute fixed-threshold 0–100** (comparable over time) |
| Decomposition | Quality/Value/Momentum sub-ranks shown | None (opaque list) | 4 pillars (Value/Quality/Growth/Safety) shown per stock |
| Piotroski | Yes | No | Yes (QUALITY pillar) |
| DCF / reverse DCF | No | No | Yes — differentiator |
| 52w anchors + recency | Momentum rank only | No | Distance-from-low + weeks-since-low + high-proximity trap-check |
| Cost / access | Paid subscription | Free but gated/limited | **Free public URL, no account** (Core Value) |

## Sources

- Piotroski F-score (9 tests, interpretation) — https://en.wikipedia.org/wiki/Piotroski_F-score (verified 2026-06-17)
- Altman Z-score (original, Z'', emerging-market formulas + zones) — https://en.wikipedia.org/wiki/Altman_Z-score (verified 2026-06-17)
- Acquirer's Multiple / EV-EBIT deep value (cheapest decile ~17.9%/yr 1973–2017) — https://www.quant-investing.com/blog/acquirers-multiple-deep-value-metric-explained (via locked-decisions doc)
- George & Hwang, 52-week high subsumes momentum — https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf (via locked-decisions doc)
- Anchoring-induced momentum — https://www.sciencedirect.com/science/article/pii/S2214635024000418
- S&P multi-factor index methodology (pillar weighting/normalization patterns) — https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-quality-value-momentum-multi-factor-indices.pdf
- Stockopedia StockRanks (decomposable composite precedent) — https://www.stockopedia.com/stockranks/
- Locked decisions & project-specific design — `.planning/research/v2-METHODOLOGY-EXPANSION.md`
- Existing implementation integration points — `stock_screener.py`, `docs/methodology.html`

---
*Feature research for: multi-factor value-stock screener (v2.0 scoring expansion)*
*Researched: 2026-06-17*
