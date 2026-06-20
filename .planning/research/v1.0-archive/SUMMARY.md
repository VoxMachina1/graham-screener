# Research Summary: GitHub Pages Stock Screener Dashboard

## Executive Summary

This project is a well-scoped output layer swap: replace `push_to_gsheets()` with a JSON writer + static web frontend. The Python pipeline is mature and working; the migration touches only the output path and CI commit step. No architectural ambiguity exists — the pattern is well-documented with HIGH confidence across every research area.

The primary risks are not architectural but operational: a hardcoded API key in `diagnose_finnhub.py` that must be removed before the repo goes public, a `.gitignore` that currently blocks all `*.json`, and the absence of a minimum-row guard that could allow a failed run to overwrite good data with an empty file. Fix these three things before any other work proceeds.

---

## Recommended Stack

| Technology | Purpose |
|---|---|
| HTML5 + Vanilla JS (ES2020+) | Dashboard UI — no framework, no build step |
| Tabulator 6.2+ (pinned) | Sortable/filterable table, built-in formatters, frozen columns, CDN-native |
| jsDelivr CDN | Delivers Tabulator CSS + JS — free, MIT |
| GitHub Pages (`docs/` on `main`) | Static hosting, auto-deploys on push |
| GitHub Actions (existing `screener.yml`) | Commits `docs/data/results.json` after each weekday run |

**File layout:**
```
docs/
  index.html          — dashboard (CSS + JS inline at MVP scale)
  methodology.html    — separate page for Lynch/Graham documentation
  .nojekyll           — disables Jekyll processing
  data/
    results.json      — committed by Actions after each run
```

**What NOT to use:** React/Vue/Svelte (build step, zero benefit), DataTables (requires jQuery), AG Grid (3–5× larger bundle), Handsontable (license ambiguity).

---

## Pipeline: How Actions → JSON → Pages Works

```
Actions (schedule: weekdays 6am ET)
  → python stock_screener.py     (writes docs/data/results.json)
  → git config user.name/email   (github-actions[bot])
  → git add docs/data/results.json
  → git diff --staged --quiet || git commit + git push
  → Pages detects push → rebuilds in 30–90s → CDN propagates in 2–15 min
  → index.html fetches ./data/results.json?v=${Date.now()} at page load
  → Tabulator renders table client-side
```

Key requirements:
- `permissions: contents: write` at job level — GitHub defaults to read-only
- `git config user.name/email` using `github-actions[bot]` canonical identity
- `git diff --staged --quiet || git commit` prevents failure on holidays/unchanged data
- `git add docs/data/results.json` only — never `git add -A`
- Cache-bust fetch: `fetch('./data/results.json?v=${Date.now()}')`
- Embed `generated_at` timestamp in JSON for staleness detection

---

## Key UX Decisions

**Table:** Sort by `Score` descending on load. Freeze Ticker column. Sticky header. Compact row density. Right-align numeric columns. Nulls display as `—`. Error rows dimmed/hidden by default.

**"Buy Signals Only" toggle:** Prominent pill button above the table, defaults OFF. Most common user action — not buried in a dropdown.

**Top 20 panel:** Collapsible inline section above the main table. Open by default, state persisted in `localStorage`. Clicking a ticker jumps to that row.

**Methodology:** Separate `methodology.html` — `DOCS_CONTENT` is ~140 lines, too long for a modal. Two-item nav header: [Dashboard] [Methodology].

**Stale data banner:** "Data as of [date]" badge. Yellow warning if data > 3 calendar days old. "Updated each weekday at ~6am ET" subtitle.

**Column presets:** "Summary view" (10 key columns, default) and "Full data" (all columns). No custom column picker at MVP.

---

## Critical Pitfalls — Fix Before Anything Else

| # | Pitfall | Severity | Fix |
|---|---|---|---|
| 1 | Hardcoded API key in `diagnose_finnhub.py` | CRITICAL | Replace with `os.environ["FINNHUB_API_KEY"]`. Audit git history before making repo public. |
| 2 | `*.json` in `.gitignore` blocks `results.json` | CRITICAL | Add `!docs/data/results.json` after the `*.json` rule — order matters |
| 3 | `permissions: contents: write` missing from `screener.yml` | CRITICAL | Add `permissions:` block — current default is read-only |
| 4 | No minimum-row guard on JSON write | HIGH | Abort write if row count < 100 — prevents silent empty-file commits |
| 5 | No git identity in Actions runner | HIGH | `git config user.name "github-actions[bot]"` before every commit step |
| 6 | Browser caches `results.json` for ~10 min | HIGH | Append `?v=${Date.now()}` to the fetch URL |

---

## What NOT to Build

| Anti-feature | Reason |
|---|---|
| Real-time / live price updates | Requires backend; breaks static constraint |
| Historical charts or trend data | No historical data produced; out of scope |
| User accounts or server-side watchlists | No server; hard constraint |
| Pagination | 550 rows renders fine; pagination adds friction |
| Per-column range sliders | Signal dropdowns cover 90% of use cases |
| CSV/Excel export | `results.json` is publicly fetchable |
| Dark mode toggle | Not MVP scope |
| React/Vue/Svelte | No build-step benefit for this use case |

---

## Suggested Phase Structure

1. **Security + pipeline prerequisites** — Fix hardcoded key, `.gitignore`, `permissions`, row guard, `.nojekyll`, Pages config
2. **JSON output from Python** — `write_json(df)` with `generated_at`, wire into `screener.yml`, verify with `workflow_dispatch`
3. **Minimal viable dashboard** — Tabulator table, traffic-light color coding, sticky header, frozen Ticker, Buy toggle, staleness banner
4. **Top 20 panel + Methodology page** — Collapsible Top 20, `methodology.html`, header nav
5. **Filters and column presets** — Signal dropdowns, Category pills, Index checkboxes, Summary/Full presets
6. **Google removal** — Remove `push_to_gsheets()`, gspread, google-auth, GSHEET_* secrets, dead Tiingo config

---

## Confidence

| Area | Confidence |
|---|---|
| Stack (Tabulator, vanilla JS, CDN) | HIGH |
| Pipeline (Actions → commit → Pages) | HIGH |
| UX decisions | HIGH |
| Pitfalls (based on direct code inspection) | HIGH |
| Full Tabulator column definitions | MEDIUM — need `process_ticker()` return shape |
