"""Receive connector v1 callbacks at the centrix boundary."""
import json
from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException

from app.db import get_db
from app.integrations.connector import partner_webhook_secret
from app.schemas import InvoiceReady, PartnerEvent, PartnerFailed, RepairCompleted, SlotsOffered
from app.services import cases as svc
from app.states import CaseStatus

router = APIRouter(prefix="/api/integrations", tags=["connector"])

EVENT_TARGETS = {
    "rejected": CaseStatus.DECLINED,
    "failed": CaseStatus.FAILED,
    "slots_offered": CaseStatus.SLOTS_OFFERED,
    "in_progress": CaseStatus.IN_PROGRESS,
    "completed": CaseStatus.COMPLETED,
    "invoice_ready": CaseStatus.CLOSED,
}


def verify_secret(x_partner_secret: str | None = Header(default=None)):
    if not x_partner_secret or not compare_digest(x_partner_secret.encode(), partner_webhook_secret().encode()):
        raise HTTPException(401, "invalid partner secret")


@router.post("/partner-events", dependencies=[Depends(verify_secret)])
def partner_event(body: PartnerEvent, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        case = conn.execute("SELECT status,partner_id,partner_job_id FROM cases WHERE id=?", (body.request_id,)).fetchone()
        if not case:
            raise HTTPException(404, "case not found")
        if body.job_id != case["partner_job_id"]:
            raise HTTPException(409, "job does not match the case")
        occurred_at = body.occurred_at.isoformat()
        event_data = json.dumps(body.model_dump(mode="json")["data"], sort_keys=True)
        receipt = (body.event_id, body.request_id, body.job_id, body.type, occurred_at, event_data)
        inserted = conn.execute(
            "INSERT INTO processed_partner_events (event_id,case_id,job_id,type,occurred_at,event_data) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(event_id) DO NOTHING", receipt)
        if not inserted.rowcount:
            matches = conn.execute(
                "SELECT 1 FROM processed_partner_events WHERE event_id=? AND case_id=? AND job_id=? AND type=? "
                "AND occurred_at=? AND (event_data IS NULL OR event_data=?)", receipt).fetchone()
            if not matches:
                raise HTTPException(409, "event ID already belongs to a different callback")
            return {"event_id": body.event_id, "duplicate": True}

        actor = f"partner:{case['partner_id']}"
        trace = {"event_id": body.event_id, "job_id": body.job_id, "type": body.type, "occurred_at": occurred_at}
        if isinstance(body, (RepairCompleted, InvoiceReady)):
            kind = "completion_report" if isinstance(body, RepairCompleted) else "invoice"
            if isinstance(body, InvoiceReady) and not conn.execute(
                "SELECT 1 FROM case_documents WHERE case_id=? AND kind='completion_report'", (body.request_id,)
            ).fetchone():
                raise HTTPException(409, "a completion report is required before invoicing")
            svc.transition(conn, body.request_id, EVENT_TARGETS[body.type], actor, {**trace, "document_kind": kind})
            conn.execute("INSERT INTO case_documents (case_id,kind,event_id,content) VALUES (?,?,?,?)",
                         (body.request_id, kind, body.event_id, body.data.model_dump_json()))
        elif body.type == "accepted":
            if case["status"] != CaseStatus.PARTNER_REQUESTED or conn.execute(
                "SELECT 1 FROM processed_partner_events WHERE case_id=? AND type='accepted' AND event_id!=?",
                (body.request_id, body.event_id),
            ).fetchone():
                raise HTTPException(409, "only a pending job can be accepted once")
            svc.record_event(conn, body.request_id, "partner.accepted", actor, trace)
        else:
            if isinstance(body, PartnerFailed):
                trace["reason"] = body.data.reason
            svc.transition(conn, body.request_id, EVENT_TARGETS[body.type], actor, trace)

        if isinstance(body, SlotsOffered):
            conn.executemany(
                "INSERT INTO appointment_slots (case_id,slot_id,start,end) VALUES (?,?,?,?)",
                [(body.request_id, slot.slot_id, slot.start.isoformat(), slot.end.isoformat())
                 for slot in body.data.slots])
    return {"event_id": body.event_id, "duplicate": False}
