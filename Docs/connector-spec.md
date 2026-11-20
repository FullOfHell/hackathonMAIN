# Heating repair connector v1.0

The centrix stand-in owns cases and appointments. The simulated HeatFix contractor owns jobs, offers and bookings. They exchange JSON over HTTP. The examples live in [the shared fixtures](../shared/fixtures/).

## Resident and partner screens

| Action | Request | Result |
| --- | --- | --- |
| Report availability | `POST /api/cases` with optional `availability_preferences` (array of strings, default `[]`) | The case stores the preferences. Include them in the preview of the `issue` field the resident approves for sharing. |
| Accept or reject | `POST /partners/heatfix/connector/jobs/{job_id}/accept` or `/reject`, empty body | Acceptance appears as `partner.accepted` in the case timeline. Rejection moves the case to `DECLINED`. |
| Offer times | `POST /partners/heatfix/connector/jobs/{job_id}/offer-slots`, empty body, after acceptance | HeatFix returns the job and two slots. The callback moves the case to `SLOTS_OFFERED`. |
| Read the offer or appointment | `GET /api/cases/{case_id}` | `slots` is an array of objects with `slot_id`, `start`, and `end`. It starts empty. `appointment` starts as `null` and contains those same fields plus `case_id` and `booked_at` after booking. All times include a UTC offset or `Z`. |
| Confirm a time | `POST /api/cases/{case_id}/select-slot` with `{"slot_id":"<offered ID>","resident_id":"c_202"}` | Returns the case in `SCHEDULED` after partner confirmation. Repeating the selection returns the same appointment. |

Use the `resident_id` and `slot_id` from the case being displayed. A different resident receives 403. A slot outside the case's offer receives 422. Changing an existing booking to another offered slot returns 409. If booking returns 502, the resident can retry the same slot. The case and its event history show the persisted outcome.

## Partner jobs and bookings

`POST /connector/jobs` accepts the existing job envelope under a partner's base URL. It requires `request_id` (the case ID), `idempotency_key`, `service_type`, `property`, `issue`, `sharing`, and `callback_url`. The schema version defaults to `1.0`. The required approved fields are `address`, `unit` and `issue`. The issue includes description, symptoms, priority and availability preferences. Name, contact, heating type, access details and previous repair context each require the corresponding approval. The optional `resident` block defaults to an empty object. Job creation returns 201, or 200 with the existing job ID on retry.

Centrix calls `POST /connector/jobs/{job_id}/book` with `{"slot_id":"<offered ID>"}`. A successful response contains the matching `job_id`, `slot_id` and `status` of `scheduled`. HeatFix accepts one booking per job and returns the same confirmation on retry. The partner dashboard can retrieve `slots` and `booked_slot_id` from `GET /partners/heatfix/connector/jobs/{job_id}`.

## Callbacks into centrix

HeatFix posts to the job's `callback_url` with the `X-Partner-Secret` header. Both sides use `PARTNER_WEBHOOK_SECRET`. HeatFix sends credentials only to the configured `PUBLIC_BACKEND_URL` origin and disables redirects. The receiver at `POST /api/integrations/partner-events` expects `schema_version`, `event_id`, `request_id`, `job_id`, `occurred_at` and `type`. See the [callback fixture](../shared/fixtures/partner-event.json).

| Type | Data | Persisted result |
| --- | --- | --- |
| `accepted` | Optional object | Records the partner event. The case stays in its current state. |
| `rejected` | Optional object | Transitions the requested case to `DECLINED`. |
| `slots_offered` | `data.slots` contains at least one slot, with unique IDs within the case and offset-aware start and end times | Stores the slots and transitions the requested case to `SLOTS_OFFERED` in one transaction. |

A successful callback returns 200 with `event_id` and `duplicate`. HeatFix retains the original event ID and payload across delivery retries. Duplicate IDs produce no additional timeline entries or slots. Case status changes record the actor, timestamp and associated job ID. A callback with a missing or incorrect secret receives 401, an unknown case receives 404, and a mismatched job or invalid state transition receives 409. An unsupported type or invalid slot payload receives 422. Failed callbacks leave the event ID available for a corrected retry.

The mock partner returns 502 if callback delivery fails. Repeat the same partner action to deliver the saved event. A booking timeout or mismatched confirmation records `partner.booking_unconfirmed` on the case. Retrying the same resident selection reconciles a booking if the original HTTP reply was lost.
