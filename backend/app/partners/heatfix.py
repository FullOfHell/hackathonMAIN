"""Simulated heating contractor 'HeatFix Aachen GmbH'. Stands in for an external partner system.
It implements the partner side of connector v1; it must not touch centrix case tables directly."""
import json
import uuid
from datetime import datetime, time, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from app.db import get_db, now_iso
from app.integrations.connector import callback_url, partner_webhook_secret
from app.schemas import PartnerJobRequest, SlotChoice

PARTNER_ID = "p_heatfix"
router = APIRouter(prefix="/partners/heatfix", tags=["mock partner: HeatFix"])


@router.get("/connector/capabilities")
def capabilities():
    return {
        "schema_version": "1.0",
        "partner_id": PARTNER_ID,
        "service_types": ["heating_repair"],
        "regions": ["Aachen"],
        "required_fields": ["address", "unit", "issue"],
        "optional_fields": ["heating_type", "access_details", "name", "contact", "previous_record"],
        "events": ["accepted", "rejected", "slots_offered"],
    }


@router.post("/connector/jobs", status_code=201)
def create_job(job: PartnerJobRequest, response: Response, conn=Depends(get_db)):
    if job.service_type != "heating_repair":
        raise HTTPException(422, "unsupported service_type")
    conn.execute("BEGIN IMMEDIATE")
    existing = conn.execute("SELECT * FROM partner_jobs WHERE idempotency_key=?", (job.idempotency_key,)).fetchone()
    if existing:
        response.status_code = 200
        return {"job_id": existing["id"], "status": existing["status"], "duplicate": True}
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    conn.execute("INSERT INTO partner_jobs VALUES (?,?,?,?,?,?,?)",
                 (job_id, PARTNER_ID, job.idempotency_key, job.request_id, job.model_dump_json(), "received", now_iso()))
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


def _send_event(conn, client, job_id: str, event_type: str):
    allowed_from = {"accepted": {"received"}, "rejected": {"received", "accepted"}, "slots_offered": {"accepted"}}
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
            if previous["delivered"]:
                return job
            event = json.loads(previous["payload"])
        else:
            if job["status"] not in allowed_from[event_type]:
                raise HTTPException(409, f"cannot send {event_type} for a {job['status']} job")
            if conn.execute("SELECT 1 FROM heatfix_callbacks WHERE job_id=? AND delivered=0", (job_id,)).fetchone():
                raise HTTPException(409, "retry the previous action to deliver its pending callback")
            data = {"slots": _demo_slots(job_id)} if event_type == "slots_offered" else {}
            event = {"schema_version": "1.0", "event_id": f"evt_{uuid.uuid4().hex}", "job_id": job_id,
                     "request_id": job["request_id"], "type": event_type, "occurred_at": now_iso(), "data": data}
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
