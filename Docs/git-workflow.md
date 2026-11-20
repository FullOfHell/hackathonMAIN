# Git workflow and push requirements

How we keep `main` working all night. Read once; every teammate and every AI tool follows it.

## One-time setup (each clone)

Fastest: run `bash scripts/setup.sh` from the repo root. It enables the hooks, creates the backend venv, installs backend and frontend dependencies, creates `backend/.env` from the template if missing, and runs the tests. Safe to re-run after every pull that changes dependencies.

Manual equivalent:

```bash
cd /c/Users/<you>/hackathonMAIN          # Git Bash: forward slashes
git config core.hooksPath scripts/hooks  # enables the commit and push checks below
cd backend
python -m venv .venv
source .venv/Scripts/activate            # Git Bash on Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env                  # fill in keys; never commit this file
```

## Daily loop

1. `git checkout main && git pull`
2. `git switch -c <area>/<task>` — e.g. `backend/invoice`, `frontend/manager-view`, `integration/n8n-workflow-1`
3. Work (yourself or Codex), one small task at a time.
4. `git status` — check that no `.env`, `.db`, `node_modules`, `__pycache__` or `.venv` appears.
5. `git add <files>` and `git commit -m "..."` — the pre-commit hook checks for secrets and junk.
6. `git push -u origin <branch>` — the pre-push hook runs backend tests with branch coverage.
7. Open a PR into `main`. Merge only when CI is green. Tell the team "merged X".

Never push directly to `main`. Merge to `main` every 1–2 hours so branches don't drift.

## What protects us

| Layer | Runs | Blocks |
|---|---|---|
| Pre-commit hook (`scripts/hooks/pre-commit`) | every commit, locally | `.env`, API keys (`sk-...`), `.db`, `node_modules`, `__pycache__`, `.venv`, coverage files |
| Pre-push hook (`scripts/hooks/pre-push`) | every push, locally | pushing when backend tests fail or branch coverage is below the threshold |
| CI (`.github/workflows/ci.yml`) | every push and every PR into `main` | **repo-safety:** same secret/junk check · **backend:** pytest with branch coverage ≥ 75% · **frontend:** `npm ci` + `npm run build` (type-check + build) |

Coverage settings live in `backend/.coveragerc` (`branch = True`, `fail_under = 75`). Baseline at setup: ~91%. Don't lower the threshold to get green; add tests instead. New backend behaviour ships with tests in the same PR.

Run the checks yourself before pushing:

```bash
cd backend && python -m pytest -q --cov --cov-report=term-missing
cd frontend && npm run build
```

## Branch protection on GitHub (repo owner, once)

Settings → Branches → Add branch protection rule (or ruleset) for `main`:

- Require a pull request before merging — approvals: **0** (nobody waits for reviews at 4am).
- Require status checks to pass: `repo-safety`, `backend`, `frontend` (they appear in the list after CI has run once).
- Leave "require branches to be up to date" **off**.

## Secrets

- API keys live only in `backend/.env` (git-ignored). Share keys privately, never in the repo, an issue, a Codex prompt, the frontend or an n8n node.
- If a key is ever committed or pushed: delete it in the provider dashboard immediately and create a new one. Removing the commit is not enough.

## Fixing common mistakes

| Problem | Fix |
|---|---|
| `.env` or junk is staged | `git restore --staged <file>` (or `git restore --staged .` to unstage everything) |
| Files "disappeared" after switching branches | They're committed on the other branch. `git log --all --oneline -- <path>` shows where; switch back or merge that branch. Don't delete and recreate. |
| `.venv\Scripts\activate: command not found` | You're in Git Bash: `source .venv/Scripts/activate` |
| Merge conflict | Open the file, keep both sides where it makes sense, `git add <file>`, `git commit`. Ask the file's owner if unsure. |
| Need to push urgently and the local hook blocks you | `git push --no-verify` skips local hooks; CI still runs on GitHub. Use only near the deadline. |

## Ownership (avoids conflicts)

- **A (frontend):** `frontend/`
- **B (backend):** `backend/app/api/cases.py`, `services/`, `partners/`, `states.py`, `db.py`, tests
- **C (integrations):** `backend/app/integrations/`, `backend/app/api/extract.py`, `n8n/`, `Docs/connector-spec.md`
- `backend/app/main.py` (router registration): keep edits to one line each and merge often.

## Deadline tags

- `demo-p0`: first reliable typed end-to-end flow (target Fri 23:30–00:00).
- `demo-final`: feature freeze, Sat 06:00. The submitted code must match this tag.

```bash
git tag demo-final && git push origin demo-final
```
