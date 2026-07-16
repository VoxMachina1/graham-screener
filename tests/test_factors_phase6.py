"""
Phase 6 factor helper tests
============================
Covers the new pure helpers added in Phase 6 Plan 01:
  _compute_fcf_yield, _compute_ev_ebit, _compute_roic,
  _compute_shareholder_yield, _compute_price_signals, _yf_row

DESIGN RULES (match test_growth_trap_fixes.py):
  - Vanilla assert only — no pytest dependency.
  - Dummy env vars retained for compatibility with network-entry-point guards.
  - No network calls, no yf.Ticker — all inputs are plain dicts/lists/values.

HOW TO RUN:
    python tests/test_factors_phase6.py
"""

import os
import sys

os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd

from stock_screener import (
    _compute_fcf_yield,
    _compute_ev_ebit,
    _compute_roic,
    _compute_shareholder_yield,
    _compute_price_signals,
    _yf_row,
)


# ── _compute_fcf_yield ───────────────────────────────────────────────────────

def test_fcf_yield_positive():
    # ocf=100, capex=-30 (negative in yfinance) → FCF = 100 + (-30) = 70
    # fcf_yield = 70 / 1000 * 100 = 7.0
    result = _compute_fcf_yield(ocf=100, capex=-30, market_cap=1000)
    assert abs(result - 7.0) < 1e-9, f"expected 7.0, got {result}"


def test_fcf_yield_negative_fcf():
    # ocf=20, capex=-80 → FCF = 20 + (-80) = -60 → yield = -6.0% (negative, not clamped)
    result = _compute_fcf_yield(ocf=20, capex=-80, market_cap=1000)
    assert result == -6.0, f"expected -6.0, got {result}"


def test_fcf_yield_no_capex_ocf_proxy():
    # capex=None → FCF = ocf; yield = 50/1000*100 = 5.0
    result = _compute_fcf_yield(ocf=50, capex=None, market_cap=1000)
    assert result == 5.0, f"expected 5.0, got {result}"


def test_fcf_yield_none_when_ocf_none():
    result = _compute_fcf_yield(ocf=None, capex=-30, market_cap=1000)
    assert result is None, f"expected None, got {result}"


def test_fcf_yield_none_when_market_cap_none():
    result = _compute_fcf_yield(ocf=100, capex=-30, market_cap=None)
    assert result is None, f"expected None, got {result}"


def test_fcf_yield_none_when_market_cap_zero():
    result = _compute_fcf_yield(ocf=100, capex=-30, market_cap=0)
    assert result is None, f"expected None, got {result}"


# ── _compute_ev_ebit ─────────────────────────────────────────────────────────

def test_ev_ebit_happy_path():
    # market_cap=1000, total_debt=200, cash=100, ebit=50
    # ev = 1000 + 200 - 100 = 1100
    # ev_ebit = 1100/50 = 22.0; earnings_yield = 50/1100*100 ≈ 4.545...
    ev_ebit, earnings_yield = _compute_ev_ebit(
        ebit=50, total_debt=200, cash=100, market_cap=1000
    )
    assert abs(ev_ebit - 22.0) < 1e-9, f"expected ev_ebit=22.0, got {ev_ebit}"
    assert abs(earnings_yield - (50 / 1100 * 100)) < 1e-9, f"unexpected earnings_yield {earnings_yield}"


def test_ev_ebit_none_when_ebit_zero():
    ev_ebit, earnings_yield = _compute_ev_ebit(
        ebit=0, total_debt=200, cash=100, market_cap=1000
    )
    assert ev_ebit is None, f"expected None, got {ev_ebit}"
    assert earnings_yield is None, f"expected None, got {earnings_yield}"


def test_ev_ebit_none_when_ebit_negative():
    ev_ebit, earnings_yield = _compute_ev_ebit(
        ebit=-50, total_debt=200, cash=100, market_cap=1000
    )
    assert ev_ebit is None
    assert earnings_yield is None


def test_ev_ebit_none_when_ev_le_zero():
    # cash > market_cap + total_debt → ev <= 0
    ev_ebit, earnings_yield = _compute_ev_ebit(
        ebit=50, total_debt=0, cash=1500, market_cap=1000
    )
    assert ev_ebit is None
    assert earnings_yield is None


def test_ev_ebit_none_when_market_cap_none():
    ev_ebit, earnings_yield = _compute_ev_ebit(
        ebit=50, total_debt=200, cash=100, market_cap=None
    )
    assert ev_ebit is None
    assert earnings_yield is None


def test_ev_ebit_none_debt_and_cash_default_to_zero():
    # total_debt=None, cash=None → both default to 0; ev = market_cap
    ev_ebit, earnings_yield = _compute_ev_ebit(
        ebit=100, total_debt=None, cash=None, market_cap=500
    )
    assert abs(ev_ebit - 5.0) < 1e-9, f"expected 5.0, got {ev_ebit}"
    assert abs(earnings_yield - 20.0) < 1e-9, f"expected 20.0, got {earnings_yield}"


# ── _compute_roic ────────────────────────────────────────────────────────────

def test_roic_happy_path():
    # ebit=100, total_debt=200, equity=300, cash=50
    # invested = 200 + 300 - 50 = 450
    # roic = 100*(1-0.21)/450*100 = 79/450*100 ≈ 17.555...
    result = _compute_roic(ebit=100, total_debt=200, equity=300, cash=50)
    expected = 100 * 0.79 / 450 * 100
    assert abs(result - expected) < 1e-9, f"expected {expected}, got {result}"


def test_roic_invested_le_zero_returns_none():
    # total_debt=10, equity=20, cash=100 → invested = 10+20-100 = -70 ≤ 0 → None
    result = _compute_roic(ebit=50, total_debt=10, equity=20, cash=100)
    assert result is None, f"expected None, got {result}"


def test_roic_negative_ebit_yields_negative():
    # ebit=-50 → nopat=-39.5; invested=450 → roic negative (not clamped)
    result = _compute_roic(ebit=-50, total_debt=200, equity=300, cash=50)
    assert result is not None and result < 0, f"expected negative, got {result}"


def test_roic_none_when_ebit_none():
    result = _compute_roic(ebit=None, total_debt=200, equity=300, cash=50)
    assert result is None


def test_roic_none_when_equity_none():
    result = _compute_roic(ebit=100, total_debt=200, equity=None, cash=50)
    assert result is None


def test_roic_cash_defaults_to_zero_when_none():
    # cash=None → 0; invested = total_debt + equity = 500
    result = _compute_roic(ebit=100, total_debt=200, equity=300, cash=None)
    expected = 100 * 0.79 / 500 * 100
    assert abs(result - expected) < 1e-9, f"expected {expected}, got {result}"


# ── _compute_shareholder_yield ───────────────────────────────────────────────

def test_shareholder_yield_div_only_partial_true():
    # shares_now=None → net_buyback=None → partial=True, total=div_yield
    total, partial = _compute_shareholder_yield(div_yield=2.0, shares_now=None, shares_prev=1000)
    assert total == 2.0, f"expected 2.0, got {total}"
    assert partial is True


def test_shareholder_yield_div_plus_buyback():
    # shares_prev=1000, shares_now=900 → net_buyback = (1000-900)/1000*100 = 10.0
    # total = 2.0 + 10.0 = 12.0; partial=False
    total, partial = _compute_shareholder_yield(div_yield=2.0, shares_now=900, shares_prev=1000)
    assert abs(total - 12.0) < 1e-9, f"expected 12.0, got {total}"
    assert partial is False


def test_shareholder_yield_dilution_negative_buyback():
    # shares_now=1100, shares_prev=1000 → net_buyback = (1000-1100)/1000*100 = -10.0
    # total = 1.0 + (-10.0) = -9.0; partial=False
    total, partial = _compute_shareholder_yield(div_yield=1.0, shares_now=1100, shares_prev=1000)
    assert abs(total - (-9.0)) < 1e-9, f"expected -9.0, got {total}"
    assert partial is False


def test_shareholder_yield_both_none_shares():
    # shares_now=None AND shares_prev=None → partial=True, total=div_yield
    total, partial = _compute_shareholder_yield(div_yield=3.0, shares_now=None, shares_prev=None)
    assert total == 3.0
    assert partial is True


def test_shareholder_yield_zero_div_partial_true():
    # div_yield=0, no buyback data → total=0.0, partial=True
    total, partial = _compute_shareholder_yield(div_yield=0.0, shares_now=None, shares_prev=None)
    assert total == 0.0
    assert partial is True


# ── _compute_price_signals ───────────────────────────────────────────────────

def _make_closes(n, base=100.0):
    """Make a synthetic pandas Series of length n with a known minimum pattern."""
    import numpy as np
    vals = [base + float(i) for i in range(n)]
    return pd.Series(vals, dtype=float)


def test_price_signals_full_52_bars():
    # n=52; price=200; low at index 0 (val=100), high at index 51 (val=151)
    closes = _make_closes(52, base=100.0)  # 100..151
    price = 200.0
    result = _compute_price_signals(closes, price)

    assert result["short_history"] is False
    # high_52w = 151; dist_52w_high = max(0, (151-200)/151*100) = 0 (clamped)
    assert result["dist_52w_high"] == 0.0, f"expected 0.0, got {result['dist_52w_high']}"
    # low_52w = 100; dist_52w_low = (200-100)/100*100 = 100.0
    assert abs(result["dist_52w_low"] - 100.0) < 1e-6, f"got {result['dist_52w_low']}"
    # low_5y = 100 same as low_52w
    assert abs(result["dist_5y_low"] - 100.0) < 1e-6
    # min is at index 0 → weeks_since = 52-1-0 = 51
    assert result["weeks_since_52w_low"] == 51
    assert result["weeks_since_5y_low"] == 51


def test_price_signals_short_history_8_to_51():
    # n=20; all signals computed but short_history=True
    closes = _make_closes(20, base=50.0)  # 50..69
    price = 60.0
    result = _compute_price_signals(closes, price)

    assert result["short_history"] is True
    # high of last min(20,52)=20 bars = 69; dist_52w_high = max(0,(69-60)/69*100)
    expected_dist_high = max(0.0, (69.0 - 60.0) / 69.0 * 100)
    assert abs(result["dist_52w_high"] - expected_dist_high) < 1e-6
    # All five signals should be non-None
    assert result["dist_52w_low"] is not None
    assert result["dist_5y_low"] is not None
    assert result["weeks_since_52w_low"] is not None
    assert result["weeks_since_5y_low"] is not None


def test_price_signals_too_few_bars_all_none():
    # n=5 < 8 → all five signals None, short_history False
    closes = _make_closes(7, base=100.0)
    result = _compute_price_signals(closes, 105.0)

    assert result["dist_52w_high"] is None
    assert result["dist_52w_low"] is None
    assert result["dist_5y_low"] is None
    assert result["weeks_since_52w_low"] is None
    assert result["weeks_since_5y_low"] is None
    assert result["short_history"] is False


def test_price_signals_empty_series_all_none():
    closes = pd.Series([], dtype=float)
    result = _compute_price_signals(closes, 100.0)

    assert result["dist_52w_high"] is None
    assert result["short_history"] is False


def test_price_signals_at_the_low():
    # price == low_52w → dist_52w_low = 0.0; if the low is the last bar → weeks_since=0
    # Construct: monotonically decreasing so min is at index -1 (last bar)
    vals = [float(100 - i) for i in range(52)]  # 100, 99, ..., 49
    closes = pd.Series(vals, dtype=float)
    price = 49.0  # == last bar value (the low)
    result = _compute_price_signals(closes, price)

    assert result["short_history"] is False
    assert result["dist_52w_low"] == 0.0, f"expected 0.0, got {result['dist_52w_low']}"
    assert result["weeks_since_52w_low"] == 0, f"expected 0, got {result['weeks_since_52w_low']}"


# ── _yf_row ──────────────────────────────────────────────────────────────────

def test_yf_row_first_matching_label():
    # Build a small DataFrame mimicking yfinance cashflow format
    df = pd.DataFrame(
        {"2024": [100.0, 200.0], "2023": [90.0, 180.0]},
        index=["Operating Cash Flow", "Capital Expenditure"],
    )
    # columns[0] = "2024" (newest first)
    result = _yf_row(df, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    assert result == 100.0, f"expected 100.0, got {result}"


def test_yf_row_second_label_when_first_absent():
    df = pd.DataFrame(
        {"2024": [100.0]},
        index=["Total Cash From Operating Activities"],
    )
    result = _yf_row(df, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    assert result == 100.0


def test_yf_row_none_when_no_label_matches():
    df = pd.DataFrame({"2024": [100.0]}, index=["Some Other Row"])
    result = _yf_row(df, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    assert result is None


def test_yf_row_none_on_empty_df():
    result = _yf_row(pd.DataFrame(), ["Operating Cash Flow"])
    assert result is None


def test_yf_row_none_on_none_df():
    result = _yf_row(None, ["Operating Cash Flow"])
    assert result is None


# ── test runner ──────────────────────────────────────────────────────────────

def run_all():
    tests = [
        # FCF yield
        test_fcf_yield_positive,
        test_fcf_yield_negative_fcf,
        test_fcf_yield_no_capex_ocf_proxy,
        test_fcf_yield_none_when_ocf_none,
        test_fcf_yield_none_when_market_cap_none,
        test_fcf_yield_none_when_market_cap_zero,
        # EV/EBIT
        test_ev_ebit_happy_path,
        test_ev_ebit_none_when_ebit_zero,
        test_ev_ebit_none_when_ebit_negative,
        test_ev_ebit_none_when_ev_le_zero,
        test_ev_ebit_none_when_market_cap_none,
        test_ev_ebit_none_debt_and_cash_default_to_zero,
        # ROIC
        test_roic_happy_path,
        test_roic_invested_le_zero_returns_none,
        test_roic_negative_ebit_yields_negative,
        test_roic_none_when_ebit_none,
        test_roic_none_when_equity_none,
        test_roic_cash_defaults_to_zero_when_none,
        # Shareholder yield
        test_shareholder_yield_div_only_partial_true,
        test_shareholder_yield_div_plus_buyback,
        test_shareholder_yield_dilution_negative_buyback,
        test_shareholder_yield_both_none_shares,
        test_shareholder_yield_zero_div_partial_true,
        # Price signals
        test_price_signals_full_52_bars,
        test_price_signals_short_history_8_to_51,
        test_price_signals_too_few_bars_all_none,
        test_price_signals_empty_series_all_none,
        test_price_signals_at_the_low,
        # _yf_row
        test_yf_row_first_matching_label,
        test_yf_row_second_label_when_first_absent,
        test_yf_row_none_when_no_label_matches,
        test_yf_row_none_on_empty_df,
        test_yf_row_none_on_none_df,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
