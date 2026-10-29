"""Current-value screen factors must not silently use an older annual filing."""

import os
import sys
from types import SimpleNamespace

import pandas as pd

os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stock_screener as screener


def _sheet(date, assets, liabilities, shares):
    return pd.DataFrame({pd.Timestamp(date): {
        "Current Assets": assets,
        "Total Liabilities Net Minority Interest": liabilities,
        "Ordinary Shares Number": shares,
    }})


def _ticker(annual, quarterly):
    return SimpleNamespace(
        fast_info=SimpleNamespace(last_price=1.0, market_cap=50_000_000),
        info={}, income_stmt=pd.DataFrame(), dividends=pd.Series(dtype=float),
        actions=pd.DataFrame(), cashflow=pd.DataFrame(),
        balance_sheet=annual, quarterly_balance_sheet=quarterly,
        history=lambda **_: pd.DataFrame(),
    )


def test_latest_quarter_replaces_annual_point_in_time_ncav(monkeypatch):
    annual = pd.concat([
        _sheet("2025-12-31", 300_000_000, 100_000_000, 100_000_000),
        _sheet("2024-12-31", 290_000_000, 110_000_000, 110_000_000),
    ], axis=1)
    quarter = _sheet("2026-06-30", 240_000_000, 100_000_000, 80_000_000)
    monkeypatch.setattr(screener.yf, "Ticker", lambda _: _ticker(annual, quarter))

    result = screener.get_yf_price_and_history("TEST")

    assert result["current_assets"] == 240_000_000
    assert result["total_liabilities"] == 100_000_000
    assert result["ncav_shares"] == 80_000_000
    assert result["shares_now"] == 100_000_000
    assert result["shares_prev"] == 110_000_000
    assert result["balance_sheet_df"].equals(annual)
    assert screener.ncav_metrics(1.0, result["current_assets"],
                                 result["total_liabilities"], result["ncav_shares"])["NCAV"] == 140_000_000


def test_older_quarter_does_not_replace_newer_annual(monkeypatch):
    annual = _sheet("2025-12-31", 300, 100, 10)
    quarter = _sheet("2025-09-30", 240, 90, 8)
    monkeypatch.setattr(screener.yf, "Ticker", lambda _: _ticker(annual, quarter))

    result = screener.get_yf_price_and_history("TEST")

    assert result["current_assets"] == 300
    assert result["ncav_shares"] == 10


def test_missing_quarterly_shares_blocks_ncav(monkeypatch):
    annual = _sheet("2025-12-31", 300, 100, 10)
    quarter = _sheet("2026-06-30", 240, 90, 8).drop(index="Ordinary Shares Number")
    monkeypatch.setattr(screener.yf, "Ticker", lambda _: _ticker(annual, quarter))

    result = screener.get_yf_price_and_history("TEST")

    assert result["current_assets"] == 240
    assert result["ncav_shares"] is None
    assert screener.ncav_metrics(1.0, result["current_assets"],
                                 result["total_liabilities"], result["ncav_shares"])["NetNet"] is None
