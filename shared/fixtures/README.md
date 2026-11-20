# Shared fixtures

These JSON files are the temporary contract between frontend, backend and integrations while the APIs are being implemented.

- `unit-context.json` represents `GET /api/units/{unit_id}/context`.
- `case-create.json` represents `POST /api/cases` input.
- `case-response.json` represents a newly persisted case.
- `partner-job.json` represents connector v1 job creation.
- `partner-event.json` represents a signed partner callback after slots are offered.

Contract changes must be reviewed by the affected owners and updated in the TypeScript types, backend schemas, tests and documentation together.
