# Structure

## Directory Layout

```
graham_screener/
├── stock_screener.py       # Main script — the entire application (~1217 lines)
├── requirements.txt        # Python dependencies (8 packages)
├── screener.yml            # GitHub Actions CI workflow
├── diagnose_yfinance.py    # Manual diagnostic: test yfinance connectivity
├── diagnose_finnhub.py     # Manual diagnostic: test Finnhub API connectivity
├── .env                    # Local credentials (gitignored)
├── .gitignore
└── .venv/                  # Local virtual environment (gitignored)
```

## Entry Point

`python stock_screener.py` → calls `main()` at the bottom of the file under `if __name__ == "__main__"`.

## Module Organization (within stock_screener.py)

The file is organized into 6 labeled steps:

```
stock_screener.py
│
├── Imports & dotenv load
├── CONFIGURATION (constants block)
├── LOGGING setup
│
├── STEP 1 — FETCH UNIVERSE
│   ├── WIKI_HEADERS (constant)
│   ├── _wiki_tables(url)           [private helper]
│   ├── fetch_sp500()
│   ├── fetch_dow30()
│   ├── fetch_nasdaq100()
│   └── get_universe()
│
├── STEP 2 — FETCH AAA YIELD
│   └── fetch_aaa_yield()
│
├── STEP 3 — FETCH FUNDAMENTALS
│   ├── FINNHUB_BASE (constant)
│   ├── get_finnhub_metrics(ticker)
│   ├── _safe_float(v)              [private helper]
│   ├── get_yf_price_and_history(ticker)
│   └── get_combined_data(ticker)
│
├── STEP 4 — COMPUTE METRICS
│   ├── compute_growth_5yr_cagr(annual_eps)
│   ├── lynch_metrics(price, eps, g, dy)
│   ├── graham_metrics(price, eps, g, aaa_yield, pb)
│   ├── graham_defensive_score(...)
│   └── combined_score(lynch_discount, graham_discount)
│
├── STEP 5 — PROCESS ALL TICKERS
│   ├── process_ticker(ticker, aaa_yield)
│   └── run_screener(universe, aaa_yield)
│
├── STEP 6 — PUSH TO GOOGLE SHEETS
│   ├── SIGNAL_COLORS (constant dict)
│   ├── _col_letter(n)              [private helper]
│   ├── _apply_color_coding(ws, df_clean)  [private]
│   ├── DOCS_CONTENT (constant list)
│   ├── _write_markdown_tab(sh, df)  [private]
│   ├── _write_docs_tab(sh)          [private]
│   └── push_to_gsheets(df)
│
└── MAIN
    └── main()
```

## CI Workflow (screener.yml)

```
Trigger: schedule (weekdays 11:00 UTC / 6am ET) + workflow_dispatch
Runner:  ubuntu-latest
Steps:
  1. actions/checkout@v4
  2. actions/setup-python@v5  (Python 3.11, pip cache enabled)
  3. pip install -r requirements.txt
  4. python stock_screener.py  (with secrets injected as env vars)
```

## Secrets Required

| Secret | Purpose |
|---|---|
| `FRED_API_KEY` | FRED API access |
| `FINNHUB_API_KEY` | Finnhub fundamental data |
| `GSHEET_CREDS_JSON` | Google service account (JSON content or file path) |
| `GSHEET_SPREADSHEET` | Target spreadsheet name (optional, has default) |
| `GSHEET_WORKSHEET` | Target worksheet name (optional, has default) |
| `TIINGO_API_KEYS` | Reserved — Tiingo not currently used |
