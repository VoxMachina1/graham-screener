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
import sys
import json
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from fredapi import Fred
from dotenv import load_dotenv

# Load .env when running locally; no-op in GitHub Actions (env vars already set)
load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURATION — all values come from env vars
# ─────────────────────────────────────────────
FRED_API_KEY     = os.environ["FRED_API_KEY"]
FINNHUB_API_KEY  = os.environ["FINNHUB_API_KEY"]

# Screener parameters
GROWTH_CAP          = 25.0   # cap 'g' at this % to prevent distortion
GRAHAM_NO_GROWTH_PE = 8.5    # classic Graham baseline P/E; change to 7 for conservative
GRAHAM_HIST_AAA     = 4.4    # Graham's original historical AAA yield constant
FRED_AAA_SERIES     = "AAA"  # Moody's AAA corporate bond yield series on FRED

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

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)


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
    tables = _wiki_tables("https://en.wikipedia.org/wiki/Nasdaq-100")
    for t in tables:
        if "Ticker" in t.columns:
            tickers = set(t["Ticker"].str.replace(".", "-", regex=False).tolist())
            log.info(f"  → {len(tickers)} Nasdaq-100 tickers")
            return tickers
    raise ValueError("Could not find Nasdaq-100 constituents table on Wikipedia.")


def get_universe() -> pd.DataFrame:
    """Return a deduplicated DataFrame with columns: ticker, indexes."""
    sp500   = fetch_sp500()
    dow30   = fetch_dow30()
    nasdaq  = fetch_nasdaq100()
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
    log.info("Fetching AAA yield from FRED...")
    fred = Fred(api_key=FRED_API_KEY)
    series = fred.get_series(FRED_AAA_SERIES)
    yield_val = float(series.dropna().iloc[-1])
    log.info(f"  → AAA yield: {yield_val:.2f}%")
    return yield_val


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
    try:
        r = requests.get(
            f"{FINNHUB_BASE}/stock/metric",
            params={"symbol": ticker, "metric": "all", "token": FINNHUB_API_KEY},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json().get("metric", {})
        log.warning(f"Finnhub {r.status_code} for {ticker}")
    except Exception as e:
        log.warning(f"Finnhub error for {ticker}: {e}")
    return {}


def _safe_float(v) -> float | None:
    """Return float or None for any null-like value including np.nan."""
    try:
        f = float(v)
        return None if f != f else f   # f != f is True only for nan
    except (TypeError, ValueError):
        return None


def get_yf_price_and_history(ticker: str) -> dict:
    """
    Fetch price and historical EPS (for defensive checks) from yfinance.
    Returns: { price, annual_eps, annual_dividends }
    """
    result = {"price": None, "annual_eps": [], "annual_dividends": []}
    try:
        t = yf.Ticker(ticker)

        # ── Price ───────────────────────────────────────────────────────
        fi = t.fast_info
        result["price"] = getattr(fi, "last_price", None)

        # ── Historical EPS (for 10yr defensive checks) ──────────────────
        inc = t.income_stmt
        if inc is not None and not inc.empty:
            inc = inc.sort_index(axis=1)  # oldest→newest
            for label in ["Basic EPS", "Diluted EPS", "Basic Eps", "Diluted Eps"]:
                if label in inc.index:
                    result["annual_eps"] = [_safe_float(v) for v in inc.loc[label].values]
                    break

        # ── Dividend history ────────────────────────────────────────────
        divs = t.dividends
        if divs is not None and not divs.empty:
            divs.index = divs.index.tz_localize(None) if divs.index.tz else divs.index
            annual_divs = divs.resample("YE").sum()
            result["annual_dividends"] = [float(v) for v in annual_divs.values[-10:]]

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
    if not ttm_eps and yf_data["annual_eps"]:
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
    if fh_mktcap:
        mkt_cap_b = fh_mktcap / 1000.0  # millions → billions

    # ── Balance sheet ratios (Finnhub direct) ───────────────────────
    current_ratio = _safe_float(fh.get("currentRatioAnnual") or fh.get("currentRatioQuarterly"))
    debt_equity   = _safe_float(fh.get("totalDebt/totalEquityAnnual"))
    book_value_ps = _safe_float(fh.get("bookValuePerShareAnnual") or fh.get("bookValuePerShareQuarterly"))
    pb_ratio      = _safe_float(fh.get("pb"))

    return {
        "price":            price,
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
    if pb and pb > 0:
        pe_cur = price / (valid_eps[-1] if valid_eps else 1)
        checks["PB_Limit"]  = int(pb <= MAX_PB_GRAHAM or (pe_cur * pb) <= MAX_PE_X_PB)
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

def process_ticker(ticker: str, aaa_yield: float) -> dict:
    """Run the full pipeline for one ticker. Returns a flat result dict."""
    row = {"Ticker": ticker}

    # --- Fetch all data (yfinance price + history, Finnhub fundamentals) ---
    fund = get_combined_data(ticker)

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
    if not eps or eps <= 0:
        log.warning(f"{ticker}: no usable EPS")
        row["Error"] = "No EPS"
        return row
    row["EPS_TTM"]    = round(float(eps), 4)
    row["EPS_Annual"] = str([round(e, 2) for e in fund["annual_eps"] if e is not None and e == e])

    # ── Dividend yield ───────────────────────────────────────────────
    dps = fund["ttm_dps"] or 0.0
    dy = round((float(dps) / float(price)) * 100, 4) if price and float(dps) > 0 else 0.0
    row["DivYield_Pct"] = round(dy, 2)

    # ── Growth — use Finnhub 5Y CAGR, fall back to computed CAGR ────
    g = fund["growth_pct"]
    if g is None:
        # Fallback: compute from yfinance EPS history
        g = compute_growth_5yr_cagr(fund["annual_eps"])
    if g is None:
        log.info(f"{ticker}: growth not computable, skipping valuation")
        row["Error"] = "Growth N/A"
        return row
    g = min(g, GROWTH_CAP)
    if g <= 0:
        log.info(f"{ticker}: negative/zero growth ({g:.1f}%), flooring to 1%")
        g = 1.0
    row["Growth_g_Pct"] = round(g, 2)
    row["AAA_Yield"]    = aaa_yield
    row["MarketCap_B"]  = round(mkt_cap_b, 2) if mkt_cap_b else None

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
    lm = lynch_metrics(price, eps, g, dy)
    row.update({f"Lynch_{k}": v for k, v in lm.items()})

    # ── Graham ──────────────────────────────────────────────────────
    gm = graham_metrics(price, eps, g, aaa_yield, pb)
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

    # ── Combined score ───────────────────────────────────────────────
    row["CombinedScore"] = combined_score(
        lm.get("Lynch_Discount_Pct"),
        gm.get("Graham_Discount_Pct"),
    )

    # ── Show? — at least one Buy signal ─────────────────────────────
    buy_signals = {"Strong Buy", "Buy", "Deep Buy"}
    lynch_buy   = lm.get("Lynch_Status") in buy_signals or lm.get("Lynch_PEG_Band") in buy_signals
    graham_buy  = gm.get("Graham_Status") in buy_signals
    row["Show"] = lynch_buy or graham_buy

    return row


def run_screener(universe: pd.DataFrame, aaa_yield: float) -> pd.DataFrame:
    results = []
    total = len(universe)
    for i, row in universe.iterrows():
        ticker = row["ticker"]
        log.info(f"[{i+1}/{total}] Processing {ticker}...")
        result = process_ticker(ticker, aaa_yield)
        result["Indexes"] = row["indexes"]
        results.append(result)
    df = pd.DataFrame(results)
    # Sort by CombinedScore descending (best opportunities first)
    if "CombinedScore" in df.columns:
        df = df.sort_values("CombinedScore", ascending=False, na_position="last")
    return df


# ═════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════

OUTPUT_PATH = Path("docs/data/results.json")


def write_json(df: pd.DataFrame) -> None:
    if len(df) < 100:
        log.error(
            f"Only {len(df)} rows produced — aborting JSON write (minimum 100 required)"
        )
        sys.exit(1)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = json.loads(df.to_json(orient="records"))
    payload = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )
    log.info(f"Results written to {OUTPUT_PATH} ({len(rows)} rows)")


def main():
    log.info("═══ Lynch & Graham Screener Starting ═══")

    # 1. Build universe
    universe = get_universe()

    # 2. Fetch AAA yield
    aaa_yield = fetch_aaa_yield()

    # 3. Process all tickers
    results_df = run_screener(universe, aaa_yield)

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
