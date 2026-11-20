"""centrix stand-in API (plan §5)."""
import json

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_db, now_iso
from app.integrations.connector import N8nDispatchError, build_job_request, dispatch_job, get_partner_client
from app.schemas import (DEFAULT_PROPOSED_FIELDS, REQUIRED_SHARED_FIELDS, SHAREABLE_FIELDS, CaseCreate,
                         SharingApprovalIn)
from app.services import cases as svc
from app.states import CaseStatus, InvalidTransition

router = APIRouter(prefix="/api", tags=["centrix"])


def _case_or_404(conn, case_id):
    case = svc.get_case(conn, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return case


def _with_sharing_request(conn, case):
    if case["status"] == CaseStatus.AWAITING_SHARING_APPROVAL.value and case["partner_id"]:
        p = conn.execute("SELECT id, name FROM partners WHERE id=?", (case["partner_id"],)).fetchone()
        case["sharing_request"] = {"partner": dict(p), "proposed_fields": DEFAULT_PROPOSED_FIELDS,
                                   "required_fields": REQUIRED_SHARED_FIELDS, "shareable_fields": SHAREABLE_FIELDS}
    return case


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/units/{unit_id}/context")
def get_unit_context(unit_id: str, conn=Depends(get_db)):
    ctx = svc.unit_context(conn, unit_id)
    if not ctx:
        raise HTTPException(404, "unit not found")
    return ctx


@router.get("/units/{unit_id}/cases")
def get_unit_cases(unit_id: str, conn=Depends(get_db)):
    return [svc.get_case(conn, r["id"]) for r in
            conn.execute("SELECT id FROM cases WHERE unit_id=? ORDER BY created_at DESC", (unit_id,))]


@router.post("/cases", status_code=201)
def create_case(body: CaseCreate, conn=Depends(get_db)):
    ctx = svc.unit_context(conn, body.unit_id)
    if not ctx:
        raise HTTPException(404, "unit not found")
    if body.resident_id not in {r["id"] for r in ctx["residents"]}:
        raise HTTPException(422, "resident does not belong to unit")
    case_id, ts = svc.new_case_id(), now_iso()
    conn.execute("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (case_id, body.unit_id, body.resident_id, body.issue_type, body.description, json.dumps(body.symptoms),
                  body.urgency, CaseStatus.REPORTED.value, None, None, body.source_channel, ts, ts))
    svc.record_event(conn, case_id, "maintenance.case_created", f"resident:{body.resident_id}",
                     {"channel": body.source_channel, "issue_type": body.issue_type, "unit_id": body.unit_id})
    svc.transition(conn, case_id, CaseStatus.TRIAGED, "system")
    partner = svc.select_partner(conn, body.issue_type, ctx["property"]["region"])
    if partner:
        conn.execute("UPDATE cases SET partner_id=? WHERE id=?", (partner["id"], case_id))
        svc.transition(conn, case_id, CaseStatus.AWAITING_SHARING_APPROVAL, "system",
                       {"partner_id": partner["id"], "reason": "service_type + region match"})
    else:
        svc.transition(conn, case_id, CaseStatus.NO_PROVIDER_AVAILABLE, "system")
    conn.commit()
    return _with_sharing_request(conn, svc.get_case(conn, case_id))


@router.get("/cases/{case_id}")
def get_case(case_id: str, conn=Depends(get_db)):
    return _with_sharing_request(conn, _case_or_404(conn, case_id))


@router.get("/cases/{case_id}/events")
def get_events(case_id: str, conn=Depends(get_db)):
    _case_or_404(conn, case_id)
    return svc.list_events(conn, case_id)


@router.post("/cases/{case_id}/sharing-approval")
def approve_sharing(case_id: str, body: SharingApprovalIn, conn=Depends(get_db),
                    partner_client=Depends(get_partner_client)):
    # Serialize approval writes, then release the lock before external calls.
    conn.execute("BEGIN IMMEDIATE")
    case = _case_or_404(conn, case_id)
    if body.approved_by != case["resident_id"]:
        raise HTTPException(403, "only the reporting resident can approve sharing")
    unknown = set(body.approved_fields) - set(SHAREABLE_FIELDS)
    missing = set(REQUIRED_SHARED_FIELDS) - set(body.approved_fields)
    if unknown or missing:
        raise HTTPException(422, {"unknown_fields": sorted(unknown), "missing_required_fields": sorted(missing)})

    # Idempotent: a repeated approval after the job was requested returns the existing state.
    if case["sharing_approval"] and case["partner_job_id"]:
        return _with_sharing_request(conn, case)

    if not case["sharing_approval"]:
        try:
            svc.transition(conn, case_id, CaseStatus.PARTNER_REQUESTED, f"resident:{body.approved_by}",
                           {"partner_id": case["partner_id"]})
        except InvalidTransition as e:
            raise HTTPException(409, str(e))
        conn.execute("INSERT INTO sharing_approvals (case_id,partner_id,shared_fields,channel,approved_by,recorded_at) "
                     "VALUES (?,?,?,?,?,?)", (case_id, case["partner_id"], json.dumps(sorted(body.approved_fields)),
                                               body.channel, body.approved_by, now_iso()))
        svc.record_event(conn, case_id, "sharing.approved", f"resident:{body.approved_by}",
                         {"fields": sorted(body.approved_fields), "channel": body.channel})
    conn.commit()

    case = svc.get_case(conn, case_id)
    ctx = svc.unit_context(conn, case["unit_id"])
    resident = conn.execute("SELECT * FROM residents WHERE id=?", (case["resident_id"],)).fetchone()
    partner = dict(conn.execute("SELECT * FROM partners WHERE id=?", (case["partner_id"],)).fetchone())
    job = build_job_request(case, ctx, dict(resident), case["sharing_approval"])
    try:
        result = dispatch_job(partner_client, partner, job)
    except N8nDispatchError as e:
        # The partner may have stored the job before n8n timed out. Retry with the same key.
        conn.execute("BEGIN IMMEDIATE")
        current = _case_or_404(conn, case_id)
        if current["partner_job_id"]:
            return current
        svc.record_event(conn, case_id, "partner.job_request_failed", "system", {"error": str(e)})
        conn.commit()
        raise HTTPException(502, "n8n dispatch was not confirmed; sharing approval can be retried") from e
    except Exception as e:  # partner unreachable or rejected: explicit failure, never fake success
        svc.record_event(conn, case_id, "partner.job_request_failed", "system", {"error": str(e)[:300]})
        svc.transition(conn, case_id, CaseStatus.NEEDS_HUMAN_REVIEW, "system", {"reason": "partner request failed"})
        conn.commit()
        raise HTTPException(502, "partner job request failed; case escalated for human review")
    linked = conn.execute("UPDATE cases SET partner_job_id=?, updated_at=? WHERE id=? AND partner_job_id IS NULL",
                          (result["job_id"], now_iso(), case_id))
    if linked.rowcount:
        svc.record_event(conn, case_id, "partner.job_requested", "system",
                         {"partner_id": partner["id"], "job_id": result["job_id"],
                          "duplicate": result.get("duplicate", False), "idempotency_key": job.idempotency_key})
    conn.commit()
    return svc.get_case(conn, case_id)
