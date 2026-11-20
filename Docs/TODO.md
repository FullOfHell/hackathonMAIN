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
- [x] Create `frontend/`, `backend/`, `n8n/` and test directories.
- [x] Add `.gitignore`, `.env.example` and initial development commands.
- [ ] Create short-lived branches for each contributor's first slice.

## P0 - Core backend

- [x] Create the FastAPI application and configure SQLite.
- [x] Model property, unit, resident, maintenance case and an append-only case timeline.
- [x] Model sharing approval, partner job and appointment.
- [x] Model completion reports and invoice documents.
- [x] Seed one fictional property, resident, prior heating case and active contractor.
- [x] Implement and validate the main state sequence:
  - `REPORTED`
  - `TRIAGED`
  - `AWAITING_SHARING_APPROVAL`
  - `PARTNER_REQUESTED`
  - `SLOTS_OFFERED`
  - `SCHEDULED`
  - `IN_PROGRESS`
  - `COMPLETED`
  - `CLOSED`
- [x] Support explicit failure states without arbitrary transitions.
- [x] Record every transition with actor and timestamp.
- [x] Implement `GET /api/units/{unit_id}/context`.
- [x] Implement case creation, retrieval and event-history endpoints.
- [x] Implement sharing approval and slot-selection endpoints.
- [x] Implement the partner-event callback endpoint.
- [x] Verify cases and timelines survive a backend restart.

## P0 - First vertical slice

Target milestone:

`resident submits issue -> persistent case created -> sharing approval recorded -> mock partner receives exactly one job`

- [x] Build the tenant's typed "no heating" report screen.
- [x] Pre-fill address, unit, heating type and resident context.
- [ ] Ask only for missing information.
- [x] Display an editable issue summary before submission.
- [x] Show the exact fields that will be shared with the partner.
- [x] Require explicit approval and persist the approval record.
- [x] Create the generic connector interface.
- [x] Implement the simulated HeatFix partner.
- [x] Implement the optional n8n dispatch path and test retry with a simulated webhook.
- [ ] Verify the approved case goes through the live n8n workflow in the demo environment.
- [x] Add an idempotency key so retries cannot create duplicate jobs.
- [x] Display the received job in a basic partner dashboard.
- [x] Test retrying the same sharing approval.

Do not begin P1 work until this milestone is reliable.

## P0 - Complete the repair loop

- [x] Add backend endpoints for partner acceptance, rejection and slot offers.
- [ ] Add accept, reject and offer-slot controls to the HeatFix inbox.
- [ ] Display slots in the tenant portal.
- [x] Validate resident identity and slot selection in the booking API.
- [ ] Add a resident confirmation step and show the booked appointment returned by the API.
- [x] Persist the selected appointment.
- [x] Accept partner start and completion actions through the HeatFix API.
- [x] Attach a synthetic repair report and invoice through the HeatFix API.
- [x] Link the appointment, completion and invoice to the original case and unit.
- [ ] Build the property-manager/unit view.
- [x] Display the persisted timeline after the initial partner handoff.
- [ ] Refresh the resident timeline as the case progresses and show it in the manager view.
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
- [x] Define timeout, rejection and unavailable-provider behavior.
- [x] Trace every request and callback to the original case.
- [x] Create `Docs/connector-spec.md`.
- [x] Export the approved-case n8n workflow with placeholders.
- [x] Load configured backend and connector secrets from the environment.

## P0 - Tests and demo readiness

- [x] Test case creation and correct unit association.
- [x] Test persistence across backend restarts.
- [x] Test approval records and shared fields.
- [x] Test duplicate partner-job submission.
- [x] Test slot selection and appointment persistence.
- [x] Test valid and invalid state transitions.
- [x] Test duplicate and invalid partner callbacks.
- [x] Test repair completion and invoice linking across retries and restart.
- [x] Test unavailable-provider escalation.
- [ ] Rehearse the entire typed workflow repeatedly.
- [x] Add real startup commands to `readme.md`.
- [ ] Create `Docs/demo-script.md`.
- [ ] Tag the first reliable typed version as `demo-p0`.

## P0 - Product / Frontend remaining work

1. **Booking loop.** Add HeatFix accept, reject and offer-slot controls. Refresh the resident's case so offered slots appear, require explicit confirmation, and show the appointment only after FastAPI confirms it. Show declines, unavailable providers and retryable failures clearly.
2. **Manager / unit view.** Show cases for the unit, who received the job, what was approved for sharing, the appointment and the backend event timeline. The unit case and event APIs already exist.
3. **Repair completion and invoice.** Wire the partner's start, complete and invoice actions. Show the returned documents on the resident and manager views. See the [connector contract](connector-spec.md).
4. **Intake handoff.** Coordinate with C on structured extraction and missing-detail prompts. Keep typed intake usable without the AI service.
5. **Demo and QA.** Write the walkthrough and rehearse from a fresh seed through report, approval, booking, completion and invoice. Include a retry and a reject or no-provider path, and verify the timeline matches persisted events.

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

## Next team handoffs

- **A - Frontend:** connect the inbox and tenant portal to the booking endpoints, then add the manager/unit view.
- **B - Backend:** the P0 case, booking, repair, invoice and failure APIs are ready for A and C. The [closed-case fixture](../shared/fixtures/case-closed.json) matches the unit history response for a completed and invoiced case.
- **C - Integrations:** verify live n8n dispatch and publish the structured intake contract.
