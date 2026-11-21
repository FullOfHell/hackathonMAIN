from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from tests.test_vertical_slice import create_case

TENANT = "/api/units/unit_4b/residents/c_202/availability"
ACTOR = {"acting_resident_id": "c_202"}
CONSENT = {"approved_by": "c_202", "approved_fields": ["address", "unit", "issue"]}


def _week(client):
    result = client.get(TENANT, params=ACTOR | {"week": 1})
    assert result.status_code == 200, result.text
    return result.json()


def _save(client, calendar, starts):
    return client.put(TENANT, json=ACTOR | {"week_start": calendar["week_start"], "available_starts": starts})


def _job(client, slug="heatfix"):
    case = create_case(client)
    path = f"/api/cases/{case['id']}"
    approved = client.post(path + "/sharing-approval", json=CONSENT)
    assert approved.status_code == 200, approved.text
    job = f"/partners/{slug}/connector/jobs/{approved.json()['partner_job_id']}"
    return path, job


def test_tenant_editing_and_contractor_booking_preserve_appointment(client):
    calendar = _week(client)
    assert len(calendar["slots"]) == 40
    last_week = client.get(TENANT, params=ACTOR | {"week": 2})
    assert last_week.status_code == 200
    assert client.get(TENANT, params=ACTOR | {"week": 3}).status_code == 422
    outside = date.fromisoformat(last_week.json()["week_start"]) + timedelta(weeks=1)
    assert _save(client, {"week_start": outside.isoformat()}, []).status_code == 422
    first, second = (slot["start"] for slot in calendar["slots"][:2])
    assert client.get(TENANT, params={"acting_resident_id": "c_203"}).status_code == 403
    assert _save(client, calendar, ["2025-01-01T10:00:00+00:00"]).status_code == 422
    assert _save(client, calendar, [first, second]).status_code == 200
    path, job = _job(client)
    timetable = job + "/tenant-availability"
    assert client.get(timetable, params={"week": 3}).status_code == 422
    assert client.get(timetable, params={"week": 1}).json()["slots"] == []
    assert client.post(timetable + "/book", json={"start": first}).status_code == 409
    assert client.post(job + "/accept").status_code == 200
    assert [slot["start"] for slot in client.get(timetable, params={"week": 1}).json()["slots"]] == [first, second]

    assert _save(client, calendar, [first]).status_code == 200
    assert client.post(timetable + "/book", json={"start": second}).status_code == 409
    booked = client.post(timetable + "/book", json={"start": first})
    assert booked.status_code == 200, booked.text
    assert client.post(timetable + "/book", json={"start": first}).json() == booked.json()
    assert _save(client, calendar, []).json()["slots"][0]["booked"]
    assert client.get(timetable).json()["appointment"] == booked.json()
    assert client.get(path).json()["status"] == "SCHEDULED"
    assert client.get(path).json()["appointment"] == booked.json()
    assert client.post(job + "/start").status_code == 200


def test_two_assigned_contractors_cannot_book_the_same_tenant_slot(client):
    calendar = _week(client)
    start, other = (slot["start"] for slot in calendar["slots"][:2])
    assert _save(client, calendar, [start, other]).status_code == 200
    _, first = _job(client)
    contractor = {"name": "Aachen Demo Heating", "slug": "demo-heating", "region": "Aachen",
                  "routing": {"latitude": 50.775, "longitude": 6.083, "quality_rating": 5,
                              "estimated_price_eur": 90}}
    assert client.post("/api/manager/contractors", json=contractor).status_code == 201
    _, second = _job(client, slug="demo-heating")
    assert client.post(first + "/accept").status_code == client.post(second + "/accept").status_code == 200
    assert client.get(first.replace("/heatfix/", "/demo-heating/") + "/tenant-availability").status_code == 404

    def book(job):
        return job, client.post(job + "/tenant-availability/book", json={"start": start})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(book, (first, second)), key=lambda result: result[1].status_code)
    (_, winner), (loser_job, loser) = results
    assert (winner.status_code, loser.status_code) == (200, 409)
    available = client.get(loser_job + "/tenant-availability", params={"week": 1}).json()["slots"]
    assert [slot["start"] for slot in available] == [other]
    assert client.post(loser_job + "/tenant-availability/book", json={"start": other}).status_code == 200
