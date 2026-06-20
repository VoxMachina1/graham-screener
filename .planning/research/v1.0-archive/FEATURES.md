# Feature Landscape: Lynch/Graham Stock Screener Dashboard

**Domain:** Financial stock screener — static GitHub Pages dashboard
**Researched:** 2026-05-29
**Confidence:** HIGH (grounded in this codebase's existing columns/signals + established patterns from platforms like Finviz, Koyfin, Simply Wall St, and Morningstar)

---

## Existing Data Shape (what the backend already produces)

Before listing features, the relevant columns from `push_to_gsheets()` and `SIGNAL_COLORS`:

**Signal columns (left-pinned, color-coded):**
- `Status_Combined` — True/False buy flag (any Buy signal from either framework)
- `Score` — 0–60 blended discount score, sorted descending
- `Lynch_Status` — Strong Buy / Buy / Hold / Avoid
- `Lynch_PEG_Band` — Strong Buy / Buy / Hold / Avoid
- `Graham_Status` — Deep Buy / Buy / Watch / Avoid
- `Defensive` — Pass / Borderline / Fail
- `Defensive_Score` — raw 0–8 integer

**Price/valuation columns:**
- `Price`, `Lynch_BuyPrice`, `Graham_FairValue`
- `Lynch_Discount_Pct`, `Graham_Discount_Pct`
- `Lynch_PE`, `Lynch_PEG`, `Lynch_PEGY`, `Lynch_Score`, `Lynch_LV_Ratio`
- `Graham_VA`, `Graham_VB`

**Fundamental columns:**
- `Ticker`, `Indexes` (S&P500 / Dow30 / Nasdaq100)
- `Category` (Slow / Stalwart / Fast)
- `Growth_Pct`, `EPS`, `Div_Yield_Pct`, `PB_Ratio`, `MarketCap_B`
- `Lynch_FV_PEG`, `Lynch_FV_PEG_Con`, `Lynch_FV_GplusD`
- Defensive check columns: `Size_OK`, `CurrRatio_OK`, `DebtEq_OK`, `EPS_Stability`, `Div_Record`, `EPS_Growth10Y`, `PE_Limit`, `PB_Limit`
- `AAA_Yield`, `EPS_Annual` (historical list as string)
- `Error` (present when ticker skipped)

---

## Table Stakes

Features users expect. Missing = dashboard feels incomplete or unprofessional.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Sortable columns | Universal table expectation; central to screener UX | Low | Click header to sort asc/desc; Score col sorted desc by default |
| Traffic-light color coding on signal cells | Already exists in Sheets; users arriving from Sheets expect it | Low | Green/yellow/red matching existing `SIGNAL_COLORS` map |
| "Buy signals only" filter toggle | The #1 user action — "show me what to look at" | Low | Filters to `Status_Combined == True`; one click, not a dropdown |
| Text search / ticker lookup | Users type a ticker they're curious about | Low | Filter-as-you-type on the Ticker column |
| Sticky header row | 550 rows; header disappears without this | Low | `position: sticky; top: 0` in CSS |
| Frozen / sticky first column (Ticker) | Wide tables scroll horizontally; ticker gets lost | Low | CSS `position: sticky; left: 0` |
| "Last updated: [date]" indicator | Users need to know if data is stale (weekends, holidays) | Low | Embed timestamp in results.json; display prominently near top |
| Column grouping / visual separation | 30+ columns; needs visual structure | Low | Thin vertical divider between signal group and price group |
| Responsive table (horizontal scroll on mobile) | GitHub Pages is public; some users will be on phones | Low | `overflow-x: auto` wrapper; don't try to reflow columns |
| Top 20 summary view | Already in Sheets as a separate tab; expected by existing users | Medium | See UX section below |
| Methodology documentation | Already in Sheets as Documentation tab; users ask "how does this work?" | Medium | See UX section below |
| Data refresh timestamp | Weekday schedule; users need to know if today's run succeeded | Low | Show run date and time in UTC or ET |

---

## Differentiators

Features that go beyond the Sheets baseline and justify the migration.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Filter by signal type | "Show only Graham Buy stocks" or "Lynch Strong Buy only" | Low | Dropdown or pill buttons per signal column; much harder in Sheets |
| Filter by Lynch category | Separate slow/stalwart/fast growers for different strategies | Low | Radio group or checkboxes; 3 values |
| Filter by index membership | "Dow 30 only" — useful for conservative investors | Low | Checkbox group: S&P500, Dow30, Nasdaq100 |
| Filter by defensive score | "Graham defensive Pass only" — Graham purist filter | Low | Dropdown: All / Pass / Pass+Borderline |
| Column visibility toggle | 30+ columns is overwhelming; let users hide raw calculation columns | Medium | "Show/hide columns" button with a checklist; persist in localStorage |
| Column presets | One-click to switch between "Signal view" (10 cols) and "Full data" (all cols) | Low | Two or three preset buttons; layered on top of visibility toggle |
| Shareable filtered URL | Copy link with current filters encoded in query params | Medium | `?signal=Buy&category=Fast` — no backend needed, all client-side |
| Keyboard shortcut to focus search | Press `/` to focus ticker search box | Low | Single event listener; matches GitHub/Notion conventions |
| Highlight row on hover | Makes wide-row scanning easier | Low | CSS `tr:hover` background |
| Score bar / mini sparkline in Score cell | Visual encoding of magnitude, not just number | Low | CSS width-based bar in the Score cell (`display: inline-block`) |

---

## Anti-Features

Things to deliberately NOT build. Each omission is a considered decision.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Real-time or live price updates | Requires a backend/API proxy; breaks the static constraint; daily data is the stated scope | Show "Last updated" timestamp clearly so users know it's daily |
| Charts / historical price graphs | Out of scope per PROJECT.md; requires historical data storage not currently produced | Link ticker to a free charting site (Yahoo Finance or TradingView) in the Ticker cell |
| User accounts or watchlists | Out of scope; backend-free is a hard constraint | localStorage-based "pinned tickers" could be considered later but is not MVP |
| Pagination (instead of all rows) | 550 rows is fast to render in a well-built table; pagination adds navigation complexity | Use virtual scrolling only if render performance proves to be a real problem |
| Per-column range filters (slider) | Finviz-style numeric range filters add UI complexity; ticker search + signal filters cover 90% of use cases | Simple signal-type dropdowns are sufficient |
| Export to CSV/Excel | Nice-to-have but low priority; the JSON file is already publicly accessible in the repo | Users who want raw data can fetch results.json directly |
| Dark mode toggle | Nice-to-have, adds complexity; not a screener-specific need | A neutral light theme with good contrast is sufficient for MVP |
| Server-side filtering/search | No server exists; everything is client-side | All filtering in-browser via JavaScript on the full JSON dataset |
| iframe embeds or widget mode | No identified use case | Not building |
| Multi-run comparison / trend data | Out of scope per PROJECT.md | Each run is independent; results.json contains current state only |

---

## UX Recommendations

### Q1: Filtering and Sorting Patterns

**Sorting:** Sort by `Score` descending on load (matches the existing Sheets behavior). Make all column headers clickable. Show sort direction indicator (arrow). Second click reverses direction. Third click returns to default Score sort — or just toggle; avoid a third state for simplicity.

**Primary filters (always visible, above the table):**
1. **"Buy signals only" toggle** — a prominent pill button or checkbox, not buried in a dropdown. This is the single most common action. Label it "Buy Signals Only" and default to OFF so users can choose to start broad or narrow.
2. **Signal filter row** — three dropdowns (one per signal column): Lynch Status, Graham Status, Defensive. Each defaults to "All". Options are the actual values from the codebase (Strong Buy / Buy / Hold / Avoid / All, etc.). Don't overload a single dropdown.
3. **Category filter** — three pill buttons: Slow / Stalwart / Fast / All. Pills are better than a dropdown for 3–4 options; they're immediately scannable.
4. **Index filter** — three checkboxes: S&P500 / Dow30 / Nasdaq100. Stocks can be in multiple indexes; checkboxes handle multi-select naturally.
5. **Ticker search** — text input at the top right. Filter-as-you-type. Does not compete with signal filters — both can be active simultaneously.

**Column presets (strongly recommended):**
- "Summary view" (default): Ticker, Indexes, Status_Combined, Score, Lynch_Status, Graham_Status, Defensive, Price, Category, Growth_Pct
- "Valuation view": Ticker, Price, Lynch_BuyPrice, Lynch_Discount_Pct, Graham_FairValue, Graham_Discount_Pct, Score, Lynch_PE, Lynch_PEG, PB_Ratio
- "Full data": all columns

Store active preset in `localStorage`. Preset buttons are more discoverable than a full column picker for most users, but offer the column picker too for power users.

### Q2: Column Layout

**Left group — signals (always visible, sticky):**
Ticker | Indexes | Status | Score | Lynch Status | Graham Status | Defensive

**Middle group — price/valuation:**
Price | Lynch Buy Price | Lynch Discount% | Graham Fair Value | Graham Discount%

**Right group — fundamentals:**
Category | Growth% | EPS | Div Yield | P/B | Market Cap

**Far right — detail columns (hidden in Summary view):**
Lynch PEG | Lynch PEGY | Lynch Score | Graham VA | Graham VB | Defensive Score | individual defensive check columns

Signal columns (Lynch_Status, Graham_Status, Defensive, Status_Combined) should have a fixed width narrower than numeric columns — the text values are short. Score column should be wide enough to show the mini score bar differentiator.

**Width guidance for 550-row table:**
- Ticker: ~80px (6 chars max)
- Signal text columns: ~110px
- Score: ~90px
- Price/dollar columns: ~100px
- Percent columns: ~90px
- Indexes: ~130px (comma-separated list)

### Q3: Top 20 View

**Recommendation: inline sticky panel above the table, not a separate tab or modal.**

Rationale:
- A separate tab (like Sheets) loses the table context and breaks deep-link sharing
- A modal requires a trigger click and hides everything else
- A sticky panel above the table is always visible, collapses gracefully, and doesn't require navigation

Implementation:
- A collapsible section at the top of the page (open by default on first visit, `localStorage`-remembered)
- Title: "Top 20 Buy Signals — [date]" (matches existing Sheets tab name)
- A compact table showing: Rank | Ticker | Price | Lynch | Graham | Defensive | Category | Growth% | Score
- Clicking a ticker in the Top 20 panel jumps to and highlights that row in the main table (anchor + JS scroll-to)
- On mobile: collapses to a "Show Top 20" toggle by default

The collapsible panel approach also preserves the "copy as markdown" use case from Sheets — add a small "Copy as Markdown" button that dumps the Top 20 as a markdown table to the clipboard. This is low effort and high value for users who currently use the Sheets "Top 20 Summary" tab.

### Q4: Methodology Documentation

**Recommendation: dedicated `/methodology` page (or `methodology.html`), linked prominently from the header.**

Rationale:
- The existing `DOCS_CONTENT` block is ~140 lines of text — too long for a modal and too long for a collapsible section that shares page space with the table
- A separate page allows linking to specific sections (anchor links to "Lynch Framework", "Graham Framework", "Signal Definitions", etc.)
- Collapsible sections within the methodology page work well for the sub-sections
- A modal would be awkward to scroll through on mobile

Implementation:
- Header nav: [Dashboard] [Methodology] — two links, always visible
- Methodology page sections (matching existing DOCS_CONTENT structure):
  1. Overview
  2. Signal Columns (color coding guide with colored swatches)
  3. Peter Lynch Framework (with formula display)
  4. Benjamin Graham Framework (with formula display)
  5. Graham Defensive Checklist (numbered list)
  6. Data Sources
- Use `<code>` blocks or styled formula displays for the math: `EPS × (8.5 + 2 × Growth%) × 4.4 ÷ AAA_Yield`
- On the main dashboard, add a small info icon (i) next to each signal column header that links to the relevant section of the methodology page

**Do not use a modal for methodology.** The content is too long, and modals are frustrating on mobile.

### Q5: Data Refresh Indicators

**What users expect from established screeners:**

1. **Prominent "As of [date]" badge** — near the page title, not in the footer. Use the run date from results.json. Format: "Data as of May 29, 2026" (not a timestamp — date is sufficient for daily data).

2. **Stale data warning** — if the current date is more than 3 calendar days after the data date (covers weekends + 1 missed weekday), show a yellow banner: "Data may be outdated — last updated [date]". This catches failed Actions runs or holidays without requiring user knowledge of the schedule.

3. **Run status signal** — small colored dot next to the "As of" date: green = data is from today or yesterday, yellow = 2–3 days old, red = 4+ days old. This is a one-line computation based on date difference.

4. **No loading spinner** — results.json is fetched once on page load. Show a loading state during the fetch, then replace with the table. Don't show partial data.

5. **"Weekday updates" note** — small subtitle under the badge: "Updated each weekday at ~6am ET". Prevents "why hasn't it updated on Saturday?" support questions.

### Q6: Table Density and Financial Data Readability

**Freeze first column:** Yes, freeze Ticker column. On a 30-column table scrolled horizontally, the ticker context is lost immediately. CSS `position: sticky; left: 0; z-index: 1` with a background color matching the row.

**Sticky header:** Yes. Essential at 550 rows. CSS `position: sticky; top: 0; z-index: 2`. Header background should be opaque (not transparent) to cover scrolling content.

**Row density:** Use "compact" density by default — financial screeners are power-user tools, and users prefer seeing more rows without scrolling. Suggested: `padding: 4px 8px` per cell. Offer a density toggle (compact / comfortable) only if it becomes a user request; don't pre-build it.

**Number formatting:**
- Prices: `$123.45` (2 decimal places, dollar sign)
- Percentages: `12.3%` (1 decimal place, percent sign)
- Score: `42.1` (1 decimal, no units — it's a relative score)
- PEG/PEGY ratios: `1.234` (3 decimal places — meaningful at this precision)
- Market cap: `$12.3B` or `$890M` (abbreviate; don't show raw billions with many decimals)
- EPS: `$3.45` (2 decimal places)
- Defensive Score: `6/8` (show denominator for immediate context)

**Signal cells:** Short text with background color only (no bold, no icons). The color carries the meaning. Keep signal cell text left-aligned.

**Numeric cells:** Right-align all number columns. Text columns left-align. This is universal financial table convention.

**Null/missing values:** Display as `—` (em dash), not empty, `null`, `NaN`, or `0`. The `Error` column values (e.g., "No EPS") should make the row visually subdued (light gray text) since it failed valuation.

**Row striping:** Alternating row background (very light — near-white and white) helps track rows across 30 columns. Not essential if hover highlight is implemented, but both together is fine.

**Column header tooltips:** Financial column names like `Lynch_PEGY` or `Graham_VB` are not self-explanatory. Add `title` attributes on `<th>` elements with a one-line description. On hover, the browser shows the native tooltip. This is zero-JS and covers the methodology inline without linking away.

---

## Feature Priority for MVP

**Must have (Phase 1):**
- Full sortable table with all existing columns
- Traffic-light color coding matching existing SIGNAL_COLORS
- Sticky header + frozen Ticker column
- "Buy signals only" toggle
- Ticker search
- "Data as of [date]" indicator with stale data warning
- Top 20 panel (collapsible, inline)
- Methodology page (static HTML)
- Column presets (Summary / Full)
- Null display as em dash; Error rows dimmed

**Should have (Phase 2 / fast follow):**
- Signal-type filter dropdowns (Lynch, Graham, Defensive)
- Category filter pills (Slow / Stalwart / Fast)
- Index membership filter (S&P500 / Dow30 / Nasdaq100)
- Score mini-bar in Score cell
- Column header tooltips
- Column visibility toggle (power user)
- "Copy as Markdown" button on Top 20

**Nice to have (later / if requested):**
- Shareable filtered URL (query params)
- Keyboard shortcut (`/` to focus search)
- Ticker cell links to Yahoo Finance or TradingView
- `localStorage` persistence of filter state

---

## Sources

- Existing codebase: `stock_screener.py` (SIGNAL_COLORS, column layout, DOCS_CONTENT)
- Existing codebase: `.planning/PROJECT.md` (scope constraints, out-of-scope items)
- Pattern reference: Finviz (screener filter UX, column density), Koyfin (column presets), Simply Wall St (methodology presentation), Morningstar (freeze columns, data freshness indicators)
- Confidence: HIGH for table stakes and UX patterns (well-established conventions); MEDIUM for differentiator priority ordering (depends on actual user behavior)
