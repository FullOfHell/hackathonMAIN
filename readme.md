# Reltix / centrix Hackathon Project

An end-to-end, context-aware maintenance coordinator for the MAIN Summit AI Hackathon. The demo turns a resident's "no heating" report into a completed repair: centrix context is reused, a simulated contractor receives the job, an appointment is booked, and the repair outcome and invoice are linked back to the unit.

## Start here

Everyone - including AI coding tools - should read these files before changing the implementation:

1. [`AGENTS.md`](AGENTS.md) - shared scope, engineering rules, and collaboration conventions.
2. [`Docs/Reltix_Hackathon_Project_Plan.md`](Docs/Reltix_Hackathon_Project_Plan.md) - product plan, architecture, API contracts, backlog, and acceptance tests.
3. [`Docs/Reltix-Track-Description.pdf`](Docs/Reltix-Track-Description.pdf) - official Reltix challenge brief and final source of truth for track requirements.
4. [`Docs/SpecialFeatures.md`](Docs/SpecialFeatures.md) - differentiators to attempt only after the core flow works.
5. [`Docs/git-workflow.md`](Docs/git-workflow.md) - branch flow, push checks, CI, coverage and secret handling.
5. [`Docs/TODO.md`](Docs/TODO.md) - prioritized implementation checklist for the three-person team.

If these documents conflict, the official track description wins for challenge requirements. `AGENTS.md` wins for repository working conventions.

## MVP demo

```text
resident reports no heating
  -> context-aware triage
  -> approval to share required data
  -> repair case created
  -> generic connector sends job to mock partner
  -> partner offers slots
  -> resident books a slot
  -> partner completes repair and attaches invoice
  -> centrix unit shows the full outcome and timeline
```

The prototype uses synthetic residents, properties, partners, and documents. It does not connect to the real centrix API or a real contractor.

## Planned architecture

- React + TypeScript for resident, partner, and property-manager views.
- FastAPI + SQLite as the source of truth for cases, state transitions, approvals, appointments, and documents.
- A provider-neutral partner connector with versioned, idempotent requests and callbacks.
- n8n for integration orchestration.
- Structured LLM extraction for issue intake; the model never invents booking or repair status.
- ElevenLabs voice as a P1 enhancement, with the typed portal as the reliable fallback.

The project plan describes the full demo. The implemented booking and callback contracts are in the [connector specification](Docs/connector-spec.md).

## Frontend development

The React and TypeScript portal is in `frontend/`. It includes tenant intake, an editable review, explicit sharing approval, a case timeline, and the HeatFix inbox.

```bash
cd frontend
npm install
npm run dev
```

For the live demo, start FastAPI, copy `frontend/.env.example` to `frontend/.env.local`, and restart Vite. The template uses `http://localhost:8000`. Open the frontend at `http://localhost:5173`, submit a heating report, approve the sharing request, then open **HeatFix inbox** to see the job. Leave `VITE_API_BASE_URL` unset for an offline fixture demo. Fixture reports reset on page reload.

Before opening a pull request, run:

```bash
npm run lint
npm run build
```

Shared frontend, backend and integration fixtures are stored in `shared/fixtures/`. Treat their shape as a team contract.

## Setup

From the repo root in Git Bash: `bash scripts/setup.sh` (installs everything, safe to re-run).

## Run the backend

From the repository root, use Python 3.10 or newer. In PowerShell run the following commands.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

In Bash, activate the virtual environment first.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                                 # vertical-slice tests
python -m uvicorn app.main:app --reload --port 8000
```

Open the interactive API at `http://localhost:8000/docs`. Startup seeds new SQLite databases in `backend/data/app.db` and upgrades existing cases in place. Defaults run both the centrix stand-in and simulated HeatFix on port 8000. For other addresses or a custom shared secret, set `PUBLIC_BACKEND_URL`, `PARTNER_BASE_URL` and `PARTNER_WEBHOOK_SECRET` in the environment or in `backend/.env`. See the [environment template](.env.example).

For ElevenLabs and n8n (cloud services), expose the backend with `cloudflared tunnel --url http://localhost:8000` and put the HTTPS URL in `PUBLIC_BACKEND_URL`.

Backend tests consume the canonical contract examples from `shared/fixtures/`.

## Three-person workflow

- Create short-lived branches such as `frontend/tenant-flow`, `backend/case-api`, or `integration/partner-connector`.
- Keep shared schemas and example payloads in version control and agree on changes before altering their shape.
- Open small pull requests and state which acceptance test they enable.
- Do not commit `.env` files, API keys, tokens, real personal data, or generated dependency folders.
- Merge only code that preserves the deterministic typed demo path.

## Current status

The tenant portal can send an approved report to the simulated HeatFix inbox and show the case timeline. The tested backend flow reaches `SCHEDULED` when the reporting resident selects an offered slot and HeatFix confirms the booking. A rejected job reaches `DECLINED`. Portal slot selection, completion records and invoices are subsequent milestones.
