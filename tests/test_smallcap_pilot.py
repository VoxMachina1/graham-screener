"""Offline checks for the IJR pilot's identity, filtering, and separate output."""

import os
import hashlib
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import smallcap_pilot
from smallcap_pilot import parse_ijr_holdings
import stock_screener as screener


def _csv(rows):
    return (
        'iShares Core S&P Small-Cap ETF\n'
        'Fund Holdings as of,"Oct 22, 2026"\n\n'
        'Ticker,Name,Type,Asset Class,Currency\n'
        + "\n".join(f"T{i},Company {i},EQUITY,Equity,USD" for i in range(500))
        + "\n" + rows
    )


def test_filters_non_equity():
    tickers, as_of = parse_ijr_holdings(_csv(
        "USD,Cash,CASH,Cash,USD\n"
        "XTSLA,Fund,STIF,Money Market,USD\n"
        "T1,Overlay,SWAP,Equity,USD\n"
    ))
    assert len(tickers) == 500
    assert "USD" not in tickers and "XTSLA" not in tickers
    assert as_of == "2026-10-22"


def test_rejects_wrong_fund_and_layout():
    for altered in (
        _csv("").replace("iShares Core S&P Small-Cap ETF", "Another Fund"),
        _csv("").replace("Ticker,Name,Type", "Ticker,Name,Asset Type"),
    ):
        try:
            parse_ijr_holdings(altered)
        except ValueError:
            pass
        else:
            raise AssertionError("Changed holdings file was accepted")


def test_separate_output_keeps_main_results_untouched():
    with TemporaryDirectory() as folder:
        main_path = Path(folder) / "results.json"
        pilot_path = Path(folder) / "results_smallcap.json"
        stats_path = Path(folder) / "stats_smallcap.json"
        main_path.write_text("main data", encoding="utf-8")
        validation = {
            "valid_rows": 1, "total_rows": 1,
            "valid_fraction": 1.0, "finnhub_fraction": 1.0, "dcf_rows": 1,
        }
        df = pd.DataFrame([{"Ticker": "T1", "Indexes": "IJRHoldings"}])
        with patch.object(screener, "_validate_output_dataframe", return_value=validation), \
             patch.object(screener, "_compute_stats", return_value={"universe_count": 1}):
            screener.write_json(df, pilot_path, stats_path, {"holdings_as_of": "2026-10-22"})
        assert main_path.read_text(encoding="utf-8") == "main data"
        assert '"holdings_as_of":"2026-10-22"' in pilot_path.read_text(encoding="utf-8")
        assert stats_path.exists()


def test_live_pilot_retains_exact_holdings_source():
    content = _csv("").encode("utf-8")
    class Response:
        def __init__(self, data):
            self.text = data.decode("utf-8")
            self.content = data
        def raise_for_status(self):
            pass
    with TemporaryDirectory() as folder:
        source = Path(folder) / "holdings_smallcap.csv"
        with patch.object(smallcap_pilot, "HOLDINGS_PATH", source), \
             patch.object(smallcap_pilot.requests, "get", return_value=Response(content)):
            universe, metadata = smallcap_pilot.get_smallcap_universe()
        assert len(universe) == 500
        assert source.read_bytes() == content
        assert metadata["holdings_sha256"] == hashlib.sha256(content).hexdigest()
        assert metadata["holdings_source_status"] == "live"


if __name__ == "__main__":
    test_filters_non_equity()
    test_rejects_wrong_fund_and_layout()
    test_separate_output_keeps_main_results_untouched()
    test_live_pilot_retains_exact_holdings_source()
    print("IJR parser checks passed")
