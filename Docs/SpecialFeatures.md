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

## Avoid during the hackathon

- Multiple unrelated service categories before the repair flow is complete.
- Payment processing or real contractor bookings.
- Complex analytics, maps, or multi-organization administration.
- AI-generated state transitions that bypass backend validation.
- Features that depend on venue internet without a deterministic fallback.
