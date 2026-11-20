"""One notification source for the in-app box and the outbound noreply bot.

`on_event` runs inside the caller's transaction (from record_event). `deliver_pending` runs after the
request committed, on its own connection, and never raises: delivery failures are recorded only.
"""
import json
import logging
import os
import secrets
import smtplib
import sqlite3
import threading
from email.message import EmailMessage

import httpx

from app.db import connect, now_iso
from app.states import CaseStatus as S

log = logging.getLogger(__name__)

CATEGORIES = {
    "resident": ("request_acknowledged", "appointment", "repair_progress", "building_incident"),
    "owner": ("building_incident", "invoice_approval"),
    "manager": ("invoice_approval",),
}
MANAGER_ID = "manager"
CHANNELS = ("email", "text")
_delivery_lock = threading.Lock()

# Resident wording follows frontend/src/repairNotifications.ts where a template already exists.
STATUS_NOTICES = {
    S.PARTNER_REQUESTED: ("request_acknowledged", "Repair request sent",
                          "We sent your repair request to the repair partner with the details you approved."),
    S.LINKED_TO_BUILDING_REPAIR: ("request_acknowledged", "Report added to building repair",
                                  "Your report is linked to the heating repair already arranged for your building. "
                                  "No further action is needed."),
    S.SLOTS_OFFERED: ("appointment", "Choose an appointment",
                      "Your contractor offered appointment times. Open your request to pick one."),
    S.IN_PROGRESS: ("repair_progress", "Repair started", "Your contractor has started the repair."),
    S.COMPLETED: ("repair_progress", "Repair completed", "Your contractor marked your repair as complete."),
    S.CLOSED: ("repair_progress", "Request closed", "Your repair request is closed."),
    S.DECLINED: ("repair_progress", "Repair request declined",
                 "Your contractor declined your repair request. Your property manager is handling it now."),
    S.FAILED: ("repair_progress", "Repair could not be completed",
               "The contractor reported a problem with your repair. Your property manager is handling it now."),
}


def _frontend(path: str) -> str:
    return os.getenv("PUBLIC_FRONTEND_URL", "http://localhost:5173").rstrip("/") + path


def _add(conn, *, case_id, property_id, recipient_type, recipient_id, category, title, body, link, source):
    conn.execute(
        "INSERT INTO notifications (case_id,property_id,recipient_type,recipient_id,category,title,body,link,"
        "dedupe_key,created_at) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(dedupe_key) DO NOTHING",
        (case_id, property_id, recipient_type, recipient_id, category, title, body, link,
         f"{category}:{recipient_type}:{recipient_id}:{source}", now_iso()))


def _source(event_id, payload):
    # A partner callback carries its own event ID, so a replayed callback can never notify twice.
    partner_event = payload.get("event_id")
    return f"partner:{partner_event}:{payload.get('to', '')}" if partner_event else f"event:{event_id}"


def _owners(conn, property_id):
    return [r["id"] for r in conn.execute("SELECT id FROM owners WHERE property_id=?", (property_id,))]


def on_event(conn: sqlite3.Connection, case_id: str, event_id: int, event_type: str, payload: dict) -> None:
    case = conn.execute("SELECT c.id,c.resident_id,c.unit_id,u.property_id,p.address FROM cases c "
                        "JOIN units u ON u.id=c.unit_id JOIN properties p ON p.id=u.property_id WHERE c.id=?",
                        (case_id,)).fetchone()
    if case is None:
        return
    resident = dict(case_id=case_id, property_id=case["property_id"], recipient_type="resident",
                    recipient_id=case["resident_id"], link=_frontend("/#cases"), source=_source(event_id, payload))

    # A saved report is still a draft until the resident approves sharing, so the first resident
    # notification is the hand-off to the partner (or the link to a building repair already under way).
    if event_type == "building.outage_detected":
        _building_incident(conn, case, payload["outage_id"])
    elif event_type == "case.status_changed":
        target = payload.get("to")
        if target in STATUS_NOTICES:
            category, title, body = STATUS_NOTICES[S(target)]
            _add(conn, category=category, title=title, body=body, **resident)
        elif target == S.SCHEDULED:
            slot = conn.execute("SELECT start,end FROM appointment_slots WHERE case_id=? AND slot_id=?",
                                (case_id, payload.get("slot_id"))).fetchone()
            when = f" for {slot['start']} to {slot['end']}" if slot else ""
            _add(conn, category="appointment", title="Appointment confirmed",
                 body=f"Your repair appointment is confirmed{when}.", **resident)
        elif target == S.NEEDS_HUMAN_REVIEW and payload.get("from") == S.LINKED_TO_BUILDING_REPAIR:
            _add(conn, category="repair_progress", title="Building repair needs review",
                 body="The building heating repair needs attention. Your property manager is handling it now.",
                 **resident)
        elif target == S.AWAITING_INVOICE_APPROVAL:
            _invoice_approval(conn, case, event_id, payload)


def _building_incident(conn, case, outage_id):
    source = f"outage:{outage_id}"
    title = "Heating issue in your building"
    body = (f"A heating issue has been reported at {case['address']}. "
            "The property manager is arranging one technician visit for the building.")
    for owner_id in _owners(conn, case["property_id"]):
        _add(conn, case_id=case["id"], property_id=case["property_id"], recipient_type="owner",
             recipient_id=owner_id, category="building_incident", title=title, body=body,
             link=_frontend("/#manager"), source=source)
    # Residents who have not reported it themselves hear about it without seeing anyone else's case.
    for r in conn.execute(
            "SELECT r.id FROM residents r JOIN units u ON u.id=r.unit_id WHERE u.property_id=? AND u.id NOT IN "
            "(SELECT c.unit_id FROM outage_cases m JOIN cases c ON c.id=m.case_id WHERE m.outage_id=?)",
            (case["property_id"], outage_id)):
        _add(conn, case_id=None, property_id=case["property_id"], recipient_type="resident", recipient_id=r["id"],
             category="building_incident", title=title, body=body, link=_frontend("/#cases"), source=source)


def _invoice_approval(conn, case, event_id, payload):
    row = conn.execute("SELECT event_data FROM processed_partner_events WHERE event_id=?",
                       (payload.get("event_id"),)).fetchone()
    data = json.loads(row["event_data"]) if row and row["event_data"] else {}
    amount = f" of €{data['amount_cents'] / 100:,.2f}" if "amount_cents" in data else ""
    body = (f"An invoice{amount} for the heating repair at {case['address']} is above the €3,000 "
            "approval limit and is waiting for approval.")
    recipients = [("owner", o) for o in _owners(conn, case["property_id"])] + [("manager", MANAGER_ID)]
    for recipient_type, recipient_id in recipients:
        _add(conn, case_id=case["id"], property_id=case["property_id"], recipient_type=recipient_type,
             recipient_id=recipient_id, category="invoice_approval", title="Invoice needs approval", body=body,
             link=_frontend("/#manager"), source=_source(event_id, payload))


# ---- recipients and preferences -------------------------------------------------------------

def recipient(conn, recipient_type: str, recipient_id: str) -> dict | None:
    if recipient_type == "resident":
        row = conn.execute("SELECT email,preferred_contact FROM residents WHERE id=?", (recipient_id,)).fetchone()
    elif recipient_type == "owner":
        row = conn.execute("SELECT email,NULL AS preferred_contact FROM owners WHERE id=?", (recipient_id,)).fetchone()
    elif recipient_type == "manager" and recipient_id == MANAGER_ID:
        row = {"email": os.getenv("NOTIFY_MANAGER_EMAIL") or None, "preferred_contact": None}
    else:
        return None
    if row is None:
        return None
    contact = conn.execute("SELECT telegram_chat_id,ntfy_topic FROM notification_contacts "
                           "WHERE recipient_type=? AND recipient_id=?", (recipient_type, recipient_id)).fetchone()
    return {"email": row["email"], "preferred_contact": row["preferred_contact"],
            "telegram_chat_id": contact["telegram_chat_id"] if contact else None,
            "ntfy_topic": contact["ntfy_topic"] if contact else None}


def ensure_ntfy_topic(conn, recipient_type: str, recipient_id: str) -> None:
    # ntfy topics are public: an unguessable name is the only thing keeping a recipient's feed private.
    topic = f"centrix-{secrets.token_urlsafe(18)}"
    conn.execute("INSERT INTO notification_contacts (recipient_type,recipient_id,ntfy_topic) VALUES (?,?,?) "
                 "ON CONFLICT(recipient_type,recipient_id) DO UPDATE SET ntfy_topic=excluded.ntfy_topic "
                 "WHERE ntfy_topic IS NULL", (recipient_type, recipient_id, topic))


def _default(recipient_type, preferred_contact, category):
    if recipient_type == "resident":
        return {"email": preferred_contact == "email", "text": preferred_contact == "phone"}
    if recipient_type == "owner":
        return {"email": True, "text": False}
    return {"email": False, "text": False}


def get_preferences(conn, recipient_type: str, recipient_id: str) -> dict | None:
    who = recipient(conn, recipient_type, recipient_id)
    if who is None:
        return None
    saved = {r["category"]: {"email": bool(r["email"]), "text": bool(r["text"])} for r in conn.execute(
        "SELECT category,email,text FROM notification_preferences WHERE recipient_type=? AND recipient_id=?",
        (recipient_type, recipient_id))}
    return {"recipient_type": recipient_type, "recipient_id": recipient_id,
            "telegram_chat_id": who["telegram_chat_id"], "ntfy_topic": who["ntfy_topic"],
            "categories": [{"category": c, **saved.get(c, _default(recipient_type, who["preferred_contact"], c))}
                           for c in CATEGORIES[recipient_type]]}


def save_preferences(conn, recipient_type: str, recipient_id: str, categories: list[dict],
                     contacts: dict) -> None:
    """`contacts` holds only the contact fields the caller supplied; omitted ones keep their values."""
    for item in categories:
        conn.execute("INSERT INTO notification_preferences VALUES (?,?,?,?,?) "
                     "ON CONFLICT(recipient_type,recipient_id,category) DO UPDATE SET "
                     "email=excluded.email, text=excluded.text",
                     (recipient_type, recipient_id, item["category"], int(item["email"]), int(item["text"])))
    conn.execute("INSERT INTO notification_contacts (recipient_type,recipient_id) VALUES (?,?) ON CONFLICT DO NOTHING",
                 (recipient_type, recipient_id))
    for field in ("telegram_chat_id", "ntfy_topic"):  # fixed column names, never from the request
        if field in contacts:
            conn.execute(f"UPDATE notification_contacts SET {field}=? WHERE recipient_type=? AND recipient_id=?",
                         (contacts[field], recipient_type, recipient_id))


def list_notifications(conn, recipient_type: str, recipient_id: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM notifications WHERE recipient_type=? AND recipient_id=? "
                        "ORDER BY created_at DESC, id DESC", (recipient_type, recipient_id)).fetchall()
    return [_with_deliveries(conn, row) for row in rows]


def _with_deliveries(conn, row) -> dict:
    item = {k: row[k] for k in row.keys() if k != "dedupe_key"}
    item["deliveries"] = [dict(d) for d in conn.execute(
        "SELECT channel,status,error,sent_at FROM notification_deliveries WHERE notification_id=? ORDER BY channel",
        (row["id"],))]
    return item


def mark_read(conn, notification_id: int) -> dict | None:
    conn.execute("UPDATE notifications SET read_at=? WHERE id=? AND read_at IS NULL", (now_iso(), notification_id))
    row = conn.execute("SELECT * FROM notifications WHERE id=?", (notification_id,)).fetchone()
    return _with_deliveries(conn, row) if row else None


# ---- outbound noreply bot -------------------------------------------------------------------

def _transports() -> set[str]:
    return {t.strip() for t in os.getenv("NOTIFY_TRANSPORT", "outbox").split(",") if t.strip()}


def _message(n) -> str:
    return f"{n['title']}\n\n{n['body']}\n\n{n['link']}"


def _send_email(to: str, n) -> None:
    msg = EmailMessage()
    msg["From"] = os.getenv("NOTIFY_FROM", "centrix <noreply@centrix.example>")
    msg["To"], msg["Subject"] = to, n["title"]
    msg.set_content(_message(n) + "\n\nThis is an automated message from a noreply address.")
    with smtplib.SMTP(os.getenv("SMTP_HOST", "localhost"), int(os.getenv("SMTP_PORT", "1025")), timeout=10) as smtp:
        if os.getenv("SMTP_STARTTLS", "false").lower() in ("1", "true", "yes"):
            smtp.starttls()
        if os.getenv("SMTP_USER"):
            smtp.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(msg)


def _send_ntfy(topic: str, n) -> None:
    # JSON publishing keeps UTF-8 titles intact; "click" opens the portal link from the phone notification.
    response = httpx.post(os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/"),
                          json={"topic": topic, "title": n["title"], "message": n["body"], "click": n["link"]},
                          timeout=10)
    response.raise_for_status()


def _send_telegram(chat_id: str, n) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    response = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": _message(n)}, timeout=10)
    response.raise_for_status()


def _deliver(n, channel: str, enabled: bool, who: dict | None) -> tuple[str, str | None]:
    if not enabled:
        return "skipped", "disabled in preferences"
    transports = _transports()
    if channel == "email":
        transport, field, label = "smtp", "email", "email address"
    elif "ntfy" in transports:
        transport, field, label = "ntfy", "ntfy_topic", "ntfy topic"
    else:
        transport, field, label = "telegram", "telegram_chat_id", "Telegram chat ID"
    address = (who or {}).get(field)
    if not address:
        return "skipped", f"no {label} on file"
    if transport not in transports:
        return "sent_simulated", None
    send = {"smtp": _send_email, "ntfy": _send_ntfy, "telegram": _send_telegram}[transport]
    try:
        send(address, n)
    except Exception as exc:  # noqa: BLE001 - any transport error is recorded, never raised
        return "failed", f"{type(exc).__name__}: {exc}"[:300]
    return "sent", None


def deliver_pending() -> None:
    """Send every committed notification that has no delivery record yet. Safe to call repeatedly."""
    try:
        with _delivery_lock:
            conn = connect()
            try:
                pending = conn.execute(
                    "SELECT * FROM notifications n WHERE (SELECT COUNT(*) FROM notification_deliveries d "
                    "WHERE d.notification_id=n.id) < 2 ORDER BY id").fetchall()
                for n in pending:
                    if "ntfy" in _transports():
                        with conn:
                            ensure_ntfy_topic(conn, n["recipient_type"], n["recipient_id"])
                    who = recipient(conn, n["recipient_type"], n["recipient_id"])
                    prefs = get_preferences(conn, n["recipient_type"], n["recipient_id"]) or {"categories": []}
                    allowed = next((c for c in prefs["categories"] if c["category"] == n["category"]), {})
                    for channel in CHANNELS:
                        if conn.execute("SELECT 1 FROM notification_deliveries WHERE notification_id=? AND channel=?",
                                        (n["id"], channel)).fetchone():
                            continue
                        status, error = _deliver(n, channel, bool(allowed.get(channel)), who)
                        with conn:
                            conn.execute("INSERT INTO notification_deliveries VALUES (?,?,?,?,?) "
                                         "ON CONFLICT DO NOTHING", (n["id"], channel, status, error, now_iso()))
            finally:
                conn.close()
    except Exception:  # noqa: BLE001 - delivery must never break the case flow
        log.exception("notification delivery pass failed; it will be retried after the next write")
