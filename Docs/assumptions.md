# Assumptions

The prototype simulates centrix and the partner. It is not connected to the real centrix API or a real contractor.

- **Data:** all people, properties, contact details and documents are synthetic (`backend/seed/seed.json`), modelled on the example payloads in the official Reltix brief.
- **centrix stand-in:** FastAPI + SQLite in `backend/` holds properties, units, residents, partners, cases, case events and sharing approvals.
- **Partner:** "HeatFix Aachen GmbH" is a simulated contractor served under `/partners/heatfix`. It keeps its own job table and only receives data through connector v1.
- **Routing.** FastAPI filters active, registered delivery providers by service, region and trigger. It ranks eligible contractors by distance, price and quality when at least two have matching details. The legacy WarmWerk seed entry in Köln has no connector registration and is excluded from routing. See the [ranking formula and fallback](connector-spec.md#contractor-ranking).
- **Data sharing:** only fields the resident approves are sent. `address`, `unit` and `issue` are required for a repair job; name, contact, heating type, access details and prior heating case are optional.
- **Notifications:** the in-app box always shows every notification; preferences only control the outbound noreply bot (email via SMTP, text via ntfy push or Telegram, simulated by default; ntfy topics are public, so each recipient gets an unguessable random topic). Residents default to their `preferred_contact` channel (`portal` means in-app only, `email` turns on email, `phone` turns on text messages), the owner to email for building incidents and invoice approvals. Messages never contain access details or other residents' data.
- **Access details:** the key-safe code is never shared automatically; the property manager releases it after booking.
- **n8n dispatch:** FastAPI sends the approved connector order after persisting sharing approval and records the job ID returned by n8n. A failed acknowledgment leaves the approval available for retry with the same idempotency key. See the [workflow contract](../n8n/README.md#backend-contract).
- **Provider-neutral dispatch:** the generic n8n workflow carries a case ID. The authorized backend gateway reads the persisted consent and routes the saved order to the registered delivery provider. The simulator serves new delivery manifests through the same job lifecycle.
- **Manager contractor setup.** The demo Manager view can register a simulated heating contractor, edit its coordinates, estimated price and 1–5 star rating, and open its inbox. Registrations live in SQLite and are active immediately. Properties, residents, manager roles and seed ratings are synthetic.
- **Manager repair overview:** `GET /api/manager/repairs` returns repair cases grouped by contractor across demo units. Cases without an available contractor appear under Unassigned. Each case shows its repair address and unit, using the saved order location after dispatch approval.
- **Portal notifications:** The resident bell uses the reporting resident’s saved acceptance, decline and completion events. The contractor bell uses that provider’s own jobs after approved dispatch. Open `#inbox/<provider-slug>` for a registered simulated delivery provider. `#inbox` remains the HeatFix view. Read markers are stored in the browser.
- **Structured intake:** the provider receives report text and an optional explicit hot-water answer. FastAPI validates suggestions and serves deterministic intake when provider settings or a valid response are unavailable. Describe and Review remain usable with manual entry. See the [intake contract](structured-intake-contract.md).
- **Availability and consent.** Availability preferences are part of the approved issue description. They are free text for the contractor. HeatFix generates two demo windows on the next UTC calendar day, 08:00–10:00 and 14:00–16:00 UTC. The portal can display them in the resident's time zone.
- **Booking.** Each job can have one appointment. The reporting resident confirms an offered slot using the synthetic resident ID, as in the sharing-approval flow. The mock keeps its own booking and confirms it over HTTP before centrix records the appointment.
- **Local callback secret.** With an empty `PARTNER_WEBHOOK_SECRET`, HeatFix and centrix share a random secret for the life of their single server process. Configure the same private environment value for separate workers or external callback senders.
- **HeatFix callback recovery (connector-spec wording for C).** The HeatFix job list and detail return `pending_callback` as `null` or `{"event_id":"…","type":"…"}`. Pending means HeatFix is waiting for acknowledgment. Centrix may already have committed the event. Send an empty `POST /partners/heatfix/connector/jobs/{job_id}/callbacks/{event_id}/retry` to redeliver the saved callback with its original ID, timestamp and data using the existing callback authentication. A successful receipt with the same event ID clears that callback and returns the current job (200). Replaying an acknowledged event also returns the current job. A failed or mismatched acknowledgment returns 502 and leaves the event pending. An unknown event or a job/event mismatch returns 404.
- **Repair records.** One confirmed appointment, one JSON repair report and one EUR invoice belong to the dispatch case and its unit. Receiving an invoice of at most €3,000 closes that case. After repair completion, a larger invoice puts the case in `AWAITING_INVOICE_APPROVAL`. The current API records a manager action and closes the case. It does not capture advance owner authorization. The organizer said that the owner–manager agreement sets the actual limit and the owner approves above it. €3,000 is our demo example. On upgrade, previously auto-closed invoices above the limit return to review with a migration event.
- **Dispatch retries.** The backend saves the approved outgoing order alongside consent before contacting the partner. A retry sends that snapshot, even if resident contact details or unit history have since changed. Pending approvals created on older versions acquire a snapshot on their first retry.
- **Human review.** Residents and the manager use simulated roles in the local demo. The manager can explicitly take over a declined, failed or unmatched repair through the case API. This records a manager timeline event. Further follow-up is manual.
- **Building heating.** Two distinct units at one property reporting loss of heat within an inclusive 24-hour UTC window indicate a *possible* shared outage. The demo assumes a common heating system and one servicing partner per building. The rule uses open reports, an explicit `no_heat` symptom or a direct typed statement such as the portal's “No heat at all”. An unresolved case with a partial or ambiguous symptom can proceed individually.
- **Building consent.** An existing approved repair takes the call-out. Otherwise the first resident to approve becomes the dispatch contact. A linked resident's report, contact details and documents remain private to their own case. The shared timeline carries the repair status and the booked window. Only the dispatch case can book or approve an invoice. Already-issued independent jobs from older data require manual reconciliation.
- **Partner registration.** Local JSON manifests describe simulated providers. Registration and discovery run offline. Internet offers, signatures and activation remain later steps in the connector design.
- **Voice dictation.** Selecting Transcribe sends the recorded clip to the selected speech-to-text provider (OpenAI by default or ElevenLabs Scribe v2). The app uses the editable transcript as report input and does not save the audio to the case. Transcription does not create a case or dispatch a job.

## Resident profile API

`PATCH /api/units/{unit_id}/residents/{resident_id}/profile` saves edits to the resident in SQLite. The required `acting_resident_id` simulates identity for the demo, like the resident ID on a slot selection. The path identifies the resident and their unit. IDs, move-in date and access details are read-only. The tenant can save their address, unit label and heating type for repair handoff. These are tenant-specific values. Property and unit IDs and building records stay linked to the original case. For an edited address, routing matches the city at the end of the address against registered service regions. Case and accents are ignored. An unmatched address leaves the case without a contractor. An existing approval and its saved order retain the original recipient.

Send at least one of `name`, `email`, `phone`, `preferred_contact`, `address`, `unit` or `heating`. Omit fields to keep their values. Each supplied value must be a nonblank string. The API trims surrounding whitespace. Names allow up to 120 characters. Email accepts an ASCII mailbox with a dotted domain, up to 254 characters. Phone accepts 7–15 digits in up to 40 characters, with an optional leading `+`, spaces, dots, hyphens and parenthesized groups. The supported preferences are `portal` (in-app only), `email` and `phone` (text messages from the noreply bot, delivered through ntfy or Telegram; see the README). Address, unit and heating accept up to 200, 80 and 120 characters, respectively. When no tenant-specific value exists, the portal and connector use the property record.

For example, send this body to `PATCH /api/units/unit_4b/residents/c_202/profile` on the seeded demo.

```json
{"acting_resident_id":"c_202","phone":"+49 151 00000001"}
```

HTTP 200 returns the complete resident object used in `GET /api/units/unit_4b/context` under `residents[]`. The portal uses this response in the profile and sharing preview. Repeating the PATCH returns the same values.

```json
{
  "id": "c_202",
  "unit_id": "unit_4b",
  "name": "Lena Hoffmann",
  "email": "lena@example.com",
  "phone": "+49 151 00000001",
  "preferred_contact": "portal",
  "move_in": "2025-03-01"
}
```

| Example request | HTTP | Response detail |
| --- | --- | --- |
| Use `"acting_resident_id":"c_203"` to edit `c_202` | 403 | `{"detail":"only the resident can edit their profile"}` |
| Send the sample body to `/api/units/unit_2a/residents/c_202/profile` | 404 | `{"detail":"resident not found for this unit"}` |
| Send only `{"acting_resident_id":"c_202"}` | 422 | `{"detail":"supply at least one profile field"}` |
| Send `{"acting_resident_id":"c_202","unit_id":"Changed"}` | 422 | FastAPI validation error in `detail[]` with `loc: ["body","unit_id"]` and `type: "extra_forbidden"` |

A profile save updates only the resident row. Cases, consent, dispatch and timeline events each retain their own API actions. A contact preference alone sends no message. For C, the existing `name` approval shares the current name and the existing `contact` approval shares the current email and phone together. Both use the values at approval time. A dispatch retry reuses the saved order payload and idempotency key.

In the resident portal, **Your home → Edit my details** opens an inline form. Save sends the edited fields and keeps the report mounted, including its review text, case ID and sharing selections. Cancel discards the draft. A failed save leaves the form open for correction or retry. After a failed PATCH, a new approval checks the saved profile in case the server committed the change before the reply was lost.

Approval waits for an in-flight profile save. Changing a value included in the sharing preview clears the approval checkbox. Heating type starts selected when it is optional and on file. The tenant can uncheck it before approval. A preference change leaves the checkbox as it was. The first dispatch attempt captures the displayed values and approval body. If the outcome is uncertain, the portal waits for evidence of recorded consent before allowing another profile edit. Once consent is recorded, the resident can edit their profile while a retry continues to use the captured preview and saved order.

Fixture mode uses a tab-local copy of the seeded resident for the home panel, consent preview and new HeatFix jobs. With session storage available, profile edits survive a reload in the same tab. Fixture reports and jobs follow their existing page lifetime. Each job keeps the values approved when it was created. A fresh browser session starts with the checked-in synthetic resident.
