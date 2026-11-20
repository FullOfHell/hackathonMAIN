# Shared AI and contributor context

This file is the canonical repository instruction file for humans and AI coding tools. Read it before editing code or documentation.

## Mission

Build one reliable demo for the Reltix track: a resident reports broken heating, centrix context reduces repeated input, a simulated repair partner receives and completes the job, and the appointment, completion record, and invoice return to the correct unit and case.

The official requirements are in `Docs/Reltix-Track-Description.pdf`. The implementation plan is in `Docs/Reltix_Hackathon_Project_Plan.md`. If requirements conflict, the official PDF wins.

## Non-negotiable product decisions

- One P0 service: heating repair.
- Typed resident portal is the baseline; voice is optional until the typed flow works.
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
4. Voice, multi-provider routing, and visual polish.

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

## Definition of done for a change

- The intended behavior works from the relevant user or API boundary.
- Persisted state, not UI-only state, drives visible progress.
- Failure behavior is explicit and does not report false success.
- Tests and documentation match the contract.
- No credentials, real personal data, build artifacts, or dependency directories are committed.

## Immediate team milestone

Freeze the case and connector schemas, seed one fictional unit and prior heating case, then deliver this vertical slice:

`resident submits issue -> persistent case created -> sharing approval recorded -> mock partner receives exactly one job`
