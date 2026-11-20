# Structured heating intake contract

Schema version `1.0` for the P0 portal and FastAPI handoff.

## Request and response

`POST /api/intake/extract` accepts two fields. `report` is the resident’s current draft, trimmed to 3–1,950 characters. `hot_water_affected` is `true`, `false`, or `null` and defaults to `null`. The portal can fold any follow-up answer into the draft and request extraction again. FastAPI rejects invalid requests with 422. The extraction endpoint has no case or dispatch side effects.

FastAPI returns `schema_version: "1.0"`, `source: "model" | "fallback"`, and `result`. The backend owns the envelope. The provider receives the report and optional hot-water answer. Keep unit and resident identifiers, saved property and resident data, prior case history, and credentials out of the provider request.

The following Draft 2020-12 JSON Schema defines the model output and the API’s `result`. For provider dialects without length or count constraints, enforce the full schema in FastAPI.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["symptoms", "urgency", "availability_preferences", "missing_information", "safety_signal"],
  "properties": {
    "symptoms": {
      "type": "array",
      "maxItems": 12,
      "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 160}
    },
    "urgency": {
      "enum": ["low", "normal", "high", null]
    },
    "availability_preferences": {
      "type": "array",
      "maxItems": 8,
      "uniqueItems": true,
      "items": {"type": "string", "minLength": 1, "maxLength": 160}
    },
    "missing_information": {
      "type": "array",
      "maxItems": 3,
      "uniqueItems": true,
      "items": {"enum": ["heating_symptom", "hot_water_affected", "availability_preferences"]}
    },
    "safety_signal": {
      "enum": ["none", "possible_gas_leak"]
    }
  }
}
```

Use short excerpts from the report for symptoms and availability. FastAPI verifies those excerpts after whitespace normalization and case folding. The explicit hot-water answer takes precedence and FastAPI adds a fixed corresponding symptom label after validation if applicable (`hot_water_affected` or `hot_water_working`). Reserve one symptom slot for that label when the answer is present. Treat timing as an availability preference only when it describes when the resident can be home. Vague or relative preferences can remain verbatim. Appointments still come from the booking API.

`urgency` reflects an explicit priority supported by the report, with `null` for unspecified or ambiguous priority. The portal lets the resident confirm or edit it and defaults to `normal` when saving without a choice. Treat model-derived fields as suggestions. FastAPI validates all required keys, types, enums, limits, and grounding, rejects whitespace-only items or normalized duplicates, and uses fallback on invalid results. It reconciles missing fields with the report excerpts and follow-up answers already collected.

## Typed portal flow

Optional voice dictation feeds the same draft. `GET /api/intake/transcription` reports whether the selected server-side provider is configured. OpenAI is the default and uses `OPENAI_API_KEY` and `OPENAI_TRANSCRIPTION_MODEL`. Set `TRANSCRIPTION_PROVIDER=elevenlabs` and `ELEVENLABS_API_KEY` to use Scribe v2. `POST /api/intake/transcription` takes an explicitly submitted WebM, Ogg, or MP4 audio body up to 4 MiB and returns `{"text": "..."}`. The portal stops recording after 30 seconds. Review and add the transcript before using the normal intake and sharing steps.

- **Describe.** Preserve the resident’s own words. If the issue is unclear, ask “What is happening with your heating?” Ask “Is hot water also affected?” only if the answer is unknown and relevant. Availability is optional. If it is useful to ask, use “When are you usually home for a repair visit?” Show at most one follow-up at a time, let residents skip optional questions, and avoid asking again after an answer or skip during the same draft.
- **Review.** Show the original report, editable symptoms and availability, and editable urgency. The resident’s final values are authoritative. Build the existing `POST /api/cases` request with `description`, `symptoms`, `availability_preferences`, and `urgency`, plus `unit_id` and `resident_id` from the existing context, `issue_type: "heating_repair"`, and `source_channel: "portal_chat"`. Keep description within the existing 3–2,000-character limit, including any appended notes.
- **Approve.** Use the existing sharing preview and explicit approval before sending the case to HeatFix. Display case, job, booking, and repair progress only from saved backend responses. Model output cannot set identity, sharing approval, provider, case status, appointments, completion, or invoice data.

## Fallback and possible gas leak

Set `OPENAI_API_KEY` and `OPENAI_TEXT_MODEL` in `backend/.env` to enable the model path. Use a model that supports JSON Schema structured output. The same endpoint serves the deterministic fallback when either setting is empty.

On missing provider configuration, timeout, provider error, or invalid output, FastAPI returns the same response shape with `source: "fallback"`. It matches a small set of known heating phrases (including the three portal shortcuts) against the report, keeps the matching text, carries over any explicit hot-water answer, and leaves uncertain urgency as `null`. Leave availability empty unless the text explicitly supplies a supported preference. Allow manual review and editing with zero extraction results. If the extraction endpoint is unreachable while the case API is usable, the portal keeps the draft and opens manual review.

Run a deterministic check for explicit possible-gas-leak reports before the provider call, including with the provider disabled. A positive deterministic check or a valid positive model signal takes precedence over the normal review flow. Show fixed copy, “If you suspect a gas leak, move to a safe place and contact local emergency services.” Pause routine submission and automatic dispatch on that path. Use a fixed escalation message in the typed fallback as well.

## Handoff and acceptance checks

- **A (frontend)** wires the optional extraction request into Describe and Review, maps missing-field codes to fixed questions, preserves manual entry, and keeps the existing approval step.
- **B (backend)** implements the request and response models, output validation, deterministic fallback and safety check, and the side-effect-free extraction endpoint. The case and connector payloads stay compatible with their existing fixtures.
- **C (integration)** connects the provider using structured output and verifies model and fallback responses against the same schema.

Use synthetic reports to check that an explicit symptom and “Weekday mornings” appear in review and the saved case, unclear reports ask only for missing information, provider timeout and malformed output preserve manual intake, a possible gas leak interrupts the routine flow, and extraction and review create zero HeatFix jobs before explicit sharing approval.
