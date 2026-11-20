"""Let the n8n workflow dispatch a stored, approved connector order by case ID."""
import os
from hmac import compare_digest

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db import get_db
from app.integrations.connector import DispatchUnconfirmed, create_job, get_partner_client
from app.schemas import PartnerJobRequest
from app.states import CaseStatus


router = APIRouter(prefix="/api/integrations", tags=["connector"])


class ApprovedDispatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(min_length=1, max_length=64)


def verify_dispatch_secret(x_connector_dispatch_secret: str | None = Header(default=None)):
    expected = os.getenv("CONNECTOR_DISPATCH_SECRET", "").strip()
    if not expected or not x_connector_dispatch_secret or not compare_digest(
        x_connector_dispatch_secret.encode(), expected.encode()
    ):
        raise HTTPException(401, "invalid connector dispatch secret")


@router.post("/approved-dispatch", dependencies=[Depends(verify_dispatch_secret)])
def dispatch_approved_order(body: ApprovedDispatch, conn=Depends(get_db), client=Depends(get_partner_client)):
    row = conn.execute(
        "SELECT c.status,c.partner_job_id,o.payload,p.base_url,p.active "
        "FROM cases c JOIN sharing_approvals a ON a.case_id=c.id AND a.partner_id=c.partner_id "
        "JOIN partner_orders o ON o.case_id=c.id JOIN partners p ON p.id=c.partner_id WHERE c.id=?",
        (body.case_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "approved connector order not found")
    if row["partner_job_id"]:
        return {"case_id": body.case_id, "job_id": row["partner_job_id"], "duplicate": True}
    if row["status"] != CaseStatus.PARTNER_REQUESTED or not row["active"]:
        raise HTTPException(409, "case is no longer eligible for dispatch")
    order = PartnerJobRequest.model_validate_json(row["payload"])
    try:
        result = create_job(client, dict(row), order)
    except (httpx.HTTPError, DispatchUnconfirmed) as exc:
        raise HTTPException(502, "partner dispatch was not confirmed") from exc
    return {"case_id": body.case_id, "job_id": result["job_id"], "duplicate": result.get("duplicate") is True}
