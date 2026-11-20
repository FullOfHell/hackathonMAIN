import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from threading import Barrier

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import connect, init_db
from app.integrations.connector import get_partner_client
from app.main import app
from app.partners.heatfix import get_callback_client
from tests.test_vertical_slice import create_case, load

CALLBACK = "/api/integrations/partner-events"
HEADER = {"X-Partner-Secret": "test-only-partner-secret"}


def case_url(case):
    return f"/api/cases/{case['id']}"


def job_url(case):
    return f"/partners/heatfix/connector/jobs/{case['partner_job_id']}"


def event(case, **fields):
    return load("partner-event.json") | {
        "request_id": case["id"], "job_id": case["partner_job_id"], **fields}


def select(client, case, slot_id, resident_id=None):
    return client.post(case_url(case) + "/select-slot",
                       json={"slot_id": slot_id, "resident_id": resident_id or case["resident_id"]})


@pytest.fixture
def approved(client):
    case = create_case(client)
    result = client.post(case_url(case) + "/sharing-approval", json=load("sharing-approval.json"))
    assert result.status_code == 200, result.text
    return result.json()


@pytest.fixture
def offered(client, approved):
    accepted = client.post(job_url(approved) + "/accept")
    assert accepted.status_code == 200, accepted.text
    assert client.get(case_url(approved)).json()["status"] == "PARTNER_REQUESTED"
    offer = client.post(job_url(approved) + "/offer-slots")
    assert offer.status_code == 200, offer.text
    return client.get(case_url(approved)).json()


def test_approve_accept_offer_select_and_restart(client, approved, offered):
    preferences = load("case-create.json")["availability_preferences"]
    job = client.get(job_url(approved)).json()
    assert job["payload"]["issue"]["availability_preferences"] == approved["availability_preferences"] == preferences
    assert approved["slots"] == [] and approved["appointment"] is None
    assert offered["status"] == "SLOTS_OFFERED"
    assert offered["slots"] == job["slots"]
    assert len(offered["slots"]) == 2
    for slot, hour in zip(offered["slots"], (8, 14)):
        start = datetime.fromisoformat(slot["start"])
        assert start.date() == datetime.now(timezone.utc).date() + timedelta(days=1)
        assert start.hour == hour and datetime.fromisoformat(slot["end"]) - start == timedelta(hours=2)

    chosen = offered["slots"][1]
    result = select(client, offered, chosen["slot_id"])
    assert result.status_code == 200, result.text
    case = result.json()
    assert case["status"] == "SCHEDULED"
    assert case["appointment"] == {**chosen, "case_id": case["id"], "booked_at": case["appointment"]["booked_at"]}
    assert datetime.fromisoformat(case["appointment"]["booked_at"].replace("Z", "+00:00")).tzinfo
    assert client.get(job_url(case)).json()["booked_slot_id"] == chosen["slot_id"]
    timeline = client.get(case_url(case) + "/events").json()
    assert [(e["payload"]["to"], e["actor"]) for e in timeline if e["type"] == "case.status_changed"][-2:] == [
        ("SLOTS_OFFERED", "partner:p_heatfix"), ("SCHEDULED", "resident:c_202")]
    assert sum(e["type"] == "partner.accepted" for e in timeline) == 1

    assert select(client, case, chosen["slot_id"]).json() == case
    assert client.post(job_url(case) + "/book", json={"slot_id": chosen["slot_id"]}).status_code == 200
    assert select(client, case, offered["slots"][0]["slot_id"]).status_code == 409
    with TestClient(app) as restarted:
        assert restarted.get(case_url(case)).json() == case
        assert restarted.get(case_url(case) + "/events").json() == timeline


def test_duplicate_callback_ignored_after_restart(client, approved):
    body = event(approved)
    first = client.post(CALLBACK, json=body, headers=HEADER)
    assert first.status_code == 200 and first.json()["duplicate"] is False
    case = client.get(case_url(approved)).json()
    assert case["slots"] == body["data"]["slots"]
    timeline = client.get(case_url(approved) + "/events").json()
    with TestClient(app) as restarted:
        duplicate = restarted.post(CALLBACK, json=body, headers=HEADER)
        assert duplicate.status_code == 200 and duplicate.json()["duplicate"] is True
        assert restarted.get(case_url(approved)).json() == case
        assert restarted.get(case_url(approved) + "/events").json() == timeline


@pytest.mark.parametrize("headers", [{}, {"X-Partner-Secret": "incorrect"}, {"X-Partner-Secret": "dev-partner-secret"}])
def test_bad_secret_changes_nothing(client, approved, headers):
    body = event(approved)
    timeline = client.get(case_url(approved) + "/events").json()
    assert client.post(CALLBACK, json=body, headers=headers).status_code == 401
    assert client.get(case_url(approved)).json() == approved
    assert client.get(case_url(approved) + "/events").json() == timeline
    assert client.post(CALLBACK, json=body, headers=HEADER).json()["duplicate"] is False


def test_local_partner_callbacks_work_without_a_configured_secret(client, approved, monkeypatch):
    monkeypatch.delenv("PARTNER_WEBHOOK_SECRET")
    assert client.post(CALLBACK, json=event(approved), headers={"X-Partner-Secret": "dev-partner-secret"}).status_code == 401
    assert client.post(job_url(approved) + "/accept").status_code == 200


@pytest.mark.parametrize(("change", "expected"), [
    ({"job_id": "job_wrong"}, 409),
    ({"request_id": "case_missing"}, 404),
    ({"type": "scheduled"}, 422),
    ({"data": {"slots": []}}, 422),
])
def test_invalid_callback_can_be_corrected(client, approved, change, expected):
    assert client.post(CALLBACK, json=event(approved, **change), headers=HEADER).status_code == expected
    assert client.get(case_url(approved)).json() == approved
    assert client.post(CALLBACK, json=event(approved), headers=HEADER).json()["duplicate"] is False


def test_rejection_declines_case_and_invalid_transition_rolls_back(client, approved):
    assert client.post(job_url(approved) + "/reject").status_code == 200
    timeline = client.get(case_url(approved) + "/events").json()
    assert timeline[-1]["payload"]["to"] == "DECLINED"
    assert timeline[-1]["actor"] == "partner:p_heatfix"
    assert client.post(CALLBACK, json=event(approved), headers=HEADER).status_code == 409
    case = client.get(case_url(approved)).json()
    assert (case["status"], case["slots"], case["appointment"]) == ("DECLINED", [], None)
    assert client.get(case_url(approved) + "/events").json() == timeline
    with closing(connect()) as conn:
        assert conn.execute("SELECT COUNT(*) FROM processed_partner_events").fetchone()[0] == 1


def test_only_owner_can_book_a_slot_offered_to_this_case(client, offered):
    slot_id = offered["slots"][0]["slot_id"]
    assert select(client, offered, slot_id, "c_203").status_code == 403
    assert select(client, offered, "unoffered").status_code == 422
    other = create_case(client)
    assert select(client, other, slot_id).status_code == 422
    assert client.get(case_url(offered)).json() == offered
    assert client.get(job_url(offered)).json()["booked_slot_id"] is None


def test_lost_callback_reply_reuses_original_event_and_slots(client, approved):
    assert client.post(job_url(approved) + "/accept").status_code == 200

    def lose_reply(request):
        assert str(request.url) == client.get(job_url(approved)).json()["payload"]["callback_url"]
        assert request.headers["X-Partner-Secret"] == HEADER["X-Partner-Secret"]
        delivered = client.post(CALLBACK, content=request.content, headers=HEADER | {"Content-Type": "application/json"})
        assert delivered.status_code == 200
        raise httpx.ReadTimeout("reply lost")

    with httpx.Client(transport=httpx.MockTransport(lose_reply)) as flaky:
        app.dependency_overrides[get_callback_client] = lambda: flaky
        assert client.post(job_url(approved) + "/offer-slots").status_code == 502
    timeline = client.get(case_url(approved) + "/events").json()
    slots = client.get(case_url(approved)).json()["slots"]
    app.dependency_overrides[get_callback_client] = lambda: client
    retried = client.post(job_url(approved) + "/offer-slots")
    assert retried.status_code == 200 and retried.json()["slots"] == slots
    assert client.get(case_url(approved) + "/events").json() == timeline


def test_lost_booking_reply_reconciles_on_retry(client, offered):
    slot_id = offered["slots"][0]["slot_id"]

    def lose_reply(request):
        booked = client.post(request.url.path, content=request.content, headers={"Content-Type": "application/json"})
        assert booked.status_code == 200
        raise httpx.ReadTimeout("reply lost")

    with httpx.Client(base_url="http://testserver", transport=httpx.MockTransport(lose_reply)) as flaky:
        app.dependency_overrides[get_partner_client] = lambda: flaky
        assert select(client, offered, slot_id).status_code == 502
    assert client.get(case_url(offered)).json() == offered
    assert client.get(case_url(offered) + "/events").json()[-1]["type"] == "partner.booking_unconfirmed"
    assert client.get(job_url(offered)).json()["booked_slot_id"] == slot_id
    app.dependency_overrides[get_partner_client] = lambda: client
    assert select(client, offered, slot_id).json()["status"] == "SCHEDULED"


def test_unconfirmed_callback_stays_pending_until_matching_receipt(client, approved):
    url = job_url(approved)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(
        200, json={"event_id": "different_event", "duplicate": False}
    ))) as wrong:
        app.dependency_overrides[get_callback_client] = lambda: wrong
        assert client.post(url + "/accept").status_code == 502
        pending = client.get(url).json()["pending_callback"]
        assert pending["type"] == "accepted"
        retry_url = f"{url}/callbacks/{pending['event_id']}/retry"
        assert client.post(retry_url).status_code == 502
        assert client.get(url).json()["pending_callback"] == pending
        assert client.post(url + "/offer-slots").status_code == 409
    app.dependency_overrides[get_callback_client] = lambda: client
    assert client.post(retry_url).json()["pending_callback"] is None
    assert sum(e["type"] == "partner.accepted" for e in client.get(case_url(approved) + "/events").json()) == 1


def test_wrong_booking_confirmation_does_not_schedule(client, offered):
    slot_id = offered["slots"][0]["slot_id"]
    wrong = {"job_id": "wrong_job", "slot_id": slot_id, "status": "scheduled"}
    with httpx.Client(base_url="http://testserver",
                      transport=httpx.MockTransport(lambda _: httpx.Response(200, json=wrong))) as partner:
        app.dependency_overrides[get_partner_client] = lambda: partner
        assert select(client, offered, slot_id).status_code == 502
    assert client.get(case_url(offered)).json() == offered


def test_callbacks_only_send_credentials_to_configured_origin(client):
    payload = load("partner-job.json") | {"callback_url": "https://other.example/partner-events"}
    result = client.post("/partners/heatfix/connector/jobs", json=payload)
    assert result.status_code == 201
    url = f"/partners/heatfix/connector/jobs/{result.json()['job_id']}"
    assert client.post(url + "/accept").status_code == 422
    assert client.get(url).json()["status"] == "received"


def test_repeated_slot_ids_rejected_before_persisting(client, approved):
    body = event(approved)
    body["data"]["slots"][1]["slot_id"] = body["data"]["slots"][0]["slot_id"]
    assert client.post(CALLBACK, json=body, headers=HEADER).status_code == 422
    assert client.get(case_url(approved)).json() == approved
    assert client.post(CALLBACK, json=event(approved), headers=HEADER).json()["duplicate"] is False


@pytest.mark.parametrize("same_slot", [True, False])
def test_concurrent_selections_make_one_appointment(client, offered, same_slot):
    first, second = [slot["slot_id"] for slot in offered["slots"]]
    with ThreadPoolExecutor(2) as pool:
        requests = [pool.submit(select, client, offered, slot) for slot in (first, first if same_slot else second)]
        statuses = sorted(request.result().status_code for request in requests)
    assert statuses == ([200, 200] if same_slot else [200, 409])
    booked = client.get(job_url(offered)).json()["booked_slot_id"]
    assert client.get(case_url(offered)).json()["appointment"]["slot_id"] == booked
    events = client.get(case_url(offered) + "/events").json()
    assert sum(e["payload"].get("to") == "SCHEDULED" for e in events) == 1


def test_existing_database_and_old_case_request_default_to_empty_preferences(client):
    with closing(connect()) as conn, conn:
        conn.execute("ALTER TABLE cases DROP COLUMN availability_preferences")
    init_db()
    assert client.get("/api/cases/case_000").json()["availability_preferences"] == []
    old_request = load("case-create.json")
    del old_request["availability_preferences"]
    assert client.post("/api/cases", json=old_request).json()["availability_preferences"] == []


@pytest.fixture
def scheduled(client, offered):
    response = select(client, offered, offered["slots"][0]["slot_id"])
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(("action", "kind", "target", "lost_after_commit"), [
    ("complete", "completion_report", "COMPLETED", False),
    ("invoice", "invoice", "CLOSED", True),
])
def test_recover_document_callback_after_restart(client, scheduled, action, kind, target, lost_after_commit):
    jobs_url = "/partners/heatfix/connector/jobs"
    url, case = job_url(scheduled), case_url(scheduled)
    _, complete, invoice = load("partner-repair-events.json")
    assert client.post(url + "/start").is_success
    command = complete if action == "complete" else invoice
    if action == "invoice":
        assert client.post(url + "/complete", json=complete["data"]).is_success
    assert client.get(jobs_url).json()[0]["pending_callback"] is None
    assert client.get(url).json()["pending_callback"] is None

    original = {}

    def fail_delivery(request):
        original.update(json.loads(request.content))
        assert original["data"] == command["data"] and request.headers["X-Partner-Secret"] == HEADER["X-Partner-Secret"]
        if lost_after_commit:
            receipt = client.post(CALLBACK, json=original, headers=HEADER)
            assert receipt.json() == {"event_id": original["event_id"], "duplicate": False}
            raise httpx.ReadTimeout("reply lost after centrix committed")
        raise httpx.ConnectError("centrix unavailable before delivery")

    with httpx.Client(transport=httpx.MockTransport(fail_delivery)) as offline:
        app.dependency_overrides[get_callback_client] = lambda: offline
        assert client.post(url + "/" + action, json=command["data"]).status_code == 502
    snapshot = client.get(case).json()
    assert (snapshot["status"] == target) == lost_after_commit
    assert (snapshot[kind] is not None) == lost_after_commit
    event_id = original["event_id"]
    pending = {"event_id": event_id, "type": command["type"]}
    retry_url = f"{url}/callbacks/{event_id}/retry"
    assert client.get(url).json()["pending_callback"] == pending

    with TestClient(app) as restarted:
        assert restarted.get(jobs_url).json()[0]["pending_callback"] == pending
        assert restarted.get(url).json()["pending_callback"] == pending
        assert restarted.post(CALLBACK, json=original).status_code == 401
        assert restarted.get(case).json() == snapshot

        both_sending = Barrier(2, timeout=10)
        receipts = []

        def deliver(request):
            assert str(request.url) == "http://testserver" + CALLBACK
            assert json.loads(request.content) == original
            assert request.headers["X-Partner-Secret"] == HEADER["X-Partner-Secret"]
            both_sending.wait()
            ack = restarted.post(CALLBACK, content=request.content, headers=request.headers)
            assert ack.status_code == 200 and ack.json()["event_id"] == event_id
            receipts.append(ack.json()["duplicate"])
            return httpx.Response(200, json=ack.json())

        with httpx.Client(transport=httpx.MockTransport(deliver)) as recovered:
            app.dependency_overrides[get_callback_client] = lambda: recovered
            with ThreadPoolExecutor(2) as pool:
                replies = list(pool.map(lambda _: restarted.post(retry_url), range(2)))
            job = restarted.get(url).json()
            assert all(r.status_code == 200 and r.json() == job for r in replies)
            assert job["pending_callback"] is None
            assert restarted.get(jobs_url).json()[0]["pending_callback"] is None
            assert restarted.post(retry_url).json() == job
        assert sorted(receipts) == [lost_after_commit, True]
        final = restarted.get(case).json()
        assert final["status"] == target
        assert {k: final[kind][k] for k in command["data"]} == command["data"]
        transitions = [e["payload"] for e in restarted.get(case + "/events").json()
                       if e["type"] == "case.status_changed" and e["payload"]["to"] == target]
        assert [t["event_id"] for t in transitions] == [event_id]
        with closing(connect()) as conn:
            docs = conn.execute("SELECT event_id FROM case_documents WHERE case_id=? AND kind=?",
                                (scheduled["id"], kind)).fetchall()
            assert [doc["event_id"] for doc in docs] == [event_id]


def test_retry_requires_matching_job_event_and_empty_input(client, offered):
    url = job_url(offered)
    # The prior acceptance is acknowledged even when a newer callback is pending.
    accepted = next(e["payload"]["event_id"] for e in client.get(case_url(offered) + "/events").json()
                    if e["type"] == "partner.accepted")
    other = client.post("/partners/heatfix/connector/jobs", json=load("partner-job.json")).json()["job_id"]
    requests = []

    def unavailable(request):
        requests.append(request)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(unavailable)) as offline:
        app.dependency_overrides[get_callback_client] = lambda: offline
        assert client.post(url + "/fail", json={"reason": ""}).status_code == 422
        assert client.get(url).json()["pending_callback"] is None
        assert client.post(url + "/fail", json={"reason": "Demo contractor unavailable"}).status_code == 502
        job = client.get(url).json()
        pending = job["pending_callback"]
        retry = f"/callbacks/{pending['event_id']}/retry"
        assert client.post(url + retry, json={"data": {"reason": "replacement"}}).status_code == 422
        assert client.post(url + "/callbacks/unknown/retry").status_code == 404
        assert client.post("/partners/heatfix/connector/jobs/missing" + retry).status_code == 404
        assert client.post(f"/partners/heatfix/connector/jobs/{other}" + retry).status_code == 404
        assert client.post(f"{url}/callbacks/{accepted}/retry", json={}).json() == job
        assert len(requests) == 1
    jobs = {j["id"]: j for j in client.get("/partners/heatfix/connector/jobs").json()}
    assert jobs[other]["pending_callback"] is None
    assert jobs[offered["partner_job_id"]]["pending_callback"] == pending


def test_repair_closes_on_the_original_unit_and_survives_restart(client, scheduled):
    other = client.post("/api/cases", json=load("case-create.json") | {
        "unit_id": "unit_2a", "resident_id": "c_203"}).json()
    start, complete, invoice = load("partner-repair-events.json")
    url = job_url(scheduled)
    assert client.post(url + "/start").json()["status"] == start["type"]
    assert client.get(case_url(scheduled)).json()["status"] == "IN_PROGRESS"
    assert client.post(url + "/complete", json=complete["data"]).json()["status"] == complete["type"]
    completed = client.get(case_url(scheduled)).json()
    assert completed["status"] == "COMPLETED"
    assert completed["completion_report"]["summary"] == complete["data"]["summary"]
    assert completed["invoice"] is None

    # Two deliveries from the partner dashboard must produce one invoice and one closure.
    with ThreadPoolExecutor(2) as pool:
        replies = [pool.submit(client.post, url + "/invoice", json=invoice["data"]) for _ in range(2)]
        assert [r.result().status_code for r in replies] == [200, 200]
    closed = client.get(case_url(scheduled)).json()
    example = load("case-closed.json")
    assert set(closed) == set(example)
    assert closed["status"] == example["status"] == "CLOSED"
    assert closed["appointment"] == scheduled["appointment"]
    for kind, data in [("completion_report", complete["data"]), ("invoice", invoice["data"])]:
        doc = closed[kind]
        assert set(doc) == set(example[kind])
        assert {key: doc[key] for key in data} == data
        assert (doc["case_id"], doc["unit_id"]) == (closed["id"], closed["unit_id"])
        downloaded = client.get(doc["url"])
        assert downloaded.json() == doc and doc["filename"] in downloaded.headers["Content-Disposition"]
        assert client.get(case_url(other) + "/documents/" + kind).status_code == 404

    timeline = client.get(case_url(closed) + "/events").json()
    assert [e["payload"]["to"] for e in timeline if e["type"] == "case.status_changed"] == [
        "TRIAGED", "AWAITING_SHARING_APPROVAL", "PARTNER_REQUESTED", "SLOTS_OFFERED", "SCHEDULED",
        "IN_PROGRESS", "COMPLETED", "CLOSED"]
    assert timeline[0]["type"] == "maintenance.case_created"
    assert all(e["case_id"] == closed["id"] and e["actor"] and e["timestamp"] for e in timeline)
    assert all(e["actor"] == "partner:p_heatfix" and e["payload"]["job_id"] == closed["partner_job_id"]
               for e in timeline[-3:])
    assert client.post(url + "/invoice", json=invoice["data"] | {"amount_cents": 1}).status_code == 409
    with TestClient(app) as restarted:
        assert restarted.get(case_url(closed)).json() == closed
        assert restarted.get(case_url(closed) + "/events").json() == timeline
        unit_cases = restarted.get("/api/units/unit_4b/cases").json()
        assert closed in unit_cases and other not in unit_cases
        assert restarted.get("/api/units/unit_2a/cases").json()[0]["id"] == other["id"]
        assert restarted.get(closed["invoice"]["url"]).json() == closed["invoice"]
        assert restarted.get(url).json()["status"] == "invoice_ready"


def test_document_callbacks_require_order_and_matching_replays(client, scheduled):
    events = [e | {"request_id": scheduled["id"], "job_id": scheduled["partner_job_id"]}
              for e in load("partner-repair-events.json")]
    start, complete, invoice = events

    def deliver(body):
        return client.post(CALLBACK, json=body, headers=HEADER)

    assert deliver(complete).status_code == 409
    assert deliver(invoice).status_code == 409
    assert deliver(complete | {"data": {"summary": " "}}).status_code == 422
    assert deliver(invoice | {"data": invoice["data"] | {"amount_cents": -1}}).status_code == 422
    assert deliver(invoice | {"data": invoice["data"] | {"currency": "USD"}}).status_code == 422
    assert client.get(case_url(scheduled)).json() == scheduled
    for body in events:
        assert deliver(body).json() == {"event_id": body["event_id"], "duplicate": False}
    closed = client.get(case_url(scheduled)).json()
    history = client.get(case_url(closed) + "/events").json()
    # Receipts from the earlier schema can recover invoice and report contents from the documents.
    with closing(connect()) as conn, conn:
        conn.execute("ALTER TABLE processed_partner_events DROP COLUMN event_data")
    init_db()
    assert deliver(invoice | {"data": invoice["data"] | {"amount_cents": 1}}).status_code == 409
    assert deliver(complete | {"event_id": invoice["event_id"]}).status_code == 409
    assert deliver(event(closed, type="accepted", data={})).status_code == 409
    for body in (invoice, complete, start):
        assert deliver(body).json() == {"event_id": body["event_id"], "duplicate": True}
    assert client.get(case_url(closed)).json() == closed
    assert client.get(case_url(closed) + "/events").json() == history


def test_failed_job_escalates_once_and_cannot_be_booked(client, offered):
    url = job_url(offered)
    assert client.post(case_url(offered) + "/escalate").status_code == 409
    failure = load("partner-failed.json")["data"]
    assert client.post(url + "/fail", json=failure).json()["status"] == "failed"
    assert client.post(url + "/fail", json=failure).status_code == 200
    failed = client.get(case_url(offered)).json()
    assert failed["status"] == "FAILED" and failed["appointment"] is None
    assert client.get(case_url(failed) + "/events").json()[-1]["payload"]["reason"] == failure["reason"]
    slot = {"slot_id": offered["slots"][0]["slot_id"]}
    assert client.post(url + "/book", json=slot).status_code == 409
    assert select(client, failed, slot["slot_id"]).status_code == 409
    assert client.post(case_url(failed) + "/escalate").json()["status"] == "NEEDS_HUMAN_REVIEW"
    history = client.get(case_url(failed) + "/events").json()
    assert history[-1]["actor"] == "manager"
    assert client.post(case_url(failed) + "/escalate").status_code == 200
    assert client.get(case_url(failed) + "/events").json() == history


@pytest.mark.parametrize(("cents", "status"), [
    (299999, "CLOSED"), (300000, "CLOSED"), (300001, "AWAITING_INVOICE_APPROVAL")])
def test_invoice_threshold_and_manager_approval(client, scheduled, cents, status):
    case = case_url(scheduled)
    assert client.post(case + "/approve-invoice").status_code == 409
    start, complete, invoice = [e | {"request_id": scheduled["id"], "job_id": scheduled["partner_job_id"]}
                                for e in load("partner-repair-events.json")]
    invoice["data"]["amount_cents"] = cents
    for body in (start, complete, invoice, invoice):
        assert client.post(CALLBACK, json=body, headers=HEADER).is_success
    with TestClient(app) as restarted:
        current = restarted.get(case).json()
        assert current["status"] == status and current["invoice"]["amount_cents"] == cents
        assert current in restarted.get("/api/units/unit_4b/cases").json()
        if status == "CLOSED":
            assert restarted.post(case + "/approve-invoice").status_code == 409
            return
        conflicting = invoice | {"event_id": "replacement", "data": invoice["data"] | {"amount_cents": 100}}
        assert restarted.post(CALLBACK, json=conflicting, headers=HEADER).status_code == 409
        assert restarted.get(case).json() == current
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(lambda _: restarted.post(case + "/approve-invoice"), range(2)))
        assert all(r.is_success and r.json()["status"] == "CLOSED" for r in responses)
        assert restarted.post(CALLBACK, json=invoice, headers=HEADER).json()["duplicate"]
        events = restarted.get(case + "/events").json()
        assert sum(e["type"] == "invoice.manager_approved" for e in events) == 1
        assert events[-1]["actor"] == "manager" and events[-1]["payload"]["to"] == "CLOSED"


def test_upgrade_flags_previously_auto_closed_large_invoice_once(client, scheduled):
    for e in load("partner-repair-events.json"):
        body = e | {"request_id": scheduled["id"], "job_id": scheduled["partner_job_id"]}
        assert client.post(CALLBACK, json=body, headers=HEADER).is_success
    with closing(connect()) as conn, conn:
        conn.execute("UPDATE case_documents SET content=json_set(content,'$.amount_cents',350000) "
                     "WHERE case_id=? AND kind='invoice'", (scheduled["id"],))
        conn.execute("PRAGMA user_version=0")
    init_db()
    init_db()
    case = case_url(scheduled)
    assert client.get(case).json()["status"] == "AWAITING_INVOICE_APPROVAL"
    events = client.get(case + "/events").json()
    assert sum(e["actor"] == "system:migration" for e in events) == 1
    assert client.post(case + "/approve-invoice").is_success
    init_db()
    assert client.get(case).json()["status"] == "CLOSED"
