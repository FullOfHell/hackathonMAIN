# Project differentiators

The [demo script](demo-script.md) gives priority to one complete heating repair. Use this list to choose a second proof point if there is time.

| Differentiator | Implemented behavior | Remaining work |
|---|---|---|
| Low-effort tenant intake | The themed wizard pre-fills home details, supports optional dictation and keeps editable priority separate from the issue. It requires a saved future slot before sharing. | Rehearse live speech transcription if shown. |
| Contractor selection and registration | The portal names the chosen contractor. Matching checks the repair city and usable slots first, then tries other cities in the same country. Manager can add or deactivate contractors. Inboxes and notifications are provider-scoped. | Show a second simulated provider once during rehearsal. |
| Booking and status | The assigned contractor can book a tenant slot. If no tenant time can be booked, the tenant can add times from My cases. The tenant and manager see the appointment, timeline and repair outcome. | Rehearse one rejection or fallback only after the happy path is stable. |
| Resident notification | The portal bell lists accepted, declined and completed jobs. The backend records notifications and supports a simulated outbox plus optional email and phone delivery. | A dedicated one-click booking link and live delivery verification are pending. |
| Building-wide outage | The backend can link reports from two units in one property within 24 hours to a single job and track the shared outcome. | A two-unit browser selector and dedicated linked-case view are pending. |
| Invoice review | The demo policy sends invoices above €3,000 for manager approval through the API. The main UI completes a normal €125 invoice. | Manager approval controls and advance owner authorization remain distinct follow-ups. |
| Connector reuse | A second heating contractor uses the same delivery contract. FibreNet illustrates capability discovery, and the spec describes a proposed internet offer-to-contract lifecycle. | End-to-end internet ordering remains planned. |
| Context and access | The connector supports optional prior repair context with source attribution and approved access details. The main browser flow demonstrates address, unit and heating type. | Portal controls for access details and prior context, plus photo attachments, remain optional work. |

See [assumptions](assumptions.md), the [connector spec](connector-spec.md), and the [implementation checklist](TODO.md).
