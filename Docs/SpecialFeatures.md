# Optional differentiators

These features are intentionally secondary. Do not start them until the typed end-to-end P0 flow is repeatable and persisted.

## P1 candidates

### Context-aware repair history

Surface a relevant prior heating case with source attribution. Present it as context for the contractor, never as an AI diagnosis.

### Text-message channel (mentor: tenants mostly text and phone)

Send simulated SMS/email messages from a persisted outbox at each step, with one-click links to confirm a slot or view the case. Links call the same backend endpoints as the portal and continue the same case. No voice agent: Reltix already has one that auto-fills the app.

### Transparent partner selection

Show why a contractor was selected: supported service, service region, capacity, and earliest slot. Keep ranking deterministic and explainable.

### Graceful failure path

Demonstrate one realistic branch such as no provider availability or a rejected job, followed by human escalation rather than a fabricated success state.

### Internet partner through the connector (mentor: "add an internet partner at a moment's notice")

Register an internet provider through the same connector (capabilities: category, regions, required fields, events) and show in the spec how a `tenant.move_in` event becomes an offer, a signed contract and a `service_contract` on the unit. Strongest evidence that the connector is reusable across categories. A second heating contractor is a lower-priority alternative.

### Building-wide outage detection

When two or more units in the same property report no heating within 24 hours, link the cases to one central-heating job instead of sending several craftsmen, and notify all affected tenants. Deterministic rule in the backend; strongest answer to the brief's "detect the moment".

### Access details and photos

Pre-fill access information (caretaker contact, key safe) from centrix and let the tenant attach a photo. The brief explicitly mentions sharing photos and access details with the craftsman. AI may describe a photo but never diagnose.

### Manager approval for costly invoices (mentor-confirmed)

centrix approves repair costs up to €3,000. Invoices above €3,000 are flagged for property-manager approval in the manager view instead of closing silently. A warning plus an approve action is enough; no payment flow.

## Avoid during the hackathon

- Multiple unrelated service categories before the repair flow is complete.
- Payment processing or real contractor bookings.
- Complex analytics, maps, or multi-organization administration.
- AI-generated state transitions that bypass backend validation.
- Features that depend on venue internet without a deterministic fallback.
