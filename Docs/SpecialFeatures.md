# Optional differentiators

These features are intentionally secondary. Do not start them until the typed end-to-end P0 flow is repeatable and persisted.

## P1 candidates

### Context-aware repair history

Surface a relevant prior heating case with source attribution. Present it as context for the contractor, never as an AI diagnosis.

### Cross-channel continuity

Allow a resident to begin by voice and continue in the portal without losing the case or repeating known information. Voice and text must call the same backend tools and use the same case state.

### Transparent partner selection

Show why a contractor was selected: supported service, service region, capacity, and earliest slot. Keep ranking deterministic and explainable.

### Graceful failure path

Demonstrate one realistic branch such as no provider availability or a rejected job, followed by human escalation rather than a fabricated success state.

### Second connector implementation

Plug a second simulated heating provider into the existing connector contract without changing case-domain logic. This is the strongest evidence that the connector is reusable.

### Building-wide outage detection

When two or more units in the same property report no heating within 24 hours, link the cases to one central-heating job instead of sending several craftsmen, and notify all affected tenants. Deterministic rule in the backend; strongest answer to the brief's "detect the moment".

### Access details and photos

Pre-fill access information (caretaker contact, key safe) from centrix and let the tenant attach a photo. The brief explicitly mentions sharing photos and access details with the craftsman. AI may describe a photo but never diagnose.

### Manager approval for costly invoices

Invoices above a configurable threshold wait for property-manager approval before the case closes. Uses the brief's "a human approves before it goes out" channel.

## Avoid during the hackathon

- Multiple unrelated service categories before the repair flow is complete.
- Payment processing or real contractor bookings.
- Complex analytics, maps, or multi-organization administration.
- AI-generated state transitions that bypass backend validation.
- Features that depend on venue internet without a deterministic fallback.
