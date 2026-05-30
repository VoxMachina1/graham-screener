"""
yfinance Data Structure Diagnostic
====================================
Run this before making any changes to stock_screener.py.
It prints exactly what yfinance returns for a sample of tickers
so we know the real field names, shapes, and values.

Run with:
    python diagnose_yfinance.py
"""

import yfinance as yf

TICKERS = ["AAPL", "ABBV", "ADP", "AES", "BRK-B"]  # mix of types


def divider(label):
    print(f"\n{'═' * 60}")
    print(f"  {label}")
    print('═' * 60)


for ticker in TICKERS:
    divider(ticker)
    t = yf.Ticker(ticker)

    # ── fast_info ──────────────────────────────────────────────────
    print("\n── fast_info ──")
    fi = t.fast_info
    for attr in ["last_price", "market_cap", "shares"]:
        print(f"  {attr}: {getattr(fi, attr, 'NOT FOUND')}")

    # ── income_stmt ────────────────────────────────────────────────
    print("\n── income_stmt ──")
    inc = t.income_stmt
    if inc is None or inc.empty:
        print("  EMPTY")
    else:
        print(f"  Shape: {inc.shape}  (rows=line items, cols=dates)")
        print(f"  Columns (dates): {list(inc.columns)}")
        print(f"  Row index (all field names):")
        for row in inc.index:
            print(f"    {row}")
        # Print EPS-related rows if present
        eps_keywords = ["eps", "earning", "income per"]
        print(f"\n  EPS-related rows + values:")
        found_any = False
        for row in inc.index:
            if any(k in row.lower() for k in eps_keywords):
                print(f"    {row}: {list(inc.loc[row].values)}")
                found_any = True
        if not found_any:
            print("    (none found)")

    # ── balance_sheet ──────────────────────────────────────────────
    print("\n── balance_sheet ──")
    bs = t.balance_sheet
    if bs is None or bs.empty:
        print("  EMPTY")
    else:
        print(f"  Shape: {bs.shape}")
        print(f"  Row index (all field names):")
        for row in bs.index:
            print(f"    {row}")
        # Print key rows we need
        target_rows = [
            "current assets", "current liab",
            "long term debt", "stockholders", "equity", "book value"
        ]
        print(f"\n  Key rows + most recent values:")
        found_any = False
        for row in bs.index:
            if any(k in row.lower() for k in target_rows):
                print(f"    {row}: {bs.iloc[:, 0].get(row, 'N/A')}")
                found_any = True
        if not found_any:
            print("    (none found)")

    # ── dividends ──────────────────────────────────────────────────
    print("\n── dividends ──")
    divs = t.dividends
    if divs is None or divs.empty:
        print("  EMPTY")
    else:
        print(f"  Shape: {divs.shape}")
        print(f"  Most recent 5 entries:\n  {divs.tail()}")
        divs.index = divs.index.tz_localize(None) if divs.index.tz else divs.index
        annual = divs.resample("YE").sum()
        print(f"  Annual totals (last 5 years):\n  {annual.tail()}")

print(f"\n{'═' * 60}")
print("  Diagnostic complete.")
print('═' * 60)