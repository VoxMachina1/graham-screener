# Phase 7 Discussion Log

**Date:** 2026-06-28

## Areas Discussed

All four flagged gray areas discussed in one session.

---

### 1. Safety Pillar Upgrade

**Q: How should Piotroski F-Score and Altman Z'' integrate into the Safety pillar?**
> User: "Honestly I'd like the ability to evaluate if something is a trap myself. Let's evaluate the consequences of dropping the 'trap filter' entirely"

Consequences walked through:
- No hard Safety floor-to-0; distressed stocks score low naturally via Piotroski + Altman sub-scores
- The is_trap badge on top.html disappears
- User sees raw Piotroski/Altman columns + Safety chip and makes the call

**Q: When Altman Z'' is unavailable, what happens to Safety?**
> User chose: neutral 50 (not average-over-present — user override of D-01b for Safety)

**Q: What happens to the trap badge on top.html?**
> User chose: Replace badge with a Safety score chip (mirrors Value/Quality/Growth chips)

**Q: Piotroski + Altman scoring?**
> User chose: Both as scored sub-scores (piecewise)

---

### 2. DCF Assumptions

**Q: WACC source?**
> User chose: FRED AAA yield + 5.5% equity risk premium (Recommended)

**Q: DCF stages?**
> User chose: 5yr high-growth + terminal (Recommended)

**Q: Terminal growth cap?**
> User chose: min(realized 5yr CAGR, 3.0%) (Recommended)

**Q: Reverse DCF non-convergence?**
> User chose: None + sentinel flag column (dcf_reverse_converged=False)

**Q: DCF sector guard?**
> User chose: Financials + REITs excluded

---

### 3. Snapshot Cadence

**Q: How often should results.json be archived?**
> User chose: Monthly — first weekday of each month (Recommended)

**Q: Where do snapshot links live in the nav?**
> User chose: Add a simple 'History' link in nav — minimal list page with dates + download links

*Note: This adds a 5th nav link (Dashboard / Top Picks / Stats / History / Methodology) — minor scope expansion beyond PAGE-04 but explicitly user-requested.*

---

### 4. stats.html Scope + Layout

**Q: Primary content layout?**
> User chose: Stat cards + simple tables (no charting library) (Recommended)

**Q: Interactivity level?**
> User chose: Read-only — stats computed in Python, emitted to JSON (Recommended)
