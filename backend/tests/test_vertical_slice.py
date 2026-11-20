"""Team milestone: resident submits issue -> persistent case -> approval recorded -> partner receives exactly one job."""
import json
from pathlib import Path

import httpx

from app.integrations.connector import get_partner_client
from app.states import ALLOWED_TRANSITIONS, CaseStatus, InvalidTransition, check_transition

FIXTURES = Path(__file__).resolve().parents[2] / "shared" / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def create_case(client):
    r = client.post("/api/cases", json=load("case-create.json"))
    assert r.status_code == 201, r.text
    return r.json()


def test_unit_context_has_prior_heating_case(client):
    ctx = client.get("/api/units/unit_4b/context").json()
    assert ctx["property"]["heating"] == "gas central heating"
    assert any(c["id"] == "case_000" for c in ctx["prior_heating_cases"])


def test_shared_unit_context_fixture_matches_api(client):
    assert client.get("/api/units/unit_4b/context").json() == load("unit-context.json")


def test_case_created_and_awaits_approval(client):
    case = create_case(client)
    assert case["status"] == "AWAITING_SHARING_APPROVAL"
    assert case["partner_id"] == "p_heatfix"  # Köln partner filtered out by region
    assert "address" in case["sharing_request"]["required_fields"]
    types = [e["type"] for e in client.get(f"/api/cases/{case['id']}/events").json()]
    assert types[0] == "maintenance.case_created"


def test_shared_case_response_fixture_matches_api_shape(client):
    case = create_case(client)
    fixture = load("case-response.json")
    assert set(case) == set(fixture)
    assert set(case["sharing_request"]) == set(fixture["sharing_request"])


def test_approval_sends_exactly_one_job_and_retry_is_idempotent(client):
    case = create_case(client)
    approval = load("sharing-approval.json")
    r1 = client.post(f"/api/cases/{case['id']}/sharing-approval", json=approval)
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "PARTNER_REQUESTED"
    r2 = client.post(f"/api/cases/{case['id']}/sharing-approval", json=approval)
    assert r2.status_code == 200
    jobs = [j for j in client.get("/partners/heatfix/connector/jobs").json() if j["request_id"] == case["id"]]
    assert len(jobs) == 1
    payload = jobs[0]["payload"]
    assert payload["property"]["unit"] == "4B"
    assert set(payload["sharing"]["approved_fields"]) == set(approval["approved_fields"])


def test_unapproved_fields_are_not_shared(client):
    case = create_case(client)
    body = {"approved_fields": ["address", "unit", "issue"], "channel": "portal_chat", "approved_by": "c_202"}
    client.post(f"/api/cases/{case['id']}/sharing-approval", json=body)
    job = [j for j in client.get("/partners/heatfix/connector/jobs").json() if j["request_id"] == case["id"]][0]
    assert job["payload"]["resident"] == {}
    assert "access_details" not in job["payload"]["property"]


def test_n8n_dispatch_retries_after_lost_acknowledgment(client, monkeypatch):
    webhook_url = "https://n8n.example.invalid/webhook/maintenance/sharing-approved"
    monkeypatch.setenv("N8N_CASE_WEBHOOK_URL", webhook_url)
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "test-secret")
    case_id = create_case(client)["id"]
    approval_url = f"/api/cases/{case_id}/sharing-approval"
    approval = load("sharing-approval.json") | {"approved_fields": ["address", "unit", "issue"]}
    attempts = []
    job_ids = []

    def simulate_workflow(request):
        assert request.method == "POST"
        assert str(request.url) == webhook_url
        assert request.headers["X-N8N-Webhook-Secret"] == "test-secret"
        event = json.loads(request.content)
        assert event["event"] == "maintenance.sharing_approved"
        assert event["case_id"] == event["order"]["request_id"] == case_id
        assert event["order"]["resident"] == {}
        assert set(event["order"]["property"]) == {"address", "unit"}
        persisted_case = client.get(f"/api/cases/{case_id}").json()
        assert persisted_case["sharing_approval"]["shared_fields"] == sorted(approval["approved_fields"])
        attempts.append(event)
        forwarded = client.post("/partners/heatfix/connector/jobs", json=event["order"])
        assert forwarded.status_code == (201 if len(attempts) == 1 else 200)
        result = forwarded.json()
        job_ids.append(result["job_id"])
        if len(attempts) == 1:
            raise httpx.ReadTimeout("workflow response lost", request=request)
        return httpx.Response(200, json={"case_id": case_id, "job_id": result["job_id"],
                                         "duplicate": result["duplicate"]})

    assert client.get("/partners/heatfix/connector/jobs").json() == []
    with httpx.Client(transport=httpx.MockTransport(simulate_workflow)) as n8n_client:
        client.app.dependency_overrides[get_partner_client] = lambda: n8n_client
        first = client.post(approval_url, json=approval)
        assert first.status_code == 502
        assert "n8n dispatch was not confirmed" in first.json()["detail"]
        pending = client.get(f"/api/cases/{case_id}").json()
        assert pending["status"] == "PARTNER_REQUESTED"
        assert pending["partner_job_id"] is None
        retry = client.post(approval_url, json=approval)
        assert retry.status_code == 200, retry.text
        assert client.post(approval_url, json=approval).json()["partner_job_id"] == job_ids[0]
    client.app.dependency_overrides[get_partner_client] = lambda: client

    jobs = client.get("/partners/heatfix/connector/jobs").json()
    assert len(jobs) == 1
    assert job_ids == [jobs[0]["id"], jobs[0]["id"]]
    assert retry.json()["partner_job_id"] == jobs[0]["id"]
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]
    events = client.get(f"/api/cases/{case_id}/events").json()
    assert [event["type"] for event in events].count("partner.job_requested") == 1

    job_url = f"/partners/heatfix/connector/jobs/{job_ids[0]}"
    assert client.post(f"{job_url}/accept").status_code == 200
    assert client.post(f"{job_url}/offer-slots").status_code == 200
    offered = client.get(f"/api/cases/{case_id}").json()
    booking = client.post(f"/api/cases/{case_id}/select-slot",
                          json={"slot_id": offered["slots"][0]["slot_id"], "resident_id": offered["resident_id"]})
    assert booking.status_code == 200, booking.text
    assert booking.json()["status"] == "SCHEDULED"


def test_missing_required_field_rejected(client):
    case = create_case(client)
    body = {"approved_fields": ["name"], "channel": "portal_chat", "approved_by": "c_202"}
    assert client.post(f"/api/cases/{case['id']}/sharing-approval", json=body).status_code == 422


def test_wrong_resident_cannot_approve(client):
    case = create_case(client)
    body = load("sharing-approval.json") | {"approved_by": "c_203"}
    assert client.post(f"/api/cases/{case['id']}/sharing-approval", json=body).status_code == 403


def test_partner_job_fixture_matches_contract():
    from app.schemas import PartnerJobRequest
    PartnerJobRequest(**load("partner-job.json"))


def test_invalid_transition_rejected():
    try:
        check_transition(CaseStatus.REPORTED, CaseStatus.COMPLETED)
        assert False, "should raise"
    except InvalidTransition:
        pass
    assert set(ALLOWED_TRANSITIONS) == set(CaseStatus)
