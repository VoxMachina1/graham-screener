"""
Phase 5.1 corrective-fix tests
==============================
Covers the two live-data bugs surfaced after the first scored Actions run:
  Bug A — the value-trap gate tripped for 100% of tickers (dead Safety pillar)
          because the 8-of-10-year EPS_Stability rule is structurally 0 with
          yfinance's ~4-year EPS history.  Fix: _eps_stable_for_gate().
  Bug B — growth was the inflated Finnhub epsGrowth5Y capped at 25% for ~every
          ticker (fake "Fast" growers).  Fix: _reconcile_growth() anchors it to
          the realized EPS CAGR.

DESIGN RULES (match test_scoring.py):
  - Vanilla assert only — no pytest dependency.
  - Dummy env vars retained for compatibility with network-entry-point guards.

HOW TO RUN:
    python tests/test_growth_trap_fixes.py
"""

import os
import sys

os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from stock_screener import (
    _reconcile_growth,
    _eps_stable_for_gate,
    compute_growth_5yr_cagr,
    trap_gate,
    GROWTH_CAP,
    GROWTH_FINNHUB_FLOOR,
)

# Real EPS_Annual arrays (oldest→newest) from the first live scored run that
# exposed the bugs. These are the regression anchors.
CTSH = [4.42, 4.21, 4.52, 4.57]   # ~flat → Finnhub reported 25% (garbage)
HBAN = [1.47, 1.26, 1.24, 1.41]   # flat/declining
LEN  = [15.74, 13.73, 14.31, 7.98]  # declining (cyclical)
L    = [3.39, 6.3, 6.41, 7.98]    # genuine fast grower (~33%)
ALL  = [-5.22, -1.2, 17.22, 38.56]  # loss years then recovery
KMB  = [6.0, 6.2, 6.1, 6.4]       # stable positive EPS (2026-07-01 prod run: Finnhub reported -242%)


# ── Bug B: _reconcile_growth ────────────────────────────────────────────────

def test_reconcile_caps_inflated_finnhub_at_realized_cagr():
    # Finnhub claims 25% but realized CTSH CAGR is ~1% → take the lower realized value.
    cagr = compute_growth_5yr_cagr(CTSH)
    g = _reconcile_growth(25.0, cagr)
    assert g == cagr, f"expected reconciled growth to equal realized CAGR {cagr}, got {g}"
    assert 0 < g < 3, f"CTSH realized growth should be low single digits, got {g}"


def test_reconcile_falls_back_to_finnhub_when_cagr_missing():
    assert _reconcile_growth(25.0, None) == 25.0


def test_reconcile_falls_back_to_cagr_when_finnhub_missing():
    assert _reconcile_growth(None, 7.0) == 7.0


def test_reconcile_both_none():
    assert _reconcile_growth(None, None) is None


def test_reconcile_declining_eps_yields_negative_growth():
    # HBAN/LEN decline → realized CAGR negative → reconciled growth negative,
    # which downstream routes to WORST_DISCOUNT (drops out of the Top-N).
    for arr in (HBAN, LEN):
        cagr = compute_growth_5yr_cagr(arr)
        g = _reconcile_growth(25.0, cagr)
        assert g is not None and g < 0, f"{arr} should reconcile to negative growth, got {g}"


def test_reconcile_genuine_grower_keeps_high_growth():
    # L grew ~33% → realized CAGR caps at GROWTH_CAP; reconciled stays at the cap.
    cagr = compute_growth_5yr_cagr(L)
    assert cagr == GROWTH_CAP, f"L realized CAGR should hit the cap, got {cagr}"
    assert _reconcile_growth(25.0, cagr) == GROWTH_CAP


def test_reconcile_discards_impossible_negative_finnhub_value():
    # KMB (2026-07-01 prod): Finnhub epsGrowth5Y=-242% is impossible (EPS can't
    # fall >100% from a positive base). min() would pick it over a sane CAGR just
    # for being lower — the floor must discard it before reconciliation instead.
    cagr = compute_growth_5yr_cagr(KMB)
    g = _reconcile_growth(-242.0, cagr)
    assert g == cagr, f"expected fallback to realized CAGR {cagr}, got {g}"
    assert g > GROWTH_FINNHUB_FLOOR, f"reconciled growth still below floor: {g}"


def test_reconcile_impossible_finnhub_with_no_cagr_falls_back_to_none():
    assert _reconcile_growth(-242.0, None) is None


def test_reconcile_at_floor_boundary_is_not_discarded():
    # Exactly at the floor is still (barely) possible; only strictly-below is discarded.
    assert _reconcile_growth(GROWTH_FINNHUB_FLOOR, None) == GROWTH_FINNHUB_FLOOR


# ── Bug A: _eps_stable_for_gate ──────────────────────────────────────────────

def test_eps_stable_all_positive_is_stable():
    # All-positive history → stable (1) → does NOT trip the trap on the EPS input.
    assert _eps_stable_for_gate(CTSH) == 1


def test_eps_stable_with_negative_year_is_unstable():
    assert _eps_stable_for_gate(ALL) == 0


def test_eps_stable_insufficient_data_is_none():
    assert _eps_stable_for_gate([4.5]) is None
    assert _eps_stable_for_gate([]) is None


def test_eps_stable_filters_nan():
    nan = float("nan")
    assert _eps_stable_for_gate([4.42, nan, 4.57]) == 1


# ── Integration: the fix actually un-trips healthy stocks ────────────────────

def test_trap_not_tripped_for_healthy_stock_after_fix():
    # CTSH-like: stable positive EPS, benign leverage/liquidity, positive FCF.
    is_trap, cov = trap_gate(
        debt_equity=0.5,
        current_ratio=1.5,
        eps_stability=_eps_stable_for_gate(CTSH),  # now 1, not the old structural 0
        fcf_per_share=2.0,
    )
    assert is_trap is False, "healthy stock should no longer trip the trap gate"
    assert cov == 1.0


def test_trap_still_tripped_for_loss_making_stock():
    is_trap, _ = trap_gate(
        debt_equity=0.5,
        current_ratio=1.5,
        eps_stability=_eps_stable_for_gate(ALL),  # 0 → trips
        fcf_per_share=2.0,
    )
    assert is_trap is True, "a stock with loss years should still trip the trap gate"


def run_all():
    tests = [
        test_reconcile_caps_inflated_finnhub_at_realized_cagr,
        test_reconcile_falls_back_to_finnhub_when_cagr_missing,
        test_reconcile_falls_back_to_cagr_when_finnhub_missing,
        test_reconcile_both_none,
        test_reconcile_declining_eps_yields_negative_growth,
        test_reconcile_genuine_grower_keeps_high_growth,
        test_reconcile_discards_impossible_negative_finnhub_value,
        test_reconcile_impossible_finnhub_with_no_cagr_falls_back_to_none,
        test_reconcile_at_floor_boundary_is_not_discarded,
        test_eps_stable_all_positive_is_stable,
        test_eps_stable_with_negative_year_is_unstable,
        test_eps_stable_insufficient_data_is_none,
        test_eps_stable_filters_nan,
        test_trap_not_tripped_for_healthy_stock_after_fix,
        test_trap_still_tripped_for_loss_making_stock,
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
