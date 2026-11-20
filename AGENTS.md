# Shared AI and contributor context

This file is the canonical repository instruction file for humans and AI coding tools. Read it before editing code or documentation.

## Mission

Build one reliable demo for the Reltix track: a resident reports broken heating, centrix context reduces repeated input, a simulated repair partner receives and completes the job, and the appointment, completion record, and invoice return to the correct unit and case.

The official requirements are in `Docs/Reltix-Track-Description.pdf`. The implementation plan is in `Docs/Reltix_Hackathon_Project_Plan.md`. If requirements conflict, the official PDF wins.

## Deadlines

- Submission: Saturday 21 November, 10:30 (GMT+1) on BuilderBase: project name, code identical to the demo version, 3-minute pitch video.
- P0 checkpoint: Friday 23:30–00:00, tag `demo-p0`.
- Feature freeze: Saturday 06:00, tag `demo-final`. After the freeze, only bug fixes.

## Non-negotiable product decisions

- One P0 service: heating repair.
- Resident channels: the portal (P0) and a simulated text-message outbox with one-click links (P1). No voice agent: Reltix already has one (see `Docs/mentor-feedback.md`).
- The owner–manager agreement sets the spending limit. The owner authorizes costs above it. €3,000 is the demo example. The shipped API holds a high invoice after completion for a simulated manager action. Advance owner authorization is a separate workflow.
- The connector must let Reltix add a new partner category (e.g. internet) without changing case-domain logic.
- FastAPI and SQLite are the source of truth for domain state.
- The LLM may extract and explain information, but it may not invent diagnoses, appointments, partner acceptance, completion, or invoice state.
- Every status transition is validated and persisted with timestamp and actor.
- Partner calls and callbacks are idempotent and traceable to the original case.
- Use only synthetic people, properties, contact details, and documents.
- Record explicit approval for the minimum fields shared with the partner.
- Never claim this prototype uses the real centrix API or a real contractor.

## Priority order

1. Repeatable end-to-end demo and resident experience.
2. Realistic persistence, consent, partner workflow, and failure handling.
3. Reusable connector contract.
4. Differentiators in this order: building-wide outage detection, text-message channel, €3,000 cost warning, internet partner via the connector, visual polish.

Do not trade a working P0 flow for a broader but incomplete feature set.

## Planned boundaries

- `frontend/`: resident, partner, and manager interfaces.
- `backend/`: FastAPI domain API, state machine, persistence, seed data, and tests.
- `n8n/`: exported workflows without credentials.
- `Docs/`: plan, official source material, connector specification, assumptions, and demo script.

Do not duplicate business rules in the UI or n8n. UI actions and partner callbacks request transitions from the backend.

## Collaboration rules for three people and multiple AI tools

- Before coding, check `git status`, read the plan section relevant to the task, and inspect existing contracts.
- Use short-lived branches and small commits. Do not overwrite another contributor's unrelated changes.
- Treat API schemas, state names, event names, and shared example payloads as team contracts. Update their documentation and tests in the same change.
- Prefer vertical increments that unlock an acceptance test over isolated scaffolding.
- Add or update tests for state transitions, validation, idempotency, and any bug fixed.
- Keep secrets in environment variables and document required names in `.env.example`; never commit secret values.
- State assumptions explicitly in `Docs/assumptions.md` when implementation begins.
- Update the README when real startup commands or major architecture decisions change.

## Push and merge requirements

- Run once per clone: `git config core.hooksPath scripts/hooks` (blocks secrets on commit, runs backend tests before push).
- Never push directly to `main`; open a PR. CI (`.github/workflows/ci.yml`) must be green: repo-safety, backend tests with branch coverage >= 75% (`backend/.coveragerc`), frontend type-check and build.
- New backend behaviour needs tests in the same PR; do not lower the coverage threshold to get green.

## Definition of done for a change

- The intended behavior works from the relevant user or API boundary.
- Persisted state, not UI-only state, drives visible progress.
- Failure behavior is explicit and does not report false success.
- Tests and documentation match the contract.
- No credentials, real personal data, build artifacts, or dependency directories are committed.

## Immediate team milestone

Freeze the case and connector schemas, seed one fictional unit and prior heating case, then deliver this vertical slice:

`resident submits issue -> persistent case created -> sharing approval recorded -> mock partner receives exactly one job`
