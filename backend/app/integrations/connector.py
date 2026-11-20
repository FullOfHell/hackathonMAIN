"""Generic partner connector v1 (client side). Provider-specific details stay behind this module."""
import os
import secrets

import httpx

from app.schemas import PartnerJobRequest


_LOCAL_CALLBACK_SECRET = secrets.token_urlsafe(32)


class DispatchUnconfirmed(Exception):
    """The partner may have received the job. It is safe to repeat the order."""


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
    issue = {"description": case["description"], "symptoms": case["symptoms"], "priority": case["urgency"],
             "availability_preferences": case["availability_preferences"]}
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
    try:
        resp = client.post(f"{partner['base_url']}/connector/jobs", json=job.model_dump())
    except httpx.ConnectError:
        raise
    except httpx.TransportError as exc:
        raise DispatchUnconfirmed("partner dispatch was not confirmed") from exc
    if resp.is_server_error:
        raise DispatchUnconfirmed("partner dispatch was not confirmed")
    resp.raise_for_status()
    try:
        result = resp.json()
    except ValueError as exc:
        raise DispatchUnconfirmed("partner returned an invalid job acknowledgment") from exc
    if not isinstance(result, dict) or not isinstance(result.get("job_id"), str) or not result["job_id"].strip():
        raise DispatchUnconfirmed("partner did not return a job ID")
    return result


def dispatch_job(client: httpx.Client, partner: dict, job: PartnerJobRequest) -> dict:
    webhook_url = os.getenv("N8N_CASE_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return create_job(client, partner, job)

    secret = os.getenv("N8N_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise DispatchUnconfirmed("N8N_WEBHOOK_SECRET is missing")

    try:
        response = client.post(
            webhook_url,
            headers={"X-N8N-Webhook-Secret": secret},
            json={"event": "maintenance.sharing_approved", "case_id": job.request_id, "order": job.model_dump()},
            follow_redirects=False,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        raise DispatchUnconfirmed("n8n dispatch was not confirmed") from exc

    if not isinstance(result, dict) or result.get("case_id") != job.request_id:
        raise DispatchUnconfirmed("n8n returned a response for an invalid case")
    job_id = result.get("job_id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise DispatchUnconfirmed("n8n did not return a job ID")
    return {"job_id": job_id, "duplicate": result.get("duplicate") is True}


def book_slot(client: httpx.Client, partner_url: str, job_id: str, slot_id: str) -> None:
    response = client.post(f"{partner_url}/connector/jobs/{job_id}/book", json={"slot_id": slot_id})
    response.raise_for_status()
    confirmation = response.json()
    expected = {"job_id": job_id, "slot_id": slot_id, "status": "scheduled"}
    if not isinstance(confirmation, dict) or any(confirmation.get(key) != value for key, value in expected.items()):
        raise ValueError("partner did not confirm the requested booking")


def partner_webhook_secret() -> str:
    return os.getenv("PARTNER_WEBHOOK_SECRET") or _LOCAL_CALLBACK_SECRET
