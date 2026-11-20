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
- [x] Add accept, reject and offer-slot controls to the HeatFix inbox.
- [x] Display slots in the tenant portal.
- [x] Validate resident identity and slot selection in the booking API.
- [x] Add a resident confirmation step and show the booked appointment returned by the API.
- [x] Persist the selected appointment.
- [x] Accept partner start and completion actions through the HeatFix API.
- [x] Attach a synthetic repair report and invoice through the HeatFix API.
- [x] Link the appointment, completion and invoice to the original case and unit.
- [x] Build the property-manager unit view with cases, sharing approvals and confirmed appointments.
- [x] Display the persisted timeline after the initial partner handoff.
- [x] Refresh the resident timeline through booking and show it in the manager view.
- [x] Wire repair start, completion and synthetic invoice submission into the HeatFix inbox.
- [x] Expose the saved pending callback on HeatFix job reads and support retry by job and event ID after a restart.
- [x] Show the repair outcome and linked invoice in resident and manager views.
- [x] Drive live case progress from backend responses and the persisted timeline.

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
- [x] Rehearse booking, confirmation retry and partner rejection in the browser.
- [x] Test valid and invalid state transitions.
- [x] Test duplicate and invalid partner callbacks.
- [x] Test repair completion and invoice linking across retries and restart.
- [x] Verify that concurrent retries after an outage or lost acknowledgment produce one document and one corresponding case transition.
- [x] Test unavailable-provider escalation.
- [x] Verify the typed report-to-invoice flow in the browser against local FastAPI and offline fixtures.
- [ ] Rehearse the full typed demo with live n8n enabled.
- [x] Add real startup commands to `readme.md`.
- [ ] Create `Docs/demo-script.md`.
- [ ] Tag the first reliable typed version as `demo-p0`.

## P0 - Product / Frontend remaining work

1. **Intake handoff.** Connect structured extraction when C publishes the API. Typed intake already works with an optional hot-water follow-up.
2. **Demo and QA.** Rehearse from a fresh seed with live n8n enabled. Include a retry and a reject or no-provider path, and verify the timeline matches persisted events.
3. **A — HeatFix inbox recovery.** Read `pending_callback` from each job on load or refresh. When present, show “Retry delivery” and POST the event ID to the retry endpoint with an empty body. Use the returned job on success and refresh after a 502. A job's local status can advance before centrix acknowledges its callback.

## P1 - Differentiators

Backend work is underway on `backend/P1` while C finishes P0 intake and live n8n verification. Keep the typed P0 checkpoint as the integration gate for the demo.

- [x] B: detect loss of heating across two distinct units within 24 hours, reuse one consented job and update both case timelines.
- [ ] A: show the shared repair and appointment on both unit screens. Rehearse two reports and one HeatFix inbox entry on the demo stack.
- [ ] C: deliver the simulated text-message outbox and one-click slot confirmation on the same case. Use the case timeline for building updates and the dispatch case for slot selection.
- [x] B: hold invoices above €3,000 for manager approval and audit the approval. Exactly €3,000 closes automatically.
- [ ] A: wire the manager approval control to `POST /api/cases/{id}/approve-invoice` and rehearse €3,000.01.
- [x] B: register a simulated internet provider through a capabilities manifest and document the move-in → offer → contract design.
- [x] B: handle partner rejection or unavailability with human escalation.
- [x] B: include the approved previous repair's case ID and date as source attribution.
- [ ] (Lower priority) Add a second simulated heating provider without changing case-domain logic.
- [ ] Include relevant caretaker or access information; never share a key-safe code automatically.
- [ ] Preserve a complete portal fallback when n8n, OpenAI or network access fails.
- [ ] Support an optional repair photo; AI may describe it but may not diagnose the fault.

## P2 - Optional; skip if the demo is at risk

- [ ] Full internet move-in flow end to end (beyond registration and spec).
- [ ] Send real SMS/email (the P1 outbox is simulated).
- [ ] Add more complex provider optimization.
- [ ] Add operational analytics or dashboards.
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

- **A - Frontend:** connect structured extraction when ready and rehearse the full browser flow.
- **B - Backend:** P1 adds building repair progress on each case, manager invoice approval, and partner discovery. Demo the two seeded units first and keep the P0 typed single-unit flow as the fallback. See the [connector contract](connector-spec.md).
- **C - Integrations:** verify live n8n dispatch and publish the structured intake contract.
- **C — Connector documentation:** add the [HeatFix callback recovery wording](assumptions.md) to the callback section of the connector spec.
