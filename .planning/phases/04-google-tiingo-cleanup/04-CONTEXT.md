# Phase 4: Google & Tiingo Cleanup - Context

**Gathered:** 2026-05-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove all Google Sheets output code, dependencies, credentials, and dead Tiingo config from the codebase. Audit non-standard ticker handling in the data pipeline and fix clearly broken cases (notably BRK-B). The dashboard is confirmed live (Phase 3 complete) — the Google Sheets safety net is no longer needed.

</domain>

<decisions>
## Implementation Decisions

### STEP 6 Removal Scope (CLN-01)
- **D-01:** Remove the **entire STEP 6 block** from `stock_screener.py`, not just the explicitly listed helpers. This includes:
  - `push_to_gsheets()` (the main function)
  - `_apply_color_coding(ws, df_clean)` (private helper)
  - `_write_docs_tab(sh)` (private helper)
  - `_write_markdown_tab(sh, df)` (private helper)
  - `_col_letter(n)` (private helper — orphaned by removing `_apply_color_coding`)
  - `SIGNAL_COLORS` constant dict (orphaned — frontend has its own JS color logic)
  - `DOCS_CONTENT` constant list (orphaned — `methodology.html` is built and live)
  - The `# ═══ STEP 6 — PUSH TO GOOGLE SHEETS ═══` section header comment
- **D-02:** All three Google imports (lines 31–33) are removed:
  - `import gspread`
  - `from google.oauth2.service_account import Credentials`
  - `from google.oauth2 import service_account`

### Google Config Removal (CLN-02, CLN-03)
- **D-03:** Remove from `stock_screener.py` CONFIGURATION block:
  - `GSHEET_CREDS_JSON`, `GSHEET_SPREADSHEET`, `GSHEET_WORKSHEET` constants (lines 51–56) and their comments
- **D-04:** Remove from `screener.yml`:
  - `GSHEET_CREDS_JSON`, `GSHEET_SPREADSHEET`, `GSHEET_WORKSHEET` env var entries
- **D-05:** Remove `gspread>=6.0.0` and `google-auth>=2.28.0` from `requirements.txt`

### Tiingo Dead Config Removal (CLN-04)
- **D-06:** Remove from `stock_screener.py`:
  - `TIINGO_API_KEYS` constant and its block comment (lines 41–46)
  - `TIINGO_DELAY_SEC = 0.25` constant (line 63) and its comment
  - `time.sleep(TIINGO_DELAY_SEC)` call (line 563, inside `process_ticker()`)
  - `import time` (line 22) — no other usages remain after removing the sleep call
- **D-07:** Remove from `screener.yml`:
  - `TIINGO_API_KEYS` env var entry

### Sleep Call Behavior
- **D-08:** Remove the 0.25s sleep **entirely** — no replacement, no renamed constant. The sleep was labeled as a Tiingo rate-limiter; yfinance and Finnhub have their own retry/backoff logic. Removing it saves ~138 seconds per run (~550 tickers × 0.25s).

### Non-Standard Ticker Audit + Fix (BRK-B)
- **D-09:** Audit all code that handles non-standard tickers (BRK-B / BRK.B) in `process_ticker()`, `get_combined_data()`, and `compute_growth_5yr_cagr()`.
- **D-10:** Fix clearly broken cases. Known issue: `GROWTH_CAP = 25.0` is applied inside `compute_growth_5yr_cagr()` but **not** when Finnhub returns `growth_pct` directly (line 595 path). Finnhub reports ~1179% 5Y growth for BRK-B (likely computed on Class A EPS basis), which flows uncapped into Lynch scoring — producing a $20,000 buy price for a $474 stock.
- **D-11:** The general `/1500 share_class_ratio scaling mechanism` is **out of scope** for Phase 4. Handle it as a separate follow-up. Phase 4 fixes only clearly broken logic (missing GROWTH_CAP application and any other obvious audit findings).
- **D-12:** Existing partial fix at lines 580–581 (`eps = eps / 1500.0` for BRK-B TTM EPS) stays as-is unless the audit reveals it's incorrect.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — CLN-01, CLN-02, CLN-03, CLN-04 (the 4 cleanup requirements)
- `.planning/ROADMAP.md` — Phase 4 success criteria (4 items)

### Code to Remove
- `stock_screener.py` lines 22 — `import time` (remove; becomes unused)
- `stock_screener.py` lines 31–33 — Google imports (remove all three)
- `stock_screener.py` lines 41–46 — `TIINGO_API_KEYS` block (remove)
- `stock_screener.py` lines 51–56 — `GSHEET_*` constants block (remove)
- `stock_screener.py` line 63 — `TIINGO_DELAY_SEC` constant (remove)
- `stock_screener.py` line 563 — `time.sleep(TIINGO_DELAY_SEC)` in `process_ticker()` (remove)
- `stock_screener.py` lines ~684–1195 — entire STEP 6 block (remove all: SIGNAL_COLORS, _col_letter, _apply_color_coding, DOCS_CONTENT, _write_markdown_tab, _write_docs_tab, push_to_gsheets)

### Non-Standard Ticker Code to Audit
- `stock_screener.py` lines 560–640 — `process_ticker()`: BRK-B EPS scaling (line 580–581), missing GROWTH_CAP application on Finnhub growth (line 595)
- `stock_screener.py` lines 270–325 — `get_combined_data()`: `growth_pct` sourcing from Finnhub `epsGrowth5Y`/`epsGrowth3Y` (line 295)
- `stock_screener.py` lines 336–354 — `compute_growth_5yr_cagr()`: already applies GROWTH_CAP correctly (line 354) — this is the pattern to replicate for Finnhub path

### CI/Secrets
- `screener.yml` — remove `TIINGO_API_KEYS`, `GSHEET_CREDS_JSON`, `GSHEET_SPREADSHEET`, `GSHEET_WORKSHEET` env var entries
- `requirements.txt` — remove `gspread>=6.0.0` and `google-auth>=2.28.0`

### Prior Phase Outputs (for verification reference)
- `.planning/phases/03-interactive-dashboard/03-02-SUMMARY.md` — confirms methodology.html built (safe to remove DOCS_CONTENT)
- `.planning/phases/01-security-pipeline-prerequisites/01-01-SUMMARY.md` — confirms history clean

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GROWTH_CAP = 25.0` (stock_screener.py line 59) — already defined; the fix for BRK-B Finnhub growth is to apply this same cap to the `g = fund["growth_pct"]` path (currently only applied inside `compute_growth_5yr_cagr()`)
- `compute_growth_5yr_cagr()` (lines 336–354) — already applies GROWTH_CAP; serves as the pattern for the fix

### Established Patterns
- The STEP 6 block is self-contained: removing it requires no changes to STEP 5 or STEP 4 logic (except line 563's sleep call and the `main()` call to `push_to_gsheets` must also be removed)
- `main()` at the bottom of the file calls `push_to_gsheets(df)` — that call must be removed when CLN-01 is applied

### Integration Points
- `requirements.txt` → `screener.yml` → `stock_screener.py` form a chain: all three need consistent cleanup or Actions will fail on import errors
- After removing Google imports, a test run (`python -c "import stock_screener"`) should confirm no import errors

</code_context>

<specifics>
## Specific Ideas

- Verification step: After cleanup, run `python -m py_compile stock_screener.py` locally to confirm no syntax errors before pushing. The Phase 4 success criteria also requires a `workflow_dispatch` run — note this in the plan as a required manual step.
- The `main()` function's `push_to_gsheets(df)` call (near the bottom of the file) is part of CLN-01 scope — it's not in STEP 6 but it's the call site. Remove it when removing the function.

</specifics>

<deferred>
## Deferred Ideas

- **Column header auto-sizing** — already in v2 deferred backlog ("Column header auto-sizing — dynamically fit column widths to header label text"). Dashboard UX improvement, not cleanup.
- **General share_class_ratio scaling mechanism** — a config-driven `/1500` scaling system for non-standard tickers (BRK-B and future ADRs/class-B shares). Out of scope for Phase 4; handle as separate follow-up once Phase 4's audit clarifies the full picture.

</deferred>

---

*Phase: 4-Google & Tiingo Cleanup*
*Context gathered: 2026-05-31*
