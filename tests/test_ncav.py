"""Tests for NCAV / net-net columns."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stock_screener import ncav_metrics


def test_netnet_classic_rule():
    # CA 900, TL 300 -> NCAV 600; 1M shares -> NCAV_PS 0.0006... use bigger:
    # CA 900M, TL 300M, 100M shares -> NCAV_PS = $6.00; 2/3 = $4.00
    m = ncav_metrics(3.50, 900_000_000.0, 300_000_000.0, 100_000_000.0)
    assert m["NCAV"] == 600_000_000.0, m
    assert m["NCAV_PS"] == 6.0, m
    assert m["NetNet"] is True, m
    assert m["NCAV_Discount_Pct"] == round((1 - 3.5 / 6.0) * 100, 1), m
    print("OK net-net true")


def test_not_netnet():
    m = ncav_metrics(5.00, 900_000_000.0, 300_000_000.0, 100_000_000.0)
    assert m["NetNet"] is False, m
    print("OK net-net false")


def test_missing_inputs_honest_none():
    m = ncav_metrics(3.50, None, 300_000_000.0, 100_000_000.0)
    assert m["NCAV"] is None and m["NetNet"] is None, m
    m = ncav_metrics(3.50, 900_000_000.0, 300_000_000.0, 0)
    assert m["NCAV"] is None, m
    print("OK missing inputs -> None")


def test_negative_ncav_no_flag():
    m = ncav_metrics(1.00, 100_000_000.0, 500_000_000.0, 100_000_000.0)
    assert m["NCAV"] == -400_000_000.0, m
    assert m["NetNet"] is None, m  # no meaningful net-net call on negative NCAV
    print("OK negative NCAV")


if __name__ == "__main__":
    test_netnet_classic_rule()
    test_not_netnet()
    test_missing_inputs_honest_none()
    test_negative_ncav_no_flag()
    print("ALL NCAV TESTS PASSED")
