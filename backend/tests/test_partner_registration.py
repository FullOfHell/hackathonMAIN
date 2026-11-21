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
    accepted, = [event for event in client.get(case_url + "/events").json() if event["type"] == "partner.accepted"]
    retry_path = f"/{job['id']}/callbacks/{accepted['payload']['event_id']}/retry"
    assert client.post(HEATFIX_JOBS + retry_path).status_code == 404
    assert client.post(INTERNET_JOBS + retry_path).status_code == 200
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


MANAGER_CONTRACTORS = "/api/manager/contractors"
MANAGER_CONTRACTOR = {"name": "Aachen Demo Heating", "slug": "aachen-demo-heating", "region": "Aachen"}


def test_matching_tries_other_local_contractors_before_falling_back(client):
    local = MANAGER_CONTRACTOR
    outside = {"name": "Berlin Demo Heating", "slug": "berlin-heating", "region": "Berlin"}
    assert client.post(MANAGER_CONTRACTORS, json=outside).status_code == 201
    slots = []
    for unit, resident in (("unit_4b", "c_202"), ("unit_2a", "c_203")):
        path = f"/api/units/{unit}/residents/{resident}/availability"
        actor = {"acting_resident_id": resident}
        week = client.get(path, params=actor | {"week": 1}).json()
        start = week["slots"][0]["start"]
        assert client.put(path, json=actor | {"week_start": week["week_start"], "available_starts": [start]}).status_code == 200
        slots.append(start)

    case = create_case(client)
    assert case["partner_id"] == "p_heatfix"
    approval = client.post(f"/api/cases/{case['id']}/sharing-approval", json=CONSENT)
    assert approval.status_code == 200, approval.text
    job = f"{HEATFIX_JOBS}/{approval.json()['partner_job_id']}"
    assert client.post(job + "/accept").status_code == 200
    assert client.post(job + "/tenant-availability/book", json={"start": slots[0]}).status_code == 200

    assert client.post(MANAGER_CONTRACTORS, json=local).status_code == 201
    request = load("case-create.json") | {"unit_id": "unit_2a", "resident_id": "c_203"}
    another = client.post("/api/cases", json=request).json()
    assert another["partner_id"] == "p_manager_aachen-demo-heating"
    assert client.delete(f"{MANAGER_CONTRACTORS}/{local['slug']}").status_code == 200
    path = f"/api/cases/{another['id']}"
    assert client.get(path).json()["partner_id"] == "p_manager_berlin-heating"
    assert client.get(path).json()["partner_id"] == "p_manager_berlin-heating"
    assert client.post(path + "/sharing-approval", json={"approved_by": "c_203",
                       "approved_fields": CONSENT["approved_fields"],
                       "expected_partner_id": another["partner_id"]}).status_code == 409


def test_removing_contractor_hides_repairs_and_keeps_case_history(client):
    registered = client.post(MANAGER_CONTRACTORS, json=MANAGER_CONTRACTOR)
    assert registered.status_code == 201
    case = create_case(client)
    url = f"/api/cases/{case['id']}"
    approved = client.post(url + "/sharing-approval", json=CONSENT)
    assert approved.status_code == 200
    assert approved.json()["contractor_name"] == MANAGER_CONTRACTOR["name"]
    removed = f"{MANAGER_CONTRACTORS}/{MANAGER_CONTRACTOR['slug']}"
    repairs = "/api/manager/repairs"
    assert any(repair["case"]["id"] == case["id"] for group in client.get(repairs).json() for repair in group["repairs"])
    assert client.delete(removed).status_code == client.delete(removed).status_code == 200
    assert client.delete(MANAGER_CONTRACTORS + "/missing").status_code == 404
    init_db()
    assert registered.json() not in client.get(MANAGER_CONTRACTORS).json()
    assert all(repair["case"]["id"] != case["id"] for group in client.get(repairs).json() for repair in group["repairs"])
    assert client.get(url).json()["contractor_name"] == MANAGER_CONTRACTOR["name"]
    jobs = f"/partners/{MANAGER_CONTRACTOR['slug']}/connector/jobs"
    existing, = client.get(jobs).json()
    assert client.post(jobs, json=existing["payload"]).status_code == 200
    assert client.post(jobs, json=existing["payload"] | {"idempotency_key": "new-removed-request"}).status_code == 410


def test_unavailable_contractor_blocks_dispatch_and_saved_case_can_recover(client):
    pending = create_case(client)
    pending_path = f"/api/cases/{pending['id']}"
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE partners SET active=0 WHERE id='p_heatfix'")
        # An offer matching the exact region, service and trigger still cannot receive a repair.
        conn.execute("UPDATE partners SET service_types=? WHERE id='p_fibrenet'", ('["heating_repair"]',))
        conn.execute("UPDATE partner_capabilities SET manifest=json_set(manifest,'$.triggers',json(?)) "
                     "WHERE partner_id='p_fibrenet'", ('["maintenance.case_created"]',))
    unavailable = create_case(client)
    assert unavailable["status"] == "NO_PROVIDER_AVAILABLE"
    assert unavailable["partner_id"] is None and "sharing_request" not in unavailable
    assert client.get(pending_path).json()["status"] == "NO_PROVIDER_AVAILABLE"
    rejected = client.post(pending_path + "/sharing-approval", json=CONSENT | {"expected_partner_id": "p_heatfix"})
    assert rejected.status_code == 409
    assert "No contractors available" in rejected.json()["detail"]
    assert client.get(pending_path).json()["sharing_approval"] is None
    assert client.get(HEATFIX_JOBS).json() == []

    assert client.post(MANAGER_CONTRACTORS, json=MANAGER_CONTRACTOR).status_code == 201
    recovered = client.get(pending_path).json()
    assert recovered["id"] == pending["id"]
    assert recovered["status"] == "AWAITING_SHARING_APPROVAL"
    assert recovered["sharing_request"]["partner"]["name"] == MANAGER_CONTRACTOR["name"]
    assert client.post(pending_path + "/sharing-approval", json=CONSENT | {"expected_partner_id": "p_heatfix"}).status_code == 409
    jobs_url = f"/partners/{MANAGER_CONTRACTOR['slug']}/connector/jobs"
    assert client.get(jobs_url).json() == []
    approved = client.post(pending_path + "/sharing-approval",
                           json=CONSENT | {"expected_partner_id": recovered["partner_id"]})
    assert approved.status_code == 200, approved.text
    job, = client.get(jobs_url).json()
    assert job["id"] == approved.json()["partner_job_id"]


def test_manager_adds_persistent_contractor_and_routes_approved_repair(client):
    response = client.post(MANAGER_CONTRACTORS, json=MANAGER_CONTRACTOR)
    assert response.status_code == 201, response.text
    registered = response.json()
    assert registered == {"name": "Aachen Demo Heating", "slug": "aachen-demo-heating", "regions": ["Aachen"]}
    init_db()
    assert registered in client.get(MANAGER_CONTRACTORS).json()
    case = create_case(client)
    assert case["sharing_request"]["partner"]["name"] == registered["name"]
    jobs_url = f"/partners/{registered['slug']}/connector/jobs"
    assert client.get(jobs_url).json() == client.get(HEATFIX_JOBS).json() == []
    approved = client.post(f"/api/cases/{case['id']}/sharing-approval", json=CONSENT)
    assert approved.status_code == 200, approved.text
    job, = client.get(jobs_url).json()
    assert job["id"] == approved.json()["partner_job_id"]
    assert client.get(HEATFIX_JOBS).json() == []


def test_manager_cannot_replace_a_contractor_or_override_connector_url(client):
    assert client.post(MANAGER_CONTRACTORS, json=MANAGER_CONTRACTOR).status_code == 201
    assert client.post(MANAGER_CONTRACTORS, json=MANAGER_CONTRACTOR | {"name": "Other"}).status_code == 409
    for reserved in ("heatfix", "fibrenet", "warmwerk"):
        assert client.post(MANAGER_CONTRACTORS, json=MANAGER_CONTRACTOR | {"slug": reserved}).status_code == 409
    for invalid in ({"slug": "../heatfix"}, {"region": " "}, {"name": " "}, {"base_url": "https://example.invalid"}):
        assert client.post(MANAGER_CONTRACTORS, json=MANAGER_CONTRACTOR | invalid).status_code == 422
    saved = client.get(MANAGER_CONTRACTORS).json()
    assert [row["name"] for row in saved if row["slug"] == MANAGER_CONTRACTOR["slug"]] == [MANAGER_CONTRACTOR["name"]]


@pytest.mark.parametrize("city", ["Düsseldorf", "Dusseldorf"])
def test_edited_repair_address_routes_to_contractor_in_that_city(client, city):
    address = f"Synthetic Street 15, 40210 {city}, Germany"
    profile = "/api/units/unit_4b/residents/c_202/profile"
    contractor = MANAGER_CONTRACTOR | {"name": "HeetsFix", "slug": "dusseldorf-heating", "region": "Dusseldorf"}
    assert client.post(MANAGER_CONTRACTORS, json=contractor).status_code == 201
    assert client.patch(profile, json={"acting_resident_id": "c_202", "address": address}).status_code == 200

    case = create_case(client)
    expected = {"id": "p_manager_dusseldorf-heating", "name": "HeetsFix"}
    assert case["sharing_request"]["partner"] == expected
    assert case["unit_id"] == "unit_4b"
    assert case["building_repair"] is None

    approval = f"/api/cases/{case['id']}/sharing-approval"
    approved = client.post(approval, json=CONSENT | {"expected_partner_id": expected["id"]})
    assert approved.status_code == 200, approved.text
    job, = client.get("/partners/dusseldorf-heating/connector/jobs").json()
    assert job["payload"]["property"]["address"] == address
    assert client.get(HEATFIX_JOBS).json() == []


def test_existing_draft_requires_consent_for_updated_recipient(client):
    case = create_case(client)
    assert case["partner_id"] == "p_heatfix"
    path = f"/api/cases/{case['id']}"
    region = MANAGER_CONTRACTOR | {"name": "HeetsFix", "slug": "dusseldorf-heating", "region": "Dusseldorf"}
    assert client.post(MANAGER_CONTRACTORS, json=region).status_code == 201

    profile = "/api/units/unit_4b/residents/c_202/profile"
    address = {"acting_resident_id": "c_202", "address": "Demo Street 15, Düsseldorf"}
    assert client.patch(profile, json=address).status_code == 200
    updated = client.get(path).json()
    assert updated["sharing_request"]["partner"]["name"] == "HeetsFix"
    assert client.post(path + "/sharing-approval", json=CONSENT | {"expected_partner_id": "p_heatfix"}).status_code == 409
    assert client.post(path + "/sharing-approval", json=CONSENT).status_code == 409
    assert client.get(HEATFIX_JOBS).json() == client.get("/partners/dusseldorf-heating/connector/jobs").json() == []

    approved = client.post(path + "/sharing-approval", json=CONSENT | {"expected_partner_id": updated["partner_id"]})
    assert approved.status_code == 200, approved.text
    assert approved.json()["partner_id"] == updated["partner_id"]
    assert client.patch(profile, json=address | {"address": "Demo Street 15, Aachen"}).status_code == 200
    assert client.get(path).json()["partner_id"] == updated["partner_id"]


def test_unknown_city_uses_stable_fallback_until_local_contractor_is_registered(client):
    profile = "/api/units/unit_4b/residents/c_202/profile"
    assert client.patch(profile, json={"acting_resident_id": "c_202", "address": "Demo Street 21, 50667 Köln"}).status_code == 200
    other = {"name": "Demo Heating Berlin", "slug": "berlin-heating", "region": "Berlin"}
    assert client.post(MANAGER_CONTRACTORS, json=other).status_code == 201
    case = create_case(client)
    url = f"/api/cases/{case['id']}"
    assert case["partner_id"] in {"p_heatfix", "p_manager_berlin-heating"}
    assert client.get(url).json()["partner_id"] == case["partner_id"]
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE cases SET partner_id='p_warmwerk' WHERE id=?", (case["id"],))
    assert client.get(url).json()["partner_id"] == case["partner_id"]
    assert client.post(url + "/sharing-approval", json=CONSENT | {"expected_partner_id": "p_warmwerk"}).status_code == 409

    local = {"name": "Demo Heating Köln", "slug": "cologne-heating", "region": "Koln"}
    assert client.post(MANAGER_CONTRACTORS, json=local).status_code == 201
    assert client.get(url).json()["sharing_request"]["partner"]["name"] == local["name"]
    assert client.post(url + "/sharing-approval", json=CONSENT | {"expected_partner_id": case["partner_id"]}).status_code == 409


def test_country_fallback_respects_explicit_foreign_country(client):
    profile = "/api/units/unit_4b/residents/c_202/profile"
    address = {"acting_resident_id": "c_202", "address": "Demo Street 1, 1000 Brussels, Belgium"}
    assert client.patch(profile, json=address).status_code == 200
    case = create_case(client)
    assert case["partner_id"] is None
    contractor = MANAGER_CONTRACTOR | {"region": "Ghent, Belgium"}
    assert client.post(MANAGER_CONTRACTORS, json=contractor).status_code == 201
    assert client.get(f"/api/cases/{case['id']}").json()["sharing_request"]["partner"]["name"] == contractor["name"]


def test_manager_groups_repairs_across_units_by_contractor_and_preserves_dispatch_address(client):
    first = create_case(client)
    contractor = {"name": "HeetsFix", "slug": "dusseldorf-heating", "region": "Dusseldorf"}
    assert client.post(MANAGER_CONTRACTORS, json=contractor).status_code == 201
    profile = "/api/units/unit_2a/residents/c_203/profile"
    details = {"acting_resident_id": "c_203", "address": "Demo Street 15, 40210 Düsseldorf", "unit": "2A rear entrance"}
    assert client.patch(profile, json=details).status_code == 200
    report = load("case-create.json") | {
        "unit_id": "unit_2a", "resident_id": "c_203", "description": "Some radiators are lukewarm.",
    }
    routed = client.post("/api/cases", json=report)
    assert routed.status_code == 201, routed.text
    second = routed.json()
    approval = {"approved_by": "c_203", "approved_fields": CONSENT["approved_fields"],
                "expected_partner_id": "p_manager_dusseldorf-heating"}
    assert client.post(f"/api/cases/{second['id']}/sharing-approval", json=approval).status_code == 200

    uncovered = "Demo Street 16, 1000 Brussels, Belgium"
    assert client.patch(profile, json=details | {"address": uncovered}).status_code == 200
    third = client.post("/api/cases", json=report).json()
    result = client.get("/api/manager/repairs")
    assert result.status_code == 200, result.text
    heatfix, heetsfix = result.json()
    assert heatfix["contractor"] == {"id": "p_heatfix", "name": "HeatFix Aachen GmbH"}
    assert {first["id"], "case_000"} <= {repair["case"]["id"] for repair in heatfix["repairs"]}
    assert heetsfix["contractor"] == {"id": "p_manager_dusseldorf-heating", "name": "HeetsFix"}
    assigned = next(repair for repair in heetsfix["repairs"] if repair["case"]["id"] == second["id"])
    assert (assigned["case"]["id"], assigned["case"]["unit_id"]) == (second["id"], "unit_2a")
    assert (assigned["address"], assigned["unit"]) == (details["address"], details["unit"])
    remaining, = [repair for group in (heatfix, heetsfix) for repair in group["repairs"]
                  if repair["case"]["id"] == third["id"]]
    assert remaining["address"] == uncovered
