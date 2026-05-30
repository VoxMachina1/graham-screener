# Architecture

## Overview

A single-file Python script that runs a full batch pipeline: fetch → compute → publish. No web server, no database, no persistent state. Designed to run unattended on a schedule (GitHub Actions, weekdays 6am ET).

## Data Flow

```
Wikipedia (HTTP)     ──► fetch_sp500/dow30/nasdaq100()
                              │
                              ▼
                         get_universe()          ~500–600 deduplicated tickers
                              │
                              ▼
FRED API             ──► fetch_aaa_yield()       current Moody's AAA bond yield
                              │
                    ┌─────────┴───────────────────────────────────┐
                    │         run_screener() loop (sequential)     │
                    │                                              │
                    │   yfinance ──► get_yf_price_and_history()   │
                    │   Finnhub  ──► get_finnhub_metrics()         │
                    │                    │                         │
                    │            get_combined_data()               │
                    │                    │                         │
                    │   compute_growth_5yr_cagr()                 │
                    │   lynch_metrics()                            │
                    │   graham_metrics()                           │
                    │   graham_defensive_score()                   │
                    │   combined_score()                           │
                    │                    │                         │
                    │            process_ticker() → dict           │
                    └────────────────────┼─────────────────────────┘
                                         │
                                    results_df (DataFrame)
                                         │
                              push_to_gsheets()
                                    ├── Results worksheet (color-coded)
                                    ├── Documentation tab (static)
                                    └── Top 20 Summary tab (markdown table)
```

## Key Components

### Universe Fetcher (Step 1)
Scrapes S&P 500, Dow 30, and Nasdaq-100 from Wikipedia HTML tables using `requests` + `pd.read_html`. Requires a browser User-Agent header to avoid Wikipedia's bot blocks. Returns a deduplicated DataFrame with an `indexes` membership column.

### AAA Yield Fetcher (Step 2)
Single call to FRED API via `fredapi`. Returns the latest non-null value from the Moody's AAA series. Used as the discount rate in both Graham formula variants.

### Data Fetcher (Step 3)
Two-source merge:
- **yfinance**: price (via `fast_info`), EPS history (from `income_stmt`), dividend history (from `dividends`, resampled annually)
- **Finnhub REST API**: current EPS (`epsAnnual`), EPS growth CAGR (`epsGrowth5Y`/`epsGrowth3Y`), dividends per share, market cap (in $M, converted to $B), current ratio, debt/equity, book value per share, P/B ratio

Finnhub takes precedence for current fundamentals; yfinance used for historical EPS series (needed for defensive score checks).

### Valuation Engine (Step 4)
Pure functions, no side effects:

| Function | Purpose |
|---|---|
| `compute_growth_5yr_cagr()` | Fallback CAGR from yfinance EPS history |
| `lynch_metrics()` | PEG, PEGY, fair values, buy price, status bands |
| `graham_metrics()` | Version A & B intrinsic values, price bands |
| `graham_defensive_score()` | 8-criterion checklist, Pass/Borderline/Fail |
| `combined_score()` | 50/50 blended Lynch+Graham discount score |

### Ticker Processor (Step 5)
`process_ticker()` orchestrates fetch + compute for one ticker and returns a flat dict. `run_screener()` loops all tickers sequentially with a 0.25s delay, accumulates results, and sorts by `CombinedScore` descending.

### Google Sheets Publisher (Step 6)
`push_to_gsheets()` authenticates via service account, clears and rewrites the Results worksheet, applies traffic-light color coding via the Sheets batchUpdate API, and writes two additional tabs (Documentation, Top 20 Summary).

## Patterns

- **Procedural, single-file** — no classes, no modules, no package structure
- **Environment-variable-only config** — all secrets and tunable parameters from env vars or module constants
- **Graceful degradation** — missing data returns early with `{"Error": "reason"}` rather than raising; valid rows still process
- **Multi-source with fallback** — Finnhub primary, yfinance secondary for each data field
- **Batch Sheets API calls** — color coding uses a single `batchUpdate` request rather than per-cell calls

## Configuration Points

All tunable thresholds are module-level constants (see top of `stock_screener.py`):
- Screener parameters: `GROWTH_CAP`, `GRAHAM_NO_GROWTH_PE`, `GRAHAM_HIST_AAA`, etc.
- Graham defensive thresholds: `MIN_MARKET_CAP_B`, `MIN_CURRENT_RATIO`, `MAX_DEBT_EQUITY`, etc.
- Lynch price-band multipliers: `LYNCH_PEG_CHEAP`, `LYNCH_LV_STRONG_BUY`, etc.
- Graham price-band multipliers: `GRAHAM_DEEP_BUY`, `GRAHAM_BUY`, `GRAHAM_WATCH`
- Category-specific Lynch discount factors: `LYNCH_DISCOUNT` dict
