"""Weekly calendar slots and conflict checks in the demo property time zone."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

CALENDAR_WEEKS = 3


def weekly_slots(week: int = 0, monday: date | None = None):
    local_zone = ZoneInfo("Europe/Berlin")
    now = datetime.now(timezone.utc)
    today = now.astimezone(local_zone).date()
    first_week = today - timedelta(days=today.weekday())
    if monday is None:
        monday = first_week + timedelta(weeks=week)
    if monday.weekday() or not first_week <= monday < first_week + timedelta(weeks=CALENDAR_WEEKS):
        raise ValueError("Choose a Monday within the calendar window.")
    slots = []
    for day in range(5):
        for hour in range(9, 17):
            start = datetime.combine(monday + timedelta(days=day), time(hour), local_zone).astimezone(timezone.utc)
            slots.append({"start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(),
                          "day": day, "hour": hour, "past": start <= now})
    return monday, slots


def reservations(conn, resident_id, start, end, exclude_case=None):
    # The second SELECT protects the interval while a legacy local booking awaits centrix confirmation.
    return conn.execute(
        """SELECT s.start,s.end FROM cases c JOIN appointments a ON a.case_id=c.id
           JOIN appointment_slots s USING (case_id,slot_id)
           WHERE c.resident_id=? AND c.id IS NOT ? AND c.status NOT IN ('CANCELLED','FAILED','DECLINED')
           AND julianday(s.start)<julianday(?) AND julianday(s.end)>julianday(?)
           UNION
           SELECT s.start,s.end FROM cases c JOIN heatfix_bookings h ON h.job_id=c.partner_job_id
           JOIN appointment_slots s ON s.case_id=c.id AND s.slot_id=h.slot_id
           WHERE c.resident_id=? AND c.id IS NOT ? AND c.status='SLOTS_OFFERED'
           AND julianday(s.start)<julianday(?) AND julianday(s.end)>julianday(?)""",
        (resident_id, exclude_case, end, start, resident_id, exclude_case, end, start),
    ).fetchall()


def slot_status(conn, resident_id, slots):
    starts = {row["start"] for row in conn.execute(
        "SELECT start FROM tenant_availability WHERE resident_id=? AND start BETWEEN ? AND ?",
        (resident_id, slots[0]["start"], slots[-1]["start"]),
    )}
    booked = [(datetime.fromisoformat(row["start"]), datetime.fromisoformat(row["end"]))
              for row in reservations(conn, resident_id, slots[0]["start"], slots[-1]["end"])]
    for slot in slots:
        start, end = datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"])
        slot["booked"] = any(start < booked_end and end > booked_start for booked_start, booked_end in booked)
        slot["available"] = slot["start"] in starts
    return slots
