# External Integrations

**Analysis Date:** 2026-05-29

## APIs & External Services

**Financial Data — Fundamentals:**
- **Finnhub REST API** — EPS (annual TTM), EPS growth (5Y/3Y CAGR), market cap, current ratio, debt/equity, book value per share, dividends per share, P/B ratio
  - Endpoint: `GET https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={key}`
  - Client: raw `requests.get()` — no SDK; implemented in `stock_screener.py::get_finnhub_metrics()`
  - Auth: `FINNHUB_API_KEY` env var passed as `token` query param
  - Rate limiting: 250ms polite delay between tickers (`TIINGO_DELAY_SEC = 0.25`); 429 responses logged as warnings and return empty dict
  - Timeout: 15 seconds per request

**Financial Data — Price & History:**
- **Yahoo Finance (yfinance)** — current stock price (`fast_info.last_price`), historical annual EPS from income statement, dividend payment history
  - Client: `yfinance >= 0.2.40` Python package
  - Auth: none (public API)
  - Implemented in `stock_screener.py::get_yf_price_and_history()`
  - Fields accessed: `Ticker.fast_info`, `Ticker.income_stmt`, `Ticker.dividends`

**Financial Data — Bond Yields:**
- **FRED (Federal Reserve Economic Data)** — Moody's AAA corporate bond yield, series `"AAA"`
  - Client: `fredapi >= 0.5.1` Python package (`Fred.get_series()`)
  - Auth: `FRED_API_KEY` env var
  - Implemented in `stock_screener.py::fetch_aaa_yield()`

**Index Constituents — Web Scraping:**
- **Wikipedia** — S&P 500, Dow 30, and Nasdaq-100 constituent lists scraped from three Wikipedia article URLs
  - URLs:
    - S&P 500: `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`
    - Dow 30: `https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average`
    - Nasdaq-100: `https://en.wikipedia.org/wiki/Nasdaq-100`
  - Client: `requests.get()` with a Chrome-spoofed `User-Agent` header (required; Wikipedia blocks default Python UA), then `pd.read_html()` with `lxml` backend
  - Auth: none
  - Implemented in `stock_screener.py::_wiki_tables()`, `fetch_sp500()`, `fetch_dow30()`, `fetch_nasdaq100()`

**Reserved / Future:**
- **Tiingo** — API key rotation infrastructure exists (`TIINGO_API_KEYS` env var, comma-separated list) but Tiingo is not called for any active data fetching as of this analysis
- **FMP (Financial Modeling Prep)** — commented out in `screener.yml` (`# FMP_API_KEYS: ${{ secrets.FMP_API_KEYS }}  # reserved for future use`)

## Data Storage

**Databases:**
- None — no database; all computation is in-memory per run

**File Storage:**
- Local filesystem: none committed; `.csv` and `.xlsx` are gitignored (output artifacts)

**Caching:**
- None — each run re-fetches all data from scratch

## Authentication & Identity

**Google Service Account:**
- Implementation: `google-auth` `Credentials.from_service_account_info()` (CI) or `Credentials.from_service_account_file()` (local)
- Scopes: `https://www.googleapis.com/auth/spreadsheets`, `https://www.googleapis.com/auth/drive`
- Local dev: `GSHEET_CREDS_JSON` points to a JSON key file path on disk
- CI: `GSHEET_CREDS_JSON` holds the entire JSON key content as a GitHub Actions secret (detected by checking if the value starts with `{`)
- Implemented in `stock_screener.py::push_to_gsheets()`

## Output — Google Sheets

- **gspread >= 6.0.0** — primary output sink
  - Spreadsheet identified by name (`GSHEET_SPREADSHEET` env var)
  - Writes to three tabs per run:
    1. Results worksheet (`GSHEET_WORKSHEET` env var, default `"Results"`) — full screener output, ~600 tickers, color-coded signal columns
    2. `"Top 20 Summary"` tab — markdown table of top 20 buy signals
    3. `"Documentation"` tab — methodology reference
  - Uses `ws.update()` with `value_input_option="USER_ENTERED"` and `sh.batch_update()` for formatting (bold headers, frozen row, column widths, cell color coding)

## Monitoring & Observability

**Error Tracking:**
- None — no external error tracking service

**Logs:**
- `logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")`
- Logs written to stdout; visible in GitHub Actions run logs
- Per-ticker warnings on API failures (`log.warning()`); skips ticker and continues

## CI/CD & Deployment

**Hosting:**
- GitHub Actions — the only runtime environment beyond local development

**CI Pipeline:**
- Workflow file: `screener.yml` (stored in repo root; must be moved to `.github/workflows/` to be picked up by GitHub Actions)
- Trigger: cron schedule (`0 11 * * 1-5` = weekdays 11:00 UTC) + manual `workflow_dispatch`
- Runner: `ubuntu-latest`
- Python: 3.11 with pip cache enabled
- Steps: checkout → setup Python → `pip install -r requirements.txt` → `python stock_screener.py`

## Webhooks & Callbacks

**Incoming:** None

**Outgoing:** None

## Environment Configuration Summary

**Required (hard failure if missing):**
- `FRED_API_KEY`
- `FINNHUB_API_KEY`
- `GSHEET_CREDS_JSON`

**Optional (have defaults):**
- `GSHEET_SPREADSHEET` — defaults to `"Lynch & Graham Screener"`
- `GSHEET_WORKSHEET` — defaults to `"Results"`
- `TIINGO_API_KEYS` — defaults to empty list (unused)

**Secrets location:**
- Local: `.env` file in project root (gitignored)
- CI: GitHub repository secrets (`Settings → Secrets and variables → Actions`)

---

*Integration audit: 2026-05-29*
