# Project TODO

This checklist turns the project plan into an execution order for the three-person team. Complete the P0 workflow before starting P1. P2 is optional and should not put the demo at risk.

**Current demo status.** The typed report-to-invoice flow, structured intake, voice dictation, contractor management and portal bells are on `main` in the release checked at `55da0ba`. That release passed 176 backend tests, 10 frontend tests, the production build, and an isolated browser rehearsal across all three roles. Live checks on the shared n8n and speech provider credentials are still open. The required availability gate and the fallback for older reports were tested in Chrome as local changes and still need a release.

## Immediate setup

- [x] Confirm team ownership:
  - A - Product/Frontend: tenant, partner and manager interfaces; demo flow.
  - B - Backend/Domain: FastAPI, SQLite, state machine and tests.
  - C - AI/Integrations: extraction, partner connector, n8n and connector documentation.
- [x] Define the shared contracts for unit context, case creation, case states, partner jobs and callbacks.
- [x] Commit representative JSON fixtures used by all three contributors.
- [x] Create `frontend/`, `backend/`, `n8n/` and test directories.
- [x] Add `.gitignore`, `.env.example` and initial development commands.
- [x] Develop the initial slices on feature branches.

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
  - `SCHEDULED`
  - `IN_PROGRESS`
  - `COMPLETED`
  - `CLOSED`
- [x] Support the alternate `SLOTS_OFFERED` path and explicit failure states with validated transitions.
- [x] Record every transition with actor and timestamp.
- [x] Implement `GET /api/units/{unit_id}/context`.
- [x] Implement case creation, retrieval and event-history endpoints.
- [x] Implement sharing approval and slot-selection endpoints.
- [x] Implement the partner-event callback endpoint.
- [x] Verify cases and timelines survive a backend restart.

## P0 - First vertical slice

Target milestone:

`resident submits issue -> persistent case created -> sharing approval recorded -> mock partner receives exactly one job`

- [x] Build the typed report wizard with Describe, Summary and Approve steps.
- [x] Apply the cream and plum theme, consistent dropdowns, and distinct status colors across the portal.
- [x] Provide a fixture-backed report and inbox for offline walkthroughs.
- [x] Pre-fill address, unit, heating type and resident context.
- [x] Ask one question at a time for missing intake details and allow optional questions to be skipped.
- [x] Show an editable issue summary, symptoms and a separate Low, Normal or High priority field.
- [x] Let the tenant return from sharing to edit the draft without creating a duplicate case.
- [x] Name the assigned contractor and show the fields to be shared. Select heating type by default when it is optional and available.
- [x] Recheck the named recipient before dispatch and require fresh approval if it changes.
- [x] Persist explicit consent and show Undo or Send now for final dispatch.
- [x] Create the generic connector interface.
- [x] Implement the simulated HeatFix partner.
- [x] Implement the optional n8n dispatch path and test retry with a simulated webhook.
- [x] Add an idempotency key so retries cannot create duplicate jobs.
- [x] Display the received job in a basic partner dashboard.
- [x] Test retrying the same sharing approval.

Do not begin P1 work until this milestone is reliable.

## P0 - Complete the repair loop

- [x] Add backend endpoints for partner acceptance, rejection and slot offers.
- [x] Add accept and reject controls, booking from saved tenant times, and a time-offer fallback when an accepted job has no matching saved slots.
- [x] Place the weekly availability table inside report review. Keep the scroll position when selecting a slot and keep the table scrollable on narrow screens.
- [x] Require at least one saved future unbooked slot across the three displayed weeks in connected mode.
- [x] Verify in Chrome that an empty or unsaved calendar blocks sharing, a saved slot in another week counts, and removing the last slot blocks sharing again.
- [x] Validate resident identity and slot selection in the booking API.
- [x] Let the tenant confirm a contractor-offered slot. Show the assigned contractor on the report confirmation and display the booked appointment with a date and local time range.
- [x] Persist the selected appointment.
- [x] Accept partner start and completion actions through the HeatFix API.
- [x] Attach a synthetic repair report and invoice through the HeatFix API.
- [x] Link the appointment, completion and invoice to the original case and unit.
- [x] Build collapsible manager repair groups by contractor with address, unit, reported time, priority, sharing approvals, confirmed appointments and timeline.
- [x] Show a simplified persisted timeline with tenant, contractor and repair milestones. Refresh it through booking and show it in Manager.
- [x] Wire repair start, completion and synthetic invoice submission into the HeatFix inbox.
- [x] Expose pending callbacks in job reads, support the retry endpoint, and show an inbox retry for acceptance.
- [ ] Surface the generic callback retry control in the portal for other pending event types.
- [x] Show the repair outcome and linked invoice in resident and manager views.
- [x] Drive live case progress from backend responses and the persisted timeline.
- [x] Submit draft saves, explicit transcription, profile saves, contractor registration, bookings, completions and invoices immediately.

## P0 - Contractor management

- [x] Register a second simulated heating contractor by name, city and inbox slug without changing the case flow.
- [x] Switch inboxes by contractor name from the header and show **Open inbox** on each manager row.
- [x] Match by saved repair address and usable appointment times. Try the same city first, then other cities in the same country in a stable random order per case.
- [x] Align the manager row actions and deactivate a contractor after a confirmed deletion. Hide its assigned repairs in Manager and retain case history.

## P0 - Notifications

- [x] Show accepted, declined and completed repair notifications in the tenant bell.
- [x] Show new repair notifications only in the assigned contractor’s inbox after the tenant approves sharing.
- [x] Mark a clicked notification as read and keep the panel open. Persist read state in the browser.

## P0 - AI intake

- [x] Define the [structured intake contract](structured-intake-contract.md) and implement `POST /api/intake/extract`.
- [x] Suggest symptoms and priority in an editable review. Keep any grounded availability notes and use the timetable for actual booking. Validate model output in FastAPI.
- [x] Ask for missing details and keep deterministic and manual intake available without OpenAI.
- [x] Show a fixed safety message and pause routine submission for a possible gas leak.
- [x] Keep booking, repair and invoice status tied to persisted backend events.
- [ ] Verify one synthetic report returns `source: "model"` with the demo OpenAI credentials, then confirm the typed fallback still works with the model disabled.

### Optional voice dictation

- [x] Add a 30-second recorder, an explicit transcription action and an editable transcript in Report.
- [x] Verify discard, failed-upload retry and transcript review with mocked responses. Transcription leaves case creation and sharing approval to the existing workflow.
- [x] Support OpenAI and ElevenLabs Scribe v2 through the same transcription API.
- [ ] Select the demo provider, restart FastAPI, and verify one fictional live recording. See [dictation setup](../readme.md#backend-configuration).

## P0 - Connector quality and security

- [x] Version the connector schema.
- [x] Document required and optional partner fields.
- [x] Add signed or shared-secret partner callbacks.
- [x] Reject invalid callback signatures.
- [x] Deduplicate repeated callback events.
- [x] Define timeout, rejection and unavailable-provider behavior.
- [x] Trace every request and callback to the original case.
- [x] Create `Docs/connector-spec.md`.
- [x] Export the provider-neutral case-ID dispatch workflow and the legacy HeatFix workflow with placeholders.
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
- [ ] Repeat the n8n rehearsal in the shared demo environment and record the execution and matching case and job IDs.
- [x] Add real startup commands to `readme.md`.
- [x] Write the [three-minute demo script](demo-script.md).
- [x] Tag the first reliable typed version as `demo-p0`.

## P1 - Differentiators

The shared-repair, high-value invoice, and partner-discovery backends are on `main`. The next browser milestone is showing one HeatFix job and appointment across two resident cases.

- [x] Detect loss of heating across two distinct units within 24 hours, reuse one consented job and update both case timelines.
- [ ] Add the 4B / 2A demo selector and shared-repair cards. Let the dispatch case confirm the slot and show the confirmed appointment read-only on the linked case. Rehearse two reports and one HeatFix inbox entry.
- [x] Persist a simulated text and email outbox with links to My cases and optional live transports.
- [ ] Verify live email or phone delivery with demo credentials if it appears in the pitch.
- [ ] Add a dedicated one-click slot confirmation link.
- [x] Hold post-completion invoices above €3,000 for manager approval and audit that action. Exactly €3,000 closes automatically.
- [ ] Wire and label the post-completion manager approval control for `POST /api/cases/{id}/approve-invoice`. Add a €3,000.01 demo invoice option and verify exactly €3,000 still closes automatically.
- [x] Register a simulated internet provider through a capabilities manifest and document the move-in → offer → contract design.
- [x] Handle partner rejection or unavailability with human escalation.
- [x] Include the approved previous repair's case ID and date as source attribution.
- [x] Support consented access details in the connector payload.
- [ ] Surface caretaker and access details as optional fields in the tenant sharing preview.
- [x] Provide deterministic and manual intake when OpenAI is unavailable, plus direct HeatFix dispatch when n8n is disabled.
- [ ] Support an optional repair photo; AI may describe it but may not diagnose the fault.

## Organizer follow-ups outside the typed P0 checkpoint

- [ ] Model the spending limit from the owner–manager agreement and record advance owner authorization for above-limit work. The current high-invoice manager action happens after completion. Allow the owner to compare quotes when the agreement or circumstances call for them.
- [x] Support resident self-service for name, email, phone, contact preference, address, unit and heating type.
- [x] Keep the report open while profile edits are saved and reset consent when shared values change. Preserve the approved snapshot on dispatch retries. See the [profile contract](assumptions.md#resident-profile-api).
- [ ] Give the manager a follow-up flag for a received job with no partner response. The organizer specified no response deadline. Existing uncertain-dispatch retries reuse the original key.

## Final hand-in

- [ ] Release the locally verified availability requirement and contractor offer fallback.
- [ ] Confirm the pushed code matches the demonstrated version and judges can access it.
- [ ] Tag the final demonstrated commit as `demo-final`.
- [x] Document startup and the current repair walkthrough in the README.
- [x] Document the connector, demo assumptions and optional integrations.
- [x] Export n8n workflows with credential placeholders.
- [ ] Record and edit the three-minute pitch video.
- [ ] Show one stable differentiator after the complete P0 flow.
- [ ] Submit the project, code and video before the event deadline.
