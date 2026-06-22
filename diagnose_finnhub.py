"""
Finnhub Data Structure Diagnostic
====================================
Verifies Finnhub API responses for the fields we need:
  - Annual income statement (EPS, 10yr history)
  - Annual balance sheet (current ratio, debt/equity, book value)
  - Basic financials (summary metrics)

Run with:
    python diagnose_finnhub.py
"""

import requests
import json
import os

FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]
TICKERS = ["AAPL", "MSFT", "UPS", "META", "KO"]  # mix of types

BASE = "https://finnhub.io/api/v1"


def fh_get(endpoint: str, params: dict) -> dict:
    params["token"] = FINNHUB_API_KEY
    r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=15)
    print(f"  HTTP {r.status_code} — {r.url.split('token=')[0]}...")
    if r.status_code == 200:
        return r.json()
    return {}


def divider(label):
    print(f"\n{'═' * 60}")
    print(f"  {label}")
    print('═' * 60)


for ticker in TICKERS:
    divider(ticker)

    # ── 1. Basic Financials ────────────────────────────────────────
    print("\n── basic_financials ──")
    bf = fh_get("stock/metric", {"symbol": ticker, "metric": "all"})
    if bf:
        metric = bf.get("metric", {})
        fields_of_interest = [
            "52WeekHigh", "52WeekLow", "marketCapitalization",
            "peBasicExclExtraTTM", "epsBasicExclExtraAnnual",
            "epsGrowth3Y", "epsGrowth5Y", "revenueGrowth5Y",
            "currentRatioAnnual", "totalDebt/totalEquityAnnual",
            "bookValuePerShareAnnual", "dividendsPerShareAnnual",
            "pb", "pe",
            # Phase 5 FCF gate fields (D-04) — confirm exact key names here
            "freeCashFlowPerShareAnnual",
            "freeCashFlowPerShareTTM",
            # Additional fields for KO fixture verification
            "epsAnnual",
            "epsGrowth5Y",
            "dividendPerShareAnnual",
            # Phase 6 [VERIFY] — confirm free-tier presence
            "evToEbit",
            "ebitAnnual",
            "enterpriseValue",
            "roiAnnual",
            "dividendYieldAnnual",
            "sharesBuybackRatioAnnual",
            "totalDebtAnnual",
            "cashAnnual",
        ]
        print("  Fields of interest:")
        for f in fields_of_interest:
            print(f"    {f}: {metric.get(f, 'NOT FOUND')}")
        print(f"\n  All available metric keys ({len(metric)} total):")
        for k in sorted(metric.keys())[:40]:
            print(f"    {k}: {metric[k]}")
        if len(metric) > 40:
            print(f"    ... and {len(metric) - 40} more")
    else:
        print("  EMPTY / ERROR")

    # ── 2. Financials (annual statements) ─────────────────────────
    print("\n── financials (annual) ──")
    fin = fh_get("stock/financials", {"symbol": ticker, "statement": "ic", "freq": "annual"})
    if fin and fin.get("financials"):
        stmts = fin["financials"]
        print(f"  Number of annual periods returned: {len(stmts)}")
        print(f"  Date range: {stmts[-1].get('period', '?')} → {stmts[0].get('period', '?')}")
        print(f"\n  Most recent period fields:")
        latest = stmts[0]
        for k, v in sorted(latest.items()):
            print(f"    {k}: {v}")
    else:
        print("  EMPTY / ERROR — full response:")
        print(f"  {json.dumps(fin, indent=2)[:500]}")

    # ── 3. Balance Sheet (annual) ──────────────────────────────────
    print("\n── balance sheet (annual) ──")
    bs = fh_get("stock/financials", {"symbol": ticker, "statement": "bs", "freq": "annual"})
    if bs and bs.get("financials"):
        stmts = bs["financials"]
        print(f"  Number of annual periods returned: {len(stmts)}")
        print(f"  Date range: {stmts[-1].get('period', '?')} → {stmts[0].get('period', '?')}")
        print(f"\n  Most recent period fields:")
        latest = stmts[0]
        for k, v in sorted(latest.items()):
            print(f"    {k}: {v}")
    else:
        print("  EMPTY / ERROR — full response:")
        print(f"  {json.dumps(bs, indent=2)[:500]}")

print(f"\n{'═' * 60}")
print("  Diagnostic complete.")
print('═' * 60)