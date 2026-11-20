from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import connect
from app.integrations.connector import get_partner_client
from app.main import app
from tests.test_repair_loop import case_url, job_url, select
from tests.test_vertical_slice import load


def report(client, unit="4b", **changes):
    body = load("case-create.json") | {
        "unit_id": f"unit_{unit}", "resident_id": {"4b": "c_202", "2a": "c_203"}[unit], **changes}
    result = client.post("/api/cases", json=body)
    assert result.status_code == 201, result.text
    return result.json()


def approve(client, case):
    return client.post(case_url(case) + "/sharing-approval", json={
        "approved_by": case["resident_id"], "approved_fields": ["address", "unit", "issue"]})


def history(client, case):
    return client.get(case_url(case) + "/events").json()


def test_two_reports_one_consented_job_and_both_residents_follow_it(client):
    first = report(client, description="No heat at all", symptoms=[])
    second = report(client, "2a", description="Cold since Friday", symptoms=["no_heat"])
    assert second["building_repair"]["repair_status"] is None
    for case in (first, second):
        assert history(client, case)[-1]["type"] == "building.outage_detected"
    assert client.get("/partners/heatfix/connector/jobs").json() == []

    # The second reporter can consent first. The first tenant's information stays on their case.
    lead = approve(client, second).json()
    assert lead["building_repair"]["is_dispatch_case"] and lead["building_repair"]["scope_confirmed"]
    jobs = client.get("/partners/heatfix/connector/jobs").json()
    assert len(jobs) == 1 and jobs[0]["request_id"] == second["id"]
    order = jobs[0]["payload"]
    assert order["property"] == {"unit": "2A", "address": load("unit-context.json")["property"]["address"]}
    assert order["resident"] == {} and order["issue"]["repair_scope"] == "building_heating"
    assert first["id"] not in str(order) and first["resident_id"] not in str(order)
    follower = client.get(case_url(first)).json()
    assert follower["status"] == "LINKED_TO_BUILDING_REPAIR" and follower["sharing_approval"] is None
    assert "sharing_request" not in follower and approve(client, follower).status_code == 409
    assert follower["building_repair"]["partner_job_id"] == lead["partner_job_id"]
    assert approve(client, lead).json() == lead

    job = job_url(lead)
    assert client.post(job + "/accept").status_code == 200
    assert client.post(job + "/offer-slots").status_code == 200
    offered = client.get(case_url(lead)).json()
    slot = offered["slots"][0]
    assert select(client, follower, slot["slot_id"]).status_code == 422
    assert select(client, lead, slot["slot_id"]).status_code == 200
    latest = client.get(case_url(first)).json()
    expected = load("building-repair.json") | {
        "outage_id": second["building_repair"]["outage_id"], "partner_job_id": lead["partner_job_id"],
        "appointment": {"start": slot["start"], "end": slot["end"]}}
    assert latest["building_repair"] == expected
    assert latest["appointment"] is None

    _, complete, invoice = load("partner-repair-events.json")
    assert client.post(job + "/start").status_code == 200
    assert client.post(job + "/complete", json=complete["data"]).status_code == 200
    assert client.post(job + "/invoice", json=invoice["data"] | {"amount_cents": 300001}).status_code == 200
    assert client.get(case_url(first)).json()["building_repair"]["repair_status"] == "AWAITING_INVOICE_APPROVAL"
    assert client.get(case_url(first)).json()["status"] == "LINKED_TO_BUILDING_REPAIR"
    assert client.post(case_url(lead) + "/approve-invoice").status_code == 200
    with TestClient(app) as restarted:
        final = restarted.get(case_url(first)).json()
        assert final["status"] == final["building_repair"]["repair_status"] == "CLOSED"
        assert final["invoice"] is None and final["completion_report"] is None
        assert final in restarted.get("/api/units/unit_4b/cases").json()
        assert [e["payload"]["repair_status"] for e in history(restarted, first)
                if e["type"] == "building.repair_updated"] == [
                    "SLOTS_OFFERED", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "AWAITING_INVOICE_APPROVAL", "CLOSED"]
        assert len(restarted.get("/partners/heatfix/connector/jobs").json()) == 1
        # A resolved incident cannot swallow a new report.
        assert report(restarted, "2a")["building_repair"] is None


def test_concurrent_approvals_choose_one_dispatch_case(client):
    first, second = report(client), report(client, "2a")
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda case: approve(client, case), [first, second]))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert len(client.get("/partners/heatfix/connector/jobs").json()) == 1


def test_additional_reports_join_active_group_and_can_withdraw_individually(client):
    first, second = report(client), report(client, "2a")
    lead = approve(client, first).json()
    extra = report(client, "4b")
    assert extra["building_repair"]["outage_id"] == lead["building_repair"]["outage_id"]
    assert extra["status"] == "LINKED_TO_BUILDING_REPAIR"
    assert client.post(case_url(extra) + "/cancel", json={"resident_id": "c_202"}).json()["building_repair"] is None
    assert client.get(case_url(second)).json()["building_repair"]["partner_job_id"] == lead["partner_job_id"]


def test_unconfirmed_scope_cannot_close_another_units_case(client):
    lead = approve(client, report(client)).json()
    url = job_url(lead)
    assert client.post(url + "/accept").is_success
    assert client.post(url + "/offer-slots").is_success
    offered = client.get(case_url(lead)).json()
    assert select(client, lead, offered["slots"][0]["slot_id"]).is_success
    assert client.post(url + "/start").is_success
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})),
                      base_url="http://testserver") as unreliable:
        app.dependency_overrides[get_partner_client] = lambda: unreliable
        follower = report(client, "2a")
    app.dependency_overrides[get_partner_client] = lambda: client
    assert client.post(url + "/complete", json={"summary": "Individual unit repair finished."}).is_success
    assert client.post(url + "/invoice", json=load("partner-repair-events.json")[2]["data"]).is_success
    assert client.get(case_url(lead)).json()["status"] == "CLOSED"
    assert client.get(case_url(follower)).json()["status"] == "NEEDS_HUMAN_REVIEW"
    assert client.post(case_url(follower) + "/sync-building-repair").status_code == 502


def test_joins_dispatched_case_and_scope_retry_keeps_original_job(client):
    lead = approve(client, report(client)).json()
    # Simulate a reply lost after HeatFix successfully received the scope change.
    def lost_reply(req):
        assert client.put(req.url.path, content=req.content, headers={"Content-Type": "application/json"}).is_success
        raise httpx.ReadTimeout("lost reply")

    with httpx.Client(transport=httpx.MockTransport(lost_reply), base_url="http://testserver") as unreliable:
        app.dependency_overrides[get_partner_client] = lambda: unreliable
        follower = report(client, "2a")
        assert follower["building_repair"]["scope_confirmed"] is False
        assert client.post(case_url(follower) + "/sync-building-repair").status_code == 502
    app.dependency_overrides[get_partner_client] = lambda: client
    for _ in range(2):
        assert client.post(case_url(follower) + "/sync-building-repair").json()["building_repair"]["scope_confirmed"]
    assert client.get(job_url(lead)).json()["payload"]["issue"]["repair_scope"] == "building_heating"
    assert sum(e["type"] == "building.partner_scope_confirmed" for e in history(client, lead)) == 1
    assert client.post(job_url(lead) + "/reject").is_success
    assert client.get(case_url(follower)).json()["status"] == "NEEDS_HUMAN_REVIEW"
    assert report(client, "2a")["building_repair"] is None


def test_second_report_arriving_during_unconfirmed_dispatch_uses_original_order(client):
    first = report(client)
    followers = []

    def handoff(request):
        assert client.post(request.url.path, content=request.content,
                           headers={"Content-Type": "application/json"}).is_success
        followers.append(report(client, "2a"))
        raise httpx.ReadTimeout("first dispatch reply lost")

    with httpx.Client(transport=httpx.MockTransport(handoff), base_url="http://testserver") as unreliable:
        app.dependency_overrides[get_partner_client] = lambda: unreliable
        assert approve(client, first).status_code == 502
    follower, = followers
    assert follower["status"] == "LINKED_TO_BUILDING_REPAIR"
    assert follower["building_repair"]["partner_job_id"] is None
    app.dependency_overrides[get_partner_client] = lambda: client
    assert approve(client, follower).status_code == 409
    lead = approve(client, first).json()
    assert lead["building_repair"]["scope_confirmed"]
    job, = client.get("/partners/heatfix/connector/jobs").json()
    assert job["id"] == client.get(case_url(follower)).json()["building_repair"]["partner_job_id"]


@pytest.mark.parametrize(("first_time", "matches"), [
    ("2026-11-19T19:00:00Z", True), ("2026-11-19T18:59:59Z", False)])
def test_distinct_units_in_inclusive_24_hour_window(client, monkeypatch, first_time, matches):
    monkeypatch.setattr("app.api.cases.now_iso", lambda: first_time)
    assert report(client)["building_repair"] is None
    assert report(client)["building_repair"] is None
    monkeypatch.setattr("app.api.cases.now_iso", lambda: "2026-11-20T19:00:00Z")
    second = report(client, "2a")
    assert bool(second["building_repair"]) is matches


def test_other_properties_partial_heat_and_withdrawn_cases_do_not_contribute(client):
    first = report(client)
    partial = report(client, "2a", symptoms=[], description="No heat in one room")
    assert partial["building_repair"] is None
    with closing(connect()) as conn, conn:
        conn.execute("INSERT INTO properties (id,address,region) VALUES ('other','Other demo address','Aachen')")
        conn.execute("UPDATE units SET property_id='other' WHERE id='unit_2a'")
    other = report(client, "2a")
    assert other["building_repair"] is None
    assert client.post(case_url(other) + "/cancel", json={"resident_id": "c_203"}).is_success
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE units SET property_id='prop_musterstr_12' WHERE id='unit_2a'")
    assert report(client, "4b")["building_repair"] is None
    second = report(client, "2a")
    assert second["building_repair"] is not None
    assert client.post(case_url(second) + "/cancel", json={"resident_id": "c_203"}).is_success
    assert client.get(case_url(first)).json()["building_repair"] is None
    assert history(client, first)[-1]["type"] == "building.outage_withdrawn"
