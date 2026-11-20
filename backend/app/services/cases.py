"""Case domain logic: creation, validated transitions, event timeline, partner routing."""
import json
import sqlite3
import uuid

from app.db import now_iso
from app.states import CaseStatus, check_transition


def record_event(conn: sqlite3.Connection, case_id: str, type_: str, actor: str, payload: dict | None = None) -> None:
    conn.execute("INSERT INTO case_events (case_id,type,actor,timestamp,payload) VALUES (?,?,?,?,?)",
                 (case_id, type_, actor, now_iso(), json.dumps(payload or {}, ensure_ascii=False)))


def transition(conn: sqlite3.Connection, case_id: str, target: CaseStatus, actor: str, payload: dict | None = None) -> None:
    row = conn.execute("SELECT status FROM cases WHERE id=?", (case_id,)).fetchone()
    current = CaseStatus(row["status"])
    check_transition(current, target)
    conn.execute("UPDATE cases SET status=?, updated_at=? WHERE id=?", (target.value, now_iso(), case_id))
    record_event(conn, case_id, "case.status_changed", actor, {"from": current.value, "to": target.value, **(payload or {})})


def unit_context(conn: sqlite3.Connection, unit_id: str) -> dict | None:
    u = conn.execute(
        "SELECT u.*, p.address, p.building_year, p.heating_type, p.region, p.access_details "
        "FROM units u JOIN properties p ON p.id=u.property_id WHERE u.id=?", (unit_id,)).fetchone()
    if not u:
        return None
    residents = [dict(r) for r in conn.execute("SELECT * FROM residents WHERE unit_id=?", (unit_id,))]
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


def select_partner(conn: sqlite3.Connection, service_type: str, region: str) -> dict | None:
    """Deterministic routing (plan §6C): service type -> region -> active; tie-break by name."""
    eligible = []
    for p in conn.execute("SELECT * FROM partners WHERE active=1 ORDER BY name"):
        if service_type in json.loads(p["service_types"]) and region in json.loads(p["regions"]):
            eligible.append(dict(p))
    return eligible[0] if eligible else None


def new_case_id() -> str:
    return f"case_{uuid.uuid4().hex[:8]}"


def get_case(conn: sqlite3.Connection, case_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
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
    appr = conn.execute("SELECT * FROM sharing_approvals WHERE case_id=?", (case_id,)).fetchone()
    case["sharing_approval"] = ({**dict(appr), "shared_fields": json.loads(appr["shared_fields"])} if appr else None)
    return case


def list_events(conn: sqlite3.Connection, case_id: str) -> list[dict]:
    return [{**dict(e), "payload": json.loads(e["payload"])}
            for e in conn.execute("SELECT * FROM case_events WHERE case_id=? ORDER BY id", (case_id,))]
