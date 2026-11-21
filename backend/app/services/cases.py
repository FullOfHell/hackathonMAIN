"""Case domain logic: creation, validated transitions, event timeline, partner routing."""
import json
import re
import sqlite3
import uuid
from hashlib import sha256
from unicodedata import combining, normalize

from app.db import RESIDENT_HOME_FIELDS, now_iso
from app.services import notifications, scheduling
from app.states import CaseStatus, check_transition


def record_event(conn: sqlite3.Connection, case_id: str, type_: str, actor: str, payload: dict | None = None) -> None:
    cursor = conn.execute("INSERT INTO case_events (case_id,type,actor,timestamp,payload) VALUES (?,?,?,?,?)",
                          (case_id, type_, actor, now_iso(), json.dumps(payload or {}, ensure_ascii=False)))
    # Same transaction: a rolled-back event never leaves a notification behind.
    notifications.on_event(conn, case_id, cursor.lastrowid, type_, payload or {})


def transition(conn: sqlite3.Connection, case_id: str, target: CaseStatus, actor: str, payload: dict | None = None) -> None:
    row = conn.execute("SELECT status FROM cases WHERE id=?", (case_id,)).fetchone()
    current = CaseStatus(row["status"])
    check_transition(current, target)
    conn.execute("UPDATE cases SET status=?, updated_at=? WHERE id=?", (target.value, now_iso(), case_id))
    record_event(conn, case_id, "case.status_changed", actor, {"from": current.value, "to": target.value, **(payload or {})})
    # Residents following a building job receive its public progress on their own timeline.
    followers = conn.execute(
        "SELECT m.case_id,o.id,o.scope_confirmed FROM building_outages o JOIN outage_cases m ON m.outage_id=o.id "
        "JOIN cases c ON c.id=m.case_id WHERE o.dispatch_case_id=? AND c.status=?",
        (case_id, CaseStatus.LINKED_TO_BUILDING_REPAIR)).fetchall()
    for member in followers:
        notice = {"outage_id": member["id"], "repair_status": target.value, "scope_confirmed": bool(member["scope_confirmed"])}
        record_event(conn, member["case_id"], "building.repair_updated", "system", notice)
        if target in (CaseStatus.COMPLETED, CaseStatus.CLOSED) and not member["scope_confirmed"]:
            transition(conn, member["case_id"], CaseStatus.NEEDS_HUMAN_REVIEW, "system",
                       {**notice, "reason": "building scope unconfirmed at repair completion"})
        elif target == CaseStatus.CLOSED:
            transition(conn, member["case_id"], CaseStatus.CLOSED, "system", notice)
        elif target in (CaseStatus.DECLINED, CaseStatus.FAILED, CaseStatus.NEEDS_HUMAN_REVIEW):
            transition(conn, member["case_id"], CaseStatus.NEEDS_HUMAN_REVIEW, "system", notice)


def resident_profile(row: sqlite3.Row) -> dict:
    profile = dict(row)
    for field in RESIDENT_HOME_FIELDS:
        if profile.get(field) is None:
            profile.pop(field, None)
    return profile


def unit_context(conn: sqlite3.Connection, unit_id: str) -> dict | None:
    u = conn.execute(
        "SELECT u.*, p.address, p.building_year, p.heating_type, p.region, p.access_details "
        "FROM units u JOIN properties p ON p.id=u.property_id WHERE u.id=?", (unit_id,)).fetchone()
    if not u:
        return None
    residents = [resident_profile(r) for r in conn.execute("SELECT * FROM residents WHERE unit_id=?", (unit_id,))]
    prior = [dict(c) for c in conn.execute(
        "SELECT id, issue_type, description, status, created_at FROM cases WHERE unit_id=? AND issue_type='heating_repair' "
        "ORDER BY created_at DESC", (unit_id,))]
    return {
        "unit_id": u["id"],
        "property": {"id": u["property_id"], "address": u["address"], "building_year": u["building_year"],
                     "heating": u["heating_type"], "region": u["region"], "access_details": u["access_details"]},
        "unit": {"label": u["unit_label"], "floor": u["floor"], "size_sqm": u["size_sqm"]},
        "residents": residents,
        "prior_heating_cases": prior,
    }


def normalize_location(value: str) -> str:
    text = "".join(character for character in normalize("NFKD", value.casefold()) if not combining(character))
    return " ".join(re.findall(r"[^\W_]+", text))


def service_area(region: str) -> tuple[str, str]:
    city, _, country = region.partition(",")
    country = normalize_location(country)
    return normalize_location(city), "de" if country in {"", "de", "germany", "deutschland"} else country


def at_property_address(ctx: dict, resident: dict) -> bool:
    address = resident.get("address")
    return not address or normalize_location(address) == normalize_location(ctx["property"]["address"])


def repair_region(ctx: dict, resident: dict) -> tuple[str, str] | None:
    property_ = ctx["property"]
    address = resident.get("address")
    if at_property_address(ctx, resident):
        return service_area(property_["region"])
    # Demo address format: street, postal code and city, optional country.
    address = re.sub(r"[,\s]+(?:germany|deutschland|de)\s*$", "", address, flags=re.IGNORECASE)
    parts = [part.strip() for part in address.rsplit(",", 2)]
    if len(parts) == 1:
        match = re.search(r"\b\d+\w*\s+([^\d,]+)$", address)
        if match:
            locality = match[1]
        elif all(word.isalpha() for word in normalize_location(address).split()):
            locality = address
        else:
            return None
        country = ""
    elif len(parts) == 2 and (match := re.search(r"\b\d{4,6}\s+([^\d,]+)$", parts[0])):
        locality, country = match[1], parts[1]
    else:
        locality = parts[1]
        country = parts[2] if len(parts) == 3 else ""
    locality = re.sub(r"\b\d{4,6}\b", "", locality).strip()
    return service_area(f"{locality},{country}") if locality else None


def select_partner(conn: sqlite3.Connection, case: dict, region: tuple[str, str] | None) -> dict | None:
    """Try available local contractors before a stable, per-case random order elsewhere."""
    if region is None:
        return None
    local, elsewhere = [], []
    for row in conn.execute(
        "SELECT p.id,p.name,p.regions FROM partners p JOIN partner_capabilities k ON k.partner_id=p.id "
        "WHERE p.active=1 AND json_extract(k.manifest,'$.kind')='delivery' "
        "AND 'maintenance.case_created' IN (SELECT value FROM json_each(k.manifest,'$.triggers')) "
        "AND ? IN (SELECT value FROM json_each(p.service_types)) ORDER BY p.name,p.id", (case["issue_type"],)
    ):
        areas = [service_area(area) for area in json.loads(row["regions"])]
        if region in areas:
            local.append(dict(row))
        elif case["issue_type"] == "heating_repair" and any(country == region[1] for _, country in areas):
            elsewhere.append(dict(row))
    elsewhere.sort(key=lambda partner: sha256(f"{case['id']}:{partner['id']}".encode()).digest())
    if not local and not elsewhere:
        return None

    slots = scheduling.repair_windows(conn, case["resident_id"])
    for partner in local + elsewhere:
        if scheduling.unreserved_slots(conn, partner["id"], slots):
            return partner
    return None


def new_case_id() -> str:
    return f"case_{uuid.uuid4().hex[:8]}"


def case_documents(conn: sqlite3.Connection, case_id: str) -> dict:
    rows = conn.execute(
        "SELECT d.kind,d.content,c.unit_id,e.occurred_at FROM case_documents d "
        "JOIN cases c ON c.id=d.case_id JOIN processed_partner_events e ON e.event_id=d.event_id "
        "WHERE d.case_id=?", (case_id,))
    return {row["kind"]: {
        **json.loads(row["content"]), "kind": row["kind"], "case_id": case_id, "unit_id": row["unit_id"],
        "created_at": row["occurred_at"], "filename": f"{row['kind']}.json",
        "url": f"/api/cases/{case_id}/documents/{row['kind']}",
    } for row in rows}


def get_case(conn: sqlite3.Connection, case_id: str) -> dict | None:
    row = conn.execute(
        "SELECT c.*,p.name AS contractor_name FROM cases c LEFT JOIN partners p ON p.id=c.partner_id WHERE c.id=?",
        (case_id,)).fetchone()
    if not row:
        return None
    case = dict(row)
    case["symptoms"] = json.loads(case["symptoms"])
    case["availability_preferences"] = json.loads(case["availability_preferences"])
    case["slots"] = [dict(slot) for slot in conn.execute(
        "SELECT slot_id,start,end FROM appointment_slots WHERE case_id=? ORDER BY julianday(start),slot_id",
        (case_id,))]
    appointment = conn.execute(
        "SELECT a.case_id,a.slot_id,s.start,s.end,a.booked_at FROM appointments a "
        "JOIN appointment_slots s USING (case_id,slot_id) WHERE a.case_id=?", (case_id,)).fetchone()
    case["appointment"] = dict(appointment) if appointment else None
    building = conn.execute(
        "SELECT o.id AS outage_id, o.dispatch_case_id, o.scope_confirmed, lead.status AS repair_status, "
        "lead.partner_job_id, s.start, s.end FROM outage_cases m JOIN building_outages o ON o.id=m.outage_id "
        "LEFT JOIN cases lead ON lead.id=o.dispatch_case_id LEFT JOIN appointments a ON a.case_id=lead.id "
        "LEFT JOIN appointment_slots s ON s.case_id=a.case_id AND s.slot_id=a.slot_id WHERE m.case_id=?",
        (case_id,)).fetchone()
    case["building_repair"] = None if building is None else {
        "outage_id": building["outage_id"], "is_dispatch_case": building["dispatch_case_id"] == case_id,
        "repair_status": building["repair_status"], "partner_job_id": building["partner_job_id"],
        "scope_confirmed": bool(building["scope_confirmed"]),
        "appointment": {"start": building["start"], "end": building["end"]} if building["start"] else None,
    }
    documents = case_documents(conn, case_id)
    case["completion_report"] = documents.get("completion_report")
    case["invoice"] = documents.get("invoice")
    appr = conn.execute("SELECT * FROM sharing_approvals WHERE case_id=?", (case_id,)).fetchone()
    case["sharing_approval"] = ({**dict(appr), "shared_fields": json.loads(appr["shared_fields"])} if appr else None)
    return case


def list_events(conn: sqlite3.Connection, case_id: str) -> list[dict]:
    return [{**dict(e), "payload": json.loads(e["payload"])}
            for e in conn.execute("SELECT * FROM case_events WHERE case_id=? ORDER BY id", (case_id,))]
