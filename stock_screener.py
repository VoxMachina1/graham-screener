"""
Lynch & Graham Stock Screener
==============================
Fetches S&P 500, Dow 30, and Nasdaq-100 constituents dynamically,
pulls fundamentals from Tiingo, AAA yield from FRED, computes
Lynch and Graham valuation metrics, and pushes results to Google Sheets.

Local setup:
    1. Copy .env.example to .env and fill in your credentials.
    2. Share your Google Sheet with your service account email.
    3. Run: python stock_screener.py

GitHub Actions setup:
    Add each variable from .env.example as a repository secret
    (Settings → Secrets and variables → Actions).
    The provided workflow file handles injection automatically.
"""

import os
import sys
import json
import time
import logging
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from fredapi import Fred
from dotenv import load_dotenv

import gspread
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account

# Load .env when running locally; no-op in GitHub Actions (env vars already set)
load_dotenv()

# ─────────────────────────────────────────────
# CONFIGURATION — all values come from env vars
# ─────────────────────────────────────────────
# Comma-separated list of Tiingo API keys.
# The script rotates to the next key automatically on a 429 rate-limit response.
# Example: TIINGO_API_KEYS=key_one,key_two,key_three
# Optional — not currently used for any active data fetching.
# Include if you plan to add Tiingo-specific features later.
TIINGO_API_KEYS = [k.strip() for k in os.environ.get("TIINGO_API_KEYS", "").split(",") if k.strip()]
FRED_API_KEY     = os.environ["FRED_API_KEY"]
FINNHUB_API_KEY  = os.environ["FINNHUB_API_KEY"]


# Google Sheets
# Locally:  set GSHEET_CREDS_JSON to the path of your service account JSON file.
# Actions:  set GSHEET_CREDS_JSON to the entire JSON content as a secret (see README).
GSHEET_CREDS_JSON   = os.environ["GSHEET_CREDS_JSON"]
GSHEET_SPREADSHEET  = os.environ.get("GSHEET_SPREADSHEET", "Lynch & Graham Screener")
GSHEET_WORKSHEET    = os.environ.get("GSHEET_WORKSHEET",   "Results")

# Screener parameters
GROWTH_CAP          = 25.0   # cap 'g' at this % to prevent distortion
GRAHAM_NO_GROWTH_PE = 8.5    # classic Graham baseline P/E; change to 7 for conservative
GRAHAM_HIST_AAA     = 4.4    # Graham's original historical AAA yield constant
FRED_AAA_SERIES     = "AAA"  # Moody's AAA corporate bond yield series on FRED
TIINGO_DELAY_SEC    = 0.25   # polite delay between Tiingo calls (rate limiting)

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
    if not ttm_eps and yf_data["annual_eps"]:
        valid = [e for e in yf_data["annual_eps"] if e is not None and e == e]
        ttm_eps = valid[-1] if valid else None

    # ── EPS growth — Finnhub pre-calculated CAGR ────────────────────
    # Prefer 5Y, fall back to 3Y, then compute from history
    growth_pct = _safe_float(fh.get("epsGrowth5Y") or fh.get("epsGrowth3Y"))

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

    # Category
    if g < 5:
        cat = "Slow"
    elif g <= 12:
        cat = "Stalwart"
    else:
        cat = "Fast"
    m["Lynch_Category"] = cat
    m["Lynch_BuyPrice"] = round(m["FV_PEG_Con"] * LYNCH_DISCOUNT[cat], 2)

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
    """
    m = {}

    if eps <= 0 or aaa_yield <= 0:
        return {"error": "Non-positive EPS or AAA yield"}

    g_capped = min(g, 15.0)  # Graham himself suggested capping at 15

    # Version A — classic rate-adjusted
    m["Graham_VA"] = round(eps * (GRAHAM_NO_GROWTH_PE + 2 * g_capped) * GRAHAM_HIST_AAA / aaa_yield, 2)

    # Version B — conservative (lower base PE, single g multiplier)
    m["Graham_VB"] = round(eps * (7 + g_capped) * GRAHAM_HIST_AAA / aaa_yield, 2)

    # Use the more conservative (lower) of the two
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
    time.sleep(TIINGO_DELAY_SEC)

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
    dy = fund["ttm_dps"] or 0.0
    row["DivYield_Pct"] = round(float(dy), 2)

    # ── Growth — use Finnhub 5Y CAGR, fall back to computed CAGR ────
    g = fund["growth_pct"]
    if g is None:
        # Fallback: compute from yfinance EPS history
        g = compute_growth_5yr_cagr(fund["annual_eps"])
    if g is None:
        log.info(f"{ticker}: growth not computable, skipping valuation")
        row["Error"] = "Growth N/A"
        return row
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
# STEP 6 — PUSH TO GOOGLE SHEETS
# ═════════════════════════════════════════════

# ── Traffic light color maps ─────────────────────────────────────────────────
# Each entry: signal column name → {cell value → (red, green, blue) 0–1 floats}
_GREEN  = {"red": 0.714, "green": 0.843, "blue": 0.659}
_YELLOW = {"red": 1.0,   "green": 0.898, "blue": 0.6}
_RED    = {"red": 0.918, "green": 0.600, "blue": 0.600}
_NONE   = None  # no fill

SIGNAL_COLORS = {
    "Lynch_Status": {
        "Strong Buy": _GREEN,
        "Buy":        _GREEN,
        "Hold":       _YELLOW,
        "Avoid":      _RED,
    },
    "Lynch_PEG_Band": {
        "Strong Buy": _GREEN,
        "Buy":        _GREEN,
        "Hold":       _YELLOW,
        "Avoid":      _RED,
    },
    "Graham_Status": {
        "Deep Buy":   _GREEN,
        "Buy":        _GREEN,
        "Watch":      _YELLOW,
        "Avoid":      _RED,
    },
    "Defensive": {
        "Pass":       _GREEN,
        "Borderline": _YELLOW,
        "Fail":       _RED,
    },
    "Status_Combined": {
        "True":       _GREEN,
        "False":      _NONE,
    },
    "Lynch_PEG_Status": {
        "Cheap":      _GREEN,
        "Reasonable": _YELLOW,
        "Rich":       _RED,
    },
    "Lynch_PEGY_Status": {
        "Cheap":      _GREEN,
        "Reasonable": _YELLOW,
        "Rich":       _RED,
    },
}


def _col_letter(n: int) -> str:
    """Convert 0-based column index to spreadsheet letter (0→A, 25→Z, 26→AA)."""
    result = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _apply_color_coding(ws, df_clean: "pd.DataFrame"):
    """
    Apply traffic-light background colors to signal columns.
    Batches all requests into a single API call for efficiency.
    """
    cols = df_clean.columns.tolist()
    requests = []

    for col_name, color_map in SIGNAL_COLORS.items():
        if col_name not in cols:
            continue
        col_idx = cols.index(col_name)

        for row_idx, val in enumerate(df_clean[col_name].tolist()):
            color = color_map.get(str(val).strip())
            if color is None:
                continue
            # row 0 = header (row 1 in sheets), data starts at row_idx+1 (0-based) → +2
            requests.append({
                "repeatCell": {
                    "range": {
                        "sheetId":          ws.id,
                        "startRowIndex":    row_idx + 1,
                        "endRowIndex":      row_idx + 2,
                        "startColumnIndex": col_idx,
                        "endColumnIndex":   col_idx + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })

    if requests:
        ws.spreadsheet.batch_update({"requests": requests})


# ── Documentation tab content ─────────────────────────────────────────────────
DOCS_CONTENT = [
    ["Lynch & Graham Stock Screener — Documentation"],
    [""],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    ["OVERVIEW"],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    ["  This screener runs two parallel valuation frameworks — Peter Lynch and"],
    ["  Benjamin Graham — across the S&P 500, Dow 30, and Nasdaq-100 universe."],
    ["  Each framework outputs a fair value estimate and a buy/hold/avoid signal."],
    ["  A blended Score combines both for easy sorting."],
    [""],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    ["SIGNAL COLUMNS (appear on the left)"],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    [""],
    ["  Status_Combined"],
    ["    • True  = at least one of Lynch or Graham says Buy"],
    ["    • False = neither framework sees value at the current price"],
    [""],
    ["  Score"],
    ["    • Blended 0–60 score. Higher = cheaper relative to both frameworks."],
    ["    • Formula: 0.5 × Lynch_Discount_Pct + 0.5 × Graham_Discount_Pct"],
    ["    • Both discounts are clipped to [0, 60%] before averaging."],
    ["    • The sheet is sorted by this column descending (best first)."],
    [""],
    ["  Lynch_Status  (G+D method — primary Lynch signal)"],
    ["    • Strong Buy  = price ≤ 70% of Lynch fair value"],
    ["    • Buy         = price ≤ 100% of Lynch fair value"],
    ["    • Hold        = price ≤ 130% of Lynch fair value"],
    ["    • Avoid       = price > 130% of Lynch fair value"],
    ["    • Fair value  = EPS × (Growth% + Dividend%)"],
    [""],
    ["  Lynch_PEG_Band  (PEG method — secondary Lynch signal)"],
    ["    • Strong Buy  = price ≤ 70% of conservative PEG fair value"],
    ["    • Buy         = price ≤ conservative PEG fair value (EPS × 0.8 × Growth)"],
    ["    • Hold        = price ≤ PEG fair value (EPS × Growth)"],
    ["    • Avoid       = price > PEG fair value"],
    [""],
    ["  Graham_Status"],
    ["    • Deep Buy    = price ≤ 60% of Graham fair value (40%+ margin of safety)"],
    ["    • Buy         = price ≤ 80% of Graham fair value (20%+ margin of safety)"],
    ["    • Watch       = price ≤ 95% of Graham fair value"],
    ["    • Avoid       = price > 95% of Graham fair value"],
    ["    • Fair value  = MIN(Version A, Version B) — see Graham section below"],
    [""],
    ["  Defensive  (Graham defensive investor filter)"],
    ["    • Pass        = score ≥ 6/8 on Graham's balance sheet checklist"],
    ["    • Borderline  = score 4–5"],
    ["    • Fail        = score < 4"],
    ["    • See Defensive_Score for the exact number"],
    [""],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    ["PETER LYNCH FRAMEWORK"],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    [""],
    ["  Core idea: a stock is fairly valued when its P/E ratio equals its"],
    ["  growth rate (PEG = 1). Add dividends for income-paying stocks (PEGY)."],
    [""],
    ["  Category  (auto-assigned from growth rate)"],
    ["    • Slow Grower  = growth < 5%  — utility/mature companies"],
    ["    • Stalwart     = growth 5–12% — large, steady compounders"],
    ["    • Fast Grower  = growth > 12% — high growth, higher risk"],
    [""],
    ["  Key metrics"],
    ["    • Lynch_PEG     = P/E ÷ Growth%.  Below 1.0 = cheap, above 1.0 = rich."],
    ["    • Lynch_PEGY    = P/E ÷ (Growth% + Div%).  Adds dividend to PEG."],
    ["    • Lynch_Score   = (Growth% + Div%) ÷ P/E.  Inverse of PEGY, higher = better."],
    ["    • Lynch_FV_GplusD  = EPS × (Growth% + Div%).  G+D fair value."],
    ["    • Lynch_BuyPrice   = Category-adjusted buy price (applies extra discount"],
    ["                         for Fast Growers, less for Stalwarts)."],
    ["    • Lynch_Discount_Pct = how far below Lynch_BuyPrice the stock is trading."],
    ["                           Positive = trading below buy price (good)."],
    [""],
    ["  Discount factors by category"],
    ["    • Slow Grower:  buy at 75% of conservative fair value"],
    ["    • Stalwart:     buy at 80% of conservative fair value"],
    ["    • Fast Grower:  buy at 70% of conservative fair value (more growth risk)"],
    [""],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    ["BENJAMIN GRAHAM FRAMEWORK"],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    [""],
    ["  Core idea: buy at a significant discount to intrinsic value (margin of"],
    ["  safety). Graham's formula adjusts for interest rates — higher rates"],
    ["  make stocks worth less, lower rates make them worth more."],
    [""],
    ["  Graham_VA  (classic rate-adjusted formula)"],
    ["    • Formula: EPS × (8.5 + 2 × Growth%) × 4.4 ÷ AAA_Yield"],
    ["    • 8.5 = Graham's no-growth P/E baseline"],
    ["    • 4.4 = historical AAA bond yield when formula was written"],
    ["    • AAA_Yield = current Moody's AAA corporate yield (fetched live from FRED)"],
    [""],
    ["  Graham_VB  (conservative variant)"],
    ["    • Formula: EPS × (7 + Growth%) × 4.4 ÷ AAA_Yield"],
    ["    • Uses a lower base P/E (7 vs 8.5) and single growth multiplier"],
    [""],
    ["  Graham_FairValue"],
    ["    • MIN(Graham_VA, Graham_VB) — always uses the more conservative estimate"],
    [""],
    ["  Graham_Discount_Pct"],
    ["    • How far below Graham_FairValue the stock is trading."],
    ["    • Positive = trading at a discount (good). Negative = trading at a premium."],
    [""],
    ["  Graham Defensive Checklist  (8 criteria, 1 point each)"],
    ["    1. Market cap ≥ $2B"],
    ["    2. Current ratio ≥ 2.0  (current assets / current liabilities)"],
    ["    3. Long-term debt / equity ≤ 1.0"],
    ["    4. Positive EPS in 8 of last 10 fiscal years"],
    ["    5. Paid a dividend in 5 of last 10 years"],
    ["    6. Cumulative EPS growth ≥ 33% over 10 years (~3%/yr)"],
    ["    7. P/E ≤ 15 based on 3-year average EPS"],
    ["    8. P/B ≤ 1.5, or P/E × P/B ≤ 22.5"],
    [""],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    ["DATA SOURCES"],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    [""],
    ["  • Price, EPS, dividends, balance sheet  →  Yahoo Finance (via yfinance)"],
    ["  • AAA corporate bond yield              →  FRED (Federal Reserve)"],
    ["  • Index constituents                    →  Wikipedia (S&P 500, Dow, Nasdaq-100)"],
    [""],
    ["  Growth is calculated as EPS CAGR using the longest available window"],
    ["  (typically 4–5 years). If growth is negative, it is floored at 1%"],
    ["  so that a conservative valuation is still computed rather than skipped."],
    [""],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    ["COLOR CODING (Results tab)"],
    ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"],
    [""],
    ["  Green  = Strong Buy / Buy / Deep Buy / Pass"],
    ["  Yellow = Hold / Watch / Borderline / Reasonable"],
    ["  Red    = Avoid / Fail"],
    [""],
    ["  Applied to: Lynch_Status, Lynch_PEG_Band, Graham_Status,"],
    ["              Defensive, Status_Combined, Lynch_PEG_Status, Lynch_PEGY_Status"],
    [""],
]


def _write_markdown_tab(sh, df: "pd.DataFrame"):
    """
    Write a Top 20 Buy Signals summary as a copyable markdown table
    on a dedicated tab. Designed for easy sharing — just copy the cell.
    """
    tab_name = "Top 20 Summary"
    try:
        md_ws = sh.worksheet(tab_name)
        md_ws.clear()
    except gspread.WorksheetNotFound:
        md_ws = sh.add_worksheet(title=tab_name, rows=60, cols=3)

    # ── Build the top 20 from the results DataFrame ──────────────────
    # Rename Score column if needed (may already be renamed by this point)
    score_col   = "Score"    if "Score"    in df.columns else "CombinedScore"
    status_col  = "Status_Combined" if "Status_Combined" in df.columns else "Show"
    lynch_col   = "Lynch_Status"
    graham_col  = "Graham_Status"
    defensive_col = "Defensive"
    price_col   = "Price"
    buy_price_col = "Lynch_BuyPrice"
    graham_fv_col = "Graham_FairValue"
    category_col  = "Category"
    growth_col    = "Growth_Pct" if "Growth_Pct" in df.columns else "Growth_g_Pct"
    eps_col       = "EPS"        if "EPS"        in df.columns else "EPS_TTM"

    # Filter to rows with a buy signal and valid score, take top 20
    has_score = df[score_col].apply(lambda x: str(x).replace(".", "").lstrip("-").isdigit()
                                    or (str(x).replace(".", "", 1).replace("-", "", 1).isdigit()))
    try:
        scored = df[has_score].copy()
        scored[score_col] = pd.to_numeric(scored[score_col], errors="coerce")
        top20 = scored.nlargest(20, score_col)
    except Exception:
        top20 = df.head(20)

    # ── Helper to safely get a cell value ────────────────────────────
    def _cell(row, col):
        if col in row.index:
            v = row[col]
            return "" if str(v) in ("nan", "None", "") else str(v)
        return ""

    # ── Build markdown table ──────────────────────────────────────────
    from datetime import date
    today = date.today().strftime("%B %d, %Y")

    header = (
        "| # | Ticker | Price | Lynch | Graham | Defensive "
        "| Category | Growth% | EPS | Lynch Buy | Graham FV | Score |"
    )
    separator = (
        "|---|--------|-------|-------|--------|-----------|"
        "----------|---------|-----|-----------|-----------|-------|"
    )

    rows_md = []
    for i, (_, row) in enumerate(top20.iterrows(), 1):
        line = (
            f"| {i} "
            f"| {_cell(row, 'Ticker')} "
            f"| ${_cell(row, price_col)} "
            f"| {_cell(row, lynch_col)} "
            f"| {_cell(row, graham_col)} "
            f"| {_cell(row, defensive_col)} "
            f"| {_cell(row, category_col)} "
            f"| {_cell(row, growth_col)}% "
            f"| ${_cell(row, eps_col)} "
            f"| ${_cell(row, buy_price_col)} "
            f"| ${_cell(row, graham_fv_col)} "
            f"| {_cell(row, score_col)} |"
        )
        rows_md.append(line)

    full_table = "\n".join([header, separator] + rows_md)

    # ── Write to sheet ────────────────────────────────────────────────
    sheet_data = [
        [f"Top 20 Buy Signals — {today}"],
        [""],
        ["Instructions: Copy the cell below and paste as markdown anywhere."],
        [""],
        [full_table],
        [""],
        ["── Individual rows (for easier reading) ──────────────────────────"],
        [header],
        [separator],
    ] + [[r] for r in rows_md]

    md_ws.update(sheet_data, value_input_option="USER_ENTERED")

    # Format: bold title, wide column, wrap text on the full table cell
    requests = [
        # Bold title
        {
            "repeatCell": {
                "range": {"sheetId": md_ws.id,
                          "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 13}}},
                "fields": "userEnteredFormat.textFormat"
            }
        },
        # Wrap text on the full-table cell (row 5, 0-indexed = row 4)
        {
            "repeatCell": {
                "range": {"sheetId": md_ws.id,
                          "startRowIndex": 4, "endRowIndex": 5,
                          "startColumnIndex": 0, "endColumnIndex": 1},
                "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP"}},
                "fields": "userEnteredFormat.wrapStrategy"
            }
        },
        # Wide column A
        {
            "updateDimensionProperties": {
                "range": {"sheetId": md_ws.id, "dimension": "COLUMNS",
                          "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 900},
                "fields": "pixelSize"
            }
        },
    ]
    sh.batch_update({"requests": requests})


def _write_docs_tab(sh):
    """Create or overwrite the Documentation worksheet."""
    tab_name = "Documentation"
    try:
        docs_ws = sh.worksheet(tab_name)
        docs_ws.clear()
    except gspread.WorksheetNotFound:
        docs_ws = sh.add_worksheet(title=tab_name, rows=200, cols=5)

    docs_ws.update(DOCS_CONTENT, value_input_option="USER_ENTERED")

    # Bold the title and section headers
    bold_rows = [i + 1 for i, row in enumerate(DOCS_CONTENT)
                 if row and ("━" in row[0] or row[0] == DOCS_CONTENT[0][0]
                 or (row[0].strip() and not row[0].startswith(" ") and not row[0].startswith("•")))]
    requests = []
    for r in bold_rows:
        requests.append({
            "repeatCell": {
                "range": {"sheetId": docs_ws.id,
                          "startRowIndex": r - 1, "endRowIndex": r,
                          "startColumnIndex": 0,  "endColumnIndex": 1},
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold"
            }
        })
    # Widen column A so text isn't clipped
    requests.append({
        "updateDimensionProperties": {
            "range": {"sheetId": docs_ws.id, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": 1},
            "properties": {"pixelSize": 700},
            "fields": "pixelSize"
        }
    })
    if requests:
        sh.batch_update({"requests": requests})

def push_to_gsheets(df: pd.DataFrame):
    """
    Authenticate and write the results DataFrame to Google Sheets.

    GSHEET_CREDS_JSON can be either:
      - A file path  (local dev):  "/path/to/service_account.json"
      - Raw JSON string (Actions): the entire JSON content as a secret
    """
    import json as _json
    log.info("Authenticating with Google Sheets...")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_val = GSHEET_CREDS_JSON.strip()
    if creds_val.startswith("{"):
        # Raw JSON content (GitHub Actions secret)
        creds_info = _json.loads(creds_val)
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    else:
        # File path (local dev)
        creds = Credentials.from_service_account_file(creds_val, scopes=scopes)
    client = gspread.authorize(creds)

    log.info(f"Opening spreadsheet: '{GSHEET_SPREADSHEET}' → '{GSHEET_WORKSHEET}'")
    sh  = client.open(GSHEET_SPREADSHEET)

    # Create worksheet if it doesn't exist
    try:
        ws = sh.worksheet(GSHEET_WORKSHEET)
        ws.clear()
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=GSHEET_WORKSHEET, rows=2000, cols=60)

    # ── Rename columns (clean up prefixes/redundancy) ──────────────
    rename_map = {
        # Signals
        "Show":                     "Status_Combined",
        "CombinedScore":            "Score",
        "DefensiveLabel":           "Defensive",
        "DefensiveScore":           "Defensive_Score",
        # Lynch signals
        "Lynch_Lynch_Status":       "Lynch_Status",
        "Lynch_Lynch_PEG_Band":     "Lynch_PEG_Band",
        "Lynch_Lynch_Category":     "Category",
        "Lynch_Lynch_BuyPrice":     "Lynch_BuyPrice",
        "Lynch_Lynch_Discount_Pct": "Lynch_Discount_Pct",
        "Lynch_Lynch_Score":        "Lynch_Score",
        "Lynch_Lynch_LV_Ratio":     "Lynch_LV_Ratio",
        "Lynch_Lynch_FV_PEG":       "Lynch_FV_PEG",
        "Lynch_Lynch_FV_PEG_Con":   "Lynch_FV_PEG_Con",
        "Lynch_Lynch_FV_GplusD":    "Lynch_FV_GplusD",
        "Lynch_Lynch_PEGY_Status":  "Lynch_PEGY_Status",
        "Lynch_Lynch_PEG_Status":   "Lynch_PEG_Status",
        "Lynch_Lynch_PE":           "Lynch_PE",
        "Lynch_Lynch_PEG":          "Lynch_PEG",
        "Lynch_Lynch_PEGY":         "Lynch_PEGY",
        # Graham signals
        "Graham_Graham_Status":         "Graham_Status",
        "Graham_Graham_FV":             "Graham_FairValue",
        "Graham_Graham_VA":             "Graham_VA",
        "Graham_Graham_VB":             "Graham_VB",
        "Graham_Graham_Discount_Pct":   "Graham_Discount_Pct",
        # Raw data
        "Growth_g_Pct":             "Growth_Pct",
        "EPS_TTM":                  "EPS",
        "DivYield_Pct":             "Div_Yield_Pct",
    }
    df = df.rename(columns=rename_map)

    # ── Reorder: signals first, raw data after ──────────────────────
    priority_cols = [
        "Ticker", "Indexes",
        "Status_Combined", "Score",
        "Lynch_Status", "Lynch_PEG_Band", "Graham_Status",
        "Defensive", "Defensive_Score",
        "Price", "Lynch_BuyPrice", "Graham_FairValue",
        "Category", "Growth_Pct", "EPS",
        "Lynch_Discount_Pct", "Graham_Discount_Pct",
    ]
    remaining_cols = [c for c in df.columns if c not in priority_cols]
    df = df[[c for c in priority_cols if c in df.columns] + remaining_cols]

    # Convert DataFrame → list of lists (header + rows)
    df_clean = df.fillna("").astype(str)
    data = [df_clean.columns.tolist()] + df_clean.values.tolist()

    ws.update(data, value_input_option="USER_ENTERED")
    log.info(f"✓ Wrote {len(df)} rows to Google Sheets.")

    # Bold the header row
    ws.format("1:1", {"textFormat": {"bold": True}})

    # Freeze header row
    sh.batch_update({
        "requests": [{
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "gridProperties": {"frozenRowCount": 1}
                },
                "fields": "gridProperties.frozenRowCount"
            }
        }]
    })
    log.info("✓ Header formatted and frozen.")

    # ── Color coding ────────────────────────────────────────────────
    _apply_color_coding(ws, df_clean)
    log.info("✓ Color coding applied.")

    # ── Documentation tab ───────────────────────────────────────────
    _write_docs_tab(sh)
    log.info("✓ Documentation tab written.")

    # ── Top 20 markdown summary tab ──────────────────────────────────
    _write_markdown_tab(sh, df)
    log.info("✓ Top 20 markdown tab written.")


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
    rows = df.where(df.notna(), other=None).to_dict(orient="records")
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

    # 4. Push to Google Sheets
    write_json(results_df)

    log.info("═══ Done ═══")
    log.info(f"Total tickers processed: {len(results_df)}")
    if "Show" in results_df.columns:
        log.info(f"Rows with Buy signals:   {results_df['Show'].astype(str).eq('True').sum()}")
    else:
        log.info("Rows with Buy signals:   0 (no tickers passed valuation filters)")


if __name__ == "__main__":
    main()