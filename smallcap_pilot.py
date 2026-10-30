"""Run the separate IJR-equity small-cap screener pilot."""

import csv
import hashlib
import json
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

import stock_screener as screener


IJR_URL = (
    "https://www.ishares.com/us/products/239774/"
    "ishares-core-s-p-small-cap-etf/latest-holdings.csv"
)
RESULTS_PATH = Path("docs/data/results_smallcap.json")
STATS_PATH = Path("docs/data/stats_smallcap.json")
HOLDINGS_PATH = Path("docs/data/holdings_smallcap.csv")


def parse_ijr_holdings(content: str) -> tuple[set[str], str]:
    """Return ordinary equity tickers and the holdings date from an IJR CSV."""
    lines = list(csv.reader(StringIO(content.lstrip("\ufeff"))))
    if not lines or lines[0] != ["iShares Core S&P Small-Cap ETF"]:
        raise ValueError("IJR holdings fund name changed")
    if len(lines) < 3 or len(lines[1]) < 2 or lines[1][0] != "Fund Holdings as of":
        raise ValueError("IJR holdings date is missing")
    as_of = datetime.strptime(lines[1][1], "%b %d, %Y").date().isoformat()
    header_index = next((i for i, row in enumerate(lines) if row[:3] == ["Ticker", "Name", "Type"]), None)
    if header_index is None:
        raise ValueError("IJR holdings columns changed")
    header = lines[header_index]
    if not {"Ticker", "Type", "Asset Class", "Currency"}.issubset(header):
        raise ValueError("IJR holdings required columns are missing")
    tickers = set()
    for values in lines[header_index + 1:]:
        if not values:
            continue
        if len(values) != len(header):
            raise ValueError("IJR holdings row has the wrong number of columns")
        row = dict(zip(header, values))
        if row["Type"] != "EQUITY":
            continue
        ticker = row["Ticker"].strip().upper().replace(".", "-")
        if ticker in {"", "-"} or row["Currency"] != "USD":
            raise ValueError("IJR equity holding has no valid USD ticker")
        tickers.add(ticker)
    if not 500 <= len(tickers) <= 750:
        raise ValueError(f"IJR equity count is implausible: {len(tickers)}")
    return tickers, as_of


def get_smallcap_universe() -> tuple[pd.DataFrame, dict]:
    """Fetch current IJR holdings, falling back to the last published pilot."""
    try:
        response = requests.get(IJR_URL, timeout=30)
        response.raise_for_status()
        tickers, as_of = parse_ijr_holdings(response.text)
        HOLDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        HOLDINGS_PATH.write_bytes(response.content)
        holdings_sha256 = hashlib.sha256(response.content).hexdigest()
        source_status = "live"
    except (requests.RequestException, ValueError) as exc:
        if not RESULTS_PATH.exists():
            raise RuntimeError(f"IJR holdings unavailable and no cached pilot exists: {exc}") from exc
        cached = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        tickers = {row["Ticker"] for row in cached["rows"] if row.get("Indexes") == "IJRHoldings"}
        if not 500 <= len(tickers) <= 750 or not cached.get("holdings_as_of"):
            raise RuntimeError("Cached IJR pilot is incomplete") from exc
        as_of = cached["holdings_as_of"]
        source_status = "cached"
        HOLDINGS_PATH.unlink(missing_ok=True)
        holdings_sha256 = None
        screener.log.warning("IJR live holdings failed (%s); using cached %s list", exc, as_of)
    universe = pd.DataFrame(
        [{"ticker": ticker, "indexes": "IJRHoldings"} for ticker in sorted(tickers)]
    )
    metadata = {
        "universe": "IJR equity holdings (SmallCap 600 proxy)",
        "holdings_as_of": as_of,
        "holdings_url": IJR_URL,
        "holdings_source_status": source_status,
        "holdings_sha256": holdings_sha256,
    }
    return universe, metadata


def main() -> None:
    universe, metadata = get_smallcap_universe()
    screener.log.info("IJR pilot: %s equities, holdings as of %s", len(universe), metadata["holdings_as_of"])
    aaa_yield = screener.fetch_aaa_yield()
    risk_free_rate = screener.fetch_risk_free_rate()
    screener._validate_finnhub_access()
    results = screener.run_screener(universe, aaa_yield, risk_free_rate)
    screener.write_json(results, RESULTS_PATH, STATS_PATH, metadata)


if __name__ == "__main__":
    main()
