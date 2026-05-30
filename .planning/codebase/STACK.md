# Technology Stack

**Analysis Date:** 2026-05-29

## Languages

**Primary:**
- Python 3.11 — entire codebase; specified in `screener.yml` (`python-version: "3.11"`)

## Runtime

**Environment:**
- CPython 3.11 (local dev: any compatible install; CI: GitHub Actions `ubuntu-latest`)

**Package Manager:**
- pip — dependencies declared in `requirements.txt`
- Lockfile: not present (version ranges only, no `pip freeze` lockfile)

## Frameworks

**Core:**
- None — pure Python script; no web framework

**Data manipulation:**
- pandas >= 2.0.0 — DataFrame construction, sorting, resampling dividend history, HTML table parsing (via `pd.read_html`)

**Testing:**
- None — no test suite exists

**Build/Dev:**
- python-dotenv >= 1.0.0 — loads `.env` for local development; no-op in CI where env vars are injected directly

## Key Dependencies

**Critical:**
- `yfinance >= 0.2.40` — stock price (`fast_info.last_price`), historical income statement (EPS), dividend history
- `fredapi >= 0.5.1` — Moody's AAA corporate bond yield from FRED (`Fred.get_series("AAA")`)
- `gspread >= 6.0.0` — Google Sheets read/write (`client.open()`, `ws.update()`, `sh.batch_update()`)
- `google-auth >= 2.28.0` — Google service account credential handling (`Credentials.from_service_account_info` / `from_service_account_file`)
- `requests >= 2.31.0` — HTTP calls to Finnhub REST API and Wikipedia HTML scraping
- `lxml >= 4.9.0` — HTML parser backend for `pd.read_html()` (Wikipedia tables)

**Infrastructure:**
- `finnhub` — accessed via direct `requests` HTTP calls (not the finnhub-python SDK); base URL `https://finnhub.io/api/v1`

## Configuration

**Environment:**
- All secrets and configuration come from environment variables
- Local: `.env` file loaded by `python-dotenv` at startup (`.env` is gitignored)
- CI: GitHub Actions repository secrets injected as env vars in `screener.yml`

**Required env vars:**
| Variable | Purpose |
|---|---|
| `FRED_API_KEY` | FRED API authentication (required; raises `KeyError` if missing) |
| `FINNHUB_API_KEY` | Finnhub API authentication (required; raises `KeyError` if missing) |
| `GSHEET_CREDS_JSON` | Google service account — file path (local) or raw JSON string (CI) |
| `GSHEET_SPREADSHEET` | Target spreadsheet name (default: `"Lynch & Graham Screener"`) |
| `GSHEET_WORKSHEET` | Target worksheet/tab name (default: `"Results"`) |
| `TIINGO_API_KEYS` | Comma-separated Tiingo keys — optional, reserved for future use |

**Build:**
- No build step — script runs directly with `python stock_screener.py`
- CI installs deps with `pip install -r requirements.txt`

## Platform Requirements

**Development:**
- Python 3.11+
- `.env` file with the required credentials listed above
- Google service account JSON file (path set in `GSHEET_CREDS_JSON`)
- Network access to FRED, Finnhub, Yahoo Finance, Wikipedia, and Google APIs

**Production:**
- GitHub Actions `ubuntu-latest` runner
- All credentials stored as GitHub repository secrets
- Scheduled via cron: weekdays at 11:00 UTC (6:00 AM ET)

---

*Stack analysis: 2026-05-29*
