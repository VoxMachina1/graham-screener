# Phase 6: Cheap Factors + Sector — Research

**Date:** 2026-06-21
**Status:** Research complete. Assembled from 3 focused researcher slices (A: fundamental factor sourcing · B: sector + price-history signals · C: scoring fold + thresholds). Live Finnhub field-name/coverage validation deferred to the next GitHub Actions run / `diagnose_finnhub.py` (offline — no API keys); unconfirmed Finnhub names flagged `[VERIFY]`; band thresholds are `[ASSUMED]` and calibrated in Phase 7.

---

# Phase 6: Cheap Factors — Research Slice A: Fundamental Factor Data Sourcing

**Researched:** 2026-06-21
**Slice:** A of 3 — FCF yield, EV/EBIT + earnings yield, ROIC, shareholder yield
**Out of scope here:** sector fetch (Slice B), price-distance signals (Slice B), band
thresholds and scoring fold (Slice C)

---

## User Constraints (from CONTEXT.md)

### Locked Decisions Relevant to This Slice
- **D-01** — Finnhub `metric=all` bundle is primary; add yfinance statement fallback for any
  field confirmed or suspected absent on the free tier. FCF is CONFIRMED absent on free tier.
- **D-01b** — Residual gaps: `None` → average-over-present (not zero). Negative-breaking
  inputs (e.g. EBIT ≤ 0) route to worst sub-score, not None.
- **D-05 pillar map** — FCF yield + EV/EBIT (earnings yield) → VALUE cash/earnings-yield
  sub-group. ROIC → QUALITY. Shareholder yield → VALUE (or QUALITY if research argues better).
- No new pip dependencies; yfinance already installed.
- One `yf.Ticker` object per ticker (reuse across sector, history, and statement fetches).

### Deferred (not this slice)
- Band thresholds and scoring fold (Slice C).
- Sector applicability gating (Phase 7 SECTOR-02).
- 30-day fundamentals cache (Phase 7 DATA-03).

---

## Offline Notice

No API keys available locally. All Finnhub field names below are sourced from Finnhub's
published API documentation and community references. Items marked `[VERIFY]` must be
confirmed by running `diagnose_finnhub.py` on the next GitHub Actions run, since the free
tier silently omits fields that appear in documentation.

---

## 1. FCF Yield

### 1a. Finnhub `metric=all` fields

FCF is **confirmed absent on the Finnhub free tier** (empirical: 05.1 live run, D-01 in
CONTEXT.md). The following field names appear in Finnhub documentation but returned `None`
in the live run:

- `freeCashFlowPerShareTTM` [VERIFY — confirmed absent free tier]
- `freeCashFlowPerShareAnnual` [VERIFY — confirmed absent free tier]
- `freeCashFlowPerShare5Y` [VERIFY — confirmed absent free tier]

**Decision:** Skip Finnhub for FCF entirely. Go straight to the yfinance cashflow-statement
fallback for all tickers.

### 1b. yfinance fallback — cashflow statement

Use `Ticker.cashflow` (the quarterly cashflow statement) or `Ticker.financials` (annual).
For annual trailing values, `Ticker.cashflow` returns the 4 most recent annual periods
(columns sorted newest-first by default).

**Operating cash flow candidate row labels** (yfinance label variance across versions):
```python
OCF_LABELS = [
    "Operating Cash Flow",
    "Total Cash From Operating Activities",
    "Cash Flow From Operations",
    "Cash From Operating Activities",
]
```

**Capital expenditure candidate row labels** (yfinance returns capex as a **negative**
number — subtract it from OCF, which means adding the absolute value):
```python
CAPEX_LABELS = [
    "Capital Expenditure",
    "Capital Expenditures",
    "Purchase Of Property Plant And Equipment",
    "Acquisition Of Property Plant Equipment And Software",
]
```

**Read pattern** (mirrors the existing `["Basic EPS", "Diluted EPS", ...]` label-scan):
```python
def _yf_row(df, labels):
    """Return the most-recent annual value for the first matching label, or None."""
    for label in labels:
        if label in df.index:
            col = df.columns[0]          # newest column first
            return _safe_float(df.loc[label, col])
    return None

cf = t.cashflow                           # reuse existing Ticker object
if cf is not None and not cf.empty:
    ocf   = _yf_row(cf, OCF_LABELS)
    capex = _yf_row(cf, CAPEX_LABELS)    # negative in yfinance
    if ocf is not None and capex is not None:
        fcf = ocf - capex                # capex is negative → ocf + |capex|
    elif ocf is not None:
        fcf = ocf                        # no capex data — use OCF as proxy
    else:
        fcf = None
```

**Capex sign caution:** yfinance consistently returns capex as a negative integer (e.g.
`-5_000_000_000`). The formula `FCF = OCF - capex` therefore becomes
`FCF = OCF - (negative) = OCF + |capex|`. Double-check with a known ticker (e.g. AAPL)
during validation: FCF should be positive and roughly equal to OCF minus the absolute capex.

### 1c. Final formula

```
market_cap = fh["marketCapitalization"] * 1e6   # Finnhub gives $millions
FCF (from yfinance, $)  → derived above
fcf_yield = FCF / market_cap                    # dimensionless ratio, e.g. 0.05 = 5%
```

Use `market_cap_b * 1e9` (already in `get_combined_data`) for the denominator so units
are consistent. If `market_cap` is None → `fcf_yield = None`.

### 1d. Coverage handling

| Condition | Handling |
|---|---|
| `fcf = None` (both OCF and capex missing) | `fcf_yield = None` → D-01b average-over-present |
| `fcf < 0` (negative FCF) | `fcf_yield` is negative → route to **worst** sub-score (D-01 carryover; negative FCF is a value-trap signal, not neutral) |
| `market_cap = None` | `fcf_yield = None` → D-01b |

---

## 2. EV/EBIT and Earnings Yield (EBIT/EV)

### 2a. Finnhub `metric=all` fields

Finnhub publishes a pre-computed EV/EBIT ratio under the key:

- `enterpriseValueToEBITDAAnnual` [VERIFY — EBITDA, not EBIT; see note below]
- `enterpriseValueEBITDA` [VERIFY — alternate label for same ratio]
- `evToEbit` [VERIFY — may exist as a computed ratio; coverage on free tier unknown]

**Important distinction:** Finnhub documents EV/EBITDA more prominently than EV/EBIT.
These are materially different (EBITDA adds back D&A). Do NOT use EV/EBITDA as a proxy
for EV/EBIT without flagging it as an approximation. The plan should:
1. Read `fh.get("evToEbit")` first [VERIFY].
2. If absent, compute EV/EBIT from components (see 2b).
3. Do NOT fall back to EV/EBITDA silently.

Component fields that may be in the Finnhub bundle [VERIFY each]:
- `enterpriseValue` — if present, avoids recomputing EV
- `ebitAnnual` — EBIT (operating income before interest and taxes)
- `totalDebtAnnual` or `totalDebt/totalEquityAnnual` (D/E ratio already fetched; but
  total debt in dollars is needed, not the ratio)
- `cashAnnual` or `totalCashAnnual`

### 2b. yfinance fallback — income statement + balance sheet

When Finnhub component fields are absent, compute from yfinance statements:

**EBIT candidate row labels** on `Ticker.income_stmt` (annual):
```python
EBIT_LABELS = [
    "EBIT",
    "Operating Income",
    "Ebit",
    "Total Operating Income As Reported",
]
```

**Total debt candidate row labels** on `Ticker.balance_sheet` (annual):
```python
TOTAL_DEBT_LABELS = [
    "Total Debt",
    "Long Term Debt And Capital Lease Obligation",  # + add current portion separately?
    "Long Term Debt",
]
CURRENT_DEBT_LABELS = [
    "Current Debt",
    "Current Portion Of Long Term Debt",
    "Short Long Term Debt",
]
```

**Cash candidate row labels** on `Ticker.balance_sheet`:
```python
CASH_LABELS = [
    "Cash And Cash Equivalents",
    "Cash Cash Equivalents And Short Term Investments",
    "Cash And Short Term Investments",
]
```

**Computation:**
```python
ebit       = _yf_row(t.income_stmt, EBIT_LABELS)
total_debt = (_yf_row(t.balance_sheet, TOTAL_DEBT_LABELS) or 0)
             + (_yf_row(t.balance_sheet, CURRENT_DEBT_LABELS) or 0)
cash       = _yf_row(t.balance_sheet, CASH_LABELS) or 0
market_cap = market_cap_b * 1e9

ev = market_cap + total_debt - cash      # standard EV formula
ev_ebit         = ev / ebit   if (ebit is not None and ebit > 0 and ev > 0) else None
earnings_yield  = ebit / ev   if (ebit is not None and ebit > 0 and ev > 0) else None
```

### 2c. Final formula

```
EV  = market_cap + total_debt − cash
EV/EBIT        = EV / EBIT          (lower = cheaper)
earnings_yield = EBIT / EV          (higher = cheaper; inverse of EV/EBIT)
```

Both are emitted as output columns. The scoring engine uses `earnings_yield` as the
sub-score input (higher → better, consistent with other yield inputs). `ev_ebit` is kept
as a diagnostic column.

### 2d. Coverage handling

| Condition | Handling |
|---|---|
| `ebit = None` | Both `ev_ebit` and `earnings_yield = None` → D-01b average-over-present |
| `ebit ≤ 0` | Negative or zero EBIT — earnings_yield is negative or undefined → route to **worst** sub-score (D-01; negative EBIT = operating loss, not neutral cheapness) |
| `ev ≤ 0` (net cash > market cap) | Arithmetic undefined → `earnings_yield = None`; flag as a rare positive anomaly worth human review, but do not assign best score automatically |
| `market_cap = None` | EV undefined → both None → D-01b |

---

## 3. ROIC

### 3a. Finnhub `metric=all` fields

Finnhub publishes an `roiAnnual` field (return on invested capital / return on investment
— terminology varies by source):

- `roiAnnual` [VERIFY — present on free tier? covers ~what % of universe?]
- `roeTTM` / `roeAnnual` — return on equity (different; do not substitute silently)
- `roaTTM` / `roaAnnual` — return on assets (different; do not substitute silently)

Greenblatt's ROIC = EBIT(1-t) / (net working capital + net fixed assets). Finnhub's
`roiAnnual` is likely "return on investment" (EBIT/total_assets or similar) rather than
exact Greenblatt ROIC. Per D-05 (SIGNAL-06): use ROIC as an **absolute input**, not the
Greenblatt rank-sum. A reasonable proxy is acceptable.

**Priority order:**
1. `fh.get("roiAnnual")` — Finnhub bundle, no extra HTTP request [VERIFY coverage]
2. Compute from components if absent (see 3b)

### 3b. yfinance fallback — computed ROIC

The Greenblatt approximation used in the CONTEXT.md scope:

```
NOPAT    = EBIT × (1 − 0.21)           # 21% US statutory tax rate; acceptable proxy
Invested = total_debt + shareholders_equity − cash
ROIC     = NOPAT / Invested
```

Candidate labels for shareholders' equity on `Ticker.balance_sheet`:
```python
EQUITY_LABELS = [
    "Stockholders Equity",
    "Total Stockholders Equity",
    "Common Stock Equity",
    "Total Equity Gross Minority Interest",
]
```

Reuse `ebit`, `total_debt`, `cash` from the EV/EBIT fetch (same statements, same period)
— do not re-fetch. `EBIT_LABELS`, `TOTAL_DEBT_LABELS`, `CASH_LABELS` already defined in
section 2b.

```python
equity = _yf_row(t.balance_sheet, EQUITY_LABELS)
if ebit is not None and total_debt is not None and equity is not None:
    nopat    = ebit * (1 - 0.21)
    invested = total_debt + equity - cash
    roic     = nopat / invested if invested != 0 else None
else:
    roic = None
```

Note: `invested` can be negative for firms with large buyback programs (negative book
equity). If `invested ≤ 0`, set `roic = None` rather than producing a nonsensical result.

### 3c. Final formula

```
ROIC = EBIT × (1 − 0.21) / (total_debt + equity − cash)
     = NOPAT / Invested Capital
```

Emitted as a dimensionless ratio (e.g. 0.18 = 18% ROIC). Higher is better → maps
naturally to the QUALITY pillar's ascending score curve.

### 3d. Coverage handling

| Condition | Handling |
|---|---|
| `roiAnnual = None` AND yf components insufficient | `roic = None` → D-01b average-over-present |
| `invested ≤ 0` (negative book equity) | `roic = None` → D-01b (not worst-score; this is a data anomaly, not a signal) |
| `ebit ≤ 0` | `nopat < 0` → negative ROIC → route to **worst** sub-score (operating loss = poor quality) |

---

## 4. Shareholder Yield

### 4a. Finnhub `metric=all` fields

Shareholder yield = dividend yield + net buyback yield.

**Dividend yield:**
- `dividendYieldAnnual` or `dividendYieldIndicatedAnnual` [VERIFY — likely present; div
  yield is a basic metric widely available on free tiers]
- Already partially in use: `dividendPerShareAnnual` is fetched in `get_combined_data`

**Buyback / share repurchase fields:**
- `sharesBuybackRatioAnnual` [VERIFY — may be free-tier present; this is the cleanest
  single-field source for net buyback yield if available]
- `sharesOutstandingAnnual` — can derive dilution/buyback from YoY change [VERIFY]
- No dedicated "buyback yield" field is confirmed in public Finnhub metric=all docs

### 4b. yfinance fallback — computed shareholder yield

**Dividend yield:** `fh.get("dividendYieldAnnual")` is likely available (verify). Fallback:
```python
div_yield = (ttm_dps / price) if (ttm_dps and price) else 0.0
```
`ttm_dps` already fetched in `get_combined_data` from Finnhub `dividendPerShareAnnual`.

**Net buyback yield** — derived from share count change on `Ticker.balance_sheet`:

Candidate row labels for shares outstanding:
```python
SHARES_LABELS = [
    "Ordinary Shares Number",
    "Share Issued",
    "Common Stock Shares Outstanding",
]
```

```python
bs = t.balance_sheet
shares_row = None
for label in SHARES_LABELS:
    if label in bs.index:
        shares_row = bs.loc[label]
        break

if shares_row is not None and len(shares_row) >= 2:
    # columns newest-first; [0] = most recent, [1] = prior year
    shares_now  = _safe_float(shares_row.iloc[0])
    shares_prev = _safe_float(shares_row.iloc[1])
    if shares_now and shares_prev and shares_prev > 0:
        # negative = reduction in shares = buyback; positive = dilution
        net_buyback_yield = (shares_prev - shares_now) / shares_prev
    else:
        net_buyback_yield = None
else:
    net_buyback_yield = None
```

This approach captures the net effect (buybacks minus new issuance). It does NOT separate
gross buybacks from dilution (options, convertibles), which is acceptable for a first pass.

**Combined:**
```python
shareholder_yield = div_yield + (net_buyback_yield or 0.0)
```

If `net_buyback_yield = None`, carry `div_yield` only and **set a low-coverage flag**
(`shareholder_yield_partial = True`) so the planner can include it in the coverage column.

### 4c. Final formula

```
shareholder_yield = dividend_yield + net_buyback_yield
                  = (DPS / price) + ((shares_prior − shares_now) / shares_prior)
```

Both components as dimensionless ratios. Higher = more capital returned → value signal.
Typical range: −0.03 (dilutive) to +0.15 (high yield + aggressive buybacks).

### 4d. Coverage handling and pillar placement

| Condition | Handling |
|---|---|
| `div_yield = 0` (no dividend), `net_buyback_yield = None` | `shareholder_yield = 0.0` with `partial` flag; include in average-over-present but low signal confidence |
| `net_buyback_yield = None` only | Use div_yield alone; set `shareholder_yield_partial = True` |
| Heavily negative (dilutive) | Route to worst sub-score (D-01 carryover — dilution destroys value) |

**Pillar placement recommendation:** VALUE (capital-return sub-group). Rationale: for a
mega-cap universe, high shareholder yield is a cheapness / value-signaling metric (company
believes stock is cheap → buys back; or generates surplus cash → returns it). The quality
read (capital allocation discipline) is already partially captured by ROIC. Keeping it in
VALUE preserves QUALITY for operational efficiency metrics. This is consistent with the
CONTEXT.md default and with academic treatment (Mebane Faber, Cambria).

---

## 5. Cross-Cutting: Statement Fetch Architecture

**Key implementation constraint:** all four factors above can share a SINGLE `yf.Ticker`
object per ticker and a SINGLE fetch per statement type:

| Statement | yfinance attribute | Used by |
|---|---|---|
| `Ticker.cashflow` | annual cashflow | FCF (OCF + capex) |
| `Ticker.income_stmt` | annual income | EBIT, EPS (already fetched) |
| `Ticker.balance_sheet` | annual balance sheet | total_debt, cash, equity, shares |

Recommended: extend `get_yf_price_and_history()` to also return raw statement DataFrames,
or pass the `Ticker` object into a new `get_yf_fundamentals(t: yf.Ticker) -> dict`
helper. The planner should ensure `t.cashflow`, `t.income_stmt`, and `t.balance_sheet` are
each accessed at most once per ticker (yfinance caches internally, but explicit single-fetch
is cleaner and avoids redundant network calls).

**Period alignment:** all yfinance annual statements return data for the same fiscal periods.
Use `iloc[0]` (newest column) consistently across all four statements for the same ticker
to ensure temporal alignment.

---

## 6. Finnhub Fields Requiring Live Validation

The following fields must be checked with `diagnose_finnhub.py` on the next Actions run
to confirm presence on the free tier. Current status is [VERIFY] (documented but unconfirmed
for free tier):

| Field | Factor | Risk if absent |
|---|---|---|
| `evToEbit` | EV/EBIT | Must fall back to yf component computation |
| `ebitAnnual` | EV/EBIT, ROIC | Must source EBIT from yf income_stmt |
| `enterpriseValue` | EV/EBIT | Must compute EV from components |
| `roiAnnual` | ROIC | Must compute NOPAT/Invested from yf |
| `dividendYieldAnnual` | Shareholder yield | Fallback: DPS/price (already have DPS) |
| `sharesBuybackRatioAnnual` | Shareholder yield | Must derive from share-count delta |
| `totalDebtAnnual` | EV, ROIC | Must source from yf balance_sheet |
| `cashAnnual` | EV, ROIC | Must source from yf balance_sheet |
| `freeCashFlowPerShareTTM` | FCF | CONFIRMED absent — yf fallback mandatory |

**Recommended `diagnose_finnhub.py` additions:** print presence/absence for all fields in
the table above across 5–10 test tickers (mix: AAPL, MSFT, V, XOM, JNJ, BRK-B, a
non-US ADR). This gives a quick coverage percentage before the scoring math depends on them.

---

## 7. Assumptions Log

| # | Claim | Risk if Wrong |
|---|---|---|
| A1 | yfinance `Ticker.cashflow` uses annual periods by default (not quarterly) | FCF computed from wrong period; add `.period_type == "annual"` check or use `Ticker.financials` |
| A2 | yfinance capex is always negative in the cashflow statement | FCF formula inverted; validate on AAPL: `capex < 0` expected |
| A3 | `Ticker.balance_sheet` columns are newest-first | Wrong period used; confirm with `df.columns[0]` date vs `df.columns[1]` date |
| A4 | Finnhub `roiAnnual` is a reasonable ROIC proxy (not pure ROI or ROE) | Quality signal diluted; may need full yf-computed ROIC for all tickers regardless |
| A5 | `sharesBuybackRatioAnnual` exists on Finnhub free tier | Buyback yield always yf-derived; acceptable fallback exists |
| A6 | Share-count delta from balance_sheet adequately proxies net buyback yield | Dilutive issuance (options) not separated; may overstate dilution for high-option-comp firms |

---

## Sources

- Finnhub API documentation (basic financials / metric=all): [ASSUMED — field names from
  training knowledge; not fetched in this session due to no API key]
- yfinance label variance: [ASSUMED — drawn from known yfinance version history and the
  existing codebase pattern at stock_screener.py:608]
- EV/EBIT and ROIC formulas: standard finance definitions; Greenblatt "The Little Book
  That Beats the Market" for ROIC construction [ASSUMED]
- Shareholder yield methodology: Mebane Faber, "Shareholder Yield" (2013) [ASSUMED]
- Phase 5.1 live run empirical data (FCF absent): `.planning/phases/05-score-foundation-public-top-n/05.1-FIXES-SUMMARY.md` [VERIFIED: project file]
- Locked decisions: `.planning/phases/06-cheap-factors-sector/06-CONTEXT.md` [VERIFIED: project file]

---

# Phase 6: Research B — GICS Sector + 5-Year Weekly Price-History Signals

**Researched:** 2026-06-21
**Scope:** Sector field (D-02) + price-distance/recency signals (D-03/D-04). Offline reasoning
from yfinance documented API and existing `stock_screener.py` code. No live calls.

---

## Sector

### What yfinance returns

`yf.Ticker(ticker).info` is a dict. The relevant key is `"sector"`. yfinance maps the
exchange/data-provider sector to an approximate GICS string. The ~11 values you will
encounter across S&P 500 / Nasdaq-100 / Dow-30:

```
"Technology"
"Healthcare"
"Financial Services"
"Consumer Cyclical"
"Consumer Defensive"
"Industrials"
"Communication Services"
"Energy"
"Basic Materials"
"Real Estate"
"Utilities"
```

Note the yfinance label "Financial Services" — GICS calls it "Financials"; Phase 7's
applicability matrix must match against yfinance's strings, not the GICS standard names.
[ASSUMED — label set sourced from training knowledge; verify against a live sample run.]

### Reliability and None handling

`.info` is the slow, web-scraped call. It raises exceptions for delisted tickers, network
timeouts, and some ADRs. `sector` itself can be absent (ETFs, shell companies) or `None`.
Always guard:

```python
try:
    sector = t.info.get("sector")   # str or None
except Exception:
    sector = None
```

If the call fails entirely, `sector = None`. Thread `None` forward as a first-class value —
Phase 6 adds the column but does not gate on it.

### Sharing the existing Ticker object

`get_yf_price_and_history()` already constructs `t = yf.Ticker(ticker)` at line 598. That
same object can fetch `.info`, `.history(...)`, and the already-used `.fast_info`,
`.income_stmt`, `.dividends` — all from one `Ticker` instance. No second `yf.Ticker(ticker)`
construction is needed.

**Extension point:** extend `get_yf_price_and_history()` to also return `sector` and the
5y-weekly `Close` series (or the computed signals). Both fetches are added inside the same
`try` block, against the same `t` object.

---

## 5-Year Weekly History Fetch

### The call

```python
hist = t.history(period="5y", interval="1wk")
```

- Returns a `pd.DataFrame` with a DatetimeIndex (UTC-aware) and columns including `Close`,
  `Open`, `High`, `Low`, `Volume`.
- Approximately 260 rows for a full 5-year window (~52 bars/year × 5).
- `Close` is the adjusted close (splits + dividends). [ASSUMED — yfinance default for
  `history()` is adjusted; verify against the `auto_adjust` default.]

### Current price

The function already reads `t.fast_info.last_price` as the current price, before the
history call. Use that value as `price` in all ratio calculations — do not use
`hist["Close"].iloc[-1]` as a substitute, because `fast_info` is already wired into the
rest of the pipeline and may reflect a fresher intraday price.

### Minimum bar guard (D-01b)

| Condition | Action |
|---|---|
| `hist` empty or `None` | all five signals = `None` |
| `len(hist) < 8` bars | all five signals = `None` (too thin to compute) |
| `8 <= len(hist) < 52` | compute over available window; set `short_history = True` coverage flag |
| `>= 52` bars | full computation; `short_history = False` |

The threshold of 8 is the minimum sensible window. Any recent IPO with fewer bars than 52
will compute a "52-week" high/low over whatever window exists — this is correct behaviour;
the `short_history` flag lets Phase 7 / `stats.html` surface it.

---

## Distance and Recency Computation

All five signals are computed from a single `Close` column slice. Use `price` (from
`fast_info`) as the current price throughout.

### Setup

```python
closes = hist["Close"]          # pd.Series, DatetimeIndex
n = len(closes)                 # number of weekly bars available

# 52-week window = last 52 bars (or all bars if fewer)
w52 = closes.iloc[-min(n, 52):]
high_52w = w52.max()
low_52w  = w52.min()

# 5-year window = all bars
low_5y = closes.min()
```

### Signal 1 — dist_below_52w_high (%)

"How far below the 52-week high is the current price?"
Larger value = cheaper / more beaten-down.

```python
dist_below_52w_high = (high_52w - price) / high_52w * 100
# clamp to [0, 100]: can't be above the high by construction,
# but price could momentarily exceed a stale weekly high
dist_below_52w_high = max(0.0, dist_below_52w_high)
```

### Signal 2 — dist_above_52w_low (%)

"How far above the 52-week low is the current price?"
Smaller value = nearer to the low = contrarian cheapness signal.

```python
dist_above_52w_low = (price - low_52w) / low_52w * 100
dist_above_52w_low = max(0.0, dist_above_52w_low)
```

### Signal 3 — dist_above_5y_low (%)

"How far above the 5-year low is the current price?"
Smaller value = cheaper on a multi-year basis.

```python
dist_above_5y_low = (price - low_5y) / low_5y * 100
dist_above_5y_low = max(0.0, dist_above_5y_low)
```

### Signal 4 — weeks_since_52w_low

"How many weekly bars ago did the 52-week low occur?"
Larger = basing longer = slightly more constructive for contrarian entry.

```python
idx_52w_low = int(w52.values.argmin())        # 0-based index within w52
weeks_since_52w_low = len(w52) - 1 - idx_52w_low
```

`argmin()` returns the position of the minimum within the slice. Subtracting from
`len(w52) - 1` gives bars-ago (0 = this week's bar is the low).

### Signal 5 — weeks_since_5y_low

"How many weekly bars ago did the 5-year low occur?"

```python
idx_5y_low = int(closes.values.argmin())      # 0-based index within all bars
weeks_since_5y_low = len(closes) - 1 - idx_5y_low
```

### Scoring direction (D-04 — VALUE pillar)

| Signal | "Cheaper" direction | Planner note |
|---|---|---|
| `dist_below_52w_high` | larger → higher score | normal band |
| `dist_above_52w_low` | **smaller** → higher score | inverted band |
| `dist_above_5y_low` | **smaller** → higher score | inverted band |
| `weeks_since_52w_low` | moderate "sweet spot" (recent = still falling; old = recovery) | monotone or U-shaped band — planner discretion |
| `weeks_since_5y_low` | same "sweet spot" pattern | same |

The recency signals modulate within Value: a very fresh low (0–2 weeks) may indicate
ongoing decline; an older, basing low (8–26 weeks) is more constructive. Exact band shape
is a Slice C / planner decision.

---

## Edge Cases

### Empty or failed history

```python
try:
    hist = t.history(period="5y", interval="1wk")
except Exception:
    hist = pd.DataFrame()

if hist is None or hist.empty or "Close" not in hist.columns:
    # return all five signals as None
```

### Short history / recent IPO

```python
if len(closes) < 8:
    # all five signals = None
elif len(closes) < 52:
    short_history = True
    # compute w52 = closes (all available); note the "52w" signals are
    # actually computed over fewer bars — label them accurately in JSON
else:
    short_history = False
```

The `short_history` flag should appear in the returned dict so `process_ticker()` can pass
it into the row and `write_json()` can emit it as a column. Phase 7 uses it for the sector
applicability guard.

### Zero denominator

`low_52w` or `low_5y` could theoretically be 0 (a penny stock that briefly touched zero,
or a data error). Guard:

```python
if low_52w == 0 or low_5y == 0:
    # set affected signals to None
```

In practice this won't occur for the S&P-500/Nasdaq-100/Dow-30 universe, but the guard
prevents a ZeroDivisionError.

### `.info` timeout vs. history timeout

Both calls share the same `try/except Exception` block in `get_yf_price_and_history()`.
If `.info` raises (e.g. timeout), the entire function returns early with the existing
fallback dict — sector and history signals all `None`. This is the correct fail-safe: a
partial fetch is worse than a clean `None` row that the average-over-present contract
handles gracefully (D-01b).

---

## Runtime Note

At ~550 tickers, adding `.info` + `t.history(period="5y", interval="1wk")` per ticker
adds two HTTP round-trips on top of the existing `fast_info`, `income_stmt`, and `dividends`
calls. `.info` is the heavier of the two (full page scrape vs. lightweight OHLCV endpoint).
A real cache (DATA-03) is Phase 7; for Phase 6 this is accepted added latency. Keep fetches
to one `Ticker` object per ticker to avoid redundant session creation.

---

## Assumptions Log

| # | Claim | Risk if Wrong |
|---|---|---|
| A1 | yfinance `info["sector"]` returns the ~11 GICS-like strings listed above | Phase 7 applicability guard may need different label matching |
| A2 | `history()` default is adjusted close (`auto_adjust=True`) | Distance signals computed on unadjusted prices if wrong; verify with a test ticker |
| A3 | `~260` weekly bars for a 5-year period | Off-by-a-few has no practical impact; the `< 52` guard handles the relevant edge |

---

# Phase 6: Cheap Factors + Sector — Research Slice C: Scoring Engine

**Slice:** C of 3 — threshold/band design, Value sub-grouping, `overall_score()` changes, JSON schema
**Date:** 2026-06-21
**Locked decisions:** D-04 (distances → Value), D-05 (3-sub-group Value, ROIC → Quality)
**All thresholds:** `[ASSUMED]` — no empirical anchor; Phase 7 `stats.html` calibrates

---

## Threshold Table

All new factors follow the existing config-block pattern: named `SCORE_*` constants at the
top of `stock_screener.py` (~82–192), tagged `# [ASSUMED]`, adjacent to the bands they govern.

### Value sub-group 2 — cash/earnings-yield cheapness

Higher raw = better for FCF yield, earnings yield, shareholder yield.
Lower raw = better for EV/EBIT (inverted via a descending-score band).

```python
# ── Value sub-group 2: cash/earnings-yield cheapness ─────────────────────────

# FCF yield (FCF / market cap, expressed as %)
# Negative FCF yield → D-01 worst-score path (cash-burning; present but terrible).
SCORE_FCF_YIELD_WIN_LO  = 0.0   # floor: negative handled via D-01 before winsorize
SCORE_FCF_YIELD_WIN_HI  = 15.0  # cap extreme FCF yields
SCORE_FCF_YIELD_BANDS   = [     # [ASSUMED] — monitor in Phase 7
    ( 0.0,  2.0,   0,  20),     # thin FCF yield
    ( 2.0,  5.0,  20,  60),     # moderate
    ( 5.0,  8.0,  60,  85),     # solid
    ( 8.0, 15.0,  85, 100),     # high FCF yield
]

# EV/EBIT (lower = cheaper; invert via descending bands)
# ≤ 0 or negative EBIT → D-01 worst-score (money-losing; present but terrible).
SCORE_EV_EBIT_WIN_LO    =  0.0  # floor (negatives handled via D-01)
SCORE_EV_EBIT_WIN_HI    = 40.0  # cap extreme multiples
SCORE_EV_EBIT_BANDS     = [     # [ASSUMED] — monitor in Phase 7; descending scores
    ( 0.0,  8.0, 100, 85),      # very cheap
    ( 8.0, 14.0,  85, 60),      # cheap
    (14.0, 20.0,  60, 30),      # fair
    (20.0, 40.0,  30,  0),      # expensive
]

# Earnings yield (EBIT / EV or EPS / Price, expressed as %)
# Negative earnings yield → D-01 worst-score.
SCORE_EARN_YIELD_WIN_LO =  0.0
SCORE_EARN_YIELD_WIN_HI = 20.0
SCORE_EARN_YIELD_BANDS  = [     # [ASSUMED] — monitor in Phase 7
    ( 0.0,  3.0,   0,  20),
    ( 3.0,  6.0,  20,  50),
    ( 6.0, 10.0,  50,  80),
    (10.0, 20.0,  80, 100),
]

# Shareholder yield (div yield + buyback yield, expressed as %)
# Zero/negative → D-01 worst-score (companies buying back nothing or issuing shares).
SCORE_SH_YIELD_WIN_LO   =  0.0
SCORE_SH_YIELD_WIN_HI   = 12.0
SCORE_SH_YIELD_BANDS    = [     # [ASSUMED] — monitor in Phase 7
    (0.0,  2.0,   0,  30),
    (2.0,  4.0,  30,  60),
    (4.0,  6.0,  60,  85),
    (6.0, 12.0,  85, 100),
]
```

### Value sub-group 3 — price-position (per D-04)

**Directional conventions** (critical — see Pitfall 1):

| Field | Direction | Higher raw = |
|---|---|---|
| `dist_52w_low` (% above 52w low) | NORMAL bands | more above low = less contrarian → LOWER score |
| `dist_52w_high` (% below 52w high) | NORMAL bands | more below high = deeper discount → HIGHER score |
| `dist_5y_low` (% above 5y low) | NORMAL bands | more above 5y low = less contrarian → LOWER score |
| `weeks_since_52w_low` | recency modifier, not standalone | used as multiplier, see §overall_score() changes |
| `weeks_since_5y_low` | recency modifier, not standalone | same |

Distance-from-low fields are "lower raw = better" for scoring purposes (near low = contrarian
buy). Use descending bands (score_lo > score_hi) rather than `_piecewise_score` inversion —
the band structure itself encodes the direction (same approach as EV/EBIT above).

```python
# ── Value sub-group 3: price-position ────────────────────────────────────────

# dist_52w_low: % the current price is above the 52-week low.
# 0% = AT the low (maximum contrarian signal = 100 score).
# Higher % = price has already bounced; score falls.
# Winsorize HI at 200% (price tripled from low — essentially no longer "near low").
SCORE_DIST_52W_LOW_WIN_LO =   0.0
SCORE_DIST_52W_LOW_WIN_HI = 200.0
SCORE_DIST_52W_LOW_BANDS  = [      # [ASSUMED] — descending: near low = 100
    (  0.0,  10.0, 100,  85),      # within 10% of 52w low — very contrarian
    ( 10.0,  30.0,  85,  55),
    ( 30.0,  60.0,  55,  25),
    ( 60.0, 200.0,  25,   0),
]

# dist_52w_high: % the current price is below the 52-week high.
# Higher = more below high = deeper price discount = better.
SCORE_DIST_52W_HIGH_WIN_LO =   0.0
SCORE_DIST_52W_HIGH_WIN_HI = 100.0
SCORE_DIST_52W_HIGH_BANDS  = [     # [ASSUMED] — ascending: far from high = 100
    ( 0.0,  5.0,   0,  10),        # within 5% of high — near peak
    ( 5.0, 20.0,  10,  50),
    (20.0, 40.0,  50,  80),
    (40.0,100.0,  80, 100),
]

# dist_5y_low: % the current price is above the 5-year low.
# Same directional logic as dist_52w_low; wider range (5y = more room to recover).
SCORE_DIST_5Y_LOW_WIN_LO =    0.0
SCORE_DIST_5Y_LOW_WIN_HI =  400.0
SCORE_DIST_5Y_LOW_BANDS  = [       # [ASSUMED] — descending: near 5y low = 100
    (  0.0,  20.0, 100,  85),
    ( 20.0,  60.0,  85,  55),
    ( 60.0, 120.0,  55,  25),
    (120.0, 400.0,  25,   0),
]
```

**Recency: weeks-since-low as a score multiplier (not a standalone sub-score).**

A fresh low (few weeks ago) suggests the stock is still falling — less attractive than one
that bottomed out months ago and is now basing. Apply as a decay multiplier to each
distance-from-low raw score before averaging into the sub-group:

```python
# Recency multiplier applied to dist_52w_low and dist_5y_low raw scores.
# weeks=0..4: multiplier ~0.70 (very fresh; may still be falling)
# weeks=13..26: multiplier ~0.85 (recent but stabilizing)
# weeks≥26: multiplier 1.00 (basing; full contrarian credit)
# Multiplier range [0.70, 1.00] — never zero (the price signal still has value).
SCORE_RECENCY_FLOOR   = 0.70   # [ASSUMED]
SCORE_RECENCY_FULL_WK = 26     # weeks at which full credit is granted [ASSUMED]

def _recency_multiplier(weeks_since_low: float | None) -> float:
    """Linear ramp from SCORE_RECENCY_FLOOR at 0 weeks to 1.0 at SCORE_RECENCY_FULL_WK."""
    if weeks_since_low is None:
        return 1.0   # absent = don't penalise; treat as basing
    t = min(1.0, weeks_since_low / SCORE_RECENCY_FULL_WK)
    return SCORE_RECENCY_FLOOR + t * (1.0 - SCORE_RECENCY_FLOOR)
```

The multiplier is applied inside the `_score_price_position()` helper (see below), not as a
separate sub-score that dilutes into the average — recency modulates the quality of the
distance signal rather than standing independently.

### Quality addition — ROIC

```python
# ── Quality pillar: ROIC ─────────────────────────────────────────────────────
# Negative ROIC → D-01 worst-score (capital-destroying; present but terrible).
SCORE_ROIC_WIN_LO =   0.0
SCORE_ROIC_WIN_HI =  50.0   # cap extreme ROIC (asset-light outliers)
SCORE_ROIC_BANDS  = [        # [ASSUMED] — monitor in Phase 7
    ( 0.0,  5.0,   0,  20),  # low/poor capital returns
    ( 5.0, 10.0,  20,  50),
    (10.0, 20.0,  50,  85),
    (20.0, 50.0,  85, 100),
]
```

---

## overall_score() Changes

### New signature

Add seven new parameters after `aaa_yield`:

```python
def overall_score(
    # existing params (unchanged)
    lynch_discount: float | None,
    graham_discount: float | None,
    defensive_score: float | None,
    debt_equity: float | None,
    current_ratio: float | None,
    growth_g: float | None,
    growth_stability: float | None,
    is_trap: bool,
    coverage_fraction: float,
    aaa_yield: float,
    # Phase 6 additions
    fcf_yield: float | None,
    ev_ebit: float | None,
    earnings_yield: float | None,
    shareholder_yield: float | None,
    roic: float | None,
    dist_52w_low: float | None,
    dist_52w_high: float | None,
    dist_5y_low: float | None,
    weeks_since_52w_low: float | None,
    weeks_since_5y_low: float | None,
) -> dict:
```

All new params default to `None` to maintain backward compatibility with existing tests
(Python keyword args). Existing positional callers pass `aaa_yield` as the last positional;
new params are keyword-only in practice.

### Value pillar — three sub-group structure (D-05)

Replace the current single-sub-group value block with the three-sub-group design:

```python
# ── VALUE PILLAR ──────────────────────────────────────────────────────────────
# (rate_scale and _scaled_disc_bands unchanged)

# Sub-group 1: valuation-discount (Lynch + Graham — existing logic)
lynch_sub  = _score_discount(lynch_discount)
graham_sub = _score_discount(graham_discount)
discount_group = _avg_present([lynch_sub, graham_sub])

# Sub-group 2: cash/earnings-yield cheapness
def _score_fcf_yield(v: float | None) -> float | None:
    if v is None: return None
    if v <= 0: return 0.0           # D-01: negative FCF → worst
    return _piecewise_score(_winsorize(v, SCORE_FCF_YIELD_WIN_LO, SCORE_FCF_YIELD_WIN_HI),
                            SCORE_FCF_YIELD_BANDS)

def _score_ev_ebit(v: float | None) -> float | None:
    if v is None: return None
    if v <= 0: return 0.0           # D-01: negative EBIT → worst
    return _piecewise_score(_winsorize(v, SCORE_EV_EBIT_WIN_LO, SCORE_EV_EBIT_WIN_HI),
                            SCORE_EV_EBIT_BANDS)

def _score_earn_yield(v: float | None) -> float | None:
    if v is None: return None
    if v <= 0: return 0.0           # D-01: negative → worst
    return _piecewise_score(_winsorize(v, SCORE_EARN_YIELD_WIN_LO, SCORE_EARN_YIELD_WIN_HI),
                            SCORE_EARN_YIELD_BANDS)

def _score_sh_yield(v: float | None) -> float | None:
    if v is None: return None
    if v <= 0: return 0.0
    return _piecewise_score(_winsorize(v, SCORE_SH_YIELD_WIN_LO, SCORE_SH_YIELD_WIN_HI),
                            SCORE_SH_YIELD_BANDS)

fcf_sub   = _score_fcf_yield(fcf_yield)
evebit_sub = _score_ev_ebit(ev_ebit)
earny_sub = _score_earn_yield(earnings_yield)
shy_sub   = _score_sh_yield(shareholder_yield)
yield_group = _avg_present([fcf_sub, evebit_sub, earny_sub, shy_sub])

# Sub-group 3: price-position (D-04)
def _score_price_position(
    d_52w_lo, d_52w_hi, d_5y_lo, wk_52w, wk_5y
) -> float | None:
    # dist_52w_low sub-score with recency modulation
    if d_52w_lo is not None:
        raw = _piecewise_score(
            _winsorize(d_52w_lo, SCORE_DIST_52W_LOW_WIN_LO, SCORE_DIST_52W_LOW_WIN_HI),
            SCORE_DIST_52W_LOW_BANDS,
        )
        s_52w_lo = raw * _recency_multiplier(wk_52w)
    else:
        s_52w_lo = None

    # dist_52w_high sub-score (no recency — high-proximity is always current)
    if d_52w_hi is not None:
        s_52w_hi = _piecewise_score(
            _winsorize(d_52w_hi, SCORE_DIST_52W_HIGH_WIN_LO, SCORE_DIST_52W_HIGH_WIN_HI),
            SCORE_DIST_52W_HIGH_BANDS,
        )
    else:
        s_52w_hi = None

    # dist_5y_low sub-score with recency modulation
    if d_5y_lo is not None:
        raw = _piecewise_score(
            _winsorize(d_5y_lo, SCORE_DIST_5Y_LOW_WIN_LO, SCORE_DIST_5Y_LOW_WIN_HI),
            SCORE_DIST_5Y_LOW_BANDS,
        )
        s_5y_lo = raw * _recency_multiplier(wk_5y)
    else:
        s_5y_lo = None

    return _avg_present([s_52w_lo, s_52w_hi, s_5y_lo])

price_group = _score_price_position(
    dist_52w_low, dist_52w_high, dist_5y_low,
    weeks_since_52w_low, weeks_since_5y_low,
)

# D-05: Value = average of the three sub-group scores (each normalized 0–100)
# _avg_present skips sub-groups that are entirely absent (D-01b)
score_value = _avg_present([discount_group, yield_group, price_group])
```

### Quality pillar — add ROIC

Append `roic_sub` to the existing `_avg_present` call:

```python
def _score_roic(v: float | None) -> float | None:
    if v is None: return None
    if v <= 0: return 0.0           # D-01: negative ROIC → worst
    return _piecewise_score(_winsorize(v, SCORE_ROIC_WIN_LO, SCORE_ROIC_WIN_HI),
                            SCORE_ROIC_BANDS)

roic_sub = _score_roic(roic)
score_quality = _avg_present([def_sub, de_sub, cr_sub, roic_sub])  # was [def_sub, de_sub, cr_sub]
```

### Growth pillar — unchanged

No modifications.

### Safety pillar — unchanged

No modifications. D-01 negative-routing and missing-Safety-unknown (coverage_fraction == 0)
contract preserved verbatim.

### coverage_pct — extend to new sub-scores

`all_sub_scores` currently lists 8 items. Phase 6 adds 9 new sub-scores across the three new
sub-groups. The denominator grows from 8 to 17 (or however many are non-None-by-design):

```python
all_sub_scores = [
    # Value sub-group 1 (existing)
    lynch_sub, graham_sub,
    # Value sub-group 2 (new)
    fcf_sub, evebit_sub, earny_sub, shy_sub,
    # Value sub-group 3 (new)
    s_52w_lo, s_52w_hi, s_5y_lo,
    # Quality (existing + new)
    def_sub, de_sub, cr_sub, roic_sub,
    # Growth (existing)
    growth_g_sub, growth_stab_sub,
    # Safety (existing)
    score_safety,
]
```

The sub-group scores (e.g. `discount_group`, `yield_group`, `price_group`) are NOT in this
list — they are intermediate aggregations. Only leaf sub-scores count toward coverage so
coverage_pct reflects actual data density, not grouping math. The 3 price-position
sub-scores (`s_52w_lo`, `s_52w_hi`, `s_5y_lo`) need to be extracted from inside
`_score_price_position` to make them visible at this level — either refactor that helper
to return a tuple, or compute them inline so they are in local scope.

**Recommended:** compute inline (avoid a new public API; keeps the pattern consistent with
the existing quality and growth sub-score locals).

### Return dict — add sub-group scores (optional detail)

Extend the return dict with sub-group scores for dashboard/debug use:

```python
return {
    "overall":           overall,
    "value":             round(score_value,   2) if score_value   is not None else None,
    "quality":           round(score_quality, 2) if score_quality is not None else None,
    "growth":            round(score_growth,  2) if score_growth  is not None else None,
    "safety":            score_safety,
    "coverage_pct":      coverage_pct,
    # Sub-group detail (Phase 6 addition)
    "value_discount":    round(discount_group, 2) if discount_group is not None else None,
    "value_yield":       round(yield_group,    2) if yield_group    is not None else None,
    "value_price":       round(price_group,    2) if price_group    is not None else None,
}
```

---

## Value Sub-Grouping — Rationale Summary

The three sub-groups prevent cheapness multi-counting (D-05):

| Sub-group | Inputs | What it measures |
|---|---|---|
| `discount_group` | Lynch discount, Graham discount | Margin of safety vs. fundamental fair value |
| `yield_group` | FCF yield, EV/EBIT (inv), earnings yield, shareholder yield | Running cash/earnings return at current price |
| `price_group` | dist_52w_low (mod), dist_52w_high, dist_5y_low (mod) | Price position relative to recent history |

Without sub-grouping: a stock with 4 yield inputs scores 4x the Value weight of a stock
missing those fields. Sub-grouping means each dimension of "cheapness" contributes equally
regardless of how many inputs are present in it — a well-covered yield group and a
well-covered discount group each count for one third of Value, not all six sub-scores
dragging toward whichever bucket happens to be fullest.

---

## JSON Schema Additions

**Additive only.** Existing keys (`OverallScore`, `score_value`, `score_quality`,
`score_growth`, `score_safety`, `is_trap`, `coverage_pct`, `scores.*`) are untouched.

### New flat row columns (added in `process_ticker`)

| Column | Type | Notes |
|---|---|---|
| `Sector` | string \| null | GICS-like sector from yfinance `.info['sector']` |
| `fcf_yield` | float \| null | FCF / market cap, % |
| `ev_ebit` | float \| null | EV / EBIT multiple |
| `earnings_yield` | float \| null | EBIT/EV or EPS/Price, % |
| `shareholder_yield` | float \| null | div yield + buyback yield, % |
| `roic` | float \| null | Return on invested capital, % |
| `dist_52w_low` | float \| null | % above 52-week low |
| `dist_52w_high` | float \| null | % below 52-week high |
| `dist_5y_low` | float \| null | % above 5-year low |
| `weeks_since_52w_low` | float \| null | weeks since 52-week low was set |
| `weeks_since_5y_low` | float \| null | weeks since 5-year low was set |

### Extended `scores` nested object (added in `write_json`)

```python
row["scores"] = {
    # existing keys — unchanged
    "overall":      row.get("OverallScore"),
    "value":        row.get("score_value"),
    "quality":      row.get("score_quality"),
    "growth":       row.get("score_growth"),
    "safety":       row.get("score_safety"),
    "coverage_pct": row.get("coverage_pct"),
    "trap":         row.get("is_trap", False),
    # Phase 6 additions
    "value_discount": row.get("score_value_discount"),
    "value_yield":    row.get("score_value_yield"),
    "value_price":    row.get("score_value_price"),
}
```

Store sub-group scores as flat columns `score_value_discount`, `score_value_yield`,
`score_value_price` in `process_ticker` (mirroring the `score_value` / `score_quality`
pattern), then read them in `write_json`. Avoids the dict-in-DataFrame edge case (existing
Pitfall 3 pattern).

**Compact encoding preserved:** `json.dumps(payload, separators=(",", ":"))` unchanged.
**Min-row guard:** `len(df) < 100` check in `write_json` unchanged.

---

## Pitfalls

### Pitfall 1 — Invert direction: lower-raw-better fields

EV/EBIT, dist_52w_low, and dist_5y_low all use descending-score band tables (score_lo >
score_hi). If you accidentally write ascending bands for these, cheap stocks score 0 and
expensive stocks score 100 — a silent polarity flip. Audit: for each descending-band field,
`bands[0][2] > bands[0][3]` must be true (first band's score_lo > score_hi).
Write a single-line assert in the test suite for each affected constant.

### Pitfall 2 — Cheapness double-counting without sub-grouping

Without the three-sub-group structure, a ticker with all four yield inputs (FCF yield,
EV/EBIT, earnings yield, shareholder yield) would have those four sub-scores averaged into
Value alongside the two discount sub-scores — effectively weighting yield evidence 4:2 over
discount evidence. The sub-group design makes each dimension equally weighted regardless of
per-dimension input count. Do not flatten all inputs into one `_avg_present` call at the
Value level.

### Pitfall 3 — Recency as standalone signal vs. modifier

`weeks_since_52w_low` and `weeks_since_5y_low` must NOT be independent sub-scores in the
price-position sub-group. If they were, a ticker missing distance data but having recency
data would receive a spurious price-position score. Recency is a multiplier on the distance
scores it modulates; absent recency = multiplier 1.0 (no penalty, distance gets full credit).
Do not add `wk_52w` or `wk_5y` to `all_sub_scores` for coverage_pct purposes.

### Pitfall 4 — coverage_pct denominator growth

Phase 5 `all_sub_scores` had 8 entries. Phase 6 adds 7 new leaf sub-scores (3 yield — FCF /
earnings / shareholder, EV/EBIT diagnostic-only per Open Questions RESOLVED #1 — + 3
price-position + 1 ROIC; recency excluded per Pitfall 3), raising the denominator to 15.
A ticker with good fundamental data but no 5y history will now show lower `coverage_pct`
than it did in Phase 5. This is correct behavior (more tracked inputs = more ways to be
partial) but will show up as a drop in the coverage column for existing tickers. Document in
the Phase 6 summary; do not treat as a bug.

### Pitfall 5 — overall_score() signature break

Existing tests call `overall_score()` with 10 positional arguments. The Phase 6 additions
must be keyword-only (place after `aaa_yield`, give default `None`) so existing test calls
remain valid without modification. Verify with `ast.parse` + the test suite before and
after the change.

---

## Open Questions (RESOLVED)

1. **EV/EBIT vs. earnings yield redundancy. — RESOLVED.** They are exact reciprocals
   (EV/EBIT = 1 / (EBIT/EV)), computed from the same EV + EBIT figures, so scoring both
   would double-weight one signal inside the yield sub-group. **Decision: score
   `earnings_yield` only; keep `EV_EBIT` as a diagnostic-only emitted column (not fed into
   the score).** No `_score_ev_ebit`, no `evebit_sub`, no `SCORE_EV_EBIT_*` constant. SIGNAL-05
   is still satisfied — both EV/EBIT and earnings yield appear as row fields and earnings_yield
   is the folded scoring input. (Implemented in 06-02-PLAN.md; confirmed by plan-checker.)

2. **Shareholder yield coverage. — RESOLVED.** Keep shareholder yield in the yield
   sub-group. The `_avg_present` contract is average-over-*present*, not average-over-all, so a
   frequently-`None` input simply does not contribute to that sub-group's average — it does not
   dilute it. The `shareholder_yield_partial` flag surfaces low coverage for monitoring. No
   change needed; revisit thresholds in Phase 7 if `stats.html` shows it adds noise.
