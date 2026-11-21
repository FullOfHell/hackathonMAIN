"""Tenant availability and bookings for approved simulated contractor jobs."""
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.db import get_db, now_iso
from app.partners.heatfix import DeliveryPartner, get_job
from app.services import cases, scheduling
from app.states import CaseStatus

router = APIRouter(tags=["tenant scheduling"])
Week = Annotated[int, Query(ge=0, lt=scheduling.CALENDAR_WEEKS)]
RESIDENT_CALENDAR = "/api/units/{unit_id}/residents/{resident_id}/availability"
JOB_CALENDAR = "/partners/{slug}/connector/jobs/{job_id}/tenant-availability"


class AvailabilityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acting_resident_id: str
    week_start: date
    available_starts: set[str] = Field(max_length=40)


class VisitChoice(BaseModel):
    start: str = Field(min_length=20, max_length=32)


def _check_resident(conn, unit_id, resident_id, actor):
    if actor != resident_id:
        raise HTTPException(403, "Only the resident can access this timetable.")
    if not conn.execute("SELECT 1 FROM residents WHERE id=? AND unit_id=?", (resident_id, unit_id)).fetchone():
        raise HTTPException(404, "Resident not found for this unit.")


@router.get(RESIDENT_CALENDAR)
def get_availability(unit_id: str, resident_id: str, acting_resident_id: str, week: Week = 0, conn=Depends(get_db)):
    conn.execute("BEGIN")
    _check_resident(conn, unit_id, resident_id, acting_resident_id)
    monday, slots = scheduling.weekly_slots(week)
    return {"week_start": monday, "slots": scheduling.slot_status(conn, resident_id, slots)}


@router.put(RESIDENT_CALENDAR)
def save_availability(unit_id: str, resident_id: str, body: AvailabilityUpdate, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        _check_resident(conn, unit_id, resident_id, body.acting_resident_id)
        try:
            monday, slots = scheduling.weekly_slots(monday=body.week_start)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if body.available_starts - {slot["start"] for slot in slots}:
            raise HTTPException(422, "Choose only working-hour slots from this week.")
        editable = [slot["start"] for slot in scheduling.slot_status(conn, resident_id, slots)
                    if not slot["past"] and not slot["booked"]]
        conn.executemany("DELETE FROM tenant_availability WHERE resident_id=? AND start=?",
                         [(resident_id, start) for start in editable])
        conn.executemany("INSERT INTO tenant_availability VALUES (?,?)",
                         [(resident_id, start) for start in editable if start in body.available_starts])
        return {"week_start": monday, "slots": scheduling.slot_status(conn, resident_id, slots)}


def _assigned_case(conn, job_id, partner):
    job = get_job(job_id, partner, conn)
    row = conn.execute(
        "SELECT c.id,c.status,c.resident_id FROM cases c JOIN sharing_approvals a ON a.case_id=c.id "
        "WHERE c.id=? AND c.partner_job_id=? AND c.partner_id=? AND a.partner_id=c.partner_id",
        (job["request_id"], job_id, partner["partner_id"]),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Approved repair not found for this job.")
    return job, row


def _can_schedule(job, case):
    return (job["status"] == "accepted" and not job["pending_callback"]
            and case["status"] == CaseStatus.PARTNER_REQUESTED)


@router.get(JOB_CALENDAR)
def get_job_availability(job_id: str, partner: DeliveryPartner, week: Week = 0, conn=Depends(get_db)):
    conn.execute("BEGIN")
    job, case = _assigned_case(conn, job_id, partner)
    monday, slots = scheduling.weekly_slots(week)
    can_book = _can_schedule(job, case)
    available = [slot for slot in scheduling.slot_status(conn, case["resident_id"], slots)
                 if slot["available"] and not slot["booked"] and not slot["past"]] if can_book else []
    return {"week_start": monday, "slots": available, "can_book": can_book,
            "appointment": cases.get_case(conn, case["id"])["appointment"]}


@router.post(JOB_CALENDAR + "/book")
def book_visit(job_id: str, partner: DeliveryPartner, body: VisitChoice, conn=Depends(get_db)):
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        job, case = _assigned_case(conn, job_id, partner)
        saved = cases.get_case(conn, case["id"])["appointment"]
        if saved:
            if saved["start"] == body.start:
                return saved
            raise HTTPException(409, "This repair already has a booked visit.")
        if not _can_schedule(job, case):
            raise HTTPException(409, "Accept the repair before booking a visit.")
        try:
            day = date.fromisoformat(body.start[:10])
            _, slots = scheduling.weekly_slots(monday=day - timedelta(days=day.weekday()))
        except (ValueError, OverflowError) as exc:
            raise HTTPException(422, "Choose a slot from the timetable.") from exc
        slot = next((item for item in scheduling.slot_status(conn, case["resident_id"], slots)
                     if item["start"] == body.start), None)
        if not slot or slot["past"] or slot["booked"] or not slot["available"]:
            raise HTTPException(409, "This slot is no longer available. Choose another time.")

        slot_id, booked_at = body.start, now_iso()
        conn.execute("INSERT INTO appointment_slots VALUES (?,?,?,?)",
                     (case["id"], slot_id, slot["start"], slot["end"]))
        conn.execute("INSERT INTO appointments VALUES (?,?,?)", (case["id"], slot_id, booked_at))
        conn.execute("INSERT INTO heatfix_bookings VALUES (?,?)", (job_id, slot_id))
        conn.execute("UPDATE partner_jobs SET status='scheduled' WHERE id=?", (job_id,))
        cases.transition(conn, case["id"], CaseStatus.SCHEDULED, f"partner:{partner['partner_id']}",
                         {"job_id": job_id, "slot_id": slot_id})
        return {"case_id": case["id"], "slot_id": slot_id, "start": slot["start"], "end": slot["end"],
                "booked_at": booked_at}
