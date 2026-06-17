# Deployment Pitfalls: GitHub Actions → results.json → GitHub Pages

**Domain:** Static dashboard deployed via git commit from CI  
**Researched:** 2026-05-29  
**Project:** Lynch & Graham Screener — GitHub Pages migration  
**Confidence:** HIGH (official GitHub documentation + direct code inspection)

---

## Critical Pitfalls

### P1 — `*.json` in `.gitignore` blocks `results.json` from being committed

**Severity:** CRITICAL  
**Phase:** Actions commit step (Phase 1 of migration)

**What goes wrong:**  
The existing `.gitignore` contains `*.json` at line 3. This was placed there to prevent the Google service account key file from being committed. When the Actions job tries to `git add results.json`, git silently ignores the file. The `git status` shows nothing staged. The push succeeds but pushes nothing. The Pages site either shows an old file or a 404.

**This project's exact exposure:**  
`.gitignore` line 3: `*.json` — affects every `.json` file in the repo root and subdirectories unless explicitly negated.

**Why it's silent:**  
`git add results.json` on an ignored file exits 0 by default. The commit either has nothing to commit (exits non-zero if you use `--allow-empty` guard) or silently commits zero files. The Actions step shows green.

**Prevention:**  
Add a negation rule immediately after the `*.json` line:
```gitignore
*.json
!results.json
```
The negation must come after the pattern it overrides — order matters in `.gitignore`.

**Alternatively**, place `results.json` in a subdirectory and scope the ignore:
```gitignore
# Credentials
/*.json          ← root-only, not recursive
!results.json    ← or just negate explicitly
```

**Detection (warning signs):**  
- Actions job exits 0 but Pages site shows stale data
- `git status` in the job shows "nothing to commit" after writing the file
- Add `git status --short` before the commit step; an empty output after writing the file is the smoking gun

**Verification step to add to workflow:**  
```yaml
- name: Verify JSON was written
  run: |
    if [ ! -f results.json ]; then echo "ERROR: results.json not found"; exit 1; fi
    python -c "import json,sys; d=json.load(open('results.json')); sys.exit(0 if len(d)>0 else 1)"
```

---

### P2 — `GITHUB_TOKEN` cannot push to a branch protected by push protection rules

**Severity:** HIGH  
**Phase:** Actions commit step

**What goes wrong:**  
The default `GITHUB_TOKEN` (available as `${{ secrets.GITHUB_TOKEN }}`) can push to unprotected branches. However, if branch protection rules are enabled on `main` (e.g., "Require pull request before merging," "Require status checks"), the push will be rejected with a 403 or a "refusing to update checked out branch" error.

For a personal repo on the free tier, branch protection is typically off by default, so this is not an immediate blocker — but it becomes one if branch protection is enabled later.

**Prevention:**  
- Do not enable branch protection rules on the branch that the Actions job commits to
- If you want branch protection, use a dedicated `data` branch for the JSON file and configure Pages to serve from that branch (or a `docs/` folder on main)
- Alternatively, use a Personal Access Token (PAT) stored as a secret — PATs bypass some branch protection rules depending on the rule type

**`GITHUB_TOKEN` write permissions:**  
The token needs `contents: write` permission. As of 2023, GitHub changed the default token permissions to read-only for new repositories. You must explicitly grant write access in the workflow:
```yaml
permissions:
  contents: write
```
Without this, the push fails with a 403 even on an unprotected branch.

**Detection:**  
- Job fails at the `git push` step with "Permission denied" or "403"
- Check the workflow run log — git will print the HTTP status

---

### P3 — Git push fails silently when there is nothing new to commit

**Severity:** HIGH  
**Phase:** Actions commit step

**What goes wrong:**  
If the screener runs on a market holiday or the data is identical to the prior run, `git diff` will show no changes. `git commit` exits with code 1 ("nothing to commit"). If this is not handled, the Actions step fails and the entire job is marked failed — even though nothing actually went wrong.

**Common bad pattern:**
```bash
git add results.json
git commit -m "Update results"   # exits 1 if no changes → step fails
git push
```

**Correct pattern:**
```bash
git add results.json
git diff --staged --quiet && echo "No changes, skipping" && exit 0
git commit -m "Update screener results $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push
```

Or with `--allow-empty` avoided intentionally — the `|| true` anti-pattern hides real errors. Use explicit diff check instead.

**Detection:**  
- Workflow marked "failed" on days with no data changes
- Error message: "nothing to commit, working tree clean"

---

### P4 — Empty or corrupt `results.json` is committed and served

**Severity:** HIGH  
**Phase:** Screener run step + Actions commit step

**What goes wrong:**  
The Python screener currently exits 0 even when every ticker fails (see `CONCERNS.md`). The JSON writer (not yet built) will write whatever `run_screener()` returns. Possible failure modes:

1. **Empty array:** All tickers fail → `results.json` = `[]` → dashboard shows "0 results"
2. **Partial data:** Network timeout mid-run → partial ticker list committed
3. **Malformed JSON:** Python exception mid-write (KeyboardInterrupt, disk full) → truncated file → `JSON.parse()` throws in the browser → dashboard shows blank/broken
4. **Zero buy signals:** Run completes correctly but no stock passes filters → `[]` is a valid, non-empty, fully correct result — but indistinguishable from a failed run without metadata

**This project's exact exposure from `run_screener()`:**  
- Returns a DataFrame even when all rows have `{"Error": "..."}` keys
- No minimum row count check exists
- `push_to_gsheets()` writes everything-or-nothing today; the JSON writer must not replicate this pattern by allowing zero-row writes

**Prevention:**

Add a validation gate before committing:
```python
import json, sys

data = df.to_dict(orient="records")
if len(data) < 100:   # S&P 500 alone has ~500 tickers; <100 rows = something broke
    print(f"ERROR: Only {len(data)} rows — aborting JSON write", file=sys.stderr)
    sys.exit(1)

with open("results.json", "w") as f:
    json.dump({"generated_at": ..., "rows": data}, f)
```

Validate in the Actions step too:
```bash
python -c "
import json, sys
d = json.load(open('results.json'))
rows = d.get('rows', d) if isinstance(d, dict) else d
if len(rows) < 100: sys.exit(1)
print(f'Validated: {len(rows)} rows')
"
```

**Detection:**  
- Dashboard shows 0 results or a JS error
- File size of `results.json` is suspiciously small (< 50 KB when normal is > 500 KB for 550 tickers)

---

## High Pitfalls

### P5 — Git user identity not configured → commit fails

**Severity:** HIGH  
**Phase:** Actions commit step

**What goes wrong:**  
GitHub Actions runners have no git user configured by default. `git commit` requires `user.name` and `user.email` to be set. Without them the commit fails immediately:
```
Author identity unknown
*** Please tell me who you are.
```

**Correct configuration:**
```bash
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
```

**Why these values specifically:**  
- `github-actions[bot]` is the canonical name for the Actions bot user; it appears correctly in GitHub's UI as a bot commit
- `41898282+github-actions[bot]@users.noreply.github.com` is the exact no-reply email GitHub maps to that bot account — using it means the commit is attributed to the bot user in the repository's commit history rather than appearing as an unresolvable unknown
- The `+` prefix format is GitHub's internal user-ID-based no-reply scheme

**Alternative (simpler, slightly less precise):**
```bash
git config user.name "github-actions"
git config user.email "github-actions@github.com"
```
This works but shows as an unverified commit author.

**Detection:**  
- Job fails at `git commit` with "Author identity unknown"

---

### P6 — GitHub Pages CDN propagation delay: committed file is not immediately live

**Severity:** HIGH (for user expectations) / LOW (for correctness)  
**Phase:** After first Pages deployment

**What goes wrong:**  
GitHub Pages is served via a CDN (Fastly). After a commit is pushed, the Pages build must trigger, complete (30 seconds to ~2 minutes), and then CDN edge nodes must invalidate their cache. The sequence is:

1. Push commit → triggers Pages build job (0–60 seconds to start)
2. Pages build runs (typically 30–90 seconds for a static site with no Jekyll processing)
3. Deploy to CDN origin
4. CDN edge propagation (varies: 1–10 minutes globally, sometimes longer)

**Total typical delay: 2–15 minutes** after the Actions push for the new `results.json` to appear at the Pages URL.

**Implications for this project:**  
- The screener runs at 06:00 ET. The dashboard will show updated data by ~06:15–06:20 ET.
- If a user refreshes immediately after 06:00 and sees old data, this is expected — not a bug.

**Hard limit: 10 deploys per hour.** If the workflow triggers multiple times within an hour (e.g., manual trigger + scheduled), Pages may queue or skip builds.

**Browser caching compound effect:**  
If `results.json` is served with default cache headers, the browser may cache a stale version independently of CDN propagation. See P7.

**Prevention:**  
- Add `generated_at` timestamp to `results.json` and display it in the dashboard UI so users can see when data was last updated
- Document the expected delay in the dashboard footer

---

### P7 — Browser caches `results.json` — dashboard shows stale data

**Severity:** HIGH  
**Phase:** Frontend fetch implementation

**What goes wrong:**  
GitHub Pages serves static files with a default `Cache-Control` header. As of recent measurements, GitHub Pages applies `max-age=600` (10 minutes) to most static assets. For `results.json`, this means:

- A browser that loaded the page 5 minutes ago may show results that are 10+ minutes old
- A user who refreshes the dashboard within 10 minutes gets the cached file, not the latest
- Mobile browsers and aggressive caching proxies can extend this further

**Specific failure mode:**  
The screener runs at 06:00. User opens dashboard at 06:05. Browser caches `results.json`. User refreshes at 06:08. Browser serves the 06:05 cached response. User sees yesterday's data marked as "today."

**Prevention:**  
Append a cache-busting query parameter when fetching the JSON:
```javascript
const ts = Date.now();
const response = await fetch(`results.json?v=${ts}`);
```
This forces the browser to make a fresh request every page load, bypassing the browser cache. It does not bypass CDN cache, but GitHub Pages CDN should propagate within minutes of a deploy.

**Alternative:** Include a build timestamp in the HTML itself (not feasible for a purely static file served from Pages without a build step).

**Detection:**  
- Dashboard `generated_at` timestamp is stale relative to wall clock by more than 15 minutes after a run

---

### P8 — `fetch()` of `results.json` fails silently or throws on CORS / path issues

**Severity:** HIGH  
**Phase:** Frontend implementation

**What goes wrong:**  
Three distinct failure modes exist when the frontend fetches `results.json`:

**8a — Path mismatch:**  
GitHub Pages serves from either the repo root or a `docs/` folder. If `results.json` is in the root but the HTML is in `docs/`, the relative path `./results.json` resolves to `docs/results.json` which doesn't exist → 404. Conversely, if Pages is configured to serve from `gh-pages` branch but the commit goes to `main`, the file is committed to the wrong place.

**8b — CORS on `file://`:**  
Opening the HTML file locally with `file://` protocol triggers CORS errors on `fetch()` — `file://` origin is not permitted to fetch other `file://` resources via XHR/fetch in Chromium-based browsers. This is only a development-time issue (Pages itself does not have CORS problems for same-origin requests), but it makes local testing impossible without a local server.

**8c — GitHub Pages CORS headers:**  
GitHub Pages does not serve CORS headers (`Access-Control-Allow-Origin`) for files in your repo by default. This is fine when the dashboard HTML and `results.json` are on the same origin (`username.github.io`). It becomes a problem only if you try to fetch from a different domain.

**Prevention:**  
- Put both `index.html` and `results.json` at the same level in the repo, with Pages configured to serve from the same source
- For local development, use `python -m http.server 8080` instead of opening `file://` directly
- Add explicit error handling in the fetch:
```javascript
fetch(`results.json?v=${Date.now()}`)
  .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
  .then(data => renderTable(data))
  .catch(err => showError(`Failed to load data: ${err.message}`));
```

**Detection:**  
- Browser console shows "Failed to fetch" or "CORS error"
- Network tab shows 404 for `results.json`

---

## Medium Pitfalls

### P9 — Screener job failure leaves the old `results.json` in place (stale data risk)

**Severity:** MEDIUM  
**Phase:** Ongoing operations

**What goes wrong:**  
If the screener Python script fails (API timeout, Finnhub quota exhausted, Wikipedia structure change), the Actions job exits non-zero. The commit step never runs. The old `results.json` remains in the repo. The dashboard continues to serve it.

**This is actually the correct safe behavior** — it's better to show yesterday's data than corrupt data. However, without a visible timestamp or staleness indicator in the dashboard, users cannot tell whether the data is from today or from three weeks ago.

**Compound risk:**  
The existing `run_screener()` does not exit non-zero on mass ticker failure (see `CONCERNS.md` — "No Run-Level Failure Detection"). The JSON write step could succeed even on a near-total failure, overwriting good data with bad.

**Prevention:**  
- Display `generated_at` prominently in the dashboard with a staleness warning if > 36 hours old
- Add the minimum-row validation gate described in P4 to ensure a partial run doesn't overwrite a complete one
- Consider committing a `run_metadata.json` with success/failure status alongside `results.json`

**Detection:**  
- `generated_at` in the dashboard is more than 1 business day old

---

### P10 — Secrets required in the screener job are not available during the Pages build job

**Severity:** MEDIUM  
**Phase:** Workflow configuration

**What goes wrong:**  
GitHub Actions has two different job contexts: the screener job (which needs `FINNHUB_API_KEY`, `FRED_API_KEY`, etc.) and the Pages deployment. If these are configured as a single job, there's no conflict. If split into separate jobs, the Pages job does not inherit secrets from the screener job — it needs its own `permissions: pages: write` and `id-token: write` grants.

**Typical mistake:**  
Configuring the Pages deploy step in a separate job without the correct `permissions` block:
```yaml
# This fails silently:
jobs:
  deploy-pages:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/deploy-pages@v4  # needs pages: write, id-token: write
```

**Prevention:**  
For this project's simple case (committing `results.json` directly to the repo branch), there is no separate Pages deployment job — GitHub Pages auto-deploys when the branch updates. No special Pages permissions are needed; only `contents: write` on the commit job is required.

If you migrate to the "GitHub Pages deployment" action approach (Actions → Pages artifact), the correct permissions are:
```yaml
permissions:
  contents: read
  pages: write
  id-token: write
```

---

### P11 — Repository is public: secrets and financial data exposure

**Severity:** MEDIUM  
**Phase:** Initial setup

**What goes wrong:**  
GitHub Pages on the free tier requires the repository to be public. A public repository means:

**11a — Secrets in code:**  
`diagnose_finnhub.py` currently contains a hardcoded Finnhub API key (see `CONCERNS.md` P1). If pushed to the public repo, the key is permanently in git history even after deletion. This is a real, immediate risk for this specific project.

**11b — Financial data as personal information:**  
The screener results themselves (which stocks score as "Buy") are personal investment research. Publishing them is the stated goal of the project, but the user should be aware that once on a public GitHub Pages URL, the data is indexed by search engines, archived by the Wayback Machine, and cannot be made private without deleting the repo or converting to a private repo (which breaks free Pages).

**11c — Workflow secrets are safe:**  
GitHub repository secrets are never exposed in workflow logs or to the public, regardless of repo visibility. `FINNHUB_API_KEY` set via Settings → Secrets is not at risk.

**Prevention:**  
- Remove the hardcoded key from `diagnose_finnhub.py` before the first push (use `os.environ["FINNHUB_API_KEY"]`)
- Run `git log --all -p -- diagnose_finnhub.py` to verify the key is not already in history
- If it is already in history: use `git filter-repo` or BFG Repo Cleaner to purge it, then force-push before making the repo public

**Detection:**  
- Review `diagnose_finnhub.py` before any `git push` — it is currently confirmed to have a hardcoded key

---

### P12 — GitHub Pages file size and repo size limits

**Severity:** MEDIUM (could become high as history accumulates)  
**Phase:** Ongoing operations

**What goes wrong:**  
GitHub Pages has documented limits:
- **Published site size:** 1 GB maximum
- **Soft bandwidth limit:** 100 GB per month (overage may trigger rate limiting)
- **Individual file serving:** No hard per-file size limit for serving, but GitHub recommends files under 50 MB for repository storage; files over 100 MB cannot be pushed to GitHub at all

**For `results.json` specifically:**  
~550 tickers × ~40 fields each as JSON = approximately 300–800 KB per run. This is well within limits per file.

**The cumulative risk:**  
Each weekday run commits a new version of `results.json`. Git stores the full object for each version. Over 1 year (~250 trading days), the `.git` directory will contain 250 versions of a ~500 KB file = ~125 MB of git objects just for this one file. Over several years this grows into the GB range.

**Prevention:**  
- `results.json` is overwritten in-place (same filename, same path) on each commit — git stores only the delta in pack files, not full copies, so growth is slower than worst-case
- For long-running projects, periodically run `git gc` or consider using `git replace` / shallow clones for the Actions checkout
- If the repo grows large: use `actions/checkout@v4` with `fetch-depth: 1` (already the default) to avoid fetching full history in CI

**No action required now** — monitor repo size after 6 months.

---

## Low Pitfalls

### P13 — `actions/checkout@v4` default `fetch-depth: 1` prevents `git push` in some configurations

**Severity:** LOW  
**Phase:** Actions commit step

**What goes wrong:**  
By default, `actions/checkout@v4` does a shallow clone (`fetch-depth: 1`). This is normally fine for committing a new file. However, if the branch has diverged from the remote (e.g., a concurrent run committed while this run was executing), `git push` will be rejected with "Updates were rejected because the remote contains work that you do not have locally."

For a scheduled daily job that runs once per weekday, concurrent runs are unlikely but possible if manual triggers overlap with scheduled runs.

**Prevention:**  
Before the commit, pull with rebase:
```bash
git pull --rebase origin main
git add results.json
git commit -m "..."
git push
```
Or accept the rare failure (a retry via `workflow_dispatch` is sufficient for a daily tool).

**Detection:**  
- Push step fails with "non-fast-forward" rejection

---

### P14 — `git push` loop triggers infinite workflow cascade

**Severity:** LOW  
**Phase:** Workflow design

**What goes wrong:**  
If the workflow triggers on `push` events AND commits back to the same branch, each commit triggers another workflow run, which commits again, creating an infinite loop.

**This project's current workflow** uses only `schedule` and `workflow_dispatch` triggers — no `push` trigger. This pitfall only applies if someone adds `on: push` to the workflow.

**Prevention:**  
Never add `on: push` to a workflow that also commits to the repo, unless you filter by path or branch:
```yaml
on:
  push:
    branches-ignore:
      - main   # or filter to only trigger on non-data paths
```
Or check `github.actor` and skip if the actor is `github-actions[bot]`.

---

### P15 — `results.json` served with wrong Content-Type on some Pages configurations

**Severity:** LOW  
**Phase:** Frontend implementation

**What goes wrong:**  
GitHub Pages correctly infers `Content-Type: application/json` for `.json` files based on file extension. However, if Pages is configured with Jekyll (the default for repos without a `.nojekyll` file), Jekyll may process files and potentially alter headers or skip files beginning with `_`.

**Prevention:**  
Add a `.nojekyll` file to the root of the branch being served:
```bash
touch .nojekyll
git add .nojekyll
git commit -m "Disable Jekyll processing"
```
This tells GitHub Pages to serve files as-is without Jekyll processing. It also prevents Jekyll from ignoring files/directories that start with `_` or `.`, which could matter if you later organize assets in subdirectories.

---

## Phase-Specific Warnings

| Migration Phase | Likely Pitfall | First Mitigation Step |
|---|---|---|
| Remove Google output, add JSON writer | P4 (empty/corrupt JSON), P9 (stale data) | Add minimum-row validation gate in Python before writing |
| Add git commit step to `screener.yml` | P1 (gitignore blocks file), P5 (no git user) | Fix `.gitignore` first; add `git config` lines before `git add` |
| Configure GitHub Pages | P15 (Jekyll), P8a (path mismatch) | Add `.nojekyll`; verify Pages source matches where files are committed |
| Write frontend `fetch()` | P7 (browser cache), P8b (local CORS) | Use `?v=${Date.now()}` cache-bust; test with `python -m http.server` not `file://` |
| Make repo public | P11 (hardcoded key), P11a (git history) | Audit `diagnose_finnhub.py` and git history BEFORE making public |
| First week of live deploys | P6 (CDN delay), P2 (permissions) | Add `permissions: contents: write` to workflow; expect 5–15 min propagation |
| Ongoing operations (months) | P9 (stale data silent), P13 (concurrent pushes) | Add `generated_at` timestamp + UI staleness indicator |

---

## Sources

- GitHub Documentation: "Automatic token authentication" — `contents: write` permission requirement, branch protection interactions (HIGH confidence, official docs)
- GitHub Documentation: "About GitHub Pages" — 1 GB site limit, 100 GB/month bandwidth, 10 deploys/hour (HIGH confidence, official docs)
- GitHub Pages behavior: Jekyll default processing, `.nojekyll` convention (HIGH confidence, widely documented)
- Git documentation: `.gitignore` negation rule ordering (`!pattern` must follow the pattern it negates) (HIGH confidence, official git docs)
- Observed pattern: `github-actions[bot]` canonical email format `41898282+github-actions[bot]@users.noreply.github.com` (HIGH confidence, GitHub community standard)
- CDN propagation timing: 2–15 minutes typical based on documented Fastly CDN behavior for GitHub Pages (MEDIUM confidence — no SLA published; observed range from community reports)
- Browser `Cache-Control: max-age=600` for GitHub Pages static assets (MEDIUM confidence — default behavior, not a guaranteed SLA)
- Project-specific: `CONCERNS.md`, `.gitignore`, `screener.yml`, `stock_screener.py` — direct code inspection (HIGH confidence)
