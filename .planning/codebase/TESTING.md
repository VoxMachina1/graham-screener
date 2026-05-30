# Testing

## Status: No Formal Test Suite

There are no automated tests. No `pytest`, `unittest`, or test framework of any kind.

## What Exists

### Diagnostic Scripts

Two manual diagnostic scripts at the project root:

- `diagnose_yfinance.py` — manually tests yfinance connectivity and data retrieval for a sample ticker; used to debug when yfinance API breaks or returns unexpected data shapes
- `diagnose_finnhub.py` — manually tests Finnhub API connectivity and metric field availability; used when debugging missing/null fundamental data

These are run by hand (`python diagnose_yfinance.py`) when something breaks in production. They are not part of CI.

### CI Pipeline

`screener.yml` runs `python stock_screener.py` directly — a live end-to-end execution against real APIs with real credentials. If it exits without an exception, CI passes.

There is no:
- Unit test step
- Integration test step
- Snapshot/regression test
- Mocked API response testing

## Test Dependencies

`requirements.txt` contains zero test dependencies (no pytest, no responses/httpretty, no freezegun, no factory_boy).

## Coverage

| Area | Coverage |
|---|---|
| `lynch_metrics()` | None |
| `graham_metrics()` | None |
| `graham_defensive_score()` | None |
| `compute_growth_5yr_cagr()` | None |
| `combined_score()` | None |
| `get_combined_data()` | None (live API only) |
| `push_to_gsheets()` | None (live Sheets only) |
| `fetch_sp500/dow30/nasdaq100()` | None (live Wikipedia only) |

## Risk

Valuation math is the core business logic and it is entirely untested. A formula bug (wrong multiplier, off-by-one in CAGR years, wrong NaN guard) would silently produce incorrect buy/avoid signals across all ~500+ tickers.

## What a Minimal Test Suite Would Target

1. `compute_growth_5yr_cagr()` — edge cases: empty list, single value, negative base, negative current, NaN entries
2. `lynch_metrics()` — known inputs → expected PEG, PEGY, fair values, status labels
3. `graham_metrics()` — known inputs → expected VA, VB, FV, discount, status
4. `graham_defensive_score()` — boundary conditions for each of the 8 criteria
5. `combined_score()` — clipping behavior at 0 and 60, None handling
6. `_safe_float()` — NaN, None, string, valid float
