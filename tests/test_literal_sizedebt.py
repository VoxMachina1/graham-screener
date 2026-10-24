"""Tests for literal Graham size/debt criteria (2026-10-16, Resurrected Managers).

Size: industrials need annual sales >= $100M (1974), inflation-adjusted to
$650M; utilities need total assets >= $50M (1974) -> $325M.
Debt: long-term debt must not exceed net current assets (working capital).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_screener import graham_defensive_score, GRAHAM_MIN_SALES_USD, GRAHAM_MIN_UTILITY_ASSETS_USD


def _base(**kw):
    args = dict(
        revenue_ttm=1_000_000_000.0,
        total_assets=2_000_000_000.0,
        sector="Technology",
        current_ratio=2.5,
        long_term_debt=50_000_000.0,
        current_assets=200_000_000.0,
        current_liabilities=100_000_000.0,
        annual_eps=[1.0] * 10,
        annual_dividends=[0.5] * 10,
        price=50.0,
        eps_3yr_avg=1.0,
        pb=1.2,
    )
    args.update(kw)
    return graham_defensive_score(**args)


def test_constants_documented():
    assert GRAHAM_MIN_SALES_USD == 650_000_000
    assert GRAHAM_MIN_UTILITY_ASSETS_USD == 325_000_000
    print("OK constants")


def test_size_industrial_pass():
    r = _base(revenue_ttm=1_000_000_000.0, sector="Technology")
    assert r["Size_OK"] == 1, r
    print("OK industrial size pass")


def test_size_industrial_fail():
    r = _base(revenue_ttm=100_000_000.0, sector="Technology")
    assert r["Size_OK"] == 0, r
    print("OK industrial size fail")


def test_size_utility_uses_assets():
    r = _base(sector="Utilities", total_assets=500_000_000.0, revenue_ttm=1_000_000.0)
    assert r["Size_OK"] == 1, r
    r = _base(sector="Utilities", total_assets=100_000_000.0, revenue_ttm=10_000_000_000.0)
    assert r["Size_OK"] == 0, r
    print("OK utility size uses assets")


def test_debt_ltd_within_nwc():
    r = _base(long_term_debt=50_000_000.0, current_assets=200_000_000.0,
              current_liabilities=100_000_000.0)
    assert r["Debt_OK"] == 1, r
    print("OK debt pass")


def test_debt_ltd_exceeds_nwc():
    r = _base(long_term_debt=150_000_000.0, current_assets=200_000_000.0,
              current_liabilities=100_000_000.0)
    assert r["Debt_OK"] == 0, r
    print("OK debt fail")


def test_debt_missing_or_negative_nwc():
    r = _base(long_term_debt=None)
    assert r["Debt_OK"] == 0, r
    r = _base(current_assets=50_000_000.0, current_liabilities=100_000_000.0)
    assert r["Debt_OK"] == 0, r
    print("OK debt missing/negative NWC")


def test_check_names_in_output():
    r = _base()
    assert "Debt_OK" in r and "Size_OK" in r, r.keys()
    assert "DebtEq_OK" not in r, "old proxy check name must be gone"
    assert r["DefensiveScore"] == sum(
        v for k, v in r.items()
        if k not in ("DefensiveScore", "DefensiveLabel", "EPS_Positive_Years_10")), r
    print("OK check names + score consistency")


if __name__ == "__main__":
    test_constants_documented()
    test_size_industrial_pass()
    test_size_industrial_fail()
    test_size_utility_uses_assets()
    test_debt_ltd_within_nwc()
    test_debt_ltd_exceeds_nwc()
    test_debt_missing_or_negative_nwc()
    test_check_names_in_output()
    print("ALL LITERAL SIZE/DEBT TESTS PASSED")
