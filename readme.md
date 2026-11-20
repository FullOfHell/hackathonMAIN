# Reltix / centrix Hackathon Project

An end-to-end, context-aware maintenance coordinator for the MAIN Summit AI Hackathon. The demo turns a resident's "no heating" report into a completed repair: centrix context is reused, a simulated contractor receives the job, an appointment is booked, and the repair outcome and invoice are linked back to the unit.

## Start here

Everyone - including AI coding tools - should read these files before changing the implementation:

1. [`AGENTS.md`](AGENTS.md) - shared scope, engineering rules, and collaboration conventions.
2. [`Docs/Reltix_Hackathon_Project_Plan.md`](Docs/Reltix_Hackathon_Project_Plan.md) - product plan, architecture, API contracts, backlog, and acceptance tests.
3. [`Docs/Reltix-Track-Description.pdf`](Docs/Reltix-Track-Description.pdf) - official Reltix challenge brief and final source of truth for track requirements.
4. [`Docs/SpecialFeatures.md`](Docs/SpecialFeatures.md) - differentiators to attempt only after the core flow works.
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

The detailed folder layout and API contracts are defined in the project plan. Add runnable setup commands here as soon as the first application skeleton is merged; do not invent commands for components that do not exist yet.

## Frontend development

The fixture-backed React and TypeScript application is in `frontend/`.

```bash
cd frontend
npm install
npm run dev
```

Before opening a pull request, run:

```bash
npm run lint
npm run build
```

Shared frontend, backend and integration fixtures are stored in `shared/fixtures/`. Treat their shape as a team contract.

## Three-person workflow

- Create short-lived branches such as `frontend/tenant-flow`, `backend/case-api`, or `integration/partner-connector`.
- Keep shared schemas and example payloads in version control and agree on changes before altering their shape.
- Open small pull requests and state which acceptance test they enable.
- Do not commit `.env` files, API keys, tokens, real personal data, or generated dependency folders.
- Merge only code that preserves the deterministic typed demo path.

## Current status

Planning and repository setup. The next milestone is a persistent case that can be created from the resident flow and received exactly once by the mock partner.
