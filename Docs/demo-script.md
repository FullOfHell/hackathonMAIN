# Three minute heating repair demo

Follow one case from the tenant report to the invoice on the original unit. Use a fresh synthetic database and start both servers from the exact commit you plan to demonstrate. Resolve API port mismatches and verify the named contractor can accept a test job before recording.

| Time | Screen and action |
|---|---|
| 0:00–0:15 | Open **Report**. Explain how a loss of heat normally sends the tenant and manager through multiple calls and handoffs. |
| 0:15–0:45 | Type “The radiators are cold and the hot water still works.” Open Summary, select High priority and save two future slots. Point out the home details already on file. |
| 0:45–1:10 | Continue to sharing. Show the named contractor and the fields being shared, then select **Approve and send** and **Send now**. Keep the case ID visible on the confirmation. |
| 1:10–1:45 | Select the named contractor from the header. Show the received job and bell, accept the job and book a saved tenant slot. |
| 1:45–2:15 | Start the repair, add a short completion summary and confirm the simulated €125 invoice. |
| 2:15–2:40 | Open **My cases** or expand the contractor’s repair group in **Manager**. Show the same case, original unit, appointment in local time, status history and invoice download. |
| 2:40–2:58 | Show the connector contract or a successfully rehearsed n8n execution and explain how a second simulated contractor uses the same job and callback interface. Close on the resolved case. |

## Recording checklist

- Use typed intake and direct dispatch for the baseline rehearsal. Clear both n8n webhook URLs for direct dispatch, or configure and verify the [provider-neutral workflow](../n8n/README.md).
- If showing dictation, select and rehearse ElevenLabs Scribe v2 or OpenAI first. A browser recording becomes editable text before it can be shared.
- If showing a differentiator, choose one after the main repair. Useful options include a second provider registration, the notification bell staying open when a message is read, or the two-unit outage API demonstration.
- Use synthetic cases and hide credentials, internal settings, and unrelated tabs. Verify the code judges can access matches the release in the video.
- Confirm the BuilderBase project name, judging access, video and current deadline before submitting.

See the [checklist](TODO.md), [startup guide](../readme.md), and [connector contract](connector-spec.md).
