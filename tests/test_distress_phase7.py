"""
Phase 7 distress signal helper tests
======================================
Covers the new pure helpers added in Phase 7 Plan 01:
  _yf_row_prev, _dcf_wacc, _compute_piotroski, _compute_altman_z

DESIGN RULES (match test_factors_phase6.py):
  - Vanilla assert only — no pytest dependency.
  - Env vars set BEFORE importing stock_screener (module reads them at import).
  - No network calls, no yf.Ticker — all inputs are plain DataFrames with synthetic values.

HOW TO RUN:
    python tests/test_distress_phase7.py
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
    _yf_row_prev,
    _dcf_wacc,
    _compute_piotroski,
    _compute_altman_z,
)


# ── Fixture helpers ──────────────────────────────────────────────────────────

def _make_df(data: dict, cols=("2024", "2023")) -> pd.DataFrame:
    """
    Build a small DataFrame with two columns (newest-first) from a
    {label: (curr_val, prev_val)} dict.
    """
    rows = {label: list(vals) for label, vals in data.items()}
    df = pd.DataFrame.from_dict(rows, orient="index", columns=list(cols))
    return df


def _make_income_curr(
    net_income=1_000,
    gross_profit=4_000,
    revenue=10_000,
    ebit=1_500,
) -> pd.DataFrame:
    return _make_df({
        "Net Income":     (net_income,    net_income * 0.8),
        "Gross Profit":   (gross_profit,  gross_profit * 0.9),
        "Total Revenue":  (revenue,       revenue * 0.9),
        "EBIT":           (ebit,          ebit * 0.9),
    })


def _make_balance_curr(
    total_assets=20_000,
    current_assets=8_000,
    current_liabilities=3_000,
    long_term_debt=2_000,
    equity=10_000,
    retained_earnings=5_000,
    total_liabilities=7_000,
) -> pd.DataFrame:
    return _make_df({
        "Total Assets":                          (total_assets,        total_assets * 0.9),
        "Total Current Assets":                  (current_assets,      current_assets * 0.9),
        "Total Current Liabilities":             (current_liabilities, current_liabilities * 1.1),
        "Long Term Debt":                        (long_term_debt,      long_term_debt * 1.1),
        "Stockholders Equity":                   (equity,              equity * 0.9),
        "Retained Earnings":                     (retained_earnings,   retained_earnings * 0.8),
        "Total Liabilities Net Minority Interest": (total_liabilities,  total_liabilities * 1.1),
    })


def _make_cashflow_curr(ocf=2_000) -> pd.DataFrame:
    return _make_df({
        "Operating Cash Flow": (ocf, ocf * 0.9),
    })


# ── _yf_row_prev ─────────────────────────────────────────────────────────────

def test_yf_row_prev_returns_prior_year_value():
    df = pd.DataFrame(
        {"2024": [100.0, 200.0], "2023": [90.0, 180.0]},
        index=["Operating Cash Flow", "Capital Expenditure"],
    )
    result = _yf_row_prev(df, ["Operating Cash Flow"])
    assert result == 90.0, f"expected 90.0, got {result}"


def test_yf_row_prev_second_label_when_first_absent():
    df = pd.DataFrame(
        {"2024": [100.0], "2023": [85.0]},
        index=["Total Cash From Operating Activities"],
    )
    result = _yf_row_prev(df, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    assert result == 85.0, f"expected 85.0, got {result}"


def test_yf_row_prev_none_when_only_one_column():
    df = pd.DataFrame({"2024": [100.0]}, index=["Operating Cash Flow"])
    result = _yf_row_prev(df, ["Operating Cash Flow"])
    assert result is None, f"expected None (1 column), got {result}"


def test_yf_row_prev_none_on_none_df():
    result = _yf_row_prev(None, ["Operating Cash Flow"])
    assert result is None, "expected None for None df"


def test_yf_row_prev_none_on_empty_df():
    result = _yf_row_prev(pd.DataFrame(), ["Operating Cash Flow"])
    assert result is None, "expected None for empty df"


def test_yf_row_prev_none_when_no_label_matches():
    df = pd.DataFrame(
        {"2024": [100.0], "2023": [90.0]},
        index=["Something Else"],
    )
    result = _yf_row_prev(df, ["Operating Cash Flow"])
    assert result is None, "expected None when no label matches"


# ── _dcf_wacc ────────────────────────────────────────────────────────────────

def test_dcf_wacc_standard():
    # aaa_yield=5.0, DCF_ERP=5.5 → wacc = (5.0 + 5.5) / 100 = 0.105
    result = _dcf_wacc(5.0)
    assert abs(result - 0.105) < 1e-9, f"expected 0.105, got {result}"


def test_dcf_wacc_zero_yield():
    # aaa_yield=0.0 → wacc = 5.5 / 100 = 0.055
    result = _dcf_wacc(0.0)
    assert abs(result - 0.055) < 1e-9, f"expected 0.055, got {result}"


def test_dcf_wacc_higher_yield():
    # aaa_yield=4.5 → wacc = 10.0 / 100 = 0.10
    result = _dcf_wacc(4.5)
    assert abs(result - 0.10) < 1e-9, f"expected 0.10, got {result}"


# ── _compute_piotroski ───────────────────────────────────────────────────────

def test_piotroski_all_pass_returns_9():
    """All 9 criteria pass → F-Score = 9."""
    # Construct two-year statements where every criterion is clearly positive.
    # curr: net_income=1000, ocf=2000, gross_profit=4000, revenue=10000
    #   total_assets=20000, current_assets=8000, current_liabilities=3000
    #   long_term_debt=2000, equity=10000, shares (via SHARES_LABELS in balance sheet)
    # prev: slightly worse on each comparison criterion to ensure improvement.

    inc_curr = _make_df({
        "Net Income":     (1_000, 800),
        "Gross Profit":   (4_000, 3_200),
        "Total Revenue":  (10_000, 9_000),
        "EBIT":           (1_500, 1_200),
    })
    inc_prev = _make_df({
        "Net Income":     (800, 600),
        "Gross Profit":   (3_200, 2_800),
        "Total Revenue":  (9_000, 8_000),
        "EBIT":           (1_200, 1_000),
    })
    bs_curr = _make_df({
        "Total Assets":                           (20_000, 18_000),
        "Total Current Assets":                   (8_000,  7_000),
        "Total Current Liabilities":              (3_000,  3_500),
        "Long Term Debt":                         (2_000,  2_500),
        "Stockholders Equity":                    (10_000, 9_000),
        "Retained Earnings":                      (5_000,  4_000),
        "Total Liabilities Net Minority Interest": (7_000, 7_500),
        # Shares: fewer now than before (no dilution: shares_curr <= shares_prev)
        "Ordinary Shares Number":                 (900,    1_000),
    })
    bs_prev = _make_df({
        "Total Assets":                           (18_000, 16_000),
        "Total Current Assets":                   (7_000,  6_000),
        "Total Current Liabilities":              (3_500,  4_000),
        "Long Term Debt":                         (2_500,  3_000),
        "Stockholders Equity":                    (9_000,  8_000),
        "Retained Earnings":                      (4_000,  3_000),
        "Total Liabilities Net Minority Interest": (7_500, 8_000),
        "Ordinary Shares Number":                 (1_000,  1_100),
    })
    cf_curr = _make_df({
        "Operating Cash Flow": (2_000, 1_800),
    })
    cf_prev = _make_df({
        "Operating Cash Flow": (1_800, 1_600),
    })

    result = _compute_piotroski(inc_curr, inc_prev, bs_curr, bs_prev, cf_curr, cf_prev)
    assert result == 9, f"expected 9 (all pass), got {result}"


def test_piotroski_all_fail_returns_0():
    """All 9 criteria fail → F-Score = 0."""
    # curr: negative net_income, negative ocf; all ratios worse than prev
    inc_curr = _make_df({
        "Net Income":     (-100, -50),
        "Gross Profit":   (1_000, 1_200),   # gross margin worsens: gp/rev curr < prev
        "Total Revenue":  (10_000, 9_000),
        "EBIT":           (-50, 50),
    })
    inc_prev = _make_df({
        "Net Income":     (-50, -30),
        "Gross Profit":   (1_200, 1_100),
        "Total Revenue":  (9_000, 8_500),
        "EBIT":           (50, 80),
    })
    bs_curr = _make_df({
        "Total Assets":                           (20_000, 19_000),
        "Total Current Assets":                   (3_000,  3_200),
        "Total Current Liabilities":              (4_000,  3_500),  # CR worsens
        "Long Term Debt":                         (3_000,  2_500),  # leverage increases
        "Stockholders Equity":                    (8_000,  9_000),
        "Retained Earnings":                      (2_000,  3_000),
        "Total Liabilities Net Minority Interest": (10_000, 9_000),
        "Ordinary Shares Number":                 (1_200,  1_000),  # dilution
    })
    bs_prev = _make_df({
        "Total Assets":                           (19_000, 18_000),
        "Total Current Assets":                   (3_200,  3_000),
        "Total Current Liabilities":              (3_500,  3_200),
        "Long Term Debt":                         (2_500,  2_000),
        "Stockholders Equity":                    (9_000,  8_500),
        "Retained Earnings":                      (3_000,  2_500),
        "Total Liabilities Net Minority Interest": (9_000, 8_500),
        "Ordinary Shares Number":                 (1_000,  900),
    })
    cf_curr = _make_df({
        "Operating Cash Flow": (-200, 100),   # F2: OCF < 0
    })
    cf_prev = _make_df({
        "Operating Cash Flow": (100, 90),
    })

    result = _compute_piotroski(inc_curr, inc_prev, bs_curr, bs_prev, cf_curr, cf_prev)
    assert result == 0, f"expected 0 (all fail), got {result}"


def test_piotroski_none_when_no_statements():
    result = _compute_piotroski(None, None, None, None, None, None)
    assert result is None, f"expected None, got {result}"


def test_piotroski_skips_comparison_when_prev_absent():
    """
    When prior-year DataFrames are None, comparison criteria (F3, F5, F6, F7, F8, F9)
    are skipped (not failed). Single-year criteria (F1, F2, F4) still contribute.
    Result should be between 1 and 3 (only F1, F2, F4 can score).
    """
    inc_curr = _make_df({
        "Net Income":     (1_000, 800),
        "Gross Profit":   (4_000, 3_200),
        "Total Revenue":  (10_000, 9_000),
    })
    bs_curr = _make_df({
        "Total Assets":                           (20_000, 18_000),
        "Total Current Assets":                   (8_000,  7_000),
        "Total Current Liabilities":              (3_000,  3_500),
        "Long Term Debt":                         (2_000,  2_500),
        "Stockholders Equity":                    (10_000, 9_000),
        "Retained Earnings":                      (5_000,  4_000),
        "Total Liabilities Net Minority Interest": (7_000, 7_500),
        "Ordinary Shares Number":                 (900,    1_000),
    })
    cf_curr = _make_df({
        "Operating Cash Flow": (2_000, 1_800),
    })

    result = _compute_piotroski(inc_curr, None, bs_curr, None, cf_curr, None)
    assert result is not None, "expected an int when curr statements present"
    assert 0 <= result <= 3, f"expected 0–3 (only F1/F2/F4 count), got {result}"


# ── _compute_altman_z ────────────────────────────────────────────────────────

def test_altman_z_known_fixture():
    """
    Hand-computed Z'' for a controlled fixture:
      total_assets=20000, current_assets=8000, current_liabilities=3000
      retained_earnings=5000, ebit=1500, equity=10000, total_liabilities=7000

    WC  = 8000 - 3000 = 5000
    X1  = 5000 / 20000 = 0.25
    X2  = 5000 / 20000 = 0.25
    X3  = 1500 / 20000 = 0.075
    X4  = 10000 / 7000 ≈ 1.42857

    Z'' = 6.56*0.25 + 3.26*0.25 + 6.72*0.075 + 1.05*1.42857
        = 1.64 + 0.815 + 0.504 + 1.5 (approx)
    """
    bs = _make_df({
        "Total Assets":                           (20_000, 18_000),
        "Total Current Assets":                   (8_000,  7_000),
        "Total Current Liabilities":              (3_000,  3_500),
        "Stockholders Equity":                    (10_000, 9_000),
        "Retained Earnings":                      (5_000,  4_000),
        "Total Liabilities Net Minority Interest": (7_000, 7_500),
    })
    inc = _make_df({
        "EBIT": (1_500, 1_200),
    })

    X1 = (8_000 - 3_000) / 20_000
    X2 = 5_000 / 20_000
    X3 = 1_500 / 20_000
    X4 = 10_000 / 7_000
    expected = 6.56 * X1 + 3.26 * X2 + 6.72 * X3 + 1.05 * X4

    result = _compute_altman_z(bs, inc)
    assert result is not None, "expected a float, got None"
    assert abs(result - expected) < 1e-6, f"expected {expected:.6f}, got {result:.6f}"


def test_altman_z_none_when_total_assets_zero():
    bs = _make_df({
        "Total Assets":                           (0, 0),
        "Total Current Assets":                   (8_000, 7_000),
        "Total Current Liabilities":              (3_000, 3_500),
        "Stockholders Equity":                    (10_000, 9_000),
        "Retained Earnings":                      (5_000, 4_000),
        "Total Liabilities Net Minority Interest": (7_000, 7_500),
    })
    inc = _make_df({"EBIT": (1_500, 1_200)})
    result = _compute_altman_z(bs, inc)
    assert result is None, f"expected None when total_assets=0, got {result}"


def test_altman_z_none_when_total_liabilities_zero():
    bs = _make_df({
        "Total Assets":                           (20_000, 18_000),
        "Total Current Assets":                   (8_000,  7_000),
        "Total Current Liabilities":              (3_000,  3_500),
        "Stockholders Equity":                    (10_000, 9_000),
        "Retained Earnings":                      (5_000,  4_000),
        "Total Liabilities Net Minority Interest": (0, 0),
    })
    inc = _make_df({"EBIT": (1_500, 1_200)})
    result = _compute_altman_z(bs, inc)
    assert result is None, f"expected None when total_liabilities=0, got {result}"


def test_altman_z_negative_equity_produces_negative_z():
    """Negative equity → X4 negative → Z'' can be negative. Must not crash."""
    bs = _make_df({
        "Total Assets":                           (20_000, 18_000),
        "Total Current Assets":                   (8_000,  7_000),
        "Total Current Liabilities":              (3_000,  3_500),
        "Stockholders Equity":                    (-5_000, -4_000),  # negative equity
        "Retained Earnings":                      (-10_000, -8_000),
        "Total Liabilities Net Minority Interest": (7_000, 7_500),
    })
    inc = _make_df({"EBIT": (-500, 100)})
    result = _compute_altman_z(bs, inc)
    assert result is not None, "expected a float (even negative), got None"
    assert result < 0, f"expected negative Z'' for deeply distressed fixture, got {result}"


def test_altman_z_none_when_bs_none():
    result = _compute_altman_z(None, None)
    assert result is None, "expected None when bs_curr is None"


# ── test runner ──────────────────────────────────────────────────────────────

def run_all():
    tests = [
        # _yf_row_prev
        test_yf_row_prev_returns_prior_year_value,
        test_yf_row_prev_second_label_when_first_absent,
        test_yf_row_prev_none_when_only_one_column,
        test_yf_row_prev_none_on_none_df,
        test_yf_row_prev_none_on_empty_df,
        test_yf_row_prev_none_when_no_label_matches,
        # _dcf_wacc
        test_dcf_wacc_standard,
        test_dcf_wacc_zero_yield,
        test_dcf_wacc_higher_yield,
        # _compute_piotroski
        test_piotroski_all_pass_returns_9,
        test_piotroski_all_fail_returns_0,
        test_piotroski_none_when_no_statements,
        test_piotroski_skips_comparison_when_prev_absent,
        # _compute_altman_z
        test_altman_z_known_fixture,
        test_altman_z_none_when_total_assets_zero,
        test_altman_z_none_when_total_liabilities_zero,
        test_altman_z_negative_equity_produces_negative_z,
        test_altman_z_none_when_bs_none,
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
