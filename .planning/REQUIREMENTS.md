# Requirements — Lynch & Graham Screener: GitHub Pages Migration

## v1 Requirements

### Security

- [ ] **SEC-01**: Hardcoded Finnhub API key in `diagnose_finnhub.py` is replaced with `os.environ["FINNHUB_API_KEY"]`
- [ ] **SEC-02**: Git history is audited and clean before repo is made public (no credential in history)

### Python Output Changes

- [ ] **PY-01**: `stock_screener.py` writes results to `docs/data/results.json` instead of Google Sheets
- [ ] **PY-02**: `results.json` includes a `generated_at` ISO timestamp field alongside the rows array
- [ ] **PY-03**: JSON write is aborted and the script exits non-zero if fewer than 100 rows were produced (guards against silent empty-file commits from mass data failure)
- [ ] **PY-04**: JSON output uses compact encoding (`separators=(',', ':')`) to minimize file size

### GitHub Actions Pipeline

- [ ] **CI-01**: `screener.yml` has `permissions: contents: write` declared at job or workflow level
- [ ] **CI-02**: `screener.yml` configures git identity (`github-actions[bot]` name and canonical noreply email) before committing
- [ ] **CI-03**: `screener.yml` commits only `docs/data/results.json` (not `git add -A`)
- [ ] **CI-04**: `screener.yml` uses a conditional commit pattern that skips the commit if data is unchanged (prevents empty commits on holidays)
- [ ] **CI-05**: `docs/.nojekyll` file exists in the repo (prevents GitHub Pages from running Jekyll)
- [ ] **CI-06**: `.gitignore` has `!docs/data/results.json` exception so the data file can be committed

### Frontend — Core Table

- [ ] **FE-01**: `docs/index.html` loads Tabulator 6.x from jsDelivr CDN (no local npm, no build step)
- [ ] **FE-02**: Table displays all screener output columns, sorted by `Score` descending on initial load
- [ ] **FE-03**: Ticker column is frozen (stays visible when scrolling horizontally)
- [ ] **FE-04**: Header row is sticky (stays visible when scrolling vertically)
- [ ] **FE-05**: Signal columns (Lynch_Status, Graham_Status, Defensive, Lynch_PEG_Band, Status_Combined) have traffic-light background colors (green/yellow/red) matching the existing `SIGNAL_COLORS` mapping
- [ ] **FE-06**: Null/missing values display as `—` (em dash) rather than `NaN`, `None`, or blank
- [x] **FE-07**: Error rows (tickers that failed data fetching) are hidden by default (no toggle — permanently hidden by design)
- [ ] **FE-08**: Page shows a "Data as of [date]" freshness badge derived from `generated_at`
- [ ] **FE-09**: A yellow stale-data warning banner appears if data is more than 3 calendar days old
- [ ] **FE-10**: `results.json` is fetched with a cache-busting query parameter (`?v=${Date.now()}`) to bypass CDN caching

### Frontend — Filters & Column Presets

- [ ] **FE-11**: "Buy Signals Only" toggle pill above the table — when active, shows only rows where `Status_Combined` is `True`
- [ ] **FE-12**: Every column has a header filter appropriate to its data type: dropdown select for categorical columns (status, category, index membership), numeric input for numeric columns (score, price, PE, discount %, etc.)
- [ ] **FE-13**: "Summary" / "Full" column preset toggle — Summary shows ~10 key signal columns, Full shows all columns
- [ ] **FE-14**: Ticker text search box for quick symbol lookup (client-side, instant filter)

### Documentation Page

- [x] **DOC-01**: `docs/methodology.html` presents the Lynch and Graham methodology documentation (ported from `DOCS_CONTENT` in `stock_screener.py`)
- [x] **DOC-02**: A two-item navigation header links between Dashboard (`index.html`) and Methodology (`methodology.html`)

### Cleanup (deferred until dashboard verified end-to-end)

- [ ] **CLN-01**: `push_to_gsheets()` and all its private helpers (`_apply_color_coding`, `_write_docs_tab`, `_write_markdown_tab`) are removed from `stock_screener.py`
- [ ] **CLN-02**: `gspread` and `google-auth` are removed from `requirements.txt`
- [ ] **CLN-03**: `GSHEET_CREDS_JSON`, `GSHEET_SPREADSHEET`, `GSHEET_WORKSHEET` env vars are removed from `screener.yml` and documentation
- [ ] **CLN-04**: Dead Tiingo config (`TIINGO_API_KEYS`, `TIINGO_DELAY_SEC`, related comments) is removed from `stock_screener.py`

---

## v2 Requirements (Deferred)

- Advanced numeric range filters (min/max sliders per column)
- Historical results archive — store one `results.json` snapshot per month, rolling 5-year window; display on a separate archive page or via a date picker on the dashboard
- Column header auto-sizing — column widths should dynamically fit the header label text so no headers are clipped on initial load
- Dark mode toggle
- Column visibility picker (beyond Summary/Full preset)
- Mobile-optimized layout (horizontal scroll is acceptable for v1)
- Methodology sourcing — add citations to original Lynch/Graham writings and interviews for each criterion (e.g. One Up on Wall Street for Lynch PEG thresholds, The Intelligent Investor chapters for Graham formulas)

---

## Out of Scope

- Real-time or intraday data — requires a backend; daily schedule is sufficient
- User accounts or server-side watchlists — no server; static constraint
- Stock detail pages or drill-down views — screener output is the product
- Charts or trend graphs — no historical data produced
- CSV/Excel export — `results.json` is publicly fetchable for power users
- A backend server, API, or database — fully static by design

---

## Traceability

| REQ-ID | Phase | Status | Notes |
|--------|-------|--------|-------|
| SEC-01 | Phase 1 | Pending | Safe to publish — fix before repo goes public |
| SEC-02 | Phase 1 | Pending | Safe to publish — audit before repo goes public |
| CI-01 | Phase 1 | Pending | Actions permissions prerequisite |
| CI-02 | Phase 1 | Pending | Actions git identity prerequisite |
| CI-03 | Phase 1 | Pending | Actions targeted commit prerequisite |
| CI-04 | Phase 1 | Pending | Actions conditional commit prerequisite |
| CI-05 | Phase 1 | Pending | .nojekyll prerequisite |
| CI-06 | Phase 1 | Pending | .gitignore exception prerequisite |
| PY-01 | Phase 2 | Pending | Core JSON writer |
| PY-02 | Phase 2 | Pending | generated_at timestamp |
| PY-03 | Phase 2 | Pending | Minimum-row guard |
| PY-04 | Phase 2 | Pending | Compact encoding |
| FE-01 | Phase 3 | Pending | Tabulator CDN load |
| FE-02 | Phase 3 | Pending | All columns, Score sort |
| FE-03 | Phase 3 | Pending | Frozen Ticker column |
| FE-04 | Phase 3 | Pending | Sticky header |
| FE-05 | Phase 3 | Pending | Traffic-light color coding |
| FE-06 | Phase 3 | Pending | Null display as em dash |
| FE-07 | Phase 3 | Complete | Error rows hidden by default (no toggle by design) |
| FE-08 | Phase 3 | Pending | Data freshness badge |
| FE-09 | Phase 3 | Pending | Stale-data warning banner |
| FE-10 | Phase 3 | Pending | Cache-busting fetch |
| FE-11 | Phase 3 | Pending | Buy Signals Only toggle |
| FE-12 | Phase 3 | Pending | Per-column header filters |
| FE-13 | Phase 3 | Pending | Summary/Full column preset |
| FE-14 | Phase 3 | Pending | Ticker text search |
| FE-15 | — | Removed | Top 20 panel — descoped before execution |
| FE-16 | — | Removed | Top 20 localStorage — descoped before execution |
| FE-17 | — | Removed | Top 20 click-to-scroll — descoped before execution |
| DOC-01 | Phase 3 | Complete | methodology.html |
| DOC-02 | Phase 3 | Complete | Two-item nav header |
| CLN-01 | Phase 4 | Pending | Remove push_to_gsheets — only after Phase 3 verified |
| CLN-02 | Phase 4 | Pending | Remove gspread/google-auth |
| CLN-03 | Phase 4 | Pending | Remove GSHEET_* env vars |
| CLN-04 | Phase 4 | Pending | Remove dead Tiingo config |
