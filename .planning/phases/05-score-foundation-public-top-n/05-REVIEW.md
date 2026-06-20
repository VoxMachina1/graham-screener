---
phase: 05-score-foundation-public-top-n
reviewed: 2026-06-19T20:45:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - stock_screener.py
  - diagnose_finnhub.py
  - tests/test_valuation_fixture.py
  - tests/test_scoring.py
  - docs/app.js
  - docs/top.html
  - docs/index.html
  - docs/methodology.html
  - docs/style.css
findings:
  critical: 1
  warning: 5
  info: 4
  total: 10
status: issues_found
fixed: critical_warning
fixed_findings: [CR-01, WR-01, WR-02, WR-03, WR-04, WR-05]
---

# Phase 5: Code Review Report

**Reviewed:** 2026-06-19T20:45:00Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** issues_found

## Summary

Reviewed the Phase 5 scoring engine (`stock_screener.py`), its two offline test
suites, and the static GitHub Pages frontend (`app.js`, `index.html`,
`top.html`, `methodology.html`, `style.css`).

The scoring math is largely sound. The sentinel-routing (WORST_DISCOUNT),
winsorization, piecewise interpolation, pillar renormalization, and trap-gate
coverage arithmetic all trace through correctly against the unit tests, and I
respected the documented intentional designs (double-prefix keys, -999 sentinel,
unanchored tunable constants, vanilla-assert tests).

The headline issue is an **XSS / HTML-injection vector in the dashboard ticker
column** (`index.html`): ticker symbols sourced from scraped Wikipedia HTML are
concatenated into an `<a>` tag with no escaping. The sibling page `top.html`
*does* escape tickers, proving the team knows the data is untrusted — the
dashboard simply missed it. There is also a genuine scoring bug in the defensive
P/B check (negative EPS grants a spurious point) and a documentation statement in
`methodology.html` that describes behavior (negative-growth flooring) that was
explicitly removed this phase.

## Critical Issues

### CR-01: Unescaped ticker injected into dashboard HTML (XSS)

**Status:** Fixed (cb16390) — shared `escHtml` added to `app.js`; `index.html` formatter now escapes the value and `encodeURIComponent`s the href.

**File:** `docs/index.html:88`
**Issue:** The Tabulator "Ticker" column uses a custom formatter that builds raw
HTML by string concatenation, inserting the cell value directly into both an
`href` attribute and the link text with no escaping:

```js
formatter: function(cell) {
  var t = cell.getValue();
  return '<a href="https://finviz.com/quote.ashx?t=' + t + '" ... >' + t + '</a>';
}
```

Tabulator custom formatters that return a string render it as HTML, so any markup
in `t` is injected into the DOM. Ticker symbols originate from scraped Wikipedia
table HTML (`fetch_sp500`/`fetch_dow30`/`fetch_nasdaq100` in `stock_screener.py`)
— externally controlled data, not a fixed allowlist. A crafted/poisoned symbol
(e.g. `"><img src=x onerror=...>`) would execute. The team already treats this
data as untrusted in `top.html:112` (`escHtml(String(r.Ticker || ""))`); the
dashboard was simply missed.

**Fix:** Escape (and ideally URL-encode for the href) before concatenating, or
return a DOM node. Reuse an escape helper:

```js
formatter: function(cell) {
  var t = String(cell.getValue() == null ? "" : cell.getValue());
  var safe = t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  var href = "https://finviz.com/quote.ashx?t=" + encodeURIComponent(t);
  return '<a href="' + href + '" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline;">' + safe + '</a>';
}
```

## Warnings

### WR-01: `escHtml` does not escape double quotes, breaking the finviz href

**Status:** Fixed (c8c2d84) — shared `escHtml` now escapes `"` and `'`; `top.html` `encodeURIComponent`s the ticker in the finviz URL.

**File:** `docs/top.html:88-90`, used at `docs/top.html:113` and `118`
**Issue:** `escHtml` only replaces `&`, `<`, `>`. The escaped ticker is also
concatenated into an attribute context: `finvizHref = "...t=" + ticker` then
`'<a href="' + finvizHref + '"...>'`. A ticker containing a double quote would
break out of the `href` attribute (attribute-injection), and tickers are not
URL-encoded for the query string either. Same untrusted-source concern as CR-01.

**Fix:** Add `.replace(/"/g, "&quot;")` to `escHtml`, and `encodeURIComponent`
the ticker used in the URL:

```js
function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
// ...
var finvizHref = "https://finviz.com/quote.ashx?t=" + encodeURIComponent(ticker);
```

### WR-02: Defensive P/B check grants a spurious point on negative EPS

**Status:** Fixed (838bb68) — P/E×P/B branch now requires `cur_eps > 0`.

**File:** `stock_screener.py:921-923`
**Issue:** In `graham_defensive_score`, criterion 8 computes
`pe_cur = price / (valid_eps[-1] if valid_eps else 1)`. When the most recent
valid EPS is negative, `pe_cur` is negative, so the test
`(pe_cur * pb) <= MAX_PE_X_PB` (a negative number ≤ 22.5) is trivially True and
the stock is awarded the P/B point it should not earn. A loss-making company
with a high P/B can thus inflate its DefensiveScore. (This also conceptually
mismatches criterion 7, which correctly guards `eps_3yr_avg > 0`.)

**Fix:** Require positive current EPS before using the P/E×P/B branch:

```js
if pb and pb > 0:
    cur_eps = valid_eps[-1] if valid_eps else None
    pe_ok = cur_eps is not None and cur_eps > 0 and (price / cur_eps) * pb <= MAX_PE_X_PB
    checks["PB_Limit"] = int(pb <= MAX_PB_GRAHAM or pe_ok)
else:
    checks["PB_Limit"] = 0
```

### WR-03: methodology.html documents removed negative-growth flooring

**Status:** Fixed (76bd6b9) — replaced the flooring sentence with the WORST_DISCOUNT retention description.

**File:** `docs/methodology.html:308-313`
**Issue:** The Data Sources panel states: *"If growth is negative it is floored
at 1% so a conservative valuation is still produced rather than skipping the
ticker."* This behavior no longer exists. Phase 5 removed the flooring constraint
(see project history "Removed Graham valuation flooring constraint" /
"Edge-case handling for negative/zero growth: retain stocks with worst-case
discount"). In the current code, negative/zero growth is passed through
(`g = min(g, GROWTH_CAP)`), `lynch_metrics`/`graham_metrics` return an error for
`g <= 0`, and the row is routed to `WORST_DISCOUNT` (`stock_screener.py:996-999,
1018-1030`). The published methodology now misleads users about how
negative-growth stocks are valued and ranked.

**Fix:** Replace the sentence with a description of the WORST_DISCOUNT retention
behavior — e.g. "Stocks with negative or zero growth cannot be valued by these
formulas; they are retained but assigned the worst-possible value score so they
rank at the bottom rather than being dropped."

### WR-04: Truthiness fallback can misroute a legitimate zero from `_safe_float`

**Status:** Fixed (838bb68) — `ttm_eps is None` and `fh_mktcap is not None`. Line 982 left as-is: `dps` is coalesced to `0.0` (never `None`) and `> 0` already yields a correct 0% for zero dividends.

**File:** `stock_screener.py:648` (`if not ttm_eps`), `665` (`if fh_mktcap`), `982`
**Issue:** `_safe_float` returns `0.0` for a real zero. Several gates use truthy
checks (`if not ttm_eps and ...`, `if fh_mktcap:`, `float(dps) > 0`) that treat
`0.0` identically to `None`. For market cap this silently discards a real value
of 0 (edge), and the pattern is fragile: it conflates "absent" with "zero". EPS
zero is independently rejected downstream so no current crash, but the idiom
risks future bugs as more fields adopt it.

**Fix:** Prefer explicit `is None` checks where "present but zero" is meaningful,
e.g. `if ttm_eps is None and yf_data["annual_eps"]:` and
`if fh_mktcap is not None:`.

### WR-05: Frontend re-sort uses `|| 0`, collapsing 0 and null/NaN scores

**Status:** Fixed (c8c2d84) — null/undefined/NaN scores now coerce to `-Infinity` so they sort last.

**File:** `docs/top.html:181-183`
**Issue:** `allRows.sort(function(a,b){ return (b.OverallScore || 0) - (a.OverallScore || 0); })`
treats `null`/`undefined`/`NaN`/`0` OverallScore all as 0. A legitimate
worst-case score of exactly 0 (produced by the WORST_DISCOUNT path) and an
unknown/null score become indistinguishable in ordering, so an unscored row can
outrank or interleave with genuinely-zero-scored rows non-deterministically. The
Python side already sorts with `na_position="last"`; the JS re-sort can undo that
ordering intent for null scores.

**Fix:** Treat null/undefined as "sort last" explicitly rather than coercing to 0:

```js
.sort(function(a, b) {
  var av = (typeof a.OverallScore === "number" && !isNaN(a.OverallScore)) ? a.OverallScore : -Infinity;
  var bv = (typeof b.OverallScore === "number" && !isNaN(b.OverallScore)) ? b.OverallScore : -Infinity;
  return bv - av;
});
```

## Info

### IN-01: `datetime.utcnow()` is deprecated

**File:** `stock_screener.py:1158`
**Issue:** `datetime.utcnow()` is deprecated as of Python 3.12 and emits a
DeprecationWarning. The project targets Python 3.11 today, but this will warn/
break on upgrade.
**Fix:** `datetime.now(datetime.timezone.utc).strftime(...)` (import `timezone`).

### IN-02: `pb` parameter is unused in `graham_metrics`

**File:** `stock_screener.py:809-810`
**Issue:** `graham_metrics(..., pb: float | None)` accepts `pb` but never
references it in the body. Dead parameter — passed from `process_ticker:1026`.
**Fix:** Remove the parameter and the call-site argument, or use it if a P/B
adjustment was intended.

### IN-03: Frontend duplicates Python sort and signal-color logic

**File:** `docs/top.html:179-183`, `docs/app.js:14-42`
**Issue:** OverallScore sorting is performed both in `run_screener`
(`stock_screener.py:1122-1125`) and again in `top.html`/`index.html`. The
duplicated sort is a maintenance hazard (the two can diverge on tie-breaking and
null handling, see WR-05). Not a bug on its own, but worth noting for
consolidation.
**Fix:** Consider trusting the server-side ordering for the Top-N page, or
document why the client re-sort is required.

### IN-04: `diagnose_finnhub.py` duplicates fields in `fields_of_interest`

**File:** `diagnose_finnhub.py:48-59`
**Issue:** `epsGrowth5Y` and `dividendPerShareAnnual` (and conceptually
`epsAnnual`/`dividendsPerShareAnnual`) appear twice in the list, producing
duplicate diagnostic output lines. Harmless in a throwaway diagnostic script but
sloppy.
**Fix:** De-duplicate the list (use a set or remove the repeated entries).

---

_Reviewed: 2026-06-19T20:45:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
