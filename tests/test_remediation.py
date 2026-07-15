"""Offline regression tests for the July 2026 model-audit remediation."""

import os
import sys
from datetime import date

import pandas as pd

os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import stock_screener as screener


def _guard_frame(tickers, scores, errors, finnhub_ok=None):
    """Build a structurally valid publication-guard fixture."""
    rows = len(tickers)
    active = [score is not None and error is None for score, error in zip(scores, errors)]
    return pd.DataFrame(
        {
            "Ticker": tickers,
            "Price": [5.0] * rows,
            "OverallScore": scores,
            "Error": errors,
            "Provider_Finnhub_OK": finnhub_ok if finnhub_ok is not None else [True] * rows,
            "DCF_Intrinsic_Value": [10.0 if ok else None for ok in active],
            "DCF_Value_Low": [8.0 if ok else None for ok in active],
            "DCF_Value_High": [12.0 if ok else None for ok in active],
            "DCF_WACC_Pct": [9.0 if ok else None for ok in active],
            "DCF_Terminal_Growth_Pct": [2.0 if ok else None for ok in active],
            "DCF_Terminal_Value_Pct": [70.0 if ok else None for ok in active],
        }
    )


def test_aggregate_total_debt_is_not_double_counted():
    balance_sheet = pd.DataFrame(
        {"2025": [100.0, 80.0, 20.0]},
        index=["Total Debt", "Long Term Debt", "Current Debt"],
    )
    assert screener._extract_total_debt(balance_sheet) == 100.0


def test_total_debt_falls_back_to_long_plus_current():
    balance_sheet = pd.DataFrame(
        {"2025": [80.0, 20.0]},
        index=["Long Term Debt", "Current Debt"],
    )
    assert screener._extract_total_debt(balance_sheet) == 100.0


def test_base_fcff_adds_back_after_tax_interest():
    result = screener._compute_base_fcff(
        ocf=100.0,
        capex=-20.0,
        interest_expense=-10.0,
        tax_rate=0.20,
    )
    assert abs(result - 88.0) < 1e-9


def test_screen_wacc_responds_to_beta():
    common = dict(
        risk_free_rate_pct=4.0,
        aaa_yield_pct=5.0,
        market_cap=1000.0,
        total_debt=200.0,
        prior_total_debt=200.0,
        interest_expense=10.0,
        tax_rate=0.21,
    )
    lower = screener._estimate_screen_wacc(beta=0.8, **common)
    higher = screener._estimate_screen_wacc(beta=1.4, **common)
    assert higher["wacc"] > lower["wacc"]


def test_fcff_dcf_reverse_round_trip():
    result = screener._compute_fcff_dcf(
        base_fcff=100.0,
        initial_growth_pct=5.0,
        wacc=0.09,
        terminal_growth_pct=2.0,
        cash=20.0,
        total_debt=50.0,
        diluted_shares=10.0,
        price=80.0,
    )
    assert result is not None
    implied, converged = screener._compute_fcff_reverse_dcf(
        price=result["intrinsic_value"],
        base_fcff=100.0,
        wacc=0.09,
        terminal_growth_pct=2.0,
        cash=20.0,
        total_debt=50.0,
        diluted_shares=10.0,
    )
    assert converged is True
    assert abs(implied - 5.0) < 0.01


def test_fcff_dcf_paired_range_brackets_base():
    result = screener._compute_fcff_dcf(
        base_fcff=100.0,
        initial_growth_pct=5.0,
        wacc=0.09,
        terminal_growth_pct=2.0,
        cash=20.0,
        total_debt=50.0,
        diluted_shares=10.0,
        price=80.0,
    )
    assert result["value_low"] < result["intrinsic_value"] < result["value_high"]


def test_more_debt_reduces_equity_value_per_share():
    low_debt, _, _ = screener._fcff_value_per_share(
        100.0, 5.0, 0.09, 2.0, 20.0, 20.0, 10.0
    )
    high_debt, _, _ = screener._fcff_value_per_share(
        100.0, 5.0, 0.09, 2.0, 20.0, 80.0, 10.0
    )
    assert high_debt < low_debt


def test_wacc_guardrail_prevents_terminal_rate_compression():
    result = screener._apply_screen_wacc_guardrail(
        calculated_wacc=0.0493,
        risk_free_rate_pct=4.62,
        terminal_growth_pct=3.0,
    )
    assert result["floor_applied"] is True
    assert abs(result["wacc"] - 0.0712) < 1e-9
    assert result["wacc"] - 0.03 >= 0.04


def test_currency_mismatch_detects_unconverted_adr_financials():
    assert screener._currency_mismatch("USD", "CNY") is True
    assert screener._currency_mismatch("usd", "USD") is False
    assert screener._currency_mismatch("USD", None) is False


def test_output_guard_accepts_healthy_dataset():
    rows = 120
    frame = _guard_frame(
        [f"T{i}" for i in range(rows)],
        [50.0] * 110 + [None] * 10,
        [None] * 110 + ["data failure"] * 10,
    )
    result = screener._validate_output_dataframe(frame)
    assert result["valid_rows"] == 110


def test_output_guard_rejects_mass_error_rows():
    rows = 500
    frame = _guard_frame(
        [f"T{i}" for i in range(rows)],
        [50.0] * 50 + [None] * 450,
        [None] * 50 + ["data failure"] * 450,
    )
    try:
        screener._validate_output_dataframe(frame)
        assert False, "Expected mass-error output to be rejected"
    except ValueError as exc:
        assert "valid scored rows" in str(exc)


def test_output_guard_rejects_duplicate_tickers():
    frame = _guard_frame(["DUP"] * 120, [50.0] * 120, [None] * 120)
    try:
        screener._validate_output_dataframe(frame)
        assert False, "Expected duplicate output to be rejected"
    except ValueError as exc:
        assert "duplicate ticker" in str(exc)


def test_output_guard_rejects_blank_tickers():
    frame = _guard_frame(
        [None] + [f"T{i}" for i in range(119)],
        [50.0] * 120,
        [None] * 120,
    )
    try:
        screener._validate_output_dataframe(frame)
        assert False, "Expected blank tickers to be rejected"
    except ValueError as exc:
        assert "blank ticker" in str(exc)


def test_output_guard_rejects_provider_wide_degradation():
    frame = _guard_frame(
        [f"T{i}" for i in range(120)],
        [50.0] * 120,
        [None] * 120,
        finnhub_ok=[False] * 120,
    )
    try:
        screener._validate_output_dataframe(frame)
        assert False, "Expected a provider-wide Finnhub outage to be rejected"
    except ValueError as exc:
        assert "valid Finnhub data" in str(exc)


def test_output_guard_rejects_misordered_dcf_range():
    frame = _guard_frame(
        [f"T{i}" for i in range(120)],
        [50.0] * 120,
        [None] * 120,
    )
    frame.loc[0, "DCF_Value_Low"] = 11.0
    try:
        screener._validate_output_dataframe(frame)
        assert False, "Expected a misordered DCF range to be rejected"
    except ValueError as exc:
        assert "misordered ranges" in str(exc)


def test_nasdaq_fetch_uses_component_list_page():
    original = screener._wiki_tables
    seen = []

    def fake_tables(url):
        seen.append(url)
        return [pd.DataFrame({"Ticker": ["AAPL", "BRK.B"]})]

    try:
        screener._wiki_tables = fake_tables
        members = screener.fetch_nasdaq100()
    finally:
        screener._wiki_tables = original

    assert seen == ["https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies"]
    assert members == {"AAPL", "BRK-B"}


def test_negative_eps_is_retained_as_a_warning_not_a_fetch_error():
    original = screener.get_combined_data
    synthetic = {
        "price": 10.0,
        "market_cap_b": 5.0,
        "annual_eps": [-3.0, -2.0, -1.0],
        "annual_dividends": [],
        "ttm_eps": -1.0,
        "ttm_dps": 0.0,
        "growth_pct": 5.0,
        "current_ratio": 1.5,
        "debt_equity": 0.5,
        "book_value_ps": 4.0,
        "pb_ratio": 2.5,
        "fcf_per_share": -0.5,
        "sector": "Industrials",
        "dist_52w_high": None,
        "dist_52w_low": None,
        "dist_5y_low": None,
        "weeks_since_52w_low": None,
        "weeks_since_5y_low": None,
        "short_history": False,
        "fcf_yield": -2.0,
        "ev_ebit": None,
        "earnings_yield": None,
        "roic": -5.0,
        "shareholder_yield": 0.0,
        "shareholder_yield_partial": True,
        "income_stmt_df": None,
        "balance_sheet_df": None,
        "cashflow_df": None,
        "ocf": -100.0,
        "capex": -20.0,
        "interest_expense": -5.0,
        "tax_rate": 0.21,
        "total_debt": 100.0,
        "prior_total_debt": 100.0,
        "cash": 20.0,
        "shares_now": 500.0,
        "diluted_shares": 500.0,
        "beta": 1.0,
    }

    try:
        screener.get_combined_data = lambda _ticker: synthetic
        row = screener.process_ticker("LOSS", aaa_yield=5.0, risk_free_rate=4.0)
    finally:
        screener.get_combined_data = original

    assert row["Error"] is None
    assert row["EPS_TTM"] == -1.0
    assert row["Lynch_Lynch_Discount_Pct"] == screener.WORST_DISCOUNT
    assert row["Graham_Graham_Discount_Pct"] == screener.WORST_DISCOUNT
    assert "Non-positive EPS" in row["Valuation_Input_Warning"]
    assert row["OverallScore"] is not None


def test_trap_reasons_are_explicit_and_warning_only():
    reasons = screener._trap_reasons(
        debt_equity=screener.TRAP_MAX_DE + 1.0,
        current_ratio=screener.TRAP_MIN_CR - 0.1,
        eps_stability=0,
        fcf_per_share=-1.0,
    )
    assert reasons == [
        "High leverage",
        "Weak liquidity",
        "Unstable earnings",
        "Negative FCF",
    ]


def test_first_weekday_snapshot_logic_handles_weekends():
    assert screener._is_first_weekday_of_month(date(2026, 7, 1)) is True
    assert screener._is_first_weekday_of_month(date(2026, 7, 2)) is False
    assert screener._is_first_weekday_of_month(date(2026, 8, 1)) is False
    assert screener._is_first_weekday_of_month(date(2026, 8, 3)) is True


def test_reverse_fcff_is_pure_without_api_credentials():
    original = screener.FINNHUB_API_KEY
    try:
        screener.FINNHUB_API_KEY = None
        implied, converged = screener._compute_fcff_reverse_dcf(
            price=80.0,
            base_fcff=100.0,
            wacc=0.09,
            terminal_growth_pct=2.0,
            cash=20.0,
            total_debt=50.0,
            diluted_shares=10.0,
        )
    finally:
        screener.FINNHUB_API_KEY = original

    assert implied is not None
    assert converged is True


def test_finnhub_fetch_rejects_missing_key_before_network():
    original = screener.FINNHUB_API_KEY
    try:
        screener.FINNHUB_API_KEY = None
        try:
            screener.get_finnhub_metrics("TEST")
            assert False, "Expected missing Finnhub key to fail explicitly"
        except RuntimeError as exc:
            assert "FINNHUB_API_KEY" in str(exc)
    finally:
        screener.FINNHUB_API_KEY = original


def test_finnhub_auth_failure_stops_the_run():
    original_key = screener.FINNHUB_API_KEY
    original_get = screener.requests.get

    class UnauthorizedResponse:
        status_code = 401

    try:
        screener.FINNHUB_API_KEY = "test"
        screener.requests.get = lambda *args, **kwargs: UnauthorizedResponse()
        try:
            screener.get_finnhub_metrics("TEST")
            assert False, "Expected an invalid Finnhub credential to stop the run"
        except RuntimeError as exc:
            assert "authentication failed" in str(exc)
    finally:
        screener.FINNHUB_API_KEY = original_key
        screener.requests.get = original_get


def test_finnhub_preflight_rejects_empty_metric_bundle():
    original = screener.get_finnhub_metrics
    try:
        screener.get_finnhub_metrics = lambda _ticker: {}
        try:
            screener._validate_finnhub_access()
            assert False, "Expected an empty Finnhub preflight to stop the run"
        except RuntimeError as exc:
            assert "preflight returned no metrics" in str(exc)
    finally:
        screener.get_finnhub_metrics = original


def run_all():
    tests = [
        test_aggregate_total_debt_is_not_double_counted,
        test_total_debt_falls_back_to_long_plus_current,
        test_base_fcff_adds_back_after_tax_interest,
        test_screen_wacc_responds_to_beta,
        test_fcff_dcf_reverse_round_trip,
        test_fcff_dcf_paired_range_brackets_base,
        test_more_debt_reduces_equity_value_per_share,
        test_wacc_guardrail_prevents_terminal_rate_compression,
        test_currency_mismatch_detects_unconverted_adr_financials,
        test_output_guard_accepts_healthy_dataset,
        test_output_guard_rejects_mass_error_rows,
        test_output_guard_rejects_duplicate_tickers,
        test_output_guard_rejects_blank_tickers,
        test_output_guard_rejects_provider_wide_degradation,
        test_output_guard_rejects_misordered_dcf_range,
        test_nasdaq_fetch_uses_component_list_page,
        test_negative_eps_is_retained_as_a_warning_not_a_fetch_error,
        test_trap_reasons_are_explicit_and_warning_only,
        test_first_weekday_snapshot_logic_handles_weekends,
        test_reverse_fcff_is_pure_without_api_credentials,
        test_finnhub_fetch_rejects_missing_key_before_network,
        test_finnhub_auth_failure_stops_the_run,
        test_finnhub_preflight_rejects_empty_metric_bundle,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"  FAIL  {test.__name__}: {exc}")
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
