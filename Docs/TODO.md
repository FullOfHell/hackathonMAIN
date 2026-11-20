# Project TODO

This checklist turns the project plan into an execution order for the three-person team. Complete the P0 workflow before starting P1. P2 is optional and should not put the demo at risk.

## Immediate setup

- [ ] Choose the final project name.
- [ ] Confirm team ownership:
  - A - Product/Frontend: tenant, partner and manager interfaces; demo flow.
  - B - Backend/Domain: FastAPI, SQLite, state machine and tests.
  - C - AI/Integrations: extraction, partner connector, n8n and connector documentation.
- [ ] Freeze shared contracts for unit context, case creation, case states, partner jobs and callbacks.
- [x] Commit representative JSON fixtures used by all three contributors.
- [ ] Create `frontend/`, `backend/`, `n8n/` and test directories.
- [x] Add `.gitignore`, `.env.example` and initial development commands.
- [ ] Create short-lived branches for each contributor's first slice.

## P0 - Core backend

- [x] Create the FastAPI application and configure SQLite.
- [ ] Model property, unit, resident, maintenance case and immutable case events.
- [ ] Model sharing approval, partner job, appointment, completion report and invoice document.
- [x] Seed one fictional property, resident, prior heating case and active contractor.
- [ ] Implement and validate the main state sequence:
  - `REPORTED`
  - `TRIAGED`
  - `AWAITING_SHARING_APPROVAL`
  - `PARTNER_REQUESTED`
  - `SLOTS_OFFERED`
  - `SCHEDULED`
  - `IN_PROGRESS`
  - `COMPLETED`
  - `CLOSED`
- [ ] Support explicit failure states without arbitrary transitions.
- [x] Record every transition with actor and timestamp.
- [x] Implement `GET /api/units/{unit_id}/context`.
- [x] Implement case creation, retrieval and event-history endpoints.
- [x] Implement sharing approval and slot-selection endpoints.
- [x] Implement the partner-event callback endpoint.
- [x] Verify cases and timelines survive a backend restart.

## P0 - First vertical slice

Target milestone:

`resident submits issue -> persistent case created -> sharing approval recorded -> mock partner receives exactly one job`

- [ ] Build the tenant's typed "no heating" report screen.
- [ ] Pre-fill address, unit, heating type and resident context.
- [ ] Ask only for missing information.
- [ ] Display an editable issue summary before submission.
- [ ] Show the exact fields that will be shared with the partner.
- [x] Require explicit approval and persist the approval record.
- [x] Create the generic connector interface.
- [x] Implement the simulated HeatFix partner.
- [ ] Route the approved case through n8n.
- [x] Add an idempotency key so retries cannot create duplicate jobs.
- [ ] Display the received job in a basic partner dashboard.
- [ ] Test retrying the same submission.

Do not begin P1 work until this milestone is reliable.

## P0 - Complete the repair loop

- [x] Let the partner accept or reject a job.
- [x] Let the partner offer appointment slots.
- [ ] Display slots in the tenant portal.
- [x] Require tenant confirmation before booking.
- [x] Persist the selected appointment.
- [ ] Let the partner mark work in progress and completed.
- [ ] Attach a synthetic repair report and invoice.
- [ ] Link the appointment, completion and invoice to the original case and unit.
- [ ] Build the property-manager/unit view.
- [ ] Display the complete persisted event timeline.
- [ ] Drive all visible progress from backend state, not UI-only state.

## P0 - AI intake

- [ ] Define a strict structured-output schema for issue extraction.
- [ ] Extract symptoms, urgency, availability and missing information.
- [ ] Validate all model output in the backend.
- [ ] Ask the resident when information is uncertain rather than guessing.
- [ ] Add a deterministic fallback that works without an LLM.
- [ ] Add a fixed emergency message for a possible gas leak.
- [ ] Prevent AI from reporting a booking or outcome that is not in persisted state.

## P0 - Connector quality and security

- [x] Version the connector schema.
- [x] Document required and optional partner fields.
- [x] Add signed or shared-secret partner callbacks.
- [x] Reject invalid callback signatures.
- [x] Deduplicate repeated callback events.
- [ ] Define timeout, rejection and unavailable-provider behavior.
- [x] Trace every request and callback to the original case.
- [x] Create `Docs/connector-spec.md`.
- [ ] Export n8n workflows without credentials.
- [ ] Keep all tokens and secrets in environment variables.

## P0 - Tests and demo readiness

- [ ] Test case creation and correct unit association.
- [x] Test persistence across backend restarts.
- [ ] Test approval records and shared fields.
- [ ] Test duplicate partner-job submission.
- [x] Test slot selection and appointment persistence.
- [x] Test valid and invalid state transitions.
- [x] Test duplicate and invalid partner callbacks.
- [ ] Test repair completion and invoice linking.
- [ ] Test unavailable-provider escalation.
- [ ] Rehearse the entire typed workflow repeatedly.
- [x] Add real startup commands to `readme.md`.
- [ ] Create `Docs/demo-script.md`.
- [ ] Tag the first reliable typed version as `demo-p0`.

## P1 - Differentiators

Implement in this order after P0 is stable:

- [ ] Add a partner-unavailable or rejection branch with human escalation.
- [ ] Surface relevant previous-repair context with source attribution and no diagnosis.
- [ ] Add a second simulated provider without changing case-domain logic.
- [ ] Detect two heating cases in one building within 24 hours and route one central-heating job.
- [ ] Include relevant caretaker or access information; never share a key-safe code automatically.
- [ ] Add ElevenLabs voice through the same backend tools as the portal.
- [ ] Preserve a complete typed fallback when voice or network access fails.
- [ ] Allow a voice conversation to continue in the portal without repeating information.
- [ ] Support an optional repair photo; AI may describe it but may not diagnose the fault.

## P2 - Optional; skip if the demo is at risk

- [ ] Add another service category such as internet or energy.
- [ ] Add real email or messaging integrations.
- [ ] Add more complex provider optimization.
- [ ] Add operational analytics or dashboards.
- [ ] Add manager approval for costly invoices.
- [ ] Add payment processing or real contractor bookings.
- [ ] Add multi-organization administration.

## Final hand-in

- [ ] Confirm the pushed code matches the demonstrated version.
- [ ] Tag the final demonstrated commit as `demo-final`.
- [ ] Complete README startup instructions.
- [ ] Complete the connector specification and assumptions document.
- [ ] Export safe n8n workflows.
- [ ] Record and edit the three-minute pitch video.
- [ ] Show one stable differentiator after the complete P0 flow.
- [ ] Submit the project, code and video before the event deadline.

## Recommended parallel starting work

- **A - Frontend:** tenant report and sharing-approval UI using shared fixtures.
- **B - Backend:** database, seed data, case creation and event timeline.
- **C - Integrations:** mock partner API, idempotent job creation and n8n connectivity.

Reconnect these pieces as early as possible and prove that one approved resident report produces exactly one persistent partner job.
