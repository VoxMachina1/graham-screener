# Lynch & Graham Screener

A daily-automated value stock screener that applies Peter Lynch and Benjamin Graham valuation frameworks — plus Piotroski F-Score, Altman Z'', and a screen-grade FCFF DCF — across the S&P 500, Dow 30, and Nasdaq-100 (~550 tickers). Results publish to a free, public dashboard on GitHub Pages, updated automatically every weekday via GitHub Actions.

**No Google account, no signup, no friction — just open the link.**

## Live site

- **Dashboard** — `docs/index.html` — full sortable/filterable table, all metrics
- **Top Picks** — `docs/top.html` — ranked shortlist with score chips
- **Stats** — `docs/stats.html` — universe overview: score distribution, sector breakdown, data coverage
- **History** — `docs/history.html` — monthly historic snapshots
- **Methodology** — `docs/methodology.html` — full writeup of every signal and scoring rule

Open the live dashboard at <https://voxmachina1.github.io/graham-screener/>.

## How it works

```
GitHub Actions (weekdays, scheduled)
        │
        ▼
stock_screener.py
  ├─ Fetch tickers: Wikipedia (S&P 500 / Dow 30 / Nasdaq-100)
  ├─ Fetch fundamentals: yfinance (price, EPS history, dividends, statements)
  ├─ Fetch fundamentals: Finnhub (EPS/growth, balance sheet ratios, sector)
  ├─ Fetch macro: FRED (Moody's AAA yield + 10-year Treasury rate)
  ├─ Compute Lynch, Graham, Piotroski, Altman Z'', DCF, and factor metrics
  ├─ Score into 4-pillar OverallScore (0–100)
  └─ Write docs/data/results.json (+ monthly docs/data/snapshots/*.json)
        │
        ▼
git commit + push (from within the Action)
        │
        ▼
GitHub Pages serves docs/ — dashboard reads results.json client-side
```

No server, no database — the "backend" is a scheduled script that commits JSON to the repo, and the "frontend" is static HTML/JS reading that JSON. [Tabulator](https://tabulator.info/) (via CDN) powers the interactive table; there is no build step.

## Scoring methodology

Every ticker gets an absolute `OverallScore` (0–100), averaged across four pillars:

| Pillar | What it measures | Key inputs |
|---|---|---|
| **Value** | How cheap the stock is | Lynch/Graham discount %, FCF yield, earnings yield, price-vs-52w/5y-low, DCF discount % |
| **Quality** | Balance sheet & profitability strength | Defensive checklist, debt/equity, current ratio, ROIC |
| **Growth** | Earnings growth & consistency | Reconciled EPS growth rate, growth stability |
| **Safety** | Distress risk | Piotroski F-Score (0–9), Altman Z'', defensive/debt/current-ratio sub-scores |

Distress and valuation signals are gated by a **sector applicability matrix** — e.g. Altman Z'' and FCFF DCF are suppressed (`None`, never `0`) for Financial Services, and FCFF DCF is suppressed for Real Estate, since those models don't apply cleanly to those sectors. Trap flags are research warnings, not hard exclusions or score penalties.

The FCFF model converts operating cash flow to free cash flow to the firm, estimates a capital-structure-weighted discount rate, bridges enterprise value to diluted per-share equity value, and reverse-solves the initial FCFF growth implied by the market price. The former EPS projection is retained under explicitly named `Discounted_Earnings_*` fields as a secondary diagnostic, not described as DCF.

Full formulas, band thresholds, and the sector matrix are documented in `docs/methodology.html`.

## Data sources

| Source | Used for | Auth |
|---|---|---|
| [Wikipedia](https://en.wikipedia.org/) | Index constituent lists | none |
| [yfinance](https://github.com/ranaroussi/yfinance) | Price, EPS history, dividends, financial statements | none |
| [Finnhub](https://finnhub.io/) | Current EPS/growth and balance-sheet ratios | free API key |
| [FRED](https://fred.stlouisfed.org/) | Moody's AAA corporate yield and 10-year Treasury rate | free API key |

## Running it yourself

### Prerequisites

- Python 3.11+
- Free API keys from [Finnhub](https://finnhub.io/register) and [FRED](https://fred.stlouisfed.org/docs/api/api_key.html)

### Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
FINNHUB_API_KEY=your_key_here
FRED_API_KEY=your_key_here
```

### Run the screener

```bash
python stock_screener.py
```

This fetches the full ~550-ticker universe, computes every metric and score, and writes `docs/data/results.json` (plus `docs/data/stats.json`). A full run takes several minutes due to per-ticker API calls.

To preview the dashboard locally:

```bash
python -m http.server 8000 --directory docs
```

Then open `http://localhost:8000/`.

### Running the tests

```bash
python tests/test_scoring.py
python tests/test_growth_trap_fixes.py
python tests/test_factors_phase6.py
python tests/test_scoring_phase6.py
python tests/test_distress_phase7.py
python tests/test_dcf_phase7.py
python tests/test_remediation.py
python tests/test_valuation_fixture.py
```

Each file is a self-contained script (no pytest dependency) — run individually or chain with `&&`. All test fixtures are offline (no network calls, no API keys required).

## Automation

`.github/workflows/tests.yml` runs the complete offline regression suite on every pull request to
`master`. It has read-only repository permissions and receives no provider secrets.

`.github/workflows/screener.yml` runs the screener on a weekday schedule and on manual `workflow_dispatch`. It:

1. Installs dependencies and runs every offline regression script
2. Runs `stock_screener.py` with `FRED_API_KEY`/`FINNHUB_API_KEY` from repo secrets
3. Validates total rows, valid scored rows, Finnhub coverage, required columns, ticker uniqueness,
   DCF row coverage, ordered valuation ranges, WACC/terminal-growth relationships, and terminal-value shares
4. Uploads generated JSON as a retained workflow artifact for inspection
5. Commits and pushes `docs/data/results.json` (+ `stats.json`) only on scheduled runs or when a
   manual run explicitly sets `publish_results` to true
6. On the first weekday of each month, also commits a dated snapshot to `docs/data/snapshots/`

Manual runs are non-publishing by default. This makes it possible to validate code, credentials,
and output artifacts on a branch without changing the public dashboard.

To set this up on a fork, add `FRED_API_KEY` and `FINNHUB_API_KEY` as repository secrets (Settings → Secrets and variables → Actions), then enable GitHub Pages (Settings → Pages → source: `docs/` on the default branch).

## Project structure

```
stock_screener.py          # entire pipeline: fetch → compute → score → write JSON
requirements.txt           # Python dependencies
tests/                     # offline unit tests, one file per feature area
docs/                      # GitHub Pages site root
  index.html                 # full dashboard
  top.html                   # top-picks page
  stats.html                  # universe stats page
  history.html                # snapshot history page
  methodology.html            # full scoring methodology writeup
  app.js, style.css           # shared frontend logic/theme
  data/
    results.json               # latest run output (committed by Actions)
    stats.json                  # universe summary stats
    snapshots/                  # monthly historic snapshots + manifest
.github/workflows/screener.yml  # scheduled + manual pipeline run
```

## Status

The GitHub Pages migration (v1.0) and the methodology expansion / 4-pillar scoring overhaul (v2.0 — Piotroski, Altman Z'', DCF, sector guards, stats page, snapshots) are both complete and live. See `.planning/PROJECT.md` and `.planning/ROADMAP.md` for full project history and requirement tracking.

## Disclaimer

This tool is for informational and educational purposes only. It is not investment advice. Scores and signals are derived from public financial data and simplified valuation heuristics — always do your own research before making investment decisions.
