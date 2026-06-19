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

- [x] **FE-01**: `docs/index.html` loads Tabulator 6.x from jsDelivr CDN (no local npm, no build step)
- [x] **FE-02**: Table displays all screener output columns, sorted by `Score` descending on initial load
- [x] **FE-03**: Ticker column is frozen (stays visible when scrolling horizontally)
- [x] **FE-04**: Header row is sticky (stays visible when scrolling vertically)
- [x] **FE-05**: Signal columns (Lynch_Status, Graham_Status, Defensive, Lynch_PEG_Band, Status_Combined) have traffic-light background colors (green/yellow/red) matching the existing `SIGNAL_COLORS` mapping
- [x] **FE-06**: Null/missing values display as `—` (em dash) rather than `NaN`, `None`, or blank
- [x] **FE-07**: Error rows (tickers that failed data fetching) are hidden by default (no toggle — permanently hidden by design)
- [x] **FE-08**: Page shows a "Data as of [date]" freshness badge derived from `generated_at`
- [x] **FE-09**: A yellow stale-data warning banner appears if data is more than 3 calendar days old
- [x] **FE-10**: `results.json` is fetched with a cache-busting query parameter (`?v=${Date.now()}`) to bypass CDN caching

### Frontend — Filters & Column Presets

- [x] **FE-11**: "Buy Signals Only" toggle pill above the table — when active, shows only rows where `Status_Combined` is `True`
- [x] **FE-12**: Every column has a header filter appropriate to its data type: dropdown select for categorical columns (status, category, index membership), numeric input for numeric columns (score, price, PE, discount %, etc.)
- [x] **FE-13**: "Summary" / "Full" column preset toggle — Summary shows ~10 key signal columns, Full shows all columns
- [x] **FE-14**: Ticker text search box for quick symbol lookup (client-side, instant filter)

### Documentation Page

- [x] **DOC-01**: `docs/methodology.html` presents the Lynch and Graham methodology documentation (ported from `DOCS_CONTENT` in `stock_screener.py`)
- [x] **DOC-02**: A two-item navigation header links between Dashboard (`index.html`) and Methodology (`methodology.html`)

### Cleanup (deferred until dashboard verified end-to-end)

- [ ] **CLN-01**: `push_to_gsheets()` and all its private helpers (`_apply_color_coding`, `_write_docs_tab`, `_write_markdown_tab`) are removed from `stock_screener.py`
- [ ] **CLN-02**: `gspread` and `google-auth` are removed from `requirements.txt`
- [ ] **CLN-03**: `GSHEET_CREDS_JSON`, `GSHEET_SPREADSHEET`, `GSHEET_WORKSHEET` env vars are removed from `screener.yml` and documentation
- [ ] **CLN-04**: Dead Tiingo config (`TIINGO_API_KEYS`, `TIINGO_DELAY_SEC`, related comments) is removed from `stock_screener.py`

---

## v2.0 Requirements — Methodology Expansion & Scoring

### Formula Correctness (prerequisite — must precede scoring)

- [x] **FIX-01**: The deferred "Buy Price visibly wrong" formula bug is diagnosed (root cause identified) and corrected across Lynch buy price and Graham fair value, with a spot-check fixture for at least one hand-verified ticker
- [x] **FIX-02**: The corrected discount fields (`Lynch_Discount_Pct`, `Graham_Discount_Pct`) are confirmed sane before any pillar consumes them

### Composite Scoring Engine

- [ ] **SCORE-01**: A scoring module computes a 4-pillar absolute `OverallScore` (0–100) from Value / Quality / Growth / Safety pillars
- [ ] **SCORE-02**: Each raw metric maps to a bounded sub-score via configurable **absolute thresholds** (piecewise-linear bands), not cross-sectional ranks
- [ ] **SCORE-03**: Raw inputs are winsorized/clamped (both tails) before pillar aggregation so one glitch cannot dominate
- [ ] **SCORE-04**: Missing metrics are handled by averaging over *present* metrics within a pillar, emitting a per-row coverage flag; a missing safety input is treated as "unknown," never "safe"
- [ ] **SCORE-05**: `OverallScore` decomposes into pillar sub-scores exposed in `results.json` (flat columns + a nested `scores` object) and in the UI
- [ ] **SCORE-06**: Pillar weights and all thresholds live as version-controlled config constants; yield-based thresholds are rate-relativized to the live FRED AAA yield
- [ ] **SCORE-07**: Correlated Value metrics are grouped so the Value pillar is not a single cheapness rank
- [ ] **SCORE-08**: `OverallScore` replaces `CombinedScore` as the primary sort key

### Value-Trap Gating

- [ ] **TRAP-01**: An interim value-trap gate is computed from existing signals (debt/equity, current ratio, EPS stability, negative FCF) so a cheap-but-dying stock is flagged before any public Top-N ships
- [ ] **TRAP-02**: A value-trap badge/flag is displayed on the Top-N page
- [ ] **TRAP-03**: Altman Z and Piotroski F replace/augment the interim gate as the Safety-pillar driver once available

### New Valuation Signals

- [ ] **SIGNAL-01**: Distance below the 52-week high and above the 52-week low (%)
- [ ] **SIGNAL-02**: Distance above the 5-year low (%)
- [ ] **SIGNAL-03**: Weeks-since-52-week-low and weeks-since-5-year-low recency
- [ ] **SIGNAL-04**: FCF yield (FCF / market cap)
- [ ] **SIGNAL-05**: EV/EBIT (Acquirer's Multiple) and earnings yield (EBIT/EV)
- [ ] **SIGNAL-06**: ROIC as an absolute Quality input (not the Greenblatt rank-sum)
- [ ] **SIGNAL-07**: Shareholder yield (dividend + net buyback), with a low-coverage flag where share-count data is sparse
- [ ] **SIGNAL-08**: Piotroski F-Score (0–9) from two years of financial statements
- [ ] **SIGNAL-09**: Altman Z-Score (Z'' variant) with distress zones, used as a penalty/veto

### Discounted Cash Flow

- [ ] **DCF-01**: Forward two-stage DCF intrinsic value and discount % per ticker
- [ ] **DCF-02**: Reverse DCF implied-growth vs actual-growth gap
- [ ] **DCF-03**: DCF is sector-guarded (financials excluded, cyclicals flagged), asserts terminal-growth < discount-rate, and the reverse solver is bounded and emits `None` on non-convergence (never a silent default)

### Sector Awareness

- [ ] **SECTOR-01**: GICS sector is fetched per ticker and threaded through the pipeline as a row field
- [ ] **SECTOR-02**: A per-metric sector applicability matrix governs which signals are valid per sector; invalid signals are treated as missing, never zero

### New Frontend Pages

- [ ] **PAGE-01**: `docs/top.html` Top 10/25 picks page (10/25 toggle), ranked by `OverallScore`, showing pillar sub-scores and headline signals
- [ ] **PAGE-02**: `docs/stats.html` universe overview — score distribution, buy-signal counts, sector breakdown, and data-coverage stats
- [ ] **PAGE-03**: A shared `docs/app.js` holds the fetch/format/color/freshness primitives reused across pages (no build step)
- [ ] **PAGE-04**: The site nav links Dashboard, Top Picks, Stats, and Methodology across all pages

### Historic Snapshots & Data

- [ ] **DATA-01**: Periodic (weekly/monthly) snapshots of `results.json` are committed under `docs/data/snapshots/`, with the required `!docs/data/snapshots/*.json` `.gitignore` exception
- [ ] **DATA-02**: The snapshot step reuses the min-row guard so no empty/partial snapshot is committed; a data-vintage caveat is documented
- [ ] **DATA-03**: (Optional) A 30-day fundamentals cache bounds runtime/rate-limit for the heavy Phase-C statement fetches

### Methodology Documentation

- [ ] **METH-01**: `methodology.html` is updated to document the new signals, the 4-pillar absolute scoring, the thresholds, and the sector guards

---

## Future Requirements (Deferred beyond v2.0)

- Advanced numeric range filters (min/max sliders per column)
- Backtest harness — validate the composite score against historic snapshots (locked decision: deferred, not a first/second-pass concern)
- Archive-browsing UI — a date picker or archive page to view past snapshots (the snapshots themselves are produced in v2.0 by DATA-01; browsing them is deferred)
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
| FE-01 | Phase 3 | Complete | Tabulator CDN load |
| FE-02 | Phase 3 | Complete | All columns, Score sort |
| FE-03 | Phase 3 | Complete | Frozen Ticker column |
| FE-04 | Phase 3 | Complete | Sticky header |
| FE-05 | Phase 3 | Complete | Traffic-light color coding |
| FE-06 | Phase 3 | Complete | Null display as em dash |
| FE-07 | Phase 3 | Complete | Error rows hidden by default (no toggle by design) |
| FE-08 | Phase 3 | Complete | Data freshness badge |
| FE-09 | Phase 3 | Complete | Stale-data warning banner |
| FE-10 | Phase 3 | Complete | Cache-busting fetch |
| FE-11 | Phase 3 | Complete | Buy Signals Only toggle |
| FE-12 | Phase 3 | Complete | Per-column header filters |
| FE-13 | Phase 3 | Complete | Summary/Full column preset |
| FE-14 | Phase 3 | Complete | Ticker text search |
| FE-15 | — | Removed | Top 20 panel — descoped before execution |
| FE-16 | — | Removed | Top 20 localStorage — descoped before execution |
| FE-17 | — | Removed | Top 20 click-to-scroll — descoped before execution |
| DOC-01 | Phase 3 | Complete | methodology.html |
| DOC-02 | Phase 3 | Complete | Two-item nav header |
| CLN-01 | Phase 4 | Pending | Remove push_to_gsheets — only after Phase 3 verified |
| CLN-02 | Phase 4 | Pending | Remove gspread/google-auth |
| CLN-03 | Phase 4 | Pending | Remove GSHEET_* env vars |
| CLN-04 | Phase 4 | Pending | Remove dead Tiingo config |
| FIX-01 | Phase 5 | Complete 2026-06-19 | Buy Price bug — root cause documented (VB conservative base PE=7); KO fixture passing |
| FIX-02 | Phase 5 | Complete 2026-06-19 | KO fixture confirms discounts sane; FIX-02 gate passed; Plan 02 may proceed |
| SCORE-01 | Phase 5 | Pending | 4-pillar absolute OverallScore (Value/Quality/Growth/Safety) |
| SCORE-02 | Phase 5 | Pending | Absolute-threshold piecewise-linear band mapping (not ranks) |
| SCORE-03 | Phase 5 | Pending | Winsorize/clamp both tails before pillar aggregation |
| SCORE-04 | Phase 5 | Pending | Average-over-present missing rule + coverage flag; missing safety = unknown |
| SCORE-05 | Phase 5 | Pending | Pillar decomposition in flat columns + nested scores object + UI |
| SCORE-06 | Phase 5 | Pending | Version-controlled weights/thresholds; yield thresholds rate-relativized to AAA |
| SCORE-07 | Phase 5 | Pending | Group correlated Value metrics (avoid glorified cheapness rank) |
| SCORE-08 | Phase 5 | Pending | OverallScore replaces CombinedScore as primary sort key |
| TRAP-01 | Phase 5 | Pending | Interim value-trap gate from existing signals before public Top-N ships |
| TRAP-02 | Phase 5 | Pending | Value-trap badge on Top-N page |
| PAGE-01 | Phase 5 | Pending | docs/top.html Top 10/25 picks page |
| PAGE-03 | Phase 5 | Pending | Shared docs/app.js fetch/format/color/freshness primitives |
| PAGE-04 | Phase 5 | Pending | Site nav: Dashboard, Top Picks, Stats, Methodology |
| SECTOR-01 | Phase 6 | Pending | GICS sector per ticker as row field — prereq for Phase 7 guards |
| SIGNAL-01 | Phase 6 | Pending | Distance below 52w high / above 52w low (%) |
| SIGNAL-02 | Phase 6 | Pending | Distance above 5-year low (%) |
| SIGNAL-03 | Phase 6 | Pending | Weeks-since-52w-low / weeks-since-5y-low recency |
| SIGNAL-04 | Phase 6 | Pending | FCF yield (FCF / market cap) |
| SIGNAL-05 | Phase 6 | Pending | EV/EBIT (Acquirer's Multiple) + earnings yield (EBIT/EV) |
| SIGNAL-06 | Phase 6 | Pending | ROIC as absolute Quality input (not Greenblatt rank-sum) |
| SIGNAL-07 | Phase 6 | Pending | Shareholder yield (dividend + net buyback) + low-coverage flag |
| SIGNAL-08 | Phase 7 | Pending | Piotroski F-Score (0–9) from 2yr statements |
| SIGNAL-09 | Phase 7 | Pending | Altman Z-Score (Z'' variant) distress zones — penalty/veto |
| TRAP-03 | Phase 7 | Pending | Altman Z + Piotroski upgrade interim gate as Safety driver |
| DCF-01 | Phase 7 | Pending | Forward two-stage DCF intrinsic value + discount % |
| DCF-02 | Phase 7 | Pending | Reverse DCF implied-vs-actual-growth gap |
| DCF-03 | Phase 7 | Pending | DCF sector-guarded, terminal-g < discount-rate assert, bounded solver → None |
| SECTOR-02 | Phase 7 | Pending | Per-metric sector applicability matrix; invalid = missing, never zero |
| PAGE-02 | Phase 7 | Pending | docs/stats.html universe overview |
| DATA-01 | Phase 7 | Pending | Periodic snapshots under docs/data/snapshots/ + .gitignore exception |
| DATA-02 | Phase 7 | Pending | Snapshot reuses min-row guard; data-vintage caveat documented |
| DATA-03 | Phase 7 | Pending | (Optional) 30-day fundamentals cache bounds runtime/rate-limit |
| METH-01 | Phase 7 | Pending | methodology.html documents new signals, scoring, thresholds, guards |
