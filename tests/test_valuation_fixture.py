"""
KO (Coca-Cola) Hand-Verified Valuation Fixture
================================================
Formula-regression test for lynch_metrics() and graham_metrics().

PURPOSE: Guard against accidental formula changes.  Every assert in this
file was hand-computed from the inputs below — NOT by calling the code and
recording whatever it produced.  If the code changes in a way that breaks
these asserts, that IS the bug-detection mechanism working correctly.

INPUTS: Fixed, documented snapshot values — NOT live data.
  These represent reasonable KO-like inputs chosen for clarity.
  Live field-name and coverage confirmation happens automatically on the
  next GitHub Actions run (per Phase 5 Plan 01 offline execution decision).

FORMULA SOURCES (as implemented in stock_screener.py):
  Lynch:  FV_GplusD = eps * (g + dy)
          Lynch_BuyPrice = FV_GplusD * LYNCH_DISCOUNT[cat]  (Slow=0.75)
          Lynch_Discount_Pct = (1 - price / Lynch_BuyPrice) * 100
  Graham: VA = eps * (8.5 + 2*g_capped) * 4.4 / aaa_yield
          VB = eps * (7 + g_capped) * 4.4 / aaa_yield   [conservative variant]
          FV = min(VA, VB)
          Graham_Discount_Pct = (1 - price / FV) * 100

HOW TO RUN:
    python tests/test_valuation_fixture.py

No pytest required — uses only stdlib assert.
"""

import os
import sys
# Allow offline / CI execution without real API keys.
# These sentinel values are never used for network calls in this test.
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")

# Ensure stock_screener.py is importable when running from any cwd.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from stock_screener import lynch_metrics, graham_metrics

# ─────────────────────────────────────────────────────────────────────────────
# FIXED INPUT SNAPSHOT
# Values chosen to be round numbers that are easy to hand-verify.
# KO-like: modest grower, dividend payer, quality franchise trading at premium.
# ─────────────────────────────────────────────────────────────────────────────
KO_INPUTS = {
    "price":     70.00,   # fixed snapshot price
    "eps":        2.50,   # TTM EPS
    "g":          7.0,    # 5Y EPS CAGR % — g < 10 → Lynch_Category "Slow"
    "dy":         3.0,    # dividend yield %
    "aaa_yield":  5.5,    # FRED AAA corporate bond yield %
    "pb":        10.0,    # price-to-book ratio
}

# ─────────────────────────────────────────────────────────────────────────────
# HAND-COMPUTED EXPECTED VALUES
# Computed by hand below; see working shown in comments.
# ─────────────────────────────────────────────────────────────────────────────
#
# LYNCH hand computation:
#   pe            = 70.00 / 2.50             = 28.0
#   g + dy        = 7.0 + 3.0               = 10.0
#   FV_GplusD     = 2.50 * 10.0             = 25.00
#   Lynch_Category: g=7 < 10                → "Slow"
#   Lynch_BuyPrice = 25.00 * 0.75           = 18.75
#   Lynch_Discount_Pct = (1 - 70/18.75)*100 = (1 - 3.7333)*100 = -273.3%
#   LV_Ratio      = 70.00 / 25.00           = 2.8  → > 1.3 → "Avoid"
#
# GRAHAM hand computation:
#   g_capped      = min(7.0, 15.0)          = 7.0
#   Graham_VA     = 2.50 * (8.5 + 14) * (4.4/5.5)
#                 = 2.50 * 22.5 * 0.8
#                 = 2.50 * 18.0             = 45.00
#   Graham_VB     = 2.50 * (7 + 7) * (4.4/5.5)
#                 = 2.50 * 14.0 * 0.8
#                 = 2.50 * 11.2             = 28.00
#   Graham_FV     = min(45.00, 28.00)       = 28.00
#   Graham_Discount_Pct = (1 - 70/28)*100  = (1 - 2.5)*100 = -150.0%
#   Graham_Status: 70 > 0.95*28=26.6       → "Avoid"
# ─────────────────────────────────────────────────────────────────────────────
KO_EXPECTED = {
    # Lynch outputs
    "Lynch_Category":     "Slow",
    "Lynch_BuyPrice":     18.75,    # hand-computed: 25.00 * 0.75
    "Lynch_Discount_Pct": -273.3,   # hand-computed; tolerance ±10
    "Lynch_Status":       "Avoid",

    # Graham outputs
    "Graham_VA":          45.00,    # hand-computed; tolerance ±1.0
    "Graham_VB":          28.00,    # hand-computed; tolerance ±1.0
    "Graham_FV":          28.00,    # min(VA, VB) = VB (more conservative)
    "Graham_Discount_Pct": -150.0,  # hand-computed; tolerance ±5
    "Graham_Status":      "Avoid",
}

# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE ASSERTIONS
# ─────────────────────────────────────────────────────────────────────────────

def run_fixture():
    p   = KO_INPUTS["price"]
    eps = KO_INPUTS["eps"]
    g   = KO_INPUTS["g"]
    dy  = KO_INPUTS["dy"]
    aaa = KO_INPUTS["aaa_yield"]
    pb  = KO_INPUTS["pb"]

    lm = lynch_metrics(p, eps, g, dy)
    gm = graham_metrics(p, eps, g, aaa, pb)

    # ── Lynch checks ─────────────────────────────────────────────────
    assert lm.get("Lynch_Category") == KO_EXPECTED["Lynch_Category"], (
        f"Lynch_Category: expected {KO_EXPECTED['Lynch_Category']!r}, "
        f"got {lm.get('Lynch_Category')!r}"
    )

    bp = lm.get("Lynch_BuyPrice")
    assert bp is not None, "Lynch_BuyPrice is None — formula returned no value"
    assert abs(bp - KO_EXPECTED["Lynch_BuyPrice"]) <= 0.50, (
        f"Lynch_BuyPrice: expected {KO_EXPECTED['Lynch_BuyPrice']} ± 0.50, "
        f"got {bp}"
    )

    ld = lm.get("Lynch_Discount_Pct")
    assert ld is not None, "Lynch_Discount_Pct is None — formula returned no value"
    assert abs(ld - KO_EXPECTED["Lynch_Discount_Pct"]) <= 10.0, (
        f"Lynch_Discount_Pct: expected {KO_EXPECTED['Lynch_Discount_Pct']} ± 10, "
        f"got {ld}"
    )

    assert lm.get("Lynch_Status") == KO_EXPECTED["Lynch_Status"], (
        f"Lynch_Status: expected {KO_EXPECTED['Lynch_Status']!r}, "
        f"got {lm.get('Lynch_Status')!r}"
    )

    # ── Graham checks ────────────────────────────────────────────────
    va = gm.get("Graham_VA")
    assert va is not None, "Graham_VA is None — formula returned no value"
    assert abs(va - KO_EXPECTED["Graham_VA"]) <= 1.0, (
        f"Graham_VA: expected {KO_EXPECTED['Graham_VA']} ± 1.0, got {va}"
    )

    vb = gm.get("Graham_VB")
    assert vb is not None, "Graham_VB is None — formula returned no value"
    assert abs(vb - KO_EXPECTED["Graham_VB"]) <= 1.0, (
        f"Graham_VB: expected {KO_EXPECTED['Graham_VB']} ± 1.0, got {vb}"
    )

    fv = gm.get("Graham_FV")
    assert fv is not None, "Graham_FV is None — formula returned no value"
    assert abs(fv - KO_EXPECTED["Graham_FV"]) <= 1.0, (
        f"Graham_FV: expected {KO_EXPECTED['Graham_FV']} ± 1.0, got {fv}"
    )

    gd = gm.get("Graham_Discount_Pct")
    assert gd is not None, "Graham_Discount_Pct is None — formula returned no value"
    assert abs(gd - KO_EXPECTED["Graham_Discount_Pct"]) <= 5.0, (
        f"Graham_Discount_Pct: expected {KO_EXPECTED['Graham_Discount_Pct']} ± 5, "
        f"got {gd}"
    )

    assert gm.get("Graham_Status") == KO_EXPECTED["Graham_Status"], (
        f"Graham_Status: expected {KO_EXPECTED['Graham_Status']!r}, "
        f"got {gm.get('Graham_Status')!r}"
    )

    print("OK — all KO fixture assertions passed")
    print(f"  Lynch_BuyPrice      = {bp}  (expected {KO_EXPECTED['Lynch_BuyPrice']})")
    print(f"  Lynch_Discount_Pct  = {ld}  (expected {KO_EXPECTED['Lynch_Discount_Pct']})")
    print(f"  Graham_VA           = {va}  (expected {KO_EXPECTED['Graham_VA']})")
    print(f"  Graham_VB           = {vb}  (expected {KO_EXPECTED['Graham_VB']})")
    print(f"  Graham_FV           = {fv}  (expected {KO_EXPECTED['Graham_FV']})")
    print(f"  Graham_Discount_Pct = {gd}  (expected {KO_EXPECTED['Graham_Discount_Pct']})")


if __name__ == "__main__":
    run_fixture()
