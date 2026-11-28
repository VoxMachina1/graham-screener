"""Tests for Greenblatt true book ROC: EBIT / (NWC + net PPE)."""
import sys
import os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_screener import OPERATING_EBIT_LABELS, _compute_roc_book, _yf_row


def test_operating_earnings_excludes_nonoperating_sale_gain():
    income = pd.DataFrame({"2026": [10_070_000_000, 4_599_000_000]},
                          index=["EBIT", "Operating Income"])
    operating = _yf_row(income, OPERATING_EBIT_LABELS)
    assert operating == 4_599_000_000
    assert _compute_roc_book(operating, 5_868_000_000, 4_092_000_000,
                             2_586_000_000) < 110


def test_book_formula():
    # EBIT 200, CA 500, CL 300 (NWC 200), PPE 800 -> 200/1000 = 20%
    assert _compute_roc_book(200.0, 500.0, 300.0, 800.0) == 20.0
    print("OK book formula")


def test_differs_from_roic_variant():
    # Book ROC must NOT apply the 0.79 tax factor and must NOT use debt+equity-cash
    r = _compute_roc_book(100.0, 400.0, 100.0, 500.0)  # 100/800 = 12.5
    assert r == 12.5, r
    print("OK no tax factor, tangible capital base")


def test_missing_ppe_excluded():
    # Book ROC cannot be certified without net fixed assets.
    assert _compute_roc_book(100.0, 400.0, 100.0, None) is None
    print("OK missing PPE excluded")


def test_nonpositive_tangible_none():
    assert _compute_roc_book(100.0, 100.0, 400.0, 50.0) is None
    print("OK non-positive tangible -> None")


def test_missing_inputs_none():
    assert _compute_roc_book(None, 400.0, 100.0, 500.0) is None
    assert _compute_roc_book(100.0, None, 100.0, 500.0) is None
    print("OK missing inputs -> None")


def test_negative_ebit_not_clamped():
    assert _compute_roc_book(-50.0, 400.0, 100.0, 500.0) == -50.0 / 800.0 * 100
    print("OK negative EBIT not clamped")


if __name__ == "__main__":
    test_operating_earnings_excludes_nonoperating_sale_gain()
    test_book_formula()
    test_differs_from_roic_variant()
    test_missing_ppe_excluded()
    test_nonpositive_tangible_none()
    test_missing_inputs_none()
    test_negative_ebit_not_clamped()
    print("ALL GREENBLATT BOOK ROC TESTS PASSED")
