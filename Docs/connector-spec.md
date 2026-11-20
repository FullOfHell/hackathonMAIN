# Service connector v1.0

The centrix stand-in owns cases and appointments. Delivery providers own their jobs, appointment offers and bookings. They exchange JSON over HTTP. HeatFix is the heating example in [the shared fixtures](../shared/fixtures/).

The SQLite registry loads new simulated partners from `backend/seed/partner-registrations/` at startup and preserves existing routing settings. Try `GET /api/integrations/partners?category=internet&region=Aachen&trigger=tenant.move_in` to discover FibreNet. Its capabilities describe the proposed move-in offer and signed contract to be written back to the unit. [FibreNet manifest](../backend/seed/partner-registrations/fibrenet.json)

## Resident and partner screens

| Action | Request | Result |
| --- | --- | --- |
| Report availability | `POST /api/cases` with optional `availability_preferences` (array of strings, default `[]`) | The case stores the preferences. Include them in the preview of the `issue` field the resident approves for sharing. |
| Accept or reject | `POST /partners/heatfix/connector/jobs/{job_id}/accept` or `/reject`, empty body | Acceptance appears as `partner.accepted` in the case timeline. Rejection moves the case to `DECLINED`. |
| Offer times | `POST /partners/heatfix/connector/jobs/{job_id}/offer-slots`, empty body, after acceptance | HeatFix returns the job and two slots. The callback moves the case to `SLOTS_OFFERED`. |
| Read the offer or appointment | `GET /api/cases/{case_id}` | `slots` is an array of objects with `slot_id`, `start`, and `end`. It starts empty. `appointment` starts as `null` and contains those same fields plus `case_id` and `booked_at` after booking. All times include a UTC offset or `Z`. |
| Confirm a time | `POST /api/cases/{case_id}/select-slot` with `{"slot_id":"<offered ID>","resident_id":"c_202"}` | Returns the case in `SCHEDULED` after partner confirmation. Repeating the selection returns the same appointment. |
| Start work | `POST /partners/heatfix/connector/jobs/{job_id}/start`, empty body | Moves the scheduled case to `IN_PROGRESS`. |
| Complete repair | `POST /partners/heatfix/connector/jobs/{job_id}/complete` with `{"summary":"Replaced the radiator valve and verified heating."}` | Stores a synthetic completion report and moves the case to `COMPLETED`. |
| Attach invoice | `POST /partners/heatfix/connector/jobs/{job_id}/invoice` with `invoice_number`, `description`, `amount_cents` and `currency` | Stores the EUR invoice. Up to and including 300,000 cents closes the case. A higher amount sets `AWAITING_INVOICE_APPROVAL` in both case and unit reads. |
| Approve a flagged invoice | `POST /api/cases/{case_id}/approve-invoice`, empty body | The simulated manager records `invoice.manager_approved` and closes the case. A retry returns the closed case. An invoice outside review returns 409. |
| Read the unit outcome | `GET /api/units/{unit_id}/cases` and `GET /api/cases/{case_id}/events` | The case includes its appointment, completion report and invoice. Each document has its case ID, unit ID and a case-scoped JSON download URL. The timeline returns events in append order. |

Use the `resident_id` and `slot_id` from the case being displayed. A different resident receives 403. A slot outside the case's offer receives 422. Changing an existing booking to another offered slot returns 409. If booking returns 502, the resident can retry the same slot. The case and its event history show the persisted outcome.

Both document fields start as `null`. The document download returns 404 until its corresponding callback succeeds. The dashboard can repeat an action with the same content after a lost reply. Changing a previously submitted report or invoice returns 409. See the [repair callback examples](../shared/fixtures/partner-repair-events.json) and [closed case](../shared/fixtures/case-closed.json).

## Partner jobs and bookings

`POST /connector/jobs` accepts the existing job envelope under a partner's base URL. It requires `request_id` (the case ID), `idempotency_key`, `service_type`, `property`, `issue`, `sharing`, and `callback_url`. The schema version defaults to `1.0`. The required approved fields are `address`, `unit` and `issue`. The issue includes description, symptoms, priority and availability preferences. Name, contact, heating type, access details and previous repair context each require the corresponding approval. The optional `resident` block defaults to an empty object. Job creation returns 201, or 200 with the existing job ID on retry.

Centrix calls `POST /connector/jobs/{job_id}/book` with `{"slot_id":"<offered ID>"}`. A successful response contains the matching `job_id`, `slot_id` and `status` of `scheduled`. HeatFix accepts one booking per job and returns the same confirmation on retry. The partner dashboard can retrieve `slots` and `booked_slot_id` from `GET /partners/heatfix/connector/jobs/{job_id}`.

## Callbacks into centrix

HeatFix posts to the job's `callback_url` with the `X-Partner-Secret` header. Both sides use `PARTNER_WEBHOOK_SECRET`. HeatFix sends credentials only to the configured `PUBLIC_BACKEND_URL` origin and disables redirects. The receiver at `POST /api/integrations/partner-events` expects `schema_version`, `event_id`, `request_id`, `job_id`, `occurred_at` and `type`. See the [callback fixture](../shared/fixtures/partner-event.json).

| Type | Data | Persisted result |
| --- | --- | --- |
| `accepted` | Optional object | Records the first acceptance for a requested job. The case remains in `PARTNER_REQUESTED`. |
| `rejected` | Optional object | Transitions the requested case to `DECLINED`. |
| `slots_offered` | `data.slots` contains at least one slot, with unique IDs within the case and offset-aware start and end times | Stores the slots and transitions the requested case to `SLOTS_OFFERED` in one transaction. |
| `in_progress` | Empty object | Transitions a scheduled case to `IN_PROGRESS`. |
| `completed` | `data.summary` (1–2,000 characters) | Stores the repair report and transitions an in-progress case to `COMPLETED` in one transaction. |
| `invoice_ready` | `data.invoice_number` (1–80 characters), `description` (1–2,000 characters), `amount_cents` and `currency` | Requires the completion report. Stores one invoice and applies the centrix approval limit in the same transaction. |
| `failed` | `data.reason` (1–500 characters) | Moves a requested, offered, scheduled or in-progress repair to `FAILED` and records the reason in the timeline. |

A successful callback returns 200 with `event_id` and `duplicate`. HeatFix retains the original event ID and payload across delivery retries. Duplicate IDs produce no additional timeline entries or slots. Case status changes record the actor, timestamp and associated job ID. A callback with a missing or incorrect secret receives 401, an unknown case receives 404, and a mismatched job or invalid state transition receives 409. An unsupported type or invalid slot payload receives 422. Failed callbacks leave the event ID available for a corrected retry.

The mock partner returns 502 if callback delivery fails or the acknowledgment omits the matching event ID. Repeat the same partner action to deliver the saved event. A booking timeout or mismatched confirmation records `partner.booking_unconfirmed` on the case. Retrying the same resident selection reconciles a booking if the original HTTP reply was lost.

Reuse the original callback ID, timestamp and data for a retry. A conflicting replay returns 409. Upgrading an existing database preserves receipts and restores document payloads from stored reports and invoices. For older non-document receipts, only the original case, job, type and timestamp are available for comparison. A connector job key also belongs to one case. Reusing it for a different case returns 409.

## Building heating reports

`POST /api/cases` accepts the explicit `no_heat` symptom or the existing typed “No heat at all” report. Two open reports from distinct units in the same property within 24 hours produce a `building.outage_detected` event on each case. A case outside a group has `building_repair: null`. For a demo, report from `unit_4b` / `c_202` and `unit_2a` / `c_203`, then approve from either case. If HeatFix already has one job, the backend uses that job.

The dispatch case owns consent, callbacks, booking and documents. The other case enters `LINKED_TO_BUILDING_REPAIR`. Its resident can follow the shared job through `building_repair` in case and unit reads. The object includes `outage_id`, `is_dispatch_case`, confirmed `partner_job_id`, `repair_status`, `scope_confirmed` and the booked `appointment` window. Values dependent on approval, partner receipt or booking start as null. Resident identities, available slots and invoice downloads stay on the dispatch case.

The original approved order can carry `issue.repair_scope = "building_heating"`. For an existing order, HeatFix accepts an idempotent `PUT /connector/jobs/{job_id}/scope` with the original `request_id` and `scope: "building_heating"`. The acknowledgment repeats both fields and the job ID. A missing acknowledgment leaves `scope_confirmed` false. Retry the same job via `POST /api/cases/{case_id}/sync-building-repair`. A 502 means confirmation is still pending. If the original repair finishes before HeatFix confirms building scope, linked reports go to human review.

Linked timelines persist `building.repair_updated` on status changes. Shared closure closes linked reports, and a declined or failed dispatch moves them to human review. A linked resident can withdraw through the existing cancel endpoint. Before any dispatch, withdrawing the second distinct unit dissolves the group and records `building.outage_withdrawn` on remaining reports. With `prior_heating_case` approval, the job's optional `issue.previous_record.source_case_id` identifies the original unit record.

## Contractor shown before sharing

Heating reports use the tenant’s saved repair address when one is supplied. Include the city at the end, for example `Demo Street 15, 40210 Düsseldorf`. The portal sends `expected_partner_id` with sharing approval. A change to the recipient returns 409 until the tenant approves the current contractor. Consent and order retries keep the recipient already recorded.

## Failures and human review

| Situation | API behavior and next action |
| --- | --- |
| No eligible active partner | The new case enters `NO_PROVIDER_AVAILABLE`. The resident's report stays on the unit and sharing approval is unavailable. |
| Resident withdraws before sharing | `POST /api/cases/{case_id}/cancel` with `resident_id` returns `CANCELLED`. Repeating the withdrawal returns the same case. |
| Unconfirmed dispatch | A direct timeout, 5xx reply, invalid acknowledgment or unconfirmed n8n request returns 502. Repeat the original sharing approval to reconcile the job using the same key. Changing the approved field set returns 409. |
| Direct dispatch refused or partner unreachable | The API returns 502 and records the failure and `NEEDS_HUMAN_REVIEW` on the case. |
| Partner declines or cannot finish | Use `/reject` on a pending job, or `POST /partners/heatfix/connector/jobs/{job_id}/fail` with a `reason` while the job is active. The case records `DECLINED` or `FAILED`, respectively. |
| Manager takes ownership | `POST /api/cases/{case_id}/escalate`, empty body, moves a `DECLINED`, `FAILED` or `NO_PROVIDER_AVAILABLE` case to `NEEDS_HUMAN_REVIEW`. Repeating the action returns the same case. Other states return 409. |

For saved local demo jobs, HTTP callback URLs on `localhost` and `127.0.0.1` can share the configured callback destination when the port and callback path match. The simulator sends the callback to the configured Centrix URL.

## Adding a delivery provider

In the portal, open **Manager → Contractors → Add contractor** to register a simulated heating contractor without restarting FastAPI. Enter the company name, exact service region and a unique inbox slug. The saved contractor appears in the list with an **Open inbox** link. New cases use the usual service and region match, with the name as a tie-break.

The demo manager API lists active local delivery providers at `GET /api/manager/contractors`. `POST /api/manager/contractors` accepts `name`, `region` and `slug`, and returns 201 with `name`, `regions` and `slug`. The slug uses lowercase letters, digits and hyphen separators. A slug already in use returns 409. The portal form generates a local connector route and uses the built-in heating simulator.

Register another delivery provider with a connector v1 adapter to reuse the case state machine, consent validation, and n8n workflow.

1. Add a manifest in `backend/seed/partner-registrations/` with a unique `partner_id`, `kind: delivery`, a `base_url`, categories, regions, and the `maintenance.case_created` trigger. Restart FastAPI. A local `/partners/{slug}` base uses the built-in simulator. For an external provider, use the HTTPS base URL of a connector v1 adapter implementing job creation, any advertised actions, and authenticated callbacks. Put provider-specific API calls and credentials behind that adapter.
2. Declare `address`, `unit`, and `issue` as required. The manifest can also require or allow supported consent fields. FastAPI presents those fields and validates approval before persisting the order. If the new service needs fields or outcomes outside connector v1, it needs an extension to the contract.
3. Use either direct dispatch or the [provider-neutral n8n workflow](../n8n/README.md#provider-neutral-workflow). The same workflow forwards an approved case ID to a fixed gateway. FastAPI chooses the provider by category, region, activation and trigger, and the gateway reads that choice from the saved case. Its request accepts only the case ID. The partner still receives the v1 order and a stable idempotency key.

**Verify a new registration.** Use the manifest’s category as `issue_type` in the [case fixture](../shared/fixtures/case-create.json). Submit it to `POST /api/cases` for a unit in a covered region, confirm the expected provider was selected, then approve the fields returned in `sharing_request`. Check `{base_url}/connector/jobs` for the job. Replay the dispatch and confirm the job ID is reused. The [registration tests](../backend/tests/test_partner_registration.py) exercise this using temporary manifests for categories outside the bundled delivery demo.

## Adding an internet move-in offer

The registry also discovers FibreNet's simulated move-in offer. The offer lifecycle and service-contract write-back below are proposed. They are distinct from a support visit using the delivery contract above.

Connector v1 supports two partner kinds with the same envelope, security and idempotency rules:

| Kind | Example | Unit of work | Outcome written back to the unit |
| --- | --- | --- | --- |
| `delivery` | HeatFix (heating repair) | job → slots → booking → completion → invoice | appointment, repair report, invoice |
| `offer` | an internet provider | offer → resident accepts → contract signed | `service_contract` (as in the brief's example payload) |

### 1. Register the partner (capabilities)

A partner publishes `GET {base_url}/connector/capabilities`:

```json
{
  "schema_version": "1.0",
  "partner_id": "p_fibrenet",
  "kind": "offer",
  "categories": ["internet"],
  "regions": ["Aachen"],
  "triggers": ["tenant.move_in"],
  "required_fields": ["address", "unit", "move_in_date"],
  "optional_fields": ["name", "contact"],
  "events": ["offer_created", "contract_signed", "activation_scheduled", "failed"]
}
```

To register a category, add a JSON file with `name`, `base_url` and `capabilities` to `backend/seed/partner-registrations/` and restart the demo backend. The SQLite registry exposes active matches through `GET /api/integrations/partners?category=internet&region=Aachen&trigger=tenant.move_in`. The demo provider publishes `GET /partners/fibrenet/connector/capabilities`. Keep callback secrets in the environment. The shared manifest is in [the FibreNet registration](../backend/seed/partner-registrations/fibrenet.json).

### 2. Proposed trigger, consent and order

1. centrix fires `tenant.move_in` for a unit (brief's example event).
2. The resident sees the offer in the portal or as a text message, plus the exact fields to be shared (`address`, `unit`, `move_in_date`, optionally `name`, `contact`), and approves.
3. centrix sends `POST {base_url}/connector/orders` with the same envelope as jobs: `request_id`, `idempotency_key`, `service_type: "internet"`, the approved fields, `sharing.approved_fields`, `callback_url`.

### 3. Proposed callbacks and result

The partner posts `offer_created`, `contract_signed`, `activation_scheduled` or `failed` to the same `POST /api/integrations/partner-events` endpoint, with the same `X-Partner-Secret`, event-ID deduplication and 401/404/409/422 rules as above. `contract_signed` writes a `service_contract` to the unit:

```json
{
  "partner": "FibreNet Aachen",
  "category": "internet",
  "product": "Fibre 500",
  "status": "signed",
  "start": "2026-12-01",
  "monthly_price_eur": 34.99,
  "consent": { "data_shared": ["name", "address", "move_in_date"], "given_at": "2026-11-20T09:21:00Z", "channel": "portal" }
}
```

### What a new partner must provide

1. A capabilities document (kind, categories, regions, triggers, required/optional fields, events).
2. An order or job endpoint that accepts the v1 envelope and is idempotent on `idempotency_key`.
3. Signed callbacks to `callback_url` using only the documented event types.
4. Only the fields the resident approved; nothing else is sent.
