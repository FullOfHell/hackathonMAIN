# Shared fixtures

These JSON files are the temporary contract between frontend, backend and integrations while the APIs are being implemented.

- `unit-context.json` represents `GET /api/units/{unit_id}/context`.
- `case-create.json` represents `POST /api/cases` input.
- `case-response.json` represents a newly persisted case.
- `building-repair.json` is the `building_repair` field on a linked unit's case after the dispatch resident books the shared visit.
- `sharing-approval.json` represents `POST /api/cases/{case_id}/sharing-approval` input.
- `partner-job.json` represents connector v1 job creation.
- `partner-event.json` represents a signed partner callback after slots are offered.
- `partner-repair-events.json` contains the callbacks for starting work, reporting completion and attaching an invoice. The `data` from the last two entries is also the request body for the HeatFix complete and invoice actions.
- `partner-failed.json` represents a partner that cannot fulfill an active repair job.
- `case-closed.json` represents the case returned after invoicing, including the booked appointment and links to both JSON documents.

These are the canonical cross-team examples. Backend tests and the frontend fixture fallback both consume them. Contract changes must be reviewed by the affected owners and updated in the TypeScript types, backend schemas, tests and documentation together.
