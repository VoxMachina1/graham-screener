---
phase: "05-score-foundation-public-top-n"
plan: "03"
subsystem: "frontend"
tags: ["frontend", "top-n", "scoring", "nav", "cards"]
dependency_graph:
  requires: ["05-02"]
  provides: ["docs/top.html", "docs/app.js", "card CSS in docs/style.css"]
  affects: ["docs/index.html", "docs/methodology.html"]
tech_stack:
  added: []
  patterns: ["array-driven nav", "client-side sort+slice toggle", "inline-style color dispatch"]
key_files:
  created:
    - docs/app.js
    - docs/top.html
  modified:
    - docs/index.html
    - docs/style.css
decisions:
  - "No new CDN dependencies — top.html loads only style.css + app.js (no Tabulator needed for card layout)"
  - "Double-prefix SIGNAL_COLORS keys (Lynch_Lynch_Status, Graham_Graham_Status) preserved verbatim per D-14/Pitfall 5"
  - "Trap badge conditional via is_trap boolean — row still shown (TRAP-02)"
  - "OverallScore color dispatch uses inline style (same pattern as makeSignalFormatter) not CSS classes"
  - "is_trap Tabulator filter uses list filter with explicit values map (true/false/empty) — boolean headerFilter not directly supported by Tabulator list filter"
metrics:
  duration: "~25 min (resumed executor)"
  completed: "2026-06-19"
  tasks_completed: 4
  files_changed: 4
---

# Phase 05 Plan 03: Frontend — Top Picks Page + Shared Module Summary

**One-liner:** Top-N ranked card page (top.html) with OverallScore badge + pillar chips + TRAP badge, shared app.js primitives, and array-driven 3-link nav across all pages.

---

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Extract docs/app.js + wire nav | `52ade9b` | docs/app.js (new), docs/index.html, docs/methodology.html |
| 2 | Build docs/top.html + card/badge/chip CSS | `710e4d9` | docs/top.html (new), docs/style.css |
| 3 | Add OverallScore/pillar/Trap columns to dashboard | `70e0376` | docs/index.html |
| 4 | Automated visual verification (offline) | — | no files |

---

## What Was Built

### docs/app.js (Task 1 — committed in prior run, `52ade9b`)

Shared frontend module loaded by all three pages. Exposes:

- `SIGNAL_COLORS` — Nord Aurora color map, double-prefix keys preserved
- `COLOR_STYLES` — bg/text pairs for green/yellow/red
- `makeSignalFormatter(field)` — Tabulator cell formatter with inline style injection
- `numFmt(decimals)` — numeric formatter (null → em-dash)
- `pctFmt` — percentage formatter
- `updateFreshnessUI(generatedAt)` — freshness badge + stale banner (>3 days)
- `NAV_ENTRIES` — array-driven nav config (Dashboard/Top Picks/Methodology); Stats deferred to Phase 7, addition is one line
- `buildNav(activePage)` — sets `nav.main-nav` innerHTML with active class + `aria-current="page"`

### docs/top.html (Task 2 — `710e4d9`)

Top 10/25 ranked-card page:
- Fetches `data/results.json?v=Date.now()` (cache-busted)
- Filters error rows, sorts by `OverallScore` desc, client-side
- 10/25 toggle: re-slices already-sorted array, no refetch; `aria-pressed` updated
- Card per stock (`.top-card`):
  - Row 1: rank badge, Finviz-linked ticker, price, OverallScore badge (green ≥70 / yellow 40-69 / red <40), TRAP badge when `is_trap`
  - Row 2: four `.pillar-chip` elements (Value/Quality/Growth/Safety, 1dp)
  - Row 3: Lynch/Graham/Defensive `.signal-chip` colored via SIGNAL_COLORS/COLOR_STYLES
- Error and empty states per UI-SPEC copywriting contract
- No new CDN — only `style.css` + `app.js` loaded

### docs/style.css (Task 2 — `710e4d9`)

Appended card/badge/chip CSS (section H):
- `#top-container` — max-width 860px, centered, 1.2rem padding
- `.top-card` — bg #3b4252, border 1px #4c566a, radius 6px, padding 12px 16px, margin-bottom 8px
- `.card-row` — flexbox row, gap 8px, margin-bottom 6px
- `.card-rank` — #434c5e bg, monospace, 4px 8px padding, radius 4px
- `.card-ticker` — 0.9rem, 600 weight, color inherit + underline
- `.card-price` — monospace, #d8dee9
- `.score-badge` — 4px 8px, radius 4px, 600 weight, 0.82rem mono; color applied inline by JS
- `.trap-badge` — #bf616a bg, #eceff4 text, 600 weight, 4px 8px, radius 3px
- `.pillar-chip` — #434c5e bg, #d8dee9 text, 4px 8px, radius 4px, 0.82rem mono
- `.signal-chip` — inline-block, 4px 8px, radius 4px, 0.82rem, 600 weight; color applied inline by JS

### docs/index.html (Task 3 — `70e0376`)

Dashboard updates:
- New columns added before CombinedScore: Overall Score (`OverallScore`, `numFmt(1)`), Value (`score_value`), Quality (`score_quality`), Growth (`score_growth`), Safety (`score_safety`) — all numeric `>=` filter; Trap? (`is_trap`) with "Yes"/"—" formatter and list filter
- `SUMMARY_COLS` updated: added `OverallScore` and `is_trap`
- `initialSort` switched from `CombinedScore` to `OverallScore` desc (SCORE-08)
- `CombinedScore` column retained as non-summary column (additive schema per D-02c)

---

## Deviations from Plan

### Auto-fixed Issues

None.

### Planned deviations

**1. [Planned] Trap? column uses list filter with explicit values map instead of Tabulator boolean filter**
- **Reason:** Tabulator's `headerFilter: "list"` with `valuesLookup: true` does not map boolean true/false to readable labels in all versions. Using an explicit `values` map `{ "true": "Yes", "false": "—", "": "All" }` gives the user readable dropdown options consistent with the "Yes"/"—" cell formatter.
- **Impact:** Cosmetic only — filtering behavior is identical.

**2. [Planned] No Tabulator CSS/JS loaded in top.html**
- **Reason:** top.html uses card layout (divs), not a Tabulator table. Loading Tabulator would be dead weight. UI-SPEC Registry Safety explicitly notes this is acceptable.

---

## Task 4: Visual Verification

**Automated checks completed:**
- `node --check docs/app.js` exits 0 (syntax valid)
- File presence check: both `docs/app.js` and `docs/top.html` exist
- Mock-row assertion suite (node -e, no deps, no files written to docs/data/):
  - `fmtPillar(75)` → `"75.0"`, `fmtPillar(null)` → `"—"` — PASS
  - `scoreBadgeStyle(82)` → green, `(55)` → yellow, `(35)` → red — PASS
  - TRAP badge emitted only when `is_trap === true` — PASS
  - Double-prefix SIGNAL_COLORS keys resolve correctly for Lynch/Graham/Defensive signals — PASS

**Deferred: in-browser visual verification against real scored data**

Opening `docs/top.html` locally today shows scores as "—" because the committed `results.json` predates the Phase 5 score columns (OverallScore/score_value/etc. are not yet in the JSON — they are produced by the Python scoring engine changes from Plan 02 on the next GitHub Actions run).

Full visual sign-off is deferred to the next Actions run, which will regenerate `docs/data/results.json` with the new schema. At that point the user should verify:
1. top.html cards are sorted by OverallScore desc; badge colors match thresholds
2. Pillar chips show real values; TRAP badge appears on trapped rows
3. 10/25 toggle re-slices without page reload; aria-pressed updates
4. Dashboard shows OverallScore/pillar/Trap? columns, sorted by OverallScore desc
5. Nav (Dashboard / Top Picks / Methodology) renders identically on all three pages with active highlight

---

## Known Stubs

None — all data fields are wired; scores display "—" only because the source JSON predates the scoring engine. This is a data availability issue, not a stub.

---

## Threat Flags

No new threat surface beyond what was documented in the plan's threat model (T-05-07 through T-05-SC). The `escHtml()` helper in top.html sanitizes ticker symbols and signal values before innerHTML insertion, mitigating T-05-07. All values come from the project's own results.json pipeline, not user input.

---

## Self-Check: PASSED

- docs/app.js exists: FOUND
- docs/top.html exists: FOUND
- docs/style.css modified: FOUND
- docs/index.html modified: FOUND
- Commit 52ade9b (Task 1): FOUND
- Commit 710e4d9 (Task 2): FOUND
- Commit 70e0376 (Task 3): FOUND
