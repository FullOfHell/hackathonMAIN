"""API request/response models. Shared team contract: see Docs/Reltix_Hackathon_Project_Plan.md §5."""
from typing import Literal

from pydantic import BaseModel, Field

IssueType = Literal["heating_repair"]
Urgency = Literal["low", "normal", "high"]
Channel = Literal["portal_chat", "voice", "email", "manager"]

# Fields a resident may approve for sharing with a partner (data minimisation).
SHAREABLE_FIELDS = ["name", "contact", "address", "unit", "heating_type", "access_details", "issue", "prior_heating_case"]
REQUIRED_SHARED_FIELDS = ["address", "unit", "issue"]
DEFAULT_PROPOSED_FIELDS = ["name", "contact", "address", "unit", "heating_type", "access_details", "issue"]


class CaseCreate(BaseModel):
    unit_id: str
    resident_id: str
    issue_type: IssueType = "heating_repair"
    description: str = Field(min_length=3, max_length=2000)
    symptoms: list[str] = []
    urgency: Urgency = "normal"
    source_channel: Channel = "portal_chat"


class SharingApprovalIn(BaseModel):
    approved_fields: list[str]
    channel: Channel = "portal_chat"
    approved_by: str  # resident id


class PartnerJobRequest(BaseModel):
    """Generic connector v1 job request (what any partner receives)."""
    schema_version: Literal["1.0"] = "1.0"
    request_id: str
    idempotency_key: str
    service_type: IssueType
    property: dict
    issue: dict
    resident: dict = {}
    sharing: dict
    callback_url: str
