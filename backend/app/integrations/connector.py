"""Generic partner connector v1 (client side). Provider-specific details stay behind this module."""
import os

import httpx

from app.schemas import PartnerJobRequest


def get_partner_client():
    """HTTP client for partner endpoints. Tests override this dependency."""
    base = os.getenv("PARTNER_BASE_URL", "http://localhost:8000")
    with httpx.Client(base_url=base, timeout=10) as client:
        yield client


def callback_url() -> str:
    base = os.getenv("PUBLIC_BACKEND_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/integrations/partner-events"


def build_job_request(case: dict, ctx: dict, resident: dict, approval: dict) -> PartnerJobRequest:
    """Only fields the resident approved leave centrix (data minimisation)."""
    fields = set(approval["shared_fields"])
    prop = {"address": ctx["property"]["address"], "unit": ctx["unit"]["label"]}
    if "heating_type" in fields:
        prop["heating_type"] = ctx["property"]["heating"]
    if "access_details" in fields:
        prop["access_details"] = ctx["property"]["access_details"]
    issue = {"description": case["description"], "symptoms": case["symptoms"], "priority": case["urgency"]}
    if "prior_heating_case" in fields:
        prior = [p for p in ctx["prior_heating_cases"] if p["id"] != case["id"]]
        if prior:
            issue["previous_record"] = {"date": prior[0]["created_at"], "description": prior[0]["description"],
                                        "note": "Context only; current fault not diagnosed."}
    res = {}
    if "name" in fields:
        res["name"] = resident["name"]
    if "contact" in fields:
        res["contact"] = {"email": resident["email"], "phone": resident["phone"]}
    return PartnerJobRequest(
        request_id=case["id"],
        idempotency_key=f"{case['id']}-{case['issue_type']}-v1",
        service_type=case["issue_type"],
        property=prop,
        issue=issue,
        resident=res,
        sharing={"approved_fields": sorted(fields), "approved_at": approval["recorded_at"]},
        callback_url=callback_url(),
    )


def create_job(client: httpx.Client, partner: dict, job: PartnerJobRequest) -> dict:
    resp = client.post(f"{partner['base_url']}/connector/jobs", json=job.model_dump())
    resp.raise_for_status()
    return resp.json()
