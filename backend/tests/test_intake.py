import json

import httpx
import pytest

from tests.test_vertical_slice import load


EXTRACT = "/api/intake/extract"
JOBS = "/partners/heatfix/connector/jobs"
MODEL_RESULT = {
    "symptoms": ["RADIATORS   ARE cold"],
    "urgency": "high",
    "availability_preferences": ["Weekday mornings"],
    "missing_information": ["heating_symptom", "hot_water_affected", "availability_preferences"],
    "safety_signal": "none",
}
REPORT = "Radiators are cold since last night. Weekday mornings. High priority."


@pytest.fixture(autouse=True)
def default_to_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "")


@pytest.fixture
def model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-intake-key")
    monkeypatch.setenv("OPENAI_TEXT_MODEL", "test-intake-model")

    def respond(result, *, status="completed", part_type="output_text"):
        def post(url, *, headers, json, timeout):
            assert url == "https://api.openai.com/v1/responses"
            assert timeout > 0 and not json["store"]
            assert json["text"]["format"]["strict"] is True
            assert json["text"]["format"]["schema"]["additionalProperties"] is False
            assert headers["Authorization"] == "Bearer test-intake-key"
            respond.input = json["input"]
            return httpx.Response(200, request=httpx.Request("POST", url), json={
                "status": status,
                "output": [{"type": "message", "content": [{"type": part_type, "text": result}]}],
            })

        monkeypatch.setattr("app.integrations.intake.httpx.post", post)

    return respond


@pytest.mark.parametrize("body", [
    {}, {"report": "  ab  "}, {"report": "x" * 1951}, {"report": 123},
    {"report": REPORT, "hot_water_affected": "yes"}, {"report": REPORT, "resident_id": "c_202"},
])
def test_reject_invalid_intake_requests(client, body):
    assert client.post(EXTRACT, json=body).status_code == 422


@pytest.mark.parametrize("shortcut", ["No heat at all", "Radiators are lukewarm", "Some radiators are cold"])
def test_fallback_preserves_shortcut_and_asks_only_for_unknown_details(client, shortcut):
    reply = client.post(EXTRACT, json={"report": f"  {shortcut}. Weekday mornings.  "})
    assert reply.status_code == 200, reply.text
    assert reply.json() == {"schema_version": "1.0", "source": "fallback", "result": {
        "symptoms": [shortcut], "urgency": None, "availability_preferences": ["Weekday mornings"],
        "missing_information": ["hot_water_affected"], "safety_signal": "none",
    }}


def test_unclear_report_and_explicit_follow_up(client):
    first = client.post(EXTRACT, json={"report": "Something seems wrong."}).json()["result"]
    assert first["symptoms"] == []
    assert first["missing_information"][0] == "heating_symptom"
    draft = {"report": "Something seems wrong. No heating since last night.\nAvailability: After school pickup",
             "hot_water_affected": False}
    result = client.post(EXTRACT, json=draft).json()["result"]
    assert result["symptoms"] == ["No heating", "hot_water_working"]
    assert result["availability_preferences"] == ["After school pickup"]
    assert result["missing_information"] == []


def test_explicit_gas_signal_is_detected_before_provider_and_negation_is_respected(client, model, monkeypatch):
    def fail_if_called(*args, **kwargs):
        pytest.fail("explicit gas signal reached the model")

    monkeypatch.setattr("app.integrations.intake.httpx.post", fail_if_called)
    positive = client.post(EXTRACT, json={"report": "The boiler stopped. I can smell gas."}).json()
    assert positive["source"] == "fallback"
    assert positive["result"]["safety_signal"] == "possible_gas_leak"
    assert client.post(EXTRACT, json={"report": "Gas is leaking from the boiler."}).json()["result"][
        "safety_signal"] == "possible_gas_leak"
    model(json.dumps(MODEL_RESULT))
    negative = client.post(EXTRACT, json={"report": REPORT + " I don't smell gas."}).json()
    assert negative["source"] == "model"
    assert negative["result"]["safety_signal"] == "none"


def test_model_uses_only_intake_data_and_respects_explicit_water_answer(client, model):
    report = REPORT + " No hot water."
    model(json.dumps(MODEL_RESULT | {"symptoms": ["RADIATORS   ARE cold", "No hot water"]}))
    result = client.post(EXTRACT, json={"report": report, "hot_water_affected": False}).json()
    assert json.loads(model.input) == {"report": report, "hot_water_affected": False}
    assert result == {"schema_version": "1.0", "source": "model", "result": MODEL_RESULT | {
        "symptoms": ["RADIATORS   ARE cold", "hot_water_working"], "missing_information": [],
    }}


def test_valid_model_safety_signal_is_returned(client, model):
    model(json.dumps(MODEL_RESULT | {"safety_signal": "possible_gas_leak"}))
    reply = client.post(EXTRACT, json={"report": REPORT + " There's a strange sulfur odour from the boiler."})
    assert reply.json()["source"] == "model"
    assert reply.json()["result"]["safety_signal"] == "possible_gas_leak"


def test_model_preserves_an_explicit_availability_excerpt_with_its_context(client, model):
    availability = "I can be home after lunch"
    model(json.dumps(MODEL_RESULT | {"availability_preferences": [availability]}))
    reply = client.post(EXTRACT, json={"report": f"{REPORT} {availability}. I still have hot water."}).json()
    assert reply["source"] == "model"
    assert reply["result"]["availability_preferences"] == [availability]
    assert reply["result"]["missing_information"] == []


@pytest.mark.parametrize("invalid", [
    {"symptoms": [" "]}, {"symptoms": ["Radiators are cold", "radiators   are COLD"]},
    {"symptoms": ["Radiators are cold"] * 13}, {"symptoms": ["broken pump"]},
    {"availability_preferences": ["last night"]}, {"urgency": "low"}, {"urgency": True},
    {"missing_information": ["unknown"]}, {"safety_signal": "gas"}, {"status": "SCHEDULED"},
])
def test_invalid_or_ungrounded_model_output_uses_fallback(client, model, invalid):
    model(json.dumps(MODEL_RESULT | invalid))
    reply = client.post(EXTRACT, json={"report": REPORT})
    assert reply.status_code == 200
    assert reply.json()["source"] == "fallback"
    assert reply.json()["result"]["symptoms"] == ["Radiators are cold"]


@pytest.mark.parametrize(("text", "status", "part"), [
    ("not json", "completed", "output_text"), ("{}", "completed", "output_text"),
    ("{}", "incomplete", "output_text"), ("{}", "completed", "refusal"),
])
def test_unusable_model_response_leaves_manual_intake_available(client, model, text, status, part):
    model(text, status=status, part_type=part)
    assert client.post(EXTRACT, json={"report": REPORT}).json()["source"] == "fallback"


def test_provider_timeout_uses_fallback_without_guessing_urgency(client, model, monkeypatch):
    def timeout(*args, **kwargs):
        raise httpx.ReadTimeout("model timed out")

    monkeypatch.setattr("app.integrations.intake.httpx.post", timeout)
    reply = client.post(EXTRACT, json={"report": "No heating since last night."}).json()
    assert reply["source"] == "fallback"
    assert reply["result"]["urgency"] is None
    assert reply["result"]["availability_preferences"] == []


def test_intake_and_case_creation_do_not_dispatch_before_explicit_approval(client):
    unit_cases = "/api/units/unit_4b/cases"
    before = client.get(unit_cases).json()
    result = client.post(EXTRACT, json={"report": REPORT, "hot_water_affected": True}).json()["result"]
    assert client.get(unit_cases).json() == before
    assert client.get(JOBS).json() == []

    reviewed = load("case-create.json") | {"description": REPORT, "symptoms": result["symptoms"],
                                           "urgency": result["urgency"],
                                           "availability_preferences": result["availability_preferences"]}
    reply = client.post("/api/cases", json=reviewed)
    assert reply.status_code == 201, reply.text
    case = reply.json()
    assert case["symptoms"] == ["Radiators are cold", "hot_water_affected"]
    assert case["availability_preferences"] == ["Weekday mornings"]
    assert client.get(JOBS).json() == []

    reply = client.post(f"/api/cases/{case['id']}/sharing-approval", json=load("sharing-approval.json"))
    assert reply.status_code == 200, reply.text
    job, = client.get(JOBS).json()
    assert job["id"] == reply.json()["partner_job_id"]
    assert job["payload"]["issue"]["availability_preferences"] == ["Weekday mornings"]
