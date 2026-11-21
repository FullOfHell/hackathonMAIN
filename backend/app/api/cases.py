"""centrix stand-in API (plan §5)."""
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.db import get_db, now_iso
from app.integrations.connector import DispatchUnconfirmed, book_slot, build_job_request, dispatch_job, get_partner_client
from app.partners.registry import sharing_policy
from app.schemas import (
    CaseCreate, DocumentKind, PartnerJobRequest, ResidentAction, ResidentProfile, ResidentProfilePatch,
    ResidentSlotChoice, SharingApprovalIn,
)
from app.services import cases as svc
from app.services import outages
from app.states import CaseStatus, check_transition

router = APIRouter(prefix="/api", tags=["centrix"])


def _case_or_404(conn, case_id):
    case = svc.get_case(conn, case_id)
    if not case:
        raise HTTPException(404, "case not found")
    return case


UNAPPROVED_REPAIR_STATES = {CaseStatus.AWAITING_SHARING_APPROVAL, CaseStatus.NO_PROVIDER_AVAILABLE}


def _current_contractor(conn, case):
    """Re-evaluate the address and contractor ranking before sharing."""
    ctx = svc.unit_context(conn, case["unit_id"])
    resident = next((r for r in ctx["residents"] if r["id"] == case["resident_id"]), None)
    if not resident:
        return None
    region = svc.repair_region(conn, ctx, resident)
    partner = svc.select_partner(conn, case["issue_type"], region, resident.get("address") or ctx["property"]["address"])
    return partner["id"] if partner else None


def _with_sharing_request(conn, case):
    if case["status"] in UNAPPROVED_REPAIR_STATES and not case["sharing_approval"]:
        partner_id = _current_contractor(conn, case)
        case["status"] = (CaseStatus.AWAITING_SHARING_APPROVAL if partner_id else CaseStatus.NO_PROVIDER_AVAILABLE)
        if partner_id != case["partner_id"]:
            case["partner_id"] = partner_id
            case["building_repair"] = None
        if partner_id:
            partner = conn.execute("SELECT id, name FROM partners WHERE id=?", (partner_id,)).fetchone()
            case["sharing_request"] = {"partner": dict(partner), **sharing_policy(conn, partner_id)}
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


@router.patch("/units/{unit_id}/residents/{resident_id}/profile", response_model=ResidentProfile,
              response_model_exclude_unset=True)
def update_resident_profile(unit_id: str, resident_id: str, body: ResidentProfilePatch, conn=Depends(get_db)):
    changes = {field: value for field, value in body.items() if field != "acting_resident_id"}
    if not changes:
        raise HTTPException(422, "supply at least one profile field")
    if body["acting_resident_id"] != resident_id:
        raise HTTPException(403, "only the resident can edit their profile")

    # Column names come from the closed request schema. Bind every value and update only supplied fields.
    assignments = ", ".join(f"{field}=?" for field in changes)
    with conn:
        resident = conn.execute(
            f"UPDATE residents SET {assignments} WHERE unit_id=? AND id=? RETURNING *",
            (*changes.values(), unit_id, resident_id),
        ).fetchone()
        if resident is None:
            raise HTTPException(404, "resident not found for this unit")
        return svc.resident_profile(resident)


@router.get("/units/{unit_id}/cases")
def get_unit_cases(unit_id: str, conn=Depends(get_db)):
    conn.execute("BEGIN")
    return [_with_sharing_request(conn, svc.get_case(conn, r["id"])) for r in
            conn.execute("SELECT id FROM cases WHERE unit_id=? ORDER BY created_at DESC", (unit_id,))]


@router.get("/manager/repairs")
def list_manager_repairs(conn=Depends(get_db)):
    conn.execute("BEGIN")
    contractors = dict(conn.execute("SELECT id,name FROM partners"))
    rows = conn.execute(
        "SELECT c.id,u.unit_label,p.address,r.address AS resident_address,r.unit AS resident_unit,"
        "json_extract(o.payload,'$.property.address') AS approved_address,"
        "json_extract(o.payload,'$.property.unit') AS approved_unit "
        "FROM cases c JOIN units u ON u.id=c.unit_id JOIN properties p ON p.id=u.property_id "
        "JOIN residents r ON r.id=c.resident_id LEFT JOIN partner_orders o ON o.case_id=c.id "
        "ORDER BY c.created_at DESC,c.rowid DESC")
    groups = {}
    for row in rows:
        case = _with_sharing_request(conn, svc.get_case(conn, row["id"]))
        pending = case["status"] in UNAPPROVED_REPAIR_STATES and not case["sharing_approval"]
        address = row["approved_address"] or (row["resident_address"] if pending else None) or row["address"]
        unit = row["approved_unit"] or (row["resident_unit"] if pending else None) or row["unit_label"]
        groups.setdefault(case["partner_id"], []).append({"case": case, "address": address, "unit": unit})

    return [
        {"contractor": {"id": partner_id, "name": contractors[partner_id]} if partner_id else None, "repairs": repairs}
        for partner_id, repairs in sorted(groups.items(), key=lambda group: (group[0] is None,
                                             contractors.get(group[0], "").casefold()))
    ]


@router.post("/cases", status_code=201)
def create_case(body: CaseCreate, conn=Depends(get_db), partner_client=Depends(get_partner_client)):
    conn.execute("BEGIN IMMEDIATE")
    ctx = svc.unit_context(conn, body.unit_id)
    if not ctx:
        raise HTTPException(404, "unit not found")
    resident = next((r for r in ctx["residents"] if r["id"] == body.resident_id), None)
    if resident is None:
        raise HTTPException(422, "resident does not belong to unit")
    case_id, ts = svc.new_case_id(), now_iso()
    conn.execute("INSERT INTO cases (id,unit_id,resident_id,issue_type,description,symptoms,urgency,status,"
                 "partner_id,partner_job_id,source_channel,created_at,updated_at,availability_preferences) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (case_id, body.unit_id, body.resident_id, body.issue_type, body.description, json.dumps(body.symptoms),
                  body.urgency, CaseStatus.REPORTED.value, None, None, body.source_channel, ts, ts,
                  json.dumps(body.availability_preferences)))
    svc.record_event(conn, case_id, "maintenance.case_created", f"resident:{body.resident_id}",
                     {"channel": body.source_channel, "issue_type": body.issue_type, "unit_id": body.unit_id})
    svc.transition(conn, case_id, CaseStatus.TRIAGED, "system")
    region = svc.repair_region(conn, ctx, resident)
    partner = svc.select_partner(conn, body.issue_type, region, resident.get("address") or ctx["property"]["address"])
    if partner:
        conn.execute("UPDATE cases SET partner_id=? WHERE id=?", (partner["id"], case_id))
        svc.transition(conn, case_id, CaseStatus.AWAITING_SHARING_APPROVAL, "system",
                       {"partner_id": partner["id"], "reason": "contractor matching for service and region"})
        if svc.normalize_location(region) == svc.normalize_location(ctx["property"]["region"]):
            outages.detect(conn, body, ctx["property"]["id"], partner["id"], ts)
    else:
        svc.transition(conn, case_id, CaseStatus.NO_PROVIDER_AVAILABLE, "system",
                       {"reason": "no active partner covers this service and region"})
    conn.commit()
    outages.confirm_scope(conn, case_id, partner_client)
    return _with_sharing_request(conn, svc.get_case(conn, case_id))


@router.get("/cases/{case_id}")
def get_case(case_id: str, conn=Depends(get_db)):
    conn.execute("BEGIN")
    return _with_sharing_request(conn, _case_or_404(conn, case_id))


@router.get("/cases/{case_id}/events")
def get_events(case_id: str, conn=Depends(get_db)):
    _case_or_404(conn, case_id)
    return svc.list_events(conn, case_id)


@router.get("/cases/{case_id}/documents/{kind}")
def download_document(case_id: str, kind: DocumentKind, conn=Depends(get_db)):
    document = svc.case_documents(conn, case_id).get(kind)
    if document is None:
        raise HTTPException(404, "document not found for this case")
    return JSONResponse(document, headers={"Content-Disposition": f'attachment; filename="{document["filename"]}"'})


@router.post("/cases/{case_id}/escalate")
def escalate(case_id: str, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        case = _case_or_404(conn, case_id)
        if case["status"] == CaseStatus.NEEDS_HUMAN_REVIEW:
            return case
        if case["status"] not in (CaseStatus.NO_PROVIDER_AVAILABLE, CaseStatus.DECLINED, CaseStatus.FAILED):
            raise HTTPException(409, "only a failed, declined or unavailable repair can be escalated")
        svc.transition(conn, case_id, CaseStatus.NEEDS_HUMAN_REVIEW, "manager",
                       {"reason": case["status"], "job_id": case["partner_job_id"]})
        return svc.get_case(conn, case_id)


@router.post("/cases/{case_id}/cancel")
def cancel_before_handoff(case_id: str, body: ResidentAction, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        case = _case_or_404(conn, case_id)
        if body.resident_id != case["resident_id"]:
            raise HTTPException(403, "only the reporting resident can withdraw the request")
        if case["status"] == CaseStatus.CANCELLED:
            return case
        if case["status"] not in (CaseStatus.AWAITING_SHARING_APPROVAL, CaseStatus.LINKED_TO_BUILDING_REPAIR):
            raise HTTPException(409, "only an unshared report can be withdrawn")
        outages.withdraw(conn, case_id, case["building_repair"])
        svc.transition(conn, case_id, CaseStatus.CANCELLED, f"resident:{body.resident_id}")
        return svc.get_case(conn, case_id)


@router.post("/cases/{case_id}/sharing-approval")
def approve_sharing(case_id: str, body: SharingApprovalIn, conn=Depends(get_db),
                    partner_client=Depends(get_partner_client)):
    # Serialize approval writes, then release the lock before external calls.
    conn.execute("BEGIN IMMEDIATE")
    case = _case_or_404(conn, case_id)
    if body.approved_by != case["resident_id"]:
        raise HTTPException(403, "only the reporting resident can approve sharing")
    fields = sorted(set(body.approved_fields))
    if case["sharing_approval"] and fields != sorted(set(case["sharing_approval"]["shared_fields"])):
        raise HTTPException(409, "sharing approval already records a different set of fields")

    if body.expected_partner_id is not None and case["sharing_approval"] and case["partner_id"] != body.expected_partner_id:
        raise HTTPException(409, "The saved approval already names a different contractor.")

    # Idempotent: a repeated approval after the job was requested returns the existing state.
    if case["sharing_approval"] and case["partner_job_id"]:
        conn.commit()
        outages.confirm_scope(conn, case_id, partner_client)
        return svc.get_case(conn, case_id)
    if case["sharing_approval"] and case["status"] != CaseStatus.PARTNER_REQUESTED:
        raise HTTPException(409, "case is no longer awaiting partner dispatch")

    if not case["sharing_approval"]:
        if case["status"] == CaseStatus.LINKED_TO_BUILDING_REPAIR:
            raise HTTPException(409, "this report follows a building repair; no additional sharing is needed")
        if case["status"] in UNAPPROVED_REPAIR_STATES:
            partner_id = _current_contractor(conn, case)
            if not partner_id:
                raise HTTPException(409, "No contractors available for this service and repair address.")
            previewed_partner = case["partner_id"] if body.expected_partner_id is None else body.expected_partner_id
            if previewed_partner != partner_id:
                raise HTTPException(409, "The contractor changed. Review the sharing details again.")
            if partner_id != case["partner_id"]:
                outages.withdraw(conn, case_id, case["building_repair"])
                conn.execute("UPDATE cases SET partner_id=? WHERE id=?", (partner_id, case_id))
                svc.record_event(conn, case_id, "partner.routing_updated", "system",
                                 {"previous_partner_id": case["partner_id"], "partner_id": partner_id})
                case = svc.get_case(conn, case_id)
            if case["status"] == CaseStatus.NO_PROVIDER_AVAILABLE:
                svc.transition(conn, case_id, CaseStatus.AWAITING_SHARING_APPROVAL, "system",
                               {"partner_id": partner_id})
        policy = sharing_policy(conn, case["partner_id"])
        unknown = set(fields) - set(policy["shareable_fields"])
        missing = set(policy["required_fields"]) - set(fields)
        if unknown or missing:
            raise HTTPException(422, {"unknown_fields": sorted(unknown), "missing_required_fields": sorted(missing)})
        svc.transition(conn, case_id, CaseStatus.PARTNER_REQUESTED, f"resident:{body.approved_by}",
                       {"partner_id": case["partner_id"]})
        outages.claim_dispatch(conn, case_id, case["building_repair"])
        conn.execute("INSERT INTO sharing_approvals (case_id,partner_id,shared_fields,channel,approved_by,recorded_at) "
                     "VALUES (?,?,?,?,?,?)", (case_id, case["partner_id"], json.dumps(fields),
                                               body.channel, body.approved_by, now_iso()))
        svc.record_event(conn, case_id, "sharing.approved", f"resident:{body.approved_by}",
                         {"fields": fields, "channel": body.channel})
    partner = dict(conn.execute("SELECT * FROM partners WHERE id=?", (case["partner_id"],)).fetchone())
    order = conn.execute("SELECT payload FROM partner_orders WHERE case_id=?", (case_id,)).fetchone()
    if order:
        job = PartnerJobRequest.model_validate_json(order["payload"])
    else:
        case = svc.get_case(conn, case_id)
        ctx = svc.unit_context(conn, case["unit_id"])
        resident = next((r for r in ctx["residents"] if r["id"] == case["resident_id"]), None)
        if resident is None:
            raise HTTPException(409, "the reporting resident no longer belongs to this unit")
        job = build_job_request(case, ctx, resident, case["sharing_approval"])
        conn.execute("INSERT INTO partner_orders (case_id,payload) VALUES (?,?)", (case_id, job.model_dump_json()))
    conn.commit()

    try:
        result = dispatch_job(partner_client, partner, job)
    except DispatchUnconfirmed as e:
        # A lost acknowledgment can follow a successful remote write.
        conn.execute("BEGIN IMMEDIATE")
        current = _case_or_404(conn, case_id)
        if current["partner_job_id"]:
            return current
        svc.record_event(conn, case_id, "partner.job_request_failed", "system", {"error": str(e)})
        conn.commit()
        raise HTTPException(502, f"{e}. Retry the same sharing approval.") from e
    except (httpx.HTTPError, httpx.InvalidURL) as e:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            current = _case_or_404(conn, case_id)
            if current["partner_job_id"]:
                return current
            if current["status"] == CaseStatus.PARTNER_REQUESTED:
                svc.record_event(conn, case_id, "partner.job_request_failed", "system", {"error": type(e).__name__})
                svc.transition(conn, case_id, CaseStatus.NEEDS_HUMAN_REVIEW, "system",
                               {"reason": "partner request failed"})
        raise HTTPException(502, "partner job request failed; case escalated for human review")
    linked = conn.execute("UPDATE cases SET partner_job_id=?, updated_at=? WHERE id=? AND partner_job_id IS NULL",
                          (result["job_id"], now_iso(), case_id))
    if linked.rowcount:
        svc.record_event(conn, case_id, "partner.job_requested", "system",
                         {"partner_id": partner["id"], "job_id": result["job_id"],
                          "duplicate": result.get("duplicate", False), "idempotency_key": job.idempotency_key})
        if job.issue.get("repair_scope") == "building_heating":
            outages.mark_scope_confirmed(conn, case["building_repair"]["outage_id"], case_id, result["job_id"])
    conn.commit()
    outages.confirm_scope(conn, case_id, partner_client)
    return svc.get_case(conn, case_id)


@router.post("/cases/{case_id}/sync-building-repair")
def sync_building_repair(case_id: str, conn=Depends(get_db), partner_client=Depends(get_partner_client)):
    building = _case_or_404(conn, case_id)["building_repair"]
    if not building or not building["partner_job_id"]:
        raise HTTPException(409, "a confirmed job is required to update the building repair")
    if not outages.confirm_scope(conn, case_id, partner_client):
        raise HTTPException(502, "partner has not confirmed the building scope; retry this action")
    return svc.get_case(conn, case_id)


@router.post("/cases/{case_id}/approve-invoice")
def approve_invoice(case_id: str, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        case = _case_or_404(conn, case_id)
        if case["status"] == CaseStatus.CLOSED and conn.execute(
            "SELECT 1 FROM case_events WHERE case_id=? AND type='invoice.manager_approved'", (case_id,)
        ).fetchone():
            return case
        if case["status"] != CaseStatus.AWAITING_INVOICE_APPROVAL:
            raise HTTPException(409, "no invoice is awaiting manager approval")
        invoice = case["invoice"]
        svc.record_event(conn, case_id, "invoice.manager_approved", "manager",
                         {"invoice_number": invoice["invoice_number"], "amount_cents": invoice["amount_cents"]})
        svc.transition(conn, case_id, CaseStatus.CLOSED, "manager")
        return svc.get_case(conn, case_id)


def _already_booked(case: dict, slot_id: str) -> bool:
    if case["appointment"] is None:
        return False
    if case["appointment"]["slot_id"] != slot_id:
        raise HTTPException(409, "a different slot is already booked")
    return True


@router.post("/cases/{case_id}/select-slot")
def select_slot(case_id: str, body: ResidentSlotChoice, conn=Depends(get_db),
                partner_client=Depends(get_partner_client)):
    with conn:
        conn.execute("BEGIN")
        case = _case_or_404(conn, case_id)
    if body.resident_id != case["resident_id"]:
        raise HTTPException(403, "only the reporting resident can select a slot")
    if not any(slot["slot_id"] == body.slot_id for slot in case["slots"]):
        raise HTTPException(422, "slot was not offered for this case")
    if _already_booked(case, body.slot_id):
        return case

    check_transition(CaseStatus(case["status"]), CaseStatus.SCHEDULED)
    partner = conn.execute("SELECT base_url FROM partners WHERE id=?", (case["partner_id"],)).fetchone()
    # The partner owns the booking and can safely repeat its confirmation after a timeout.
    try:
        book_slot(partner_client, partner["base_url"], case["partner_job_id"], body.slot_id)
    except (httpx.HTTPError, ValueError) as exc:
        partner_status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        with conn:
            svc.record_event(conn, case_id, "partner.booking_unconfirmed", f"resident:{body.resident_id}",
                             {"job_id": case["partner_job_id"], "slot_id": body.slot_id, "partner_status": partner_status})
        if partner_status in (409, 422):
            raise HTTPException(partner_status, "partner declined this slot") from exc
        raise HTTPException(502, "partner did not confirm the booking") from exc

    with conn:
        conn.execute("BEGIN IMMEDIATE")
        case = _case_or_404(conn, case_id)
        if _already_booked(case, body.slot_id):
            return case
        svc.transition(conn, case_id, CaseStatus.SCHEDULED, f"resident:{body.resident_id}",
                       {"job_id": case["partner_job_id"], "slot_id": body.slot_id})
        conn.execute("INSERT INTO appointments (case_id,slot_id,booked_at) VALUES (?,?,?)",
                     (case_id, body.slot_id, now_iso()))
        return svc.get_case(conn, case_id)
