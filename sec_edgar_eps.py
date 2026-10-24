#!/usr/bin/env python3
"""SEC EDGAR annual diluted-EPS fetcher for the Lynch & Graham screener.

Fills the screener's biggest data gap: 10+ years of annual diluted EPS per
ticker, needed to score Graham's two 10-year defensive criteria
(EPS_Stability and EPS_Growth10Y) honestly on the 0-8 scale.

Data source: SEC EDGAR companyfacts API (free, no key, ~10 requests/sec).
The screener's existing yfinance path is hard-capped at ~4 years of annuals,
and Finnhub's standardized statements are paid-tier only, so this module
exists to be wired into the screener's data pipeline as a supplemental
annual-EPS source.

Design notes
------------
- stdlib only (urllib / json / time / os / datetime) — no pip installs on Fangorn.
- Weekly file cache: annual data barely moves, so each CIK's companyfacts
  payload is cached on disk for 7 days (~1 request per ticker per week).
- One module-level USER_AGENT constant. SEC policy asks for a User-Agent with
  contact info; it works with a placeholder, but Jake should supply a real
  email for by-the-book compliance.
- Returns a plain {fiscal_year: eps} dict, sorted ascending. Negative and zero
  EPS values are kept as-is — the *criteria* decide what to do with them, not
  the fetcher.

Usage
-----
    from sec_edgar_eps import fetch_eps_series
    series = fetch_eps_series("AAPL")          # {2016: 2.08, ..., 2025: 6.44}

    python3 sec_edgar_eps.py AAPL MSFT XOM     # CLI print of series
    python3 sec_edgar_eps.py --selftest       # quick live self-test

Placement note: this lives in the Resurrected Managers goal workspace until
Jake wires it into the screener repo (a new fetcher module + weekly refresh
in his daily pipeline is the intended integration).

Known data quirks (all verified against live SEC data 2026-10-16)
----------------------------------------------------------------
1. The ``fy`` metadata tag on companyfacts is the FILING's fiscal year, not
   the fact's — every fact in a 10-K carries the filing's fy. The module keys
   facts by period end date instead.
2. 10-Ks also tag quarterly/partial-period EPS facts, so the module keeps only
   facts whose start->end span is 350-380 days (annual), covering 52/53-week
   filers.
3. Split restatements only reach back ~2-3 years in practice: years before the
   most recent split keep PRE-SPLIT EPS (e.g. AAPL's 4:1 2020 split corrupts
   any 10Y window starting before ~2018). See ten_year_growth's docstring —
   the criterion layer must apply split factors before computing growth.
4. The SEC ticker map can point a ticker at a NEW filer with no history
   (XOM -> ExxonMobil Holdings Corp, CIK 2115436, 2026-only 10-Qs). Known
   cases live in CIK_OVERRIDES; new ones will surface as suspiciously short
   series.
5. SEC tickers use hyphens for class shares (BRK-B); the module retries with
   "." -> "-" automatically.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# SEC wants a User-Agent identifying the tool and a contact. Placeholder works
# immediately; replace with Jake's real email for full by-the-book compliance.
USER_AGENT = "LynchGrahamScreener/1.0 (contact: placeholder@example.com)"

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sec_cache")
CACHE_TTL_SECONDS = 7 * 24 * 3600          # weekly — annual data barely moves
REQUEST_PAUSE_SECONDS = 0.15              # well under SEC's ~10 req/sec guidance

TICKER_MAP_CACHE = os.path.join(CACHE_DIR, "company_tickers.json")

# Manual overrides where the SEC ticker map points at a filer with no annual
# history. XOM: the map's row now points at "ExxonMobil Holdings Corp"
# (CIK 2115436, a 2026 filer with only 10-Qs); the 17-year annual history lives
# under the legacy filer "Exxon Mobil Corp" (CIK 34088).
CIK_OVERRIDES = {
    "XOM": 34088,
}

# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------

def _get_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Host": urllib.request.urlparse(url).netloc,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))
    # (pause is applied by the caller)


def _cache_path(name):
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, name + ".json")


def _cache_load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if time.time() - payload.get("fetched_at", 0) < CACHE_TTL_SECONDS:
            return payload.get("data")
    except (OSError, ValueError):
        pass
    return None


def _cache_save(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"fetched_at": time.time(), "data": data}, f)
    except OSError:
        pass

# ---------------------------------------------------------------------------
# Ticker -> CIK mapping
# ---------------------------------------------------------------------------

def load_ticker_map(refresh=False):
    """Return {TICKER: cik_int} for all SEC filers (cached weekly)."""
    if not refresh:
        cached = _cache_load(TICKER_MAP_CACHE)
        if cached is not None:
            return {k: int(v) for k, v in cached.items()}
    raw = _get_json(TICKER_MAP_URL)   # {idx: {cik_str, ticker, title}}
    time.sleep(REQUEST_PAUSE_SECONDS)
    mapping = {row["ticker"].upper(): int(row["cik_str"]) for row in raw.values()}
    _cache_save(TICKER_MAP_CACHE, mapping)
    return mapping

# ---------------------------------------------------------------------------
# Annual diluted EPS series
# ---------------------------------------------------------------------------

def _extract_annual_eps(companyfacts):
    """Pull ({fiscal_year: diluted EPS}, {fiscal_year: period-end "YYYY-MM-DD"},
    {fiscal_year: winning-filing "YYYY-MM-DD"}) from a companyfacts payload.

    Uses us-gaap EarningsPerShareDiluted, 10-K (annual) filings only, falling
    back to EarningsPerShareBasic when a filer tags no diluted concept
    (e.g. Berkshire Hathaway reports basic only — no dilutive instruments).
    Facts are keyed by their period *end* date, not the filing's ``fy`` tag
    (the SEC metadata tags every fact in a 10-K with the filing's fiscal
    year, so ``fy`` is wrong for the comparative years). When the same period
    appears in multiple filings (restatements, amendments, splits), the later
    ``filed`` date wins — so the series is the most recently restated one.
    The fiscal year is taken as the calendar year of the period end date,
    which matches the naming convention for the large-cap universe this
    screener covers; flagged here so a future maintainer can refine it with
    the submissions API's fiscalYearEnd field if needed.
    Quarterly fallback: filers that tag no annual EPS fact at all (e.g.
    Berkshire tags quarterly EPS only) get an annual series by summing
    exactly-4-quarter years; partial years are dropped, never estimated.
    """
    try:
        facts = companyfacts["facts"]["us-gaap"]
        concept = "EarningsPerShareDiluted"
        if concept not in facts:
            concept = "EarningsPerShareBasic"  # e.g. Berkshire: no dilutive concept tagged
        unit_blocks = facts[concept]["units"]
    except KeyError:
        return {}
    # Unit label varies by filer ("USD/shares" for AAPL, sometimes "USD/sh");
    # scan all blocks and merge.
    by_period = {}
    quarterly = {}   # fallback: (end -> (val, filed)) for quarterly facts
    for units in unit_blocks.values():
        for entry in units:
            if entry.get("form") not in ("10-K", "10-K/A"):
                continue
            end = entry.get("end")
            start = entry.get("start")
            val = entry.get("val")
            if end is None or start is None or val is None:
                continue
            try:
                span = (datetime.strptime(end, "%Y-%m-%d")
                        - datetime.strptime(start, "%Y-%m-%d")).days
            except ValueError:
                continue
            filed = entry.get("filed", "")
            if 350 <= span <= 380:
                # keep the most recently filed figure for the period
                if end not in by_period or filed > by_period[end][1]:
                    by_period[end] = (float(val), filed)
            elif 80 <= span <= 100:
                # quarterly fact — only used if NO annual facts exist at all
                if end not in quarterly or filed > quarterly[end][1]:
                    quarterly[end] = (float(val), filed)
    if not by_period and quarterly:
        # Some filers (e.g. Berkshire: 10-K tags quarterly EPS only) never tag
        # an annual fact. Sum exactly-4-quarter years; partial years are
        # dropped rather than guessed at.
        from collections import defaultdict
        by_year = defaultdict(list)
        for end, (qval, _filed) in quarterly.items():
            by_year[int(end[:4])].append(qval)
        for yr, qs in sorted(by_year.items()):
            if len(qs) == 4:
                by_period["%d-12-31" % yr] = (sum(qs), "")
    series, ends, filed = {}, {}, {}
    for end, (eps, filed_date) in sorted(by_period.items()):
        fy = int(end[:4])
        series[fy] = round(eps, 4)  # one annual figure per period end
        ends[fy] = end             # period end the screener uses for split dating
        if filed_date:
            # A 10-K retroactively restates comparatives for splits before its
            # filing date — so a split only needs manual adjustment for years
            # whose winning filing PREDATES the split.
            filed[fy] = filed_date
    return series, ends, filed


def _fetch_eps_data(ticker, refresh=False):
    """Return ({fiscal_year: diluted EPS}, {fiscal_year: period-end date},
    {fiscal_year: winning-filing date}).

    Single cached fetch backing the public helpers below — one HTTP call
    serves the EPS values plus the dates the screener needs for split
    adjustment. Cached weekly per CIK.
    Raises ValueError for unknown tickers, RuntimeError on fetch failure.
    """
    ticker = ticker.upper().strip()
    if ticker in CIK_OVERRIDES:
        cik = CIK_OVERRIDES[ticker]
    else:
        mapping = load_ticker_map(refresh=refresh)
        cik = mapping.get(ticker)
        if cik is None:
            # SEC uses hyphens for class shares: BRK.B -> BRK-B, BF.B -> BF-B
            cik = mapping.get(ticker.replace(".", "-"))
        if cik is None:
            raise ValueError("ticker %r not found in SEC company_tickers map" % ticker)
    cache_path = _cache_path("eps_%010d" % cik)
    if not refresh:
        cached = _cache_load(cache_path)
        # v3 cache holds {"eps": {...}, "ends": {...}, "filed": {...}};
        # anything older or unexpected is treated as a miss and refetched.
        if (isinstance(cached, dict) and "eps" in cached
                and "ends" in cached and "filed" in cached):
            return ({int(k): v for k, v in cached["eps"].items()},
                    {int(k): v for k, v in cached["ends"].items()},
                    {int(k): v for k, v in cached["filed"].items()})
    try:
        payload = _get_json(COMPANYFACTS_URL.format(cik=cik))
    except Exception as exc:  # noqa: BLE001 — surface as-is, no silent gaps
        raise RuntimeError("SEC companyfacts fetch failed for %s: %s" % (ticker, exc))
    time.sleep(REQUEST_PAUSE_SECONDS)
    series, ends, filed = _extract_annual_eps(payload)
    _cache_save(cache_path, {"eps": series, "ends": ends, "filed": filed})
    return series, ends, filed


def fetch_eps_details(ticker, refresh=False):
    """Return ({fiscal_year: diluted EPS}, {fiscal_year: period-end "YYYY-MM-DD"},
    {fiscal_year: winning-filing "YYYY-MM-DD"}).

    The dates let the screener restate pre-split fiscal years to post-split
    per-share basis without double-counting restatements the 10-K already
    made. Cached weekly.
    """
    return _fetch_eps_data(ticker, refresh=refresh)


def fetch_eps_series(ticker, refresh=False):
    """Return {fiscal_year: diluted EPS} for a ticker, cached weekly.

    Raises ValueError for unknown tickers, RuntimeError on fetch failure.
    """
    series, _, _ = _fetch_eps_data(ticker, refresh=refresh)
    return series


def fetch_eps_period_ends(ticker, refresh=False):
    """Return {fiscal_year: period-end "YYYY-MM-DD"} for a ticker, cached weekly."""
    _, ends, _ = _fetch_eps_data(ticker, refresh=refresh)
    return ends


def ten_year_growth(eps_series, end_year=None):
    """CAGR over the trailing 10 annual EPS figures; None if unusable.

    Convenience for the screener's EPS_Growth10Y criterion.

    IMPORTANT SPLIT CAVEAT: the SEC series is as-restated in each filing, and
    10-Ks only restate ~2-3 prior years, so years before the most recent
    split keep PRE-SPLIT EPS. A naive CAGR across a split boundary is wrong
    (e.g. AAPL's 2020 4:1 split corrupts any 10Y window starting before
    ~2018). The screener's criterion layer MUST apply split factors — e.g.
    from yfinance ``ticker.actions`` splits, cumulative product — to the
    pre-split years before calling this, or restrict the window to the
    post-split restated years. This helper does no split adjustment itself.
    """
    years = sorted(eps_series)
    if end_year is None:
        end_year = years[-1] if years else None
    window = [y for y in years if end_year - 10 < y <= end_year]
    if len(window) < 10:
        return None
    start_eps, end_eps = eps_series[window[0]], eps_series[window[-1]]
    if start_eps is None or end_eps is None or start_eps <= 0 or end_eps <= 0:
        return None
    return round((end_eps / start_eps) ** (1 / 10) - 1, 4)


def positive_eps_count(eps_series, years_back=10, end_year=None):
    """Count of positive annual EPS in the trailing window (EPS_Stability)."""
    years = sorted(eps_series)
    if end_year is None:
        end_year = years[-1] if years else None
    window = [y for y in years if end_year - years_back < y <= end_year]
    return sum(1 for y in window if eps_series.get(y, 0) > 0)

# ---------------------------------------------------------------------------
# CLI / self-test
# ---------------------------------------------------------------------------

def _main(argv):
    if "--selftest" in argv:
        tickers = ["AAPL", "MSFT", "XOM"]
        print("self-test: fetching annual diluted EPS for", ", ".join(tickers))
        for t in tickers:
            t0 = time.time()
            series = fetch_eps_series(t)
            print("%-5s %d years (%d-%d), last=%s, 10Y CAGR=%s, pos10=%d/10  [%.1fs]" % (
                t, len(series), min(series), max(series),
                series[max(series)], ten_year_growth(series),
                positive_eps_count(series), time.time() - t0))
        # cache-hit check: second fetch should be near-instant
        t0 = time.time()
        fetch_eps_series("AAPL")
        print("cache-hit second fetch of AAPL: %.2fs" % (time.time() - t0))
        print("cache dir:", CACHE_DIR)
        print("OK")
        return 0
    for t in argv:
        series = fetch_eps_series(t)
        print(t.upper(), "->", series)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
