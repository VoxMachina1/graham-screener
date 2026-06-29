# Phase 7: Distress Signals, DCF, Stats & Snapshots - Pattern Map

**Mapped:** 2026-06-28
**Files analyzed:** 10
**Analogs found:** 10 / 10

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `stock_screener.py` — `_compute_piotroski()` | utility | transform | `_compute_fcf_yield()` (line 876) | exact |
| `stock_screener.py` — `_compute_altman_z()` | utility | transform | `_compute_roic()` (line 910) | exact |
| `stock_screener.py` — `_compute_dcf_forward()` + `_compute_dcf_reverse()` | utility | transform | `_compute_ev_ebit()` (line 892) | role-match |
| `stock_screener.py` — `_yf_row_prev()` | utility | transform | `_yf_row()` (line 805) | exact |
| `stock_screener.py` — `overall_score()` Safety pillar | utility | transform | current Safety block (lines 549–611) | exact (replace) |
| `stock_screener.py` — `process_ticker()` additions | service | request-response | `process_ticker()` lines 1595–1654 | exact (extend) |
| `stock_screener.py` — `write_json()` additions | service | batch | `write_json()` lines 1691–1723 | exact (extend) |
| `stock_screener.py` — `get_yf_price_and_history()` additions | service | request-response | `get_yf_price_and_history()` lines 945–1050 | exact (extend) |
| `tests/test_distress_phase7.py` | test | transform | `tests/test_factors_phase6.py` | exact |
| `tests/test_dcf_phase7.py` | test | transform | `tests/test_factors_phase6.py` | exact |
| `docs/stats.html` | component | request-response | `docs/top.html` (fetch + render pattern) | role-match |
| `docs/history.html` | component | request-response | `docs/top.html` (fetch + render pattern) | role-match |
| `docs/app.js` — NAV_ENTRIES + buildNav() | utility | event-driven | `docs/app.js` lines 107–120 | exact (extend) |
| `docs/top.html` — Safety chip | component | event-driven | `docs/top.html` lines 122–131 | exact (replace) |
| `.github/workflows/screener.yml` | config | event-driven | existing commit step (lines 34–42) | role-match |
| `.gitignore` | config | — | existing `!docs/data/results.json` exception | exact |

---

## Pattern Assignments

### `_compute_piotroski()` and `_compute_altman_z()` (new pure helpers in stock_screener.py)

**Analog:** `_compute_fcf_yield()` (line 876) and `_compute_roic()` (line 910)

**Imports pattern** — no new imports needed; scipy only for DCF reverse.

**Core helper pattern** (lines 876–925) — copy this structure exactly:
```python
def _compute_fcf_yield(ocf, capex, market_cap) -> float | None:
    """
    Compute FCF yield as a whole-number percent.
    ...
    internal — for tests only.
    """
    if ocf is None:
        return None
    fcf = ocf + capex if capex is not None else ocf
    if not market_cap:
        return None
    return fcf / market_cap * 100


def _compute_roic(ebit, total_debt, equity, cash) -> float | None:
    """
    Compute ROIC as a whole-number percent.
    ...
    internal — for tests only.
    """
    if ebit is None or total_debt is None or equity is None:
        return None
    c = cash if cash is not None else 0
    invested = total_debt + equity - c
    if invested <= 0:
        return None
    return ebit * (1 - 0.21) / invested * 100
```

**Key conventions to copy:**
- Docstring must include `internal — for tests only.`
- None-guard all required inputs at the top; return None immediately
- Optional inputs default via `if x is not None else fallback`
- Return `float | None` type hint
- No logging, no side effects — pure numeric transform

**SCORE_* config block pattern** (lines 82–281) — extend with new constants in the same style:
```python
# ── Safety pillar: Piotroski F-Score bands ───────────────────────────────
SCORE_PIOTROSKI_BANDS = [      # [ASSUMED] — no empirical anchor; monitor in Phase 7
    (0, 2,   0,  20),          # distressed
    (2, 4,  20,  40),          # weak
    (4, 6,  40,  65),          # average
    (6, 8,  65,  85),          # strong
    (8, 9,  85, 100),          # very strong
]

# ── Safety pillar: Altman Z'' bands ──────────────────────────────────────
SCORE_ALTMAN_DISTRESS = 1.1    # [ASSUMED] below = distress zone
SCORE_ALTMAN_SAFE     = 2.6    # [ASSUMED] above = safe zone
SCORE_ALTMAN_BANDS = [         # [ASSUMED] — no empirical anchor; monitor in Phase 7
    (-999.0,  1.1,   0,   0),  # distress zone
    (   1.1,  2.6,   0,  70),  # grey zone (interpolated)
    (   2.6, 10.0,  70, 100),  # safe zone
]

# ── DCF config ─────────────────────────────────────────────────────────────
DCF_ERP                = 5.5   # [ASSUMED] equity risk premium %
DCF_TERMINAL_GROWTH_CAP = 3.0  # [ASSUMED] cap terminal growth at nominal GDP
DCF_EXCLUDED_SECTORS   = {"Financial Services", "Real Estate"}
ALTMAN_EXCLUDED_SECTORS = {"Financial Services"}
```

---

### `_yf_row_prev()` (new helper in stock_screener.py)

**Analog:** `_yf_row()` (lines 805–816)

**Pattern to copy and adapt:**
```python
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
```

Phase 7 adds a companion that reads `df.columns[1]` (prior year). Also note the two-year shares pattern already in `get_yf_price_and_history()` at line 1041–1046:
```python
for label in SHARES_LABELS:
    if label in bs.index:
        shares_row = bs.loc[label]
        result["shares_now"]  = _safe_float(shares_row.iloc[0]) if len(shares_row) >= 1 else None
        result["shares_prev"] = _safe_float(shares_row.iloc[1]) if len(shares_row) >= 2 else None
        break
```
`_yf_row_prev()` generalizes `iloc[1]` with a `df.shape[1] < 2` guard — exactly the same shape-check pattern.

---

### `overall_score()` Safety pillar replacement (lines 549–611)

**Analog:** existing Safety block (lines 549–561) + Quality block pattern (lines 499–529)

**Current Safety block to replace** (lines 549–561):
```python
# ── SAFETY PILLAR (D-03 / D-01b) ─────────────────────────────────────────
if is_trap:
    score_safety = float(SCORE_SAFETY_TRAP_PENALTY)
elif coverage_fraction == 0.0:
    score_safety = None
else:
    score_safety = round(SCORE_SAFETY_NOTRAP_BASE * coverage_fraction, 2)
```

**Pattern to copy from Quality pillar** (lines 499–529) — the inner scorer functions + `_avg_present` call:
```python
def _score_defensive(ds: float | None) -> float | None:
    if ds is None:
        return None
    return _piecewise_score(_winsorize(ds, 0.0, 8.0), SCORE_DEF_BANDS)

def _score_debt_equity(de: float | None) -> float | None:
    if de is None:
        return None
    if de < 0:
        return 0.0
    return _piecewise_score(_winsorize(de, 0.0, SCORE_DE_WIN_HI), SCORE_DE_BANDS)

def _score_current_ratio(cr: float | None) -> float | None:
    if cr is None:
        return None
    return _piecewise_score(_winsorize(cr, 0.0, SCORE_CR_WIN_HI), SCORE_CR_BANDS)

def_sub   = _score_defensive(defensive_score)
de_sub    = _score_debt_equity(debt_equity)
cr_sub    = _score_current_ratio(current_ratio)
...
score_quality = _avg_present([def_sub, de_sub, cr_sub, roic_sub])
```

**D-04 absent→50.0 pattern** (new for Phase 7 — different from D-01b): Piotroski and Altman specifically use `50.0` when None, not `_avg_present` skip. Inner scorer:
```python
def _score_piotroski(f: int | None) -> float:
    # D-04: absent → neutral 50.0 (not avg-over-present skip)
    if f is None:
        return 50.0
    return _piecewise_score(float(f), SCORE_PIOTROSKI_BANDS)

def _score_altman(z: float | None) -> float:
    # D-04: absent → neutral 50.0
    if z is None:
        return 50.0
    return _piecewise_score(_winsorize(z, -999.0, 10.0), SCORE_ALTMAN_BANDS)
```
Both always return `float` (never None), so the `_avg_present` call always sees them as present. The existing `def_sub`, `de_sub`, `cr_sub` retain D-01b (None → avg-over-present skip).

**`all_sub_scores` list** (line 576–583) — extend to replace `score_safety` leaf with `piotroski_sub` + `altman_sub` (+ optionally `dcf_discount_sub`):
```python
all_sub_scores = [
    lynch_sub, graham_sub,                          # Value: discount
    fcf_sub, earny_sub, shy_sub,                    # Value: yield
    s_52w_lo, s_52w_hi, s_5y_lo,                   # Value: price-position
    def_sub, de_sub, cr_sub, roic_sub,              # Quality
    growth_g_sub, growth_stab_sub,                  # Growth
    piotroski_sub, altman_sub,                      # Safety (Phase 7 — replaces score_safety leaf)
    # dcf_discount_sub if added to Value
]
```

**`overall_score()` signature extension pattern** (lines 381–401) — Phase 6 added 9 None-defaulted params after the original 10 positional. Phase 7 removes `is_trap` / `coverage_fraction` and adds 3 new None-defaulted params at the end:
```python
# Remove from signature:
#   is_trap: bool
#   coverage_fraction: float
# Add at end (None-defaulted):
    piotroski_f: int | None = None,
    altman_z: float | None = None,
    dcf_discount_pct: float | None = None,
```
Note: `coverage_fraction` is retained per RESEARCH.md — it still informs Quality coverage. Only `is_trap` is removed.

---

### `process_ticker()` additions (extend lines 1595–1654)

**Analog:** existing `process_ticker()` call site (lines 1583–1654)

**Sector gate pattern** — copy the `fund.get("sector")` pattern already established (line 1635). Phase 7 adds a gate helper before calling `overall_score()`:
```python
# Existing pattern (line 1588–1593):
is_trap, cov_fraction = trap_gate(
    debt_equity   = fund["debt_equity"],
    current_ratio = fund["current_ratio"],
    eps_stability = eps_stab_for_gate,
    fcf_per_share = fund["fcf_per_share"],
)

# Phase 7 pattern (new, before overall_score call):
sector = fund.get("sector") or ""
piotroski_f = _compute_piotroski(...)   # no sector exclusion
altman_z    = _compute_altman_z(...)    if sector not in ALTMAN_EXCLUDED_SECTORS else None
dcf_result  = _compute_dcf_forward(...) if sector not in DCF_EXCLUDED_SECTORS    else (None, None)
```

**overall_score() call extension** (lines 1599–1619) — copy the existing kwarg-pass pattern:
```python
scores = overall_score(
    lynch_discount      = lm.get("Lynch_Discount_Pct"),
    ...
    # existing Phase-6 kwargs:
    roic                = fund.get("roic"),
    dist_52w_low        = fund.get("dist_52w_low"),
    ...
    weeks_since_5y_low  = fund.get("weeks_since_5y_low"),
    # Phase-7 additions:
    piotroski_f         = piotroski_f,
    altman_z            = altman_z,
    dcf_discount_pct    = dcf_discount_pct,
)
```

**Flat column addition pattern** (lines 1638–1654) — copy `_r2()` helper + column assignment:
```python
def _r2(v):
    return round(float(v), 2) if v is not None else None

row["Dist_52w_High_Pct"]    = _r2(fund["dist_52w_high"])
# Phase 7 additions follow same pattern:
row["Piotroski_F"]          = piotroski_f         # int | None (no rounding)
row["Altman_Z"]             = _r2(altman_z)
row["DCF_Intrinsic_Value"]  = _r2(dcf_intrinsic)
row["DCF_Discount_Pct"]     = _r2(dcf_discount_pct)
row["DCF_Implied_Growth"]   = _r2(dcf_implied_growth)
row["dcf_reverse_converged"] = dcf_reverse_converged  # bool
```

---

### `write_json()` additions (extend lines 1691–1723)

**Analog:** existing `write_json()` (lines 1691–1723)

**Nested scores object pattern** (lines 1702–1714) — extend by adding new keys:
```python
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
        "trap":           row.get("is_trap", False),       # keep for backward compat
        # Phase 7 additions:
        "piotroski":      row.get("score_piotroski_sub"),  # sub-score 0–100 | 50.0
        "altman":         row.get("score_altman_sub"),
        "dcf_discount":   row.get("score_dcf_discount_sub"),
    }
```

**stats.json write pattern** — add a `_compute_stats(df)` helper called from `write_json()`, following the `datetime.utcnow().strftime(...)` + `Path.write_text(json.dumps(...))` pattern (lines 1716–1722):
```python
STATS_PATH = Path("docs/data/stats.json")

def _compute_stats(df: pd.DataFrame) -> dict:
    """Compute universe-level stats for stats.html. Pure DataFrame transform."""
    ...
    return { "generated_at": ..., "universe_count": ..., ... }

# In write_json(), after writing results.json:
stats = _compute_stats(df)
STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
STATS_PATH.write_text(json.dumps(stats, separators=(",", ":")), encoding="utf-8")
```

---

### `get_yf_price_and_history()` additions (extend lines 945–1050)

**Analog:** existing function (lines 945–1050)

**Return dict initialization pattern** (lines 959–979) — add new keys with None defaults:
```python
result = {
    "price":              None,
    "annual_eps":         [],
    ...
    # Phase 7 additions:
    "income_stmt_df":     None,   # raw DataFrame for Piotroski/Altman
    "balance_sheet_df":   None,
    "cashflow_df":        None,
}
```

**Statement capture pattern** (lines 995–1046) — existing code reads `t.income_stmt`, `t.balance_sheet`, `t.cashflow` but only extracts specific rows. Phase 7 also stores the raw DataFrames:
```python
# Existing:
inc = t.income_stmt
if inc is not None and not inc.empty:
    inc = inc.sort_index(axis=1)   # NOTE: sorted for EPS; do NOT use sorted version
    ...                             # for Piotroski (needs newest-first column order)
    result["ebit"] = _yf_row(t.income_stmt, EBIT_LABELS)  # raw (unsorted)

# Phase 7 addition — store raw unsorted DataFrames:
result["income_stmt_df"]   = t.income_stmt    # raw, newest-first (columns[0] = newest)
result["balance_sheet_df"] = t.balance_sheet
result["cashflow_df"]      = t.cashflow
```

**Error guard pattern** (lines 1048–1050) — all fetches are inside the outer `try/except`:
```python
    except Exception as e:
        log.warning(f"yfinance error for {ticker}: {e}")
    return result
```
Phase 7 raw DataFrame stores follow the same pattern — if the ticker fetch fails, all new keys remain None.

---

### `tests/test_distress_phase7.py` and `tests/test_dcf_phase7.py` (new test files)

**Analog:** `tests/test_factors_phase6.py` (full file)

**File header pattern** (lines 1–36):
```python
"""
Phase 7 distress signal helper tests
======================================
Covers: _compute_piotroski, _compute_altman_z, _yf_row_prev
...

DESIGN RULES (match test_growth_trap_fixes.py):
  - Vanilla assert only — no pytest dependency.
  - Env vars set BEFORE importing stock_screener (module reads them at import).
  - No network calls, no yf.Ticker — all inputs are plain dicts/lists/values.

HOW TO RUN:
    python tests/test_distress_phase7.py
"""

import os
import sys

os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd

from stock_screener import (
    _compute_piotroski,
    _compute_altman_z,
    _yf_row_prev,
)
```

**Test function pattern** (lines 41–80 of test_factors_phase6.py):
```python
def test_NAME_happy_path():
    result = _compute_X(arg1=VAL, arg2=VAL, ...)
    assert abs(result - EXPECTED) < 1e-9, f"expected {EXPECTED}, got {result}"

def test_NAME_none_when_CONDITION():
    result = _compute_X(arg1=None, ...)
    assert result is None, f"expected None, got {result}"
```

**Fixture DataFrame pattern** for Piotroski/Altman (pandas DataFrame with known values):
```python
def _make_income_stmt(net_income, gross_profit, revenue, col="2024-01-01"):
    """Synthetic income_stmt DataFrame (newest-first column order)."""
    data = {
        "Net Income": [net_income],
        "Gross Profit": [gross_profit],
        "Total Revenue": [revenue],
    }
    return pd.DataFrame(data, index=["Net Income", "Gross Profit", "Total Revenue"]).T
    # columns[0] = newest year
```

**run_all() pattern** — check test_factors_phase6.py end for the exact run_all() + `__main__` block to copy.

---

### `docs/app.js` — NAV_ENTRIES + buildNav() extension

**Analog:** `docs/app.js` lines 107–120 (exact)

**Current NAV_ENTRIES** (lines 107–112):
```javascript
var NAV_ENTRIES = [
  { label: "Dashboard",   href: "index.html",       key: "dashboard" },
  { label: "Top Picks",   href: "top.html",          key: "top" },
  { label: "Methodology", href: "methodology.html",  key: "methodology" }
  // Phase 7: { label: "Stats", href: "stats.html", key: "stats" }
];
```

**Phase 7 replacement** — insert Stats and History before Methodology:
```javascript
var NAV_ENTRIES = [
  { label: "Dashboard",   href: "index.html",       key: "dashboard" },
  { label: "Top Picks",   href: "top.html",          key: "top" },
  { label: "Stats",       href: "stats.html",        key: "stats" },
  { label: "History",     href: "history.html",      key: "history" },
  { label: "Methodology", href: "methodology.html",  key: "methodology" }
];
```

**buildNav() is unchanged** (lines 114–120) — it reads NAV_ENTRIES; no modification needed.

---

### `docs/top.html` — Safety chip (replacing trap badge)

**Analog:** `docs/top.html` lines 72–84 (signalChipHtml) + lines 122–131 (pillar chips)

**Current trap badge** (line 122):
```javascript
(r.is_trap ? '<span class="trap-badge">TRAP</span>' : '')
```

**Replace with** — Safety chip already rendered as a pillar chip on row 2 (line 130):
```javascript
'<span class="pillar-chip">Safety: '  + fmtPillar(r.score_safety)  + '</span>'
```
The Safety pillar chip is already present on row 2. The only change is removing the `is_trap ? '<span class="trap-badge">TRAP</span>'` ternary from row 1. No new chip function needed — `fmtPillar(r.score_safety)` already displays the Safety score. The trap badge line (122) is deleted entirely.

---

### `docs/stats.html` and `docs/history.html` (new pages)

**Analog:** `docs/top.html` for fetch + render structure; `docs/app.js` for nav/freshness helpers

**Fetch pattern** (from top.html and app.js):
```javascript
// Cache-busted fetch (matches results.json pattern)
fetch("data/stats.json?v=" + Date.now())
  .then(function(r) { return r.json(); })
  .then(function(data) {
    updateFreshnessUI(data.generated_at);   // reuse app.js helper
    renderStats(data);
  })
  .catch(function(err) {
    document.getElementById("stats-container").innerHTML =
      '<p>Could not load stats data.</p>';
  });
```

**Nav activation pattern** — each page calls `buildNav("stats")` or `buildNav("history")` at the bottom of its `<script>` block (matches `buildNav("top")` in top.html, `buildNav("dashboard")` in index.html).

**updateFreshnessUI** (app.js lines 93–104) — already shared; both new pages call it with `data.generated_at`. No changes to the function.

**escHtml** (app.js lines 49–56) — use for any ticker/sector strings displayed in stats or history tables.

---

### `.github/workflows/screener.yml` — snapshot step

**Analog:** existing "Commit and push results" step (lines 34–42)

**Current commit step** (lines 34–42):
```yaml
- name: Commit and push results
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
    git add docs/data/results.json
    if ! git diff --cached --quiet; then
      git commit -m "chore: update screener results"
      git push
    fi
```

**Phase 7 additions** — two new steps inserted after the existing commit step:
```yaml
- name: Check if first weekday of month
  id: check-date
  run: |
    DAY=$(date +%d)
    DOW=$(date +%u)
    if [ "$DAY" -le 7 ] && [ "$DOW" -le 5 ]; then
      echo "is_first_weekday=true" >> "$GITHUB_OUTPUT"
    else
      echo "is_first_weekday=false" >> "$GITHUB_OUTPUT"
    fi

- name: Commit monthly snapshot
  if: steps.check-date.outputs.is_first_weekday == 'true'
  run: |
    SNAP_DATE=$(date +%Y-%m-%d)
    cp docs/data/results.json "docs/data/snapshots/${SNAP_DATE}.json"
    # index.json updated by Python screener (or inline here per RESEARCH.md)
    git add "docs/data/snapshots/${SNAP_DATE}.json" docs/data/snapshots/index.json \
            docs/data/stats.json
    if ! git diff --cached --quiet; then
      git commit -m "chore: monthly snapshot ${SNAP_DATE}"
      git push
    fi
```

Note: `git config` is already set by the earlier step — do not repeat it.

---

### `.gitignore` — new exceptions

**Analog:** existing `!docs/data/results.json` exception (line 5)

**Current state** (lines 1–5):
```
.env
*.json
!.planning/*.json
!docs/data/results.json
```

**Phase 7 additions** — three new exception lines immediately after the existing exception:
```
!docs/data/results.json
!docs/data/stats.json
!docs/data/snapshots/*.json
!docs/data/snapshots/index.json
```

---

## Shared Patterns

### Piecewise scoring (apply to all new sub-score functions)
**Source:** `stock_screener.py` lines 297–317 (`_piecewise_score`) + lines 320–322 (`_winsorize`) + lines 325–331 (`_avg_present`)
```python
def _piecewise_score(value: float, bands: list) -> float:
    for (raw_lo, raw_hi, score_lo, score_hi) in bands:
        if value <= raw_hi:
            if raw_hi == raw_lo:
                return float(score_lo)
            t = (value - raw_lo) / (raw_hi - raw_lo)
            t = max(0.0, min(1.0, t))
            return score_lo + t * (score_hi - score_lo)
    return float(bands[-1][3])

def _winsorize(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))

def _avg_present(values: list) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None
```
**Apply to:** `_compute_piotroski()` sub-score mapping, `_compute_altman_z()` sub-score mapping, `_compute_dcf_forward()` discount sub-score (if scored), Safety pillar in `overall_score()`.

### D-01 negative-routing (apply to all new scored inputs)
**Source:** `stock_screener.py` lines 505–511 (debt_equity negative-equity path):
```python
def _score_debt_equity(de: float | None) -> float | None:
    if de is None:
        return None
    if de < 0:
        return 0.0   # D-01: present but worst-possible → 0, not winsorized
    return _piecewise_score(_winsorize(de, 0.0, SCORE_DE_WIN_HI), SCORE_DE_BANDS)
```
**Apply to:** `dcf_discount_pct` scoring (negative discount = stock is overpriced → 0.0 before scoring).

### None-guard early-return (apply to all `_compute_*` helpers)
**Source:** `stock_screener.py` line 884–889:
```python
if ocf is None:
    return None
fcf = ocf + capex if capex is not None else ocf
if not market_cap:
    return None
```
**Apply to:** Every new `_compute_*` helper. Required inputs checked first; optional inputs get `if x is not None else 0` fallback.

### `_safe_float()` for yfinance values
**Source:** `stock_screener.py` (used throughout `get_yf_price_and_history()`). Any value read from a yfinance DataFrame cell must go through `_safe_float()` to handle NaN and None uniformly. Used in `_yf_row()` line 815 and shares_now/shares_prev lines 1044–1045.

### Log warning on yfinance failure
**Source:** `stock_screener.py` lines 1048–1050:
```python
    except Exception as e:
        log.warning(f"yfinance error for {ticker}: {e}")
    return result
```
**Apply to:** All new yfinance statement reads inside `get_yf_price_and_history()`.

### Test env-var setup (apply to all new test files)
**Source:** `tests/test_factors_phase6.py` lines 20–25:
```python
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("FINNHUB_API_KEY", "test")

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
```
**Apply to:** `test_distress_phase7.py`, `test_dcf_phase7.py` — must appear before any `from stock_screener import` line.

---

## No Analog Found

All files have close analogs. No files without a codebase match.

| File | Note |
|------|------|
| `scipy.optimize.brentq` usage | No existing analog for a bounded solver — use RESEARCH.md code example directly (lines 517–525 of RESEARCH.md). The surrounding `_compute_dcf_reverse()` structure follows the `_compute_*` helper pattern. |

---

## Metadata

**Analog search scope:** `stock_screener.py` (full), `docs/app.js`, `docs/top.html`, `.github/workflows/screener.yml`, `.gitignore`, `tests/test_factors_phase6.py`, `tests/test_scoring_phase6.py`
**Files scanned:** 7
**Pattern extraction date:** 2026-06-28
