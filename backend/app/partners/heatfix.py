"""Simulated delivery partners implementing connector v1 on their own job records."""
import json
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Response

from app.db import get_db, now_iso
from app.integrations.connector import callback_url, partner_webhook_secret
from app.partners.registry import local_capabilities
from app.schemas import BuildingJobScope, FailureReason, PartnerJobRequest, RepairInvoice, RepairReport, SlotChoice

router = APIRouter(prefix="/partners/{slug}", tags=["simulated delivery partners"])

ALLOWED_JOB_ACTIONS = {
    "accepted": {"received"},
    "rejected": {"received", "accepted"},
    "slots_offered": {"accepted"},
    "in_progress": {"scheduled"},
    "completed": {"in_progress"},
    "invoice_ready": {"completed"},
    "failed": {"received", "accepted", "slots_offered", "scheduled", "in_progress"},
}


def delivery_partner(slug: str, conn=Depends(get_db)) -> dict:
    manifest = local_capabilities(conn, slug)
    if manifest["kind"] != "delivery":
        raise HTTPException(404, "partner does not provide delivery jobs")
    return manifest


DeliveryPartner = Annotated[dict, Depends(delivery_partner)]


@router.post("/connector/jobs", status_code=201)
def create_job(job: PartnerJobRequest, response: Response, partner: DeliveryPartner, conn=Depends(get_db)):
    if job.service_type not in partner["categories"]:
        raise HTTPException(422, "unsupported service_type")
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    inserted = conn.execute("INSERT INTO partner_jobs VALUES (?,?,?,?,?,?,?) ON CONFLICT(idempotency_key) DO NOTHING",
                            (job_id, partner["partner_id"], job.idempotency_key, job.request_id, job.model_dump_json(),
                             "received", now_iso()))
    if not inserted.rowcount:
        existing = conn.execute("SELECT id, status, request_id, partner_id FROM partner_jobs WHERE idempotency_key=?",
                                (job.idempotency_key,)).fetchone()
        if existing["request_id"] != job.request_id or existing["partner_id"] != partner["partner_id"]:
            raise HTTPException(409, "idempotency key already belongs to a different case or provider")
        conn.commit()
        response.status_code = 200
        return {"job_id": existing["id"], "status": existing["status"], "duplicate": True}
    conn.commit()
    return {"job_id": job_id, "status": "received", "duplicate": False}


# HeatFix persists at most one unacknowledged callback per job.
PENDING_CALLBACK = ("(SELECT payload FROM heatfix_callbacks WHERE job_id=j.id AND delivered=0) "
                    "AS pending_callback")


def _job_from_row(row):
    job = dict(row)
    job["payload"] = json.loads(job["payload"])
    if job["pending_callback"] is not None:
        event = json.loads(job["pending_callback"])
        job["pending_callback"] = {"event_id": event["event_id"], "type": event["type"]}
    return job


@router.get("/connector/jobs")
def list_jobs(partner: DeliveryPartner, conn=Depends(get_db)):
    rows = conn.execute(f"SELECT j.*, {PENDING_CALLBACK} FROM partner_jobs j "
                        "WHERE j.partner_id=? ORDER BY j.received_at DESC", (partner["partner_id"],))
    return [_job_from_row(row) for row in rows]


@router.put("/connector/jobs/{job_id}/scope")
def set_building_scope(job_id: str, body: BuildingJobScope, partner: DeliveryPartner, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        job = get_job(job_id, partner, conn)
        if job["payload"]["service_type"] != "heating_repair":
            raise HTTPException(422, "building scope applies to heating repairs")
        if body.request_id != job["request_id"]:
            raise HTTPException(409, "scope update does not match the original request")
        if job["payload"]["issue"].get("repair_scope") == body.scope:
            return {"job_id": job_id, **body.model_dump()}
        if job["status"] in ("completed", "invoice_ready", "rejected", "failed"):
            raise HTTPException(409, "only an active job can acquire building scope")
        job["payload"]["issue"]["repair_scope"] = body.scope
        conn.execute("UPDATE partner_jobs SET payload=? WHERE id=?", (json.dumps(job["payload"]), job_id))
    return {"job_id": job_id, **body.model_dump()}


@router.get("/connector/jobs/{job_id}")
def get_job(job_id: str, partner: DeliveryPartner, conn=Depends(get_db)):
    row = conn.execute(
        f"SELECT j.*, {PENDING_CALLBACK}, o.payload AS offer,b.slot_id AS booked_slot_id FROM partner_jobs j "
        "LEFT JOIN heatfix_callbacks o ON o.job_id=j.id AND o.type='slots_offered' "
        "LEFT JOIN heatfix_bookings b ON b.job_id=j.id WHERE j.id=? AND j.partner_id=?",
        (job_id, partner["partner_id"])).fetchone()
    if not row:
        raise HTTPException(404, "job not found")
    job = _job_from_row(row)
    offer = job.pop("offer")
    job["slots"] = json.loads(offer)["data"]["slots"] if offer else []
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


def _trusted_callback_url(job):
    try:
        url = httpx.URL(job["payload"]["callback_url"])
    except httpx.InvalidURL as exc:
        raise HTTPException(422, "invalid callback URL") from exc
    trusted = httpx.URL(callback_url())
    if not url.userinfo:
        if (url.scheme, url.host, url.port) == (trusted.scheme, trusted.host, trusted.port):
            return url
        # Older demo jobs may use the other loopback name for the same local server.
        if (url.scheme == trusted.scheme == "http"
                and {url.host, trusted.host} == {"localhost", "127.0.0.1"}
                and url.port == trusted.port and url.raw_path == trusted.raw_path and not url.fragment):
            return trusted
    raise HTTPException(422, "callback URL must use the configured centrix origin")


def _send_event(conn, client, job_id: str, partner: dict, event_type: str, data: dict | None = None):
    if event_type not in partner["events"]:
        raise HTTPException(422, "unsupported partner event")
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        job = get_job(job_id, partner, conn)
        url = _trusted_callback_url(job)
        previous = conn.execute("SELECT payload,delivered FROM heatfix_callbacks WHERE job_id=? AND type=?",
                                (job_id, event_type)).fetchone()
        if previous:
            event = json.loads(previous["payload"])
            if data is not None and data != event["data"]:
                raise HTTPException(409, "this action already has a different payload")
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

    return _deliver_callback(conn, client, url, event, partner)


def _deliver_callback(conn, client, url, event, partner):
    # Network I/O happens after the event is committed and outside any write transaction.
    try:
        response = client.post(url, json=event, headers={"X-Partner-Secret": partner_webhook_secret()},
                               follow_redirects=False)
        response.raise_for_status()
        receipt = response.json()
        if not isinstance(receipt, dict) or receipt.get("event_id") != event["event_id"]:
            raise ValueError("callback acknowledgment did not match the event")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "retry this action because centrix did not acknowledge the callback") from exc
    with conn:
        conn.execute("UPDATE heatfix_callbacks SET delivered=1 WHERE job_id=? AND type=? AND delivered=0",
                     (event["job_id"], event["type"]))
    return get_job(event["job_id"], partner, conn)


@router.post("/connector/jobs/{job_id}/callbacks/{event_id}/retry")
def retry_callback(job_id: str, event_id: str, partner: DeliveryPartner, _body: dict = Body(default_factory=dict, max_length=0),
                   conn=Depends(get_db), client=Depends(get_callback_client)):
    job = get_job(job_id, partner, conn)
    saved = conn.execute(
        "SELECT payload,delivered FROM heatfix_callbacks WHERE job_id=? AND json_extract(payload,'$.event_id')=?",
        (job_id, event_id)).fetchone()
    if not saved:
        raise HTTPException(404, "callback not found for this job")
    if saved["delivered"]:
        return job
    return _deliver_callback(conn, client, _trusted_callback_url(job), json.loads(saved["payload"]), partner)


@router.post("/connector/jobs/{job_id}/accept")
def accept(job_id: str, partner: DeliveryPartner, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, partner, "accepted")


@router.post("/connector/jobs/{job_id}/reject")
def reject(job_id: str, partner: DeliveryPartner, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, partner, "rejected")


@router.post("/connector/jobs/{job_id}/fail")
def fail_job(job_id: str, body: FailureReason, partner: DeliveryPartner, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, partner, "failed", body.model_dump())


@router.post("/connector/jobs/{job_id}/offer-slots")
def offer_slots(job_id: str, partner: DeliveryPartner, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, partner, "slots_offered")


@router.post("/connector/jobs/{job_id}/book")
def book(job_id: str, body: SlotChoice, partner: DeliveryPartner, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        job = get_job(job_id, partner, conn)
        if job["booked_slot_id"] is not None:
            if job["booked_slot_id"] != body.slot_id:
                raise HTTPException(409, "job already booked for another slot")
        else:
            if job["status"] != "slots_offered":
                raise HTTPException(409, "job is no longer offering slots")
            if not any(slot["slot_id"] == body.slot_id for slot in job["slots"]):
                raise HTTPException(422, "slot was not offered for this job")
            conn.execute("INSERT INTO heatfix_bookings (job_id,slot_id) VALUES (?,?)", (job_id, body.slot_id))
            conn.execute("UPDATE partner_jobs SET status='scheduled' WHERE id=?", (job_id,))
    return {"job_id": job_id, "status": "scheduled", "slot_id": body.slot_id}


@router.post("/connector/jobs/{job_id}/start")
def start_work(job_id: str, partner: DeliveryPartner, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, partner, "in_progress")


@router.post("/connector/jobs/{job_id}/complete")
def complete_work(job_id: str, body: RepairReport, partner: DeliveryPartner, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, partner, "completed", body.model_dump())


@router.post("/connector/jobs/{job_id}/invoice")
def submit_invoice(job_id: str, body: RepairInvoice, partner: DeliveryPartner, conn=Depends(get_db), client=Depends(get_callback_client)):
    return _send_event(conn, client, job_id, partner, "invoice_ready", body.model_dump())
