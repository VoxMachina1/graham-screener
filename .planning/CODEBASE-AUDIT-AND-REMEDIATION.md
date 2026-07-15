# Codebase Audit and Remediation Proposal

**Date:** 2026-07-15

**Audited production baseline:** `69b724e` (`origin/master`)

**Implementation branch:** `codex/model-audit-remediation`

**Audience:** Jacob and Claude

**Current permitted use:** Research and idea triage only; not decision-grade valuation

## Executive verdict

The static GitHub Pages architecture is a strong fit for the product: it is inexpensive, public, shareable, auditable through versioned JSON, and operationally simple. The principal risks are not the browser UI. They are upstream data fragility, weak publication controls, formula/control defects, incomplete sector applicability, correlated scoring inputs, and false precision in the final ranking.

The reviewed production model should not be used as a standalone buy recommendation. It is useful as an idea generator. A high score means “worth investigating,” not “underwritten expected return.” Trap flags should remain visible warnings rather than hard exclusions; unusual situations such as CMCSA can be exactly why a human should investigate a surfaced candidate.

This branch implements the unambiguous operational and formula fixes, plus a first screen-grade FCFF DCF. A 518-ticker Yahoo/FRED live run has been reviewed for coverage, outliers, terminal-value dependence, and sector behavior. Full-provider validation remains pending because the local Finnhub credential returned HTTP 401; the branch now fails immediately on that condition instead of publishing degraded rankings.

## Confirmed product decisions

1. `is_trap` remains a warning and research prompt. It does not veto a stock or mechanically reduce the score.
2. The former EPS projection is retained, but renamed as a discounted-earnings diagnostic. It is not described as DCF or WACC.
3. The new DCF method is FCFF for non-financial operating companies. Financial Services and Real Estate remain excluded pending sector-specific methods.
4. The current four-pillar score remains in production during review. A replacement should first run in shadow mode against historical snapshots.
5. Missing or unsuitable data must reduce confidence; it must never improve a candidate merely because a weak metric disappeared.

## Priority issue ledger

| ID | Severity | Finding type | Status on branch | Remediation and acceptance test |
|---|---|---|---|---|
| A-01 | Critical | Formula/control defect | Implemented | Correct rate scaling to `live AAA / 4.4`. The same discount must score lower when AAA yield is higher. Offline regression added. |
| A-02 | Critical | Formula/control defect | Implemented | Nasdaq-100 now reads the dedicated component-list page. All index fetches fall back to membership in the last published dataset if a live page fails. A mocked regression verifies the exact URL and ticker normalization. |
| A-03 | Critical | Formula/control defect | Implemented | Publication now requires at least 100 total rows, 100 valid scored rows, a 60% valid fraction, 60% Finnhub coverage, at least 100 valid FCFF DCFs, required columns, nonblank unique tickers, no duplicate ticker rows, ordered DCF ranges, valid terminal shares, and WACC above terminal growth. A provider-wide outage can no longer masquerade as 100% valid output. |
| A-04 | High | Formula/control defect | Implemented | Missing EPS remains a data error. Zero or negative EPS is retained as a financially meaningful warning, with Lynch/Graham discounts routed to the worst sentinel and other available factors still scored. Integration regression added. |
| A-05 | High | Formula/control defect | Implemented | Use aggregate `Total Debt` when present. Only reconstruct debt as long-term plus current when aggregate debt is absent. Regressions cover both paths. |
| A-06 | High | Formula/control defect | Implemented | Trap FCF sign now prefers the independently calculated Yahoo FCF yield and falls back to Finnhub FCF/share. `Trap_Reasons` identifies high leverage, weak liquidity, unstable earnings, and negative FCF while preserving warning-only behavior. |
| A-07 | High | Formula/control defect | Implemented | Monthly snapshot check now computes the actual first weekday. It no longer snapshots every weekday occurring on calendar days 1–7. |
| A-08 | High | Governance/control defect | Implemented, follow-up proposed | Actions now has concurrency protection, a 90-minute timeout, fail-fast offline tests, immutable action pins, non-publishing manual validation runs, and retained validation artifacts. Follow-up: pin Python dependencies and combine result/snapshot publication into one push. |
| A-09 | High | Missing decision output | Implemented as screen-grade prototype | Replace scored discounted EPS with FCFF DCF, an EV-to-equity bridge, paired range, reverse solve, and actual-minus-implied growth gap. Retain the old output only as `Discounted_Earnings_*`. Live QA added currency-consistency exclusion, a disclosed WACC guardrail, and leverage/terminal-dependence warnings. A valid-Finnhub Actions run remains required before calling the model stable. |
| A-10 | High | Unsupported assumption | Proposed | Replace missing-data renormalization with an explicit confidence score and minimum evidence gates. Neutral fallback values must not count as observed coverage. |
| A-11 | High | Not comparable without bridge | Proposed | Introduce sector-specific metric applicability. Banks/insurers need book-value, ROE/ROTCE, capital, and payout logic; REITs need AFFO/NAV/cap-rate logic; cyclicals need mid-cycle normalization. |
| A-12 | High | Unsupported assumption | Proposed | Normalize Piotroski by criteria evaluated or emit both pass count and evaluated count. A 4/4 record must not be represented as equivalent to 4/9. |
| A-13 | Medium | Output presentation | Proposed | Rename annual Finnhub EPS/dividend inputs honestly unless a true TTM source is present. Emit source period and source provider for load-bearing fields. |
| A-14 | Medium | Formula/control defect | Proposed | Missing capex must produce missing FCF, not an OCF-as-FCF proxy. The FCFF implementation already follows this rule; the separate FCF-yield helper should follow it too. |
| A-15 | Medium | Model architecture | Partially implemented | API keys are no longer required merely to import the module, and network entry points now fail explicitly when a required key is absent. Follow-up: split the 2,500-line module into configuration, universe adapters, provider adapters, accounting normalization, valuation, scoring, persistence, and orchestration. |
| A-16 | Medium | Governance/control defect | Partially implemented | Provider calls have request timeouts, and Finnhub authentication failures now stop immediately instead of issuing hundreds of rejected calls and publishing silently degraded scores. Follow-up: add bounded retries/backoff, provider-specific error counters, and cached inputs for transient failures. |
| A-17 | Medium | Governance/control defect | Partially implemented | GitHub Actions are pinned to verified release commit SHAs. Follow-up: pin/lock Python dependencies, add a dependency-update cadence, and add SRI/CSP or locally vendored static dependencies. |
| A-18 | Medium | Governance/control defect | Proposed | Stop indefinite Git-history growth from full daily JSON commits and duplicate snapshot commits. Consider artifact retention or periodic repository-history policy while keeping the latest Pages data committed. |
| A-19 | Medium | Output presentation | Partially implemented | Public methodology and README now distinguish FCFF DCF from discounted earnings. Remaining planning files need a reconciliation pass because phase status, branch naming, requirements, and code-size/test descriptions conflict. |

## FCFF DCF proposal and implementation

### Method selection

FCFF is the least-wrong generic DCF for the non-financial portion of this universe. It values operating cash flow independent of financing, then bridges enterprise value to common equity. It should not be forced onto banks, insurers, or REITs.

The implementation follows the conventional FCFF/WACC/enterprise-value structure described in Aswath Damodaran’s [FCFF valuation materials](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/fcff.html) and uses the Federal Reserve’s [10-year Treasury series](https://fred.stlouisfed.org/series/DGS10) as the risk-free anchor.

### Starting cash flow

```text
Base FCFF = Operating Cash Flow
          - absolute Capital Expenditure
          + absolute Interest Expense × (1 - effective tax rate)
```

This starts with operating cash flow because reported CFO already contains working-capital movement. After-tax interest is added back to convert the levered cash-flow starting point toward FCFF. Missing capex produces no DCF. Effective tax rate is tax provision divided by positive pretax income, bounded from 0% to 35%; otherwise the model uses 21% and should disclose that fallback.

### Discount rate

```text
Cost of Equity = 10Y Treasury + bounded Beta × 5.5% ERP
Pre-tax Cost of Debt = max(AAA yield, usable interest expense / average debt)
After-tax Cost of Debt = Pre-tax Cost of Debt × (1 - tax rate)
WACC = Equity Weight × Cost of Equity + Debt Weight × After-tax Cost of Debt
```

Market-capital-structure weights are used. Beta defaults to 1.0 when missing and is bounded from 0.5 to 2.0, with an explicit warning. The 5.5% ERP is deliberately retained as a conservative configured assumption, although Damodaran’s April 2026 trailing-payout implied ERP was approximately 4.67%. Claude should challenge whether 5.5%, 4.7%, or a periodically refreshed source is more appropriate.

### Forecast and terminal value

Live QA added a conservative screen guardrail: the effective WACC is the greater of the calculated WACC, the 10-year Treasury plus 2.5 percentage points, and terminal growth plus 4.0 percentage points. Both raw and effective WACC are emitted. This prevents an accidental current capital structure from compressing the discount-rate spread enough to mechanically explode equity value; it is an explicit screening control, not a company-specific target-capital-structure forecast.

- Five explicit years.
- Initial growth uses reconciled EPS growth as a screen-level FCFF-growth proxy.
- Initial growth is bounded from -20% to 15%.
- Growth fades linearly to terminal growth.
- Terminal growth is non-negative and capped at 3%.
- Terminal value uses Gordon growth and must have `WACC > terminal growth`.
- Terminal value as a percentage of enterprise value is emitted for review.

Using EPS growth as an FCFF proxy is the largest remaining modeling weakness. The preferred next improvement is to derive a normalized FCFF base and growth path from multiple annual cash-flow statements, with revenue/margin/reinvestment drivers where history supports them.

### Enterprise-to-equity bridge

```text
Equity Value = Present Value of FCFF + Cash - Total Debt
Value per Share = Equity Value / Diluted Shares
```

The model prefers diluted average shares, then outstanding shares, then a market-cap/price fallback. Longer term, leases, minority interest, preferred stock, pensions, options, and material non-operating investments should be added to the bridge when reliable fields exist.

Price and financial-statement currencies must match. Known mismatches are excluded from DCF rather than left unconverted; live QA confirmed that PDD mixed a USD quote with CNY financial statements and would otherwise produce a materially false per-share value. Missing currency metadata remains a visible warning because the screen cannot prove unit consistency.

### Range and reverse DCF

The displayed low case combines initial growth minus 2 points, WACC plus 1 point, and terminal growth minus 0.5 points. The high case applies the opposite changes. The base case alone feeds the current Value score.

Reverse DCF solves for initial FCFF growth that makes enterprise value reconcile to current equity price:

```text
Target EV = Price × Diluted Shares + Debt - Cash
Growth Gap = Bounded model growth - Market-implied FCFF growth
```

A positive gap says the screen’s growth proxy exceeds market-implied growth; it is a diligence prompt, not proof of mispricing. Solver non-convergence remains explicit.

### Live validation gate and 2026-07-15 results

The isolated run loaded 503 S&P 500, 30 Dow, and 103 Nasdaq-100 constituents for 518 unique tickers. FRED returned 5.52% AAA and 4.62% 10-year Treasury rates. Yahoo produced enough data for 303 FCFF DCFs; 224 reverse solves converged. Mechanical controls found no reversed ranges, no WACC-at-or-below-terminal rows, and no terminal shares outside 0%-100%.

Eight valuations had terminal value above 85% of EV. The deepest apparent discounts included CHTR, PDD, CMCSA, FOX, GPN, and LDOS. Review identified three distinct explanations: PDD was a currency-unit error and is now excluded; CHTR/CMCSA were highly leverage- and WACC-sensitive and now carry a WACC floor plus explicit warnings; several semiconductor, industrial, energy, and utility names had very low values because one-year FCFF and EPS-growth proxies are not mid-cycle normalized. Those cyclical/normalization limitations remain model weaknesses rather than formula errors.

The run was not full-provider-valid: every local Finnhub request returned HTTP 401, while the old guard still reported 518/518 scored rows because Yahoo fallbacks and missing-data renormalization masked the outage. The branch now adds a Finnhub preflight, fatal authentication handling, per-row provider provenance, and a minimum provider-coverage publication gate.

Before the FCFF result is considered stable:

1. Run the entire production universe without publishing automatically.
2. Report DCF coverage by sector and each missing-input reason.
3. Inspect the top and bottom 25 DCF discounts manually.
4. Flag WACC below 6%, WACC above 20%, terminal value above 85% of EV, negative equity bridges, and value ranges wider than 3×.
5. Compare at least ten companies across capital intensity and leverage against a simple analyst-built FCFF cross-check.
6. Confirm financials and REITs are absent rather than scored zero.
7. Review rank changes before allowing the new DCF field to affect public Top Picks.

Until those steps are complete, the status is `screen-grade`, not `decision-grade`.

## Counterproposal to the four-pillar score

### Design goal

Replace a single additive score full of correlated inputs with a research-priority system that answers three different questions separately:

1. **Opportunity:** Does valuation versus fundamentals look interesting?
2. **Confidence:** Do we have enough comparable, current evidence to trust the screen?
3. **Warnings:** What could make the apparent opportunity a false positive?

### Proposed five sleeves

| Sleeve | Suggested weight | Inputs and anti-double-counting rule |
|---|---:|---|
| Valuation support | 30% | One intrinsic-value gap plus one cash/earnings yield family. Lynch/Graham/FCFF may corroborate one another, but do not each receive full independent weight. |
| Business economics | 25% | ROIC, FCF conversion, profitability stability, and dilution-aware economics. Remove current ratio and debt/equity from this sleeve. |
| Expectations gap | 20% | Reverse-DCF growth gap, normalized growth versus price, and eventually estimate revisions. This separates “cheap” from “market already expects deterioration.” |
| Financial resilience | 15% | Sector-appropriate leverage, liquidity, Piotroski pass rate, Altman where applicable, and refinancing warning inputs. |
| Capital allocation | 10% | Dividends, net buybacks/dilution, debt reduction, and reinvestment consistency. Partial shareholder yield remains explicitly partial. |

Price distance from recent highs/lows should leave the valuation sleeve. It is a **setup overlay**—useful for “why now” and falling-knife warnings, but not evidence of intrinsic value.

### Combination method

Use a weighted geometric mean, with modest floors, rather than a simple arithmetic sum. This prevents one spectacular sleeve from fully compensating for a broken sleeve and reduces the benefit of loading several correlated cheapness signals.

Do not hide the intermediate result behind two decimal places. Publish whole-number sleeve scores and a research-priority band:

- `A — immediate research candidate`
- `B — watchlist / needs a trigger`
- `C — screen flag only`
- `Insufficient evidence`

### Confidence should be separate

```text
Confidence = observed coverage × source quality × sector applicability × freshness
```

- A missing metric does not receive 50 and does not disappear harmlessly.
- Sector-excluded metrics are not counted in the denominator.
- Defaulted beta, defaulted tax, annual-as-TTM fields, partial shareholder yield, short price history, and provider fallback each reduce confidence visibly.
- Critical missing evidence can cap research priority without erasing the candidate.

The dashboard should show Opportunity and Confidence on two axes. A high-opportunity/low-confidence stock is often exactly the sort of unusual case worth investigating, but it should not be confused with a well-supported high-confidence candidate.

### Warnings remain overlays

`is_trap` becomes a warning family with reasons such as:

- Negative FCF
- Weak liquidity
- High leverage
- Unstable or negative earnings
- High terminal-value dependence
- Cyclical peak-risk candidate
- Data-quality warning
- Corporate-action/SOTP candidate

Warnings do not automatically remove a company. They tell the analyst what must be explained before the idea advances.

### Archetype routing

A single rank should be supplemented with candidate archetypes:

- Quality compounder at a reasonable price
- Balance-sheet value
- Fallen angel / repair story
- Cyclical recovery candidate
- Capital-return candidate
- Event or sum-of-the-parts candidate
- Distressed optionality / high-risk research only

CMCSA could surface as an event/SOTP candidate with trap warnings rather than being either suppressed or treated as an ordinary statistically cheap cable company.

### Validation plan

1. Compute the proposed system in shadow mode; do not replace `OverallScore` immediately.
2. Recalculate all available monthly snapshots with point-in-time inputs where possible.
3. Measure forward 1-, 3-, 6-, and 12-month returns, drawdowns, turnover, sector exposure, and factor concentration.
4. Compare arithmetic versus geometric aggregation and with/without confidence adjustments.
5. Review the false-positive queue manually, especially negative-EPS, high-leverage, cyclical, and sector-excluded names.
6. Choose weights only after seeing stability and concentration. Do not optimize weights on the same short history used to judge success.

## Architecture proposal

Suggested module boundaries:

```text
screener/
  config.py
  universe.py
  providers/fred.py
  providers/finnhub.py
  providers/yahoo.py
  normalization/accounting.py
  valuation/lynch.py
  valuation/graham.py
  valuation/discounted_earnings.py
  valuation/fcff.py
  scoring/current.py
  scoring/proposed.py
  quality/piotroski.py
  quality/altman.py
  pipeline.py
  persistence.py
```

Rules for the split:

- No environment-variable lookup at import time for pure math.
- Provider adapters return typed normalized records plus source/as-of metadata.
- Pure valuation/scoring code performs no network or filesystem I/O.
- One ticker/provider failure is recorded, not swallowed into an empty dictionary without attribution.
- Publication is atomic: write to a temporary file, validate, then replace the live file.
- The current JSON schema remains backward-compatible through an explicit version and migration period.

## Automation proposal beyond this branch

1. Add retry/backoff and explicit network timeouts.
2. Cache successful universe constituents and macro inputs with as-of dates.
3. Implemented: emit Finnhub success count and coverage percentage into `stats.json`; extend this
   to per-provider reason codes when adapters are split from orchestration.
4. Implemented: manual workflow runs calculate, validate, and upload artifacts without pushing by
   default; `publish_results` must be explicitly enabled.
5. Combine results and a due monthly snapshot into one commit and one push.
6. Implemented for GitHub Actions with release-tag comments; Python package locking remains open.
7. Keep `cancel-in-progress: false`; two overlapping writers should queue, not cancel a nearly completed dataset.
8. Consider scheduling by UTC with documentation that daylight-saving time changes the local run hour, or use an external timezone-aware trigger if exact 6 a.m. ET matters.

## Documentation reconciliation proposal

The documentation should be treated as a maintained product surface:

- Replace stale claims that the project has no tests or a much smaller script.
- Reconcile `main` versus the actual default branch.
- Make requirement checkboxes and summary tables agree.
- Mark the four-pillar model as current, not empirically validated.
- Mark the five-sleeve design as proposed/shadow until approved.
- Define Yahoo sector labels as provider taxonomy, not GICS.
- Document every field’s period (`annual`, `TTM`, `latest fiscal year`) and provider.
- Document trap semantics as warnings.
- Add a model/version identifier to every generated payload.
- Add a short change log for score-affecting assumption changes.

## Questions for Claude’s review

1. Is the cached index fallback acceptable, or should a failed live index fetch fail closed after a maximum cache age?
2. Should valid publication require 60%, 75%, or a trailing-baseline-relative success rate?
3. Is 5.5% the desired ERP, or should the model adopt a periodically reviewed implied ERP?
4. Are beta bounds of 0.5–2.0 and initial FCFF growth bounds of -20% to 15% reasonable for this universe?
5. Should observed book cost of debt be used when above AAA, or should all companies receive a synthetic rating/default-spread schedule?
6. Should FCFF use the latest year, a three-year median, or a normalized multi-year cash-flow base?
7. Should the FCFF value affect `OverallScore` immediately after live QA, or remain diagnostic until the replacement score is validated?
8. Does the proposed five-sleeve structure sufficiently de-correlate the model, or should the product abandon a single composite entirely in favor of archetype ranks?
9. Which trap reasons should be visible on cards, and which should stay in the detailed table?
10. What historical and point-in-time dataset is acceptable for the first defensible backtest?

## Branch verification status

- Existing offline test scripts: passing.
- New remediation regression script: passing.
- Total named cases after this branch: 173, plus the KO fixture assertions.
- Live provider run: partially performed in an isolated output directory for all 518 tickers.
  Wikipedia, FRED, and Yahoo succeeded; the local Finnhub credential returned HTTP 401 for every
  ticker. The run exposed and drove the new provider-coverage gate, credential preflight, currency
  exclusion, WACC guardrail, and DCF warnings. A branch Actions run with the repository secret is
  the remaining live acceptance test.
- Public JSON regenerated: no.
- Public ranking behavior approved: no; requires live distribution review.
