import smtplib

import httpx

from tests.test_building_repairs import approve, report
from tests.test_repair_loop import CALLBACK, HEADER, approved, case_url, job_url, offered, select  # noqa: F401
from tests.test_vertical_slice import load


def inbox(client, recipient_type, recipient_id):
    result = client.get("/api/notifications", params={"recipient_type": recipient_type, "recipient_id": recipient_id})
    assert result.status_code == 200, result.text
    return result.json()


def prefs_url(recipient_type, recipient_id):
    return f"/api/recipients/{recipient_type}/{recipient_id}/notification-preferences"


def test_case_flow_notifies_resident_once_even_when_a_callback_is_replayed(client, offered):
    assert select(client, offered, offered["slots"][0]["slot_id"]).status_code == 200
    start = load("partner-repair-events.json")[0] | {"request_id": offered["id"], "job_id": offered["partner_job_id"]}
    assert client.post(CALLBACK, json=start, headers=HEADER).json()["duplicate"] is False
    assert client.post(CALLBACK, json=start, headers=HEADER).json()["duplicate"] is True

    items = inbox(client, "resident", "c_202")
    assert [n["title"] for n in reversed(items)] == [
        "Repair request sent", "Choose an appointment",
        "Appointment confirmed", "Repair started"]
    assert all(n["case_id"] == offered["id"] and "code" not in n["body"] for n in items)
    # Lena prefers the portal: the box has everything, the bot sends nothing.
    assert {d["status"] for n in items for d in n["deliveries"]} == {"skipped"}
    read = client.post(f"/api/notifications/{items[0]['id']}/read").json()
    assert read["read_at"] is not None


def test_turning_a_category_off_stops_delivery_but_keeps_the_in_app_notification(client):
    prefs = client.get(prefs_url("resident", "c_203")).json()
    assert [c["category"] for c in prefs["categories"]] == [
        "request_acknowledged", "appointment", "repair_progress", "building_incident"]
    assert all(c["email"] and not c["text"] for c in prefs["categories"])
    body = {"categories": [{"category": "invoice_approval", "email": True, "text": False}]}
    assert client.put(prefs_url("resident", "c_203"), json=body).status_code == 422

    kitchen = {"description": "Kitchen radiator stays lukewarm.", "symptoms": ["radiators_cold"]}
    case = report(client, "2a", **kitchen)
    assert inbox(client, "resident", "c_203") == []  # a saved report is not sent until sharing is approved
    approve(client, case)
    assert inbox(client, "resident", "c_203")[0]["deliveries"][0] == {
        "channel": "email", "status": "sent_simulated", "error": None,
        "sent_at": inbox(client, "resident", "c_203")[0]["deliveries"][0]["sent_at"]}

    body = {"categories": [{"category": "request_acknowledged", "email": False, "text": False}]}
    assert client.put(prefs_url("resident", "c_203"), json=body).status_code == 200
    approve(client, report(client, "2a", **kitchen))
    latest = inbox(client, "resident", "c_203")
    assert len(latest) == 2 and latest[0]["title"] == "Repair request sent"
    assert latest[0]["deliveries"][0]["status"] == "skipped"


def test_owner_hears_about_building_outage_and_invoice_above_limit(client):
    report(client, description="No heat at all", symptoms=[])
    second = report(client, "2a", description="Cold since Friday", symptoms=["no_heat"])
    owner = inbox(client, "owner", "o_101")
    assert [n["category"] for n in owner] == ["building_incident"]
    assert owner[0]["deliveries"][0]["status"] == "sent_simulated"
    assert "key safe" not in owner[0]["body"].lower()

    lead = approve(client, second).json()
    job = job_url(lead)
    assert client.post(job + "/accept").status_code == 200
    assert client.post(job + "/offer-slots").status_code == 200
    assert select(client, lead, client.get(case_url(lead)).json()["slots"][0]["slot_id"]).status_code == 200
    _, complete, invoice = load("partner-repair-events.json")
    assert client.post(job + "/start").status_code == 200
    assert client.post(job + "/complete", json=complete["data"]).status_code == 200
    assert client.post(job + "/invoice", json=invoice["data"] | {"amount_cents": 300001}).status_code == 200

    for recipient_type, recipient_id in (("owner", "o_101"), ("manager", "manager")):
        latest = inbox(client, recipient_type, recipient_id)[0]
        assert latest["category"] == "invoice_approval" and "€3,000.01" in latest["body"]


def test_failing_transport_is_recorded_and_the_case_still_progresses(client, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setenv("NOTIFY_TRANSPORT", "smtp")
    monkeypatch.setattr(smtplib, "SMTP", refuse)
    case = report(client, "2a", description="Kitchen radiator stays lukewarm.", symptoms=["radiators_cold"])
    approved_case = approve(client, case)
    assert approved_case.status_code == 200 and approved_case.json()["status"] == "PARTNER_REQUESTED"
    email = inbox(client, "resident", "c_203")[0]["deliveries"][0]
    assert email["status"] == "failed" and "smtp down" in email["error"]


def test_phone_preference_pushes_text_messages_to_a_private_ntfy_topic(client, monkeypatch):
    sent = []
    monkeypatch.setenv("NOTIFY_TRANSPORT", "ntfy")
    monkeypatch.setattr(httpx, "post", lambda url, json, timeout: sent.append((url, json)) or httpx.Response(
        200, request=httpx.Request("POST", url)))
    profile = "/api/units/unit_4b/residents/c_202/profile"
    assert client.patch(profile, json={"acting_resident_id": "c_202", "preferred_contact": "phone"}).status_code == 200
    prefs = client.get(prefs_url("resident", "c_202")).json()
    assert all(c["text"] and not c["email"] for c in prefs["categories"])
    topic = prefs["ntfy_topic"]
    assert topic.startswith("centrix-") and len(topic) >= 30

    approve(client, report(client, description="Kitchen radiator stays lukewarm.", symptoms=["radiators_cold"]))
    assert inbox(client, "resident", "c_202")[0]["deliveries"][1] == {
        "channel": "text", "status": "sent", "error": None,
        "sent_at": inbox(client, "resident", "c_202")[0]["deliveries"][1]["sent_at"]}
    assert sent == [("https://ntfy.sh", {"topic": topic, "title": "Repair request sent", "message":
                     "We sent your repair request to the repair partner with the details you approved.",
                     "click": "http://localhost:5173/#cases"})]

    # Updating another contact field keeps the subscribed topic.
    body = {"telegram_chat_id": "123456", "categories": []}
    assert client.put(prefs_url("resident", "c_202"), json=body).json()["ntfy_topic"] == topic
