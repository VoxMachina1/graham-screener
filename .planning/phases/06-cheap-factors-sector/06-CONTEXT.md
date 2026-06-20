# Phase 6: Cheap Factors + Sector - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Thread a per-ticker GICS `Sector` field through every row (a prerequisite for Phase 7's
DCF/distress/applicability guards), and add the high-evidence factors that mostly already
live in the fetched Finnhub `metric=all` bundle — 52w/5y distance + recency, FCF yield,
EV/EBIT + earnings yield, ROIC, shareholder yield — folding them into the Phase 5 4-pillar
composite via the existing threshold engine.

**In scope:** SECTOR-01, SIGNAL-01..07.
**Out of scope (Phase 7):** Piotroski/Altman (TRAP-03), forward+reverse DCF, the per-metric
sector applicability matrix (SECTOR-02), `stats.html`, snapshots, the 30-day fundamentals
cache (DATA-03), methodology refresh. Phase 6 only *adds* the `Sector` field; it does not
yet *gate* on it.
</domain>

<decisions>
## Implementation Decisions

### Factor data sourcing (SIGNAL-04/05/06/07)
- **D-01 — Finnhub bundle + targeted yfinance fallback.** Use Finnhub `metric=all` fields
  where present (EV/EBIT, earnings yield, ROIC, shareholder-yield inputs) with per-field
  coverage flags; **add a yfinance cashflow-statement fallback for FCF** (operating cash
  flow − capex), because the assumed Finnhub field (`freeCashFlowPerShareTTM/Annual`) is
  **empirically confirmed absent on the free tier** (5.1 live run: Safety capped at 45 = ¾
  trap coverage). Research must measure per-field coverage across the universe and add a
  yfinance/statement fallback for **any** field it finds sparse (not just FCF). Residual
  gaps flow through the Phase 5 average-over-present + coverage-flag contract (D-01b).
  FCF yield = FCF / market cap.

### Sector (SECTOR-01)
- **D-02 — yfinance `.info['sector']` (GICS-like).** Accuracy matters because Phase 7's
  financials/cyclicals guards key off it. Accept the heavier per-ticker `.info` call
  (sector changes rarely → cache-friendly; Phase 7's DATA-03 cache amortizes it). Thread it
  as a `Sector` string column on every row. Phase 6 only *adds* the field — no gating yet.

### Price-history signals (SIGNAL-01/02/03)
- **D-03 — One yfinance 5-year *weekly* history fetch** per ticker (~260 points, light vs a
  daily ~1260). From it compute: distance below 52-week high (%), distance above 52-week low
  (%), distance above 5-year low (%), and weeks-since-52w-low / weeks-since-5y-low recency.
- **D-04 — Distance/recency signals live in the VALUE pillar, NOT Safety (USER OVERRIDE of
  the research's Safety placement).** Rationale (user, verbatim intent): the universe is
  ~500 of the largest global companies, so "near a low" reads as **contrarian cheapness**, a
  value signal — any genuinely distressing condition (leverage, negative EPS/FCF, illiquidity)
  is caught elsewhere (the interim trap gate / Safety inputs). **Drop** the
  "52w-high-proximity-as-value-trap-flag" framing from the research. Recency modulates the
  contrarian read within Value (a very recent low = still falling = less attractive than an
  older, basing low) — keep distance + recency together in Value.

### Folding into the 4-pillar composite (SIGNAL-* + SCORE-07)
- **D-05 — Research pillar map, with the D-04 override; group Value cheapness; monitor, don't
  pre-tune.**
  - **VALUE** gains, as **distinct averaged sub-groups** (SCORE-07 — so cheapness is not
    multi-counted into one inflated rank):
    1. valuation-discount (existing Lynch/Graham discounts),
    2. cash/earnings-yield cheapness (FCF yield, EV/EBIT → earnings yield EBIT/EV),
    3. price-position (distance-from-52w-low, distance-above-5y-low, distance-below-52w-high + recency, per D-04).
  - **QUALITY** gains **ROIC** (absolute input, NOT the Greenblatt rank-sum — SIGNAL-06).
  - **GROWTH** unchanged (g + growth stability).
  - **SAFETY** unchanged in Phase 6 — remains the interim trap gate; Phase 7 upgrades it
    (Altman/Piotroski, TRAP-03).
  - Keep the Phase 5 pillar weights (~35/30/20/15). The new Value/Quality factors are
    expected to **dilute the growth-dominance** observed in the 5.1 run. **Do not pre-tune**
    weights/thresholds — add the factors, then observe the live distribution (loud config
    constants; tuning is a monitored Phase 7 activity via `stats.html`).
  - Every new metric is winsorized/clamped as it is added (Phase 5 contract) and routes
    negatives to worst-possible sub-scores (D-01 carryover).

### Claude's Discretion
- **Shareholder yield (SIGNAL-07)** placement defaults to a VALUE capital-return input
  (with a low-coverage flag where share-count/buyback data is sparse); planner may place it
  in Quality (capital-allocation discipline) if research argues better fit.
- Exact band thresholds for each new factor (loud, tunable config constants per D-02b from
  Phase 5); starting values at researcher/planner discretion, flagged as `[ASSUMED]`.
- Whether `.info` sector and the 5y history fetch share a single yfinance `Ticker` object
  per ticker to minimize calls — an implementation optimization left to the planner.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` (Phase 6 section) — goal, success criteria, requirement list
- `.planning/REQUIREMENTS.md` — SECTOR-01, SIGNAL-01..07 (and SECTOR-02 / TRAP-03 / DCF-* for
  the Phase 7 trajectory these factors feed)

### Methodology & prior-phase contracts
- `.planning/research/v2-METHODOLOGY-EXPANSION.md` — new-signal evidence tiers, the 4-pillar
  design, and the "mostly already in the Finnhub bundle" sourcing claim (now qualified by D-01)
- `.planning/phases/05-score-foundation-public-top-n/05-CONTEXT.md` — the Phase 5 scoring
  contract these factors fold into (absolute thresholds, winsorization, average-over-present,
  D-01 negative-routing, SCORE-07 grouping)
- `.planning/phases/05-score-foundation-public-top-n/05.1-FIXES-SUMMARY.md` — the empirical
  basis for D-01: FCF field absent on the free tier; growth-window/coverage realities
- `.planning/STATE.md` — Blockers/Concerns: "Finnhub free-tier field coverage unconfirmed —
  validate coverage in Phase 6 before scoring math depends on these fields"

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_finnhub_metrics()` (stock_screener.py ~565) already fetches the full `metric=all`
  bundle (`fh` dict) — EV/EBIT, ROIC, shareholder-yield inputs are read from it (coverage-flagged).
- `get_yf_price_and_history()` (~593) already builds a yfinance `Ticker`; extend it for the
  5y weekly history (`t.history(period="5y", interval="1wk")`) and the `.info['sector']` read,
  reusing one `Ticker` object per ticker (D-05 discretion).
- `get_combined_data()` (~640) is where the new fields (`sector`, `fcf_yield`, `ev_ebit`,
  `earnings_yield`, `roic`, `shareholder_yield`, `dist_52w_low`, `dist_5y_low`,
  `dist_52w_high`, `weeks_since_52w_low`, `weeks_since_5y_low`) join the unified dict.
- The Phase 5 scoring engine — `_piecewise_score`, `_winsorize`, `_avg_present`,
  `overall_score()` (~283), and the `SCORE_*`/`PILLAR_WEIGHTS` config block (~82-180) — is
  the extension point: add band constants + new sub-score inputs, keeping the pillar-weight
  and average-over-present contract.

### Established Patterns
- `compute_growth_5yr_cagr()` / `_reconcile_growth()` / `_eps_stable_for_gate()` show the
  pure-helper + vanilla-assert-test pattern (tests/test_scoring.py, test_growth_trap_fixes.py)
  to mirror for new factor helpers.
- `process_ticker()` assembles the row dict + calls `overall_score()`; `write_json()` emits
  flat columns + the nested `scores` object — both get the new fields additively.
- FCF fallback mirrors the existing yfinance-statement reads in `get_yf_price_and_history`.

### Integration Points
- Sector + new factors are additive columns (no breaking of the existing flat/nested schema).
- New per-ticker I/O (5y weekly history + `.info`) adds runtime across ~550 tickers — watch
  rate limits; a real cache is Phase 7 (DATA-03), but keep fetches minimal (one Ticker object).

</code_context>

<specifics>
## Specific Ideas

- **User override (verbatim intent):** distance-from-low is a *value* signal for a mega-cap
  universe — "Any other distressing issues besides just being down will show up elsewhere."
- FCF must be sourced reliably (yfinance fallback) — the Finnhub field is confirmed dead.

</specifics>

<deferred>
## Deferred Ideas

- Per-metric **sector applicability matrix** (SECTOR-02) — Phase 7. Phase 6 adds the `Sector`
  field but does not gate signals on it yet.
- Piotroski F / Altman Z replacing the interim trap gate (TRAP-03), forward+reverse DCF — Phase 7.
- 30-day fundamentals **cache** (DATA-03) to bound the added I/O — Phase 7.
- Threshold/weight **re-tuning** to counter growth-dominance — deferred to monitored tuning
  once the new factors' live distribution is observable (Phase 7 `stats.html`).

</deferred>

---

*Phase: 6-Cheap Factors + Sector*
*Context gathered: 2026-06-20*
