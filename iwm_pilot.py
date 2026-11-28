"""Run an isolated Russell 2000 proxy screen from retained IWM holdings."""

import csv
import hashlib
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

import stock_screener as screener


IWM_URL = "https://www.ishares.com/us/products/239710/ishares-russell-2000-etf/latest-holdings.csv"
OUTPUT = Path("pilot-output/iwm")
LISTED_EXCHANGES = {"NASDAQ", "NYSE", "Nyse Mkt Llc"}


def parse_iwm_holdings(content: str) -> tuple[set[str], str, dict]:
    lines = list(csv.reader(StringIO(content.lstrip("\ufeff"))))
    if not lines or lines[0] != ["iShares Russell 2000 ETF"]:
        raise ValueError("IWM holdings fund name changed")
    if len(lines) < 3 or len(lines[1]) < 2 or lines[1][0] != "Fund Holdings as of":
        raise ValueError("IWM holdings date is missing")
    as_of = datetime.strptime(lines[1][1], "%b %d, %Y").date().isoformat()
    start = next((i for i, row in enumerate(lines)
                  if row[:4] == ["Ticker", "Name", "Sector", "Asset Class"]), None)
    if start is None:
        raise ValueError("IWM holdings columns changed")
    header = lines[start]
    if not {"Ticker", "Asset Class", "Currency", "Exchange"} <= set(header):
        raise ValueError("IWM holdings required columns are missing")
    tickers = set()
    omitted = {"unlisted_or_foreign": 0, "missing_ticker": 0, "duplicate_ticker": 0}
    for values in lines[start + 1:]:
        if not values:
            continue
        if len(values) != len(header):
            raise ValueError("IWM holdings row has the wrong number of columns")
        row = dict(zip(header, values))
        if row["Asset Class"] != "Equity":
            continue
        if row["Currency"] != "USD" or row["Exchange"] not in LISTED_EXCHANGES:
            omitted["unlisted_or_foreign"] += 1
            continue
        ticker = row["Ticker"].strip().upper().replace(".", "-").replace(" ", "-")
        if ticker in {"", "-"}:
            omitted["missing_ticker"] += 1
            continue
        if ticker in tickers:
            omitted["duplicate_ticker"] += 1
            continue
        tickers.add(ticker)
    if not 1800 <= len(tickers) <= 2200:
        raise ValueError(f"IWM listed equity count is implausible: {len(tickers)}")
    return tickers, as_of, omitted


def get_iwm_universe() -> tuple[pd.DataFrame, dict]:
    response = requests.get(IWM_URL, timeout=30)
    response.raise_for_status()
    tickers, as_of, omitted = parse_iwm_holdings(response.text)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "holdings.csv").write_bytes(response.content)
    universe = pd.DataFrame([{"ticker": ticker, "indexes": "IWMHoldings"}
                             for ticker in sorted(tickers)])
    return universe, {"universe": "IWM listed USD equity holdings (Russell 2000 proxy)",
                      "holdings_as_of": as_of, "holdings_url": IWM_URL,
                      "holdings_source_status": "live",
                      "holdings_sha256": hashlib.sha256(response.content).hexdigest(),
                      "omitted_source_rows": omitted}


def main() -> None:
    universe, metadata = get_iwm_universe()
    screener.log.info("IWM pilot: %s listed equities, holdings as of %s",
                      len(universe), metadata["holdings_as_of"])
    aaa_yield = screener.fetch_aaa_yield()
    risk_free_rate = screener.fetch_risk_free_rate()
    screener._validate_finnhub_access()
    results = screener.run_screener(universe, aaa_yield, risk_free_rate)
    screener.write_json(results, OUTPUT / "results.json", OUTPUT / "stats.json", metadata)


if __name__ == "__main__":
    main()
