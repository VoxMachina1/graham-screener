"""
SEC EDGAR integration unit tests
================================
Offline tests for the split-adjustment helper and the literal Graham
defensive criteria (10/10 stability, 20-year dividends, 3-year-average
10Y growth) introduced with the SEC EDGAR EPS integration.

DESIGN RULES:
  - Vanilla assert only — no pytest dependency (matches repo test style).
  - Offline: dummy env vars guard against accidentally reaching a network
    entry point.  All functions under test are pure.

HOW TO RUN:
    python tests/test_sec_eps_integration.py
"""

import os
import sys
from datetime import datetime

# Dummy credentials keep any accidentally reached network entry point deterministic.
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from stock_screener import _apply_split_adjustment, graham_defensive_score


def _base_kwargs(**over):
    kw = dict(
        revenue_ttm=1_000_000_000.0,
        total_assets=2_000_000_000.0,
        sector="Industrials",
        current_ratio=2.5,
        long_term_debt=100_000_000.0,
        current_assets=500_000_000.0,
        current_liabilities=200_000_000.0,
        annual_eps=[1.0, 1.1, 1.2, 1.3],
        annual_dividends=[0.5] * 4,
        price=20.0,
        eps_3yr_avg=1.2,
        pb=1.0,
        sec_eps_series=None,
        div_paid_years=None,
    )
    kw.update(over)
    return kw


# ── _apply_split_adjustment ─────────────────────────────────────────────
# A 10-K retroactively restates comparatives for splits before its filing
# date, so a split adjusts year Y only when the split ex-date is AFTER Y's
# winning filing date.  (filed, ends) use the AAPL shape: Sep FYE.

def test_split_adjust_no_splits_identity():
    series = {2019: 4.0, 2020: 1.2}
    out = _apply_split_adjustment(series, {}, {}, [])
    assert out == series
    out = _apply_split_adjustment(series, {}, {}, None)
    assert out == series


def test_split_adjust_none_series():
    assert _apply_split_adjustment(None, {}, {}, []) is None
    assert _apply_split_adjustment({}, {}, {}, []) is None


def test_split_adjust_split_after_filing():
    # FY2016's winning filing (Nov 2018) predates the Aug 2020 4:1 split,
    # so the figure is pre-split and gets divided by 4.
    series = {2016: 8.31}
    ends = {2016: "2016-09-24"}
    filed = {2016: "2018-11-05"}
    out = _apply_split_adjustment(series, ends, filed, [("2020-08-31", 4.0)])
    assert out == {2016: 2.0775}, out


def test_split_adjust_no_double_count_when_already_restated():
    # REGRESSION: FY2019's winning filing (Oct 2021) POSTDATES the Aug 2020
    # 4:1 split, so the 10-K already restated it — adjusting again would
    # quarter an already-correct figure (the naive period-end rule's bug).
    series = {2019: 2.97}
    ends = {2019: "2019-09-28"}
    filed = {2019: "2021-10-29"}
    out = _apply_split_adjustment(series, ends, filed, [("2020-08-31", 4.0)])
    assert out == {2019: 2.97}, out


def test_split_adjust_cumulative_multiple_splits():
    # 2:1 in 2018 (after the 2017 filing) then 4:1 in 2020 (after the 2019
    # filing): pre-2018 years divided by 8.
    series = {2017: 8.0, 2018: 4.0, 2019: 2.0, 2020: 1.0}
    ends = {y: "%d-12-31" % y for y in series}
    filed = {2017: "2018-03-01", 2018: "2019-03-01",
             2019: "2020-03-01", 2020: "2021-03-01"}
    out = _apply_split_adjustment(
        series, ends, filed, [("2018-06-01", 2.0), ("2020-08-31", 4.0)])
    assert out == {2017: 1.0, 2018: 1.0, 2019: 0.5, 2020: 1.0}, out


def test_split_adjust_reverse_split():
    series = {2019: 0.5, 2020: 6.0}
    ends = {2019: "2019-12-31", 2020: "2020-12-31"}
    filed = {2019: "2020-03-01", 2020: "2021-03-01"}
    out = _apply_split_adjustment(series, ends, filed, [("2020-06-01", 0.1)])
    assert out == {2019: 5.0, 2020: 6.0}, out


def test_split_adjust_missing_filed_falls_back_to_period_end():
    # No filing date known: split after the period end still adjusts.
    series = {2019: 4.0, 2020: 1.2}
    ends = {2019: "2019-12-31", 2020: "2020-12-31"}
    out = _apply_split_adjustment(series, ends, {}, [("2020-08-31", 4.0)])
    assert out == {2019: 1.0, 2020: 1.2}, out


def test_split_adjust_bad_split_rows_ignored():
    series = {2019: 4.0, 2020: 1.2}
    ends = {2019: "2019-12-31", 2020: "2020-12-31"}
    filed = {2019: "2020-03-01", 2020: "2021-03-01"}
    out = _apply_split_adjustment(
        series, ends, filed,
        [("not-a-date", 4.0), ("2020-08-31", 0.0), ("2020-08-31", -2.0)])
    assert out == series, out


# ── graham_defensive_score: literal criteria ────────────────────────────

def _ten_clean_years():
    return {y: 1.0 + 0.1 * (y - 2016) for y in range(2016, 2026)}


def test_stability_literal_ten_of_ten():
    ds = graham_defensive_score(**_base_kwargs(sec_eps_series=_ten_clean_years()))
    assert ds["EPS_Stability"] == 1, ds


def test_stability_one_deficit_year_fails():
    s = _ten_clean_years()
    s[2020] = -0.5
    ds = graham_defensive_score(**_base_kwargs(sec_eps_series=s))
    assert ds["EPS_Stability"] == 0, ds


def test_stability_short_history_fails():
    s = {y: 1.0 for y in range(2020, 2026)}  # only 6 years, all positive
    ds = graham_defensive_score(**_base_kwargs(sec_eps_series=s))
    assert ds["EPS_Stability"] == 0, ds


def test_missing_fiscal_year_does_not_count_as_full_decade():
    s = _ten_clean_years()
    del s[2020]
    s[2015] = 1.0
    ds = graham_defensive_score(**_base_kwargs(sec_eps_series=s))
    assert ds["EPS_Stability"] == 0, ds
    assert ds["EPS_Growth10Y"] == 0, ds


def test_stability_no_sec_data_fails():
    ds = graham_defensive_score(**_base_kwargs(sec_eps_series=None))
    assert ds["EPS_Stability"] == 0, ds


def test_growth_uses_three_year_averages_not_endpoints():
    # Endpoints alone would pass (1.5/1.0 = +50%), but Graham's 3yr-average
    # method fails: first-3 avg 2.333 vs last-3 avg 1.167 = -50%.
    s = {2016: 1.0, 2017: 3.0, 2018: 3.0, 2019: 1.0, 2020: 1.0,
         2021: 1.0, 2022: 1.0, 2023: 1.0, 2024: 1.0, 2025: 1.5}
    ds = graham_defensive_score(**_base_kwargs(sec_eps_series=s))
    assert ds["EPS_Growth10Y"] == 0, ds


def test_growth_three_year_average_pass():
    # first-3 avg 1.0, last-3 avg 1.4 -> +40% >= 33%.
    s = {2016: 1.0, 2017: 1.0, 2018: 1.0, 2019: 1.1, 2020: 1.1,
         2021: 1.2, 2022: 1.2, 2023: 1.4, 2024: 1.4, 2025: 1.4}
    ds = graham_defensive_score(**_base_kwargs(sec_eps_series=s))
    assert ds["EPS_Growth10Y"] == 1, ds


def test_growth_negative_base_fails():
    s = {y: 1.0 for y in range(2016, 2026)}
    s[2016] = -1.0
    s[2017] = -1.0
    s[2018] = -1.0
    ds = graham_defensive_score(**_base_kwargs(sec_eps_series=s))
    assert ds["EPS_Growth10Y"] == 0, ds


def test_dividend_record_twenty_uninterrupted_years():
    last_full = datetime.now().year - 1
    need = set(range(last_full - 19, last_full + 1))
    ds = graham_defensive_score(**_base_kwargs(div_paid_years=set(need)))
    assert ds["Div_Record"] == 1, ds


def test_dividend_record_one_gap_year_fails():
    last_full = datetime.now().year - 1
    need = set(range(last_full - 19, last_full + 1))
    need.discard(last_full - 7)
    ds = graham_defensive_score(**_base_kwargs(div_paid_years=need))
    assert ds["Div_Record"] == 0, ds


def test_dividend_record_no_data_fails():
    ds = graham_defensive_score(**_base_kwargs(div_paid_years=set()))
    assert ds["Div_Record"] == 0, ds
    ds = graham_defensive_score(**_base_kwargs(div_paid_years=None))
    assert ds["Div_Record"] == 0, ds


def test_full_literal_pass_reaches_expected_checks():
    # A textbook defensive name: 10/10 positive, 20yr dividends, strong
    # 3yr-avg growth, cheap on 3yr earnings.
    s = {2016 + i: 1.0 + 0.15 * i for i in range(10)}  # 1.0 -> 2.35
    last_full = datetime.now().year - 1
    need = set(range(last_full - 19, last_full + 1))
    ds = graham_defensive_score(**_base_kwargs(
        sec_eps_series=s, div_paid_years=need,
        price=10.0, eps_3yr_avg=2.2,  # P/E ~4.5 <= 15
    ))
    assert ds["EPS_Stability"] == 1, ds
    assert ds["Div_Record"] == 1, ds
    assert ds["EPS_Growth10Y"] == 1, ds  # (2.2/1.15)-1 = +91%
    assert ds["PE_Limit"] == 1, ds
    assert ds["DefensiveScore"] >= 7, ds


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except AssertionError as e:
            failed += 1
            print("FAIL", t.__name__, "->", e)
    print("%d/%d passed" % (len(tests) - failed, len(tests)))
    sys.exit(1 if failed else 0)
