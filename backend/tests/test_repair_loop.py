from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone

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
        assert client.post(url + "/offer-slots").status_code == 409
    app.dependency_overrides[get_callback_client] = lambda: client
    assert client.post(url + "/accept").status_code == 200
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
