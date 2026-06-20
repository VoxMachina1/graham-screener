# Architecture Research — v2.0 Integration

**Domain:** Single-file Python batch screener + static Tabulator frontend (GitHub Pages)
**Researched:** 2026-06-17
**Confidence:** HIGH (grounded in the actual codebase + locked decisions in `v2-METHODOLOGY-EXPANSION.md`; no external unknowns)

This file answers: *where do the v2.0 scoring + signals integrate into the existing architecture, what is new vs modified, how does the JSON schema evolve, how do the new pages share (or not share) code, and in what order should it be built.*

---

## 0. TL;DR Decisions (for the roadmapper)

| Question | Decision | One-line rationale |
|---|---|---|
| Single-file vs module split | **Extract `scoring.py`** (4-pillar composite + sub-score mapping + winsorize). Keep new *fetch/factor* code inside `stock_screener.py` Step 3/4. | The composite is config-heavy and self-contained pure logic; it is the one piece large enough that "simplicity first" favors a seam. Factors are small and belong next to existing metric functions. |
| New factor signals in `process_ticker()` | Add **one orchestration helper per concern** called from `process_ticker()` (`compute_factor_signals()`, `compute_distress_signals()`, `compute_dcf()`), not inline blocks. `process_ticker()` stays a thin conductor. | Prevents `process_ticker()` from becoming a god-function; mirrors the existing `lynch_metrics`/`graham_metrics` call pattern. |
| Fetch expansion | Extend `get_combined_data()` return dict + add **one new fetcher** `get_yf_price_history_5y()`. Stop discarding the Finnhub `metric=all` bundle fields we already pull. | Most factor inputs (FCF, EV/EBIT, ROIC) are already in the Finnhub bundle currently thrown away; only 5y price history and 2yr statements are genuinely new fetches. |
| JSON schema | **Additive flat columns + one nested `scores` object per row.** Leave the `Lynch_Lynch_`/`Graham_Graham_` double-prefix ALONE. | Surgical-change principle; renaming touches `index.html` (SIGNAL_COLORS, buildColumns, SUMMARY_COLS) and `methodology.html` for zero functional gain and high regression risk. |
| Frontend code sharing | **Introduce one shared `docs/app.js`** for the genuinely-duplicated primitives (fetch+cache-bust, formatters, SIGNAL_COLORS, freshness UI). Keep page-specific wiring inline per page. | Three pages now duplicate the same formatter/color/fetch code; that crosses the threshold where a shared file is *less* complex than triplicated inline JS. Still no build step (plain `<script src>`). |
| Snapshot mechanism | **Actions workflow step**, date-gated, copying the committed `results.json` to `docs/data/snapshots/YYYY-MM-DD.json`. Python stays snapshot-agnostic. | Snapshotting is a git/CI concern, not a screener concern; keeps the min-100-row guard as the single quality gate before anything is committed. |
| GICS sector | Fetch in `get_combined_data()` (yfinance `.info["sector"]` with Finnhub `finnhubIndustry` fallback), thread as `row["Sector"]`, consume in `scoring.py` sector guards. | Sector is a per-ticker fundamental; belongs with the other per-ticker fetches. |

---

## 1. Current Architecture (verified from source)

```
┌──────────────────────────────────────────────────────────────────────┐
│  DATA SOURCES                                                          │
│  Wikipedia ──► get_universe()    FRED ──► fetch_aaa_yield()           │
│  yfinance  ──► get_yf_price_and_history()                             │
│  Finnhub   ──► get_finnhub_metrics()   (metric=all bundle)           │
└───────────────────────────┬──────────────────────────────────────────┘
                            ▼
              get_combined_data(ticker)  →  unified fund dict
                            ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  process_ticker(ticker, aaa_yield)   [Step 5 — orchestrator]  │
   │    price/EPS/g/dy guards → early-return error dict            │
   │    lynch_metrics()        → row["Lynch_*"]   (double-prefix)  │
   │    graham_metrics()       → row["Graham_*"]  (double-prefix)  │
   │    graham_defensive_score() → row[...] (flat, no prefix)      │
   │    combined_score()       → row["CombinedScore"]             │
   │    Show = any buy signal                                     │
   └───────────────────────────┬──────────────────────────────────┘
                              ▼
              run_screener()  → DataFrame, sort by CombinedScore
                              ▼
              write_json()  → docs/data/results.json  (min-100-row guard)
                              ▼
   Actions: python stock_screener.py → git add/commit/push results.json
                              ▼
   docs/index.html (Tabulator) + methodology.html   [all JS inline]
```

**Key facts confirmed in source:**
- `combined_score()` (`stock_screener.py:528`) is 10 lines — trivially replaceable.
- The double-prefix is created by `row.update({f"Lynch_{k}": v ...})` (`:604`) where `lynch_metrics` already emits keys like `Lynch_Status`, `Lynch_Score`, `Lynch_BuyPrice` → yields `Lynch_Lynch_Status` etc. Same for Graham (`:608`). Defensive score keys are flat (no prefix) because `graham_defensive_score` returns plain keys and `row.update(ds)` adds them directly (`:621`).
- The Finnhub `metric=all` bundle is fetched in full (`get_finnhub_metrics`, `:188`) but `get_combined_data` only reads ~10 fields and **discards the rest** — FCF, EV/EBIT, ROIC, ROE live in that bundle today.
- Active workflow is `.github/workflows/screener.yml` (has `permissions: contents: write` + commit/push). Root `screener.yml` is a **stale duplicate** (no push step, references dead Tiingo/GSheet secrets) — flag for cleanup, not a v2 dependency.
- The deferred **Buy Price bug** lives in `lynch_metrics()` (`Lynch_BuyPrice` = `FV_GplusD * LYNCH_DISCOUNT[cat]`, `:370`) and feeds `Lynch_Discount_Pct` (`:415`) which feeds `combined_score`. New VALUE pillar reuses the same discounts → **must fix before scoring builds on it** (locked decision).

---

## 2. New vs Modified Components

### NEW files

| File | Responsibility | Why new |
|---|---|---|
| `scoring.py` | 4-pillar absolute composite. `score_metric(value, thresholds)` sub-score mapper, `winsorize(value, lo, hi)`, per-pillar aggregation with missing-data averaging, `compute_overall_score(row) -> dict` returning `{overall, value, quality, growth, safety, coverage}` + per-metric decomposition. Holds the `SCORE_THRESHOLDS` / `PILLAR_WEIGHTS` config constants. | Large, pure, config-dense, single-responsibility. The one piece where a module seam reduces total complexity vs. inlining ~150 lines into the already-1200-line script. |
| `docs/app.js` | Shared frontend primitives: `fetchResults()` (cache-bust), `numFmt`/`pctFmt`/`makeSignalFormatter`, `SIGNAL_COLORS`/`COLOR_STYLES`, `updateFreshnessUI()`. | Three pages now need identical fetch+format+color logic. |
| `docs/top.html` | Top 10/25 by `OverallScore`. Reads same `results.json`, sorts+slices client-side. N toggle. Card/compact layout (mockup approved). | Locked deliverable (Phase A). |
| `docs/stats.html` | Universe aggregates (Phase C). | Locked deliverable. |
| `docs/data/snapshots/` | Directory holding `YYYY-MM-DD.json` historic copies. Needs a `.gitignore` exception (see §6). | Locked decision 1b. |

### MODIFIED files

| File | Change | Granularity |
|---|---|---|
| `stock_screener.py` | (a) Fix Buy Price bug in `lynch_metrics()`. (b) Expand `get_combined_data()` return dict (FCF, EV/EBIT, ROIC, ROE, sector). (c) New fetcher `get_yf_price_history_5y()`. (d) New compute helpers `compute_factor_signals()`, `compute_distress_signals()`, `compute_dcf()` in Step 4. (e) `process_ticker()` calls the new helpers + `scoring.compute_overall_score(row)`; replace `CombinedScore` line. (f) `run_screener()` sort key → `OverallScore`. | Function-level, additive. |
| `docs/index.html` | Inline duplicated primitives → `import` from `app.js`. Add new columns to `buildColumns()` (factors, pillar sub-scores, `OverallScore`, `Sector`). Update `SUMMARY_COLS`. Add nav links to Top/Stats. Re-point default sort `CombinedScore` → `OverallScore`. | Additive + de-dup. |
| `docs/methodology.html` | Add nav links; add panels documenting the 4-pillar score + new signals. | Additive. |
| `docs/style.css` | Card styles for top.html; stat-block styles for stats.html; `.active` nav for new pages. | Additive. |
| `.github/workflows/screener.yml` | Add date-gated snapshot step **after** the existing commit/push. | One new step. |

### UNCHANGED (deliberately)

- The `Lynch_Lynch_` / `Graham_Graham_` double-prefix keys (surgical-change; see §4).
- `get_finnhub_metrics()` — already fetches the full bundle; only its *consumers* change.
- The min-100-row guard in `write_json()` — stays the single pre-commit quality gate.
- No new API keys / no build step (locked constraints preserved).

---

## 3. Data-Flow Changes (prose)

**Fetch layer.** `get_combined_data()` gains: `fcf` / `fcf_per_share`, `ev_ebit`, `roic`, `roe`, `sector` — all read from the *already-fetched* Finnhub bundle plus yfinance `.info` for sector (Finnhub `finnhubIndustry` as fallback). One genuinely new network call: `get_yf_price_history_5y(ticker)` returning weekly closes → used to derive `low_52w`, `low_5y`, `high_52w`, distances, and `Weeks_Since_*_Low`. This is the heaviest new fetch; cache-friendly (price history changes daily but the *lows* change rarely) — acceptable given the existing 0.25s-throttled sequential loop. Piotroski's 2-yr statements (Phase C) are the heaviest of all and may need their own fetcher `get_finnhub_financials_2y()`.

**Compute layer.** `process_ticker()` stays a conductor. After the existing Lynch/Graham/Defensive blocks it calls, in order:
1. `compute_factor_signals(fund, price)` → FCF yield, earnings yield, EV/EBIT, Magic-Formula rank inputs, shareholder yield, 52w/5y distances + recency. Returns a flat dict → `row.update(...)`.
2. `compute_distress_signals(fund)` → Altman Z (Phase C), Piotroski F (Phase C). Flat dict.
3. `compute_dcf(fund, aaa_yield)` → `DCF_FV`, `DCF_Discount_Pct`, `RevDCF_Implied_g` (Phase C), sector-guarded (returns `None`s for financials).
4. `scoring.compute_overall_score(row)` → reads the now-populated `row`, returns `{OverallScore, Score_Value, Score_Quality, Score_Growth, Score_Safety, Score_Coverage}` + a nested decomposition. `process_ticker` writes the flat pillar scores **and** attaches the nested `scores` object (§4).

**Publish layer.** `run_screener()` sorts by `OverallScore` (fallback `CombinedScore` retained as a column for one milestone of continuity, or dropped — roadmapper's call). `write_json()` unchanged except it now serializes the richer rows including the nested `scores`. Min-100-row guard unchanged.

**Snapshot layer (new).** After the existing commit/push step succeeds, a CI step checks the date (weekly: e.g. `[ "$(date +%u)" = "1" ]` for Mondays) and, if it fires, copies `docs/data/results.json` → `docs/data/snapshots/$(date +%F).json`, then commits/pushes that. The snapshot is a copy of an *already-guarded, already-committed* file, so it inherits the min-100-row safety for free.

---

## 4. JSON Schema Evolution

**Decision: additive, hybrid flat + nested. Do not rename existing keys.**

Current per-row shape (flat): `Ticker, Price, ..., Lynch_Lynch_Status, Graham_Graham_FV, DefensiveScore, CombinedScore, Show, Error, Indexes`.

v2 adds:

```jsonc
{
  // ... all existing flat keys unchanged (incl. double-prefix) ...
  "Sector": "Information Technology",
  "OverallScore": 72.4,
  "Score_Value": 80.1, "Score_Quality": 66.0,
  "Score_Growth": 71.2, "Score_Safety": 59.8,
  "Score_Coverage": 0.92,            // fraction of metrics present
  "FCF_Yield_Pct": 6.3, "EV_EBIT": 11.2, "Earnings_Yield_Pct": 7.1,
  "Dist_52w_Low_Pct": 14.0, "Dist_52w_High_Pct": -22.0,
  "Weeks_Since_52w_Low": 9, "Weeks_Since_5y_Low": 9,
  "Piotroski_F": 7, "Altman_Z": 3.1,        // Phase C
  "DCF_FV": 188.0, "DCF_Discount_Pct": 12.0, "RevDCF_Implied_g": 8.5,  // Phase C
  "scores": {                         // nested decomposition (anti-black-box)
    "value":   { "score": 80.1, "metrics": { "graham_disc": 90, "fcf_yield": 75, "ev_ebit": 70 } },
    "quality": { "score": 66.0, "metrics": { "piotroski": 78, "roic": 60 } },
    "growth":  { "score": 71.2, "metrics": { "eps_g": 71 } },
    "safety":  { "score": 59.8, "metrics": { "altman_z": 65, "dist_52w_low": 55 } }
  }
}
```

**Why flat pillar scores AND a nested `scores` object:** Tabulator sorts/filters cleanly on flat top-level fields (`OverallScore`, `Score_Value`), so the table and top.html use those. The nested `scores` object carries the per-metric decomposition that the Top page tooltips / stats page consume without polluting the flat column space (Tabulator can read `scores.value.score` via dot-notation `field` but cannot easily *header-filter* nested fields — hence both). This keeps `buildColumns()` additive: new flat columns slot in, the nested object is read only where decomposition is shown.

**Double-prefix: leave it.** Renaming `Lynch_Lynch_Status` → `Lynch_Status` would touch `SIGNAL_COLORS` keys, `buildColumns` fields, `SUMMARY_COLS`, the `methodology.html` `<code>` references, and the Python `row.update` prefix — a cross-cutting rename with real regression surface and **zero user-visible benefit**. New keys are added clean (no double-prefix) so the wart does not propagate. (If cosmetic cleanup is ever wanted, it is a standalone "rename pass" with its own verification, not bundled into v2.)

---

## 5. Frontend Code-Sharing Decision

**Decision: introduce `docs/app.js` (one shared file), keep per-page wiring inline. Still no build step.**

v1.0 deliberately kept all JS inline because there was *one* page with logic. v2 adds two more pages that need the **same** fetch+cache-bust, the same `numFmt`/`pctFmt`/`makeSignalFormatter`, the same `SIGNAL_COLORS`/`COLOR_STYLES`, and the same `updateFreshnessUI`. Triplicating ~120 lines of identical formatter/color code across `index.html`, `top.html`, `stats.html` is *more* complex and more error-prone than a single `<script src="app.js">` loaded before each page's small inline block.

This honors the constraints: `app.js` is a plain static file served by Pages — **no npm, no bundler, no build step** (same posture as the Tabulator CDN `<script>`). It is not a framework; it is shared vanilla functions on a global namespace (e.g. `window.Screener = {...}`), matching the project's "vanilla JS" stack.

What stays inline per page:
- `index.html`: `buildColumns()`, `SUMMARY_COLS`, preset toggles, ticker search — table-specific, not reused.
- `top.html`: sort+slice, N-toggle, card render — page-specific.
- `stats.html`: aggregate computation, chart/stat-block render — page-specific.

Build order note: `app.js` should be extracted **first** in the page-work phase (refactor index.html to consume it with zero behavior change), then top.html/stats.html are built *on top of* it rather than copy-pasting.

---

## 6. Snapshot + Sector Placement

**Snapshot — in the Actions workflow, not Python.** Rationale: the screener's job is "produce a guarded results.json"; archiving copies of it for histor  trend work is a repo/CI concern. Placing it in CI keeps Python free of date/calendar logic and keeps the min-100-row guard as the *single* gate — the snapshot copies a file that has already passed that gate and already been committed. Mechanics:
- New step **after** the existing commit/push in `.github/workflows/screener.yml`.
- Date gate for weekly cadence (locked: weekly/monthly, NOT daily), e.g. run only on Mondays.
- `cp docs/data/results.json docs/data/snapshots/$(date +%F).json`, then `git add docs/data/snapshots/`, commit, push.
- **`.gitignore` gotcha:** the repo ignores `*.json` with explicit exceptions. `snapshots/*.json` are NOT covered by `!docs/data/results.json`. Add `!docs/data/snapshots/*.json` (or `!docs/data/snapshots/`) to `.gitignore` — without it, every snapshot is silently ignored and never committed. This is the single highest-risk wiring detail of the snapshot work.

**GICS sector — fetched in `get_combined_data()`, threaded as `row["Sector"]`.** Source: yfinance `Ticker.info["sector"]` (GICS-aligned sector string) with Finnhub `finnhubIndustry` as fallback. It is a per-ticker fundamental, so it belongs alongside the existing per-ticker fetches, surfaced into the unified `fund` dict, written to `row["Sector"]` in `process_ticker()`. Consumers: `compute_dcf()` (skip financials), `scoring.py` sector guards (e.g. don't penalize banks on current-ratio), and `stats.html` sector breakdown. Note `.info` is a heavier yfinance call than `fast_info`; fetch it once per ticker inside the existing `get_yf_*` path rather than adding a separate round-trip.

---

## 7. Dependency-Ordered Build Sequence

The quality gate requires: **bug fix → score → factors → DCF/pages.** Concrete ordering:

**Phase A (first milestone — locked scope: score foundation + Top page):**
1. **Fix the Buy Price bug** in `lynch_metrics()`. Verify against a known ticker before proceeding — everything downstream reuses `Lynch_Discount_Pct`. *(blocker for all scoring)*
2. **Create `scoring.py`** with the 4-pillar composite using *only metrics that already exist* (Graham disc, Lynch disc, defensive score, growth g). Add `SCORE_THRESHOLDS`/`PILLAR_WEIGHTS` config. Unit-checkable in isolation (no network).
3. **Wire into `process_ticker()`**: replace `CombinedScore` line with `scoring.compute_overall_score(row)`; write flat pillar scores + nested `scores`. Re-point `run_screener()` sort to `OverallScore`. Extend JSON schema (additive).
4. **Extract `docs/app.js`** from `index.html` (behavior-preserving refactor); add new score columns to `buildColumns()`/`SUMMARY_COLS`; default sort → `OverallScore`.
5. **Build `docs/top.html`** on `app.js`; add nav links across pages.

**Phase B (cheap high-evidence factors — mostly already in Finnhub bundle):**
6. Add `get_yf_price_history_5y()` + `Sector` to `get_combined_data()`.
7. `compute_factor_signals()` (FCF yield, EV/EBIT, earnings yield, Magic-Formula inputs, shareholder yield, 52w/5y distance + recency). Feed these into the relevant pillars in `scoring.py`.
8. Surface new factor columns in `index.html`/`top.html`.

**Phase C (heavier signals + remaining pages + snapshots):**
9. `compute_distress_signals()` — Piotroski F (needs `get_finnhub_financials_2y()`), Altman Z. Feed QUALITY/SAFETY pillars.
10. `compute_dcf()` — forward + reverse DCF, sector-guarded.
11. `docs/stats.html` on `app.js`.
12. Snapshot CI step + `.gitignore` exception.

**Phase D (deferred):** backtest harness — out of scope this milestone.

**Why this order holds:** every step depends only on earlier ones. Scoring (step 2) needs the bug fix (1). Factors (7) feed pillars defined in (2). DCF (10) needs the sector field (6). Pages (4,5,11) need `app.js` (4) and the schema (3). Snapshots (12) need a finalized schema so archived files are comparable. The single cross-phase trap is the `.gitignore` snapshot exception — call it out explicitly in the Phase C plan.

---

## 8. Anti-Patterns to Avoid

| Anti-pattern | Why bad here | Instead |
|---|---|---|
| Inlining the composite into `process_ticker()` | Turns a 1200-line file's conductor into a god-function; the threshold/winsorize config has nowhere clean to live. | `scoring.py` module. |
| Renaming the double-prefix keys "while we're in there" | Cross-cutting change across Python + 3 HTML files, pure regression risk, no user benefit. Violates surgical-change. | Add new keys clean; leave old wart. |
| A second new JSON file for scores or snapshots | `.gitignore *.json` will silently ignore it; the `results.json` exception is per-path. | Extend `results.json` (additive); snapshots need an explicit new `.gitignore` exception. |
| Copy-pasting formatters into top.html/stats.html | Triplicated drift; a color tweak now means 3 edits. | `docs/app.js` shared primitives. |
| Snapshotting inside Python | Mixes calendar/CI concerns into the screener; bypasses the clean "one gate, then commit" flow. | CI step after commit/push. |
| Doing DCF before the sector field exists | DCF is meaningless/dangerous for financials; needs the sector guard. | Sector (Phase B) precedes DCF (Phase C). |

---

## 9. Confidence & Gaps

**HIGH confidence** on every integration point — they are read directly from `stock_screener.py`, `docs/index.html`, `.github/workflows/screener.yml`, and the locked decisions doc. Function names, line anchors, and the double-prefix mechanism are verified in source.

**Gaps for phase-specific research (flag to roadmapper):**
- **Finnhub free-tier field coverage**: confirm `freeCashFlowAnnual`, `ev/ebitda` (or EV/EBIT inputs), `roicAnnual`, `roeAnnual` are actually populated on the free tier for the full universe before the scoring math depends on them. (Methodology doc assumes "much already in the bundle" — verify in Phase B planning.)
- **Piotroski data source**: 2-yr statements on Finnhub free tier vs. yfinance financials — the heaviest fetch; pick the source during Phase C research.
- **Exact Buy Price bug root cause**: deferred in STATE.md as "visibly wrong across all tickers"; needs its own debug pass (the fix is step A1, but the *diagnosis* is not in this research's scope).
- **Threshold calibration**: absolute thresholds are "set by judgment" (no backtest); expect tuning iterations — keep them as loud config constants.
