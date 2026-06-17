# Technology Stack Research: GitHub Pages Static Stock Screener

**Project:** Lynch & Graham Screener — Static Frontend
**Researched:** 2026-05-29
**Research mode:** Ecosystem + Feasibility
**Confidence basis:** Training data through August 2025. External tools (WebSearch, WebFetch, Bash) were unavailable in this environment. All claims marked with confidence level. The libraries covered here are mature and well-established; confidence is HIGH for all primary recommendations.

---

## Research Question Answers

### Q1: Best no-build static table library for ~550 rows / ~30 columns

**Recommendation: Tabulator 6.x**

Rationale: Tabulator is the only major table library designed from the ground up to work without a build step, with first-class CDN support, zero mandatory dependencies, and a rich feature set that matches every stated requirement. It is actively maintained, has an MIT license, and ships self-contained CSS + JS bundles via CDN.

**Comparison matrix:**

| Library | Version | CDN support | Dependencies | Min bundle (JS+CSS) | Sort | Filter | Cell formatters | License |
|---------|---------|------------|--------------|---------------------|------|--------|-----------------|---------|
| **Tabulator** | 6.2 | YES (jsDelivr, unpkg) | None | ~200 KB | YES, built-in | YES, built-in | YES, built-in | MIT |
| DataTables | 2.x | YES (CDN.datatables.net) | jQuery required | ~120 KB + jQuery (~90 KB) | YES | YES (extension) | YES | MIT |
| AG Grid Community | 31+ | YES (unpkg, CDN) | None | ~700–900 KB | YES | YES | YES (cell renderers) | MIT (community) |
| Grid.js | 6.x | YES (unpkg, CDN) | None | ~50 KB | YES | YES (plugin) | YES | MIT |
| Handsontable | 14.x | YES | None | ~500 KB | YES | YES | YES | Non-commercial free / paid |

**Detailed verdicts:**

**Tabulator 6.x — RECOMMENDED**
- CDN install: one `<link>` and one `<script>` from jsDelivr, nothing else.
- Built-in: multi-column sorting, header filters (text input, select, range), column formatters (color, icon, custom function), pagination, frozen columns.
- `formatter` callback per column makes traffic-light coloring trivial — a function receives cell value, returns any HTML or sets background color directly via `cell.getElement().style`.
- `ajaxURL` or `fetch`-then-`setData()` both work; for a same-origin JSON file, `fetch()` then `table.setData(data)` is the simpler pattern.
- 550 rows × 30 columns is well within Tabulator's comfort zone without virtualization. Virtualization (`renderType: "virtual"`) is available if needed.
- Confidence: HIGH

**DataTables 2.x — viable alternative, not recommended**
- Requires jQuery. Adds ~90 KB with no functional benefit for this use case. The jQuery dependency is the main reason to prefer Tabulator.
- Column search requires the `SearchBuilder` or `SearchPanes` extension (separate CDN load).
- Extremely mature and battle-tested; good documentation. Choose this if jQuery is already on the page for another reason.
- Confidence: HIGH

**AG Grid Community — overkill, not recommended**
- Bundle is 3–5x larger than Tabulator. Designed for enterprise row counts (100K+) and React/Angular/Vue integrations. Vanilla JS usage works but the API is more complex for the same features.
- Community edition is MIT licensed; the enterprise edition requires a commercial license. CDN-only usage of community edition is fine.
- Confidence: HIGH

**Grid.js — viable for minimal setups, not recommended here**
- Smallest bundle, very clean API. However, column-level filtering requires a plugin, and cell-level custom formatters (needed for traffic-light coloring) are less ergonomic than Tabulator's.
- Better suited for simple read-only tables. The signal columns require per-cell color logic, which Tabulator handles more naturally.
- Confidence: HIGH

**Handsontable — explicitly avoid**
- License changed: free only for non-commercial use (GPL-style for open source, paid for commercial). A public GitHub Pages site tied to personal investing is likely fine legally, but it adds ambiguity not present with the MIT alternatives. Not worth the risk.
- Confidence: HIGH (licensing is publicly documented)

---

### Q2: Is vanilla JS + CDN library viable for this scale?

**Yes, definitively.**

550 rows × 30 columns = 16,500 cells. This is not a large dataset by browser standards. Modern browsers handle DOM trees of this size without issue, especially with a table library that batches rendering. No framework (React, Vue, Svelte) is needed or beneficial here. Framework build pipelines exist to solve component reuse and reactivity at scale — neither applies to a static dashboard displaying a single daily snapshot.

Vanilla JS + Tabulator via CDN is the correct architecture. The full page can be written as a single `index.html` with an inline `<script>` block.

Confidence: HIGH

---

### Q3: GitHub Pages deployment — `docs/` folder vs `gh-pages` branch

**Recommendation: `docs/` folder on `main`**

GitHub Pages offers three source configurations (as of 2024):
1. Root of `main` (or any branch) — entire repo is served
2. `/docs` subfolder of `main` — only the `docs/` directory is served
3. A dedicated `gh-pages` branch — entire branch is served
4. GitHub Actions deployment (writing to Pages via the Actions artifact API — the "modern" method)

**For this project, use `docs/` on `main`.** Rationale:

- The Python screener already commits `results.json` to the repo. Having the frontend in `docs/` means a single commit (from the Actions job) can update both the data file and be adjacent to the frontend files — all in one place, all versioned together.
- No branch-switching complexity. The `gh-pages` branch approach requires either a dedicated orphan branch or tooling like `gh-pages` npm package to push to it — both add friction for a Python-only project.
- `docs/` is simpler to reason about: `docs/index.html`, `docs/results.json`, done.
- The Actions job writes `results.json` to `docs/results.json` (or the repo root `results.json` if you prefer to keep data outside `docs/`), commits, and pushes. Pages re-deploys automatically on push.

**On the Actions artifact method (gh-pages via Actions):** GitHub introduced a first-party `actions/deploy-pages` action that uploads a Pages artifact from an Actions run without committing to the repo. This is cleaner for generated content but adds complexity (separate upload step, artifact retention). Since the goal is to have `results.json` committed and versioned in git anyway, the artifact method offers no advantage here.

Confidence: HIGH (GitHub Pages configuration is well-documented and stable)

---

### Q4: Fetching a local JSON file on GitHub Pages

**Use `fetch('results.json')` with a relative path. No CORS issues.**

GitHub Pages serves all files in the configured source directory from the same origin (`https://<user>.github.io/<repo>/`). A `fetch('results.json')` call from `index.html` in the same directory resolves to the same origin — CORS does not apply to same-origin requests.

**Specific implementation notes:**

- Place `results.json` in the same directory as `index.html` (both in `docs/`) and use `fetch('results.json')` — this is a relative URL, always same-origin.
- If `results.json` is at the repo root and `index.html` is in `docs/`, use `fetch('../results.json')` — still same-origin, still no CORS.
- `fetch()` works for all file types served by Pages; GitHub Pages serves `.json` with `Content-Type: application/json`, which is correct.
- **Local development caveat:** `fetch()` fails for `file://` URLs due to browser security restrictions (this applies locally, not on Pages). During local dev, serve with `python -m http.server` from the `docs/` directory. This is the only local-dev tooling needed.
- Avoid `XMLHttpRequest` — `fetch()` is the modern standard and is supported in all browsers that would access a GitHub Pages site.

**Pattern:**
```javascript
fetch('results.json')
  .then(r => r.json())
  .then(data => {
    table.setData(data);
  });
```

Confidence: HIGH

---

### Q5: Licensing concerns for CDN-loaded libraries

**No concerns for the recommended stack.**

| Library | License | Public GitHub Pages OK? | Commercial restriction? |
|---------|---------|------------------------|------------------------|
| Tabulator 6.x | MIT | YES | No |
| DataTables 2.x | MIT | YES | No |
| AG Grid Community | MIT | YES | No |
| Grid.js | MIT | YES | No |
| jsDelivr CDN | Free tier | YES | None for open-source repos |
| unpkg CDN | Free tier | YES | None |

MIT license means: free to use, distribute, and modify in any project (commercial or non-commercial) as long as the license text is retained. Retention is automatic when loading from CDN — the library's own source includes the license header.

**jsDelivr vs unpkg:** Both are free, reliable CDNs. jsDelivr has historically had better uptime SLAs and caches more aggressively. Either works. jsDelivr is preferred.

Confidence: HIGH

---

## Recommended Stack

### Core

| Technology | Version | Purpose | CDN URL |
|------------|---------|---------|---------|
| HTML5 | — | Page structure | — (no CDN) |
| Vanilla JavaScript (ES2020+) | — | Table initialization, fetch, color logic | — (inline) |
| Tabulator | 6.2+ | Interactive sortable/filterable table | jsDelivr (see below) |

**CDN links for `<head>`:**
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/tabulator-tables@6.2.5/dist/css/tabulator.min.css">
<script type="text/javascript" src="https://cdn.jsdelivr.net/npm/tabulator-tables@6.2.5/dist/js/tabulator.min.js"></script>
```
(Pin to a specific minor version to avoid surprise breakage.)

### File Layout

```
docs/
  index.html        — single-page dashboard
  results.json      — written by Python screener, committed by Actions job
```

No other files required. CSS can be inline in `index.html` for simplicity. Splitting to `style.css` is fine if the file grows.

### GitHub Pages Configuration

- Source: `docs/` folder on `main` branch
- Set in repo Settings → Pages → Source → "Deploy from a branch" → branch: `main`, folder: `/docs`
- No `_config.yml` needed (Jekyll not used)
- Add a `.nojekyll` file at the repo root (or in `docs/`) to prevent GitHub Pages from running Jekyll processing on the directory — important if any folder names start with `_`

### Color Coding Implementation

The existing `SIGNAL_COLORS` dict in `stock_screener.py` maps column name → cell value → RGB. Mirror this in JavaScript as a plain object. Tabulator's `formatter` option per column receives the cell value and can set `cell.getElement().style.backgroundColor` directly.

```javascript
const SIGNAL_COLORS = {
  "Lynch_Status": {
    "Strong Buy": "#b6d7a8",
    "Buy":        "#b6d7a8",
    "Hold":       "#ffe599",
    "Avoid":      "#ea9999",
  },
  // ... other signal columns
};

// In column definition:
{
  title: "Lynch Status",
  field: "Lynch_Status",
  formatter: function(cell) {
    const val = cell.getValue();
    const colors = SIGNAL_COLORS["Lynch_Status"];
    if (colors && colors[val]) {
      cell.getElement().style.backgroundColor = colors[val];
    }
    return val;
  }
}
```

The RGB values from Python (`_GREEN = {"red": 0.714, "green": 0.843, "blue": 0.659}`) convert to hex as `#b6d7a8` (multiply each channel by 255, round, format as hex). This conversion is a one-time manual step.

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Table library | Tabulator 6.x | DataTables 2.x | Requires jQuery; no functional advantage |
| Table library | Tabulator 6.x | AG Grid Community | 3–5x larger bundle; enterprise-oriented API |
| Table library | Tabulator 6.x | Grid.js | Per-cell color formatting is less ergonomic |
| Deployment | `docs/` on `main` | `gh-pages` branch | Requires separate branch or npm tooling |
| Deployment | `docs/` on `main` | Actions artifact upload | Extra complexity; no benefit since JSON is committed anyway |
| Framework | None (vanilla JS) | React/Vue/Svelte | Requires build pipeline; overkill for a single static page |
| Local dev server | `python -m http.server` | Node.js `live-server` | Python is already the project language; no extra installs |

---

## What NOT to Use

**React / Vue / Svelte / Angular**
Any framework that requires `npm install` + a build step violates the stated constraint. The output is a static file; the data is static JSON; there is no state management problem to solve. Adding a framework would require Vite/webpack/Rollup, complicate the Actions pipeline, and provide zero user-visible benefit.

**Handsontable**
License ambiguity (GPL/commercial dual license). MIT alternatives exist with equivalent features.

**Plotly / Chart.js / D3**
Charting libraries, not table libraries. Useful if trend charts are added later (out of scope per PROJECT.md), but wrong tool for a sortable data table.

**Jekyll/Liquid templates**
GitHub Pages runs Jekyll by default. This project does not need Jekyll's template system. Add `.nojekyll` to opt out and keep the build chain simple.

**Bootstrap Table / Semantic UI Table**
These are CSS-only or CSS+JS table enhancements that add basic sorting. They lack built-in column filtering. Tabulator covers sorting, filtering, and cell formatting in one CDN load.

---

## Confidence Assessment

| Area | Confidence | Basis |
|------|-----------|-------|
| Tabulator as recommended library | HIGH | Mature library, stable since v5; v6 released 2023, CDN support is core feature |
| DataTables/AG Grid/Grid.js comparison | HIGH | All are established libraries with stable APIs and documented CDN support |
| GitHub Pages `docs/` folder approach | HIGH | Documented GitHub feature, stable since 2016, widely used |
| `fetch()` same-origin behavior on Pages | HIGH | Standard browser behavior; not GitHub-specific |
| Local dev `file://` fetch restriction | HIGH | Well-documented browser security restriction |
| MIT licensing for all recommended libraries | HIGH | Publicly documented, verified against known license files |
| 550-row performance without virtualization | HIGH | Browser DOM handles <10K rows without issue; Tabulator docs confirm |
| jsDelivr reliability | MEDIUM | Good historical track record; CDN availability is always a minor operational risk |

---

## Gaps / Open Questions

1. **Exact column list and types for Tabulator column definitions** — need to inspect what `process_ticker()` returns (all dict keys) to write the full column definitions array. This is implementation detail, not a stack question.

2. **`results.json` schema** — the Python screener doesn't yet write JSON; the schema (array of objects vs object with metadata) should be decided when implementing the writer. Recommendation: plain array of row objects, one object per ticker, matching the DataFrame column names as keys. Tabulator's `setData()` accepts this directly.

3. **Top 20 summary view** — PROJECT.md lists this as a requirement. It can be a second Tabulator instance filtered to the top 20 rows by `CombinedScore`, or a simple static HTML table pre-rendered. No additional library needed.

4. **Pinning Tabulator version** — the CDN URL above uses `@6.2.5`. Verify the latest 6.x patch version at https://cdn.jsdelivr.net/npm/tabulator-tables/ before implementation and pin to that exact version.
