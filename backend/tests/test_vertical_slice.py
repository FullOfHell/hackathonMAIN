"""Team milestone: resident submits issue -> persistent case -> approval recorded -> partner receives exactly one job."""
import json
from pathlib import Path

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
