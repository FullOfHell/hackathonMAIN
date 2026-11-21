# centrix portal

This React and TypeScript app connects the tenant, contractor and manager views to FastAPI. See the [repository startup instructions](../readme.md) and [demo script](../Docs/demo-script.md).

## Run locally

From `frontend/`, run the commands below with the backend running at the configured address.

```bash
npm ci
VITE_API_BASE_URL=http://localhost:8000 npm run dev -- --port 5173 --strictPort
```

Set `VITE_API_BASE_URL` in `.env.local` to keep the API address between sessions. With no API URL, fixture mode offers a simulated report and job flow. The connected calendar, provider registration and voice transcription require FastAPI.

## Views

| Route | What to test |
|---|---|
| `#report` | Type or dictate a report, review symptoms and priority, save a future calendar slot, and approve the fields for the assigned contractor. The progress bar follows Describe, Summary and Approve. Address, unit, heating type and contact details are editable in **Your home**. |
| `#cases` | Expand a report to see status, confirmed appointment, repair timeline and invoice. Confirm an offered time if the contractor sent options. |
| `#inbox` or `#inbox/<slug>` | Choose the contractor in the header. Accept or reject a job, book a saved time or offer options, start and complete the repair, then confirm a demo invoice. |
| `#manager` | Add contractors by name, city and inbox slug. **Delete** deactivates the contractor after confirmation and hides its repair group from Manager. Existing case history is retained. **Open inbox** opens the selected provider’s jobs. |

The tenant bell shows acceptance, decline and completion. Each contractor bell shows that provider’s relevant new jobs. Clicking a message marks it read while the panel stays open. Availability is saved by week. At least one future unbooked slot in any of the three displayed weeks is required to continue in connected mode.

Report draft saves, profile saves, transcription, contractor registration, visit booking, completion and invoice submission run immediately. **Approve and send** offers **Undo** and **Send now** for the final handoff.

## Verification

```bash
npm test
npm run build
```

For a browser rehearsal, open the connected portal with a fresh synthetic database and follow the [demo script](../Docs/demo-script.md).
