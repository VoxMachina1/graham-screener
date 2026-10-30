"""Offline checks for the isolated IWM source and screener universe."""

import hashlib
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import iwm_pilot


def _csv(extra=""):
    return ('iShares Russell 2000 ETF\n'
            'Fund Holdings as of,"Oct 27, 2026"\n\n'
            'Ticker,Name,Sector,Asset Class,Exchange,Currency\n'
            + "\n".join(f"T{i},Company {i},Industrials,Equity,NASDAQ,USD"
                        for i in range(1800)) + "\n" + extra)


def test_parser_keeps_listed_usd_equities_only():
    tickers, as_of, omitted = iwm_pilot.parse_iwm_holdings(_csv(
        '-,Private,Industrials,Equity,NASDAQ,USD\n'
        'OTC,Private,Industrials,Equity,NO MARKET (E.G. UNLISTED),USD\n'
        'T0,Duplicate,Industrials,Equity,NYSE,USD\n'
        'USD,Cash,,Cash,NASDAQ,USD\n'))
    assert len(tickers) == 1800 and as_of == "2026-10-27"
    assert omitted == {"unlisted_or_foreign": 1, "missing_ticker": 1,
                       "duplicate_ticker": 1}


def test_parser_rejects_wrong_source_and_retains_exact_csv():
    try:
        iwm_pilot.parse_iwm_holdings(_csv().replace("iShares Russell 2000 ETF", "Other Fund"))
    except ValueError:
        pass
    else:
        raise AssertionError("Wrong fund name was accepted")

    content = _csv().encode("utf-8")

    class Response:
        def __init__(self, data):
            self.text = data.decode("utf-8")
            self.content = data

        def raise_for_status(self):
            pass

    with TemporaryDirectory() as folder:
        output = Path(folder) / "iwm"
        with patch.object(iwm_pilot, "OUTPUT", output), \
             patch.object(iwm_pilot.requests, "get", return_value=Response(content)):
            universe, metadata = iwm_pilot.get_iwm_universe()
        assert len(universe) == 1800
        assert (output / "holdings.csv").read_bytes() == content
        assert metadata["holdings_sha256"] == hashlib.sha256(content).hexdigest()


if __name__ == "__main__":
    test_parser_keeps_listed_usd_equities_only()
    test_parser_rejects_wrong_source_and_retains_exact_csv()
    print("IWM pilot parser checks passed")
