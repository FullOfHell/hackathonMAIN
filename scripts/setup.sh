#!/usr/bin/env bash
# One-command setup for a fresh clone (Git Bash on Windows, macOS or Linux).
# Usage, from anywhere in the repo:   bash scripts/setup.sh
# Safe to re-run: it only installs/updates what's missing and never overwrites backend/.env.
set -e

root=$(git rev-parse --show-toplevel)
cd "$root"
ok()   { printf '\033[32m[ok]\033[0m %s\n' "$1"; }
warn() { printf '\033[33m[!!]\033[0m %s\n' "$1"; }
step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

# --- Git hooks ---------------------------------------------------------------
step "Git hooks"
git config core.hooksPath scripts/hooks
ok "hooks enabled (secret check on commit, tests on push)"

# --- Python / backend --------------------------------------------------------
step "Backend (Python)"
if command -v python >/dev/null 2>&1 && python -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  PY=python
elif command -v py >/dev/null 2>&1; then
  PY="py -3"
elif command -v python3 >/dev/null 2>&1; then
  PY=python3
else
  warn "Python 3.10+ not found. Install it from python.org (tick 'Add to PATH'), then re-run."; exit 1
fi
cd "$root/backend"
if [ ! -d .venv ]; then
  $PY -m venv .venv
  ok "created backend/.venv"
fi
if [ -f .venv/Scripts/python.exe ]; then VPY=.venv/Scripts/python.exe; else VPY=.venv/bin/python; fi
"$VPY" -m pip install -q --upgrade pip
"$VPY" -m pip install -q -r requirements.txt
ok "backend dependencies installed"

if [ ! -f .env ]; then
  cp "$root/.env.example" .env
  warn "created backend/.env from .env.example: fill in OPENAI_API_KEY (and others) yourself"
else
  ok "backend/.env already exists (left untouched)"
fi

echo "running backend tests..."
if "$VPY" -m pytest -q --cov --cov-report=term-missing:skip-covered; then
  ok "backend tests pass"
else
  warn "backend tests failed: check the output above"
fi

# --- Frontend ------------------------------------------------------------------
step "Frontend (Node)"
cd "$root/frontend"
if ! command -v npm >/dev/null 2>&1; then
  warn "npm not found. Install Node.js LTS from nodejs.org, then re-run."
elif [ -f package.json ]; then
  if [ -f package-lock.json ]; then npm ci --silent; else npm install --silent; fi
  ok "frontend dependencies installed"
else
  warn "frontend/package.json not found; skipping"
fi

# --- Optional tools ------------------------------------------------------------
step "Optional tools"
if command -v cloudflared >/dev/null 2>&1; then
  ok "cloudflared found (public tunnel for ElevenLabs/n8n)"
else
  warn "cloudflared not found (only needed by whoever runs the tunnel). Windows: winget install --id Cloudflare.cloudflared"
fi

step "Done"
cat <<'MSG'
Activate the backend venv in each new terminal:
  cd backend && source .venv/Scripts/activate      (macOS/Linux: source .venv/bin/activate)
Start the backend:   python -m uvicorn app.main:app --reload --port 8000   -> http://localhost:8000/docs
Start the frontend:  cd frontend && npm run dev
MSG
