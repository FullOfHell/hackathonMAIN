# Assumptions

The prototype simulates centrix and the partner. It is not connected to the real centrix API or a real contractor.

- **Data:** all people, properties, contact details and documents are synthetic (`backend/seed/seed.json`), modelled on the example payloads in the official Reltix brief.
- **centrix stand-in:** FastAPI + SQLite in `backend/` holds properties, units, residents, partners, cases, case events and sharing approvals.
- **Partner:** "HeatFix Aachen GmbH" is a simulated contractor served under `/partners/heatfix`. It keeps its own job table and only receives data through connector v1.
- **Routing:** deterministic: service type, then region, then active; tie-break by name. A second partner (Köln) exists in seed data to show region filtering.
- **Data sharing:** only fields the resident approves are sent. `address`, `unit` and `issue` are required for a repair job; name, contact, heating type, access details and prior heating case are optional.
- **Access details:** the key-safe code is never shared automatically; the property manager releases it after booking.
- **n8n dispatch:** FastAPI sends the approved connector order after persisting sharing approval and records the job ID returned by n8n. A failed acknowledgment leaves the approval available for retry with the same idempotency key. See the [workflow contract](../n8n/README.md#backend-contract).
- **Availability and consent.** Availability preferences are part of the approved issue description. They are free text for the contractor. HeatFix generates two demo windows on the next UTC calendar day, 08:00–10:00 and 14:00–16:00 UTC. The portal can display them in the resident's time zone.
- **Booking.** Each job can have one appointment. The reporting resident confirms an offered slot using the synthetic resident ID, as in the sharing-approval flow. The mock keeps its own booking and confirms it over HTTP before centrix records the appointment.
- **Local callback secret.** With an empty `PARTNER_WEBHOOK_SECRET`, HeatFix and centrix share a random secret for the life of their single server process. Configure the same private environment value for separate workers or external callback senders.
- **Repair records.** One confirmed appointment, one JSON repair report and one EUR invoice belong to a repair case. The unit history looks them up through that case. Completion and invoicing are separate partner actions. The case closes when the invoice is recorded.
- **Dispatch retries.** The backend saves the approved outgoing order alongside consent before contacting the partner. A retry sends that snapshot, even if resident contact details or unit history have since changed. Pending approvals created on older versions acquire a snapshot on their first retry.
- **Human review.** Residents and the manager use simulated roles in the local demo. The manager can explicitly take over a declined, failed or unmatched repair through the case API. This records a manager timeline event. Further follow-up is manual.
