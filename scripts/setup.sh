#!/usr/bin/env bash
# One-command setup for a fresh clone (Git Bash on Windows, macOS or Linux).
# From the repository root: bash scripts/setup.sh
# Safe to re-run: it only installs/updates what's missing and never overwrites backend/.env.
set -e

root=$(git rev-parse --show-toplevel)
cd "$root"
ok()   { printf '\033[32m[ok]\033[0m %s\n' "$1"; }
warn() { printf '\033[33m[!!]\033[0m %s\n' "$1"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "Prerequisites"
PY=()
for executable in python py python3; do
  candidate=("$executable")
  if [ "$executable" = py ]; then candidate+=(-3); fi
  if "${candidate[@]}" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY=("${candidate[@]}")
    break
  fi
done
if [ "${#PY[@]}" -eq 0 ]; then
  warn "Install Python 3.10+ with venv and pip, then rerun setup."; exit 1
fi
if ! command -v npm >/dev/null || ! command -v node >/dev/null; then
  warn "Install Node.js 24 LTS with npm, then rerun setup."; exit 1
fi

# --- Git hooks ---------------------------------------------------------------
step "Git hooks"
git config core.hooksPath scripts/hooks
ok "hooks enabled (secret check on commit, tests on push)"

# --- Python / backend --------------------------------------------------------
step "Backend (Python)"
cd "$root/backend"
if [ ! -d .venv ]; then
  "${PY[@]}" -m venv .venv
  ok "created backend/.venv"
fi
if [ -f .venv/Scripts/python.exe ]; then VPY=.venv/Scripts/python.exe; else VPY=.venv/bin/python; fi
"$VPY" -m pip install -r requirements.txt
"$VPY" -c 'from zoneinfo import ZoneInfo; ZoneInfo("Europe/Berlin")'
ok "backend dependencies installed, Europe/Berlin available"

if [ ! -f .env ]; then
  cp "$root/.env.example" .env
  ok "created backend/.env with local demo defaults"
else
  ok "backend/.env already exists (left untouched)"
fi

# --- Frontend ------------------------------------------------------------------
step "Frontend (Node)"
cd "$root/frontend"
npm ci --include=dev --engine-strict
ok "frontend dependencies installed"

# --- Optional tools ------------------------------------------------------------
step "Optional tools"
if command -v cloudflared >/dev/null 2>&1; then
  ok "cloudflared found (public tunnel for ElevenLabs/n8n)"
else
  warn "cloudflared not found (only needed by whoever runs the tunnel). Windows: winget install --id Cloudflare.cloudflared"
fi

step "Done"
cat <<'MSG'
Windows: double-click start-demo.cmd in the repository root.
macOS/Linux: run these in two terminals from the repository root:
  cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000
  cd frontend && VITE_API_BASE_URL=http://localhost:8000 npm run dev -- --port 5173 --strictPort
Open http://localhost:5173. Personal email and phone delivery settings go in backend/.env
or in the environment inherited by the backend. See "Notifications" in readme.md.
MSG
