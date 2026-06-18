# Pitfalls Research

**Domain:** Multi-factor composite scoring on free-tier financial data, published as a static public tool (no backtest)
**Researched:** 2026-06-17
**Confidence:** HIGH — failure modes are well-documented in quant-finance literature (Piotroski, Altman, DCF, factor construction) and directly observable in this codebase's existing scars (BRK-B EPS scaling, 1179% growth glitch, deferred Buy Price bug).

These pitfalls are specific to **adding the 4-pillar absolute composite + new signals (Piotroski, Altman, DCF, FCF/EV, 52w/5y distance)** to *this* screener: ~550 tickers, yfinance + Finnhub free tier + FRED, static GitHub Pages, no backtest harness, public URL. Generic "write tests" advice is omitted in favor of context-specific hazards and a strict ordering of when each must be addressed.

---

## Ordering Constraints (read first)

The roadmapper must respect these dependencies. Violating them produces a confident-looking but wrong public score:

1. **Buy Price formula bug → fixed and verified BEFORE any pillar consumes a discount.** The Value pillar inherits `Lynch_Discount_Pct` / `Graham_Discount_Pct`, which depend on `Lynch_BuyPrice` / `Graham_FV`. A broken denominator silently propagates into every composite.
2. **Winsorization/clamping → BEFORE pillar aggregation.** One glitch (1179% growth) must be clamped *before* it is averaged into a pillar, not after.
3. **Sector guards → BEFORE `top.html` / `stats.html` publish scores.** Altman Z, Piotroski, EV/EBIT are invalid for banks/insurers. A public 0–100 score on a bank where half the inputs are invalid is a reputational hazard.
4. **Safety pillar / Altman / Piotroski gating → BEFORE the Top-N page is reachable by the public.** A cheap-but-dying stock topping a public Top-10 is the single highest reputational risk.

Phase mapping below uses the locked sequencing: **Phase A** (fix bug + refactor composite from existing metrics + `top.html`), **Phase B** (cheap high-evidence factors: 52w/5y, FCF yield, EV/EBIT, Magic Formula), **Phase C** (Piotroski, Altman, DCF, `stats.html`, snapshots), **Phase D** (backtest, deferred).

---

## Critical Pitfalls

### Pitfall 1: Building the composite on top of the unresolved Buy Price formula bug

**What goes wrong:**
The deferred bug ("Buy Price visibly wrong across all tickers," STATE.md, deferred 2026-05-31) means `Lynch_BuyPrice` and/or the discount denominators are incorrect. The new Value pillar consumes `Lynch_Discount_Pct = (1 - price/Lynch_BuyPrice)*100` and `Graham_Discount_Pct = (1 - price/Graham_FV)*100` directly. If the denominator is wrong, every Value sub-score, and therefore every `OverallScore`, is wrong — but it *looks* plausible (still 0–100, still sorted, still color-coded). You'd ship a polished public ranking built on a known-broken formula.

**Why it happens:**
The bug was deferred, not fixed. The temptation in Phase A is to "refactor `CombinedScore` into 4 pillars using existing metrics" and treat the existing discount columns as trustworthy inputs. They are not. The bug is upstream of the refactor.

**How to avoid:**
- Make "audit + fix Buy Price formula" the **first task of Phase A**, blocking the composite refactor. The locked sequencing already says this ("fix formula-audit bug → refactor"); enforce it as a hard gate.
- Audit each formula against its source definition: Lynch G+D buy price (`FV_GplusD * LYNCH_DISCOUNT[cat]`, line 370), Lynch discount (line 415), Graham VA/VB/FV (lines 434–440), Graham discount (line 453). Suspect candidates: a discount-vs-target-price sign/inversion, or `Lynch_BuyPrice` being a *target* not a *buy-below* price.
- **Add a spot-check fixture** with at least one ticker whose Lynch/Graham buy price, FV, and discounts are hand-computed from known EPS/growth/dividend/AAA inputs (e.g. a stable stalwart like JNJ or KO). Assert the pipeline reproduces those numbers within rounding. This is the verification the deferred ticket itself demands.

**Warning signs:**
- Buy prices that are uniformly above or below current price across all tickers (a sign/multiplier error affects everyone the same way).
- Discounts that don't reconcile by hand: pick one ticker, compute `(1 - price/buyprice)*100` on paper, compare to the JSON.
- The composite's Value pillar correlates suspiciously with one framework only.

**Phase to address:** **Phase A, task 1 (blocking).** No composite work proceeds until the fixture passes.

---

### Pitfall 2: One bad metric dominating the composite (garbage-in, un-winsorized outliers)

**What goes wrong:**
A single corrupted free-tier value blows up a pillar. The 1179% Finnhub growth glitch is the canonical example — it's already capped by `GROWTH_CAP=25.0`, but the *new* metrics (FCF yield, EV/EBIT, earnings yield, ROIC, Piotroski components) have **no equivalent caps yet**. A near-zero EV makes EV/EBIT explode; a tiny denominator makes FCF yield read 400%; a one-off asset sale inflates ROIC. If the raw metric maps linearly to a 0–100 sub-score, the outlier maxes that sub-score and drags the stock to the top of a *public* Top-10.

**Why it happens:**
Absolute-threshold scoring (locked decision 1) maps raw → 0–100 via fixed cutoffs. Without an explicit clamp, "FCF yield ≥ 8% = 100" still lets a garbage 400% value score 100 — and worse, garbage that *exceeds* the threshold is indistinguishable from a legitimately great value.

**How to avoid:**
- **Winsorize/clamp every raw input before it maps to a sub-score**, mirroring the existing `GROWTH_CAP` pattern. Make caps config constants alongside `LYNCH_*`/`GRAHAM_*` (e.g. `FCF_YIELD_CAP`, `EV_EBIT_FLOOR`, `EARNINGS_YIELD_CAP`). Cap *both* tails — a wildly negative EV/EBIT is as misleading as a wildly positive one.
- Clamp happens **before** pillar averaging (ordering constraint 2), not after the average.
- For ratios with small/negative denominators (EV/EBIT, FCF yield, P/B), guard the denominator explicitly and emit a "metric invalid" flag rather than a number — see Pitfall 5 on missing-data handling.

**Warning signs:**
- A stock tops Top-10 on the strength of a single sub-score that's pinned at 100 while its peers are 30–60.
- Sub-score distributions with a spike at exactly the max value (clamping working) vs. a long tail of impossible values (no clamping).
- The same ticker that triggered a data scar before (BRK-B, any negative-equity name) reappears with an implausibly high pillar.

**Phase to address:** **Phase A** for existing metrics (growth already capped; add caps to anything reused). **Phase B** for each new cheap factor as it's introduced — cap it in the same PR that adds it. **Phase C** for Piotroski/Altman/DCF inputs.

---

### Pitfall 3: Double-counting correlated factors across pillars

**What goes wrong:**
The locked Value pillar loads **Graham discount, Lynch discount, FCF yield, EV/EBIT, earnings yield, and reverse-DCF gap** — six metrics that are largely the *same bet* (cheapness) expressed six ways. Earnings yield and EV/EBIT are near-collinear; Graham and Lynch discounts both key off EPS and price; FCF yield and earnings yield co-move. Averaging six correlated metrics doesn't add information — it just **multiplies the weight of "cheap"** inside an already 35%-weighted Value pillar, making the composite a glorified cheapness rank. That's exactly the value-trap-prone behavior the 4-pillar design was meant to fix.

**Why it happens:**
"More factors = more robust" intuition. Each metric looks independent on paper. Without a backtest (deferred), there's no empirical correlation check to catch the redundancy.

**How to avoid:**
- Treat the Value pillar as **measuring one thing** and resist piling every cheapness metric into it equally. Either (a) sub-group correlated metrics and average within the group first (so Graham+Lynch+earnings-yield count as ~one "multiples cheapness" vote, FCF yield as a "cash cheapness" vote), or (b) deliberately keep the most *distinct* signals (e.g. one multiples-based, one cash-based, one expectations-based reverse-DCF gap) and drop the rest.
- Without a backtest you can still do a cheap empirical check: compute pairwise correlation of the candidate Value metrics across the 550-row snapshot. Anything > ~0.8 is double-counting — collapse it.
- Document the *intent* of each pillar so future tuners don't re-add redundant metrics.

**Warning signs:**
- `OverallScore` rank order ≈ simple cheapness rank order (compare Spearman correlation of OverallScore vs. raw FCF yield).
- Removing one Value metric barely changes the Top-10.
- Quality/Growth/Safety pillars rarely change a stock's rank — Value dominates.

**Phase to address:** **Phase A** (set the pillar architecture and within-pillar grouping when first built). Revisit in **Phase B/C** as each new factor lands — add it to a group, not as a fresh independent vote.

---

### Pitfall 4: Value-trap ranking — a cheap-but-dying stock topping a PUBLIC Top-10

**What goes wrong:**
Deep-discount distressed names (falling knives, pre-bankruptcy) score highest on cheapness and therefore on a Value-heavy composite. The current `CombinedScore` already "can top-rank distressed deep-discount names" (methodology doc). On a **public Top-10 page**, that's a reputational and arguably quasi-advisory hazard: the tool confidently recommends a stock that proceeds to collapse.

**Why it happens:**
Cheapness and distress are correlated — stocks are cheap *because* the market is pricing in trouble. A pure value score can't tell "unfairly cheap" from "correctly cheap." The Safety/Quality pillars exist to gate this, but if they're weak (15% Safety) or not yet built (Altman/Piotroski are Phase C), a Phase-A Top-10 ships ungated.

**How to avoid:**
- **Altman Z and Piotroski F must act as gates/penalties, not gentle positive contributors.** Methodology doc already says "Altman Z … penalty/veto, not positive contributor" — enforce it. A stock in the Altman distress zone (Z < 1.8 for manufacturers) or with Piotroski ≤ 2 should be *capped* in OverallScore or flagged "value trap" regardless of how cheap it is.
- **Sequencing risk:** Phase A ships `top.html` *before* Altman/Piotroski exist (Phase C). Mitigate by gating Phase A's Top-N with the cheapest available distress proxies already in the data — debt/equity, current ratio, EPS stability (Graham checks 1–4, already computed), negative-FCF flag. Don't publish an ungated Top-10.
- Add an explicit "value-trap" / low-quality badge on the Top-N card so a flagged stock can't appear endorsed.

**Warning signs:**
- A Top-10 entry has a high Value pillar but failing Graham defensive checks, negative FCF, or high debt/equity.
- The Top-10 skews toward beaten-down sectors (regional banks in a crisis, distressed retail).
- Stocks with recent large price drops (near 52w low, far from 52w high) cluster at the top with no recency/quality offset.

**Phase to address:** **Phase A** must ship an *interim* gate using existing quality/safety signals before exposing Top-N publicly. **Phase C** replaces it with Altman + Piotroski. This is a hard publish-blocker.

---

### Pitfall 5: Missing-data handling that silently zeros or unfairly penalizes

**What goes wrong:**
Free-tier data is sparse: Finnhub returns `None` for many fields, yfinance statements have gaps, share-count series break buyback yield. Two opposite failure modes:
- **Silent zero:** a missing FCF yield treated as 0 drags the Value pillar down → a good stock looks bad.
- **Silent full-marks / silent skip:** a missing distress input treated as "fine" lets a value trap through.
Either way, a stock with 3 of 6 Value metrics gets a score that *looks* as authoritative as one with all 6.

**Why it happens:**
`_safe_float` (line 207) returns `None` cleanly, but downstream sub-score mappers must each decide what `None` means. The path of least resistance (`value or 0`) silently zeros. The methodology doc's rule — "average over available metrics within a pillar; flag low-coverage rows" — is correct but must be *implemented consistently in every mapper*, which is easy to miss for 20+ new metrics.

**How to avoid:**
- **Pillar = average over present metrics only**; never substitute 0 or a neutral midpoint for missing. If a pillar has < N present metrics, mark the pillar (and the row) **low-coverage**.
- **Surface coverage to the user**: a `coverage_pct` / data-quality field per stock, shown on the dashboard and Top-N card. A 78/100 computed from 2 of 6 metrics must look different from 78/100 computed from 6 of 6.
- **Distress inputs are special**: a *missing* Altman/Piotroski input should not be treated as "passes the safety gate." Missing safety data → flag as "safety unknown," not "safe." Err toward excluding from a public Top-10 rather than including on incomplete data.
- Reuse the existing pattern: negative growth is floored *with a flag* concern (CONCERNS.md) — apply the same "value + flag" discipline so users can distinguish imputed from real.

**Warning signs:**
- Two stocks with identical OverallScore but wildly different input coverage.
- Pillar scores clustering at a suspicious neutral value (e.g. many 50s = midpoint imputation).
- `stats.html` coverage stats show a metric present for < 50% of the universe but still feeding scores at full weight.

**Phase to address:** **Phase A** establishes the missing-data contract (average-over-present + coverage flag) once, in the scoring engine. Every new metric in **B/C** must conform. `stats.html` (**Phase C**) surfaces coverage.

---

### Pitfall 6: Factor validity by sector — invalid inputs publishing a confident score

**What goes wrong:**
Altman Z (original form), Piotroski F, and EV/EBIT are **meaningless for banks, insurers, and other financials** — their balance sheets (no inventory, leverage is the business, "EBIT" is ill-defined, working-capital terms don't apply). Roughly 60–70 of the ~550 universe (S&P financials sector) fall here. Computing these anyway produces numbers that *look* valid, feed the pillars, and yield a confident 0–100 on a stock where half the safety/quality inputs are nonsense. DCF is similarly invalid for financials (Pitfall 7).

**Why it happens:**
The formulas run on any numbers you hand them — there's no exception thrown. Sector awareness requires an explicit lookup and per-metric applicability rules that are easy to skip when "it returns a number."

**How to avoid:**
- **Tag each ticker with a sector** (the universe is S&P 500 / Dow / Nasdaq-100 — GICS sector is readily available from Wikipedia constituents already scraped, or Finnhub profile).
- **Per-metric applicability matrix**: Altman Z, Piotroski, EV/EBIT, DCF → **not applied to Financials** (and use sector-appropriate variants or skip for REITs/utilities where relevant). When a metric is N/A for a sector, treat it as *missing* (Pitfall 5), not zero — and adjust the pillar to average over the metrics that *do* apply to that sector.
- **Never publish a Safety/Quality pillar for a bank that's silently built from inapplicable metrics.** Either use a financials-appropriate signal set or explicitly label the pillar lower-confidence for that sector.

**Warning signs:**
- Banks/insurers appearing in Top-10 on the strength of an EV/EBIT or Altman score.
- Altman Z computed for a company with no inventory/working-capital line.
- Financials sector has implausibly uniform Quality/Safety scores (formula returning a degenerate value).

**Phase to address:** **Phase B** must add the sector tag (cheap, needed for EV/EBIT applicability anyway). **Phase C** must implement the applicability matrix *before* Altman/Piotroski/DCF results are published. This is a publish-blocker for `top.html`/`stats.html` confidence.

---

### Pitfall 7: DCF-specific traps (forward + reverse)

**What goes wrong:**
DCF is a precision-illusion machine. Specific traps for this build:
- **Discount/terminal-growth sensitivity:** a 1% change in WACC or terminal g swings intrinsic value 20–40%. The plan uses WACC ≈ AAA yield + ERP and terminal ≈ 2.5%. Small input wobble → large `DCF_Discount_Pct` swing → noisy Value pillar.
- **Negative/cyclical FCF:** Stage-1 growth off a current FCF that's negative or at a cyclical peak/trough produces nonsense (negative intrinsic value, or extrapolating a peak forever).
- **Terminal value dominating:** with low discount rates, 70–85% of DCF value sits in the terminal — so the "DCF" is really just a terminal-growth assumption wearing a 5-year coat.
- **Reverse-DCF non-convergence:** solving implied growth from price can fail to converge, return multiple roots, or yield absurd implied growth (e.g. 90%) for high-multiple names — and a non-converged solve silently returning a default poisons the Growth pillar.
- **Applying DCF to financials:** invalid (see Pitfall 6).

**Why it happens:**
DCF *looks* rigorous, so it's trusted more than it deserves on free single-point data. The terminal-dominance and sensitivity problems are structural, not implementation bugs.

**How to avoid:**
- **Sensitivity guard:** clamp `DCF_Discount_Pct` and treat DCF as a *low-weight corroborating* signal, not a headline. Don't let one assumption-laden number dominate the Value pillar.
- **Input gating:** skip forward DCF when trailing FCF ≤ 0, or when FCF is highly volatile across available years (cyclical) — flag as "DCF N/A," don't fabricate. Skip for financials.
- **Terminal sanity:** terminal g must be < discount rate (else the formula diverges) and < long-run GDP (~2.5–3%); assert this and reject otherwise.
- **Reverse-DCF robustness:** bound the solver's growth search range, require convergence, and on non-convergence emit `None` + flag — never a silent default. Sanity-cap implied growth (e.g. reject > GROWTH_CAP-scale absurdities).
- Verify with the same hand-checked fixture (Pitfall 1) extended to a DCF case.

**Warning signs:**
- DCF fair values swinging wildly run-to-run with small AAA-yield moves.
- `DCF_FV` negative or implausibly large for cyclical/financial names.
- Reverse-DCF implied growth pinned at the solver bound or at a default.
- DCF-derived Value sub-score has a much wider distribution than the multiples-based ones.

**Phase to address:** **Phase C** (DCF is scheduled there). Build input-gating and convergence-flagging *with* the DCF, not after.

---

### Pitfall 8: Absolute thresholds becoming stale/arbitrary without a backtest

**What goes wrong:**
Locked decision 1 chose **absolute thresholds** (FCF yield ≥ 8% = full marks) over percentile ranks, accepting they're "more arbitrary." The risk: thresholds set by judgment in 2026 drift out of regime. In a high-rate environment an 8% FCF-yield bar that scored 40% of stocks "great" might score 5% three years later — the whole universe's scores sag or spike, and a "65" in 2026 isn't comparable to a "65" in 2029 *despite the design goal of comparability*. With no backtest, there's no empirical anchor for where thresholds should sit.

**Why it happens:**
Absolute thresholds *promise* cross-time comparability but only deliver it if the thresholds themselves are regime-appropriate. AAA yield (already fetched) shifts the meaning of every yield-based threshold; rate regimes shift "cheap."

**How to avoid:**
- **Keep all thresholds as named config constants** (the plan already does — alongside `LYNCH_*`/`GRAHAM_*`). This makes recalibration a config edit, not a code change.
- **Rate-relativize where it matters**: yield-based thresholds (FCF yield, earnings yield, EV/EBIT) and the DCF discount rate should reference the live AAA yield rather than a hardcoded number, so they breathe with the regime — Graham VA already does this (`* GRAHAM_HIST_AAA / aaa_yield`). Mirror that pattern.
- **Document threshold provenance** (why 8%?) so future tuning isn't cargo-culted.
- The deferred backtest (Phase D) is the real fix; until then, sanity-check threshold calibration against the live score distribution in `stats.html` (if 90% of stocks score < 30, the thresholds are too harsh).

**Warning signs:**
- Score distribution heavily skewed to one end (everything cheap, or nothing cheap).
- A snapshot from 6 months ago has a visibly different score *level* than today for unchanged fundamentals.
- A yield threshold hardcoded as a number sitting next to a live-fetched AAA yield.

**Phase to address:** **Phase A** (establish config-constant discipline + rate-relativization pattern). **Phase C** (`stats.html` distribution monitoring as the interim calibration check). **Phase D** (backtest, deferred) for the real anchor.

---

### Pitfall 9: Look-ahead / regime bias creeping in via "snapshots"

**What goes wrong:**
Snapshots (locked decision 1b, weekly/monthly) are stored "to enable future backtest." The trap: if the snapshot uses *restated* or *currently-available* fundamentals stamped with a past date, any future backtest built on them has look-ahead bias (you're scoring 2026-Q1 using data that wasn't knowable until 2026-Q3 restatement). Also, tuning thresholds to make *today's* universe look good is implicit regime-fitting.

**Why it happens:**
Free APIs return *latest* values, not point-in-time. A snapshot of `results.json` captures "what we computed today," which is fine as a forward record but dangerous if later mistaken for point-in-time historical fundamentals.

**How to avoid:**
- **Label snapshots as "computed-on-date" records, not point-in-time fundamentals.** Document clearly that they reflect data *as available on the snapshot date* — adequate for forward tracking, not a clean backtest dataset.
- Set the expectation now (in the snapshot schema/docs) so Phase D's backtest doesn't over-trust them.
- Avoid tuning thresholds against the current universe to look good — that's the no-backtest version of overfitting.

**Warning signs:**
- A future backtest shows implausibly good performance (classic look-ahead signature).
- Snapshot docs/schema don't state the data-vintage caveat.

**Phase to address:** **Phase C** (snapshot mechanism — bake the caveat into schema + docs). **Phase D** (backtest must account for it).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Treat missing metric as 0 in a pillar | One-line, no flag plumbing | Silently penalizes good stocks / hides value traps; corrupts public scores | **Never** — average over present + coverage flag is mandatory |
| Ship Top-N in Phase A before Altman/Piotroski exist | Faster first milestone | Ungated value traps on public page | Only with an *interim* gate from existing quality/safety signals (debt/equity, current ratio, EPS stability, negative-FCF) |
| Hardcode yield thresholds as fixed numbers | Simple constants | Go stale across rate regimes; break cross-time comparability | MVP only if rate-relativization is a tracked follow-up; prefer referencing live AAA yield from day one |
| Linear raw→sub-score with no clamp | Less config | One glitch maxes a sub-score and tops Top-10 | **Never** for free-tier inputs — clamp both tails |
| Run Altman/Piotroski/EV-EBIT/DCF on all tickers regardless of sector | No sector lookup needed | Confident garbage scores for ~60–70 financials | **Never** publicly — applicability matrix required before publish |
| Commit `results.json` snapshot without min-row guard | Simpler write path | Empty/partial snapshot pollutes the 5-year archive | **Never** — extend the existing min-100-row abort to snapshots |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Finnhub free tier | Treating sparse `None` fields as 0; no 429 backoff (CONCERNS.md) so rate-limited tickers silently degrade scores across the 550-loop | `_safe_float` → `None` → average-over-present; add retry/backoff so a rate-limit run doesn't quietly zero a pillar universe-wide |
| Finnhub `metric=all` bundle | Re-fetching FCF/EV/ROIC separately when much is already in the bundle we currently discard | Mine the existing bundle first (methodology doc) — fewer calls, less rate-limit exposure |
| yfinance statements | Assuming 10y EPS / FCF / share-count series are always present; unstable field names (`Basic EPS`, CONCERNS.md) | Guard every series length; missing share-count series → buyback yield = N/A + flag, not 0; pin yfinance version (no lockfile today) |
| FRED AAA yield | Hardcoding a discount rate / yield threshold instead of using the live value | Reference the fetched AAA yield for DCF WACC and yield thresholds (Graham VA already does this) |
| GitHub Actions run | Exit 0 even if most tickers failed (CONCERNS.md: no run-level failure detection) → composite computed on a half-empty universe, snapshot committed anyway | Add a run-level coverage gate (e.g. abort/alert if > X% tickers errored) *before* writing the public JSON/snapshot |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Piotroski 2-yr statements add heavy per-ticker fetches to the 550-loop | Runtime balloons past the existing 20–40 min; more 429s | Cache quarterly-changing data; fetch only deltas; reuse `metric=all` bundle | When statement fetches push total calls past free-tier rate limits |
| DCF/reverse-DCF solver per ticker | Slower loop; non-converged solves retry | Bounded solver, iteration cap, vectorize where possible | At 550 tickers if solver is unbounded/iterative-heavy |
| Snapshot archive committed weekly/monthly for 5 years | Repo bloat; slow clones; Pages slow | Store compact snapshots (trim columns / compress); rolling-window prune (STATE.md already specs 1/month, 5-yr rolling) | When cumulative snapshots dominate repo size |

## Security / Reputational Mistakes

This is a **public** tool — "security" here is largely reputational and quasi-advisory risk.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Publish a confident 0–100 on a stock with invalid sector inputs | Tool looks authoritative while being wrong (banks via Altman/EV-EBIT/DCF) | Sector applicability matrix; lower-confidence label for invalid-input sectors |
| Value trap atop public Top-10 | Tool appears to "recommend" a stock that then collapses | Altman/Piotroski gate; value-trap badge; interim gate in Phase A |
| Imply investment advice | Liability / trust | Clear "educational, not advice" disclaimer on Top-N and dashboard |
| Re-expose secrets while editing the pipeline | Repeat of the `diagnose_finnhub.py` hardcoded-key scar | Keep keys in env; don't add new diagnostic scripts with literals |

## UX Pitfalls (public tool)

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Black-box score | Users distrust a bare "73" with no reasoning | Decomposable pillars on the card (Value/Quality/Growth/Safety sub-scores) — methodology doc calls this "essential" |
| False precision | "73.4" implies accuracy the free single-point data can't support | Round to whole numbers or banded tiers; show coverage/confidence alongside |
| Uniform-looking scores from non-uniform coverage | A 70 from 2 metrics looks as solid as a 70 from 6 | Coverage badge / "data quality" indicator per stock |
| No "why is this cheap" context | Users can't distinguish value from trap | Surface the trap flag and the dominant pillar driving the rank |
| Stale snapshot mistaken for live | User acts on old data | Cache-bust the fetch (`?v=${Date.now()}`, existing gotcha); show data timestamp prominently |

## "Looks Done But Isn't" Checklist

- [ ] **Buy Price fix:** verify with a hand-computed fixture ticker — not just "the number looks different now."
- [ ] **Composite refactor:** verify Value pillar isn't ~6 correlated cheapness metrics (pairwise correlation check on the 550-row snapshot).
- [ ] **Winsorization:** verify both tails clamped for every raw input — feed a synthetic glitch (e.g. EV near 0) and confirm the sub-score caps, not explodes.
- [ ] **Missing data:** verify a stock with half its metrics absent gets a low-coverage flag, not a silently-zeroed or silently-full pillar.
- [ ] **Sector guards:** verify a bank does NOT get an Altman/EV-EBIT/DCF-driven public score.
- [ ] **Value-trap gate:** verify a distressed deep-discount name is capped/flagged and cannot top Top-10.
- [ ] **DCF:** verify negative-FCF and cyclical names are skipped (N/A + flag), terminal g < discount rate enforced, reverse-DCF non-convergence returns None not a default.
- [ ] **Snapshot:** verify min-row guard applies to snapshots and the data-vintage caveat is documented.
- [ ] **Run-level health:** verify a run where many tickers errored does NOT silently publish/snapshot a half-empty universe.
- [ ] **Thresholds:** verify yield-based thresholds reference live AAA yield, not hardcoded numbers.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Composite shipped on broken Buy Price | HIGH | Fix formula, recompute all scores, regenerate Top-N; any committed snapshots from the broken window are tainted — mark/prune them |
| Outlier maxed a public Top-10 entry | MEDIUM | Add the missing clamp, recompute; review whether other metrics need the same cap |
| Value trap published in Top-10 | MEDIUM (reputational) | Add gate, recompute, add value-trap badge; communicate the methodology change |
| Sector-invalid scores published | MEDIUM | Add applicability matrix, recompute financials' pillars; label affected sectors |
| Stale thresholds skew distribution | LOW | Recalibrate config constants; ideally rate-relativize so it self-corrects |
| Repo bloat from snapshots | LOW–MEDIUM | Prune to rolling window; compress; consider trimmed snapshot schema |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. Buy Price bug propagating into Value pillar | **Phase A (task 1, blocking)** | Hand-computed fixture ticker passes |
| 2. Outlier dominating (un-winsorized) | **A** (reused metrics), **B/C** (each new metric) | Synthetic-glitch test caps the sub-score |
| 3. Double-counting correlated factors | **A** (pillar architecture), revisit B/C | Pairwise correlation < ~0.8 within pillar; OverallScore ≠ pure cheapness rank |
| 4. Value trap atop public Top-10 | **A** (interim gate), **C** (Altman/Piotroski) | No Top-10 entry fails quality/safety gate |
| 5. Missing-data zeroing/penalizing | **A** (contract), enforced B/C | Half-coverage stock shows low-coverage flag, not silent score |
| 6. Sector-invalid inputs | **B** (sector tag), **C** (applicability matrix) | No bank gets Altman/EV-EBIT/DCF-driven public score |
| 7. DCF traps | **C** | Negative-FCF skipped; terminal g < discount; reverse-DCF non-convergence → None |
| 8. Stale absolute thresholds | **A** (config + rate-relativize), **C** (distribution monitor), **D** (backtest) | Yield thresholds reference live AAA; distribution not degenerate |
| 9. Look-ahead via snapshots | **C** (caveat in schema/docs), **D** (backtest) | Snapshot docs state data-vintage caveat |
| Run-level silent degradation | **A/B** (coverage gate before publish) | A high-error run aborts publish/snapshot |
| Empty/partial snapshot committed | **C** (extend min-row guard) | Snapshot write aborts < 100 rows |

## Sources

- v2-METHODOLOGY-EXPANSION.md — locked decisions, sequencing, pillar design, sources (George & Hwang 52w-high, QuantPedia formula OOS test, Acquirer's Multiple, Piotroski, S&P multi-factor methodology, Stockopedia StockRanks).
- This codebase: `stock_screener.py` (`_safe_float` L207, `GROWTH_CAP` L40, BRK-B scaling L269–271, `lynch_metrics`/`graham_metrics` L341–458, `combined_score` L528, min-100-row abort L664), CONCERNS.md (no test suite, no 429 backoff, no run-level failure detection, yfinance fragility, no input validation), STATE.md (deferred Buy Price bug, BRK-B history), CLAUDE.md (`.gitignore *.json` exception, cache-bust, min-row guard).
- Domain literature on factor construction (winsorization, factor collinearity), Altman Z (distress zones; inapplicability to financials), Piotroski F-Score (quality/value-trap filter), DCF sensitivity & terminal-value dominance, reverse-DCF convergence — standard quant-finance knowledge.

---
*Pitfalls research for: multi-factor composite scoring on free-tier data, public static tool, no backtest*
*Researched: 2026-06-17*
