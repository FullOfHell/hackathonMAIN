import json
from contextlib import closing

import httpx
import pytest

from app.db import connect, init_db
from app.integrations.connector import get_partner_client
from app.partners.registry import install_registrations
from tests.test_vertical_slice import create_case, load


GATEWAY = "/api/integrations/approved-dispatch"
INTERNET_JOBS = "/partners/demo-internet/connector/jobs"
HEATFIX_JOBS = "/partners/heatfix/connector/jobs"
CONSENT = {"approved_by": "c_202", "approved_fields": ["address", "unit", "issue"]}


def discover(client, **overrides):
    return client.get("/api/integrations/partners", params={
        "region": "Aachen", "category": "internet", "trigger": "tenant.move_in", **overrides}).json()


@pytest.fixture
def install_demo_provider(client, tmp_path):
    def install(category, *, required_fields=None, base_url=None):
        heat, = discover(client, category="heating_repair", trigger="maintenance.case_created")
        registration = {
            "name": f"Demo {category}",
            "base_url": base_url or f"/partners/demo-{category}",
            "capabilities": heat["capabilities"] | {
                "partner_id": f"p_demo_{category}", "categories": [category],
                "required_fields": required_fields or CONSENT["approved_fields"],
                "optional_fields": ["name"],
            },
        }
        (tmp_path / f"{category}.json").write_text(json.dumps(registration), encoding="utf-8")
        with closing(connect()) as conn, conn:
            install_registrations(conn, tmp_path)
            install_registrations(conn, tmp_path)
        return registration

    return install


def test_internet_registration_is_durable_and_category_specific(client):
    init_db()
    partner, = discover(client)
    caps = client.get(partner["base_url"] + "/connector/capabilities").json()
    assert caps == partner["capabilities"]
    assert (caps["partner_id"], caps["kind"], caps["categories"]) == ("p_fibrenet", "offer", ["internet"])
    assert discover(client, region="Berlin") == discover(client, trigger="maintenance.case_created") == []
    heat, = discover(client, category="heating_repair", trigger="maintenance.case_created")
    heat_caps = client.get(heat["base_url"] + "/connector/capabilities").json()
    assert heat_caps == heat["capabilities"] | {"service_types": ["heating_repair"]}
    assert client.get("/partners/unknown/connector/capabilities").status_code == 404
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE partners SET active=0 WHERE id='p_fibrenet'")
    init_db()
    assert discover(client) == []
    assert create_case(client)["partner_id"] == "p_heatfix"


def test_installation_preserves_preexisting_partner_endpoint_and_regions(client):
    with closing(connect()) as conn, conn:
        conn.execute("DELETE FROM partner_capabilities WHERE partner_id='p_heatfix'")
        conn.execute("UPDATE partners SET base_url='/custom/heatfix',regions='[\"Berlin\"]' WHERE id='p_heatfix'")
    init_db()
    cap = client.get("/partners/heatfix/connector/capabilities").json()
    assert cap["regions"] == ["Berlin"]
    partner, = discover(client, region="Berlin", category="heating_repair", trigger="maintenance.case_created")
    assert partner["base_url"] == "/custom/heatfix"


def test_new_simulated_category_only_requires_a_manifest(client, install_demo_provider):
    registration = install_demo_provider("solar", required_fields=["address", "unit", "issue", "contact"])
    assert discover(client, category="solar", trigger="maintenance.case_created") == [registration]
    assert client.get("/partners/demo-solar/connector/capabilities").json() == registration["capabilities"]
    report = load("case-create.json") | {"issue_type": "solar", "description": "The solar inverter stopped responding."}
    response = client.post("/api/cases", json=report)
    assert response.status_code == 201, response.text
    case = response.json()
    assert case["partner_id"] == "p_demo_solar"
    assert case["sharing_request"]["required_fields"] == registration["capabilities"]["required_fields"]
    approval_url = f"/api/cases/{case['id']}/sharing-approval"
    assert client.post(approval_url, json=CONSENT).status_code == 422
    assert client.get("/partners/demo-solar/connector/jobs").json() == []
    approved = client.post(approval_url, json=CONSENT | {"approved_fields": CONSENT["approved_fields"] + ["contact"]})
    assert approved.status_code == 200, approved.text
    job, = client.get("/partners/demo-solar/connector/jobs").json()
    assert job["id"] == approved.json()["partner_job_id"]
    assert job["payload"]["service_type"] == "solar"
    assert set(job["payload"]["resident"]) == {"contact"}


def test_internet_partner_uses_same_approval_and_booking_flow(client, monkeypatch, install_demo_provider):
    install_demo_provider("internet")
    monkeypatch.setenv("N8N_CASE_WEBHOOK_URL", "https://legacy-heatfix.example.invalid/")
    report = load("case-create.json") | {"issue_type": "internet", "description": "The internet connection drops."}
    response = client.post("/api/cases", json=report)
    assert response.status_code == 201, response.text
    case = response.json()
    assert case["partner_id"] == "p_demo_internet"
    assert client.get(INTERNET_JOBS).json() == []
    case_url = f"/api/cases/{case['id']}"
    bad_consent = CONSENT | {"approved_fields": CONSENT["approved_fields"] + ["heating_type"]}
    assert client.post(case_url + "/sharing-approval", json=bad_consent).status_code == 422
    approval = client.post(case_url + "/sharing-approval", json=CONSENT)
    assert approval.status_code == 200, approval.text
    job, = client.get(INTERNET_JOBS).json()
    assert job["id"] == approval.json()["partner_job_id"]
    assert job["payload"]["service_type"] == "internet"
    assert job["payload"]["resident"] == {}
    assert client.get(HEATFIX_JOBS).json() == []
    assert client.get(f"{HEATFIX_JOBS}/{job['id']}").status_code == 404
    job_url = f"{INTERNET_JOBS}/{job['id']}"
    assert client.post(job_url + "/accept").status_code == 200
    offer = client.post(job_url + "/offer-slots")
    assert offer.status_code == 200, offer.text
    slot = offer.json()["slots"][0]
    booked = client.post(case_url + "/select-slot", json={"slot_id": slot["slot_id"], "resident_id": "c_202"})
    assert booked.status_code == 200, booked.text
    assert booked.json()["status"] == "SCHEDULED"


def test_external_adapter_uses_the_registered_endpoint(client, install_demo_provider):
    base_url = "https://new-adapter.example.invalid/service"
    install_demo_provider("appliance", base_url=base_url)
    report = load("case-create.json") | {"issue_type": "appliance", "description": "The extractor fan stopped."}
    case_id = client.post("/api/cases", json=report).json()["id"]
    orders = []

    def adapter(request):
        assert str(request.url) == base_url + "/connector/jobs"
        orders.append(json.loads(request.content))
        return httpx.Response(201, json={"job_id": "job_external"})

    with httpx.Client(transport=httpx.MockTransport(adapter)) as adapter_client:
        client.app.dependency_overrides[get_partner_client] = lambda: adapter_client
        approval = client.post(f"/api/cases/{case_id}/sharing-approval", json=CONSENT)

    assert approval.status_code == 200, approval.text
    assert approval.json()["partner_job_id"] == "job_external"
    order, = orders
    assert (order["request_id"], order["service_type"]) == (case_id, "appliance")
    assert order["resident"] == {}


@pytest.mark.parametrize(("category", "target", "other"), [
    ("heating_repair", HEATFIX_JOBS, INTERNET_JOBS), ("internet", INTERNET_JOBS, HEATFIX_JOBS),
])
def test_generic_workflow_routes_stored_order_once_after_lost_acknowledgment(
    client, monkeypatch, install_demo_provider, category, target, other,
):
    install_demo_provider("internet")
    webhook = "https://connector.example.invalid/webhook/connector/approved-dispatch"
    monkeypatch.setenv("N8N_CONNECTOR_WEBHOOK_URL", webhook)
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "test-webhook")
    monkeypatch.setenv("CONNECTOR_DISPATCH_SECRET", "test-gateway")
    headers = {"X-Connector-Dispatch-Secret": "test-gateway"}
    report = load("case-create.json") | {"issue_type": category, "description": f"Synthetic {category} service request."}
    case_id = client.post("/api/cases", json=report).json()["id"]
    assert client.post(GATEWAY, json={"case_id": case_id}).status_code == 401
    assert client.post(GATEWAY, headers=headers, json={"case_id": case_id}).status_code == 404
    assert client.post(GATEWAY, headers=headers, json={"case_id": case_id, "partner_id": "p_heatfix"}).status_code == 422
    deliveries = []

    def simulate_workflow(request):
        if str(request.url) == webhook:
            assert request.headers["X-N8N-Webhook-Secret"] == "test-webhook"
            assert json.loads(request.content) == {"event": "maintenance.sharing_approved", "case_id": case_id}
            receipt = client.post(GATEWAY, headers=headers, json={"case_id": case_id})
            assert receipt.status_code == 200, receipt.text
            deliveries.append(receipt.json())
            if len(deliveries) == 1:
                raise httpx.ReadTimeout("workflow reply lost", request=request)
            return httpx.Response(200, json=receipt.json())
        assert request.url.path == target
        result = client.post(target, json=json.loads(request.content))
        return httpx.Response(result.status_code, json=result.json())

    approval_url = f"/api/cases/{case_id}/sharing-approval"
    with httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(simulate_workflow)) as workflow:
        client.app.dependency_overrides[get_partner_client] = lambda: workflow
        assert client.post(approval_url, json=CONSENT).status_code == 502
        retry = client.post(approval_url, json=CONSENT)
        assert retry.status_code == 200, retry.text
        replay = client.post(GATEWAY, headers=headers, json={"case_id": case_id})

    job, = client.get(target).json()
    assert client.get(other).json() == []
    assert job["payload"]["service_type"] == category
    assert replay.json() == {"case_id": case_id, "job_id": job["id"], "duplicate": True}
    assert retry.json()["partner_job_id"] == job["id"]
    assert [receipt["job_id"] for receipt in deliveries] == [job["id"], job["id"]]
    assert [receipt["duplicate"] for receipt in deliveries] == [False, True]
