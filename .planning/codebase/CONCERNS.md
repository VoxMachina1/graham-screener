# Concerns & Technical Debt

## High Severity

### CRITICAL — Hardcoded API Key in diagnose_finnhub.py
`diagnose_finnhub.py:16` contains a Finnhub API key as a hardcoded string literal. The `.gitignore` does not exclude `.py` files. If this file is pushed to GitHub, the key is permanently exposed in git history.

**Action required:** Remove the hardcoded key and replace with `os.environ["FINNHUB_API_KEY"]` before any git push.

### No Test Suite — Valuation Math Untested
`lynch_metrics()`, `graham_metrics()`, `graham_defensive_score()`, and `compute_growth_5yr_cagr()` are the core business logic. A silent formula bug (wrong multiplier, wrong CAGR years, bad NaN guard) produces incorrect buy/avoid signals for all ~550+ tickers with no detection mechanism.

### Wikipedia Scraping is Fragile
`fetch_sp500()` uses `tables[0]` with no column validation. `fetch_dow30()` and `fetch_nasdaq100()` loop looking for `"Symbol"`/`"Ticker"` columns. Any Wikipedia table restructure or additional table inserted before the target breaks the entire run silently or with a confusing error.

### yfinance Unofficial API Breaks Frequently
yfinance reverse-engineers Yahoo Finance's private API. It breaks several times per year when Yahoo changes its internal endpoints or response schemas. `income_stmt` field names (`"Basic EPS"`, `"Diluted EPS"`) are particularly unstable. No monitoring or alerting exists for mass yfinance failures.

### No Run-Level Failure Detection
`run_screener()` continues past individual ticker failures (they return `{"Error": "reason"}`). The script exits 0 even if every single ticker failed. GitHub Actions marks the run "Success." A complete data outage (yfinance down, Finnhub quota exhausted) is invisible in CI.

---

## Medium Severity

### No Finnhub 429 Retry/Backoff
`get_finnhub_metrics()` logs a warning on non-200 status and returns `{}`. There is no retry, exponential backoff, or delay on 429 responses. Rate-limited tickers are silently dropped and appear in the sheet as "Growth N/A" or "No EPS."

### Sequential Processing — 20+ Minute Runtime
~550 tickers processed one at a time with `time.sleep(0.25)` between each. This is ~140 seconds minimum just in sleep, plus API latency. Actual runtime is likely 20–40 minutes. No checkpointing — a crash at ticker 500 loses all results. GitHub Actions has a 6-hour job limit, but this creates an unnecessarily long window of potential failure.

### 1,200-Line Single File
All logic — fetching, computation, output formatting, documentation strings, color maps — lives in one file. Adding a new data source or output format requires editing the same file that contains valuation math. Growing unwieldy.

### No Input Data Validation
Implausible API values (negative BVPS, EPS of $0.0001, market cap of $0, P/B of 500) flow directly into valuation math. `graham_metrics()` and `lynch_metrics()` check for `eps <= 0` but not for obviously corrupted values. A Finnhub data quality regression would produce garbage fair values.

### Google Sheets as Sole Output — No Backup
If the Sheets write fails (quota, auth, network), the entire run's computed results are lost. No local CSV, no intermediate file, no retry. `push_to_gsheets()` writes everything or nothing.

### Negative Growth Silently Floored to 1%
`process_ticker()` floors negative growth to 1.0 with a `log.info` message, but `row["Growth_g_Pct"]` still shows the floored value. A user reading the sheet cannot distinguish "grew 1%" from "actually shrinking but floored." No flag column or footnote.

---

## Low Severity

### Error Rows Invisible in Sheet Output
Tickers that fail (no price, no EPS, growth N/A) have an `"Error"` key but no systematic way to see them in the sheet. They appear as sparse rows or are absent. A user cannot tell how many tickers were skipped or why.

### Dead Config — TIINGO_API_KEYS and TIINGO_DELAY_SEC
`TIINGO_API_KEYS` is parsed from env vars and `TIINGO_DELAY_SEC = 0.25` is defined as a constant. Tiingo is never called. The 0.25s sleep in `process_ticker()` is labeled as a Tiingo delay but is actually applied to every ticker regardless. The comment "Optional — not currently used for any active data fetching" acknowledges this but the dead config remains.

### diagnose_*.py Are Dev Tools with No CI Safety
`diagnose_yfinance.py` and `diagnose_finnhub.py` are manual debugging tools. They are not excluded from the repo, not documented in any README, and — in the case of `diagnose_finnhub.py` — contain a hardcoded API key. They provide no automated protection.

### No Dependency Lockfile
`requirements.txt` uses `>=` lower bounds only (e.g., `yfinance>=0.2.40`). No `pip freeze` lockfile. yfinance version drift is a known breakage vector — a new yfinance release can change `income_stmt` field names or `fast_info` attributes and break the run silently. CI uses pip cache but not pinned versions.
