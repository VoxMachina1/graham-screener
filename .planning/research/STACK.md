# Stack Research — v2.0 Methodology Expansion

**Domain:** Free-data static-hosting equity screener (Python pipeline → GitHub Pages dashboard)
**Researched:** 2026-06-17
**Confidence:** HIGH

## Headline

**No new third-party Python dependency is warranted, and no new paid API/credential is needed.** Every v2.0 signal is computable from (a) fields already inside the Finnhub `stock/metric?metric=all` bundle we currently fetch-and-discard, plus (b) a small number of *additional yfinance accessors on the Ticker we already construct per ticker* (`income_stmt` / `balance_sheet` / `cashflow`, and `history(period="5y")`). Math is pure arithmetic over pandas/numpy values already in the dependency tree. The only stack-shaped additions are: one numpy pin (currently transitive), two new static HTML pages reusing the existing Tabulator/vanilla-JS frontend, and a git-only snapshot step in GitHub Actions.

The dominant *risk* is not a missing library — it is **per-ticker runtime and Finnhub rate limits** once Piotroski/Altman pull multi-statement yfinance data across ~550 tickers. That is a sequencing/throttling concern, addressed below, not a new-dependency concern.

## Reuse-vs-new-fetch decision per signal

| Signal | Source decision | Concrete fields / accessors |
|--------|-----------------|------------------------------|
| 52w / 5y low distance + recency | **MIXED.** 52w high/low + dates already in Finnhub bundle (today). 5y low + week-of-low needs new yfinance history. | Finnhub: `52WeekLow`, `52WeekLowDate`, `52WeekHigh`, `52WeekHighDate`. 5y: `yf.Ticker(t).history(period="5y", interval="1wk")["Close"]` → `.min()`, `.idxmin()` for recency. |
| FCF yield | **REUSE.** Already in bundle. | `freeCashFlowTTM` (or `freeCashFlowPerShareTTM` × shares) ÷ `marketCapitalization`. Inverse already present as `pfcfShareTTM`. |
| EV / EBIT (Acquirer's Multiple) | **REUSE.** Already in bundle. | `enterpriseValue` (a.k.a. `ev`) ÷ (`ebitPerShareTTM` × shares). |
| Magic Formula (earnings yield + ROIC) | **REUSE (degrade-gracefully).** | Earnings yield = `ebitPerShareTTM`/EV or `epsAnnual`/price. ROIC: prefer bundle `roicTTM`; fall back to `roiTTM`/`roaTTM` (free-tier population is inconsistent — see caveat). |
| Shareholder yield | **REUSE + existing.** | Dividend already computed (`ttm_dps`/price). Net buyback proxy from bundle: change in `sharesOutstanding`/`shareOutstanding` series, or `currentEv/freeCashFlow` family; if absent, ship dividend-yield-only and flag low coverage. |
| Piotroski F-Score (0–9) | **NEW FETCH (heaviest).** Needs ~2yr income + balance + cashflow. | `yf.Ticker(t).income_stmt`, `.balance_sheet`, `.cashflow` (annual, 2 most-recent columns). Some ratios (current ratio, gross margin, asset turnover) also derivable from Finnhub `*Annual` fields to reduce yfinance load. |
| Altman Z-Score | **NEW FETCH (shared with Piotroski).** | Same `balance_sheet` (working capital, retained earnings, total assets/liabilities) + Finnhub `marketCapitalization` (market value of equity) + `enterpriseValue`/EBIT. Reuses the statements pulled for Piotroski — fetch once. |
| Forward 2-stage DCF | **REUSE.** No new fetch. | Inputs already present: `freeCashFlowTTM` (or per-share), growth `g` (Finnhub CAGR, existing), discount = FRED AAA yield (already fetched) + equity-risk-premium constant. Pure arithmetic. |
| Reverse DCF (solve implied g) | **REUSE.** No new fetch. | Same inputs; solve for `g` that makes DCF FV = current price. Closed-form-ish; if iterative, use stdlib (bisection) — **no scipy needed**. |
| 4-pillar 0–100 composite | **REUSE.** Pure computation over the above. | Threshold constants in the existing `LYNCH_*`/`GRAHAM_*` config style. numpy for winsorize/clamp. |

**Net new per-ticker fetches:** (1) `history(period="5y", interval="1wk")` and (2) the three annual financial statements (`income_stmt`/`balance_sheet`/`cashflow`) — fetched together, only when Piotroski/Altman are enabled (Phase C). Phases A–B add **zero** new network calls beyond what's already in the Finnhub bundle, because the bundle fields are already in the JSON we receive and throw away.

## Finnhub `metric=all` fields we already receive and currently discard

The `get_finnhub_metrics()` call already returns the full `metric` object (~117 fields); `get_combined_data()` only reads ~9 of them. The following are present in the same response — **no extra call** to use them:

| Field key | Used for |
|-----------|----------|
| `freeCashFlowTTM`, `freeCashFlowPerShareTTM`, `freeCashFlowAnnual` | FCF yield, DCF base FCF |
| `pfcfShareTTM` | price/FCF (inverse FCF yield, cross-check) |
| `enterpriseValue` / `ev` | EV/EBIT, EV/FCF |
| `currentEv/freeCashFlowAnnual`, `currentEv/freeCashFlowTTM` | Acquirer-style EV/FCF (when populated) |
| `ebitPerShareTTM`, `ebitdaPerShareTTM` | EV/EBIT, earnings yield |
| `roiTTM`, `roicTTM`, `roaTTM`, `roeTTM` | Magic Formula ROIC, Quality pillar |
| `grossMarginTTM`, `netProfitMarginTTM`, `operatingMarginTTM` | Piotroski margin trend, Quality |
| `52WeekHigh`, `52WeekHighDate`, `52WeekLow`, `52WeekLowDate` | 52w distance + high-proximity trap flag |
| `payoutRatioTTM`, `currentDividendYieldTTM` | Shareholder yield support |
| `currentRatioAnnual`, `longTermDebt/equityAnnual`, `totalDebt/totalEquityAnnual`, `netInterestCoverageTTM` | Altman/Piotroski leverage & liquidity (avoids some statement parsing) |

**Caveat (MEDIUM confidence):** free-tier population of the derived fields (`roicTTM`, `currentEv/freeCashFlowTTM`, some `*PerShareTTM`) is **inconsistent across tickers** — some return `null`. This is fine: the existing `_safe_float()` → `None` pattern plus the locked "average over available metrics within a pillar, flag low coverage" rule handles it without new code shape. Do **not** treat any single field as guaranteed-present.

## Recommended Stack (additions/changes only)

### Core Technologies (changes)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11 | unchanged | Already pinned in `screener.yml`; no reason to bump. |
| yfinance | `>=0.2.55,<1.0` (currently 0.2.66 installed) | Add `income_stmt`/`balance_sheet`/`cashflow`/`history` accessors for Piotroski, Altman, 5y low | Accessors stabilized in 0.2.5x to match the Yahoo site; a 1.x line now exists but is a major-version jump — **stay on 0.2.x for this milestone** to avoid an untested break in the production-proven pipeline. Tighten the floor from `0.2.40` to `0.2.55` so the statement-table key changes are present. |
| numpy | `>=1.26,<3` (add explicit pin; 2.2.2 present transitively) | winsorize/clamp raw pillar inputs, vectorized threshold mapping | Already in the tree via pandas/yfinance; pin it explicitly because v2.0 code imports it directly. No new install on CI. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pandas | `>=2.0.0` (unchanged) | Statement DataFrames, 5y resample, snapshot diffs | Already present; `income_stmt` etc. return DataFrames. |
| (stdlib) `statistics` / hand-rolled bisection | n/a | Reverse-DCF implied-growth solve | Bisection over a monotonic DCF is ~15 lines — **avoid scipy**. |
| (stdlib) `datetime`, `json`, `pathlib`, `shutil` | n/a | Snapshot file naming/copy in Actions | Already imported; `shutil.copyfile` for snapshots. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| GitHub Actions (existing `screener.yml`) | Add a periodic snapshot job/step | Already has `permissions: contents: write` and a git push step — extend, don't replace. |
| Tabulator 6.4 (CDN, existing) | `top.html` / `stats.html` tables | Same library, same `results.json`; no new frontend dep, no build step. |

## Installation

`requirements.txt` delta (the only file change for dependencies):

```text
# changed
yfinance>=0.2.55,<1.0     # was: yfinance>=0.2.40  — need stable statement accessors
# added (explicit pin for direct import; already transitive)
numpy>=1.26,<3
```

No `pip install` of any genuinely new package on CI. Frontend: zero installs (CDN).

## Snapshot mechanism (git + Actions only — no new infra)

Locked decision 1b = weekly/monthly snapshots, **not daily**. Implement entirely in the existing workflow:

1. **Storage layout:** `docs/data/snapshots/results-YYYY-MM-DD.json` (a copy of that run's `results.json`). Keeping snapshots under `docs/` means GitHub Pages can serve them later for the deferred trend/backtest work with zero extra hosting.
2. **`.gitignore` gotcha (critical):** the repo ignores `*.json`. `docs/data/results.json` is already excepted; the snapshot path needs its own exception, e.g. `!docs/data/snapshots/*.json` (or `!docs/data/snapshots/`). Without this the snapshots will silently never commit — same trap called out in CLAUDE.md.
3. **Cadence without daily noise:** the cron stays weekday-daily for `results.json`; gate the snapshot copy on a date condition (e.g. only on the first run of an ISO week / first business day of month) inside the Python writer or a small shell `if` in the workflow. A separate `schedule:` cron entry (`0 11 * * 1` for Mondays) feeding a `workflow_dispatch`-style flag is the cleaner option.
4. **Commit:** extend the existing "Commit and push results" step to `git add docs/data/snapshots/` alongside `results.json`. The existing `git diff --cached --quiet` guard already prevents empty commits.
5. **Min-row guard reuse:** snapshots should only be written *after* `write_json()` passes its `< 100 rows` abort, so a bad run never gets frozen into history.

No database, no external object store, no new action — `actions/checkout@v4` + `setup-python@v5` + git push are sufficient.

## Rate-limit & runtime risk (the real constraint)

| Concern | Detail | Mitigation |
|---------|--------|-----------|
| Finnhub free tier | 60 calls/min. Pipeline already does **1** `metric=all` call/ticker with a 250ms delay (~550 calls ≈ 2.3 min spread). **v2.0 adds no new Finnhub calls** if we mine the existing bundle. | Keep it to one Finnhub call/ticker. Do **not** add per-ticker Finnhub statement endpoints — use yfinance for statements instead. |
| yfinance new fetches | `history(5y)` + 3 statement tables per ticker materially increase wall-clock and Yahoo throttling exposure across ~550 tickers (Phase C). Yahoo has no hard documented limit but rate-limits aggressively. | (a) Reuse the single `yf.Ticker(t)` object already built in `get_yf_price_and_history()` — fetch price, history, and statements from one Ticker, not four. (b) Phase C only. (c) Add modest backoff/retry; the existing per-ticker try/except-and-skip already degrades gracefully. |
| Quarterly-data caching | Statements/5y-low change slowly (quarterly), but price/EPS change daily. Re-fetching statements every weekday is wasteful and raises throttle risk. | **Cache slow-moving fundamentals.** Recommended: a committed `docs/data/fundamentals_cache.json` keyed by ticker with a fetch date; refresh a row only if older than ~30 days. Honors the static/git-only constraint (no DB) and the `.gitignore` exception pattern (needs `!docs/data/fundamentals_cache.json`). This is the single highest-value optional add for keeping Phase C runtimes sane. |
| Actions wall-clock | Free Actions minutes are ample for a few-minute job, but 550× extra yfinance round-trips could push runtime up. | Cache (above) keeps the steady-state run near v1.0 timings; only cache-cold tickers pay the statement-fetch cost. |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Mine existing Finnhub bundle | Finnhub `/stock/financials-reported` per ticker | Never for this milestone — adds 550 Finnhub calls and blows the 60/min budget. |
| yfinance statements | Finnhub financial-statement endpoints | Only if yfinance statement coverage proves unreliable for a pillar; even then, cache hard. |
| Hand-rolled bisection for reverse DCF | scipy `brentq` | Never — scipy is a heavy new dep (numpy/BLAS) for a 15-line monotonic root-find. |
| numpy winsorize | pandas-only clip | Either works; numpy chosen because it's already present and clamp/winsorize reads cleaner. Pure-pandas is an acceptable substitute if avoiding the explicit numpy pin. |
| `docs/data/snapshots/*.json` in repo | git tags / separate orphan branch / external storage | Only if repo size becomes a problem after many months; weekly/monthly cadence keeps growth small (~tens of files/year). |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Any new paid API or credential | Constraint: zero new credentials; FRED+Finnhub free tiers cover everything | Existing FRED + Finnhub bundle + yfinance |
| scipy | Heavy transitive weight for one root-find | stdlib bisection |
| A database (sqlite/postgres) for snapshots or cache | Constraint: static hosting, no server/DB | Committed JSON files under `docs/data/` |
| A JS framework (React/Vue) or any build step for `top.html`/`stats.html` | Constraint: no build step; v1.0 is vanilla JS + Tabulator CDN | Reuse Tabulator 6.4 CDN + vanilla JS, read the same `results.json` |
| A second/new JSON output file at repo root | `.gitignore *.json` trap; extra schema surface | Extend existing `results.json` (already excepted) with new columns + nested `scores` object |
| yfinance 1.x (major bump) this milestone | Unverified break risk in production-proven pipeline | Stay on yfinance 0.2.5x; defer 1.x to a dedicated upgrade pass |
| Per-ticker Finnhub statement calls | Burns the 60/min free-tier budget across 550 tickers | yfinance statements + 30-day cache |

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| yfinance 0.2.55–0.2.66 | pandas 2.x, numpy 2.x | Statement accessors (`income_stmt`/`balance_sheet`/`cashflow`) stable in this band; `history(period=...)` unchanged for years. |
| numpy 2.2.x | pandas 2.2.x | Both already resolve together in the current environment (verified locally). |
| Tabulator 6.4 (CDN) | vanilla JS, `results.json` schema | Unchanged from v1.0; new pages add no version constraint. |

## Sources

- Finnhub Basic Financials / `stock/metric` field reference — https://finnhub.io/docs/api/company-basic-financials — confirms `52WeekHigh/Low(+Date)`, `enterpriseValue`/`ev`, FCF & EV/FCF families, ROIC/ROI/ROA/ROE, `ebitPerShareTTM`. MEDIUM (page is JS-rendered; field set cross-checked below).
- Robot Wealth, "Exploring the finnhub.io API" — https://robotwealth.com/finnhub-api/ — documents the `metric` object returning ~117 fundamental fields, confirming the bundle breadth we already receive. HIGH.
- yfinance API reference (`Ticker.income_stmt`, `.balance_sheet`, `.cashflow`, `.history`) — https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.html — confirms the accessors and the 0.2.x table-format note. HIGH.
- yfinance on PyPI (version availability: 0.2.66 installed, 1.4.1 latest) — https://pypi.org/project/yfinance/ — HIGH.
- Existing codebase (`stock_screener.py`, `requirements.txt`, `.github/workflows/screener.yml`, CLAUDE.md gotchas) — primary source for what's already fetched/discarded and the git/Actions constraints. HIGH.
- Locked decisions — `.planning/research/v2-METHODOLOGY-EXPANSION.md`. HIGH.

---
*Stack research for: v2.0 methodology-expansion signals on free-data static pipeline*
*Researched: 2026-06-17*
