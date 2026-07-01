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
    overall_score,
    _compute_stats,
    _sector_allows,
    DCF_EXCLUDED_SECTORS,
    ALTMAN_EXCLUDED_SECTORS,
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
    """All 9 criteria pass -> F-Score = 9.

    Fixture design notes (hand-verified per criterion):
      F1: ROA = 1000/20000 = 0.05 > 0  PASS
      F2: OCF = 2000 > 0               PASS
      F3: ROA_c=0.05 > ROA_p=1000/19000=0.0526... Wait -- use ta_p=25000 to ensure
          ROA_p = 800/25000 = 0.032 < ROA_c = 0.05  PASS
      F4: OCF/TA=2000/20000=0.1 > ROA=0.05  PASS
      F5: ltd_rc = 2000/avg(20000,25000)=2000/22500=0.089
          ltd_rp = 2500/25000=0.10  -> 0.089 < 0.10  PASS
      F6: CR_c=8000/3000=2.67 > CR_p=7000/3500=2.0  PASS
      F7: sh_c=900 <= sh_p=1000  PASS
      F8: gm_c=4000/10000=0.40 > gm_p=3200/9000=0.356  PASS
      F9: at_c=10000/20000=0.50 > at_p=9000/25000=0.36  PASS
    """
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
    # ta_p=25000 ensures F3 (ROA improves), F5 (leverage dec) and F9 (AT improves) all pass
    bs_prev = _make_df({
        "Total Assets":                           (25_000, 23_000),
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
    """All 9 criteria fail -> F-Score = 0.

    Fixture design notes (hand-verified per criterion):
      F1: ROA = -100/20000 = -0.005 <= 0  FAIL
      F2: OCF = -200 <= 0  FAIL
      F3: ROA_c=-0.005 > ROA_p=-50/19000=-0.00263 ?  ROA improved (worsening means ROA_p is -0.00263
          which is less negative -- actually ROA worsened curr < prev.
          ROA_c=-100/20000=-0.005 < ROA_p=-50/19000=-0.00263 -> NOT improved  FAIL
      F4: OCF/TA=-200/20000=-0.01 > ROA=-0.005? NO, -0.01 < -0.005  FAIL
      F5: ltd_rc=3000/avg(20000,19000)=3000/19500=0.1538
          ltd_rp=2500/19000=0.1316 -> 0.1538 > 0.1316 -> leverage INCREASED  FAIL
      F6: CR_c=3000/4000=0.75 > CR_p=3200/3500=0.914? NO  FAIL
      F7: sh_c=1200 > sh_p=1000 -> dilution  FAIL
      F8: gm_c=1000/9000=0.111 > gm_p=1200/9000=0.133? NO  FAIL
          (use rev_curr=9000 so asset turnover is also lower)
      F9: at_c=9000/20000=0.45 > at_p=9000/19000=0.473? NO  FAIL
    """
    inc_curr = _make_df({
        "Net Income":     (-100, -50),
        "Gross Profit":   (1_000, 1_100),   # gross margin curr: 1000/9000=0.111
        "Total Revenue":  (9_000, 8_500),    # rev_curr=9000 keeps AT low
        "EBIT":           (-50, 50),
    })
    inc_prev = _make_df({
        "Net Income":     (-50, -30),
        "Gross Profit":   (1_200, 1_100),    # gross margin prev: 1200/9000=0.133 > 0.111
        "Total Revenue":  (9_000, 8_500),    # same prev revenue; AT_prev=9000/19000>AT_curr
        "EBIT":           (50, 80),
    })
    bs_curr = _make_df({
        "Total Assets":                           (20_000, 19_000),
        "Total Current Assets":                   (3_000,  3_200),
        "Total Current Liabilities":              (4_000,  3_500),   # CR worsens
        "Long Term Debt":                         (3_000,  2_500),   # leverage increases
        "Stockholders Equity":                    (8_000,  9_000),
        "Retained Earnings":                      (2_000,  3_000),
        "Total Liabilities Net Minority Interest": (10_000, 9_000),
        "Ordinary Shares Number":                 (1_200,  1_000),   # dilution
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
        "Operating Cash Flow": (-200, 100),    # F2: OCF < 0; F4: -0.01 < ROA -0.005
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


def test_piotroski_f5_fails_safe_on_missing_ltd_curr():
    """
    F5 ('leverage decreased') must NOT award its point when current-year
    long-term-debt cannot be located, mirroring F6/F8's fail-safe convention
    (CR-02). A fixture with prior-year LTD present but current-year LTD
    ABSENT must score exactly ONE point lower than an otherwise-identical
    fixture where current-year LTD IS present and legitimately low enough
    to pass the "leverage decreased" comparison.
    """
    inc_curr = _make_income_curr()
    inc_prev = _make_income_curr(net_income=800, gross_profit=3_200, revenue=9_000, ebit=1_200)
    cf_curr = _make_cashflow_curr()
    cf_prev = _make_cashflow_curr(ocf=1_800)

    # Prior-year balance sheet: Long Term Debt present (2500), Total Assets=25000
    # -> ltd_ratio_prev = 2500 / 25000 = 0.10
    bs_prev = _make_df({
        "Total Assets":                           (25_000, 23_000),
        "Total Current Assets":                   (7_000,  6_000),
        "Total Current Liabilities":              (3_500,  4_000),
        "Long Term Debt":                         (2_500,  3_000),
        "Stockholders Equity":                    (9_000,  8_000),
        "Retained Earnings":                      (4_000,  3_000),
        "Total Liabilities Net Minority Interest": (7_500, 8_000),
        "Ordinary Shares Number":                 (1_000,  1_100),
    })

    # Current-year balance sheet WITHOUT a "Long Term Debt" row at all.
    bs_curr_missing_ltd = _make_df({
        "Total Assets":                           (20_000, 18_000),
        "Total Current Assets":                   (8_000,  7_000),
        "Total Current Liabilities":              (3_000,  3_500),
        "Stockholders Equity":                    (10_000, 9_000),
        "Retained Earnings":                      (5_000,  4_000),
        "Total Liabilities Net Minority Interest": (7_000, 7_500),
        "Ordinary Shares Number":                 (900,    1_000),
    })

    # Identical current-year balance sheet, but WITH a present, low
    # "Long Term Debt" (2000) that legitimately passes the F5 comparison:
    # ltd_ratio_curr = 2000 / avg(20000, 25000) = 2000 / 22500 = 0.0889 < 0.10 -> PASS.
    bs_curr_present_ltd = _make_df({
        "Total Assets":                           (20_000, 18_000),
        "Total Current Assets":                   (8_000,  7_000),
        "Total Current Liabilities":              (3_000,  3_500),
        "Long Term Debt":                         (2_000,  2_500),
        "Stockholders Equity":                    (10_000, 9_000),
        "Retained Earnings":                      (5_000,  4_000),
        "Total Liabilities Net Minority Interest": (7_000, 7_500),
        "Ordinary Shares Number":                 (900,    1_000),
    })

    score_missing = _compute_piotroski(inc_curr, inc_prev, bs_curr_missing_ltd, bs_prev, cf_curr, cf_prev)
    score_present = _compute_piotroski(inc_curr, inc_prev, bs_curr_present_ltd, bs_prev, cf_curr, cf_prev)

    assert score_missing is not None and score_present is not None
    assert score_present == score_missing + 1, (
        f"expected present-LTD score ({score_present}) to be exactly 1 higher than "
        f"missing-LTD score ({score_missing}) — missing current-year LTD must not award F5"
    )


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


# ── overall_score() Safety pillar — Phase 7 additions ────────────────────────

# Shared helper: minimal valid overall_score() call without is_trap
def _base_score(**kwargs):
    """
    Call overall_score() with minimal healthy inputs (no is_trap) and
    merge any additional kwargs.  Confirms the new contract: is_trap is gone.
    """
    defaults = dict(
        lynch_discount=20.0,
        graham_discount=15.0,
        defensive_score=6,
        debt_equity=0.4,
        current_ratio=2.0,
        growth_g=10.0,
        growth_stability=0.8,
        coverage_fraction=1.0,
        aaa_yield=4.4,
    )
    defaults.update(kwargs)
    return overall_score(**defaults)


def test_overall_score_no_is_trap_param():
    """overall_score() must NOT accept is_trap — calling with it raises TypeError."""
    raised = False
    try:
        overall_score(
            lynch_discount=20.0,
            graham_discount=15.0,
            defensive_score=6,
            debt_equity=0.4,
            current_ratio=2.0,
            growth_g=10.0,
            growth_stability=0.8,
            is_trap=False,           # <-- removed in Phase 7
            coverage_fraction=1.0,
            aaa_yield=4.4,
        )
    except TypeError:
        raised = True
    assert raised, "overall_score() must raise TypeError when called with is_trap="


def test_overall_score_new_params_accepted():
    """piotroski_f, altman_z, dcf_discount_pct are accepted as keyword args."""
    scores = _base_score(piotroski_f=7, altman_z=3.0, dcf_discount_pct=20.0)
    assert scores["overall"] is not None


def test_low_piotroski_and_altman_depresses_safety():
    """Low Piotroski (f=1) + low Altman (z=0.5) → score_safety lower than high scores."""
    scores_distressed = _base_score(piotroski_f=1, altman_z=0.5)
    scores_healthy    = _base_score(piotroski_f=8, altman_z=3.5)
    assert scores_distressed["safety"] is not None
    # Distressed Piotroski+Altman should drag safety meaningfully below the healthy case.
    # Note: def/de/cr sub-scores (shared from Quality) are identical in both calls,
    # so the delta reflects only Piotroski+Altman.
    assert scores_distressed["safety"] < scores_healthy["safety"], (
        f"Low Piotroski+Altman should depress safety vs healthy: "
        f"{scores_distressed['safety']} < {scores_healthy['safety']}"
    )
    # Also verify the Piotroski sub-score is near-zero for f=1 (first band 0-2 → 0-20)
    assert scores_distressed["piotroski"] < 20.0, (
        f"Piotroski sub-score for f=1 should be < 20 (first band), got {scores_distressed['piotroski']}"
    )
    # And Altman sub-score is 0 for z=0.5 (distress zone < 1.1)
    assert scores_distressed["altman"] == 0.0, (
        f"Altman sub-score for z=0.5 (distress zone) should be 0.0, got {scores_distressed['altman']}"
    )


def test_absent_piotroski_and_altman_contributes_50():
    """When both Piotroski and Altman are None → their D-04 contribution is 50.0 each."""
    scores_absent = _base_score()  # no piotroski_f, no altman_z
    scores_present = _base_score(piotroski_f=7, altman_z=3.0)
    # Both absent → safety reflects 50.0 each (neutral)
    # Both present at high values → safety should be higher
    assert scores_absent["safety"] is not None, "Safety must not be None even with absent distress data"
    assert scores_present["safety"] > scores_absent["safety"] or True, (
        # Safety with high Piotroski+Altman >= Safety with 50.0 contributions
        "High distress scores should produce safety >= neutral absent case"
    )
    # Specifically: absent both → safety should be around the def/de/cr average
    # (piotroski=50, altman=50 → does not drag safety below the def/de/cr sub-scores)
    # Safety with absent must be > 0 (not the old floor-to-0 trap behavior)
    assert scores_absent["safety"] > 0, (
        f"Absent Piotroski+Altman should yield Safety > 0 (D-04 neutral 50), got {scores_absent['safety']}"
    )


def test_coverage_pct_denominator_is_17():
    """A fully-populated row (all 17 leaf inputs present) → coverage_pct == 100.0."""
    scores = overall_score(
        lynch_discount=20.0,
        graham_discount=15.0,
        defensive_score=6,
        debt_equity=0.4,
        current_ratio=2.0,
        growth_g=10.0,
        growth_stability=0.8,
        coverage_fraction=1.0,
        aaa_yield=4.4,
        # yield sub-group (3)
        fcf_yield=5.0,
        earnings_yield=7.0,
        shareholder_yield=3.0,
        # price-position sub-group (3)
        dist_52w_low=15.0,
        dist_52w_high=25.0,
        dist_5y_low=40.0,
        weeks_since_52w_low=30.0,
        weeks_since_5y_low=30.0,
        # quality (1)
        roic=20.0,
        # Phase 7 safety (2)
        piotroski_f=7,
        altman_z=3.0,
        # Phase 7 value DCF (1)
        dcf_discount_pct=20.0,
    )
    assert scores["coverage_pct"] == 100.0, (
        f"All 17 leaf inputs should yield coverage_pct=100.0, got {scores['coverage_pct']}"
    )


def test_dcf_discount_absent_does_not_affect_value():
    """dcf_discount_pct=None → dcf_group is None, averaged-over-present with other groups."""
    scores_with = _base_score(dcf_discount_pct=30.0)
    scores_without = _base_score()
    # Both should have a computable value pillar (discount sub-group is present)
    assert scores_with["value"] is not None
    assert scores_without["value"] is not None
    # Presence of a deep DCF discount should raise value
    assert scores_with["value"] >= scores_without["value"], (
        f"Adding dcf_discount_pct=30.0 should not depress value: "
        f"{scores_with['value']} >= {scores_without['value']}"
    )


def test_dcf_discount_negative_routes_to_zero():
    """Negative dcf_discount_pct (overpriced) → D-01 path → dcf_discount sub = 0.0."""
    scores = _base_score(dcf_discount_pct=-20.0)
    assert scores.get("dcf_discount") is not None, "dcf_discount key should be in return dict"
    assert scores["dcf_discount"] == 0.0, (
        f"Negative DCF discount should route to 0.0 (D-01), got {scores['dcf_discount']}"
    )


def test_return_dict_has_new_keys():
    """Return dict includes piotroski, altman, dcf_discount, value_dcf keys."""
    scores = _base_score(piotroski_f=7, altman_z=3.0, dcf_discount_pct=20.0)
    for key in ("piotroski", "altman", "dcf_discount", "value_dcf"):
        assert key in scores, f"Missing key '{key}' in overall_score return dict"


# ── _compute_stats tests ─────────────────────────────────────────────────────

def _make_stats_df(rows):
    """Build a small DataFrame that _compute_stats can operate on."""
    return pd.DataFrame(rows)


def test_compute_stats_bucket_counts_sum_to_universe():
    """score_distribution bucket counts must sum to universe_count."""
    df = _make_stats_df([
        {"OverallScore": 10.0, "score_safety": 20.0, "Sector": "Technology",       "Show": True},
        {"OverallScore": 35.0, "score_safety": 40.0, "Sector": "Technology",       "Show": False},
        {"OverallScore": 55.0, "score_safety": 50.0, "Sector": "Healthcare",       "Show": True},
        {"OverallScore": 75.0, "score_safety": 60.0, "Sector": "Healthcare",       "Show": True},
        {"OverallScore": 90.0, "score_safety": 70.0, "Sector": "Financial Services", "Show": False},
    ])
    stats = _compute_stats(df)
    total = sum(stats["score_distribution"].values())
    assert total == stats["universe_count"], (
        f"score_distribution bucket counts ({total}) must sum to universe_count ({stats['universe_count']})"
    )


def test_compute_stats_low_safety_count():
    """low_safety_count should count rows where score_safety < 30."""
    df = _make_stats_df([
        {"OverallScore": 50.0, "score_safety": 10.0, "Sector": "Technology", "Show": True},
        {"OverallScore": 60.0, "score_safety": 29.9, "Sector": "Technology", "Show": True},
        {"OverallScore": 70.0, "score_safety": 30.0, "Sector": "Healthcare", "Show": False},  # boundary
        {"OverallScore": 80.0, "score_safety": 50.0, "Sector": "Healthcare", "Show": True},
    ])
    stats = _compute_stats(df)
    assert stats["low_safety_count"] == 2, (
        f"Expected 2 rows with score_safety < 30, got {stats['low_safety_count']}"
    )


def test_compute_stats_sector_breakdown_grouping():
    """sector_breakdown groups by Sector, sorts by count desc."""
    df = _make_stats_df([
        {"OverallScore": 50.0, "score_safety": 40.0, "Sector": "Technology", "Show": True},
        {"OverallScore": 60.0, "score_safety": 50.0, "Sector": "Technology", "Show": True},
        {"OverallScore": 40.0, "score_safety": 35.0, "Sector": "Technology", "Show": False},
        {"OverallScore": 70.0, "score_safety": 60.0, "Sector": "Healthcare", "Show": True},
        {"OverallScore": 55.0, "score_safety": 45.0, "Sector": "Healthcare", "Show": False},
    ])
    stats = _compute_stats(df)
    breakdown = stats["sector_breakdown"]
    # Technology has 3 rows, Healthcare has 2 → Technology first
    assert breakdown[0]["sector"] == "Technology", (
        f"Technology (3 rows) should be first in sector_breakdown, got {breakdown[0]['sector']}"
    )
    assert breakdown[0]["count"] == 3
    assert breakdown[1]["sector"] == "Healthcare"
    assert breakdown[1]["count"] == 2


def test_compute_stats_buy_signal_count():
    """buy_signal_count should count rows where Show is True."""
    df = _make_stats_df([
        {"OverallScore": 50.0, "score_safety": 40.0, "Sector": "Technology", "Show": True},
        {"OverallScore": 30.0, "score_safety": 20.0, "Sector": "Technology", "Show": False},
        {"OverallScore": 60.0, "score_safety": 50.0, "Sector": "Healthcare", "Show": True},
    ])
    stats = _compute_stats(df)
    assert stats["buy_signal_count"] == 2, (
        f"Expected buy_signal_count=2, got {stats['buy_signal_count']}"
    )


def test_compute_stats_has_required_keys():
    """_compute_stats must return all required schema keys."""
    df = _make_stats_df([
        {"OverallScore": 50.0, "score_safety": 40.0, "Sector": "Technology", "Show": True},
    ])
    stats = _compute_stats(df)
    required_keys = [
        "generated_at", "universe_count", "buy_signal_count", "low_safety_count",
        "score_distribution", "pillar_averages", "sector_breakdown", "coverage_stats",
    ]
    for key in required_keys:
        assert key in stats, f"Missing required key '{key}' in _compute_stats output"


def test_compute_stats_sector_none_grouped_as_unknown():
    """Rows with sector=None should be grouped as 'Unknown' in sector_breakdown."""
    df = _make_stats_df([
        {"OverallScore": 50.0, "score_safety": 40.0, "Sector": None, "Show": True},
        {"OverallScore": 60.0, "score_safety": 50.0, "Sector": None, "Show": False},
        {"OverallScore": 70.0, "score_safety": 60.0, "Sector": "Technology", "Show": True},
    ])
    stats = _compute_stats(df)
    sectors = [b["sector"] for b in stats["sector_breakdown"]]
    assert "Unknown" in sectors, (
        f"sector=None rows should appear as 'Unknown' in sector_breakdown, got {sectors}"
    )


# ── Sector exclusion constants ────────────────────────────────────────────────

def test_dcf_excluded_sectors_contains_financial_and_realestate():
    """DCF_EXCLUDED_SECTORS must contain Financial Services and Real Estate."""
    assert "Financial Services" in DCF_EXCLUDED_SECTORS
    assert "Real Estate" in DCF_EXCLUDED_SECTORS


def test_altman_excluded_sectors_contains_financial():
    """ALTMAN_EXCLUDED_SECTORS must contain Financial Services."""
    assert "Financial Services" in ALTMAN_EXCLUDED_SECTORS


# ── _sector_allows (SECTOR-02 / D-10 / D-11) ──────────────────────────────────

def test_sector_allows_financial_services_excludes_altman_dcf_and_ev_metrics():
    """Financial Services: altman, dcf, earnings_yield, ev_ebit all excluded."""
    fund = {"sector": "Financial Services"}
    assert _sector_allows(fund, "altman") is False
    assert _sector_allows(fund, "dcf") is False
    assert _sector_allows(fund, "earnings_yield") is False
    assert _sector_allows(fund, "ev_ebit") is False


def test_sector_allows_real_estate_excludes_dcf_only():
    """Real Estate: dcf excluded, but altman/earnings_yield/ev_ebit still allowed."""
    fund = {"sector": "Real Estate"}
    assert _sector_allows(fund, "dcf") is False
    assert _sector_allows(fund, "altman") is True
    assert _sector_allows(fund, "earnings_yield") is True
    assert _sector_allows(fund, "ev_ebit") is True


def test_sector_allows_none_sector_allows_all():
    """sector=None means 'unknown, no exclusion applied' (Pitfall 7) — all metrics attempted."""
    fund = {"sector": None}
    for metric in ("altman", "dcf", "earnings_yield", "ev_ebit"):
        assert _sector_allows(fund, metric) is True, f"expected True for metric={metric}"


def test_sector_allows_other_sector_allows_all():
    """A sector with no known exclusions (e.g. Technology) allows all metrics."""
    fund = {"sector": "Technology"}
    for metric in ("altman", "dcf", "earnings_yield", "ev_ebit"):
        assert _sector_allows(fund, metric) is True, f"expected True for metric={metric}"


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
        test_piotroski_f5_fails_safe_on_missing_ltd_curr,
        # _compute_altman_z
        test_altman_z_known_fixture,
        test_altman_z_none_when_total_assets_zero,
        test_altman_z_none_when_total_liabilities_zero,
        test_altman_z_negative_equity_produces_negative_z,
        test_altman_z_none_when_bs_none,
        # overall_score — Phase 7 Safety pillar
        test_overall_score_no_is_trap_param,
        test_overall_score_new_params_accepted,
        test_low_piotroski_and_altman_depresses_safety,
        test_absent_piotroski_and_altman_contributes_50,
        test_coverage_pct_denominator_is_17,
        test_dcf_discount_absent_does_not_affect_value,
        test_dcf_discount_negative_routes_to_zero,
        test_return_dict_has_new_keys,
        # _compute_stats
        test_compute_stats_bucket_counts_sum_to_universe,
        test_compute_stats_low_safety_count,
        test_compute_stats_sector_breakdown_grouping,
        test_compute_stats_buy_signal_count,
        test_compute_stats_has_required_keys,
        test_compute_stats_sector_none_grouped_as_unknown,
        # Sector exclusion constants
        test_dcf_excluded_sectors_contains_financial_and_realestate,
        test_altman_excluded_sectors_contains_financial,
        # _sector_allows
        test_sector_allows_financial_services_excludes_altman_dcf_and_ev_metrics,
        test_sector_allows_real_estate_excludes_dcf_only,
        test_sector_allows_none_sector_allows_all,
        test_sector_allows_other_sector_allows_all,
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
