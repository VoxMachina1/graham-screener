# Architecture: GitHub Actions → JSON Commit → GitHub Pages Pipeline

**Project:** Lynch & Graham Screener — Google Sheets to GitHub Pages Migration
**Researched:** 2026-05-29
**Confidence:** HIGH — this is a well-established, widely-documented pattern with no meaningful variance across sources since 2021.

---

## Recommended Pipeline

```
GitHub Actions (schedule: weekdays 6am ET)
    │
    ├─ 1. actions/checkout@v4         ← checks out repo with GITHUB_TOKEN
    │
    ├─ 2. python stock_screener.py    ← existing pipeline; writes docs/data/results.json
    │
    ├─ 3. git diff --quiet (check)    ← skip commit if data unchanged
    │
    └─ 4. git commit + git push       ← commits results.json; Pages auto-deploys
                                           (triggers Pages rebuild ~30–90 seconds later)
```

The static site in `docs/` is served by GitHub Pages. `index.html` fetches `data/results.json` via `fetch()` at load time and renders the table client-side. No build step. No CDN. No separate deploy job.

---

## Question-by-Question Findings

### 1. Standard Pattern for Committing Data Files from GitHub Actions

**The minimal working pattern:**

```yaml
- name: Commit updated results
  run: |
    git config user.name  "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add docs/data/results.json
    git diff --staged --quiet || git commit -m "chore: update screener results $(date -u +%Y-%m-%d)"
    git push
```

**Permissions required:**

The `GITHUB_TOKEN` that Actions injects automatically has `contents: read` by default in repositories created after 2023 (GitHub hardened the default). You must explicitly grant write:

```yaml
permissions:
  contents: write
```

This goes at the **job level** (or workflow level) in `screener.yml`. No PAT (Personal Access Token) needed. No new secrets. This is the zero-credential path.

**Why `github-actions[bot]`:** Using the bot identity prevents the commit from appearing under your personal account and makes it clear in git log which commits are automated. The email format `github-actions[bot]@users.noreply.github.com` is the canonical form GitHub itself uses for Actions-generated commits.

**The `git config` scope:** These are local configs (`--local` is implicit), scoped to the checked-out repo on the runner. They do not persist anywhere.

**Confidence:** HIGH. This exact pattern is in GitHub's own official Actions documentation and used by thousands of public repos.

---

### 2. docs/ on main vs. gh-pages Branch

**Recommendation: `docs/` folder on `main` branch.**

Rationale specific to this project:

| Criterion | `docs/` on `main` | `gh-pages` branch |
|---|---|---|
| Commit complexity | Single commit writes data + Pages serves it | Need a second job/action to push to `gh-pages` separately |
| Data + frontend co-location | Yes — HTML and JSON live in same branch | No — frontend on `gh-pages`, data on `main`; cross-branch fetch is awkward |
| CI workflow steps | 1 push (to main) | 2 pushes (main → `gh-pages`) or an orphan-branch action |
| git history on main | Weekday data commits visible in main history | Data commits isolated on `gh-pages`; main history cleaner |
| Debugging | Open GitHub, click on `docs/data/results.json`, done | Have to switch branches |
| Race condition risk | None — single atomic push | Low but non-zero: Pages job could start between pushes |

**The gh-pages branch pattern is better when** you have a separate frontend build step (e.g., Vite, Next.js) where you'd want to keep build artifacts off `main`. For a static HTML file + JSON with no build step, `docs/` on `main` is strictly simpler.

**GitHub Settings configuration:**
- Settings → Pages → Source: "Deploy from a branch"
- Branch: `main` / Folder: `/docs`

Pages will rebuild within ~30–90 seconds of any push to `main` that touches the `docs/` directory.

**Confidence:** HIGH.

---

### 3. JSON File Size — 550 rows × 30 columns

**Estimated size:** 300–600 KB uncompressed.

Calculation basis:
- 550 rows × 30 columns = 16,500 values
- Values are mostly short strings (status labels), small floats (2–4 decimal places), and a few longer strings (e.g., `"annual_eps"` arrays as stringified lists)
- Average value: ~15–20 chars including JSON key overhead
- 16,500 × ~25 chars = ~412 KB uncompressed
- With pretty-printing (newlines/indentation): closer to 500–600 KB
- With compact JSON (no extra whitespace): closer to 300–400 KB

**Git history implications:**

At ~500 KB per commit, 5 days/week, 52 weeks = ~130 MB/year added to git history. This is problematic over a multi-year horizon but fine for 1–2 years.

**Mitigations (in priority order):**

1. **Compact JSON** — use `json.dumps(data, separators=(',', ':'))` in Python. Saves ~15–20% vs. default `indent=2`. Easy win, do this from day one.

2. **Omit null/error rows** — the current script already has `"Error"` rows for tickers with no data. Exclude these from the JSON export; only write rows that passed valuation. Reduces row count by ~30–40% based on the screener's current behavior.

3. **Accept the history** — for a personal project with daily cadence, a multi-year horizon before hitting GitHub's 1 GB soft limit is acceptable. No action needed now; revisit if the repo grows past ~500 MB.

4. **Do not use git LFS** — unnecessary complexity for this file size. LFS is for binaries and files >100 MB.

**Git's 100 MB per-file hard limit** is not a concern at ~500 KB.

**Confidence:** HIGH on size estimate; HIGH on git behavior at this scale.

---

### 4. Only Commit If Data Actually Changed

**The correct pattern:**

```bash
git add docs/data/results.json
git diff --staged --quiet || git commit -m "chore: update screener results $(date -u +%Y-%m-%d)"
git push
```

`git diff --staged --quiet` exits 0 (success) if nothing is staged, 1 if there are changes. The `||` means "run the right side only if the left side failed (exited non-zero)". So `git commit` only runs when there are actual changes.

`git push` should always run (even when no commit was made), but an empty push is harmless — git will just say "Everything up to date."

**Alternative — skip push entirely on no-change:**

```bash
git add docs/data/results.json
if git diff --staged --quiet; then
  echo "No changes to results.json — skipping commit"
else
  git commit -m "chore: update screener results $(date -u +%Y-%m-%d)"
  git push
fi
```

This is slightly cleaner in the Actions log because the push step doesn't run at all on no-change days. Use whichever reads better.

**When does data NOT change?** In practice for a stock screener running weekday mornings, data will change almost every run (prices move, EPS updates happen). Empty commits will be rare, but the guard is good hygiene regardless.

**Confidence:** HIGH. This is a standard shell idiom.

---

### 5. GitHub Pages Configuration Steps

**One-time setup (in GitHub repository Settings):**

1. Go to **Settings → Pages**
2. Under "Source", select **"Deploy from a branch"** (not "GitHub Actions")
3. Branch: `main`
4. Folder: `/docs`
5. Click **Save**

GitHub will immediately show the Pages URL: `https://<username>.github.io/<repo-name>/`

**File requirements:**

- `docs/index.html` must exist (GitHub Pages serves `index.html` by default)
- `docs/data/results.json` is fetched by `index.html` at runtime via `fetch('./data/results.json')`
- No `_config.yml` or Jekyll configuration needed for a plain HTML site
- Optional: add a `docs/.nojekyll` empty file to tell GitHub not to run Jekyll processing — prevents potential future conflicts if any file/folder starts with `_`

**Custom domain:** Not required; the default `*.github.io` URL works fine.

**HTTPS:** Enforced automatically on `*.github.io` domains. No configuration needed.

**Confidence:** HIGH.

---

### 6. Race Conditions Between Job Writing JSON and Pages Serving It

**The actual sequence:**

```
T+0:00   Actions job starts
T+0:30   Python screener runs (~45–60 min for 550 tickers based on the 0.25s delay)
T+1:00   results.json written locally on runner
T+1:01   git commit + git push
T+1:02   GitHub Pages detects push, queues a rebuild
T+1:03   Pages rebuild starts (deploys in ~30–90 seconds)
T+1:04   Pages CDN serves the new results.json
```

**There is no meaningful race condition** because:

1. The Pages deploy is triggered by the push event. A user loading the page before `T+1:04` gets the previous run's data — which is correct and expected behavior. Daily data does not need sub-minute freshness.

2. The JSON file is a single atomic file replacement. GitHub Pages does not serve a partial write.

3. There is no scenario where a user gets a partially-written or corrupt JSON file, because the file is committed (and thus complete) before Pages deploys it.

**The only "race" that exists:** A user loads the page at `T+1:03` while Pages is still rebuilding. They get yesterday's data for ~60 seconds. This is acceptable for a daily screener.

**If you want to expose the data timestamp:** Write a `"generated_at": "2026-05-29T11:02:34Z"` field into the JSON from Python. The frontend can display "Last updated: May 29 at 6:02 AM ET" so users know the data age.

**Confidence:** HIGH.

---

### 7. Committing HTML/CSS/JS Frontend Files vs. Data File

**Recommendation: Commit them separately, by hand.**

**Strategy:**

- Frontend files (`docs/index.html`, `docs/style.css`, `docs/app.js`) are committed manually by the developer — they change only when the UI is updated.
- Data file (`docs/data/results.json`) is committed automatically by GitHub Actions on every screener run.
- The Actions workflow must only `git add docs/data/results.json` — never `git add docs/` or `git add -A` — to avoid accidentally committing unintended changes.

**Why keep them separate:**

1. **Cleaner git log** — mixing "fix table sorting" commits with "chore: update screener results 2026-05-29" commits makes history hard to read.
2. **Safer Actions job** — a scoped `git add docs/data/results.json` cannot accidentally commit WIP frontend changes that happen to be on the runner's checkout.
3. **Simpler workflow** — no logic needed to distinguish "did a human change this" vs. "did the screener change this."

**File layout:**

```
docs/
├── index.html          ← committed by developer; served as the dashboard
├── style.css           ← committed by developer (optional; can inline in index.html)
├── app.js              ← committed by developer (optional; can inline in index.html)
├── .nojekyll           ← committed by developer (empty file, one-time setup)
└── data/
    └── results.json    ← committed by GitHub Actions after every screener run
```

For a simple dashboard, keeping all frontend code in a single `index.html` (inlining CSS and JS) removes the separate file management entirely and is a reasonable choice at this scale.

**Confidence:** HIGH.

---

## Component Boundaries

| Component | Responsibility | Owned By | Changes When |
|---|---|---|---|
| `stock_screener.py` | Fetch data, compute metrics, write `results.json` | Developer commits | Screener logic changes |
| `screener.yml` | Orchestrates Python run + git commit + push | Developer commits | Workflow changes |
| `docs/data/results.json` | Current screener output, machine-readable | GitHub Actions commits | Every weekday run |
| `docs/index.html` | Dashboard UI, reads and renders `results.json` | Developer commits | UI/UX changes |
| GitHub Pages | Serves `docs/` as static site | GitHub infrastructure | Auto, on push to main |

---

## Data Flow (Target State)

```
GitHub Actions runner (ubuntu-latest)
    │
    ├─ actions/checkout@v4
    │       └─ checks out main branch with write permissions (contents: write)
    │
    ├─ python stock_screener.py
    │       ├─ Wikipedia → ticker universe
    │       ├─ FRED → AAA yield
    │       ├─ yfinance + Finnhub → per-ticker fundamentals
    │       ├─ compute Lynch/Graham metrics
    │       └─ write docs/data/results.json  ← NEW output target
    │
    ├─ git add docs/data/results.json
    ├─ git diff --staged --quiet || git commit -m "chore: update screener results YYYY-MM-DD"
    └─ git push origin main
            │
            ▼
    GitHub detects push → Pages rebuild queued
            │
            ▼ (~30–90 seconds)
    https://<user>.github.io/<repo>/   serves docs/index.html
            │
            ▼ (client-side, on page load)
    fetch('./data/results.json')
            │
            └─ render table with Lynch/Graham signals + color coding
```

---

## Build Order Implications for Implementation

The migration has a natural dependency order. Each step can be verified before the next:

**Step 1 — JSON writer in Python (no Actions changes needed yet)**
Add `write_json(df)` to `stock_screener.py`. Test locally: run the script, confirm `docs/data/results.json` is valid JSON with the right shape. This step is safe to do before any workflow changes.

**Step 2 — Minimal `docs/index.html` (no Actions changes needed yet)**
Build a static page that does `fetch('./data/results.json')` and renders a basic table. Open `docs/index.html` directly in the browser with a local `results.json` to verify it works before touching Pages or Actions.

**Step 3 — Wire up GitHub Actions commit step**
Add `permissions: contents: write` to `screener.yml`. Add the `git config / git add / git commit / git push` steps after the Python run step. Run manually via `workflow_dispatch` to verify the commit appears in the repo.

**Step 4 — Enable GitHub Pages**
Settings → Pages → main / /docs. Verify the URL loads with the frontend and the data.

**Step 5 — Remove Google dependencies**
Only after Steps 1–4 are verified: remove `push_to_gsheets()`, `SIGNAL_COLORS` (or migrate to frontend), and `GSHEET_*` env vars and secrets.

This order means Google Sheets continues working until the new pipeline is confirmed, eliminating rollback risk.

---

## Full Workflow YAML (Target State)

```yaml
name: Run Stock Screener

on:
  schedule:
    - cron: "0 11 * * 1-5"
  workflow_dispatch:

permissions:
  contents: write          # required for git push

jobs:
  run-screener:
    runs-on: ubuntu-latest

    steps:
      - name: Check out repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run screener
        env:
          FRED_API_KEY:    ${{ secrets.FRED_API_KEY }}
          FINNHUB_API_KEY: ${{ secrets.FINNHUB_API_KEY }}
        run: python stock_screener.py

      - name: Commit results
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/data/results.json
          git diff --staged --quiet || git commit -m "chore: update screener results $(date -u +%Y-%m-%d)"
          git push
```

Note: `GSHEET_*` secrets are absent from the target — they are removed as part of Step 5.

---

## One-Time Repository Configuration Checklist

- [ ] Create `docs/` directory and commit `docs/.nojekyll` (empty file)
- [ ] Settings → Pages → Source: "Deploy from a branch" → `main` / `/docs`
- [ ] Verify Pages URL is live after first push to `docs/`
- [ ] Remove `GSHEET_CREDS_JSON`, `GSHEET_SPREADSHEET`, `GSHEET_WORKSHEET` secrets after migration is verified
- [ ] (Optional) Set repo description to include the Pages URL for discoverability

---

## Confidence Assessment

| Question | Confidence | Basis |
|---|---|---|
| GITHUB_TOKEN permissions pattern | HIGH | Documented GitHub Actions behavior; widely used |
| docs/ vs gh-pages tradeoff | HIGH | Direct reasoning from project constraints |
| JSON file size estimate | HIGH | Arithmetic from known row/column counts |
| Git history implications | HIGH | Git object model; known GitHub limits |
| Skip-if-unchanged pattern | HIGH | Standard shell idiom; used in thousands of repos |
| Pages configuration steps | HIGH | Stable GitHub Settings UI since 2022 |
| Race condition analysis | HIGH | Pages deploy sequence is deterministic |
| Frontend vs. data commit separation | HIGH | Git best practice; straightforward reasoning |
