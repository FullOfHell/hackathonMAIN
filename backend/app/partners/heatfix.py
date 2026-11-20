"""Simulated heating contractor 'HeatFix Aachen GmbH'. Stands in for an external partner system.
It implements the partner side of connector v1; it must not touch centrix case tables directly."""
import json
import uuid
from datetime import datetime, time, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from app.db import get_db, now_iso
from app.integrations.connector import callback_url, partner_webhook_secret
from app.schemas import PartnerJobRequest, RepairInvoice, RepairReport, SlotChoice

PARTNER_ID = "p_heatfix"
router = APIRouter(prefix="/partners/heatfix", tags=["mock partner: HeatFix"])

ALLOWED_JOB_ACTIONS = {
    "accepted": {"received"},
    "rejected": {"received", "accepted"},
    "slots_offered": {"accepted"},
    "in_progress": {"scheduled"},
    "completed": {"in_progress"},
    "invoice_ready": {"completed"},
}


@router.get("/connector/capabilities")
def capabilities():
    return {
        "schema_version": "1.0",
        "partner_id": PARTNER_ID,
        "service_types": ["heating_repair"],
        "regions": ["Aachen"],
        "required_fields": ["address", "unit", "issue"],
        "optional_fields": ["heating_type", "access_details", "name", "contact", "previous_record"],
        "events": list(ALLOWED_JOB_ACTIONS),
    }


@router.post("/connector/jobs", status_code=201)
def create_job(job: PartnerJobRequest, response: Response, conn=Depends(get_db)):
    if job.service_type != "heating_repair":
        raise HTTPException(422, "unsupported service_type")
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    inserted = conn.execute("INSERT INTO partner_jobs VALUES (?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING",
                            (job_id, PARTNER_ID, job.idempotency_key, job.request_id, job.model_dump_json(),
                             "received", now_iso()))
    if not inserted.rowcount:
        existing = conn.execute("SELECT id, status FROM partner_jobs WHERE idempotency_key=?",
                                (job.idempotency_key,)).fetchone()
        conn.commit()
        response.status_code = 200
        return {"job_id": existing["id"], "status": existing["status"], "duplicate": True}
    conn.commit()
    return {"job_id": job_id, "status": "received", "duplicate": False}


@router.get("/connector/jobs")
def list_jobs(conn=Depends(get_db)):
    return [{**dict(j), "payload": json.loads(j["payload"])}
            for j in conn.execute("SELECT * FROM partner_jobs WHERE partner_id=? ORDER BY received_at DESC", (PARTNER_ID,))]


@router.get("/connector/jobs/{job_id}")
def get_job(job_id: str, conn=Depends(get_db)):
    row = conn.execute(
        "SELECT j.*,o.payload AS offer,b.slot_id AS booked_slot_id FROM partner_jobs j "
        "LEFT JOIN heatfix_callbacks o ON o.job_id=j.id AND o.type='slots_offered' "
        "LEFT JOIN heatfix_bookings b ON b.job_id=j.id WHERE j.id=? AND j.partner_id=?",
        (job_id, PARTNER_ID)).fetchone()
    if not row:
        raise HTTPException(404, "job not found")
    job = dict(row)
    offer = job.pop("offer")
    job["slots"] = json.loads(offer)["data"]["slots"] if offer else []
    job["payload"] = json.loads(job["payload"])
    return job


def get_callback_client():
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        yield client


def _demo_slots(job_id: str) -> list[dict]:
    tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
    slots = []
    for hour in (8, 14):
        start = datetime.combine(tomorrow, time(hour), tzinfo=timezone.utc)
        slots.append({"slot_id": f"{job_id}_{hour:02d}", "start": start.isoformat(),
                      "end": (start + timedelta(hours=2)).isoformat()})
    return slots


def _send_event(conn, client, job_id: str, event_type: str, data: dict | None = None):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        job = get_job(job_id, conn)
        try:
            url = httpx.URL(job["payload"]["callback_url"])
        except httpx.InvalidURL as exc:
            raise HTTPException(422, "invalid callback URL") from exc
        trusted = httpx.URL(callback_url())
        if (url.scheme, url.host, url.port) != (trusted.scheme, trusted.host, trusted.port) or url.userinfo:
            raise HTTPException(422, "callback URL must use the configured centrix origin")
        previous = conn.execute("SELECT payload,delivered FROM heatfix_callbacks WHERE job_id=? AND type=?",
                                (job_id, event_type)).fetchone()
        if previous:
            event = json.loads(previous["payload"])
            if data is not None and data != event["data"]:
                raise HTTPException(409, "this action already has a different document")
            if previous["delivered"]:
                return job
        else:
            if job["status"] not in ALLOWED_JOB_ACTIONS[event_type]:
                raise HTTPException(409, f"cannot send {event_type} for a {job['status']} job")
            if conn.execute("SELECT 1 FROM heatfix_callbacks WHERE job_id=? AND delivered=0", (job_id,)).fetchone():
                raise HTTPException(409, "retry the previous action to deliver its pending callback")
            if event_type == "slots_offered":
                data = {"slots": _demo_slots(job_id)}
            event = {"schema_version": "1.0", "event_id": f"evt_{uuid.uuid4().hex}", "job_id": job_id,
                     "request_id": job["request_id"], "type": event_type, "occurred_at": now_iso(), "data": data or {}}
            conn.execute("INSERT INTO heatfix_callbacks (job_id,type,payload) VALUES (?,?,?)",
                         (job_id, event_type, json.dumps(event)))
            conn.execute("UPDATE partner_jobs SET status=? WHERE id=?", (event_type, job_id))

    # Commit the exact callback before delivery. A retry after a lost reply reuses its ID and slots.
    try:
        response = client.post(url, json=event, headers={"X-Partner-Secret": partner_webhook_secret()},
                               follow_redirects=False)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(502, "retry this action because centrix did not acknowledge the callback") from exc
    with conn:
        conn.execute("UPDATE heatfix_callbacks SET delivered=1 WHERE job_id=? AND type=?", (job_id, event_type))
    return get_job(job_id, conn)


@router.post("/connector/jobs/{job_id}/accept")
def accept(job_id: str, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, "accepted")


@router.post("/connector/jobs/{job_id}/reject")
def reject(job_id: str, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, "rejected")


@router.post("/connector/jobs/{job_id}/offer-slots")
def offer_slots(job_id: str, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, "slots_offered")


@router.post("/connector/jobs/{job_id}/book")
def book(job_id: str, body: SlotChoice, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        job = get_job(job_id, conn)
        if job["booked_slot_id"] is not None:
            if job["booked_slot_id"] != body.slot_id:
                raise HTTPException(409, "job already booked for another slot")
        else:
            if not any(slot["slot_id"] == body.slot_id for slot in job["slots"]):
                raise HTTPException(422, "slot was not offered for this job")
            conn.execute("INSERT INTO heatfix_bookings (job_id,slot_id) VALUES (?,?)", (job_id, body.slot_id))
            conn.execute("UPDATE partner_jobs SET status='scheduled' WHERE id=?", (job_id,))
    return {"job_id": job_id, "status": "scheduled", "slot_id": body.slot_id}


@router.post("/connector/jobs/{job_id}/start")
def start_work(job_id: str, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, "in_progress")


@router.post("/connector/jobs/{job_id}/complete")
def complete_work(job_id: str, body: RepairReport, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, "completed", body.model_dump())


@router.post("/connector/jobs/{job_id}/invoice")
def submit_invoice(job_id: str, body: RepairInvoice, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, "invoice_ready", body.model_dump())
