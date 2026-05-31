# Phase 4: Google & Tiingo Cleanup - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-31
**Phase:** 04-google-tiingo-cleanup
**Areas discussed:** Sleep call in process_ticker(), Scope of STEP 6 removal, BRK-B non-standard ticker bug

---

## Sleep Call in process_ticker()

| Option | Description | Selected |
|--------|-------------|----------|
| Remove it entirely | Tiingo is never used — the sleep has no purpose and costs ~2 min per run. yfinance and Finnhub have their own retry/backoff logic. Remove the sleep and the time import if it becomes unused. | ✓ |
| Keep as a general throttle | Rename to API_DELAY_SEC = 0.25 and keep the sleep to avoid hammering yfinance/Finnhub across 550 tickers. Slower but safer if rate limits are a concern. | |
| Remove sleep, keep time import | Remove just the time.sleep call but leave the time import in case it's used elsewhere. | |

**User's choice:** Remove it entirely
**Notes:** `import time` has no other usages in the file (verified: only appears on line 22 and is used only at line 563). Both the sleep call and the import are removed.

---

## Scope of STEP 6 Removal

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, remove all of STEP 6 | SIGNAL_COLORS, DOCS_CONTENT, and _col_letter() have no callers once push_to_gsheets and helpers are gone. The frontend has its own implementations. Remove the entire STEP 6 block cleanly. | ✓ |
| Keep SIGNAL_COLORS only | It's useful documentation of what colors mean which signals — keep it as a reference comment even without callers. | |

**User's choice:** Yes, remove all of STEP 6
**Notes:** CLN-01 explicitly listed push_to_gsheets + 3 helpers. User confirmed SIGNAL_COLORS and DOCS_CONTENT (not listed in CLN-01) should also be removed since they're only used by the removed Google Sheets code. Frontend already has its own color logic; methodology.html is live.

---

## BRK-B Non-Standard Ticker Bug

### Q1: Fold into Phase 4?

| Option | Description | Selected |
|--------|-------------|----------|
| Fix it in Phase 4 (alongside cleanup) | Phase 4 already edits stock_screener.py — folding in a BRK-B ticker fix is natural. | ✓ |
| Note it as a separate bug fix | Keep Phase 4 purely as CLN-01/02/03/04. Create a tracked bug to fix BRK-B independently. | |

**User's choice:** Fix it in Phase 4

### Q2: What's wrong with BRK-B?

**User's choice (freeform):** "All of the data, the numbers and everything, are either being pulled as or scaled to the size of BRK-A. The entire process for non-standard tickers needs to be gone over."
**Notes:** Not just the growth rate — all BRK-B metrics appear to be in Class A scale. Investigation needed before scoping fixes. Key known issue found during codebase scan: GROWTH_CAP = 25.0 is only applied inside compute_growth_5yr_cagr() (the fallback path) but not applied to Finnhub's directly-returned growth_pct. Finnhub reports ~1179% 5Y growth for BRK-B, causing Lynch buy price of $20,498 for a $474 stock.

### Q3: Fix breadth

| Option | Description | Selected |
|--------|-------------|----------|
| BRK-B only — targeted fix | Audit all fields for BRK-B specifically and apply correct /1500 scaling wherever needed. | |
| Build a general mechanism | Add a share_class_ratio config and apply scaling systematically. | |

**User's choice (freeform):** "Audit any code related to handling non-standard tickers. Let's handle the scaling as a separate issue."
**Notes:** The /1500 share_class_ratio scaling mechanism is out of scope for Phase 4. Phase 4 audits and fixes clearly broken logic only.

### Q4: Audit-only vs. fix

| Option | Description | Selected |
|--------|-------------|----------|
| Audit + fix what's clearly broken | Fix obvious issues found (e.g., missing GROWTH_CAP application) alongside the audit. | ✓ |
| Audit only — document findings | Leave all fixes to a dedicated Phase 5 once the full picture is clear. | |

**User's choice:** Audit + fix what's clearly broken

---

## Claude's Discretion

- None — all decisions were made explicitly by the user or have clear deterministic outcomes.

## Deferred Ideas

- **Column header auto-sizing** — user flagged that column header labels are being clipped in the dashboard. Already in v2 deferred backlog; not Phase 4 scope.
- **General share_class_ratio scaling mechanism** — user wants a systematic solution for non-standard tickers (BRK-B and future ADRs/class-B shares). Explicitly deferred from Phase 4; handle as follow-up after audit findings clarify the full scope.
