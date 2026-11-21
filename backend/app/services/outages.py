"""Link independent reports of lost heating while preserving one consented partner order."""
import json
import re
import uuid

import httpx

from app.services.cases import normalize_location, record_event, transition
from app.states import CaseStatus as S


def reports_no_heat(symptoms, description):
    # Recognize the portal's "No heat at all" shortcut and an explicit typed report.
    # Partial, uncertain and unrelated symptoms can still be handled as individual repairs.
    return "no_heat" in symptoms or bool(re.match(
        r"^\s*(?:(?:(?:I|we) have |there is )?no heat(?:ing)?|(?:the |my )?heating "
        r"(?:is out|is off|is not working|isn't working|doesn't work|does not work))"
        r"(?:\s+at all)?(?:\s+(?:in|throughout) (?:the |my |our )?(?:flat|apartment|unit)\b(?: [\w-]+)?)?"
        r"(?:\s+(?:since|for)\s+[^.\n]+)?\s*(?:[.,!\n]|$)",
        description, re.IGNORECASE))


def link_followers(conn, outage_id, dispatch_case_id):
    for case in conn.execute(
        "SELECT c.id FROM cases c JOIN outage_cases m ON m.case_id=c.id "
        "WHERE m.outage_id=? AND c.id!=? AND c.status=?",
        (outage_id, dispatch_case_id, S.AWAITING_SHARING_APPROVAL)).fetchall():
        transition(conn, case["id"], S.LINKED_TO_BUILDING_REPAIR, "system", {"outage_id": outage_id})


def detect(conn, body, property_id, partner_id, timestamp):
    if body.issue_type != "heating_repair" or not reports_no_heat(body.symptoms, body.description):
        return
    rows = conn.execute(
        "SELECT c.id,c.unit_id,c.symptoms,c.description,c.status,m.outage_id,o.dispatch_case_id,p.address, "
        "COALESCE(json_extract(ord.payload,'$.property.address'),r.address,p.address) AS repair_address "
        "FROM cases c JOIN units u ON u.id=c.unit_id JOIN properties p ON p.id=u.property_id "
        "JOIN residents r ON r.id=c.resident_id LEFT JOIN partner_orders ord ON ord.case_id=c.id "
        "LEFT JOIN outage_cases m ON m.case_id=c.id "
        "LEFT JOIN building_outages o ON o.id=m.outage_id LEFT JOIN cases lead ON lead.id=o.dispatch_case_id "
        "WHERE u.property_id=? AND c.issue_type='heating_repair' AND c.partner_id=? "
        "AND julianday(c.created_at) BETWEEN julianday(?)-1 AND julianday(?) "
        "AND c.status IN (?,?,?,?,?,?) AND (lead.id IS NULL OR lead.status IN (?,?,?,?)) "
        "ORDER BY c.created_at,c.rowid",
        (property_id, partner_id, timestamp, timestamp, S.AWAITING_SHARING_APPROVAL, S.PARTNER_REQUESTED,
         S.SLOTS_OFFERED, S.SCHEDULED, S.IN_PROGRESS, S.LINKED_TO_BUILDING_REPAIR,
         S.PARTNER_REQUESTED, S.SLOTS_OFFERED, S.SCHEDULED, S.IN_PROGRESS)).fetchall()
    matches = [r for r in rows if normalize_location(r["repair_address"]) == normalize_location(r["address"])
               and reports_no_heat(json.loads(r["symptoms"]), r["description"])]
    if not any(r["unit_id"] != body.unit_id for r in matches):
        return
    existing = next((r for r in matches if r["outage_id"]), None)
    if existing:
        outage_id, dispatch_case = existing["outage_id"], existing["dispatch_case_id"]
    else:
        outage_id = f"outage_{uuid.uuid4().hex}"
        # An approved order may already be in flight, even before its job ID is known.
        dispatch_case = next((r["id"] for r in matches if r["status"] != S.AWAITING_SHARING_APPROVAL), None)
        conn.execute("INSERT INTO building_outages (id,dispatch_case_id) VALUES (?,?)", (outage_id, dispatch_case))
    for row in matches:
        if row["outage_id"] or (row["status"] != S.AWAITING_SHARING_APPROVAL and row["id"] != dispatch_case):
            continue
        conn.execute("INSERT INTO outage_cases VALUES (?,?)", (row["id"], outage_id))
        record_event(conn, row["id"], "building.outage_detected", "system", {"outage_id": outage_id})
    if dispatch_case:
        link_followers(conn, outage_id, dispatch_case)


def claim_dispatch(conn, case_id, building):
    if building:
        outage_id = building["outage_id"]
        conn.execute("UPDATE building_outages SET dispatch_case_id=? WHERE id=? AND dispatch_case_id IS NULL",
                     (case_id, outage_id))
        link_followers(conn, outage_id, case_id)


def withdraw(conn, case_id, building):
    if building is None:
        return
    outage_id = building["outage_id"]
    conn.execute("DELETE FROM outage_cases WHERE case_id=?", (case_id,))
    members = conn.execute("SELECT c.id,c.unit_id FROM cases c JOIN outage_cases m ON m.case_id=c.id "
                           "WHERE m.outage_id=?", (outage_id,)).fetchall()
    if building["repair_status"] is None and len({r["unit_id"] for r in members}) < 2:
        for row in members:
            record_event(conn, row["id"], "building.outage_withdrawn", "system", {"outage_id": outage_id})
        conn.execute("DELETE FROM outage_cases WHERE outage_id=?", (outage_id,))
        conn.execute("DELETE FROM building_outages WHERE id=?", (outage_id,))


def mark_scope_confirmed(conn, outage_id, request_id, job_id):
    updated = conn.execute("UPDATE building_outages SET scope_confirmed=1 WHERE id=? AND scope_confirmed=0",
                           (outage_id,))
    if updated.rowcount:
        record_event(conn, request_id, "building.partner_scope_confirmed", "system",
                     {"outage_id": outage_id, "job_id": job_id})


def confirm_scope(conn, case_id, client):
    """An idempotent scope update also upgrades a single-unit order already at the partner."""
    row = conn.execute(
        "SELECT o.id,c.id AS request_id,c.partner_job_id,p.base_url FROM outage_cases m "
        "JOIN building_outages o ON o.id=m.outage_id JOIN cases c ON c.id=o.dispatch_case_id "
        "JOIN partners p ON p.id=c.partner_id WHERE m.case_id=? AND o.scope_confirmed=0 "
        "AND c.partner_job_id IS NOT NULL", (case_id,)).fetchone()
    if not row:
        return True
    job_id = row["partner_job_id"]
    body = {"request_id": row["request_id"], "scope": "building_heating"}
    try:
        response = client.put(f"{row['base_url']}/connector/jobs/{job_id}/scope", json=body)
        response.raise_for_status()
        if response.json() != {"job_id": job_id, **body}:
            raise ValueError("scope acknowledgment did not match the requested job")
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        with conn:
            record_event(conn, row["request_id"], "building.partner_scope_unconfirmed", "system",
                         {"outage_id": row["id"], "job_id": job_id})
        return False
    with conn:
        mark_scope_confirmed(conn, row["id"], row["request_id"], job_id)
    return True
