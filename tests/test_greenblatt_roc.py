"""Tests for Greenblatt true book ROC: EBIT / (NWC + net PPE)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_screener import _compute_roc_book


def test_book_formula():
    # EBIT 200, CA 500, CL 300 (NWC 200), PPE 800 -> 200/1000 = 20%
    assert _compute_roc_book(200.0, 500.0, 300.0, 800.0) == 20.0
    print("OK book formula")


def test_differs_from_roic_variant():
    # Book ROC must NOT apply the 0.79 tax factor and must NOT use debt+equity-cash
    r = _compute_roc_book(100.0, 400.0, 100.0, 500.0)  # 100/800 = 12.5
    assert r == 12.5, r
    print("OK no tax factor, tangible capital base")


def test_missing_ppe_ok():
    # net PPE missing -> treated as 0, NWC alone is the base
    assert _compute_roc_book(100.0, 400.0, 100.0, None) == 100.0 / 300.0 * 100
    print("OK missing PPE")


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
    test_book_formula()
    test_differs_from_roic_variant()
    test_missing_ppe_ok()
    test_nonpositive_tangible_none()
    test_missing_inputs_none()
    test_negative_ebit_not_clamped()
    print("ALL GREENBLATT BOOK ROC TESTS PASSED")
