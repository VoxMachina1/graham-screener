---
phase: 03-interactive-dashboard
reviewed: 2026-05-30T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - docs/index.html
  - docs/methodology.html
  - docs/style.css
  - stock_screener.py
findings:
  critical: 5
  warning: 4
  info: 3
  total: 12
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-05-30
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Four source files were reviewed: two HTML pages (dashboard and methodology), one shared CSS file, and the Python screener. The HTML and CSS are structurally sound and implement the Nord theme correctly. However, there are four blockers — two in the JavaScript filter logic that break the table's error-row hiding on every ticker search, and two in the Python screener involving unit mismatches that corrupt the PEGY/Lynch calculations and the Finnhub growth CAGR path. Three additional warnings cover a misnamed `.push_to_gsheets` call comment, an off-by-one in the progress logger, and missing Subresource Integrity on the CDN resources.

---

## Critical Issues

### CR-01: `table.setFilter` overwrites `noErrorFilter`, exposing error rows on ticker search

**File:** `docs/index.html:340`

**Issue:** `table.setFilter("Ticker", "like", val)` replaces the entire Tabulator filter array. The `noErrorFilter` function-based filter installed at line 286 is silently discarded the first time a user types in the ticker search box. After that, error rows (tickers with `Error` set) are visible again, directly contradicting requirement FE-07. The filter is gone for the rest of the session even if the search box is cleared.

**Fix:** Use `table.addFilter` instead of `table.setFilter` for the ticker search, so it stacks on top of the existing `noErrorFilter`:

```javascript
// line 340 — replace setFilter with addFilter
if (val) {
  table.addFilter("Ticker", "like", val);
} else {
  table.removeFilter("Ticker", "like", val);   // see CR-02
}
```

---

### CR-02: `removeFilter` called with wrong value argument — ticker filter never clears

**File:** `docs/index.html:342`

**Issue:** When the ticker search is cleared, `table.removeFilter("Ticker", "like", "")` is called with an empty string as the third argument. Tabulator's `removeFilter` matches by all three arguments (field, type, value). The filter was added with a non-empty `val` (e.g., `"AAPL"`), so `removeFilter` with `""` does not match it — the ticker filter is never removed. The table stays permanently filtered to the last searched value.

**Fix:** Remove using the same `val` that was passed to `addFilter`, or use `table.removeFilter("Ticker")` (field-only removal, supported in Tabulator 6):

```javascript
searchInput.addEventListener("input", function() {
  clearTimeout(searchTimeout);
  var val = this.value.trim().toUpperCase();
  searchTimeout = setTimeout(function() {
    table.removeFilter("Ticker", "like", val);   // remove the previous filter
    if (val) {
      table.addFilter("Ticker", "like", val);
    }
  }, 120);
});
```

Note: this also requires capturing the previous `val` in a closure variable to call `removeFilter` correctly on the next keystroke. The simplest correct approach is `table.removeFilter("Ticker")` which removes all filters on the Ticker field regardless of value.

---

### CR-03: Dividend yield passed to `lynch_metrics` as dollars-per-share, not percentage

**File:** `stock_screener.py:585-616`

**Issue:** `lynch_metrics(price, eps, g, dy)` at line 358 documents that `dy` must be a "whole-number percentage (e.g. 15.0 for 15%)." However, `dy` is set at line 585 directly from `fund["ttm_dps"]`, which is `dividendPerShareAnnual` from Finnhub — a dollar amount per share (e.g., Apple: ~$1.00, not 1% yield). The function receives dollars-per-share but treats it as a percentage.

Consequence: for a $150 stock paying $1.50/year, `dy` should be 1.0 (percent) but is passed as 1.5 (dollars). The PEGY formula `pe / (g + dy)` and the G+D fair value `eps * (g + dy)` are both distorted. For high-priced stocks with small dividends the error is small but non-zero; for low-priced high-yield stocks the PEGY and FV_GplusD values will be materially wrong.

**Fix:** Convert DPS to yield percentage before passing to `lynch_metrics`:

```python
# line 585 — convert DPS to yield %
dy_raw = fund["ttm_dps"] or 0.0
dy = round((float(dy_raw) / float(price)) * 100, 4) if price else 0.0
row["DivYield_Pct"] = round(dy, 2)
```

---

### CR-04: Finnhub `epsGrowth5Y` is a decimal (e.g. 0.15) but used as whole-number percent (15.0)

**File:** `stock_screener.py:295, 597-599`

**Issue:** Finnhub's `/stock/metric` endpoint returns `epsGrowth5Y` and `epsGrowth3Y` as decimal fractions (0.15 = 15% growth). The fallback `compute_growth_5yr_cagr()` at line 351 correctly returns whole-number percents (multiplies by 100). As a result, `g` is on different scales depending on the data path:

- Finnhub primary path: `g = 0.15` (decimal) → passed to `lynch_metrics` as 15% but actually used in formulas as if it were 0.15%
- yfinance fallback path: `g = 15.0` (whole number) → correct

The floor at line 599 (`if g <= 0: g = 1.0`) will never trigger for the Finnhub path since even a 1% growth rate arrives as `0.01`, not `1.0`. The `GROWTH_CAP = 25.0` also fails to cap Finnhub values since `0.15 < 25.0`.

All Lynch and Graham metrics are wrong by a factor of ~100 when the Finnhub path is used: a stock with 15% growth has `g = 0.15` fed into `eps * g` formulas, producing a fair value 100x too low.

**Fix:** Normalize the Finnhub growth value to whole-number percent immediately after retrieval:

```python
# line 295 — multiply by 100 to convert decimal fraction to whole-number %
growth_pct = _safe_float(fh.get("epsGrowth5Y") or fh.get("epsGrowth3Y"))
if growth_pct is not None:
    growth_pct = growth_pct * 100  # Finnhub returns 0.15, we need 15.0
```

---

### CR-05: BRK-B uses BRK-A price but BRK-A-equivalent EPS — fair values overstated by ~1,500×

**File:** `stock_screener.py` (data fetch / ticker normalization path)

**Issue:** Berkshire Hathaway Class B (BRK-B) shares trade at roughly 1/1,500th the price of Class A (BRK-A). yfinance (and some Finnhub endpoints) report EPS for BRK-B in Class A equivalents — the same large per-share value (~$60,000+) as BRK-A — while returning the correct Class B price (~$470). When `lynch_metrics` and `graham_metrics` receive a Class A EPS paired with a Class B price, every fair value and ratio is off by the A/B conversion factor (~1,500×).

**Observed:** BRK-B shows a fair value roughly 1,000–1,500× larger than its actual price, while appearing to fetch the correct (lower) Class B price.

**Root cause candidates (in priority order):**
1. yfinance `info["trailingEps"]` for `BRK-B` returns the Class A per-share figure rather than the adjusted Class B figure
2. Finnhub `basicEps` for `BRK-B` returns the Class A equivalent
3. The screener normalizes `BRK-B` → `BRK-A` for one API call but not the other

**Fix:** After fetching EPS, detect the A/B mismatch by checking whether `price / eps` produces an implausible P/E (e.g. P/E < 0.01 or > 10,000) and flag the row with an Error. Alternatively, add an explicit BRK-B conversion constant:
```python
BRK_CLASS_RATIO = 1500  # BRK-A EPS ÷ BRK-B shares outstanding adjustment
if ticker == "BRK-B" and eps is not None:
    eps = eps / BRK_CLASS_RATIO
```
The ratio should be confirmed against the current conversion factor (historically ~1,500:1, set when BRK-B was created in 1996).

---

## Warnings

### WR-01: `main()` comment says "Push to Google Sheets" but calls `write_json`

**File:** `stock_screener.py:1231-1232`

**Issue:** The comment on line 1231 reads `# 4. Push to Google Sheets` but the code calls `write_json(results_df)`. `push_to_gsheets` is never called from `main()`. This is a misleading leftover comment from Phase 1/2 migration that will confuse anyone reading the main flow.

**Fix:**
```python
# 4. Write JSON output
write_json(results_df)
```

---

### WR-02: Progress counter is wrong when `universe` DataFrame has non-zero-based index

**File:** `stock_screener.py:654-656`

**Issue:** `run_screener` uses `i` from `universe.iterrows()` as the progress counter: `[{i+1}/{total}]`. `iterrows()` yields the DataFrame's actual index values, not a sequential 0..N counter. `get_universe()` builds the DataFrame with `pd.DataFrame(rows)` which does produce a 0-based index, so this is usually fine. However, if the DataFrame is ever filtered or re-indexed upstream (e.g., to skip a subset of tickers), `i` will jump or repeat, producing log lines like `[25/516]` followed by `[50/516]`, skipping numbers and confusing progress tracking.

**Fix:** Use `enumerate` for a reliable counter:
```python
for i, (_, row) in enumerate(universe.iterrows()):
    log.info(f"[{i+1}/{total}] Processing {row['ticker']}...")
```

---

### WR-03: No Subresource Integrity (SRI) on CDN resources

**File:** `docs/index.html:14, 70`

**Issue:** The Tabulator CSS and JS are loaded from jsDelivr CDN without `integrity` attributes:

```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/.../tabulator_midnight.min.css">
<script src="https://cdn.jsdelivr.net/.../tabulator.min.js"></script>
```

If the CDN is compromised or the URL is hijacked, malicious code would execute in users' browsers. This is a static GitHub Pages site with no CSP header support (GitHub Pages does not allow custom response headers without a proxy), but SRI is still a meaningful defence against CDN compromise.

**Fix:** Add `integrity` and `crossorigin` attributes. Compute the SHA-384 hash for each resource:

```html
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/tabulator-tables@6.4.0/dist/css/tabulator_midnight.min.css"
      integrity="sha384-<hash>"
      crossorigin="anonymous">

<script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6.4.0/dist/js/tabulator.min.js"
        integrity="sha384-<hash>"
        crossorigin="anonymous"></script>
```

Use `https://www.srihash.org/` or `openssl dgst -sha384 -binary <file> | openssl base64 -A` to generate the hash.

---

### WR-04: `buildColumns()` called twice, constructing duplicate column definitions

**File:** `docs/index.html:273, 281`

**Issue:** `buildColumns()` is called once at line 273 to extract `allFields`, and again at line 281 as the `columns` argument to `Tabulator`. The function builds the full column definition array including formatter closures each time. This is harmless in practice but creates unnecessary object allocation and makes the code fragile — if `buildColumns()` had side effects or the column list diverged between calls, the `allFields` array would not match the actual table columns.

**Fix:** Call `buildColumns()` once and reuse the result:

```javascript
const cols = buildColumns();
const allFields = cols.map(function(c) { return c.field; });

var table = new Tabulator("#data-table", {
  data: data.rows,
  layout: "fitData",
  height: "calc(100vh - 140px)",
  renderVertical: "virtual",
  initialSort: [{ column: "CombinedScore", dir: "desc" }],
  columns: cols,
});
```

---

## Info

### IN-01: `Error` column is `visible: true` — error messages visible in default Summary view

**File:** `docs/index.html:216-221`

**Issue:** The `Error` column definition sets `visible: true`. In Summary preset mode, `applyPreset` calls `table.showColumn(field)` or `table.hideColumn(field)` based on `SUMMARY_COLS`. Since `"Error"` is not in `SUMMARY_COLS`, `applyPreset` hides it on load — but only after `tableBuilt` fires. During the brief window between table render and `tableBuilt`, the Error column will flash visible. More importantly, the intent of the `Error` column (utility column, programmatic use only, per the comment) suggests it should default to `visible: false` like the `Show` column above it.

**Fix:** Set `visible: false` on the Error column definition to match its stated purpose:

```javascript
{ title: "Error", field: "Error", visible: false, headerFilter: false, ... }
```

---

### IN-02: Google Fonts loaded on methodology page but `JetBrains Mono` import is in `style.css`

**File:** `docs/methodology.html:7`, `docs/style.css:1`

**Issue:** `methodology.html` loads `style.css` which contains `@import url('https://fonts.googleapis.com/...')` for JetBrains Mono. The methodology page has no data table, so the monospace font is only used for inline `<code>` elements (and the `[role="tabpanel"] code` CSS rule). This is not a bug but a minor inefficiency — the font is loaded even though no data cells appear on that page. The `@import` inside a CSS file also blocks CSS parsing until the font request completes, slightly delaying the page render.

**Fix (optional):** Move the Google Fonts `<link>` preload tags to `index.html` only, and replace the CSS `@import` with a direct `<link rel="stylesheet">` tag on pages that need the font. No change required if the performance impact is acceptable.

---

### IN-03: `push_to_gsheets` function is dead code in the current main flow

**File:** `stock_screener.py:1073`

**Issue:** `push_to_gsheets` (line 1073) along with the `_apply_color_coding`, `_write_markdown_tab`, and `_write_docs_tab` helper functions are never called from `main()`. They remain as legacy Google Sheets infrastructure that Phase 4 (CLN) is intended to remove. The CLAUDE.md note confirms this is intentional ("CLN phase is always last"). This is informational — no action needed until Phase 4.

**Fix:** No action needed now. Flag for removal in Phase 4 (CLN).

---

_Reviewed: 2026-05-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
