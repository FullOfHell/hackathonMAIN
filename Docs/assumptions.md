# Assumptions

The prototype simulates centrix and the partner. It is not connected to the real centrix API or a real contractor.

- **Data:** all people, properties, contact details and documents are synthetic (`backend/seed/seed.json`), modelled on the example payloads in the official Reltix brief.
- **centrix stand-in:** FastAPI + SQLite in `backend/` holds properties, units, residents, partners, cases, case events and sharing approvals.
- **Partner:** "HeatFix Aachen GmbH" is a simulated contractor served under `/partners/heatfix`. It keeps its own job table and only receives data through connector v1.
- **Routing:** deterministic: service type, then region, then active; tie-break by name. A second partner (Köln) exists in seed data to show region filtering.
- **Data sharing:** only fields the resident approves are sent. `address`, `unit` and `issue` are required for a repair job; name, contact, heating type, access details and prior heating case are optional.
- **Access details:** the key-safe code is never shared automatically; the property manager releases it after booking.
