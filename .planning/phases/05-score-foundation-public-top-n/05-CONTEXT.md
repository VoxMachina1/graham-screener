# Phase 5: Score Foundation + Public Top-N - Context

**Gathered:** 2026-06-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the price-only `CombinedScore` with a 4-pillar absolute `OverallScore`
(0–100, Value/Quality/Growth/Safety), built **entirely from metrics that already
exist** (no new data fetches), on a corrected hand-verified Buy Price, behind an
interim value-trap gate — and ship `docs/top.html` (Top 10/25) with a shared
`docs/app.js` and updated site nav.

**In scope:** FIX-01/02 (Buy Price audit + fixture), SCORE-01..08 (composite
engine, absolute thresholds, winsorization, missing-data rule, pillar
decomposition in JSON+UI, config constants, correlated-Value grouping, sort-key
swap), TRAP-01/02 (interim trap gate + badge), PAGE-01/03/04 (top.html, shared
app.js, nav).

**Out of scope (later phases):** new fetched signals — 52w/5y distance, FCF
yield as a graded factor, EV/EBIT, ROIC, shareholder yield (Phase 6); Piotroski,
Altman, DCF, sector applicability matrix, stats.html, snapshots (Phase 7). GICS
sector field (Phase 6). Backtest harness (deferred beyond v2.0).

</domain>

<decisions>
## Implementation Decisions

### Missing / invalid input handling (cross-cutting — overrides naive SCORE-04 reading)
- **D-01 — Negative / calculation-breaking inputs → worst-possible sub-score, never a failure.**
  Where a present value is negative in a way that would otherwise abort a
  calculation (negative EPS breaking PE/PEG, non-positive growth `g`, negative
  book value, negative FCF, etc.), the stock is **not** dropped and **not** treated
  as "missing." It receives the **worst possible sub-score** for that metric so it
  still ranks but stands out as a terrible choice.
- **D-01b — Truly absent data (null) still follows SCORE-04:** average over
  *present* metrics within the pillar + per-row coverage flag; a missing **Safety**
  input is treated as "unknown," never "safe." Negative-but-present (D-01) is
  floored to terrible; genuinely missing is averaged-over-present. These are two
  different paths — do not conflate them.

### Composite scoring (SCORE-01..08)
- **D-02 — Interim pillar weights:** keep the research's target **~35/30/20/15**
  (Value/Quality/Growth/Safety). Each pillar sub-score = average of whatever
  sub-scores exist now (avg-over-present); pillars deepen as Phase 6/7 factors land.
  No interim re-weighting churn between phases.
- **Phase 5 pillar inputs (existing metrics only) — guidance for planner/researcher:**
  - **VALUE:** `Lynch_Discount_Pct` + `Graham_Discount_Pct`. These are correlated
    (both price-discount) — per SCORE-07, **group them as one "discount" sub-factor**
    (averaged) so the Value pillar is not double-counted cheapness. Phase 6's
    FCF-yield / EV-EBIT / earnings-yield become a second, distinct Value sub-group.
  - **QUALITY:** Graham `DefensiveScore` (0–8), `debt/equity`, `current ratio`.
  - **GROWTH:** growth `g` (already `GROWTH_CAP`-capped at 25%), plus a growth-stability
    measure derived from the existing yfinance `annual_eps` history.
  - **SAFETY:** driven by the interim trap gate (D-03). Missing Safety input = unknown,
    never safe (D-01b).
  - **Intentional double-use:** `debt/equity` and `current ratio` inform both the
    graded **Quality** sub-scores and the **Safety** trap gate (at distress
    thresholds). This is deliberate, not a bug — document it so it isn't "cleaned up."
- **D-02b — Thresholds & weights as loud config constants:** all pillar weights,
  piecewise-linear band thresholds, and winsorization bounds live as version-controlled
  constants in the existing `LYNCH_*`/`GRAHAM_*` style block(s). Yield-based thresholds
  are rate-relativized to the live FRED AAA yield (already fetched). Thresholds have
  **no empirical anchor yet** (no backtest) — keep them loud and tunable; their
  distribution gets monitored in `stats.html` (Phase 7).
- **D-02c — Sort key swap (SCORE-08):** `OverallScore` replaces `CombinedScore` as
  the primary descending sort in `run_screener`. Keep `CombinedScore` as a retained
  column (additive schema) for now.

### Value-trap gate (TRAP-01/02)
- **D-03 — Safety-pillar penalty + visible badge.** A tripped interim gate **floors
  the Safety sub-score** (worst-possible, consistent with D-01), which sinks
  `OverallScore` so traps rarely top the public list — satisfying "caught before it
  can top a public list." The row is **still shown** (on dashboard and, if it still
  ranks, on top.html) carrying a visible **trap badge**. Not a hard-exclude.
- **D-04 — Interim gate inputs:** `debt/equity`, `current ratio`, EPS stability
  (reuse the defensive checklist's `EPS_Stability` logic), and **negative FCF**.
  - **FCF source:** read FCF from the **Finnhub `metric=all` bundle we already fetch
    and currently discard** — this is **not a new data fetch** (honors the Phase 5
    no-new-fetch constraint). Negative FCF trips the gate **and** scores worst (D-01).
    Where FCF is absent in the bundle, coverage-flag the row and run the gate on the
    other three inputs (D-01b). Graded FCF-*yield* as a positive Value factor is still
    Phase 6 (SIGNAL-04) — Phase 5 only consumes the FCF *sign* for the gate.

### Buy Price correctness (FIX-01/02)
- **D-05 — Full formula audit + KO fixture.** Diagnose the root cause of the deferred
  "Buy Price visibly wrong across all tickers" bug, then audit **every** Lynch/Graham
  formula against source definitions (Lynch PEG/PEGY/buy price, Graham VA/VB/FV,
  combined score) — not just the discount denominators. Add a committed spot-check
  **fixture for KO** (Coca-Cola: large, stable dividend payer, easy to hand-verify).
  `Lynch_Discount_Pct` / `Graham_Discount_Pct` must read sane **before** any pillar
  consumes them (FIX-02 is a hard gate ahead of the composite).

### Claude's Discretion
- **Stats nav link (PAGE-04 nuance):** PAGE-04 lists Dashboard/Top Picks/Stats/Methodology,
  but `stats.html` does not exist until Phase 7 — a live link would 404. Recommended:
  Phase 5 ships nav = **Dashboard, Top Picks, Methodology**, and Phase 7 adds the Stats
  entry when the page lands. Build the shared nav in `app.js` so adding the 4th entry
  later is a one-line change. Planner may override if a placeholder Stats page is preferred.
- Exact winsorization bounds, band breakpoints, and the growth-stability formula are
  Claude's discretion (subject to D-02b: loud, tunable constants).
- `top.html` presentation (cards vs compact table) — the mockup approved 2026-06-17 is
  the contract; minor layout details at discretion within that mockup.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` (Phase 5 section) — goal, 5 success criteria, requirement list
- `.planning/REQUIREMENTS.md` — FIX-01/02, SCORE-01..08, TRAP-01/02, PAGE-01/03/04
  (and TRAP-03 / SIGNAL-04 for the cross-phase trajectory the interim gate feeds into)

### Locked methodology & design decisions
- `.planning/research/v2-METHODOLOGY-EXPANSION.md` — Locked Decisions table; the
  4-pillar absolute scoring design (§Scoring metric design); top.html mockup
  **approved 2026-06-17** (§Technical / dashboard)
- `.planning/STATE.md` — Blockers/Concerns (Buy Price root cause; Finnhub free-tier
  field coverage; absolute-threshold calibration has no empirical anchor) and the
  FIX-01 deferred-bug entry (scheduled Phase 5)

### Codebase conventions
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONVENTIONS.md`,
  `.planning/codebase/STRUCTURE.md` — single-file pipeline conventions, naming

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/index.html` inline `<script>` (≈ lines 70–270): `SIGNAL_COLORS` map (line 80),
  cache-busted `fetch("data/results.json?v="+Date.now())` (line 265), freshness-badge
  + stale-banner logic, em-dash null formatter, color formatter. **PAGE-03:** extract
  these into `docs/app.js` and reuse on `top.html` (and back-port into `index.html`).
- `docs/style.css` — Nord theme overrides, `.main-nav`/`.nav-link` styles (reuse for
  top.html nav; nav markup at `index.html:29–32`).
- `stock_screener.py` config-constant blocks (`LYNCH_*` lines 59–73, `GRAHAM_*`
  41–70, `GROWTH_CAP` 40) — add `SCORE_*` / pillar-weight / band-threshold constants
  in the same loud, version-controlled style.

### Established Patterns
- `process_ticker()` (line 544) assembles each row dict and is where new pillar columns
  + nested `scores` object originate. `lynch_metrics` (341), `graham_metrics` (420),
  `graham_defensive_score` (461), `combined_score` (528) are the formula sites the
  FIX-01 audit must cover.
- `run_screener()` sorts by `CombinedScore` desc (lines 648–650) → switch to `OverallScore`.
- `write_json()` (line 661) currently serializes a flat DataFrame → JSON. **SCORE-05**
  needs a nested `scores` object alongside flat pillar columns — `write_json` (or row
  assembly) must build that nested structure.

### Integration Points
- `get_finnhub_metrics()` (188) / `get_combined_data()` (250) fetch the Finnhub bundle;
  the discarded `metric=all` fields are where the interim gate's FCF sign comes from
  (D-04) — no new request, just stop discarding.
- Existing negative-input guards that currently `return {"error": ...}`
  (`lynch_metrics:348`, `graham_metrics:428`) must change behavior under D-01:
  instead of erroring the stock out, route to worst-possible sub-scores.

</code_context>

<specifics>
## Specific Ideas

- **User philosophy (verbatim intent):** negative / calculation-breaking values should
  "stand out as terrible choices" — never silently fail or get neutral treatment.
- **Fixture ticker:** KO (Coca-Cola) for the hand-verified Buy Price spot-check.
- **top.html:** the layout mockup approved 2026-06-17 is the design contract.

</specifics>

<deferred>
## Deferred Ideas

- Graded **FCF yield** as a positive Value factor — Phase 6 (SIGNAL-04). Phase 5 uses
  only the FCF *sign* for the trap gate.
- 52w/5y distance + recency, EV/EBIT + earnings yield, ROIC, shareholder yield — Phase 6.
- Piotroski F, Altman Z (upgrade the interim gate → real Safety driver, TRAP-03),
  forward + reverse DCF, sector applicability matrix, `stats.html`, historic snapshots,
  fundamentals cache, methodology refresh — Phase 7.
- **Stats nav link** — recommended for Phase 7 when `stats.html` exists (see Claude's
  Discretion above).
- Backtest harness — deferred beyond v2.0.

</deferred>

---

*Phase: 5-Score Foundation + Public Top-N*
*Context gathered: 2026-06-18*
