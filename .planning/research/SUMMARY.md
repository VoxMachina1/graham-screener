# Project Research Summary

**Project:** Lynch & Graham Screener — v2.0 Methodology Expansion (multi-factor absolute scoring + Top-N page)
**Domain:** Multi-factor value-stock screener on free-tier financial data, published as a static public GitHub Pages tool (no backtest)
**Researched:** 2026-06-17
**Confidence:** HIGH

## Executive Summary

v2.0 replaces the naive 50/50 price-discount `CombinedScore` with a **4-pillar absolute composite (Value ~35 / Quality ~30 / Growth ~20 / Safety ~15, 0–100)** and ships a public Top 10/25 page. The good news from all four research streams is convergent: this is an *integration and discipline* milestone, not a stack milestone. **No new paid API, no new credential, and effectively no new Python dependency** — most Phase A/B factor inputs (FCF, EV/EBIT, ROIC, ROE, 52w high/low) are already inside the Finnhub `metric=all` bundle the pipeline fetches and then discards. Only Phase C adds genuinely new fetches (5y price history and 2-yr financial statements for Piotroski/Altman/DCF), and those are the rate-limit and runtime risk to plan around. The recommended structure is a single new `scoring.py` module (config-dense, pure logic), factors kept next to the existing metric functions in `stock_screener.py`, an **additive** JSON schema (existing flat keys untouched + a nested `scores` object), one shared `docs/app.js`, and snapshots handled in the Actions workflow.

The dominant risks are not technical — they are **ordering and credibility** risks, and the four researchers agree strongly on the sequence. (1) The deferred **Buy Price formula bug must be fixed and hand-verified FIRST**, before any pillar consumes a discount: the Value pillar inherits `Lynch_Discount_Pct` / `Graham_Discount_Pct`, so a broken denominator silently corrupts every `OverallScore` while still looking plausible. (2) Phase A ships a **public** Top-N page, but the real value-trap gates (Altman Z, Piotroski) don't land until Phase C — so Phase A must build an **interim trap-gate** from signals already in the data (debt/equity, current ratio, EPS stability, negative-FCF) or risk a cheap-but-dying stock topping a public list. (3) The locked Value pillar over-weights cheapness — Graham disc, Lynch disc, FCF yield, EV/EBIT, earnings yield, and reverse-DCF gap are ~6 expressions of one bet — so correlated metrics must be **grouped** or the composite is a glorified cheapness rank.

Three cross-cutting design corrections also fall out of the research and should be treated as requirements, not options: Greenblatt's **Magic Formula is rank-based and conflicts with the locked absolute-threshold decision** (ship EBIT/EV + ROIC as absolute inputs, not the rank-sum); a **GICS sector field is a new prerequisite** because DCF/EV-EBIT/Altman/Piotroski are all invalid for financials (~60–70 of the 550 tickers); and **winsorization/clamping must precede pillar aggregation** so one free-tier glitch (the documented 1179% growth episode, a near-zero EV) cannot max a sub-score and top a public Top-10.

## Key Findings

### Recommended Stack

See `STACK.md`. The headline is **near-zero new surface**. The only `requirements.txt` change is tightening the yfinance floor to `>=0.2.55,<1.0` (stable statement accessors; stay on 0.2.x, defer the 1.x major bump) and adding an explicit `numpy>=1.26,<3` pin (already transitive, but now imported directly for winsorize/clamp). Reverse-DCF uses a **hand-rolled stdlib bisection — no scipy**. Snapshots and the optional fundamentals cache are committed JSON files under `docs/` — **no database, no new infra**.

**Core technologies:**
- Finnhub `metric=all` bundle (already fetched) — source for FCF, EV/EBIT, ROIC, ROE, 52w high/low — Phase A/B add **zero** new network calls by mining fields currently discarded.
- yfinance 0.2.5x (`income_stmt`/`balance_sheet`/`cashflow`/`history(5y)`) — Phase C only; the heaviest fetch and the real rate-limit/runtime constraint across 550 tickers.
- numpy (explicit pin) — winsorize/clamp + vectorized threshold mapping; already in the tree.
- Tabulator 6.4 CDN + vanilla JS (unchanged) — `top.html`/`stats.html` reuse the same `results.json`, no build step.
- GitHub Actions (existing `screener.yml`) — extend with a date-gated snapshot step; already has `contents: write`.

### Expected Features

See `FEATURES.md`. The composite + decomposable pillars + missing-data rule **are** the milestone's core value.

**Must have (table stakes):**
- 4-pillar absolute composite (0–100) with piecewise-linear band mapping from config thresholds — replaces `CombinedScore`.
- Decomposable pillar sub-scores in JSON + UI — anti-black-box; required for a public-trust tool.
- Winsorize/clamp + average-over-present missing-data rule + coverage flag — free-tier data is noisy.
- Piotroski F-Score, Altman Z'' (penalty/veto only), EV/EBIT + earnings yield, ROIC, FCF yield (Phase B/C).
- Sector guards (Financials/cyclicals) — DCF/EV-EBIT/Z/Piotroski all break on banks.

**Should have (competitive differentiators):**
- Reverse DCF (implied-vs-actual growth) — the standout, assumption-light headline.
- Forward 2-stage DCF — per-stock intrinsic value few free tools show.
- Distance-from-low + "weeks since low" recency (falling-knife vs basing) and 52w-high proximity trap-check (George & Hwang).
- Shareholder yield (net buyback, not gross).
- Top-N picks page + historic snapshots.

**Defer (v2+):**
- Backtest harness (locked decision 3, Phase D).
- Greenblatt percentile-rank Magic Formula as the score — **anti-feature** (conflicts with absolute decision; use EBIT/EV + ROIC as absolute inputs instead).
- Cross-sectional percentile normalization, pure technical indicators, analyst price targets, hard Altman veto on growth names.

### Architecture Approach

See `ARCHITECTURE.md`. Every integration point is verified against source (HIGH confidence). Extract **one** new module `scoring.py` (4-pillar composite, sub-score mapper, winsorize, config constants); keep new factor/fetch code inside `stock_screener.py` as thin helpers called from a still-conductor `process_ticker()`. JSON schema is **additive** — leave the `Lynch_Lynch_`/`Graham_Graham_` double-prefix wart alone (renaming is pure regression risk, zero benefit). One shared `docs/app.js` for the now-triplicated fetch/format/color primitives. Snapshots live in the Actions workflow (date-gated copy of the already-guarded, already-committed `results.json`), keeping Python free of calendar logic and the min-100-row guard as the single quality gate.

**Major components:**
1. `scoring.py` (NEW) — `compute_overall_score(row)` → flat pillar scores + nested decomposition; holds `SCORE_THRESHOLDS`/`PILLAR_WEIGHTS`.
2. `stock_screener.py` (MODIFIED) — fix Buy Price bug; expand `get_combined_data()` (FCF/EV-EBIT/ROIC/ROE/**Sector**); new `get_yf_price_history_5y()`; helpers `compute_factor_signals()`/`compute_distress_signals()`/`compute_dcf()`.
3. `docs/app.js` (NEW) + `docs/top.html` (NEW, Phase A) + `docs/stats.html` (NEW, Phase C) — shared primitives + the two new pages.
4. `.github/workflows/screener.yml` (MODIFIED) — date-gated snapshot step after commit/push, with the `!docs/data/snapshots/*.json` `.gitignore` exception.

### Critical Pitfalls

See `PITFALLS.md`. The top hazards are ordering- and credibility-driven, not coding bugs.

1. **Composite built on the unresolved Buy Price bug** — fix and verify against a **hand-computed fixture ticker** (e.g. JNJ/KO) as Phase A task 1, blocking. A broken denominator silently corrupts every score.
2. **Value-trap atop a public Top-10** — Phase A ships Top-N before Altman/Piotroski (Phase C), so gate Phase A with an **interim** trap-gate from existing signals (debt/equity, current ratio, EPS stability, negative-FCF) + a value-trap badge. Publish-blocker.
3. **One bad metric dominating** — winsorize/clamp **both tails** of every raw input *before* pillar averaging; only `GROWTH_CAP` exists today.
4. **Double-counting correlated cheapness** — group correlated Value metrics (multiples / cash / expectations votes) or the 35% Value pillar becomes a glorified cheapness rank; pairwise-correlation check on the 550-row snapshot.
5. **Sector-invalid scores published** — GICS sector tag + per-metric applicability matrix; DCF/EV-EBIT/Altman/Piotroski are nonsense for financials → treat as missing, never zero.
6. **Missing-data silently zeroing or full-marking** — average over present metrics only; surface a coverage flag; missing *safety* input = "unknown," not "safe."

## Implications for Roadmap

The four research streams produce a **single, dependency-forced ordering**. The hard gate chain is: **bug fix → composite (with winsorize + missing-data contract) → interim trap-gate → public Top-N → cheap factors + sector → heavy signals + DCF + stats + snapshots.**

### Phase 5 (A): Score Foundation + Public Top-N (locked first milestone)
**Rationale:** Everything downstream reuses `Lynch_Discount_Pct`; the composite is the milestone's core value; it can be built entirely from metrics that already exist. The public page must not ship ungated.
**Delivers:** Fixed & fixture-verified Buy Price; `scoring.py` 4-pillar composite from existing metrics (Lynch/Graham/defensive/g) with piecewise-linear bands, winsorization, average-over-present missing-data rule + coverage flag; additive JSON (`OverallScore`, flat pillar scores, nested `scores`); `app.js` extracted from `index.html`; `docs/top.html` (Top 10/25); **interim value-trap gate** from existing debt/equity, current ratio, EPS stability, negative-FCF + a value-trap badge.

### Phase 6 (B): Cheap High-Evidence Factors + Sector (mostly already in the Finnhub bundle)
**Rationale:** These deepen Value/Quality/Safety at near-zero new I/O; the **sector field is a prerequisite** for EV/EBIT applicability and for Phase C's DCF/Altman/Piotroski guards, so it lands here.
**Delivers:** `Sector` in `get_combined_data()`; `get_yf_price_history_5y()`; `compute_factor_signals()` — FCF yield, EV/EBIT + earnings yield, ROIC (absolute inputs, **not** Greenblatt rank-sum), shareholder yield, 52w/5y distance + weeks-since-low recency + 52w-high proximity trap-flag; clamp each new metric in the PR that adds it; surface columns.

### Phase 7 (C): Heavy Signals + DCF + Stats Page + Snapshots
**Rationale:** Piotroski/Altman/DCF are the heaviest fetches and the real trap-gate; they require the sector applicability matrix and depend on the Phase B sector field. Snapshots need a finalized schema to be comparable.
**Delivers:** `compute_distress_signals()` (Piotroski F via 2-yr statements, Altman Z'' as penalty/veto) replacing the interim gate; `compute_dcf()` (forward + reverse, sector-guarded, FCF-normalized, terminal-g < discount-rate assert, bounded reverse solver → None on non-convergence); per-metric sector applicability matrix; `docs/stats.html` (coverage + score distribution monitoring); date-gated snapshot CI step + `!docs/data/snapshots/*.json` exception + optional 30-day fundamentals cache.

### Phase D: Backtest Harness (deferred — locked decision 3)
Out of scope this milestone; snapshots from Phase C are the substrate.

### Phase Ordering Rationale
- **Hard data dependency:** the Buy Price fix gates the composite; the composite gates the Top-N rank; the sector field (B) gates the DCF/distress guards (C). Violating the chain produces a confident-looking but wrong public score.
- **Credibility gating:** the public Top-N exists from Phase A, so the *interim* trap-gate is non-negotiable in A and is upgraded (not first built) in C.
- **I/O cost rises monotonically:** A/B add ~zero new calls (bundle mining); C adds the heavy statement/history fetches → it owns the caching + rate-limit + run-level coverage-gate work.

### Research Flags
- **Phase 5 (A):** **Buy Price bug *diagnosis*** — STATE.md only says "visibly wrong across all tickers"; the root cause (sign/inversion, target-vs-buy-below) needs its own debug pass before the fix.
- **Phase 6 (B):** **Finnhub free-tier field coverage** — confirm `freeCashFlowAnnual`, EV/EBIT inputs, `roicTTM`, `roeAnnual` are actually populated across the full universe before scoring math depends on them.
- **Phase 7 (C):** **Piotroski data source** (Finnhub free tier vs yfinance statements) + **threshold calibration** (set by judgment, no backtest — expect tuning iterations against the `stats.html` distribution).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Field-level cross-check of the Finnhub bundle + yfinance accessors + existing codebase; one MEDIUM caveat on free-tier field population. |
| Features | HIGH | Factor formulas are textbook-stable (Piotroski, Altman, DCF); design constraints locked in `v2-METHODOLOGY-EXPANSION.md`. |
| Architecture | HIGH | Every integration point read directly from `stock_screener.py`/`index.html`/`screener.yml` with line anchors; double-prefix mechanism verified. |
| Pitfalls | HIGH | Failure modes documented in quant literature and observable in this codebase's own scars (BRK-B, 1179% growth, deferred Buy Price bug). |

**Overall confidence:** HIGH

### Gaps to Address
- **Buy Price root cause** — diagnose before the Phase A fix; verify with a hand-computed fixture.
- **Finnhub free-tier population per ticker** — `roicTTM`/`currentEv/freeCashFlow`/some `*PerShareTTM` return `null` inconsistently; average-over-present handles it, but validate coverage in Phase B before weighting.
- **Absolute threshold calibration** — no empirical anchor without a backtest; keep thresholds as loud config constants, rate-relativize yield-based ones to live AAA, monitor the distribution in `stats.html`.
- **Reverse-DCF convergence** on high-multiple names — bound the solver, require convergence, emit None + flag (never a silent default) into the Growth pillar.

### Cleanup Observations (NOT v2 blockers)
- `.planning/codebase/*.md` docs are **stale** — still describe the Google Sheets era; refresh opportunistically.
- Root `screener.yml` is a **stale duplicate** of `.github/workflows/screener.yml` (no push step, dead Tiingo/GSheet secrets) — candidate for deletion in a cleanup pass.

## Sources

### Primary (HIGH confidence)
- `v2-METHODOLOGY-EXPANSION.md` — locked decisions, pillar design, sequencing (anchor doc).
- Existing codebase (`stock_screener.py` with line anchors, `docs/index.html`, `.github/workflows/screener.yml`, `requirements.txt`, CLAUDE.md, STATE.md, CONCERNS.md).
- yfinance API reference + PyPI version availability.
- Piotroski F-score and Altman Z-score (Wikipedia, verified 2026-06-17).

### Secondary (MEDIUM confidence)
- Finnhub Basic Financials `stock/metric` field reference (cross-checked via Robot Wealth ~117-field write-up); free-tier per-field population inconsistent.
- George & Hwang (52w high subsumes momentum), Acquirer's Multiple decile data, S&P multi-factor methodology, Stockopedia StockRanks.

### Tertiary (LOW confidence)
- Anchoring-induced momentum (ScienceDirect) — single source.

---
*Research completed: 2026-06-17*
*Ready for roadmap: yes*
