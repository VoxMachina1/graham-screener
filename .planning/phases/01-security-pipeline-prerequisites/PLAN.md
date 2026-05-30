---
phase: 01-security-pipeline-prerequisites
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - diagnose_finnhub.py
  - screener.yml
  - .github/workflows/screener.yml
  - .gitignore
  - docs/.nojekyll
autonomous: false
requirements:
  - SEC-01
  - SEC-02
  - CI-01
  - CI-02
  - CI-03
  - CI-04
  - CI-05
  - CI-06

must_haves:
  truths:
    - "diagnose_finnhub.py reads the API key from os.environ['FINNHUB_API_KEY'] — no hardcoded string remains"
    - "Git history contains no hardcoded Finnhub API key string; repo is safe to make public"
    - "screener.yml at .github/workflows/screener.yml declares permissions: contents: write at the job level"
    - "screener.yml configures github-actions[bot] git identity before any commit step"
    - "screener.yml commits only docs/data/results.json using a conditional pattern that skips commit when data is unchanged"
    - "docs/.nojekyll exists so GitHub Pages does not run Jekyll processing"
    - ".gitignore has !docs/data/results.json exception after the !.planning/*.json line"
  artifacts:
    - path: "diagnose_finnhub.py"
      provides: "API key read from environment, not hardcoded"
      contains: "os.environ[\"FINNHUB_API_KEY\"]"
    - path: ".github/workflows/screener.yml"
      provides: "Correct Actions workflow with permissions, git identity, and conditional commit"
      contains: "permissions"
    - path: "docs/.nojekyll"
      provides: "Disables Jekyll on GitHub Pages"
    - path: ".gitignore"
      provides: "Exception allowing docs/data/results.json to be tracked"
      contains: "!docs/data/results.json"
  key_links:
    - from: ".github/workflows/screener.yml"
      to: "docs/data/results.json"
      via: "git add docs/data/results.json in commit step"
      pattern: "git add docs/data/results\\.json"
    - from: "diagnose_finnhub.py"
      to: "FINNHUB_API_KEY env var"
      via: "os.environ lookup"
      pattern: "os\\.environ\\[.FINNHUB_API_KEY.\\]"
---

<objective>
Make the repository safe to publish and establish correct GitHub Actions CI infrastructure
before any new output code runs.

Purpose: The repo currently contains a hardcoded Finnhub API key in diagnose_finnhub.py
and the Actions workflow sits at the repo root (invisible to GitHub Actions) with no
permissions block, no git identity config, and no commit/push steps. This plan fixes all
of that in the correct order: audit history first, scrub if needed, then fix the source
file, then create the correctly-structured workflow, then update supporting files.

Output:
- diagnose_finnhub.py with API key read from environment
- .github/workflows/screener.yml with permissions, git identity, and conditional commit
- docs/.nojekyll
- .gitignore with !docs/data/results.json exception
- Git history confirmed free of credentials (or scrubbed)
</objective>

<execution_context>
@C:/Python Projects/.claude/get-shit-done/workflows/execute-plan.md
@C:/Python Projects/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@C:/Python Projects/graham_screener/.planning/PROJECT.md
@C:/Python Projects/graham_screener/.planning/ROADMAP.md
@C:/Python Projects/graham_screener/CLAUDE.md
</context>

<tasks>

<task type="auto">
  <name>T-01: Audit git history for hardcoded API key</name>
  <files>none (read-only audit)</files>
  <action>
    Run the following command from the repo root to check whether the hardcoded Finnhub
    API key appears in any commit in git history:

      git log -S "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" --oneline

    Record the output. Two outcomes are possible:

    - OUTPUT IS EMPTY: The key does not appear in any commit. Proceed directly to T-02
      with the "Key not found" path.
    - OUTPUT HAS COMMITS LISTED: The key exists in history. Proceed to T-02 with the
      "Key found" path.

    Do not proceed to T-02 without running this command and recording its output.
  </action>
  <verify>
    <automated>git log -S "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" --oneline</automated>
  </verify>
  <done>Command has been run and its output (empty or list of commits) has been recorded.
  The "Key found" vs "Key not found" determination has been made.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>T-02: Scrub git history if key was found (conditional)</name>
  <what-built>
    T-01 determined whether the hardcoded Finnhub API key exists in git history.
    This task handles both outcomes. Read T-01's output and follow the matching path.

    PATH A — Key NOT found (T-01 output was empty):
      No history action is required. Skip to T-03. Mark this task complete with note
      "Key not found in history — no scrub needed."

    PATH B — Key found (T-01 listed one or more commits):
      Execute the following steps in order:

      Step 1: Verify git-filter-repo is installed:
        pip show git-filter-repo
        If not installed: pip install git-filter-repo

      Step 2: Create a temporary replacements file:
        Create a file named /tmp/replacements.txt with exactly this content (one line):
          d73jm39r01qjjol39n40d73jm39r01qjjol39n4g==>REMOVED_API_KEY

      Step 3: Run filter-repo to rewrite history:
        git filter-repo --replace-text /tmp/replacements.txt

      Step 4: Force-push the rewritten history:
        git push origin --force --all

      Step 5: Verify the key is gone from history:
        git log -S "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" --oneline
        This must return empty output.

      Step 6: Document the manual key rotation requirement for the user:
        The Finnhub API key "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" was exposed
        in git history and has now been scrubbed. The user MUST rotate the key:
          1. Go to https://finnhub.io/dashboard
          2. Regenerate the API key
          3. Update the FINNHUB_API_KEY secret in the GitHub repository:
             Settings -> Secrets and variables -> Actions -> FINNHUB_API_KEY

    After completing either path, report the outcome to the user before proceeding.
  </what-built>
  <how-to-verify>
    Confirm with the user which path was taken (Key found or Key not found).

    If Key found path was taken:
      - git log -S "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" --oneline must be empty
      - User must acknowledge the key rotation instructions

    If Key not found:
      - Confirm no action was needed
  </how-to-verify>
  <resume-signal>
    Type "history clean" if T-01 found no key in history.
    Type "history scrubbed" if filter-repo was run and the key is confirmed gone and
    you have read the key rotation instructions.
  </resume-signal>
</task>

<task type="auto">
  <name>T-03: Fix SEC-01 — remove hardcoded API key from diagnose_finnhub.py</name>
  <files>diagnose_finnhub.py</files>
  <action>
    Edit diagnose_finnhub.py line 16. Replace the hardcoded assignment:

      FINNHUB_API_KEY = "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g"

    with:

      FINNHUB_API_KEY = os.environ["FINNHUB_API_KEY"]

    Also add "import os" to the imports at the top of the file. The file currently
    imports only "requests" and "json" (lines 13-14). Add "import os" after those two
    import lines, making the import block:

      import requests
      import json
      import os

    The fh_get() function at line 22 already uses the FINNHUB_API_KEY variable
    (params["token"] = FINNHUB_API_KEY) — no change is needed there.

    No fallback, no try/except, no default value. If the env var is absent, Python will
    raise KeyError and that is the correct behavior (per D-03).
  </action>
  <verify>
    <automated>python -c "import ast, sys; src=open('C:/Python Projects/graham_screener/diagnose_finnhub.py').read(); tree=ast.parse(src); print('No hardcoded key' if 'd73jm39r01qjjol39n40d73jm39r01qjjol39n4g' not in src else sys.exit(1))"</automated>
  </verify>
  <done>
    diagnose_finnhub.py line 16 reads os.environ["FINNHUB_API_KEY"] with no hardcoded
    string. The string "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" does not appear
    anywhere in the file. "import os" is present in the imports block.
  </done>
</task>

<task type="auto">
  <name>T-04: Create .github/workflows/ and write updated screener.yml</name>
  <files>.github/workflows/screener.yml</files>
  <action>
    Create the directory .github/workflows/ and write the updated workflow file to
    .github/workflows/screener.yml. The old screener.yml at the repo root is now a
    dead file — leave it in place (do not delete it; that is Phase 4 cleanup scope).

    The new .github/workflows/screener.yml must contain the following content exactly.
    Pay attention to YAML indentation — permissions is at the job level (indented under
    run-screener:), not at the top workflow level.

    Key requirements implemented (per D-04, D-05, CI-01, CI-02, CI-03, CI-04):
    - permissions: contents: write at job level (CI-01)
    - git config user.name and user.email before any commit (CI-02)
    - git add docs/data/results.json only (CI-03)
    - conditional commit using git diff --cached --quiet guard (CI-04)
    - email is the canonical GitHub Actions bot noreply: 41898282+github-actions[bot]@users.noreply.github.com

    Write this exact content to .github/workflows/screener.yml:

    ---
    name: Run Stock Screener

    on:
      schedule:
        - cron: "0 11 * * 1-5"
      workflow_dispatch:

    jobs:
      run-screener:
        runs-on: ubuntu-latest

        permissions:
          contents: write

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
              TIINGO_API_KEYS:     ${{ secrets.TIINGO_API_KEYS }}
              FRED_API_KEY:        ${{ secrets.FRED_API_KEY }}
              FINNHUB_API_KEY:     ${{ secrets.FINNHUB_API_KEY }}
              GSHEET_CREDS_JSON:   ${{ secrets.GSHEET_CREDS_JSON }}
              GSHEET_SPREADSHEET:  ${{ secrets.GSHEET_SPREADSHEET }}
              GSHEET_WORKSHEET:    ${{ secrets.GSHEET_WORKSHEET }}
            run: python stock_screener.py

          - name: Commit and push results
            run: |
              git config user.name "github-actions[bot]"
              git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
              git add docs/data/results.json
              if ! git diff --cached --quiet; then
                git commit -m "chore: update screener results"
                git push
              fi
    ---

    The YAML delimiters (---) above are illustrative — do not include them in the
    actual file. Write the content starting with "name: Run Stock Screener".
  </action>
  <verify>
    <automated>python -c "
import yaml, sys
with open('C:/Python Projects/graham_screener/.github/workflows/screener.yml') as f:
    doc = yaml.safe_load(f)
job = doc['jobs']['run-screener']
perms = job.get('permissions', {})
assert perms.get('contents') == 'write', 'permissions: contents: write missing'
steps = job['steps']
commit_step = next((s for s in steps if 'Commit' in s.get('name', '')), None)
assert commit_step is not None, 'Commit step missing'
run = commit_step['run']
assert 'github-actions[bot]' in run, 'git identity missing'
assert 'git add docs/data/results.json' in run, 'scoped git add missing'
assert 'git diff --cached --quiet' in run, 'conditional commit guard missing'
print('screener.yml structure valid')
"</automated>
  </verify>
  <done>
    .github/workflows/screener.yml exists and passes the structure check:
    permissions: contents: write is present at the job level, the commit step configures
    github-actions[bot] identity, git add targets only docs/data/results.json, and the
    conditional guard skips commit when data is unchanged.
  </done>
</task>

<task type="auto">
  <name>T-05: Update .gitignore and create docs/.nojekyll</name>
  <files>.gitignore, docs/.nojekyll</files>
  <action>
    Two changes in this task.

    CHANGE 1 — .gitignore (per D-08, CI-06):
    The current .gitignore has these two lines at the top of the Credentials section:
      *.json
      !.planning/*.json

    Add a new line immediately after !.planning/*.json:
      !docs/data/results.json

    Order matters for gitignore negation rules: the exception must follow the glob that
    would otherwise match. The result should be:
      *.json
      !.planning/*.json
      !docs/data/results.json

    Do not change any other line in .gitignore.

    CHANGE 2 — docs/.nojekyll (per D-07, CI-05):
    Create the directory docs/ and create an empty file docs/.nojekyll. The file has no
    content — it is a marker file that tells GitHub Pages not to run Jekyll processing.
    Write an empty file (zero bytes is fine; a single newline is also acceptable).
  </action>
  <verify>
    <automated>python -c "
import os, sys

# Check .gitignore has the exception in the right order
lines = open('C:/Python Projects/graham_screener/.gitignore').read().splitlines()
planning_idx = next(i for i, l in enumerate(lines) if l == '!.planning/*.json')
docs_idx = next((i for i, l in enumerate(lines) if l == '!docs/data/results.json'), -1)
assert docs_idx != -1, '!docs/data/results.json not found in .gitignore'
assert docs_idx == planning_idx + 1, '!docs/data/results.json must immediately follow !.planning/*.json'
print('.gitignore exception order: OK')

# Check docs/.nojekyll exists
nojekyll = 'C:/Python Projects/graham_screener/docs/.nojekyll'
assert os.path.exists(nojekyll), 'docs/.nojekyll does not exist'
print('docs/.nojekyll: exists')
"</automated>
  </verify>
  <done>
    .gitignore has !docs/data/results.json on the line immediately following
    !.planning/*.json. docs/.nojekyll exists (content is empty or a single newline).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions runner -> git remote | The workflow pushes commits; wrong permissions block this or allow overly broad writes |
| Developer machine -> git history | git filter-repo rewrites all commits; force-push replaces remote history |
| Environment -> Python process | diagnose_finnhub.py reads FINNHUB_API_KEY from env; absent var raises KeyError |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01 | Information Disclosure | diagnose_finnhub.py line 16 | mitigate | Replace hardcoded key with os.environ lookup (SEC-01, T-03) |
| T-01-02 | Information Disclosure | git history | mitigate | Audit with git log -S; scrub with git filter-repo if found (SEC-02, T-01/T-02) |
| T-01-03 | Tampering | screener.yml commit step | mitigate | Scope git add to docs/data/results.json only; conditional commit prevents spurious writes (CI-03, CI-04) |
| T-01-04 | Elevation of Privilege | GitHub Actions GITHUB_TOKEN | mitigate | Declare permissions: contents: write at job level — principle of least privilege; no broader scope granted (CI-01) |
| T-01-05 | Spoofing | git commit author in Actions | mitigate | Explicit git config user.name/email set to canonical github-actions[bot] identity before commit (CI-02) |
| T-01-SC | Tampering | pip install in workflow | accept | No new packages added in this phase; existing requirements.txt unchanged; low risk |
</threat_model>

<verification>
After all tasks complete, verify the full phase success criteria:

1. grep -n "FINNHUB_API_KEY" C:/Python\ Projects/graham_screener/diagnose_finnhub.py
   Expected: shows os.environ["FINNHUB_API_KEY"] — no quoted key string

2. grep -rn "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" C:/Python\ Projects/graham_screener/
   Expected: no matches (key absent from all files)

3. git log -S "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" --oneline
   Expected: empty output (key absent from all commits)

4. cat C:/Python\ Projects/graham_screener/.github/workflows/screener.yml
   Expected: permissions: contents: write present, commit step has github-actions[bot]
   identity, git add targets docs/data/results.json only, conditional guard present

5. python -c "import yaml; doc=yaml.safe_load(open('C:/Python Projects/graham_screener/.github/workflows/screener.yml')); print(doc['jobs']['run-screener']['permissions'])"
   Expected: {'contents': 'write'}

6. ls C:/Python\ Projects/graham_screener/docs/.nojekyll
   Expected: file exists

7. grep -n "docs/data/results.json" C:/Python\ Projects/graham_screener/.gitignore
   Expected: !docs/data/results.json on line immediately after !.planning/*.json
</verification>

<success_criteria>
Phase 1 is complete when ALL of the following are true:

1. diagnose_finnhub.py line 16 contains os.environ["FINNHUB_API_KEY"] — the string
   "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" does not appear anywhere in the file.

2. git log -S "d73jm39r01qjjol39n40d73jm39r01qjjol39n4g" --oneline returns empty output.

3. .github/workflows/screener.yml exists and declares permissions: contents: write at
   the job level (not top-level), configures github-actions[bot] git identity, adds only
   docs/data/results.json, and uses the conditional commit guard.

4. docs/.nojekyll exists.

5. .gitignore contains !docs/data/results.json on the line immediately following
   !.planning/*.json.
</success_criteria>

<output>
When all tasks are complete and success criteria verified, create:
  C:/Python Projects/graham_screener/.planning/phases/01-security-pipeline-prerequisites/01-01-SUMMARY.md

The summary should record:
- Which history path was taken (key found + scrubbed, or key not found)
- Whether key rotation was required (and that the user was informed)
- Confirmation that screener.yml moved to .github/workflows/
- Files modified and their final state
</output>
