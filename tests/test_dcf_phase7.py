"""
Phase 7 DCF helper tests
=========================
Covers the new pure helpers added in Phase 7 Plan 01, Task 3:
  _compute_dcf_forward, _compute_dcf_reverse, _dcf_wacc

DESIGN RULES (match test_factors_phase6.py):
  - Vanilla assert only -- no pytest dependency.
  - Env vars set BEFORE importing stock_screener (module reads them at import).
  - No network calls -- all inputs are plain numeric values.

HOW TO RUN:
    python tests/test_dcf_phase7.py
"""

import os
import sys

os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from stock_screener import (
    _compute_dcf_forward,
    _compute_dcf_reverse,
    _dcf_wacc,
    DCF_ERP,
    DCF_TERMINAL_GROWTH_CAP,
    DCF_GROWTH_FLOOR,
)


# ── _compute_dcf_forward ─────────────────────────────────────────────────────

def _hand_compute_dcf(eps, g_cagr_pct, aaa_yield_pct, price=None):
    """
    Reference implementation of forward DCF for test assertions.
    Returns (intrinsic_value, discount_pct) or (None, None).
    """
    import math
    if eps is None or eps <= 0:
        return (None, None)
    wacc = (aaa_yield_pct + DCF_ERP) / 100.0
    g = g_cagr_pct / 100.0
    g_terminal = min(g, DCF_TERMINAL_GROWTH_CAP / 100.0)
    if g_terminal >= wacc:
        raise ValueError("terminal_growth >= WACC in reference implementation")
    pv_stage1 = 0.0
    eps_t = eps
    for t in range(1, 6):
        eps_t = eps_t * (1 + g)
        pv_stage1 += eps_t / (1 + wacc) ** t
    eps_5 = eps_t
    tv = eps_5 * (1 + g_terminal) / (wacc - g_terminal)
    pv_tv = tv / (1 + wacc) ** 5
    intrinsic = pv_stage1 + pv_tv
    if price is not None:
        discount = (1 - price / intrinsic) * 100
    else:
        discount = None
    return (intrinsic, discount)


def test_dcf_forward_returns_finite_intrinsic_and_discount():
    """Standard fixture: eps=5.0, g=8%, aaa=5%, price=80. Should return finite values."""
    intrinsic, discount = _compute_dcf_forward(
        eps=5.0, g_cagr_pct=8.0, aaa_yield_pct=5.0, price=80.0
    )
    assert intrinsic is not None, "expected finite intrinsic, got None"
    assert discount is not None, "expected finite discount, got None"
    assert intrinsic > 0, f"expected positive intrinsic, got {intrinsic}"


def test_dcf_forward_matches_reference_implementation():
    """Forward DCF result must match the hand-computed reference within 1e-6."""
    eps, g, aaa, price = 5.0, 8.0, 5.0, 80.0
    expected_intrinsic, expected_discount = _hand_compute_dcf(eps, g, aaa, price)

    intrinsic, discount = _compute_dcf_forward(
        eps=eps, g_cagr_pct=g, aaa_yield_pct=aaa, price=price
    )
    assert abs(intrinsic - expected_intrinsic) < 1e-6, (
        f"intrinsic mismatch: expected {expected_intrinsic:.6f}, got {intrinsic:.6f}"
    )
    assert abs(discount - expected_discount) < 1e-6, (
        f"discount mismatch: expected {expected_discount:.6f}, got {discount:.6f}"
    )


def test_dcf_forward_cheap_stock_positive_discount():
    """When price < intrinsic, discount_pct should be positive (cheap signal)."""
    # Use a low price relative to a good EPS/growth combo
    intrinsic, discount = _compute_dcf_forward(
        eps=8.0, g_cagr_pct=10.0, aaa_yield_pct=5.0, price=50.0
    )
    assert discount is not None and discount > 0, (
        f"expected positive discount for cheap stock, got {discount}"
    )


def test_dcf_forward_expensive_stock_negative_discount():
    """When price > intrinsic, discount_pct should be negative (overpriced signal)."""
    # Low EPS, low growth, high price -- very expensive
    intrinsic, discount = _compute_dcf_forward(
        eps=0.5, g_cagr_pct=2.0, aaa_yield_pct=5.0, price=500.0
    )
    assert discount is not None and discount < 0, (
        f"expected negative discount for expensive stock, got {discount}"
    )


def test_dcf_forward_none_none_when_eps_none():
    """eps=None -> (None, None)."""
    intrinsic, discount = _compute_dcf_forward(
        eps=None, g_cagr_pct=8.0, aaa_yield_pct=5.0, price=80.0
    )
    assert intrinsic is None, f"expected None intrinsic when eps=None, got {intrinsic}"
    assert discount is None, f"expected None discount when eps=None, got {discount}"


def test_dcf_forward_none_none_when_eps_zero():
    """eps=0 -> (None, None)."""
    intrinsic, discount = _compute_dcf_forward(
        eps=0.0, g_cagr_pct=8.0, aaa_yield_pct=5.0, price=80.0
    )
    assert intrinsic is None
    assert discount is None


def test_dcf_forward_none_none_when_eps_negative():
    """eps < 0 -> (None, None)."""
    intrinsic, discount = _compute_dcf_forward(
        eps=-1.0, g_cagr_pct=8.0, aaa_yield_pct=5.0, price=80.0
    )
    assert intrinsic is None
    assert discount is None


def test_dcf_forward_raises_when_terminal_growth_gte_wacc():
    """
    terminal_growth >= WACC must raise ValueError with a config-diagnostic message.
    aaa_yield=1.0 -> wacc=(1+5.5)/100=0.065.
    g_cagr=10% -> g_terminal=min(10,3)/100=0.03 < 0.065 -- safe.
    To trigger the assert: use a very low aaa_yield AND override DCF_TERMINAL_GROWTH_CAP
    by making g_cagr extremely low but testing the edge. Actually the simplest path:
    use g_cagr=3.0 so g_terminal=0.03 and aaa=0.0 so wacc=0.055 -> 0.03<0.055 safe.
    For a definitive trigger: set aaa_yield negative (impossible in practice but tests the guard).
    Better: set aaa=-5.0 so wacc=(−5+5.5)/100=0.005 and g_terminal=min(3,3)/100=0.03 -> 0.03>=0.005 FIRES.
    """
    raised = False
    try:
        _compute_dcf_forward(
            eps=5.0,
            g_cagr_pct=3.0,    # g_terminal = min(3,3)/100 = 0.03
            aaa_yield_pct=-5.0, # wacc = (-5+5.5)/100 = 0.005 -> 0.03 >= 0.005 -> ValueError
            price=80.0,
        )
    except ValueError as e:
        raised = True
        msg = str(e)
        # Message must name the config knobs
        assert "DCF_ERP" in msg or "DCF_TERMINAL_GROWTH_CAP" in msg, (
            f"ValueError missing config names: {msg}"
        )
    assert raised, "expected ValueError when terminal_growth >= WACC, but no exception raised"


def test_dcf_growth_floor_constant_is_sane():
    """
    DCF_GROWTH_FLOOR must be strictly between -100% (which would make
    (1+g) hit zero) and 0% (it is a floor on decline, not on growth).
    """
    assert DCF_GROWTH_FLOOR > -100.0, (
        f"DCF_GROWTH_FLOOR must be > -100.0 to keep (1+g) positive, got {DCF_GROWTH_FLOOR}"
    )
    assert DCF_GROWTH_FLOOR < 0.0, (
        f"DCF_GROWTH_FLOOR must be < 0.0 (a floor on decline), got {DCF_GROWTH_FLOOR}"
    )


def test_dcf_forward_growth_floor_prevents_sign_flip():
    """
    CR-03: a severely negative reconciled growth rate (-150%) must be floored
    to DCF_GROWTH_FLOOR before reaching _compute_dcf_forward, producing a
    positive, finite intrinsic value -- never a sign-flipped/negative one.
    """
    raw_g = -150.0
    floored_g = max(raw_g, DCF_GROWTH_FLOOR)

    # The floor must actually clamp this severely negative input.
    assert floored_g == DCF_GROWTH_FLOOR, (
        f"expected max({raw_g}, DCF_GROWTH_FLOOR) == DCF_GROWTH_FLOOR, got {floored_g}"
    )
    # DCF_GROWTH_FLOOR > -100.0 keeps (1+g) strictly positive.
    assert DCF_GROWTH_FLOOR > -100.0

    intrinsic, discount_pct = _compute_dcf_forward(
        eps=2.0, g_cagr_pct=floored_g, aaa_yield_pct=5.0, price=10.0
    )
    assert intrinsic is not None, "expected finite intrinsic for floored growth, got None"
    assert intrinsic > 0, f"expected positive intrinsic for floored growth, got {intrinsic}"
    assert discount_pct is not None and discount_pct == discount_pct, (
        f"expected finite discount_pct, got {discount_pct}"
    )

    # Documents WHY the floor is required: the raw unfloored -150% growth
    # would have produced a negative, nonsensical intrinsic value.
    raw_intrinsic, _ = _compute_dcf_forward(
        eps=2.0, g_cagr_pct=raw_g, aaa_yield_pct=5.0, price=10.0
    )
    assert raw_intrinsic is not None and raw_intrinsic < 0, (
        f"expected the raw unfloored -150% growth to produce a negative intrinsic "
        f"(demonstrating why the floor is needed), got {raw_intrinsic}"
    )


# ── _compute_dcf_reverse ─────────────────────────────────────────────────────

def test_dcf_reverse_round_trip():
    """
    Round-trip: compute forward intrinsic at known g, set price=intrinsic,
    assert reverse implied_growth is close to g within 0.1 percentage points.
    """
    eps, g_cagr_pct, aaa_yield_pct = 5.0, 8.0, 5.0
    intrinsic, _ = _compute_dcf_forward(
        eps=eps, g_cagr_pct=g_cagr_pct, aaa_yield_pct=aaa_yield_pct,
        price=0.0  # price irrelevant for intrinsic computation
    )
    # Use intrinsic as price for round-trip
    implied_growth, converged = _compute_dcf_reverse(
        price=intrinsic, eps=eps, aaa_yield_pct=aaa_yield_pct,
        g_stage1_pct=g_cagr_pct
    )
    assert converged is True, f"expected converged=True for round-trip, got {converged}"
    assert implied_growth is not None, "expected numeric implied_growth, got None"
    assert abs(implied_growth - g_cagr_pct) < 0.1, (
        f"round-trip failed: input g={g_cagr_pct}, implied={implied_growth}"
    )


def test_dcf_reverse_converged_returns_float_and_true():
    """Standard fixture: should find a root and return (float, True)."""
    implied_growth, converged = _compute_dcf_reverse(
        price=80.0, eps=5.0, aaa_yield_pct=5.0, g_stage1_pct=8.0
    )
    assert converged is True, f"expected converged=True, got {converged}"
    assert isinstance(implied_growth, float), f"expected float, got {type(implied_growth)}"


def test_dcf_reverse_no_root_returns_none_false():
    """
    For an extreme price with no sign change in the bracket [-50,100],
    _compute_dcf_reverse must return (None, False) -- never a numeric default.
    Use price=1,000,000 (astronomically expensive; even at 100% growth DCF won't match).
    """
    implied_growth, converged = _compute_dcf_reverse(
        price=1_000_000.0, eps=0.01, aaa_yield_pct=5.0, g_stage1_pct=8.0
    )
    assert converged is False, f"expected converged=False for no-root case, got {converged}"
    assert implied_growth is None, (
        f"expected None implied_growth for no-root case, got {implied_growth}"
    )


def test_dcf_reverse_none_false_when_eps_none():
    """eps=None -> (None, False)."""
    implied_growth, converged = _compute_dcf_reverse(
        price=80.0, eps=None, aaa_yield_pct=5.0, g_stage1_pct=8.0
    )
    assert implied_growth is None
    assert converged is False


def test_dcf_reverse_none_false_when_eps_zero():
    """eps=0 -> (None, False)."""
    implied_growth, converged = _compute_dcf_reverse(
        price=80.0, eps=0.0, aaa_yield_pct=5.0, g_stage1_pct=8.0
    )
    assert implied_growth is None
    assert converged is False


def test_dcf_reverse_implied_growth_is_rounded():
    """Returned implied_growth should be rounded to 2 decimal places."""
    implied_growth, converged = _compute_dcf_reverse(
        price=80.0, eps=5.0, aaa_yield_pct=5.0, g_stage1_pct=8.0
    )
    if converged and implied_growth is not None:
        # Check it's been rounded: str(x) should not have more than 2 decimal places
        parts = str(implied_growth).split(".")
        if len(parts) == 2:
            assert len(parts[1]) <= 2, f"expected max 2 decimal places, got {implied_growth}"


# ── test runner ──────────────────────────────────────────────────────────────

def run_all():
    tests = [
        # _compute_dcf_forward
        test_dcf_forward_returns_finite_intrinsic_and_discount,
        test_dcf_forward_matches_reference_implementation,
        test_dcf_forward_cheap_stock_positive_discount,
        test_dcf_forward_expensive_stock_negative_discount,
        test_dcf_forward_none_none_when_eps_none,
        test_dcf_forward_none_none_when_eps_zero,
        test_dcf_forward_none_none_when_eps_negative,
        test_dcf_forward_raises_when_terminal_growth_gte_wacc,
        test_dcf_growth_floor_constant_is_sane,
        test_dcf_forward_growth_floor_prevents_sign_flip,
        # _compute_dcf_reverse
        test_dcf_reverse_round_trip,
        test_dcf_reverse_converged_returns_float_and_true,
        test_dcf_reverse_no_root_returns_none_false,
        test_dcf_reverse_none_false_when_eps_none,
        test_dcf_reverse_none_false_when_eps_zero,
        test_dcf_reverse_implied_growth_is_rounded,
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
