# Phase 6: Cheap Factors + Sector - Discussion Log

> **Audit trail only.** Decisions are captured in CONTEXT.md.

**Date:** 2026-06-20
**Phase:** 6-Cheap Factors + Sector
**Areas discussed:** Factor data sourcing, GICS sector source, Price-history fetch + placement, Composite fold

---

## Factor data sourcing
| Option | Selected |
|--------|----------|
| Finnhub bundle + targeted yfinance fallback (FCF from op-CF − capex) | ✓ |
| Finnhub-only + coverage flag | |
| Compute all from yfinance statements | |

**Notes:** FCF empirically confirmed absent on Finnhub free tier (5.1 run). Research measures per-field coverage and adds fallbacks where sparse. → D-01.

## GICS sector source
| Option | Selected |
|--------|----------|
| yfinance .info['sector'] (GICS-like) | ✓ |
| Finnhub finnhubIndustry | |

**Notes:** Accuracy matters for Phase 7 guards; accept heavier call, cache-friendly. → D-02.

## Price-history fetch + pillar placement
| Option | Selected |
|--------|----------|
| Weekly 5y → Safety | |
| Daily 5y → Safety | |
| Weekly, distance → Value | ✓ (user override) |

**User's choice:** Weekly 5y history; distance/recency → **Value** pillar, not Safety.
**Notes (verbatim):** "I still don't think this inherently belongs in the safety pillar. We're screening for basically the 500-ish largest companies in the world. Any other distressing issues besides just being down will show up elsewhere." → D-03, D-04. Dropped the 52w-high-proximity-as-trap-flag framing.

## Composite fold
| Option | Selected |
|--------|----------|
| Research map + group cheapness, monitor (no pre-tune) | ✓ |
| Add factors + re-tune weights now | |

**Notes:** Value sub-grouped (discount / yield-cheapness / price-position) per SCORE-07; Quality += ROIC; Safety unchanged (Phase 7 upgrades it); keep ~35/30/20/15; new factors dilute growth-dominance; monitor live distribution before tuning. → D-05.

## Claude's Discretion
- Shareholder yield default placement = Value (capital-return), low-coverage flagged; planner may move to Quality.
- New factor band thresholds = loud tunable [ASSUMED] constants.
- Share one yfinance Ticker object per ticker for sector + history.

## Deferred Ideas
- Sector applicability matrix (SECTOR-02), Piotroski/Altman/DCF, DATA-03 cache, threshold re-tuning — Phase 7.
