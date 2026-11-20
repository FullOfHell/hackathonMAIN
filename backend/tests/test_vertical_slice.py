"""Team milestone: resident submits issue -> persistent case -> approval recorded -> partner receives exactly one job."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from app.db import connect
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


def test_approved_prior_repair_identifies_source_record(client):
    case = create_case(client)
    # A newer open report is not a previous repair.
    create_case(client)
    fields = ["address", "unit", "issue", "prior_heating_case"]
    result = client.post(f"/api/cases/{case['id']}/sharing-approval", json={
        "approved_by": "c_202", "approved_fields": fields})
    assert result.is_success
    job, = client.get("/partners/heatfix/connector/jobs").json()
    assert job["payload"]["issue"]["previous_record"]["source_case_id"] == "case_000"
    assert job["payload"]["resident"] == {}


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


def test_no_provider_can_be_escalated_without_sharing_or_dispatch(client):
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE partners SET active=0 WHERE id='p_heatfix'")
    case = create_case(client)
    assert case["status"] == "NO_PROVIDER_AVAILABLE"
    assert case["partner_id"] is None and case["sharing_approval"] is None
    url = f"/api/cases/{case['id']}"
    assert client.post(url + "/sharing-approval", json=load("sharing-approval.json")).status_code == 409
    assert client.post(url + "/escalate").json()["status"] == "NEEDS_HUMAN_REVIEW"
    events = client.get(url + "/events").json()
    assert [e["payload"]["to"] for e in events[1:]] == ["TRIAGED", "NO_PROVIDER_AVAILABLE", "NEEDS_HUMAN_REVIEW"]
    assert client.get("/partners/heatfix/connector/jobs").json() == []


def test_withdraw_before_consent(client):
    case = create_case(client)
    url = f"/api/cases/{case['id']}"
    assert client.post(url + "/cancel", json={"resident_id": "c_203"}).status_code == 403
    for _ in range(2):
        assert client.post(url + "/cancel", json={"resident_id": case["resident_id"]}).json()["status"] == "CANCELLED"
    assert client.post(url + "/sharing-approval", json=load("sharing-approval.json")).status_code == 409
    events = client.get(url + "/events").json()
    assert sum(e["payload"].get("to") == "CANCELLED" for e in events) == 1
    assert client.get("/partners/heatfix/connector/jobs").json() == []


def test_direct_dispatch_lost_reply_retries_only_original_approval(client):
    case = create_case(client)
    url = f"/api/cases/{case['id']}/sharing-approval"
    approval = load("sharing-approval.json")

    def lost_reply(request):
        result = client.post(request.url.path, json=json.loads(request.content))
        assert result.status_code == 201
        raise httpx.ReadTimeout("reply lost")

    with httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(lost_reply)) as partner:
        client.app.dependency_overrides[get_partner_client] = lambda: partner
        assert client.post(url, json=approval).status_code == 502
    pending = client.get(f"/api/cases/{case['id']}").json()
    assert pending["status"] == "PARTNER_REQUESTED" and pending["partner_job_id"] is None
    assert client.post(url, json=approval | {"approved_fields": ["address", "unit", "issue"]}).status_code == 409
    original = client.get("/partners/heatfix/connector/jobs").json()[0]["payload"]
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE residents SET email='updated@example.com' WHERE id=?", (case["resident_id"],))

    def confirm_retry(request):
        assert json.loads(request.content) == original
        reply = client.post(request.url.path, json=original)
        assert reply.status_code == 200 and reply.json()["duplicate"]
        return httpx.Response(200, json=reply.json())

    with httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(confirm_retry)) as partner:
        client.app.dependency_overrides[get_partner_client] = lambda: partner
        linked = client.post(url, json=approval).json()
    jobs = client.get("/partners/heatfix/connector/jobs").json()
    assert [job["id"] for job in jobs] == [linked["partner_job_id"]]
    assert linked["sharing_approval"] == pending["sharing_approval"]
    conflicting = jobs[0]["payload"] | {"request_id": "case_other"}
    assert client.post("/partners/heatfix/connector/jobs", json=conflicting).status_code == 409


@pytest.mark.parametrize(("status", "content"), [(200, b"{}"), (200, b""), (503, b"unavailable")])
def test_invalid_direct_acknowledgment_leaves_approval_retryable(client, status, content):
    case = create_case(client)
    url = f"/api/cases/{case['id']}/sharing-approval"
    approval = load("sharing-approval.json")
    with httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(
        lambda _: httpx.Response(status, content=content)
    )) as partner:
        client.app.dependency_overrides[get_partner_client] = lambda: partner
        assert client.post(url, json=approval).status_code == 502
    pending = client.get(f"/api/cases/{case['id']}").json()
    assert pending["status"] == "PARTNER_REQUESTED" and pending["partner_job_id"] is None
    client.app.dependency_overrides[get_partner_client] = lambda: client
    assert client.post(url, json=approval).json()["partner_job_id"]


def test_unreachable_partner_escalates_without_reporting_a_job(client):
    case = create_case(client)

    def unavailable(request):
        raise httpx.ConnectError("connection refused", request=request)

    with httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(unavailable)) as partner:
        client.app.dependency_overrides[get_partner_client] = lambda: partner
        response = client.post(f"/api/cases/{case['id']}/sharing-approval", json=load("sharing-approval.json"))
    assert response.status_code == 502
    result = client.get(f"/api/cases/{case['id']}").json()
    assert result["status"] == "NEEDS_HUMAN_REVIEW" and result["partner_job_id"] is None
    assert result["sharing_approval"]["case_id"] == case["id"]
    assert client.get("/partners/heatfix/connector/jobs").json() == []


def test_case_creation_requires_resident_of_unit_and_events_are_immutable(client):
    request = load("case-create.json")
    assert client.post("/api/cases", json=request | {"resident_id": "c_203"}).status_code == 422
    assert client.post("/api/cases", json=request | {"unit_id": "unknown"}).status_code == 404
    case = create_case(client)
    assert (case["unit_id"], case["resident_id"]) == (request["unit_id"], request["resident_id"])
    events = client.get(f"/api/cases/{case['id']}/events").json()
    with closing(connect()) as conn:
        for statement in ("UPDATE case_events SET actor='changed' WHERE id=?", "DELETE FROM case_events WHERE id=?",
                          "INSERT OR REPLACE INTO case_events SELECT * FROM case_events WHERE id=?"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                conn.execute(statement, (events[0]["id"],))
    assert client.get(f"/api/cases/{case['id']}/events").json() == events
