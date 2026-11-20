# Project TODO

This checklist turns the project plan into an execution order for the three-person team. Complete the P0 workflow before starting P1. P2 is optional and should not put the demo at risk.

**Current demo status.** The typed report-to-invoice flow, structured intake, and optional voice dictation are on `main`. The typed flow has passed a local browser rehearsal. Live n8n, model-assisted intake, and audio transcription still need verification with the demo credentials.

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
- [x] Ask one question at a time for missing intake details and allow optional questions to be skipped.
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

- [x] Define the [structured intake contract](structured-intake-contract.md) and implement `POST /api/intake/extract`.
- [x] Suggest symptoms, priority and availability in an editable review. Validate model output in FastAPI.
- [x] Ask for missing details and keep deterministic and manual intake available without OpenAI.
- [x] Show a fixed safety message and pause routine submission for a possible gas leak.
- [x] Keep booking, repair and invoice status tied to persisted backend events.
- [ ] C: verify one synthetic report returns `source: "model"` with the demo OpenAI credentials, then confirm the typed fallback still works with the model disabled.

### Optional voice dictation

- [x] Add a 30-second recorder, an explicit transcription action and an editable transcript in Report.
- [x] Verify discard, failed-upload retry and transcript review with mocked responses. Transcription leaves case creation and sharing approval to the existing workflow.
- [ ] A + C: set `OPENAI_API_KEY` and `OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe` in `backend/.env`, restart FastAPI, and verify one fictional recording end to end with the live provider.

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
- [x] Rehearse the typed portal against live FastAPI on a fresh synthetic SQLite database with external services disabled. Repeating the minimum-field approval returned the same HeatFix job. After a backend restart the appointment, repair report, €125 invoice and all 12 actor-stamped events still belonged to the original case and unit. A separate case remained `DECLINED`.
- [x] Rehearse the full typed demo against C’s published provider-neutral workflow on a local n8n instance. The authenticated webhook created one job. A real webhook replay returned the same job with `duplicate: true`. A third execution dispatched the separate case used for rejection.
- [ ] C: repeat in the shared demo environment and record the execution and case/job IDs in the checkpoint PR.
- [x] Add real startup commands to `readme.md`.
- [ ] Create `Docs/demo-script.md`.
- [ ] Tag the first reliable typed version as `demo-p0`.

## P0 - Product / Frontend handoff

1. **Shared demo rehearsal.** Repeat the typed flow from a fresh seed using the published n8n workflow. Include a retry and a rejection or no-provider path, verify the persisted timeline, and record the execution and matching case and job IDs in the checkpoint PR.
2. **Optional dictation.** Pair with C for the live microphone check after the key is configured. Keep typed intake available for the rehearsal.
3. **A — HeatFix inbox recovery.** Read `pending_callback` from each job on load or refresh. When present, show “Retry delivery” and POST the event ID to the retry endpoint with an empty body. Use the returned job on success and refresh after a 502. A job's local status can advance before centrix acknowledges its callback.

## P1 - Differentiators

The shared-repair, high-value invoice, and partner-discovery backends are on `main`. The next browser milestone is showing one HeatFix job and appointment across two resident cases.

- [x] B: detect loss of heating across two distinct units within 24 hours, reuse one consented job and update both case timelines.
- [ ] A: add the 4B / 2A demo selector and shared-repair cards. Let the dispatch case confirm the slot and show the confirmed appointment read-only on the linked case. Rehearse two reports and one HeatFix inbox entry.
- [ ] C: deliver the simulated text-message outbox and one-click slot confirmation on the same case. Use the case timeline for building updates and the dispatch case for slot selection.
- [x] B: hold post-completion invoices above €3,000 for manager approval and audit that action. Exactly €3,000 closes automatically.
- [ ] A: wire and label the post-completion manager approval control for `POST /api/cases/{id}/approve-invoice`. Add a €3,000.01 demo invoice option and verify exactly €3,000 still closes automatically.
- [x] B: register a simulated internet provider through a capabilities manifest and document the move-in → offer → contract design.
- [x] B: handle partner rejection or unavailability with human escalation.
- [x] B: include the approved previous repair's case ID and date as source attribution.
- [ ] (Lower priority) Add a second simulated heating provider without changing case-domain logic.
- [ ] Include relevant caretaker or access information; never share a key-safe code automatically.
- [x] Provide deterministic and manual intake when OpenAI is unavailable, plus direct HeatFix dispatch when n8n is disabled.
- [ ] Support an optional repair photo; AI may describe it but may not diagnose the fault.

## Organizer follow-ups outside the typed P0 checkpoint

- [ ] Model the spending limit from the owner–manager agreement and record advance owner authorization for above-limit work. The current high-invoice manager action happens after completion. Allow the owner to compare quotes when the agreement or circumstances call for them.
- [x] B implemented resident self-service for name, email, phone and contact preference. The API tests cover partial saves, restart persistence and partner consent across edits and dispatch retries.
- [x] B connected **Edit my details** in the resident portal. Browser checks covered Cancel, a failed save and correction during report review, selected-field consent, a lost HeatFix acknowledgment, reload persistence and fixture jobs before and after a profile edit. See the [profile contract and portal behavior](assumptions.md#resident-profile-api).
- [ ] Give the manager a follow-up flag for a received job with no partner response. The organizer specified no response deadline. Existing uncertain-dispatch retries reuse the original key.

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

- **A - Frontend:** surface and rehearse pending HeatFix callback retries, build the two-unit browser demo, and connect manager invoice approval. Own the browser rehearsal and pitch.
- **B - Backend:** support the two-unit rehearsal and verify that both timelines follow one consented job and booking. See the [connector contract](connector-spec.md).
- **C - Integrations:** verify n8n dispatch in the shared demo and check the configured OpenAI model path. Pair with A on dictation verification, then implement the simulated text-message outbox and booking link.
- **C — Connector documentation:** add the [HeatFix callback recovery wording](assumptions.md) to the callback section of the connector spec.
