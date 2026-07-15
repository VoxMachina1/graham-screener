"""
Lynch & Graham Stock Screener
==============================
Fetches S&P 500, Dow 30, and Nasdaq-100 constituents dynamically,
pulls fundamentals from yfinance and Finnhub, computes Lynch and
Graham valuation metrics, and writes results to docs/data/results.json
for GitHub Pages.

Local setup:
    1. Copy .env.example to .env and fill in your API keys.
    2. Run: python stock_screener.py

GitHub Actions setup:
    Add each variable from .env.example as a repository secret
    (Settings → Secrets and variables → Actions).
    The provided workflow file handles injection automatically.
"""

import os
import json
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from fredapi import Fred
from dotenv import load_dotenv
from scipy.optimize import brentq

# Load .env when running locally; no-op in GitHub Actions (env vars already set)
load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURATION — all values come from env vars
# ─────────────────────────────────────────────
FRED_API_KEY     = os.environ.get("FRED_API_KEY")
FINNHUB_API_KEY  = os.environ.get("FINNHUB_API_KEY")

# Screener parameters
GROWTH_CAP          = 25.0   # cap 'g' at this % to prevent distortion
GROWTH_FINNHUB_FLOOR = -100.0  # below this, Finnhub epsGrowth5Y is impossible (EPS can't fall >100% from positive base) — treat as bad data, not real growth
GRAHAM_NO_GROWTH_PE = 8.5    # classic Graham baseline P/E; change to 7 for conservative
GRAHAM_HIST_AAA     = 4.4    # Graham's original historical AAA yield constant
FRED_AAA_SERIES     = "AAA"  # Moody's AAA corporate bond yield series on FRED
FRED_RISK_FREE_SERIES = "DGS10"  # 10-year Treasury constant maturity rate

# Graham defensive-investor filter thresholds
MIN_MARKET_CAP_B    = 2.0    # minimum market cap in $B
MIN_CURRENT_RATIO   = 2.0    # current assets / current liabilities
MAX_DEBT_EQUITY     = 1.0    # long-term debt / equity
MIN_POSITIVE_EPS_YRS = 8     # out of last 10 fiscal years
MIN_DIV_YEARS       = 5      # paid dividend in at least N of last 10 years
MIN_EPS_GROWTH_10Y  = 33.0   # cumulative % EPS growth over 10 years (~3%/yr)
MAX_PE_GRAHAM       = 15.0   # P/E ≤ 15 (based on 3-yr avg EPS)
MAX_PB_GRAHAM       = 1.5    # P/B ≤ 1.5
MAX_PE_X_PB         = 22.5   # P/E × P/B ≤ 22.5
DEFENSIVE_PASS_SCORE = 6     # minimum score to be "Pass"
DEFENSIVE_BORDER_SCORE = 4   # minimum score to be "Borderline" (below = Fail)

# Lynch price-band multipliers
LYNCH_PEG_CHEAP     = 0.7
LYNCH_PEG_FAIR      = 1.0
LYNCH_PEGY_CHEAP    = 0.8
LYNCH_PEGY_FAIR     = 1.2
LYNCH_LV_STRONG_BUY = 0.7
LYNCH_LV_BUY        = 1.0
LYNCH_LV_HOLD       = 1.3

# Graham price-band multipliers (fraction of fair value)
GRAHAM_DEEP_BUY     = 0.60
GRAHAM_BUY          = 0.80
GRAHAM_WATCH        = 0.95

# Category-specific Lynch buy discount factors
LYNCH_DISCOUNT = {"Slow": 0.75, "Stalwart": 0.80, "Fast": 0.70}

# Sentinel discount for tickers with negative/zero growth or EPS that breaks
# the Lynch/Graham formulas.  Plan 02's scorer maps this to sub-score 0 (worst).
# The stock is RETAINED in the output and ranks at the bottom — it is NOT dropped.
# Distinct from a genuine no-price/no-EPS fetch failure, which early-returns as Error.
WORST_DISCOUNT = -999.0

# ─────────────────────────────────────────────────────────────────────────────
# SCORING ENGINE CONFIG — SCORE_* / TRAP_* / PILLAR_WEIGHTS
#
# All weights, band thresholds, and winsorization bounds live here as
# version-controlled loud constants (D-02b).  THESE HAVE NO EMPIRICAL ANCHOR
# YET — they are first-pass estimates.  Distribution monitoring is planned for
# stats.html (Phase 7); expect tuning after real production runs.
#
# Rate-relativized thresholds (discount bands): scaled by live AAA yield /
# SCORE_AAA_REFERENCE at runtime so a 15% discount is less impressive in a high-rate
# environment (SCORE-06).
# ─────────────────────────────────────────────────────────────────────────────

# Graham's 1963 AAA reference yield — used to rate-relativize discount thresholds.
SCORE_AAA_REFERENCE  = 4.4     # % — Graham's original 1963 reference; DO NOT CHANGE

# ── Value pillar: discount winsorization + bands ──────────────────────────
# Winsorize both Lynch and Graham discounts before piecewise scoring.
# Below -100%: extreme premium (stock at 2× fair value) — floor here.
# Above  60%:  extreme discount — cap here (matches legacy CombinedScore clip).
SCORE_DISC_WIN_LO    = -100.0  # floor discount at -100% (2× fair value)
SCORE_DISC_WIN_HI    =   60.0  # cap   discount at  60% (deep value)

# Piecewise bands: (raw_lo, raw_hi, score_lo, score_hi).
# Assumed at AAA = 4.4%; scaled by aaa_yield/SCORE_AAA_REFERENCE at runtime.
# Negative discount (stock above buy price) → low-but-nonzero score; the
# Lynch/Graham framework already signals "Avoid" — discount adds texture, not a veto.
SCORE_DISC_BANDS     = [       # [ASSUMED] — no empirical anchor; monitor in Phase 7
    (-100.0,  -30.0,   0,  10),  # very expensive
    ( -30.0,    0.0,  10,  40),  # modestly expensive
    (   0.0,   15.0,  40,  70),  # near or at buy target
    (  15.0,   30.0,  70,  90),  # significantly cheap
    (  30.0,   60.0,  90, 100),  # deep value territory
]

# ── Quality pillar: DefensiveScore bands ─────────────────────────────────
# DefensiveScore ranges 0–8 (one point per Graham criterion passed).
SCORE_DEF_BANDS      = [       # [ASSUMED] — no empirical anchor; monitor in Phase 7
    (0, 2,   0,  20),
    (2, 4,  20,  50),
    (4, 6,  50,  80),
    (6, 8,  80, 100),
]

# ── Quality pillar: Debt/Equity bands ─────────────────────────────────────
# Lower D/E = better; bands map raw D/E → [0, 100] inverted.
# Negative D/E (negative equity) → D-01 worst-score path, NOT winsorize path.
SCORE_DE_WIN_HI      =   5.0   # cap D/E at 5.0 (extreme leverage)
SCORE_DE_BANDS       = [       # [ASSUMED] — no empirical anchor; monitor in Phase 7
    (0.0, 0.5, 100,  90),  # minimal debt
    (0.5, 1.0,  90,  70),  # moderate leverage
    (1.0, 2.0,  70,  40),  # elevated leverage
    (2.0, 5.0,  40,   0),  # high leverage
]

# ── Quality pillar: Current Ratio bands ──────────────────────────────────
SCORE_CR_WIN_HI      =   8.0   # cap current ratio at 8.0 (hoarding threshold)
SCORE_CR_BANDS       = [       # [ASSUMED] — no empirical anchor; monitor in Phase 7
    (0.0, 1.0,   0,  30),  # technically illiquid
    (1.0, 1.5,  30,  60),
    (1.5, 2.0,  60,  80),
    (2.0, 4.0,  80, 100),
    (4.0, 8.0, 100,  90),  # above 4 fine; above 8 may signal hoarding
]

# ── Growth pillar: Growth level bands ────────────────────────────────────
# g is already GROWTH_CAP-capped at 25%.  Non-positive g → D-01 worst = 0.
SCORE_G_BANDS        = [       # [ASSUMED] — no empirical anchor; monitor in Phase 7
    ( 0.0,  3.0,   0,  20),  # near-zero / slow
    ( 3.0,  7.0,  20,  50),  # slow grower
    ( 7.0, 12.0,  50,  75),  # moderate grower
    (12.0, 20.0,  75,  90),
    (20.0, 25.0,  90, 100),
]

# ── Growth pillar: Growth stability bands ─────────────────────────────────
# Derived from annual_eps history: fraction of years with positive EPS.
# Range: 0.0–1.0.  None when fewer than 3 years available (D-01b).
SCORE_GSTAB_BANDS    = [       # [ASSUMED] — no empirical anchor; monitor in Phase 7
    (0.0, 0.4,   0,  20),
    (0.4, 0.6,  20,  50),
    (0.6, 0.8,  50,  80),
    (0.8, 1.0,  80, 100),
]

# ── Safety pillar: Trap gate result ──────────────────────────────────────
# Tripped gate → floors Safety to 0 (D-03 worst-possible, consistent with D-01).
# Non-tripped with full coverage → interim baseline 60 ("not a trap" is positive
# but Altman/Piotroski will provide real granularity in Phase 7).
# Non-tripped with partial coverage → baseline * coverage_fraction (D-01b).
SCORE_SAFETY_TRAP_PENALTY = 0   # Safety floor when trap is tripped (D-03)
SCORE_SAFETY_NOTRAP_BASE  = 60  # Interim baseline for non-trapped rows

# ── Trap gate thresholds (TRAP-01 / D-04) ────────────────────────────────
# Distress-level thresholds — deliberately more lenient than the Graham
# defensive-investor criteria above (this gate is an interim trip-wire, not
# a full safety analysis).
TRAP_MAX_DE   = 2.0   # D/E above this trips the gate
TRAP_MIN_CR   = 1.0   # current ratio below this trips the gate
# EPS_Stability == 0  → trips gate (no positive EPS in recent history)
# fcf_per_share < 0   → trips gate (negative free cash flow)

# ── Value sub-group 2: cash/earnings-yield cheapness ─────────────────────
# Higher yield = better for all three; ascending bands.
# Negative inputs are routed to worst sub-score before reaching winsorize.

# FCF yield (FCF / market_cap, expressed as %)
SCORE_FCF_YIELD_WIN_LO  =  0.0   # floor: negatives handled via D-01 before winsorize
SCORE_FCF_YIELD_WIN_HI  = 15.0   # cap extreme FCF yields
SCORE_FCF_YIELD_BANDS   = [      # [ASSUMED] — monitor in Phase 7
    ( 0.0,  2.0,   0,  20),      # thin FCF yield
    ( 2.0,  5.0,  20,  60),      # moderate
    ( 5.0,  8.0,  60,  85),      # solid
    ( 8.0, 15.0,  85, 100),      # high FCF yield
]

# Earnings yield (EBIT / EV, expressed as %)
# Negative earnings yield → D-01 worst-score.
SCORE_EARN_YIELD_WIN_LO =  0.0
SCORE_EARN_YIELD_WIN_HI = 20.0
SCORE_EARN_YIELD_BANDS  = [      # [ASSUMED] — monitor in Phase 7
    ( 0.0,  3.0,   0,  20),
    ( 3.0,  6.0,  20,  50),
    ( 6.0, 10.0,  50,  80),
    (10.0, 20.0,  80, 100),
]

# Shareholder yield (div yield + buyback yield, expressed as %)
# Zero/negative → D-01 worst-score.
SCORE_SH_YIELD_WIN_LO   =  0.0
SCORE_SH_YIELD_WIN_HI   = 12.0
SCORE_SH_YIELD_BANDS    = [      # [ASSUMED] — monitor in Phase 7
    (0.0,  2.0,   0,  30),
    (2.0,  4.0,  30,  60),
    (4.0,  6.0,  60,  85),
    (6.0, 12.0,  85, 100),
]

# ── Value sub-group 3: price-position (D-04) ─────────────────────────────

# dist_52w_low: % the current price is above the 52-week low.
# 0% = AT the low (maximum contrarian signal = 100 score). Higher % = bounced; score falls.
# descending: nearer-low scores higher — score_lo > score_hi encodes inversion (no _piecewise_score invert path)
SCORE_DIST_52W_LOW_WIN_LO =   0.0
SCORE_DIST_52W_LOW_WIN_HI = 200.0
SCORE_DIST_52W_LOW_BANDS  = [      # [ASSUMED] — descending: near low = 100; monitor in Phase 7
    (  0.0,  10.0, 100,  85),      # within 10% of 52w low — very contrarian
    ( 10.0,  30.0,  85,  55),
    ( 30.0,  60.0,  55,  25),
    ( 60.0, 200.0,  25,   0),
]

# dist_52w_high: % the current price is below the 52-week high.
# Higher = more below high = deeper price discount = better. Ascending.
SCORE_DIST_52W_HIGH_WIN_LO =   0.0
SCORE_DIST_52W_HIGH_WIN_HI = 100.0
SCORE_DIST_52W_HIGH_BANDS  = [     # [ASSUMED] — ascending: far from high = 100; monitor in Phase 7
    ( 0.0,  5.0,   0,  10),        # within 5% of high — near peak
    ( 5.0, 20.0,  10,  50),
    (20.0, 40.0,  50,  80),
    (40.0,100.0,  80, 100),
]

# dist_5y_low: % the current price is above the 5-year low.
# Same directional logic as dist_52w_low; wider range.
# descending: nearer-low scores higher — score_lo > score_hi encodes inversion (no _piecewise_score invert path)
SCORE_DIST_5Y_LOW_WIN_LO =    0.0
SCORE_DIST_5Y_LOW_WIN_HI =  400.0
SCORE_DIST_5Y_LOW_BANDS  = [       # [ASSUMED] — descending: near 5y low = 100; monitor in Phase 7
    (  0.0,  20.0, 100,  85),
    ( 20.0,  60.0,  85,  55),
    ( 60.0, 120.0,  55,  25),
    (120.0, 400.0,  25,   0),
]

# Recency multiplier constants for dist_52w_low and dist_5y_low sub-scores.
# weeks=0: multiplier = SCORE_RECENCY_FLOOR (very fresh low; may still be falling)
# weeks>=SCORE_RECENCY_FULL_WK: multiplier = 1.0 (basing; full contrarian credit)
SCORE_RECENCY_FLOOR   = 0.70   # [ASSUMED]
SCORE_RECENCY_FULL_WK = 26     # weeks at which full credit is granted [ASSUMED]

# ── Quality pillar: ROIC ─────────────────────────────────────────────────
# Negative ROIC → D-01 worst-score (capital-destroying).
SCORE_ROIC_WIN_LO =   0.0
SCORE_ROIC_WIN_HI =  50.0   # cap extreme ROIC (asset-light outliers)
SCORE_ROIC_BANDS  = [        # [ASSUMED] — monitor in Phase 7
    ( 0.0,  5.0,   0,  20),  # low/poor capital returns
    ( 5.0, 10.0,  20,  50),
    (10.0, 20.0,  50,  85),
    (20.0, 50.0,  85, 100),
]

# ── Pillar weights ────────────────────────────────────────────────────────
# ~35/30/20/15 (Value/Quality/Growth/Safety) per D-02.
# Weights are renormalized over present pillars at runtime (avg-over-present).
PILLAR_WEIGHTS = {
    "value":   0.35,
    "quality": 0.30,
    "growth":  0.20,
    "safety":  0.15,
}

# ── Safety pillar: Piotroski F-Score bands ───────────────────────────────────
# [ASSUMED] — no empirical anchor; monitor distribution in stats.html (Phase 7)
SCORE_PIOTROSKI_BANDS = [
    (0, 2,   0,  20),   # distressed
    (2, 4,  20,  40),   # weak
    (4, 6,  40,  65),   # average
    (6, 8,  65,  85),   # strong
    (8, 9,  85, 100),   # very strong (9/9 rare)
]

# ── Safety pillar: Altman Z'' bands ──────────────────────────────────────────
SCORE_ALTMAN_DISTRESS = 1.1    # [ASSUMED] Z'' below this = distress zone
SCORE_ALTMAN_SAFE     = 2.6    # [ASSUMED] Z'' above this = safe zone
SCORE_ALTMAN_BANDS = [         # [ASSUMED] — no empirical anchor; monitor in Phase 7
    (-999.0,  1.1,   0,   0),  # distress zone (flat at 0)
    (   1.1,  2.6,   0,  70),  # grey zone (interpolated)
    (   2.6, 10.0,  70, 100),  # safe zone
]

# ── DCF config ────────────────────────────────────────────────────────────────
DCF_ERP                 = 5.5   # [ASSUMED] mature-market equity risk premium %
DCF_TERMINAL_GROWTH_CAP = 3.0   # [ASSUMED] maximum perpetual nominal growth %
DCF_FORECAST_YEARS      = 5
DCF_INITIAL_GROWTH_FLOOR = -20.0
DCF_INITIAL_GROWTH_CAP   = 15.0
DCF_DEFAULT_TAX_RATE     = 0.21
DCF_BETA_FLOOR           = 0.50
DCF_BETA_CAP             = 2.00
DCF_SENSITIVITY_WACC_STEP = 0.01
DCF_SENSITIVITY_GROWTH_STEP = 0.005
DCF_MIN_WACC_RISK_FREE_SPREAD_PCT = 2.5
DCF_MIN_WACC_TERMINAL_SPREAD_PCT = 4.0
DCF_HIGH_TERMINAL_VALUE_PCT = 85.0
DCF_HIGH_DEBT_WEIGHT = 0.50
DCF_EXCLUDED_SECTORS    = {"Financial Services", "Real Estate"}
ALTMAN_EXCLUDED_SECTORS = {"Financial Services"}
# [ASSUMED] Lower bound on the reconciled growth g before it reaches the DCF
# helpers. No empirical anchor; -50% matches the reverse-DCF search lower
# bound used by the legacy discounted-earnings diagnostic. Floors distressed-EPS
# growth so (1+g) stays positive; forward and reverse DCF share this bound.
# Calibrate in a later tuning phase.
DCF_GROWTH_FLOOR = -50.0
# yfinance GICS sector strings for the cyclical group D-10 requires flagging.
# NOTE: yfinance returns "Basic Materials", not "Materials".
CYCLICAL_SECTORS = {"Energy", "Basic Materials"}


def _sector_allows(fund: dict, metric: str) -> bool:
    """
    Sector applicability gate (SECTOR-02 / D-10 / D-11).

    Returns False when the ticker's sector excludes `metric`, so the caller
    substitutes None (never zero) for that metric. `metric` is one of
    "dcf", "altman", "earnings_yield", "ev_ebit". sector=None/"" means
    "sector unknown, no exclusion applied" — intentional (RESEARCH.md Pitfall 7).
    internal — for tests only.
    """
    sector = fund.get("sector") or ""
    if metric == "dcf" and sector in DCF_EXCLUDED_SECTORS:
        return False
    if metric == "altman" and sector in ALTMAN_EXCLUDED_SECTORS:
        return False
    if metric in ("earnings_yield", "ev_ebit") and sector == "Financial Services":
        return False
    return True


# ── Value sub-group 4: DCF discount ──────────────────────────────────────────
# DCF discount % = (1 - price/intrinsic) * 100; positive = cheap.
# Negative discount (overpriced) → D-01 worst-score path before winsorize.
SCORE_DCF_DISCOUNT_WIN_LO = -100.0   # [ASSUMED] floor: negatives via D-01 before winsorize
SCORE_DCF_DISCOUNT_WIN_HI =   60.0   # [ASSUMED] cap extreme DCF discounts
SCORE_DCF_DISCOUNT_BANDS  = [        # [ASSUMED] — ascending; monitor in Phase 7
    (-100.0, -30.0,   0,  10),       # deeply overpriced by DCF
    ( -30.0,   0.0,  10,  40),       # modestly overpriced
    (   0.0,  15.0,  40,  70),       # near fair value
    (  15.0,  30.0,  70,  90),       # meaningful DCF discount
    (  30.0,  60.0,  90, 100),       # deep DCF value
]

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)


# ═════════════════════════════════════════════
# STEP — SCORING ENGINE (pure helpers + trap gate)
# ═════════════════════════════════════════════
# All functions here are pure: numeric inputs → numeric outputs, no I/O or
# side effects.  They can be imported and tested without any API keys.


def _piecewise_score(value: float, bands: list) -> float:
    """
    Map a raw metric value to [0, 100] via linear interpolation between breakpoints.

    bands: list of (raw_lo, raw_hi, score_lo, score_hi) tuples, sorted ascending
           by raw_lo.

    Behaviour:
      - value below the first band  → score_lo of the first band (typically 0).
      - value above the last band   → score_hi of the last band (typically 100).
      - value inside a band         → linearly interpolated; t clamped to [0, 1].
    """
    for (raw_lo, raw_hi, score_lo, score_hi) in bands:
        if value <= raw_hi:
            if raw_hi == raw_lo:
                return float(score_lo)
            t = (value - raw_lo) / (raw_hi - raw_lo)
            t = max(0.0, min(1.0, t))
            return score_lo + t * (score_hi - score_lo)
    # Above all bands → score_hi of last band
    return float(bands[-1][3])


def _winsorize(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi] — both-tail winsorization (SCORE-03)."""
    return max(lo, min(hi, value))


def _avg_present(values: list) -> float | None:
    """
    Average over non-None values.  Returns None when all inputs are absent (D-01b).
    Used at both the sub-group level (within a pillar) and the pillar level.
    """
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None


def _recency_multiplier(weeks_since_low: float | None) -> float:
    """internal — for tests only. Linear ramp SCORE_RECENCY_FLOOR->1.0 over SCORE_RECENCY_FULL_WK weeks."""
    if weeks_since_low is None:
        return 1.0
    t = min(1.0, weeks_since_low / SCORE_RECENCY_FULL_WK)
    return SCORE_RECENCY_FLOOR + t * (1.0 - SCORE_RECENCY_FLOOR)


def _trap_reasons(
    debt_equity: float | None,
    current_ratio: float | None,
    eps_stability: int | None,
    fcf_per_share: float | None,
) -> list:
    """Return explicit research warnings for each present threshold breach."""
    reasons = []
    if debt_equity is not None and debt_equity > TRAP_MAX_DE:
        reasons.append("High leverage")
    if current_ratio is not None and current_ratio < TRAP_MIN_CR:
        reasons.append("Weak liquidity")
    if eps_stability is not None and eps_stability == 0:
        reasons.append("Unstable earnings")
    if fcf_per_share is not None and fcf_per_share < 0:
        reasons.append("Negative FCF")
    return reasons


def trap_gate(
    debt_equity: float | None,
    current_ratio: float | None,
    eps_stability: int | None,
    fcf_per_share: float | None,
) -> tuple:
    """
    Interim value-trap gate (TRAP-01 / D-03 / D-04).

    Returns (is_trap: bool, coverage_fraction: float).

    is_trap is True if ANY *present* input trips its threshold:
      - debt/equity  > TRAP_MAX_DE   (excessive leverage)
      - current_ratio < TRAP_MIN_CR  (near-illiquid)
      - eps_stability == 0           (no positive EPS in recent history)
      - fcf_per_share < 0            (burning cash)

    coverage_fraction = count_present / 4.  A value of 0.0 means all inputs were
    None — the caller must treat Safety as "unknown", never "safe" (D-01b).

    Note: debt_equity and current_ratio deliberately feed both the Quality pillar
    (as graded sub-scores) and this Safety gate (at distress thresholds).  This is
    intentional per 05-CONTEXT.md D-02 — do not "clean up" the double-use.
    """
    checks = []
    if debt_equity is not None:
        checks.append(debt_equity > TRAP_MAX_DE)
    if current_ratio is not None:
        checks.append(current_ratio < TRAP_MIN_CR)
    if eps_stability is not None:
        checks.append(eps_stability == 0)
    if fcf_per_share is not None:
        checks.append(fcf_per_share < 0)

    is_trap = bool(_trap_reasons(
        debt_equity, current_ratio, eps_stability, fcf_per_share
    ))
    coverage_fraction = len(checks) / 4  # 4 possible gate inputs
    return is_trap, coverage_fraction


def overall_score(
    lynch_discount: float | None,
    graham_discount: float | None,
    defensive_score: float | None,
    debt_equity: float | None,
    current_ratio: float | None,
    growth_g: float | None,
    growth_stability: float | None,
    coverage_fraction: float,  # vestigial (WR-03): unused since the Phase 7 Safety-pillar
                                # rewrite dropped the trap-gate baseline it used to scale;
                                # kept only for call-site compatibility with trap_gate()'s
                                # return signature and existing test fixtures.
    aaa_yield: float,
    fcf_yield: float | None = None,
    earnings_yield: float | None = None,
    shareholder_yield: float | None = None,
    roic: float | None = None,
    dist_52w_low: float | None = None,
    dist_52w_high: float | None = None,
    dist_5y_low: float | None = None,
    weeks_since_52w_low: float | None = None,
    weeks_since_5y_low: float | None = None,
    piotroski_f: int | None = None,
    altman_z: float | None = None,
    dcf_discount_pct: float | None = None,
) -> dict:
    """
    Compute the 4-pillar absolute OverallScore (0–100) and return a breakdown dict.

    Returns:
        {
            "overall":      float | None,
            "value":        float | None,
            "quality":      float | None,
            "growth":       float | None,
            "safety":       float | None,
            "coverage_pct": float,         # 0–100 fraction of sub-scores present (17 leaves)
            "piotroski":    float,         # Safety sub-score (50.0 when absent — D-04)
            "altman":       float,         # Safety sub-score (50.0 when absent — D-04)
            "dcf_discount": float | None,  # Value sub-score (None when DCF absent)
            "value_dcf":    float | None,  # Value DCF sub-group
        }

    Pillar design (per 05-CONTEXT.md D-02, updated Phase 7):
      VALUE   = 4 equal sub-groups averaged:
                  1. discount  (Lynch + Graham)
                  2. yield     (FCF yield + earnings yield + shareholder yield)
                  3. price-pos (dist_52w_low * recency + dist_52w_high + dist_5y_low * recency)
                  4. dcf       (DCF discount % — None when absent, 0 when overpriced)
      QUALITY = DefensiveScore + debt/equity + current_ratio + ROIC
      GROWTH  = growth level (g) + growth_stability
      SAFETY  = Piotroski F-Score + Altman Z'' + defensive_score + debt/equity + current_ratio
                (Piotroski and Altman absent → D-04 neutral 50.0; others use D-01b avg-over-present)

    Intentional double-use: debt_equity and current_ratio appear in BOTH Quality
    (as graded sub-scores) and Safety (as distress-pillar inputs).  Per 05-CONTEXT.md
    this is deliberate — do not "clean up" the overlap.

    Input handling:
      D-01  — negative/present values (WORST_DISCOUNT, negative D/E, non-positive g,
              negative DCF discount) → sub-score 0 (worst), checked BEFORE winsorize.
      D-01b — genuinely None values → averaged over present within pillar.
      D-04  — Piotroski and Altman absent → 50.0 (neutral), NOT avg-over-present skip.
      D-02  — pillars renormalized over present pillars (avg-over-present at pillar level).
      D-06  — discount thresholds scaled by aaa_yield/SCORE_AAA_REFERENCE.
    """

    # ── VALUE PILLAR ──────────────────────────────────────────────────────────
    # Rate-relativization: scale discount band breakpoints by live/reference yield.
    # When AAA yield is high, a 15% discount is less impressive → thresholds scale up.
    rate_scale = aaa_yield / SCORE_AAA_REFERENCE if aaa_yield > 0 else 1.0

    def _scaled_disc_bands():
        """Return SCORE_DISC_BANDS with raw_lo/raw_hi scaled by the rate factor."""
        return [
            (lo * rate_scale, hi * rate_scale, s_lo, s_hi)
            for (lo, hi, s_lo, s_hi) in SCORE_DISC_BANDS
        ]

    def _score_discount(disc: float | None) -> float | None:
        """Map one discount value → sub-score 0–100 (D-01 + D-01b paths)."""
        if disc is None:
            return None  # D-01b: genuinely absent
        if disc <= WORST_DISCOUNT + 1.0:
            # D-01: sentinel value → worst sub-score 0 (checked before winsorize)
            return 0.0
        w = _winsorize(disc, SCORE_DISC_WIN_LO, SCORE_DISC_WIN_HI)
        return _piecewise_score(w, _scaled_disc_bands())

    lynch_sub   = _score_discount(lynch_discount)
    graham_sub  = _score_discount(graham_discount)
    # Sub-group 1: discount (Lynch + Graham averaged — SCORE-07 two-level structure)
    discount_group = _avg_present([lynch_sub, graham_sub])

    # Sub-group 2: yield (ascending; negative/zero → 0.0 before winsorize)
    def _score_yield(v, win_lo, win_hi, bands):
        if v is None:
            return None
        if v <= 0:
            return 0.0
        return _piecewise_score(_winsorize(v, win_lo, win_hi), bands)

    fcf_sub   = _score_yield(fcf_yield,         SCORE_FCF_YIELD_WIN_LO,  SCORE_FCF_YIELD_WIN_HI,  SCORE_FCF_YIELD_BANDS)
    earny_sub = _score_yield(earnings_yield,    SCORE_EARN_YIELD_WIN_LO, SCORE_EARN_YIELD_WIN_HI, SCORE_EARN_YIELD_BANDS)
    shy_sub   = _score_yield(shareholder_yield, SCORE_SH_YIELD_WIN_LO,   SCORE_SH_YIELD_WIN_HI,   SCORE_SH_YIELD_BANDS)
    yield_group = _avg_present([fcf_sub, earny_sub, shy_sub])

    # Sub-group 3: price-position (descending bands; low ones get recency multiplier)
    if dist_52w_low is None:
        s_52w_lo = None
    else:
        raw = _piecewise_score(_winsorize(dist_52w_low, SCORE_DIST_52W_LOW_WIN_LO, SCORE_DIST_52W_LOW_WIN_HI), SCORE_DIST_52W_LOW_BANDS)
        s_52w_lo = raw * _recency_multiplier(weeks_since_52w_low)

    if dist_52w_high is None:
        s_52w_hi = None
    else:
        s_52w_hi = _piecewise_score(_winsorize(dist_52w_high, SCORE_DIST_52W_HIGH_WIN_LO, SCORE_DIST_52W_HIGH_WIN_HI), SCORE_DIST_52W_HIGH_BANDS)

    if dist_5y_low is None:
        s_5y_lo = None
    else:
        raw = _piecewise_score(_winsorize(dist_5y_low, SCORE_DIST_5Y_LOW_WIN_LO, SCORE_DIST_5Y_LOW_WIN_HI), SCORE_DIST_5Y_LOW_BANDS)
        s_5y_lo = raw * _recency_multiplier(weeks_since_5y_low)

    price_group = _avg_present([s_52w_lo, s_52w_hi, s_5y_lo])

    # Sub-group 4: DCF discount (Value pillar — D-01 negative-routing per D-11)
    # Negative discount means stock trades ABOVE intrinsic → D-01 worst-score path.
    # None means DCF is absent (sector excluded or EPS <= 0) → avg-over-present skip.
    def _score_dcf_discount(d: float | None) -> float | None:
        if d is None:
            return None  # D-01b: absent → skip in avg-over-present
        if d < 0:
            return 0.0   # D-01: overpriced by DCF → worst score
        return _piecewise_score(
            _winsorize(d, SCORE_DCF_DISCOUNT_WIN_LO, SCORE_DCF_DISCOUNT_WIN_HI),
            SCORE_DCF_DISCOUNT_BANDS,
        )

    dcf_sub   = _score_dcf_discount(dcf_discount_pct)
    dcf_group = _avg_present([dcf_sub])

    score_value = _avg_present([discount_group, yield_group, price_group, dcf_group])

    # ── QUALITY PILLAR ────────────────────────────────────────────────────────
    def _score_defensive(ds: float | None) -> float | None:
        if ds is None:
            return None
        return _piecewise_score(_winsorize(ds, 0.0, 8.0), SCORE_DEF_BANDS)

    def _score_debt_equity(de: float | None) -> float | None:
        if de is None:
            return None
        if de < 0:
            # D-01: negative equity (negative D/E) → worst sub-score
            return 0.0
        return _piecewise_score(_winsorize(de, 0.0, SCORE_DE_WIN_HI), SCORE_DE_BANDS)

    def _score_current_ratio(cr: float | None) -> float | None:
        if cr is None:
            return None
        return _piecewise_score(_winsorize(cr, 0.0, SCORE_CR_WIN_HI), SCORE_CR_BANDS)

    def_sub   = _score_defensive(defensive_score)
    de_sub    = _score_debt_equity(debt_equity)
    cr_sub    = _score_current_ratio(current_ratio)

    if roic is None:
        roic_sub = None
    elif roic <= 0:
        roic_sub = 0.0
    else:
        roic_sub = _piecewise_score(_winsorize(roic, SCORE_ROIC_WIN_LO, SCORE_ROIC_WIN_HI), SCORE_ROIC_BANDS)

    score_quality = _avg_present([def_sub, de_sub, cr_sub, roic_sub])

    # ── GROWTH PILLAR ─────────────────────────────────────────────────────────
    def _score_growth_g(gg: float | None) -> float | None:
        if gg is None:
            return None
        if gg <= 0:
            # D-01: non-positive growth (present but terrible) → worst sub-score
            return 0.0
        return _piecewise_score(_winsorize(gg, 0.0, GROWTH_CAP), SCORE_G_BANDS)

    def _score_growth_stability(gs: float | None) -> float | None:
        if gs is None:
            return None
        return _piecewise_score(_winsorize(gs, 0.0, 1.0), SCORE_GSTAB_BANDS)

    growth_g_sub    = _score_growth_g(growth_g)
    growth_stab_sub = _score_growth_stability(growth_stability)
    score_growth    = _avg_present([growth_g_sub, growth_stab_sub])

    # ── SAFETY PILLAR (Phase 7 — TRAP-03 / D-04) ────────────────────────────
    # Piotroski F-Score and Altman Z'' are scored Safety sub-scores.
    # D-04: when absent (sector excluded or missing statements), each contributes
    # 50.0 (neutral) — NOT avg-over-present skip.  This prevents sector-excluded
    # stocks from inheriting artificially high Safety from the remaining inputs.
    # The defensive_score, debt_equity, current_ratio sub-scores retain D-01b
    # (avg-over-present) — they are double-used from the Quality pillar above.
    # Intentional double-use: def_sub/de_sub/cr_sub computed in Quality block.
    # Do NOT recompute — they feed both pillars by design.
    # SCORE_SAFETY_TRAP_PENALTY / SCORE_SAFETY_NOTRAP_BASE are retained as
    # constants but no longer drive the Safety calculation (deprecated — Phase 7).
    def _score_piotroski(f: int | None) -> float:
        """D-04: absent → neutral 50.0 (always returns float)."""
        if f is None:
            return 50.0
        return _piecewise_score(float(f), SCORE_PIOTROSKI_BANDS)

    def _score_altman(z: float | None) -> float:
        """D-04: absent → neutral 50.0 (always returns float)."""
        if z is None:
            return 50.0
        return _piecewise_score(_winsorize(z, -999.0, 10.0), SCORE_ALTMAN_BANDS)

    piotroski_sub = _score_piotroski(piotroski_f)
    altman_sub    = _score_altman(altman_z)
    # def_sub, de_sub, cr_sub are reused from the Quality block above (D-01b)
    score_safety = _avg_present([piotroski_sub, altman_sub, def_sub, de_sub, cr_sub])

    # ── OVERALL SCORE — weighted avg over present pillars (D-02) ─────────────
    pillars = {
        "value":   score_value,
        "quality": score_quality,
        "growth":  score_growth,
        "safety":  score_safety,
    }
    total_weight = 0.0
    weighted_sum = 0.0
    present_count = 0
    total_sub_scores = 0

    # Count all expected sub-scores for coverage_pct numerator/denominator (17 leaves)
    # Phase 7: removed score_safety aggregate leaf; added piotroski_sub, altman_sub,
    # dcf_sub.  Piotroski and Altman always return float (50.0 when absent) so they
    # are always "present" — but dcf_sub may be None and counts only when present.
    all_sub_scores = [
        lynch_sub, graham_sub,                          # Value: discount (2)
        fcf_sub, earny_sub, shy_sub,                    # Value: yield (3)
        s_52w_lo, s_52w_hi, s_5y_lo,                   # Value: price-position (3)
        dcf_sub,                                        # Value: DCF (1)
        def_sub, de_sub, cr_sub, roic_sub,              # Quality (4)
        growth_g_sub, growth_stab_sub,                  # Growth (2)
        piotroski_sub, altman_sub,                      # Safety (2) — always float per D-04
    ]  # total = 17 leaves
    present_sub_count = sum(1 for s in all_sub_scores if s is not None)
    total_sub_count   = len(all_sub_scores)

    for pillar_name, pillar_val in pillars.items():
        if pillar_val is not None:
            w = PILLAR_WEIGHTS[pillar_name]
            weighted_sum  += pillar_val * w
            total_weight  += w
            present_count += 1

    if total_weight > 0:
        overall = round(weighted_sum / total_weight, 2)
    else:
        overall = None

    coverage_pct = round(present_sub_count / total_sub_count * 100, 1) if total_sub_count > 0 else 0.0

    return {
        "overall":        overall,
        "value":          round(score_value,   2) if score_value   is not None else None,
        "quality":        round(score_quality, 2) if score_quality is not None else None,
        "growth":         round(score_growth,  2) if score_growth  is not None else None,
        "safety":         round(score_safety,  2) if score_safety  is not None else None,
        "coverage_pct":   coverage_pct,
        "value_discount": round(discount_group, 2) if discount_group is not None else None,
        "value_yield":    round(yield_group,    2) if yield_group    is not None else None,
        "value_price":    round(price_group,    2) if price_group    is not None else None,
        "value_dcf":      round(dcf_group,      2) if dcf_group      is not None else None,
        "piotroski":      round(piotroski_sub,  2),
        "altman":         round(altman_sub,     2),
        "dcf_discount":   round(dcf_sub,        2) if dcf_sub        is not None else None,
    }


# ═════════════════════════════════════════════
# STEP 1 — FETCH UNIVERSE
# ═════════════════════════════════════════════

# Wikipedia blocks requests that don't include a browser-like User-Agent.
# We fetch the HTML ourselves with requests, then pass it to pd.read_html().
WIKI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def _wiki_tables(url: str) -> list:
    """Fetch a Wikipedia page and return all HTML tables as a list of DataFrames."""
    from io import StringIO
    resp = requests.get(url, headers=WIKI_HEADERS, timeout=15)
    resp.raise_for_status()
    return pd.read_html(StringIO(resp.text))


def fetch_sp500() -> set:
    """Scrape current S&P 500 constituents from Wikipedia."""
    log.info("Fetching S&P 500 constituents from Wikipedia...")
    tables = _wiki_tables("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    tickers = set(tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist())
    log.info(f"  → {len(tickers)} S&P 500 tickers")
    return tickers


def fetch_dow30() -> set:
    """Scrape current Dow 30 constituents from Wikipedia."""
    log.info("Fetching Dow 30 constituents from Wikipedia...")
    tables = _wiki_tables("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average")
    for t in tables:
        if "Symbol" in t.columns:
            tickers = set(t["Symbol"].str.replace(".", "-", regex=False).tolist())
            log.info(f"  → {len(tickers)} Dow 30 tickers")
            return tickers
    raise ValueError("Could not find Dow 30 constituents table on Wikipedia.")


def fetch_nasdaq100() -> set:
    """Scrape current Nasdaq-100 constituents from Wikipedia."""
    log.info("Fetching Nasdaq-100 constituents from Wikipedia...")
    tables = _wiki_tables("https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies")
    for t in tables:
        if "Ticker" in t.columns:
            tickers = set(t["Ticker"].str.replace(".", "-", regex=False).tolist())
            log.info(f"  → {len(tickers)} Nasdaq-100 tickers")
            return tickers
    raise ValueError("Could not find Nasdaq-100 constituents table on Wikipedia.")


def _cached_index_members(index_name: str) -> set:
    """Return the last published members for one index, or an empty set."""
    results_path = Path("docs/data/results.json")
    try:
        payload = json.loads(results_path.read_text(encoding="utf-8"))
        members = {
            str(row.get("Ticker", "")).strip()
            for row in payload.get("rows", [])
            if index_name in {
                part.strip() for part in str(row.get("Indexes", "")).split(",")
            }
        }
        return {ticker for ticker in members if ticker}
    except (OSError, ValueError, TypeError):
        return set()


def _fetch_index_with_fallback(index_name: str, fetcher) -> set:
    """Fetch current members, falling back to the last published membership."""
    try:
        return fetcher()
    except Exception as exc:
        cached = _cached_index_members(index_name)
        if cached:
            log.warning(
                f"{index_name} live constituent fetch failed ({exc}); "
                f"using {len(cached)} cached members from the last published dataset"
            )
            return cached
        raise


def get_universe() -> pd.DataFrame:
    """Return a deduplicated DataFrame with columns: ticker, indexes."""
    sp500   = _fetch_index_with_fallback("S&P500", fetch_sp500)
    dow30   = _fetch_index_with_fallback("Dow30", fetch_dow30)
    nasdaq  = _fetch_index_with_fallback("Nasdaq100", fetch_nasdaq100)
    all_tickers = sp500 | dow30 | nasdaq

    rows = []
    for t in sorted(all_tickers):
        membership = []
        if t in sp500:   membership.append("S&P500")
        if t in dow30:   membership.append("Dow30")
        if t in nasdaq:  membership.append("Nasdaq100")
        rows.append({"ticker": t, "indexes": ", ".join(membership)})

    df = pd.DataFrame(rows)
    log.info(f"Total deduplicated universe: {len(df)} tickers")
    return df


# ═════════════════════════════════════════════
# STEP 2 — FETCH AAA YIELD FROM FRED
# ═════════════════════════════════════════════

def fetch_aaa_yield() -> float:
    """Fetch the latest Moody's AAA corporate bond yield from FRED."""
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY is required to fetch market rates")
    log.info("Fetching AAA yield from FRED...")
    fred = Fred(api_key=FRED_API_KEY)
    series = fred.get_series(FRED_AAA_SERIES)
    yield_val = float(series.dropna().iloc[-1])
    log.info(f"  → AAA yield: {yield_val:.2f}%")
    return yield_val


def fetch_risk_free_rate() -> float:
    """Fetch the latest 10-year Treasury constant-maturity rate from FRED."""
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY is required to fetch market rates")
    log.info("Fetching 10-year Treasury rate from FRED...")
    fred = Fred(api_key=FRED_API_KEY)
    series = fred.get_series(FRED_RISK_FREE_SERIES)
    rate = float(series.dropna().iloc[-1])
    log.info(f"  → 10-year Treasury rate: {rate:.2f}%")
    return rate


# ═════════════════════════════════════════════
# STEP 3 — FETCH FUNDAMENTALS
# ═════════════════════════════════════════════
# Data sources:
#   yfinance  → price (fast_info), EPS history for defensive checks, dividends
#   Finnhub   → EPS (current + growth), balance sheet ratios, market cap, BVPS
#
# Finnhub provides pre-calculated 5Y EPS CAGR and clean current-year values,
# which are more reliable than computing CAGR from 4-5 years of yfinance data.
# yfinance is kept for price (fastest) and historical EPS for defensive checks.

import yfinance as yf

FINNHUB_BASE = "https://finnhub.io/api/v1"


def get_finnhub_metrics(ticker: str) -> dict:
    """
    Fetch the full metric bundle from Finnhub stock/metric endpoint.
    Returns the raw metric dict, or empty dict on failure.
    """
    if not FINNHUB_API_KEY:
        raise RuntimeError("FINNHUB_API_KEY is required to fetch fundamentals")
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/stock/metric",
            params={"symbol": ticker, "metric": "all", "token": FINNHUB_API_KEY},
            timeout=15,
        )
        if r.status_code in (401, 403):
            raise RuntimeError(
                f"Finnhub authentication failed with HTTP {r.status_code}; "
                "refresh FINNHUB_API_KEY before running the screener"
            )
        if r.status_code == 200:
            return r.json().get("metric", {})
        log.warning(f"Finnhub {r.status_code} for {ticker}")
    except RuntimeError:
        raise
    except Exception as e:
        log.warning(f"Finnhub error for {ticker}: {e}")
    return {}


def _validate_finnhub_access() -> None:
    """Fail before the universe run when Finnhub cannot return a normal metric bundle."""
    log.info("Validating Finnhub access...")
    metrics = get_finnhub_metrics("AAPL")
    if not metrics:
        raise RuntimeError(
            "Finnhub preflight returned no metrics for AAPL; refusing to run with "
            "silently degraded provider coverage"
        )
    log.info("  → Finnhub access validated")


def _safe_float(v) -> float | None:
    """Return float or None for any null-like value including np.nan."""
    try:
        f = float(v)
        return None if f != f else f   # f != f is True only for nan
    except (TypeError, ValueError):
        return None


# ── Phase 6 yfinance candidate label lists (module-level constants) ───────────

OCF_LABELS = [
    "Operating Cash Flow",
    "Total Cash From Operating Activities",
    "Cash Flow From Operations",
    "Cash From Operating Activities",
]

CAPEX_LABELS = [
    "Capital Expenditure",
    "Capital Expenditures",
    "Purchase Of Property Plant And Equipment",
    "Acquisition Of Property Plant Equipment And Software",
]

EBIT_LABELS = [
    "EBIT",
    "Operating Income",
    "Ebit",
    "Total Operating Income As Reported",
]

INTEREST_EXPENSE_LABELS = [
    "Interest Expense Non Operating",
    "Interest Expense",
    "Interest And Debt Expense",
]

TAX_PROVISION_LABELS = [
    "Tax Provision",
    "Income Tax Expense",
]

PRETAX_INCOME_LABELS = [
    "Pretax Income",
    "Income Before Tax",
]

TOTAL_DEBT_LABELS = [
    "Total Debt",
]

CURRENT_DEBT_LABELS = [
    "Current Debt",
    "Current Portion Of Long Term Debt",
    "Short Long Term Debt",
]

CASH_LABELS = [
    "Cash And Cash Equivalents",
    "Cash Cash Equivalents And Short Term Investments",
    "Cash And Short Term Investments",
]

EQUITY_LABELS = [
    "Stockholders Equity",
    "Total Stockholders Equity",
    "Common Stock Equity",
    "Total Equity Gross Minority Interest",
]

SHARES_LABELS = [
    "Ordinary Shares Number",
    "Share Issued",
    "Common Stock Shares Outstanding",
]

DILUTED_SHARES_LABELS = [
    "Diluted Average Shares",
    "Diluted Average Shares Outstanding",
]

# ── Phase 7 yfinance candidate label lists ────────────────────────────────────
# [ASSUMED — yfinance label names vary by ticker; validated on a live Actions run]

NET_INCOME_LABELS = [
    "Net Income",
    "Net Income Common Stockholders",
    "Net Income Including Noncontrolling Interests",
]

TOTAL_ASSETS_LABELS = [
    "Total Assets",
]

GROSS_PROFIT_LABELS = [
    "Gross Profit",
]

REVENUE_LABELS = [
    "Total Revenue",
    "Revenue",
    "Operating Revenue",
]

CURRENT_ASSETS_LABELS = [
    "Current Assets",
    "Total Current Assets",
]

CURRENT_LIABILITIES_LABELS = [
    "Current Liabilities",
    "Total Current Liabilities",
    "Current Liabilities Net Minority Interest",
]

LONG_TERM_DEBT_LABELS = [
    "Long Term Debt",
    "Long Term Debt And Capital Lease Obligation",
]

RETAINED_EARNINGS_LABELS = [
    "Retained Earnings",
    "Retained Earnings Deficit",
]

TOTAL_LIABILITIES_LABELS = [
    "Total Liabilities Net Minority Interest",
    "Total Liabilities",
]


# ── Phase 6 pure helpers (internal — for tests only per CLAUDE.md §B) ─────────

def _yf_row(df, labels) -> float | None:
    """
    Return the most-recent annual value for the first matching label, or None.
    Newest column is index 0 (yfinance default sort — newest-first).
    internal — for tests only.
    """
    if df is None or df.empty:
        return None
    for label in labels:
        if label in df.index:
            return _safe_float(df.loc[label, df.columns[0]])
    return None


def _yf_row_prev(df, labels) -> float | None:
    """
    Return the prior-year (second column) value for the first matching label, or None.
    Newest column is index 0; prior year is index 1.
    Returns None if df is None, empty, or has fewer than 2 columns.
    internal — for tests only.
    """
    if df is None or df.empty or df.shape[1] < 2:
        return None
    for label in labels:
        if label in df.index:
            return _safe_float(df.loc[label, df.columns[1]])
    return None


def _extract_total_debt(balance_sheet) -> float | None:
    """Use aggregate total debt when present; otherwise sum current and long-term debt."""
    aggregate = _yf_row(balance_sheet, TOTAL_DEBT_LABELS)
    if aggregate is not None:
        return aggregate

    long_term = _yf_row(balance_sheet, LONG_TERM_DEBT_LABELS)
    current = _yf_row(balance_sheet, CURRENT_DEBT_LABELS)
    if long_term is None and current is None:
        return None
    return (long_term or 0.0) + (current or 0.0)


def _extract_total_debt_prev(balance_sheet) -> float | None:
    """Prior-year counterpart to _extract_total_debt."""
    aggregate = _yf_row_prev(balance_sheet, TOTAL_DEBT_LABELS)
    if aggregate is not None:
        return aggregate

    long_term = _yf_row_prev(balance_sheet, LONG_TERM_DEBT_LABELS)
    current = _yf_row_prev(balance_sheet, CURRENT_DEBT_LABELS)
    if long_term is None and current is None:
        return None
    return (long_term or 0.0) + (current or 0.0)


def _effective_tax_rate(income_statement) -> float:
    """Derive a bounded effective tax rate; fall back to the configured rate."""
    tax = _yf_row(income_statement, TAX_PROVISION_LABELS)
    pretax = _yf_row(income_statement, PRETAX_INCOME_LABELS)
    if tax is None or pretax is None or pretax <= 0:
        return DCF_DEFAULT_TAX_RATE
    return _winsorize(tax / pretax, 0.0, 0.35)


def _currency_mismatch(price_currency, financial_currency) -> bool:
    """Return True when quoted price and reported financials use different currencies."""
    if not price_currency or not financial_currency:
        return False
    return str(price_currency).strip().upper() != str(financial_currency).strip().upper()


def _apply_screen_wacc_guardrail(
    calculated_wacc,
    risk_free_rate_pct,
    terminal_growth_pct,
) -> dict:
    """Apply transparent screen-level floors to unstable low-WACC estimates."""
    risk_free_floor = (
        risk_free_rate_pct + DCF_MIN_WACC_RISK_FREE_SPREAD_PCT
    ) / 100.0
    terminal_floor = (
        terminal_growth_pct + DCF_MIN_WACC_TERMINAL_SPREAD_PCT
    ) / 100.0
    floor = max(risk_free_floor, terminal_floor)
    guarded_wacc = max(calculated_wacc, floor)
    return {
        "wacc": guarded_wacc,
        "unfloored_wacc": calculated_wacc,
        "wacc_floor": floor,
        "floor_applied": guarded_wacc > calculated_wacc + 1e-12,
    }


def _discounted_earnings_rate(aaa_yield_pct: float) -> float:
    """
    Discount rate for the legacy discounted-earnings diagnostic.

    This is deliberately not called WACC: it has no beta, debt weighting, or
    company-specific cost of debt.
    internal — for tests only.
    """
    return (aaa_yield_pct + DCF_ERP) / 100.0


def _compute_base_fcff(ocf, capex, interest_expense, tax_rate) -> float | None:
    """Convert reported operating cash flow to a screen-grade FCFF estimate."""
    if ocf is None or capex is None:
        return None
    interest = abs(interest_expense) if interest_expense is not None else 0.0
    capex_outflow = abs(capex)
    return ocf - capex_outflow + interest * (1.0 - tax_rate)


def _estimate_screen_wacc(
    risk_free_rate_pct,
    aaa_yield_pct,
    beta,
    market_cap,
    total_debt,
    prior_total_debt,
    interest_expense,
    tax_rate,
) -> dict | None:
    """Estimate a transparent screen-grade WACC and its component assumptions."""
    if (
        risk_free_rate_pct is None
        or aaa_yield_pct is None
        or market_cap is None
        or market_cap <= 0
        or total_debt is None
        or total_debt < 0
    ):
        return None

    beta_used = _winsorize(
        beta if beta is not None and beta > 0 else 1.0,
        DCF_BETA_FLOOR,
        DCF_BETA_CAP,
    )
    cost_of_equity = (risk_free_rate_pct + beta_used * DCF_ERP) / 100.0

    observed_cost = None
    debt_base = total_debt
    if prior_total_debt is not None and prior_total_debt >= 0:
        debt_base = (total_debt + prior_total_debt) / 2.0
    if interest_expense is not None and debt_base > 0:
        observed_cost = abs(interest_expense) / debt_base
        if observed_cost <= 0 or observed_cost > 0.30:
            observed_cost = None

    aaa_cost = max(0.0, aaa_yield_pct / 100.0)
    pre_tax_cost_of_debt = max(aaa_cost, observed_cost or 0.0)
    after_tax_cost_of_debt = pre_tax_cost_of_debt * (1.0 - tax_rate)

    total_capital = market_cap + total_debt
    equity_weight = market_cap / total_capital
    debt_weight = total_debt / total_capital
    wacc = equity_weight * cost_of_equity + debt_weight * after_tax_cost_of_debt

    return {
        "wacc": wacc,
        "beta": beta_used,
        "cost_of_equity": cost_of_equity,
        "pre_tax_cost_of_debt": pre_tax_cost_of_debt,
        "equity_weight": equity_weight,
        "debt_weight": debt_weight,
        "observed_cost_of_debt": observed_cost,
    }


def _compute_price_signals(closes, price) -> dict:
    """
    Compute five distance/recency signals from a pandas Close series and current price.
    Returns dict with keys: dist_52w_high, dist_52w_low, dist_5y_low,
    weeks_since_52w_low, weeks_since_5y_low, short_history.
    internal — for tests only.
    """
    none_result = {
        "dist_52w_high":     None,
        "dist_52w_low":      None,
        "dist_5y_low":       None,
        "weeks_since_52w_low": None,
        "weeks_since_5y_low":  None,
        "short_history":     False,
    }
    if closes is None or len(closes) == 0:
        return none_result

    n = len(closes)
    if n < 8:
        return none_result

    short_history = n < 52

    # 52-week window = last 52 bars (or all bars if fewer)
    w52 = closes.iloc[-min(n, 52):]
    high_52w = w52.max()
    low_52w  = w52.min()
    low_5y   = closes.min()

    # Zero-denominator guard
    if high_52w == 0 or low_52w == 0 or low_5y == 0:
        return {
            "dist_52w_high":     None if high_52w == 0 else max(0.0, (high_52w - price) / high_52w * 100),
            "dist_52w_low":      None if low_52w == 0  else max(0.0, (price - low_52w) / low_52w * 100),
            "dist_5y_low":       None if low_5y == 0   else max(0.0, (price - low_5y) / low_5y * 100),
            "weeks_since_52w_low": len(w52) - 1 - int(w52.values.argmin()),
            "weeks_since_5y_low":  len(closes) - 1 - int(closes.values.argmin()),
            "short_history":     short_history,
        }

    dist_52w_high = max(0.0, (high_52w - price) / high_52w * 100)
    dist_52w_low  = max(0.0, (price - low_52w) / low_52w * 100)
    dist_5y_low   = max(0.0, (price - low_5y) / low_5y * 100)
    weeks_since_52w_low = len(w52) - 1 - int(w52.values.argmin())
    weeks_since_5y_low  = len(closes) - 1 - int(closes.values.argmin())

    return {
        "dist_52w_high":       dist_52w_high,
        "dist_52w_low":        dist_52w_low,
        "dist_5y_low":         dist_5y_low,
        "weeks_since_52w_low": weeks_since_52w_low,
        "weeks_since_5y_low":  weeks_since_5y_low,
        "short_history":       short_history,
    }


def _compute_fcf_yield(ocf, capex, market_cap) -> float | None:
    """
    Compute FCF yield as a whole-number percent.
    FCF = ocf + capex (capex is negative in yfinance → addition adds the absolute value).
    If capex is None but ocf is present, FCF = ocf (OCF proxy).
    Negative FCF yields a negative result (NOT clamped — 06-02 routes it to worst).
    internal — for tests only.
    """
    if ocf is None:
        return None
    fcf = ocf + capex if capex is not None else ocf
    if not market_cap:
        return None
    return fcf / market_cap * 100


def _compute_ev_ebit(ebit, total_debt, cash, market_cap) -> tuple:
    """
    Compute EV/EBIT and earnings yield (EBIT/EV*100).
    total_debt and cash default to 0 when None.
    Returns (ev_ebit, earnings_yield) — both None unless ebit > 0 and ev > 0.
    market_cap None → (None, None).
    internal — for tests only.
    """
    if market_cap is None:
        return (None, None)
    td   = total_debt if total_debt is not None else 0
    cash = cash if cash is not None else 0
    ev = market_cap + td - cash
    if ebit is None or ebit <= 0 or ev <= 0:
        return (None, None)
    return (ev / ebit, ebit / ev * 100)


def _compute_roic(ebit, total_debt, equity, cash) -> float | None:
    """
    Compute ROIC as a whole-number percent.
    ROIC = EBIT*(1-0.21) / (total_debt + equity - cash) * 100.
    cash defaults to 0 when None.
    invested <= 0 → None (data anomaly, NOT worst per Slice A §3d).
    Negative EBIT yields negative ROIC (NOT clamped — 06-02 routes it to worst).
    internal — for tests only.
    """
    if ebit is None or total_debt is None or equity is None:
        return None
    c = cash if cash is not None else 0
    invested = total_debt + equity - c
    if invested <= 0:
        return None
    return ebit * (1 - 0.21) / invested * 100


def _compute_shareholder_yield(div_yield, shares_now, shares_prev) -> tuple:
    """
    Compute shareholder yield and a partial flag.
    div_yield is already a whole-number percent (e.g. 1.5 = 1.5%).
    net_buyback_yield = (shares_prev - shares_now) / shares_prev * 100
    Returns (shareholder_yield, partial_flag) where partial_flag is True when
    net_buyback_yield is None (div-only fallback).
    internal — for tests only.
    """
    net_buyback = None
    if shares_now is not None and shares_prev is not None and shares_prev > 0:
        net_buyback = (shares_prev - shares_now) / shares_prev * 100
    partial_flag = net_buyback is None
    total = (div_yield or 0.0) + (net_buyback if net_buyback is not None else 0.0)
    return (total, partial_flag)


def _compute_piotroski(
    inc_curr, inc_prev,
    bs_curr, bs_prev,
    cf_curr, cf_prev,
) -> int | None:
    """
    Compute Piotroski F-Score (0–9) from two years of financial statement DataFrames.

    Each DataFrame has newest-first columns (columns[0] = current year, columns[1] = prior year).
    The helper splits each DataFrame at columns[0] — it receives separate curr/prev DataFrames
    so the caller can pass a single-year DataFrame as curr and None as prev when only one year
    is available.

    Returns None when all current-year statements are None (no data at all).
    When prior-year DataFrames are None, two-year comparison criteria (F3, F5, F6, F7, F8, F9)
    are skipped rather than failed.

    Absent-data strategy per RESEARCH.md lines 295-299:
      - Missing single-year input → criterion fails (contributes 0).
      - Missing prior-year input for a comparison criterion → criterion skipped (not counted).
      - All statements absent → return None.

    WR-04: returns None (not a raw score) when 3 or fewer criteria were evaluable —
    i.e. only the always-available single-year criteria (F1, F2, F4) could be assessed
    and zero 2-year comparison signal exists. A raw score out of a theoretical 9 in that
    case would land in the distressed/weak band regardless of how F1/F2/F4 actually
    scored, unfairly penalizing thin-history tickers (e.g. recent IPOs). Callers should
    treat None the same as "absent" — it routes to the D-04 neutral-50 fallback at the
    Safety-pillar level, same as a fully-missing ticker.

    Columns must be newest-first (do NOT sort_index — per Pitfall 1 in RESEARCH.md).
    internal — for tests only.
    """
    # If all current-year statements are None, return None.
    if inc_curr is None and bs_curr is None and cf_curr is None:
        return None

    def _get(df, labels):
        """Read current-year (columns[0]) value for the first matching label."""
        if df is None or df.empty or df.shape[1] < 1:
            return None
        for label in labels:
            if label in df.index:
                return _safe_float(df.loc[label, df.columns[0]])
        return None

    def _get_prev(df, labels):
        """Read prior-year (columns[0]) from a prior-year DataFrame."""
        if df is None or df.empty or df.shape[1] < 1:
            return None
        for label in labels:
            if label in df.index:
                return _safe_float(df.loc[label, df.columns[0]])
        return None

    # ── Current-year inputs ──────────────────────────────────────────────────
    net_income_curr = _get(inc_curr, NET_INCOME_LABELS)
    total_assets_curr = _get(bs_curr, TOTAL_ASSETS_LABELS)
    ocf_curr = _get(cf_curr, OCF_LABELS)
    gross_profit_curr = _get(inc_curr, GROSS_PROFIT_LABELS)
    revenue_curr = _get(inc_curr, REVENUE_LABELS)
    current_assets_curr = _get(bs_curr, CURRENT_ASSETS_LABELS)
    current_liabilities_curr = _get(bs_curr, CURRENT_LIABILITIES_LABELS)
    long_term_debt_curr = _get(bs_curr, LONG_TERM_DEBT_LABELS)
    shares_curr = _get(bs_curr, SHARES_LABELS)

    # ── Prior-year inputs (from separate prev DataFrames, read at columns[0]) ─
    net_income_prev = _get_prev(inc_prev, NET_INCOME_LABELS)
    total_assets_prev = _get_prev(bs_prev, TOTAL_ASSETS_LABELS)
    gross_profit_prev = _get_prev(inc_prev, GROSS_PROFIT_LABELS)
    revenue_prev = _get_prev(inc_prev, REVENUE_LABELS)
    current_assets_prev = _get_prev(bs_prev, CURRENT_ASSETS_LABELS)
    current_liabilities_prev = _get_prev(bs_prev, CURRENT_LIABILITIES_LABELS)
    long_term_debt_prev = _get_prev(bs_prev, LONG_TERM_DEBT_LABELS)
    shares_prev = _get_prev(bs_prev, SHARES_LABELS)

    score = 0
    criteria_counted = 0  # track how many criteria were actually evaluated

    # F1: ROA > 0 (Net Income / Total Assets, current year)
    # WR-04: unconditional criteria_counted += 1, matching F2's fail-on-missing
    # pattern — a wholly-missing net_income_curr must count as an evaluated
    # (failed) criterion, not be silently skipped.
    if net_income_curr is not None and total_assets_curr:
        criteria_counted += 1
        if (net_income_curr / total_assets_curr) > 0:
            score += 1
    else:
        criteria_counted += 1  # missing net_income or total_assets → conservative fail

    # F2: OCF > 0 (current year)
    if ocf_curr is not None:
        criteria_counted += 1
        if ocf_curr > 0:
            score += 1
    else:
        criteria_counted += 1  # missing → fail

    # F3: ROA improved (requires prior year) — skip if prev absent
    if net_income_prev is not None and total_assets_prev and total_assets_curr:
        criteria_counted += 1
        roa_curr = (net_income_curr / total_assets_curr) if net_income_curr is not None and total_assets_curr else None
        roa_prev = net_income_prev / total_assets_prev
        if roa_curr is not None and roa_curr > roa_prev:
            score += 1

    # F4: Accruals — OCF / Total Assets > ROA (quality of earnings)
    if ocf_curr is not None and total_assets_curr and net_income_curr is not None:
        criteria_counted += 1
        roa_curr = net_income_curr / total_assets_curr
        cfo_assets = ocf_curr / total_assets_curr
        if cfo_assets > roa_curr:
            score += 1
    elif total_assets_curr:
        criteria_counted += 1  # missing ocf or net_income → fail

    # F5: Leverage decreased (long_term_debt / avg_total_assets) — skip if prev absent,
    # and fail safe (do not award) if current-year long-term-debt is absent (matches F6/F8).
    if long_term_debt_prev is not None and total_assets_prev and total_assets_curr and long_term_debt_curr is not None:
        criteria_counted += 1
        avg_assets = (total_assets_curr + total_assets_prev) / 2.0
        ltd_ratio_curr = long_term_debt_curr / avg_assets
        ltd_ratio_prev = long_term_debt_prev / total_assets_prev
        if ltd_ratio_curr < ltd_ratio_prev:
            score += 1

    # F6: Current ratio improved — skip if prev absent
    if current_assets_prev is not None and current_liabilities_prev and current_liabilities_curr:
        criteria_counted += 1
        cr_curr = (current_assets_curr / current_liabilities_curr) if current_assets_curr is not None else 0
        cr_prev = current_assets_prev / current_liabilities_prev
        if cr_curr > cr_prev:
            score += 1

    # F7: No dilution (shares outstanding did not increase) — skip if prev absent
    if shares_prev is not None and shares_curr is not None:
        criteria_counted += 1
        if shares_curr <= shares_prev:
            score += 1

    # F8: Gross margin improved — skip if prev absent
    if gross_profit_prev is not None and revenue_prev and revenue_curr:
        criteria_counted += 1
        gm_curr = (gross_profit_curr / revenue_curr) if gross_profit_curr is not None else 0
        gm_prev = gross_profit_prev / revenue_prev
        if gm_curr > gm_prev:
            score += 1

    # F9: Asset turnover improved (Revenue / Total Assets) — skip if prev absent
    if revenue_prev is not None and total_assets_prev and total_assets_curr and revenue_curr:
        criteria_counted += 1
        at_curr = revenue_curr / total_assets_curr
        at_prev = revenue_prev / total_assets_prev
        if at_curr > at_prev:
            score += 1

    # WR-04: with 2-year history absent entirely, only the 3 always-available
    # single-year criteria (F1, F2, F4) can be evaluated — a raw score out of a
    # theoretical 9 then lands in the "distressed"/"weak" bands regardless of
    # how those 3 actually scored, unfairly penalizing thin-history tickers
    # (e.g. recent IPOs). Route to None (→ D-04 neutral-50 at the Safety-pillar
    # level) instead of a misleadingly small 0-3 raw score.
    if criteria_counted <= 3:
        return None
    return score


def _compute_altman_z(bs_curr, inc_curr) -> float | None:
    """
    Compute Altman Z'' score for non-financial, non-manufacturer firms.
    Formula: Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4

      X1 = Working Capital / Total Assets  (WC = Current Assets - Current Liabilities)
      X2 = Retained Earnings / Total Assets
      X3 = EBIT / Total Assets
      X4 = Book Value of Equity / Total Liabilities

    Returns None if total_assets is None/0, total_liabilities is None/0, or any
    numerator input that would make the formula meaningless is absent.
    Negative Z'' (e.g. deeply distressed / negative equity) is returned as-is — the
    band table starts at -999.0 to handle it correctly.

    internal — for tests only.
    """
    if bs_curr is None or bs_curr.empty:
        return None

    def _get(df, labels):
        if df is None or df.empty or df.shape[1] < 1:
            return None
        for label in labels:
            if label in df.index:
                return _safe_float(df.loc[label, df.columns[0]])
        return None

    total_assets = _get(bs_curr, TOTAL_ASSETS_LABELS)
    if not total_assets:
        return None

    total_liabilities = _get(bs_curr, TOTAL_LIABILITIES_LABELS)
    if not total_liabilities:
        return None

    current_assets = _get(bs_curr, CURRENT_ASSETS_LABELS)
    current_liabilities = _get(bs_curr, CURRENT_LIABILITIES_LABELS)
    retained_earnings = _get(bs_curr, RETAINED_EARNINGS_LABELS)
    equity = _get(bs_curr, EQUITY_LABELS)
    ebit = _get(inc_curr, EBIT_LABELS) if inc_curr is not None else None

    # Working capital
    if current_assets is None or current_liabilities is None:
        return None
    wc = current_assets - current_liabilities

    # X1 = WC / TA
    X1 = wc / total_assets

    # X2 = RE / TA (retained earnings may be negative)
    if retained_earnings is None:
        return None
    X2 = retained_earnings / total_assets

    # X3 = EBIT / TA
    if ebit is None:
        return None
    X3 = ebit / total_assets

    # X4 = BVE / TL
    if equity is None:
        return None
    X4 = equity / total_liabilities

    return 6.56 * X1 + 3.26 * X2 + 6.72 * X3 + 1.05 * X4


def _compute_discounted_earnings_forward(
    eps,
    g_cagr_pct: float,
    aaa_yield_pct: float,
    price: float,
) -> tuple:
    """
    Compute the legacy two-stage discounted-earnings value and discount percentage.

    Stage 1: 5 years of EPS at g_cagr growth, discounted at the diagnostic rate.
    Stage 2: Gordon Growth terminal value using g_terminal = min(g_cagr, DCF_TERMINAL_GROWTH_CAP/100).
    Discount rate = AAA yield + configured equity premium.

    Returns (intrinsic_value, discount_pct) where discount_pct = (1 - price/intrinsic)*100.
    Positive discount = cheap (price below intrinsic). Negative = overpriced.

    Returns (None, None) when eps is None or eps <= 0.
    Raises ValueError when terminal_growth >= WACC (misconfigured constants).
    internal — for tests only.
    """
    if eps is None or eps <= 0:
        return (None, None)

    discount_rate = _discounted_earnings_rate(aaa_yield_pct)
    g = g_cagr_pct / 100.0
    g_terminal = min(g, DCF_TERMINAL_GROWTH_CAP / 100.0)

    if g_terminal >= discount_rate:
        raise ValueError(
            f"Discounted-earnings config error: terminal_growth ({g_terminal:.4f}) "
            f">= discount rate ({discount_rate:.4f}). "
            f"Increase DCF_ERP or reduce DCF_TERMINAL_GROWTH_CAP."
        )

    # Stage 1: sum PV of 5 years of EPS
    pv_stage1 = 0.0
    eps_t = eps
    for t in range(1, 6):
        eps_t = eps_t * (1 + g)
        pv_stage1 += eps_t / (1 + discount_rate) ** t

    # Stage 2: terminal value (Gordon Growth Model) discounted to present
    tv = eps_t * (1 + g_terminal) / (discount_rate - g_terminal)
    pv_tv = tv / (1 + discount_rate) ** 5

    intrinsic = pv_stage1 + pv_tv
    discount_pct = (1 - price / intrinsic) * 100

    return (intrinsic, discount_pct)


def _compute_discounted_earnings_reverse(
    price: float,
    eps,
    aaa_yield_pct: float,
) -> tuple:
    """
    Reverse discounted earnings: find the implied growth rate that makes the value
    equal the current market price, using scipy.optimize.brentq.

    Returns (implied_growth_pct, True) when brentq converges.
    Returns (None, False) when no sign change exists in the bracket [-50, 100]
    (no root in that range) or on solver error.

    Non-convergence is the expected outcome for extreme valuations (very cheap or
    very expensive stocks where the bracket has no sign change) — never a silent
    default per D-09.

    Guards: eps None or <= 0 -> (None, False).
    internal — for tests only.
    """
    if eps is None or eps <= 0:
        return (None, False)

    discount_rate = _discounted_earnings_rate(aaa_yield_pct)

    def _dcf_value(g_pct: float) -> float:
        """Returns DCF intrinsic value at g_pct% growth minus current price."""
        g = g_pct / 100.0
        g_term = min(g, DCF_TERMINAL_GROWTH_CAP / 100.0)
        # Guard: clamp to prevent Gordon Growth denominator from going to zero
        if g_term >= discount_rate:
            g_term = discount_rate - 0.001
        pv = 0.0
        eps_t = eps
        for t in range(1, 6):
            eps_t = eps_t * (1 + g)
            pv += eps_t / (1 + discount_rate) ** t
        tv = eps_t * (1 + g_term) / (discount_rate - g_term)
        pv += tv / (1 + discount_rate) ** 5
        return pv - price

    try:
        lo, hi = -50.0, 100.0
        # Bracket guard: brentq requires opposite signs at endpoints
        if _dcf_value(lo) * _dcf_value(hi) > 0:
            return (None, False)
        root = brentq(_dcf_value, lo, hi, xtol=1e-4, maxiter=100)
        return (round(root, 2), True)
    except (ValueError, RuntimeError):
        return (None, False)


def _project_fcff_enterprise_value(
    base_fcff: float,
    initial_growth_pct: float,
    wacc: float,
    terminal_growth_pct: float,
    years: int = DCF_FORECAST_YEARS,
) -> tuple:
    """Project FCFF with a linear growth fade and return EV plus terminal share."""
    if base_fcff is None or base_fcff <= 0 or years < 1:
        return (None, None)

    terminal_growth = terminal_growth_pct / 100.0
    if wacc <= terminal_growth:
        raise ValueError(
            f"FCFF DCF requires WACC ({wacc:.4f}) above terminal growth "
            f"({terminal_growth:.4f})"
        )

    initial_growth = initial_growth_pct / 100.0
    fcff_t = base_fcff
    pv_explicit = 0.0
    for year in range(1, years + 1):
        fade = (year - 1) / max(1, years - 1)
        growth_t = initial_growth + (terminal_growth - initial_growth) * fade
        fcff_t *= 1.0 + growth_t
        pv_explicit += fcff_t / (1.0 + wacc) ** year

    terminal_value = fcff_t * (1.0 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal_value / (1.0 + wacc) ** years
    enterprise_value = pv_explicit + pv_terminal
    if enterprise_value <= 0:
        return (None, None)
    terminal_share_pct = pv_terminal / enterprise_value * 100.0
    return (enterprise_value, terminal_share_pct)


def _fcff_value_per_share(
    base_fcff,
    initial_growth_pct,
    wacc,
    terminal_growth_pct,
    cash,
    total_debt,
    diluted_shares,
) -> tuple:
    """Bridge projected enterprise value to common-equity value per share."""
    if (
        cash is None
        or total_debt is None
        or diluted_shares is None
        or diluted_shares <= 0
    ):
        return (None, None, None)

    enterprise_value, terminal_share_pct = _project_fcff_enterprise_value(
        base_fcff,
        initial_growth_pct,
        wacc,
        terminal_growth_pct,
    )
    if enterprise_value is None:
        return (None, None, None)

    equity_value = enterprise_value + cash - total_debt
    if equity_value <= 0:
        return (None, enterprise_value, terminal_share_pct)
    return (equity_value / diluted_shares, enterprise_value, terminal_share_pct)


def _compute_fcff_dcf(
    base_fcff,
    initial_growth_pct,
    wacc,
    terminal_growth_pct,
    cash,
    total_debt,
    diluted_shares,
    price,
) -> dict | None:
    """Compute a screen-grade FCFF DCF, EV bridge, and paired valuation range."""
    if initial_growth_pct is None or price is None or price <= 0:
        return None

    growth_used = _winsorize(
        initial_growth_pct,
        DCF_INITIAL_GROWTH_FLOOR,
        DCF_INITIAL_GROWTH_CAP,
    )
    value, enterprise_value, terminal_share_pct = _fcff_value_per_share(
        base_fcff,
        growth_used,
        wacc,
        terminal_growth_pct,
        cash,
        total_debt,
        diluted_shares,
    )
    if value is None:
        return None

    low_value, _, _ = _fcff_value_per_share(
        base_fcff,
        max(DCF_INITIAL_GROWTH_FLOOR, growth_used - 2.0),
        wacc + DCF_SENSITIVITY_WACC_STEP,
        max(0.0, terminal_growth_pct - DCF_SENSITIVITY_GROWTH_STEP * 100.0),
        cash,
        total_debt,
        diluted_shares,
    )
    high_wacc = wacc - DCF_SENSITIVITY_WACC_STEP
    high_terminal_growth = min(
        DCF_TERMINAL_GROWTH_CAP,
        terminal_growth_pct + DCF_SENSITIVITY_GROWTH_STEP * 100.0,
    )
    if high_wacc <= high_terminal_growth / 100.0:
        high_value = None
    else:
        high_value, _, _ = _fcff_value_per_share(
            base_fcff,
            min(DCF_INITIAL_GROWTH_CAP, growth_used + 2.0),
            high_wacc,
            high_terminal_growth,
            cash,
            total_debt,
            diluted_shares,
        )

    return {
        "intrinsic_value": value,
        "discount_pct": (1.0 - price / value) * 100.0,
        "enterprise_value": enterprise_value,
        "terminal_value_pct": terminal_share_pct,
        "growth_used_pct": growth_used,
        "value_low": low_value,
        "value_high": high_value,
    }


def _compute_fcff_reverse_dcf(
    price,
    base_fcff,
    wacc,
    terminal_growth_pct,
    cash,
    total_debt,
    diluted_shares,
) -> tuple:
    """Solve for the initial FCFF growth rate implied by the current equity price."""
    if (
        price is None
        or price <= 0
        or base_fcff is None
        or base_fcff <= 0
        or cash is None
        or total_debt is None
        or diluted_shares is None
        or diluted_shares <= 0
    ):
        return (None, False)

    target_enterprise_value = price * diluted_shares + total_debt - cash
    if target_enterprise_value <= 0:
        return (None, False)

    def objective(growth_pct: float) -> float:
        enterprise_value, _ = _project_fcff_enterprise_value(
            base_fcff,
            growth_pct,
            wacc,
            terminal_growth_pct,
        )
        if enterprise_value is None:
            return -target_enterprise_value
        return enterprise_value - target_enterprise_value

    try:
        lo, hi = -50.0, 50.0
        lo_value = objective(lo)
        hi_value = objective(hi)
        if lo_value * hi_value > 0:
            return (None, False)
        root = brentq(objective, lo, hi, xtol=1e-4, maxiter=100)
        return (round(root, 2), True)
    except (ValueError, RuntimeError):
        return (None, False)


def get_yf_price_and_history(ticker: str) -> dict:
    """
    Fetch price, historical EPS, dividends, sector, 5y weekly history, and
    raw statement components for the Phase 6 factor helpers — all from ONE
    reused yf.Ticker object per ticker (D-03/D-05).

    Returns: {
        price, annual_eps, annual_dividends,
        sector,
        dist_52w_high, dist_52w_low, dist_5y_low,
        weeks_since_52w_low, weeks_since_5y_low, short_history,
        ocf, capex, ebit, total_debt, cash, equity, shares_now, shares_prev,
    }
    """
    result = {
        "price":              None,
        "annual_eps":         [],
        "annual_dividends":   [],
        # Phase 6 additions
        "sector":             None,
        "dist_52w_high":      None,
        "dist_52w_low":       None,
        "dist_5y_low":        None,
        "weeks_since_52w_low": None,
        "weeks_since_5y_low":  None,
        "short_history":      False,
        "ocf":                None,
        "capex":              None,
        "ebit":               None,
        "interest_expense":   None,
        "tax_rate":           DCF_DEFAULT_TAX_RATE,
        "total_debt":         None,
        "prior_total_debt":   None,
        "cash":               None,
        "equity":             None,
        "shares_now":         None,
        "shares_prev":        None,
        "diluted_shares":     None,
        "market_cap":         None,
        "beta":               None,
        "price_currency":     None,
        "financial_currency": None,
        # Phase 7 additions: raw DataFrames for Piotroski/Altman (newest-first columns)
        "income_stmt_df":     None,
        "balance_sheet_df":   None,
        "cashflow_df":        None,
    }
    try:
        t = yf.Ticker(ticker)

        # ── Price ───────────────────────────────────────────────────────
        fi = t.fast_info
        result["price"] = getattr(fi, "last_price", None)
        result["market_cap"] = _safe_float(getattr(fi, "market_cap", None))
        price = result["price"]

        # ── Sector — guard .info separately; it may raise on delisted tickers ──
        try:
            info = t.info or {}
            result["sector"] = info.get("sector")
            result["beta"] = _safe_float(info.get("beta"))
            result["price_currency"] = info.get("currency")
            result["financial_currency"] = info.get("financialCurrency")
            if result["market_cap"] is None:
                result["market_cap"] = _safe_float(info.get("marketCap"))
        except Exception:
            result["sector"] = None

        # ── Historical EPS (for 10yr defensive checks) ──────────────────
        inc = t.income_stmt
        if inc is not None and not inc.empty:
            inc = inc.sort_index(axis=1)  # oldest→newest
            for label in ["Basic EPS", "Diluted EPS", "Basic Eps", "Diluted Eps"]:
                if label in inc.index:
                    result["annual_eps"] = [_safe_float(v) for v in inc.loc[label].values]
                    break
            # EBIT from income statement (newest-first — NOT re-sorted here; use raw)
            result["ebit"] = _yf_row(t.income_stmt, EBIT_LABELS)
            result["interest_expense"] = _yf_row(t.income_stmt, INTEREST_EXPENSE_LABELS)
            result["tax_rate"] = _effective_tax_rate(t.income_stmt)
            result["diluted_shares"] = _yf_row(t.income_stmt, DILUTED_SHARES_LABELS)

        # ── Dividend history ────────────────────────────────────────────
        divs = t.dividends
        if divs is not None and not divs.empty:
            divs.index = divs.index.tz_localize(None) if divs.index.tz else divs.index
            annual_divs = divs.resample("YE").sum()
            result["annual_dividends"] = [float(v) for v in annual_divs.values[-10:]]

        # ── 5-year weekly history → price distance/recency signals ──────
        try:
            hist = t.history(period="5y", interval="1wk")
        except Exception:
            hist = pd.DataFrame()
        if hist is not None and not hist.empty and "Close" in hist.columns and price:
            signals = _compute_price_signals(hist["Close"], price)
            result["dist_52w_high"]      = signals["dist_52w_high"]
            result["dist_52w_low"]       = signals["dist_52w_low"]
            result["dist_5y_low"]        = signals["dist_5y_low"]
            result["weeks_since_52w_low"] = signals["weeks_since_52w_low"]
            result["weeks_since_5y_low"]  = signals["weeks_since_5y_low"]
            result["short_history"]      = signals["short_history"]

        # ── Cashflow statement — OCF and capex ──────────────────────────
        cf = t.cashflow
        if cf is not None and not cf.empty:
            result["ocf"]   = _yf_row(cf, OCF_LABELS)
            result["capex"] = _yf_row(cf, CAPEX_LABELS)

        # ── Balance sheet — debt, cash, equity, shares ──────────────────
        bs = t.balance_sheet
        if bs is not None and not bs.empty:
            result["total_debt"] = _extract_total_debt(bs)
            result["prior_total_debt"] = _extract_total_debt_prev(bs)
            result["cash"]       = _yf_row(bs, CASH_LABELS)
            result["equity"]     = _yf_row(bs, EQUITY_LABELS)
            # Shares outstanding: newest (col 0) and prior year (col 1)
            for label in SHARES_LABELS:
                if label in bs.index:
                    shares_row = bs.loc[label]
                    result["shares_now"]  = _safe_float(shares_row.iloc[0]) if len(shares_row) >= 1 else None
                    result["shares_prev"] = _safe_float(shares_row.iloc[1]) if len(shares_row) >= 2 else None
                    break

        # ── Phase 7: store raw unsorted DataFrames for Piotroski / Altman ──
        # Store the raw Ticker attributes (newest-first columns).
        # Do NOT use the sorted `inc` local above — that is oldest→newest (for EPS).
        # _compute_piotroski / _compute_altman_z read columns[0] as current year.
        result["income_stmt_df"]   = t.income_stmt
        result["balance_sheet_df"] = t.balance_sheet
        result["cashflow_df"]      = t.cashflow

    except Exception as e:
        log.warning(f"yfinance error for {ticker}: {e}")
    return result


def get_combined_data(ticker: str) -> dict:
    """
    Merge yfinance (price, EPS history) and Finnhub (current fundamentals).
    Finnhub values take precedence for current EPS, growth, and balance sheet.
    Falls back to yfinance values where Finnhub is missing.

    Returns a unified dict with all fields downstream code expects:
        price, market_cap_b, annual_eps, annual_dividends,
        ttm_eps, ttm_dps, growth_pct,
        current_ratio, debt_equity, book_value_ps
    """
    yf_data = get_yf_price_and_history(ticker)
    fh      = get_finnhub_metrics(ticker)

    # ── Price (yfinance is fastest) ─────────────────────────────────
    price = yf_data["price"]

    # ── Current EPS — Finnhub first, yfinance history as fallback ───
    ttm_eps = _safe_float(fh.get("epsAnnual") or fh.get("epsBasicExclExtraItemsAnnual"))
    # BRK-B: Finnhub returns Class A equivalent EPS; scale to Class B before falling back.
    # yfinance already reports per-Class-B-share EPS, so the fallback needs no scaling.
    if ticker in ("BRK-B", "BRK.B") and ttm_eps is not None:
        ttm_eps = ttm_eps / 1500.0
    if ttm_eps is None and yf_data["annual_eps"]:
        valid = [e for e in yf_data["annual_eps"] if e is not None and e == e]
        ttm_eps = valid[-1] if valid else None

    # ── EPS growth — Finnhub pre-calculated CAGR ────────────────────
    # Prefer 5Y, fall back to 3Y, then compute from history
    growth_pct = _safe_float(fh.get("epsGrowth5Y") or fh.get("epsGrowth3Y"))
    if growth_pct is not None:
        growth_pct = round(growth_pct * 100, 4)  # Finnhub returns decimal fraction (0.15 = 15%)

    # ── Dividends per share ─────────────────────────────────────────
    ttm_dps = _safe_float(fh.get("dividendPerShareAnnual") or fh.get("dividendPerShareTTM")) or 0.0

    # ── Market cap ──────────────────────────────────────────────────
    # Finnhub returns marketCapitalization in $millions
    mkt_cap_b = None
    fh_mktcap = _safe_float(fh.get("marketCapitalization"))
    if fh_mktcap is not None:
        mkt_cap_b = fh_mktcap / 1000.0  # millions → billions
    elif yf_data["market_cap"] is not None:
        mkt_cap_b = yf_data["market_cap"] / 1e9

    # ── Balance sheet ratios (Finnhub direct) ───────────────────────
    current_ratio = _safe_float(fh.get("currentRatioAnnual") or fh.get("currentRatioQuarterly"))
    debt_equity   = _safe_float(fh.get("totalDebt/totalEquityAnnual"))
    book_value_ps = _safe_float(fh.get("bookValuePerShareAnnual") or fh.get("bookValuePerShareQuarterly"))
    pb_ratio      = _safe_float(fh.get("pb"))

    # ── FCF per share — read from already-fetched Finnhub bundle (D-04) ──
    # No new HTTP request; reuses the metric=all bundle fetched above.
    # Primary: freeCashFlowPerShareTTM; fallback: freeCashFlowPerShareAnnual.
    # Field names are community-sourced [ASSUMED]; run diagnose_finnhub.py on
    # the next live Actions run to confirm the exact key names in production.
    # If both fields are absent, _safe_float returns None → Plan 02's trap gate
    # runs on the other 3 inputs (D-01b: genuinely-missing path).
    fcf_per_share = _safe_float(
        fh.get("freeCashFlowPerShareTTM") or fh.get("freeCashFlowPerShareAnnual")
    )

    # ── Phase 6: compute factor values from raw yfinance components ────
    mkt_cap = mkt_cap_b * 1e9 if mkt_cap_b is not None else None

    # FCF yield — yfinance cashflow (D-01: Finnhub FCF confirmed absent on free tier)
    fcf_yield = _compute_fcf_yield(
        ocf=yf_data["ocf"],
        capex=yf_data["capex"],
        market_cap=mkt_cap,
    )

    # EV/EBIT and earnings yield
    ev_ebit, earnings_yield = _compute_ev_ebit(
        ebit=yf_data["ebit"],
        total_debt=yf_data["total_debt"],
        cash=yf_data["cash"],
        market_cap=mkt_cap,
    )

    # ROIC
    roic = _compute_roic(
        ebit=yf_data["ebit"],
        total_debt=yf_data["total_debt"],
        equity=yf_data["equity"],
        cash=yf_data["cash"],
    )

    # Shareholder yield — div_yield computed as whole-number percent (matches DivYield_Pct)
    div_yield_pct = (float(ttm_dps) / float(price) * 100.0) if (price and ttm_dps) else 0.0
    shareholder_yield, sh_partial = _compute_shareholder_yield(
        div_yield=div_yield_pct,
        shares_now=yf_data["shares_now"],
        shares_prev=yf_data["shares_prev"],
    )

    return {
        "price":            price,
        "finnhub_ok":       bool(fh),
        "market_cap_b":     mkt_cap_b,
        "annual_eps":       yf_data["annual_eps"],      # historical list for defensive checks
        "annual_dividends": yf_data["annual_dividends"],
        "ttm_eps":          ttm_eps,
        "ttm_dps":          ttm_dps,
        "growth_pct":       growth_pct,                 # Finnhub 5Y CAGR
        "current_ratio":    current_ratio,
        "debt_equity":      debt_equity,
        "book_value_ps":    book_value_ps,
        "pb_ratio":         pb_ratio,
        "fcf_per_share":    fcf_per_share,              # FCF sign for Plan 02 trap gate (D-04)
        # Screen-grade FCFF DCF inputs
        "ocf":                  yf_data["ocf"],
        "capex":                yf_data["capex"],
        "interest_expense":     yf_data["interest_expense"],
        "tax_rate":             yf_data["tax_rate"],
        "total_debt":           yf_data["total_debt"],
        "prior_total_debt":     yf_data["prior_total_debt"],
        "cash":                 yf_data["cash"],
        "shares_now":           yf_data["shares_now"],
        "diluted_shares":       yf_data["diluted_shares"],
        "beta":                 yf_data["beta"],
        "price_currency":       yf_data["price_currency"],
        "financial_currency":   yf_data["financial_currency"],
        # Phase 6 additions — sector + price signals
        "sector":                yf_data["sector"],
        "dist_52w_high":         yf_data["dist_52w_high"],
        "dist_52w_low":          yf_data["dist_52w_low"],
        "dist_5y_low":           yf_data["dist_5y_low"],
        "weeks_since_52w_low":   yf_data["weeks_since_52w_low"],
        "weeks_since_5y_low":    yf_data["weeks_since_5y_low"],
        "short_history":         yf_data["short_history"],
        # Phase 6 additions — fundamental factors
        "fcf_yield":             fcf_yield,
        "ev_ebit":               ev_ebit,
        "earnings_yield":        earnings_yield,
        "roic":                  roic,
        "shareholder_yield":     shareholder_yield,
        "shareholder_yield_partial": sh_partial,
        # Phase 7 additions — raw statement DataFrames for Piotroski/Altman (D-05)
        "income_stmt_df":        yf_data["income_stmt_df"],
        "balance_sheet_df":      yf_data["balance_sheet_df"],
        "cashflow_df":           yf_data["cashflow_df"],
    }




# ═════════════════════════════════════════════
# STEP 4 — COMPUTE METRICS
# ═════════════════════════════════════════════

def compute_growth_5yr_cagr(annual_eps: list) -> float | None:
    """
    EPS CAGR using the longest available window up to 5 years.
    yfinance typically returns 4-5 years of annual data, so we use
    whatever span is available rather than requiring exactly 6 points.
    Minimum 2 data points required.
    Returns growth as a whole-number percent, capped at GROWTH_CAP.
    Returns None if data insufficient or base EPS is negative/zero.
    """
    eps = [e for e in annual_eps if e is not None and e == e]  # e == e filters np.nan
    if len(eps) < 2:
        return None
    eps_now  = eps[-1]
    eps_base = eps[0]   # oldest available
    years    = len(eps) - 1
    if eps_base <= 0 or eps_now <= 0:
        return None
    cagr = ((eps_now / eps_base) ** (1 / years) - 1) * 100
    return min(round(cagr, 2), GROWTH_CAP)


def _reconcile_growth(g_finnhub: float | None, g_cagr: float | None) -> float | None:
    """
    Reconcile Finnhub's reported 5Y EPS growth against the realized CAGR from EPS
    history (Bug B fix).  Finnhub free-tier ``epsGrowth5Y`` is frequently inflated
    for flat/declining-EPS names — left unchecked it gets trusted, then capped at
    GROWTH_CAP, producing a fake 25% grower that inflates Lynch/Graham valuations.
    When a realized CAGR exists we take the lower (reality-anchored) value; otherwise
    we fall back to whichever single value is present.

    Finnhub values below GROWTH_FINNHUB_FLOOR are mathematically impossible (EPS
    can't drop >100% from a positive base) and are discarded before reconciliation,
    since taking min() with them would only make the existing inflation-guard worse
    (e.g. KMB: g_finnhub=-242% would win over a sane g_cagr just for being lower).

    # ponytail: endpoint-sensitive (uses first/last EPS in the available window).
    #   Good enough as an interim anchor — Phase 7 refines growth handling
    #   (upgrade path: regression slope across the window, or a longer EPS history).
    """
    if g_finnhub is not None and g_finnhub < GROWTH_FINNHUB_FLOOR:
        g_finnhub = None
    if g_finnhub is None:
        return g_cagr
    if g_cagr is None:
        return g_finnhub
    return min(g_finnhub, g_cagr)


def _eps_stable_for_gate(annual_eps: list) -> int | None:
    """
    Window-appropriate EPS-stability signal for the value-trap gate (Bug A fix).

    The defensive ``EPS_Stability`` criterion uses an 8-of-10-year rule, but yfinance
    supplies only ~4 years of annual EPS, so it is structurally 0 for every ticker —
    which tripped the trap gate (and floored the Safety pillar to 0) for the entire
    universe, making both signals useless.  Instead, judge stability over the
    *available* window: stable (1) only if every available year had positive EPS;
    unstable (0) if any year was <= 0; None when too few years to judge (D-01b unknown).
    """
    eps = [e for e in annual_eps if e is not None and e == e]  # e == e filters np.nan
    if len(eps) < 2:
        return None
    return 1 if all(e > 0 for e in eps) else 0


def lynch_metrics(price: float, eps: float, g: float, dy: float) -> dict:
    """
    Compute all Lynch valuation metrics.
    g and dy are whole-number percentages (e.g. 15.0 for 15%).
    """
    m = {}

    if eps <= 0 or g <= 0:
        return {"error": "Non-positive EPS or growth"}

    pe = price / eps
    m["PE"]            = round(pe, 2)
    m["PEG"]           = round(pe / g, 3)
    m["PEGY"]          = round(pe / (g + dy), 3) if (g + dy) > 0 else None
    m["Lynch_Score"]   = round((g + dy) / pe, 3) if pe > 0 else None  # inverse PEGY

    # Fair values
    m["FV_PEG"]        = round(eps * g, 2)                  # PEG=1 fair value
    m["FV_PEG_Con"]    = round(eps * 0.8 * g, 2)            # conservative (PEG=0.8)
    m["FV_GplusD"]     = round(eps * (g + dy), 2)           # G+D method

    # Category — thresholds per Lynch's One Up on Wall Street (Ch. 8)
    if g < 10:
        cat = "Slow"
    elif g <= 20:
        cat = "Stalwart"
    else:
        cat = "Fast"
    m["Lynch_Category"] = cat
    # FV_GplusD treats Lynch_Score = 1.0 as the fair-value anchor (fair P/E = g + dy).
    # Lynch_BuyPrice applies a category-specific margin-of-safety haircut (Slow=75%, etc.).
    m["Lynch_BuyPrice"] = round(m["FV_GplusD"] * LYNCH_DISCOUNT[cat], 2)

    # PEG status
    if m["PEG"] < LYNCH_PEG_CHEAP:
        m["PEG_Status"] = "Cheap"
    elif m["PEG"] <= LYNCH_PEG_FAIR:
        m["PEG_Status"] = "Reasonable"
    else:
        m["PEG_Status"] = "Rich"

    # PEGY status
    if m["PEGY"] is not None:
        if m["PEGY"] < LYNCH_PEGY_CHEAP:
            m["PEGY_Status"] = "Cheap"
        elif m["PEGY"] <= LYNCH_PEGY_FAIR:
            m["PEGY_Status"] = "Reasonable"
        else:
            m["PEGY_Status"] = "Rich"

    # Lynch value ratio (G+D method)
    lv = price / m["FV_GplusD"] if m["FV_GplusD"] > 0 else None
    m["LV_Ratio"] = round(lv, 3) if lv else None
    if lv is not None:
        if lv <= LYNCH_LV_STRONG_BUY:
            m["Lynch_Status"] = "Strong Buy"
        elif lv <= LYNCH_LV_BUY:
            m["Lynch_Status"] = "Buy"
        elif lv <= LYNCH_LV_HOLD:
            m["Lynch_Status"] = "Hold"
        else:
            m["Lynch_Status"] = "Avoid"

    # Price band status (PEG-based)
    fv_con = m["FV_PEG_Con"]
    fv     = m["FV_PEG"]
    if price <= 0.7 * fv_con:
        m["Lynch_PEG_Band"] = "Strong Buy"
    elif price <= fv_con:
        m["Lynch_PEG_Band"] = "Buy"
    elif price <= fv:
        m["Lynch_PEG_Band"] = "Hold"
    else:
        m["Lynch_PEG_Band"] = "Avoid"

    # Discount to Lynch buy price
    m["Lynch_Discount_Pct"] = round((1 - price / m["Lynch_BuyPrice"]) * 100, 1) if m["Lynch_BuyPrice"] > 0 else None

    return m


def graham_metrics(price: float, eps: float, g: float, aaa_yield: float,
                   pb: float | None) -> dict:
    """
    Compute Graham intrinsic value (both versions) and price bands.
    g is a whole-number percent, capped upstream.

    FORMULA AUDIT (Phase 5, FIX-01) — do NOT "fix" these without reading this:

    VA = eps * (8.5 + 2*g) * 4.4 / aaa_yield
         This IS the canonical 1974 revised Graham formula from The Intelligent
         Investor (Ch. 11).  8.5 = no-growth P/E, 2g = growth adjustment,
         4.4 = Graham's 1963 AAA reference yield.  ✓ matches source definition.

    VB = eps * (7 + g) * 4.4 / aaa_yield
         This is a practitioner-conservative variant (NOT from Graham's book).
         It uses a lower no-growth base P/E of 7 instead of Graham's 8.5, and
         applies the growth multiplier once (not 2×).  This deliberately
         produces lower fair values for quality franchises — which is the
         intended conservative behavior.

    FV = min(VA, VB)  → always picks the more conservative (lower) value.

    AUDIT CONCLUSION: Both formulas are algebraically correct relative to their
    definitions.  The "visibly wrong" buy prices are the expected output of a
    conservative model: quality franchises trading at justified premiums
    (e.g., KO at $70 with FV ≈ $28) will always show large negative discounts.
    This is model conservatism, not a code defect.  See tests/test_valuation_fixture.py.
    """
    m = {}

    if eps <= 0 or aaa_yield <= 0:
        return {"error": "Non-positive EPS or AAA yield"}

    g_capped = min(g, 15.0)  # Graham himself suggested capping at 15

    # Version A — classic 1974 rate-adjusted Graham formula (8.5 + 2g) × 4.4/Y
    m["Graham_VA"] = round(eps * (GRAHAM_NO_GROWTH_PE + 2 * g_capped) * GRAHAM_HIST_AAA / aaa_yield, 2)

    # Version B — conservative practitioner variant: base P/E 7 + g (NOT from Graham's book)
    m["Graham_VB"] = round(eps * (7 + g_capped) * GRAHAM_HIST_AAA / aaa_yield, 2)

    # Use the more conservative (lower) of the two — intentional, see audit note above
    m["Graham_FV"] = min(m["Graham_VA"], m["Graham_VB"])

    # Price band
    fv = m["Graham_FV"]
    if fv > 0:
        if price <= GRAHAM_DEEP_BUY * fv:
            m["Graham_Status"] = "Deep Buy"
        elif price <= GRAHAM_BUY * fv:
            m["Graham_Status"] = "Buy"
        elif price <= GRAHAM_WATCH * fv:
            m["Graham_Status"] = "Watch"
        else:
            m["Graham_Status"] = "Avoid"
        m["Graham_Discount_Pct"] = round((1 - price / fv) * 100, 1)
    else:
        m["Graham_Status"] = "N/A"
        m["Graham_Discount_Pct"] = None

    return m


def graham_defensive_score(
    market_cap_b: float | None,
    current_ratio: float | None,
    debt_equity: float | None,
    annual_eps: list,
    annual_dividends: list,
    price: float,
    eps_3yr_avg: float | None,
    pb: float | None,
) -> dict:
    """
    Score each Graham defensive-investor criterion (0 or 1 per check).
    Returns score, breakdown, and Pass/Borderline/Fail label.
    """
    checks = {}

    # 1) Size
    checks["Size_OK"]       = int(market_cap_b is not None and market_cap_b >= MIN_MARKET_CAP_B)

    # 2) Current ratio
    checks["CurrRatio_OK"]  = int(current_ratio is not None and current_ratio >= MIN_CURRENT_RATIO)

    # 3) Debt/Equity
    checks["DebtEq_OK"]     = int(debt_equity is not None and debt_equity <= MAX_DEBT_EQUITY)

    # 4) Earnings stability — positive EPS in 8 of last 10 years
    valid_eps = [e for e in annual_eps if e is not None and e == e]  # e == e filters np.nan
    pos_eps_yrs = sum(1 for e in valid_eps[-10:] if e > 0)
    checks["EPS_Stability"]  = int(pos_eps_yrs >= MIN_POSITIVE_EPS_YRS)

    # 5) Dividend record — paid in 5 of last 10 years
    div_years = sum(1 for d in annual_dividends[-10:] if d is not None and d > 0)
    checks["Div_Record"]    = int(div_years >= MIN_DIV_YEARS)

    # 6) 10-year EPS growth ≥ 33% cumulative
    if len(valid_eps) >= 10 and valid_eps[-10] > 0:
        cum_growth = (valid_eps[-1] / valid_eps[-10] - 1) * 100
        checks["EPS_Growth10Y"] = int(cum_growth >= MIN_EPS_GROWTH_10Y)
    else:
        checks["EPS_Growth10Y"] = 0

    # 7) P/E ≤ 15 (based on 3-yr avg EPS)
    if eps_3yr_avg and eps_3yr_avg > 0:
        pe_3yr = price / eps_3yr_avg
        checks["PE_Limit"]  = int(pe_3yr <= MAX_PE_GRAHAM)
    else:
        checks["PE_Limit"]  = 0

    # 8) P/B ≤ 1.5 OR P/E × P/B ≤ 22.5
    # The P/E×P/B branch is only meaningful with positive current EPS; a negative
    # EPS makes pe_cur negative and (pe_cur * pb) trivially ≤ 22.5, which would
    # award a spurious point (mirrors criterion 7's eps_3yr_avg > 0 guard).
    if pb and pb > 0:
        cur_eps = valid_eps[-1] if valid_eps else None
        pe_ok = cur_eps is not None and cur_eps > 0 and (price / cur_eps) * pb <= MAX_PE_X_PB
        checks["PB_Limit"]  = int(pb <= MAX_PB_GRAHAM or pe_ok)
    else:
        checks["PB_Limit"]  = 0

    score = sum(checks.values())

    if score >= DEFENSIVE_PASS_SCORE:
        label = "Pass"
    elif score >= DEFENSIVE_BORDER_SCORE:
        label = "Borderline"
    else:
        label = "Fail"

    return {"DefensiveScore": score, "DefensiveLabel": label, **checks}


def combined_score(lynch_discount: float | None, graham_discount: float | None) -> float | None:
    """
    Simple 50/50 blended price score (higher = cheaper relative to both frameworks).
    Each discount is clipped to [0, 60]%.
    """
    ld = min(max(lynch_discount or 0, 0), 60)
    gd = min(max(graham_discount or 0, 0), 60)
    if lynch_discount is None and graham_discount is None:
        return None
    return round(0.5 * ld + 0.5 * gd, 1)


# ═════════════════════════════════════════════
# STEP 5 — PROCESS ALL TICKERS
# ═════════════════════════════════════════════

def process_ticker(ticker: str, aaa_yield: float, risk_free_rate: float | None = None) -> dict:
    """Run the full pipeline for one ticker. Returns a flat result dict."""
    row = {"Ticker": ticker, "Error": None}

    def _r2(value):
        return round(float(value), 2) if value is not None else None

    # --- Fetch all data (yfinance price + history, Finnhub fundamentals) ---
    fund = get_combined_data(ticker)
    row["Provider_Finnhub_OK"] = bool(fund.get("finnhub_ok"))

    # ── Price ───────────────────────────────────────────────────────
    price = fund["price"]
    if not price:
        log.warning(f"{ticker}: no price data")
        row["Error"] = "No price"
        return row
    row["Price"]      = round(float(price), 2)
    mkt_cap_b         = fund["market_cap_b"]

    # ── EPS ─────────────────────────────────────────────────────────
    eps = fund["ttm_eps"]
    if eps is None:
        log.warning(f"{ticker}: EPS data is missing")
        row["Error"] = "No EPS"
        return row
    row["EPS_TTM"]    = round(float(eps), 4)
    row["EPS_Annual"] = str([round(e, 2) for e in fund["annual_eps"] if e is not None and e == e])

    # ── Dividend yield ───────────────────────────────────────────────
    dps = fund["ttm_dps"] or 0.0
    dy = round((float(dps) / float(price)) * 100, 4) if price and float(dps) > 0 else 0.0
    row["DivYield_Pct"] = round(dy, 2)

    # ── Growth — Finnhub 5Y CAGR, reality-anchored to realized EPS CAGR (Bug B) ──
    # Reconcile against the realized CAGR so an inflated Finnhub growth can't make a
    # flat/declining-EPS stock look like a 25% grower; falls back to computed CAGR
    # when Finnhub is absent. Negative reconciled growth is intercepted below and
    # routed to WORST_DISCOUNT (D-01) — not floored or dropped.
    g = _reconcile_growth(fund["growth_pct"], compute_growth_5yr_cagr(fund["annual_eps"]))
    if g is not None:
        g = min(g, GROWTH_CAP)
    # D-01: negative/zero growth is present-but-terrible; do NOT floor or drop.
    # Lynch/Graham are skipped for g <= 0 and route directly to WORST_DISCOUNT,
    # so the ticker remains available for other diagnostics.
    row["Growth_g_Pct"] = round(g, 2) if g is not None else None
    row["AAA_Yield"]    = aaa_yield
    row["MarketCap_B"]  = round(mkt_cap_b, 2) if mkt_cap_b else None

    valuation_warnings = []
    if eps <= 0:
        valuation_warnings.append("Non-positive EPS")
    if g is None:
        valuation_warnings.append("Growth unavailable")
    elif g <= 0:
        valuation_warnings.append("Non-positive growth")
    row["Valuation_Input_Warning"] = "; ".join(valuation_warnings) or None

    # ── P/B ratio — Finnhub direct, or compute from BVPS ────────────
    pb = fund["pb_ratio"]
    if pb is None:
        bvps = fund["book_value_ps"]
        pb   = round(float(price) / float(bvps), 2) if bvps and float(bvps) > 0 else None
    row["PB_Ratio"] = pb

    # ── 3-yr avg EPS for Graham P/E check ───────────────────────────
    valid_eps   = [e for e in fund["annual_eps"] if e is not None and e == e]
    eps_3yr_avg = sum(valid_eps[-3:]) / len(valid_eps[-3:]) if len(valid_eps) >= 3 else None

    # ── Lynch ───────────────────────────────────────────────────────
    # D-01: if negative/zero EPS or growth causes an error-return, retain the row
    # with WORST_DISCOUNT so it ranks at the bottom rather than being dropped.
    if eps <= 0 or g is None or g <= 0:
        lm = {"Lynch_Discount_Pct": WORST_DISCOUNT}
    else:
        lm = lynch_metrics(price, eps, g, dy)
        if "error" in lm:
            log.info(f"{ticker}: Lynch formula error ({lm['error']}), routing to WORST_DISCOUNT")
            lm = {"Lynch_Discount_Pct": WORST_DISCOUNT}
    row.update({f"Lynch_{k}": v for k, v in lm.items()})

    # ── Graham ──────────────────────────────────────────────────────
    # D-01: same sentinel routing for Graham error returns.
    if eps <= 0 or g is None or g <= 0:
        gm = {"Graham_Discount_Pct": WORST_DISCOUNT}
    else:
        gm = graham_metrics(price, eps, g, aaa_yield, pb)
        if "error" in gm:
            log.info(f"{ticker}: Graham formula error ({gm['error']}), routing to WORST_DISCOUNT")
            gm = {"Graham_Discount_Pct": WORST_DISCOUNT}
    row.update({f"Graham_{k}": v for k, v in gm.items()})

    # ── Graham defensive score ───────────────────────────────────────
    ds = graham_defensive_score(
        market_cap_b     = mkt_cap_b,
        current_ratio    = fund["current_ratio"],
        debt_equity      = fund["debt_equity"],
        annual_eps       = fund["annual_eps"],
        annual_dividends = fund["annual_dividends"],
        price            = price,
        eps_3yr_avg      = eps_3yr_avg,
        pb               = pb,
    )
    row.update(ds)

    # ── Combined score (retained column — D-02c) ─────────────────────
    row["CombinedScore"] = combined_score(
        lm.get("Lynch_Discount_Pct"),
        gm.get("Graham_Discount_Pct"),
    )

    # ── Growth stability — fraction of years with positive EPS ───────
    # Derived from annual_eps history (Open Question 2 from RESEARCH.md).
    # Formula: count of positive-EPS years / total available years.
    # None when fewer than 3 years available (D-01b: genuinely missing).
    # This reuses the EPS_Stability computation pattern already present in
    # graham_defensive_score rather than introducing a new formula.
    valid_eps_hist = [e for e in fund["annual_eps"] if e is not None and e == e]
    if len(valid_eps_hist) >= 3:
        pos_years   = sum(1 for e in valid_eps_hist if e > 0)
        growth_stability = pos_years / len(valid_eps_hist)
    else:
        growth_stability = None

    # ── Trap gate (TRAP-01 / D-04) ───────────────────────────────────
    # Bug A fix: the defensive EPS_Stability uses an 8-of-10-year rule, but yfinance
    # supplies only ~4 years, so it was structurally 0 and tripped the gate for EVERY
    # ticker (dead Safety pillar). Use a window-appropriate stability signal instead.
    eps_stab_for_gate = _eps_stable_for_gate(fund["annual_eps"])
    trap_fcf_metric = (
        fund["fcf_yield"] if fund.get("fcf_yield") is not None
        else fund["fcf_per_share"]
    )
    is_trap, cov_fraction = trap_gate(
        debt_equity   = fund["debt_equity"],
        current_ratio = fund["current_ratio"],
        eps_stability = eps_stab_for_gate,
        # Only the sign is used by trap_gate. Prefer the independently computed
        # yfinance FCF yield; fall back to Finnhub FCF/share when unavailable.
        fcf_per_share = trap_fcf_metric,
    )
    trap_reasons = _trap_reasons(
        fund["debt_equity"],
        fund["current_ratio"],
        eps_stab_for_gate,
        trap_fcf_metric,
    )

    # ── Distress signals + DCF (TRAP-03/SECTOR-02/SIGNAL-08/09/DCF-01..03) ───
    # Piotroski F-Score — no sector exclusion. Split the raw multi-year
    # statement (columns[0]=newest) into (curr, prev) per _compute_piotroski's
    # convention: prev is the same statement with the newest column dropped,
    # so prev.columns[0] becomes the prior year.
    def _prev_frame(df):
        if df is None or df.empty or df.shape[1] < 2:
            return None
        return df.iloc[:, 1:]

    inc_df = fund.get("income_stmt_df")
    bs_df  = fund.get("balance_sheet_df")
    cf_df  = fund.get("cashflow_df")
    piotroski_f = _compute_piotroski(
        inc_df, _prev_frame(inc_df),
        bs_df,  _prev_frame(bs_df),
        cf_df,  _prev_frame(cf_df),
    )

    altman_z = _compute_altman_z(bs_df, inc_df) if _sector_allows(fund, "altman") else None

    # Preserve the former EPS projection as a clearly named diagnostic. It is not
    # an FCFF/FCFE DCF and does not feed the DCF value sub-score.
    discounted_earnings_value = None
    discounted_earnings_discount = None
    discounted_earnings_implied_growth = None
    if _sector_allows(fund, "dcf") and eps > 0 and g is not None:
        legacy_growth = max(g, DCF_GROWTH_FLOOR)
        try:
            discounted_earnings_value, discounted_earnings_discount = (
                _compute_discounted_earnings_forward(
                    eps, legacy_growth, aaa_yield, price
                )
            )
            discounted_earnings_implied_growth, _ = (
                _compute_discounted_earnings_reverse(
                    price, eps, aaa_yield
                )
            )
        except ValueError as exc:
            log.warning(f"Discounted-earnings error for {ticker}: {exc}")

    dcf_result = None
    dcf_implied_growth = None
    dcf_reverse_converged = False
    dcf_growth_gap = None
    dcf_wacc = None
    wacc_detail = None
    wacc_guard = None
    dcf_terminal_growth = None
    dcf_price_currency = fund.get("price_currency")
    dcf_financial_currency = fund.get("financial_currency")
    dcf_currency_mismatch = _currency_mismatch(
        dcf_price_currency,
        dcf_financial_currency,
    )
    dcf_base_fcff = _compute_base_fcff(
        fund.get("ocf"),
        fund.get("capex"),
        fund.get("interest_expense"),
        fund.get("tax_rate", DCF_DEFAULT_TAX_RATE),
    )
    dcf_missing_inputs = []
    dcf_assumption_warnings = []

    if _sector_allows(fund, "dcf") and g is not None:
        market_cap = mkt_cap_b * 1e9 if mkt_cap_b is not None else None
        diluted_shares = fund.get("diluted_shares") or fund.get("shares_now")
        if diluted_shares is None and market_cap is not None and price > 0:
            diluted_shares = market_cap / price

        wacc_inputs = {
            "risk-free rate": risk_free_rate,
            "market cap": market_cap,
            "total debt": fund.get("total_debt"),
            "cash": fund.get("cash"),
            "diluted shares": diluted_shares,
            "base FCFF": dcf_base_fcff,
        }
        dcf_missing_inputs = [name for name, value in wacc_inputs.items() if value is None]
        if dcf_currency_mismatch:
            dcf_missing_inputs.append("compatible price and financial currencies")
            dcf_assumption_warnings.append(
                f"Currency mismatch ({dcf_price_currency} price vs "
                f"{dcf_financial_currency} financials); DCF excluded"
            )
        elif not dcf_price_currency or not dcf_financial_currency:
            dcf_assumption_warnings.append("Currency metadata incomplete")
        if dcf_base_fcff is not None and dcf_base_fcff <= 0:
            dcf_assumption_warnings.append("Non-positive base FCFF")
        if fund.get("beta") is None:
            dcf_assumption_warnings.append("Beta unavailable; defaulted to 1.0")
        if fund.get("interest_expense") is None and (fund.get("total_debt") or 0) > 0:
            dcf_assumption_warnings.append("Interest expense unavailable; AAA debt cost used")

        wacc_detail = _estimate_screen_wacc(
            risk_free_rate_pct=risk_free_rate,
            aaa_yield_pct=aaa_yield,
            beta=fund.get("beta"),
            market_cap=market_cap,
            total_debt=fund.get("total_debt"),
            prior_total_debt=fund.get("prior_total_debt"),
            interest_expense=fund.get("interest_expense"),
            tax_rate=fund.get("tax_rate", DCF_DEFAULT_TAX_RATE),
        )
        if not dcf_missing_inputs and wacc_detail is not None:
            dcf_terminal_growth = max(0.0, min(g, DCF_TERMINAL_GROWTH_CAP))
            wacc_guard = _apply_screen_wacc_guardrail(
                calculated_wacc=wacc_detail["wacc"],
                risk_free_rate_pct=risk_free_rate,
                terminal_growth_pct=dcf_terminal_growth,
            )
            dcf_wacc = wacc_guard["wacc"]
            if wacc_guard["floor_applied"]:
                dcf_assumption_warnings.append(
                    "WACC guardrail applied "
                    f"({wacc_guard['unfloored_wacc'] * 100.0:.2f}% to "
                    f"{dcf_wacc * 100.0:.2f}%)"
                )
            if wacc_detail["debt_weight"] > DCF_HIGH_DEBT_WEIGHT:
                dcf_assumption_warnings.append(
                    "High leverage makes DCF equity value highly sensitive"
                )
            try:
                dcf_result = _compute_fcff_dcf(
                    base_fcff=dcf_base_fcff,
                    initial_growth_pct=g,
                    wacc=dcf_wacc,
                    terminal_growth_pct=dcf_terminal_growth,
                    cash=fund["cash"],
                    total_debt=fund["total_debt"],
                    diluted_shares=diluted_shares,
                    price=price,
                )
                dcf_implied_growth, dcf_reverse_converged = _compute_fcff_reverse_dcf(
                    price=price,
                    base_fcff=dcf_base_fcff,
                    wacc=dcf_wacc,
                    terminal_growth_pct=dcf_terminal_growth,
                    cash=fund["cash"],
                    total_debt=fund["total_debt"],
                    diluted_shares=diluted_shares,
                )
                if dcf_implied_growth is not None and dcf_result is not None:
                    dcf_growth_gap = dcf_result["growth_used_pct"] - dcf_implied_growth
                if (
                    dcf_result is not None
                    and dcf_result["terminal_value_pct"] > DCF_HIGH_TERMINAL_VALUE_PCT
                ):
                    dcf_assumption_warnings.append(
                        f"Terminal value exceeds {DCF_HIGH_TERMINAL_VALUE_PCT:.0f}% of EV"
                    )
            except ValueError as exc:
                log.warning(f"FCFF DCF error for {ticker}: {exc}")

    dcf_intrinsic = dcf_result["intrinsic_value"] if dcf_result else None
    dcf_discount_pct = dcf_result["discount_pct"] if dcf_result else None
    dcf_cyclical_flag = (fund.get("sector") in CYCLICAL_SECTORS) and _sector_allows(fund, "dcf")

    # D-11: Financial Services excluded from EV/EBIT + earnings yield (None, never zero)
    earnings_yield = fund.get("earnings_yield") if _sector_allows(fund, "earnings_yield") else None
    ev_ebit        = fund.get("ev_ebit")        if _sector_allows(fund, "ev_ebit")        else None

    # ── Overall score (SCORE-01..08) ─────────────────────────────────
    # Pass the audited discount values from lm/gm (already sentinel-routed
    # to WORST_DISCOUNT for negative-input tickers via the D-01 intercepts
    # above, so negative-input rows reach here and receive Value=0).
    scores = overall_score(
        lynch_discount      = lm.get("Lynch_Discount_Pct"),
        graham_discount     = gm.get("Graham_Discount_Pct"),
        defensive_score     = ds.get("DefensiveScore"),
        debt_equity         = fund["debt_equity"],
        current_ratio       = fund["current_ratio"],
        growth_g            = g,
        growth_stability    = growth_stability,
        coverage_fraction   = cov_fraction,
        aaa_yield           = aaa_yield,
        fcf_yield           = fund.get("fcf_yield"),
        earnings_yield      = earnings_yield,
        shareholder_yield   = fund.get("shareholder_yield"),
        roic                = fund.get("roic"),
        dist_52w_low        = fund.get("dist_52w_low"),
        dist_52w_high       = fund.get("dist_52w_high"),
        dist_5y_low         = fund.get("dist_5y_low"),
        weeks_since_52w_low = fund.get("weeks_since_52w_low"),
        weeks_since_5y_low  = fund.get("weeks_since_5y_low"),
        piotroski_f         = piotroski_f,
        altman_z            = altman_z,
        dcf_discount_pct    = dcf_discount_pct,
    )

    # Merge flat score columns (additive — existing keys untouched, D-02c)
    row["OverallScore"]          = scores["overall"]
    row["score_value"]           = scores["value"]
    row["score_value_discount"]  = scores["value_discount"]
    row["score_value_yield"]     = scores["value_yield"]
    row["score_value_price"]     = scores["value_price"]
    row["score_quality"]         = scores["quality"]
    row["score_growth"]          = scores["growth"]
    row["score_safety"]          = scores["safety"]
    row["is_trap"]               = is_trap
    row["Trap_Reasons"]           = "; ".join(trap_reasons) or None
    row["coverage_pct"]          = scores["coverage_pct"]

    # Phase 7 additive columns — distress signals + DCF (diagnostic + scoring)
    row["Piotroski_F"]           = piotroski_f  # int | None (no rounding)
    row["Altman_Z"]               = round(float(altman_z), 2) if altman_z is not None else None
    row["DCF_Intrinsic_Value"]    = round(float(dcf_intrinsic), 2) if dcf_intrinsic is not None else None
    row["DCF_Value_Low"]          = _r2(dcf_result["value_low"]) if dcf_result else None
    row["DCF_Value_High"]         = _r2(dcf_result["value_high"]) if dcf_result else None
    row["DCF_Discount_Pct"]       = round(float(dcf_discount_pct), 2) if dcf_discount_pct is not None else None
    row["DCF_Implied_Growth"]     = round(float(dcf_implied_growth), 2) if dcf_implied_growth is not None else None
    row["DCF_Growth_Used_Pct"]    = _r2(dcf_result["growth_used_pct"]) if dcf_result else None
    row["DCF_Growth_Gap_Pct"]     = round(float(dcf_growth_gap), 2) if dcf_growth_gap is not None else None
    row["DCF_WACC_Pct"]           = round(dcf_wacc * 100.0, 2) if dcf_wacc is not None else None
    row["DCF_WACC_Unfloored_Pct"] = _r2(wacc_guard["unfloored_wacc"] * 100.0) if wacc_guard else None
    row["DCF_WACC_Floor_Applied"] = wacc_guard["floor_applied"] if wacc_guard else False
    row["DCF_Beta"]               = _r2(wacc_detail["beta"]) if wacc_detail else None
    row["DCF_Cost_Equity_Pct"]    = _r2(wacc_detail["cost_of_equity"] * 100.0) if wacc_detail else None
    row["DCF_PreTax_Cost_Debt_Pct"] = _r2(wacc_detail["pre_tax_cost_of_debt"] * 100.0) if wacc_detail else None
    row["DCF_Debt_Weight_Pct"]    = _r2(wacc_detail["debt_weight"] * 100.0) if wacc_detail else None
    row["DCF_Terminal_Growth_Pct"] = _r2(dcf_terminal_growth)
    row["DCF_Terminal_Value_Pct"] = _r2(dcf_result["terminal_value_pct"]) if dcf_result else None
    row["DCF_Base_FCFF_B"]        = _r2(dcf_base_fcff / 1e9) if dcf_base_fcff is not None else None
    row["DCF_Price_Currency"]     = dcf_price_currency
    row["DCF_Financial_Currency"] = dcf_financial_currency
    row["DCF_Currency_Mismatch"]  = dcf_currency_mismatch
    row["DCF_Method"]              = "FCFF screen-grade" if dcf_result else None
    row["DCF_Data_Warning"]        = (
        "; ".join(
            (["Missing " + ", ".join(dcf_missing_inputs)] if dcf_missing_inputs else [])
            + dcf_assumption_warnings
        ) or None
    )
    row["dcf_reverse_converged"]  = dcf_reverse_converged
    row["DCF_Cyclical_Flag"]      = dcf_cyclical_flag
    row["Discounted_Earnings_Value"] = _r2(discounted_earnings_value)
    row["Discounted_Earnings_Discount_Pct"] = _r2(discounted_earnings_discount)
    row["Discounted_Earnings_Implied_Growth"] = _r2(discounted_earnings_implied_growth)
    row["score_piotroski_sub"]    = scores["piotroski"]
    row["score_altman_sub"]       = scores["altman"]
    row["score_dcf_discount_sub"] = scores["dcf_discount"]

    # ── Phase 6 additive columns — sector + price signals + factors ──
    # Sector (SECTOR-01, D-02)
    row["Sector"] = fund["sector"]

    # Price-distance/recency signals (SIGNAL-01/02/03, D-03)
    row["Dist_52w_High_Pct"]    = _r2(fund["dist_52w_high"])
    row["Dist_52w_Low_Pct"]     = _r2(fund["dist_52w_low"])
    row["Dist_5y_Low_Pct"]      = _r2(fund["dist_5y_low"])
    row["Weeks_Since_52w_Low"]  = _r2(fund["weeks_since_52w_low"])
    row["Weeks_Since_5y_Low"]   = _r2(fund["weeks_since_5y_low"])
    row["short_history"]        = fund["short_history"]

    # Fundamental factors (SIGNAL-04/05/06/07, D-01)
    row["FCF_Yield_Pct"]          = _r2(fund["fcf_yield"])
    row["EV_EBIT"]                = _r2(ev_ebit)
    row["Earnings_Yield_Pct"]     = _r2(earnings_yield)
    row["ROIC_Pct"]               = _r2(fund["roic"])
    row["Shareholder_Yield_Pct"]  = _r2(fund["shareholder_yield"])
    row["shareholder_yield_partial"] = fund["shareholder_yield_partial"]

    # ── Show? — at least one Buy signal ─────────────────────────────
    buy_signals = {"Strong Buy", "Buy", "Deep Buy"}
    lynch_buy   = lm.get("Lynch_Status") in buy_signals or lm.get("Lynch_PEG_Band") in buy_signals
    graham_buy  = gm.get("Graham_Status") in buy_signals
    row["Show"] = lynch_buy or graham_buy

    return row


def run_screener(
    universe: pd.DataFrame,
    aaa_yield: float,
    risk_free_rate: float | None = None,
) -> pd.DataFrame:
    results = []
    total = len(universe)
    for i, row in universe.iterrows():
        ticker = row["ticker"]
        log.info(f"[{i+1}/{total}] Processing {ticker}...")
        result = process_ticker(ticker, aaa_yield, risk_free_rate)
        result["Indexes"] = row["indexes"]
        results.append(result)
    df = pd.DataFrame(results)
    # Sort by OverallScore descending (SCORE-08 / D-02c).
    # CombinedScore is retained as a column — only the sort key changes.
    if "OverallScore" in df.columns:
        df = df.sort_values("OverallScore", ascending=False, na_position="last")
    elif "CombinedScore" in df.columns:
        df = df.sort_values("CombinedScore", ascending=False, na_position="last")
    return df


# ═════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════

OUTPUT_PATH     = Path("docs/data/results.json")
STATS_PATH      = Path("docs/data/stats.json")
SNAPSHOTS_DIR   = Path("docs/data/snapshots")
SNAPSHOTS_INDEX = SNAPSHOTS_DIR / "index.json"

MIN_OUTPUT_ROWS = 100
MIN_VALID_ROWS = 100
MIN_VALID_FRACTION = 0.60
MIN_FINNHUB_VALID_FRACTION = 0.60
MIN_DCF_ROWS = 100

# [ASSUMED] — no empirical anchor; low_safety_count flags rows the Safety
# pillar considers distressed. Replaces the old is_trap count (Phase 7 PAGE-02).
LOW_SAFETY_THRESHOLD = 30.0


def _is_first_weekday_of_month(day) -> bool:
    """Return True only for the first Monday-Friday date in day’s month."""
    first = day.replace(day=1)
    weekend_offset = 7 - first.weekday() if first.weekday() > 4 else 0
    return day == first + timedelta(days=weekend_offset)


def _compute_stats(df: pd.DataFrame) -> dict:
    """
    Compute universe-level aggregate stats for stats.html (PAGE-02 / D-15).
    Pure DataFrame transform — no I/O. Columns not present in `df` (e.g. in
    unit-test fixtures that only populate a subset of fields) are treated as
    entirely absent rather than raising.
    internal — for tests only.
    """
    universe_count = len(df)

    show_col = df["Show"] if "Show" in df.columns else None
    buy_signal_count = int(show_col.fillna(False).astype(bool).sum()) if show_col is not None else 0

    safety_col = df["score_safety"] if "score_safety" in df.columns else None
    low_safety_count = int((safety_col.dropna() < LOW_SAFETY_THRESHOLD).sum()) if safety_col is not None else 0

    # score_distribution — 5 buckets over OverallScore
    buckets = {"0_20": 0, "20_40": 0, "40_60": 0, "60_80": 0, "80_100": 0}
    overall_col = df["OverallScore"] if "OverallScore" in df.columns else None
    if overall_col is not None:
        for v in overall_col.dropna():
            if v < 20:
                buckets["0_20"] += 1
            elif v < 40:
                buckets["20_40"] += 1
            elif v < 60:
                buckets["40_60"] += 1
            elif v < 80:
                buckets["60_80"] += 1
            else:
                buckets["80_100"] += 1

    # pillar_averages — mean of each pillar sub-score over non-null rows
    pillar_averages = {}
    for pillar, col_name in (
        ("value", "score_value"), ("quality", "score_quality"),
        ("growth", "score_growth"), ("safety", "score_safety"),
    ):
        col = df[col_name] if col_name in df.columns else None
        vals = col.dropna() if col is not None else None
        pillar_averages[pillar] = round(float(vals.mean()), 2) if vals is not None and len(vals) > 0 else None

    # sector_breakdown — group by Sector (None -> "Unknown"), sorted by count desc
    breakdown = []
    if "Sector" in df.columns:
        tmp = df.copy()
        tmp["_sector"] = tmp["Sector"].fillna("Unknown").replace("", "Unknown")
        for sector_name, group in tmp.groupby("_sector"):
            overall_vals = group["OverallScore"].dropna() if "OverallScore" in group.columns else None
            avg_score = round(float(overall_vals.mean()), 2) if overall_vals is not None and len(overall_vals) > 0 else None
            buy_count = int(group["Show"].fillna(False).astype(bool).sum()) if "Show" in group.columns else 0
            breakdown.append({
                "sector":           sector_name,
                "count":            int(len(group)),
                "avg_score":        avg_score,
                "buy_signal_count": buy_count,
            })
        breakdown.sort(key=lambda b: b["count"], reverse=True)

    # coverage_stats
    cov_col = df["coverage_pct"] if "coverage_pct" in df.columns else None
    cov_vals = cov_col.dropna() if cov_col is not None else None
    coverage_stats = {
        "avg_coverage_pct": round(float(cov_vals.mean()), 2) if cov_vals is not None and len(cov_vals) > 0 else None,
    }
    finnhub_col = df["Provider_Finnhub_OK"] if "Provider_Finnhub_OK" in df.columns else None
    finnhub_ok_rows = (
        int(finnhub_col.fillna(False).astype(bool).sum())
        if finnhub_col is not None
        else 0
    )
    coverage_stats["finnhub_ok_rows"] = finnhub_ok_rows
    coverage_stats["finnhub_coverage_pct"] = (
        round(finnhub_ok_rows / len(df) * 100.0, 2) if len(df) else None
    )
    for key, col_name in (
        ("tickers_with_piotroski", "Piotroski_F"),
        ("tickers_with_altman",    "Altman_Z"),
        ("tickers_with_dcf",       "DCF_Intrinsic_Value"),
        ("tickers_with_fcf_yield", "FCF_Yield_Pct"),
    ):
        col = df[col_name] if col_name in df.columns else None
        coverage_stats[key] = int(col.notna().sum()) if col is not None else 0

    return {
        "generated_at":       datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "universe_count":     universe_count,
        "buy_signal_count":   buy_signal_count,
        "low_safety_count":   low_safety_count,
        "score_distribution": buckets,
        "pillar_averages":    pillar_averages,
        "sector_breakdown":   breakdown,
        "coverage_stats":     coverage_stats,
    }


def _validate_output_dataframe(df: pd.DataFrame) -> dict:
    """Reject structurally complete-looking output that is not decision-useful."""
    total_rows = len(df)
    if total_rows < MIN_OUTPUT_ROWS:
        raise ValueError(
            f"Only {total_rows} rows produced; minimum total is {MIN_OUTPUT_ROWS}"
        )

    required_columns = {
        "Ticker",
        "Price",
        "OverallScore",
        "Error",
        "Provider_Finnhub_OK",
        "DCF_Intrinsic_Value",
        "DCF_Value_Low",
        "DCF_Value_High",
        "DCF_WACC_Pct",
        "DCF_Terminal_Growth_Pct",
        "DCF_Terminal_Value_Pct",
    }
    missing_columns = sorted(required_columns - set(df.columns))
    if missing_columns:
        raise ValueError(f"Output is missing required columns: {', '.join(missing_columns)}")

    ticker_values = df["Ticker"].fillna("").astype(str).str.strip()
    missing_ticker_count = int(ticker_values.eq("").sum())
    if missing_ticker_count:
        raise ValueError(f"Output contains {missing_ticker_count} blank ticker rows")

    duplicate_count = int(ticker_values.duplicated().sum())
    if duplicate_count:
        raise ValueError(f"Output contains {duplicate_count} duplicate ticker rows")

    valid_mask = df["Error"].isna() & df["OverallScore"].notna()
    valid_rows = int(valid_mask.sum())
    valid_fraction = valid_rows / total_rows if total_rows else 0.0
    if valid_rows < MIN_VALID_ROWS:
        raise ValueError(
            f"Only {valid_rows} valid scored rows produced; minimum is {MIN_VALID_ROWS}"
        )
    if valid_fraction < MIN_VALID_FRACTION:
        raise ValueError(
            f"Only {valid_fraction:.1%} of rows are valid and scored; "
            f"minimum is {MIN_VALID_FRACTION:.0%}"
        )

    finnhub_rows = int(df["Provider_Finnhub_OK"].eq(True).sum())
    finnhub_fraction = finnhub_rows / total_rows if total_rows else 0.0
    if finnhub_fraction < MIN_FINNHUB_VALID_FRACTION:
        raise ValueError(
            f"Only {finnhub_fraction:.1%} of rows have valid Finnhub data; "
            f"minimum is {MIN_FINNHUB_VALID_FRACTION:.0%}"
        )

    dcf_rows = df[df["Error"].isna() & df["DCF_Intrinsic_Value"].notna()].copy()
    dcf_count = len(dcf_rows)
    if dcf_count < MIN_DCF_ROWS:
        raise ValueError(
            f"Only {dcf_count} valid FCFF DCF rows produced; minimum is {MIN_DCF_ROWS}"
        )
    if bool((dcf_rows["DCF_Intrinsic_Value"] <= 0).any()):
        raise ValueError("FCFF DCF output contains non-positive intrinsic values")

    range_columns = ["DCF_Value_Low", "DCF_Intrinsic_Value", "DCF_Value_High"]
    missing_range_count = int(dcf_rows[range_columns].isna().any(axis=1).sum())
    if missing_range_count:
        raise ValueError(f"FCFF DCF output contains {missing_range_count} incomplete ranges")
    invalid_range_count = int(
        (
            (dcf_rows["DCF_Value_Low"] > dcf_rows["DCF_Intrinsic_Value"])
            | (dcf_rows["DCF_Value_High"] < dcf_rows["DCF_Intrinsic_Value"])
        ).sum()
    )
    if invalid_range_count:
        raise ValueError(f"FCFF DCF output contains {invalid_range_count} misordered ranges")

    invalid_rate_count = int(
        (dcf_rows["DCF_WACC_Pct"] <= dcf_rows["DCF_Terminal_Growth_Pct"]).sum()
    )
    if invalid_rate_count:
        raise ValueError(
            f"FCFF DCF output contains {invalid_rate_count} rows with WACC at or below terminal growth"
        )
    invalid_terminal_count = int(
        (
            (dcf_rows["DCF_Terminal_Value_Pct"] < 0)
            | (dcf_rows["DCF_Terminal_Value_Pct"] > 100)
        ).sum()
    )
    if invalid_terminal_count:
        raise ValueError(
            f"FCFF DCF output contains {invalid_terminal_count} invalid terminal-value shares"
        )

    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "valid_fraction": valid_fraction,
        "finnhub_rows": finnhub_rows,
        "finnhub_fraction": finnhub_fraction,
        "dcf_rows": dcf_count,
    }


def write_json(df: pd.DataFrame) -> None:
    try:
        validation = _validate_output_dataframe(df)
    except ValueError as exc:
        log.error(f"Aborting JSON write: {exc}")
        raise

    log.info(
        "Output validation passed: "
        f"{validation['valid_rows']}/{validation['total_rows']} valid scored rows "
        f"({validation['valid_fraction']:.1%}); "
        f"Finnhub {validation['finnhub_fraction']:.1%}; "
        f"FCFF DCF {validation['dcf_rows']} rows"
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = json.loads(df.to_json(orient="records"))
    # Build nested scores object post-serialization (SCORE-05 / Pitfall 3).
    # Constructing here rather than storing a dict in a DataFrame column avoids
    # pandas dict-column edge cases (Pitfall 3 preferred approach).
    for row in rows:
        row["scores"] = {
            "overall":        row.get("OverallScore"),
            "value":          row.get("score_value"),
            "value_discount": row.get("score_value_discount"),
            "value_yield":    row.get("score_value_yield"),
            "value_price":    row.get("score_value_price"),
            "quality":        row.get("score_quality"),
            "growth":         row.get("score_growth"),
            "safety":         row.get("score_safety"),
            "coverage_pct":   row.get("coverage_pct"),
            "trap":           row.get("is_trap", False),
            # Phase 7 additions
            "piotroski":      row.get("score_piotroski_sub"),
            "altman":         row.get("score_altman_sub"),
            "dcf_discount":   row.get("score_dcf_discount_sub"),
        }
    payload = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )
    log.info(f"Results written to {OUTPUT_PATH} ({len(rows)} rows)")

    # Phase 7 (PAGE-02 / D-15) — universe-level stats for stats.html.
    # No separate row-count guard needed: this code path is unreachable when
    # len(df) < 100 (the guard above already exits).
    stats = _compute_stats(df)
    STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATS_PATH.write_text(json.dumps(stats, separators=(",", ":")), encoding="utf-8")
    log.info(f"Stats written to {STATS_PATH}")


def update_snapshot_manifest(filename: str) -> None:
    """
    Append `filename` to the docs/data/snapshots/index.json manifest (D-13).

    Ensures SNAPSHOTS_DIR exists, loads the existing manifest (or starts a
    fresh {"snapshots": []} one), appends `filename` if not already present,
    sorts the list, and writes it back compact.

    NOT called during normal screener runs — snapshots are monthly, driven
    by the "first weekday of month" check in .github/workflows/screener.yml,
    which invokes this via `python -c "import stock_screener; ..."` only when
    that condition is met.
    """
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    if SNAPSHOTS_INDEX.exists():
        manifest = json.loads(SNAPSHOTS_INDEX.read_text(encoding="utf-8"))
    else:
        manifest = {"snapshots": []}
    if filename not in manifest["snapshots"]:
        manifest["snapshots"].append(filename)
    manifest["snapshots"].sort()
    SNAPSHOTS_INDEX.write_text(
        json.dumps(manifest, separators=(",", ":")),
        encoding="utf-8",
    )
    log.info(f"Snapshot manifest updated: {filename} ({SNAPSHOTS_INDEX})")


def main():
    log.info("═══ Lynch & Graham Screener Starting ═══")

    # 1. Build universe
    universe = get_universe()

    # 2. Fetch market discount-rate anchors
    aaa_yield = fetch_aaa_yield()
    risk_free_rate = fetch_risk_free_rate()
    _validate_finnhub_access()

    # 3. Process all tickers
    results_df = run_screener(universe, aaa_yield, risk_free_rate)

    # 4. Write JSON output
    write_json(results_df)

    log.info("═══ Done ═══")
    log.info(f"Total tickers processed: {len(results_df)}")
    if "Show" in results_df.columns:
        log.info(f"Rows with Buy signals:   {results_df['Show'].astype(str).eq('True').sum()}")
    else:
        log.info("Rows with Buy signals:   0 (no tickers passed valuation filters)")


if __name__ == "__main__":
    main()
