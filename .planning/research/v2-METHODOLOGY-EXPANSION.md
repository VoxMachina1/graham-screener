# v2 Methodology Expansion — Research & Locked Decisions

**Status:** Research complete, decisions locked by user 2026-06-17. Input for v2 milestone planning.
**Author:** Research pass (Claude), 2026-06-17.

## Motivation

v1.0 ships Lynch + Graham + a naive 50/50 price-discount `CombinedScore`. The user wants to:

1. Expand valuation methodology beyond Lynch/Graham buy/don't-buy.
2. Introduce a real **scoring metric** to rank how good a buy each stock is.
3. Add a **Top 10/25** picks page plus a **stats/overview** page.

## Locked Decisions (user, 2026-06-17)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Scoring style | **Absolute thresholds** (0–100), comparable over time — not relative percentile ranks. Accepts that thresholds are more arbitrary. |
| 1b | Historic snapshots | **Yes** — store periodic snapshots in the repo (weekly/monthly cadence, NOT daily). Enables future trend/backtest work. |
| 2 | DCF | **Both** forward intrinsic-value DCF and reverse DCF, if data exists. |
| 3 | Backtest harness | **Deferred** — not a first- or second-pass concern. Testing "available eventually." |
| 4 | First milestone scope | **Phase A + Top-N page.** Score foundation first, then iterate. |

## Current baseline (what exists)

- `stock_screener.py` computes Lynch (PEG/PEGY/G+D bands), Graham (VA/VB intrinsic + 8-pt defensive checklist), and `CombinedScore = 0.5*lynch_disc + 0.5*graham_disc` (each clipped [0,60]).
- Weaknesses: `CombinedScore` is price-discount only (no quality/safety/trap awareness), not normalized, and can top-rank distressed deep-discount names.
- **Open bug (deferred in STATE.md):** "Buy Price visibly wrong across all tickers." Must be resolved before new scores build on that denominator.
- Single-point-in-time data; no backtest harness; free-tier data is noisy (see BRK-B / 1179% growth-glitch episodes).

## New signals — recommendation tiers

### Add (strong evidence)
- **Distance from 52-week low / 5-year low**, plus `Weeks_Since_52w_Low` / `Weeks_Since_5y_Low` (recency framing — falling-knife vs basing). NOTE: academic literature anchors on the 52-week *high* (George & Hwang — proximity to 52w high subsumes momentum). Sign is ambiguous: value reads "near low" as cheap; anchoring reads "far from high" as likely-underperform. Use distance-from-low as contrarian value input AND 52w-high proximity as a value-trap cross-check.
- **Piotroski F-Score (0–9)** — canonical quality / value-trap filter. Data: yfinance 2-yr financials or Finnhub ratios.
- **Acquirer's Multiple (EV/EBIT)** — deep value incl. debt. Cheapest decile ~17.9%/yr 1973–2017.
- **Magic Formula (earnings yield + ROIC)** — Greenblatt.
- **FCF yield** (FCF/market cap) — cash-based value.
- **Shareholder yield** (dividend + net buyback).

### Add (value-trap guard)
- **Altman Z-Score** — distress/bankruptcy proxy. Use as penalty/veto, not positive contributor.

### DCF
- **Forward 2-stage DCF** → `DCF_FV`, `DCF_Discount_Pct`. Stage 1: current FCF growing at min(g, cap) 5y; Stage 2: terminal ~2.5%. Discount: WACC proxy = AAA yield (already fetched from FRED) + equity risk premium.
- **Reverse DCF** → solve implied growth from current price; compare to actual g ("margin of safety in expectations"). Assumption-light headline.
- **Guard:** DCF meaningless for financials, unreliable for cyclical FCF — needs sector-aware handling.

### Skip (low evidence)
- Pure technical indicators (RSI/MACD/MA crossovers), naive single-ratio screens, analyst price targets.

## Scoring metric design

Replace `CombinedScore` with a **4-pillar absolute composite (0–100)**:

```
OverallScore (0–100)
├── VALUE    (~35%)  Graham disc, Lynch disc, FCF yield, EV/EBIT, earnings yield, reverse-DCF gap
├── QUALITY  (~30%)  Piotroski F, ROIC/ROE, Graham defensive score, debt/equity, current ratio
├── GROWTH   (~20%)  EPS growth g, growth stability, reverse-DCF implied-vs-actual
└── SAFETY   (~15%)  Altman Z, distance-from-52w-low recency, 52w-high proximity (trap flag)
```

- **Absolute thresholds** (per decision 1): each raw metric maps to a 0–100 sub-score via fixed thresholds (e.g. FCF yield ≥8% = full marks), NOT cross-sectional percentile. Thresholds become config constants like existing `LYNCH_*`/`GRAHAM_*` blocks → easy to tune.
- **Winsorize / clamp** raw inputs so one glitch (e.g. 1179% growth) can't dominate.
- **Missing-data rule:** average over available metrics within a pillar; flag low-coverage rows rather than zeroing the stock.
- **Decomposable:** dashboard exposes pillar sub-scores per stock (trust + anti-black-box). Confirmed essential for a public tool.
- Pillar weights set by judgment (no backtest yet); keep as tunable config.

## Technical / dashboard

- **`docs/top.html`** — Top 10/25 by OverallScore; reads same `results.json`, sorts+slices. Cards/compact table: rank, ticker, price, overall score, 4 pillar sub-scores, headline signals. N toggle 10/25. (Mockup approved 2026-06-17.)
- **`docs/stats.html`** — universe aggregates: # buy signals, score distribution, sector breakdown, median discount, defensive pass count, data coverage/quality stats.
- Add both to nav alongside Dashboard/Methodology.
- **Pipeline:** new fetches — 5y price history (yfinance), FCF/EV/ROIC (much already in the Finnhub `metric=all` bundle we currently discard), Piotroski 2-yr statements (heaviest). Watch Finnhub free-tier rate limits; cache quarterly-changing data.
- **JSON schema:** extend `results.json` with new columns + nested `scores` object. No new JSON file (avoids `.gitignore *.json` gotcha — `results.json` already excepted).
- **Snapshots (decision 1b):** new mechanism to commit periodic (weekly/monthly) snapshots of `results.json` for historic comparison/future backtest.

## Recommended sequencing

- **Phase A (first milestone):** fix formula-audit bug → refactor `CombinedScore` into the 4-pillar absolute composite using *existing* metrics → ship `top.html`.
- **Phase B:** cheap high-evidence factors (52w/5y distance+recency, FCF yield, EV/EBIT, Magic Formula inputs — mostly already in Finnhub bundle).
- **Phase C:** Piotroski F-Score, Altman Z, forward + reverse DCF; `stats.html`; snapshot mechanism.
- **Phase D (deferred):** backtest harness.

## Sources

- George & Hwang, 52-Week High & Momentum — https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf
- Anchoring-induced momentum — https://www.sciencedirect.com/science/article/pii/S2214635024000418
- QuantPedia, out-of-sample formula test — https://quantpedia.com/out-of-sample-test-of-formula-investing-strategies/
- Acquirer's Multiple — https://www.quant-investing.com/blog/acquirers-multiple-deep-value-metric-explained
- Piotroski F-Score — https://en.wikipedia.org/wiki/Piotroski_F-score
- S&P multi-factor methodology — https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-quality-value-momentum-multi-factor-indices.pdf
- Stockopedia StockRanks — https://www.stockopedia.com/stockranks/
