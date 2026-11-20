"""Simulated heating contractor 'HeatFix Aachen GmbH'. Stands in for an external partner system.
It implements the partner side of connector v1; it must not touch centrix case tables directly."""
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response

from app.db import get_db, now_iso
from app.schemas import PartnerJobRequest

PARTNER_ID = "p_heatfix"
router = APIRouter(prefix="/partners/heatfix", tags=["mock partner: HeatFix"])


@router.get("/connector/capabilities")
def capabilities():
    return {
        "schema_version": "1.0",
        "partner_id": PARTNER_ID,
        "service_types": ["heating_repair"],
        "regions": ["Aachen"],
        "required_fields": ["address", "unit", "issue"],
        "optional_fields": ["heating_type", "access_details", "name", "contact", "previous_record"],
        "events": ["accepted", "slots_offered", "scheduled", "in_progress", "completed", "invoice_ready", "failed"],
    }


@router.post("/connector/jobs", status_code=201)
def create_job(job: PartnerJobRequest, response: Response, conn=Depends(get_db)):
    if job.service_type != "heating_repair":
        raise HTTPException(422, "unsupported service_type")
    existing = conn.execute("SELECT * FROM partner_jobs WHERE idempotency_key=?", (job.idempotency_key,)).fetchone()
    if existing:
        response.status_code = 200
        return {"job_id": existing["id"], "status": existing["status"], "duplicate": True}
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    conn.execute("INSERT INTO partner_jobs VALUES (?,?,?,?,?,?,?)",
                 (job_id, PARTNER_ID, job.idempotency_key, job.request_id, job.model_dump_json(), "received", now_iso()))
    conn.commit()
    return {"job_id": job_id, "status": "received", "duplicate": False}


@router.get("/connector/jobs")
def list_jobs(conn=Depends(get_db)):
    return [{**dict(j), "payload": json.loads(j["payload"])}
            for j in conn.execute("SELECT * FROM partner_jobs WHERE partner_id=? ORDER BY received_at DESC", (PARTNER_ID,))]


@router.get("/connector/jobs/{job_id}")
def get_job(job_id: str, conn=Depends(get_db)):
    j = conn.execute("SELECT * FROM partner_jobs WHERE id=? AND partner_id=?", (job_id, PARTNER_ID)).fetchone()
    if not j:
        raise HTTPException(404, "job not found")
    return {**dict(j), "payload": json.loads(j["payload"])}
