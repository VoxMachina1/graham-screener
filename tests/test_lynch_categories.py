"""Tests for the six-category Lynch classifier."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_screener import lynch_classify, lynch_metrics


def _base(**kw):
    args = dict(
        g=15.0,
        eps=2.0,
        sector="Technology",
        annual_eps=[1.0, 1.2, 1.4, 1.6],
        dist_5y_low=80.0,
        piotroski_f=7,
        altman_z=3.0,
        pb=3.0,
        current_ratio=2.5,
        long_term_debt=10.0,
        current_assets=500.0,
        current_liabilities=200.0,
        earnings_yield=5.0,
    )
    args.update(kw)
    return lynch_classify(**args)


def test_slow_band():
    cat, detail = _base(g=5.0)
    assert cat == "Slow", (cat, detail)
    print("OK slow")


def test_stalwart_band_tightened():
    cat, _ = _base(g=11.0)
    assert cat == "Stalwart", cat
    cat, _ = _base(g=12.0)
    assert cat == "Stalwart", cat
    cat, _ = _base(g=12.1)
    assert cat == "Fast", cat
    print("OK stalwart 10-12")


def test_fast_bands_documented():
    cat, detail = _base(g=25.0)
    assert cat == "Fast" and "book" in detail, (cat, detail)
    cat, detail = _base(g=15.0)
    assert cat == "Fast" and "judgment" in detail, (cat, detail)
    print("OK fast bands")


def test_turnaround():
    cat, detail = _base(
        eps=1.5,
        annual_eps=[-2.0, -0.5, 0.8, 1.5],
        dist_5y_low=15.0,
        piotroski_f=6,
        altman_z=2.0,
    )
    assert cat == "Turnaround", (cat, detail)
    print("OK turnaround")


def test_turnaround_needs_evidence():
    # weak Piotroski -> not a turnaround
    cat, _ = _base(eps=1.5, annual_eps=[-2.0, -0.5, 0.8, 1.5],
                   dist_5y_low=15.0, piotroski_f=3, altman_z=2.0)
    assert cat != "Turnaround", cat
    print("OK turnaround evidence gate")


def test_cyclical():
    cat, detail = _base(sector="Energy",
                        annual_eps=[3.0, -1.0, 4.0, 0.5])
    assert cat == "Cyclical", (cat, detail)
    print("OK cyclical")


def test_cyclical_needs_variance():
    cat, _ = _base(sector="Energy", annual_eps=[3.0, 3.2, 3.4, 3.6])
    assert cat != "Cyclical", cat
    print("OK cyclical variance gate")


def test_asset_play():
    cat, detail = _base(pb=0.7, current_ratio=2.5, long_term_debt=10.0,
                        current_assets=500.0, current_liabilities=200.0,
                        earnings_yield=4.0, g=5.0)
    assert cat == "Asset Play", (cat, detail)
    print("OK asset play")


def test_asset_play_needs_fortress():
    cat, _ = _base(pb=0.7, current_ratio=1.2, g=5.0)
    assert cat != "Asset Play", cat
    print("OK asset play balance-sheet gate")


def test_unclassified_without_growth():
    cat, detail = _base(g=None)
    assert cat == "Unclassified", (cat, detail)
    cat, _ = _base(g=-5.0)
    assert cat == "Unclassified", cat
    print("OK unclassified")


def test_provisional_bands_tightened_in_metrics():
    m = lynch_metrics(100.0, 2.0, 11.0, 1.0)
    assert m["Lynch_Category"] == "Stalwart", m["Lynch_Category"]
    m = lynch_metrics(100.0, 2.0, 15.0, 1.0)
    assert m["Lynch_Category"] == "Fast", m["Lynch_Category"]
    print("OK provisional bands")


if __name__ == "__main__":
    test_slow_band()
    test_stalwart_band_tightened()
    test_fast_bands_documented()
    test_turnaround()
    test_turnaround_needs_evidence()
    test_cyclical()
    test_cyclical_needs_variance()
    test_asset_play()
    test_asset_play_needs_fortress()
    test_unclassified_without_growth()
    test_provisional_bands_tightened_in_metrics()
    print("ALL LYNCH CATEGORY TESTS PASSED")
