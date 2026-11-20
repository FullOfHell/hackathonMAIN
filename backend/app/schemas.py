"""API request/response models. Shared team contract: see Docs/Reltix_Hackathon_Project_Plan.md §5."""
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

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
    availability_preferences: list[str] = Field(default_factory=list)
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


class SlotChoice(BaseModel):
    slot_id: str = Field(min_length=1)


class ResidentAction(BaseModel):
    resident_id: str


class ResidentSlotChoice(SlotChoice, ResidentAction):
    pass


class AppointmentSlot(SlotChoice):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def validate_interval(self):
        if self.end <= self.start:
            raise ValueError("slot end must be after start")
        return self


class SlotOffer(BaseModel):
    slots: list[AppointmentSlot] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ids(self):
        if len({slot.slot_id for slot in self.slots}) != len(self.slots):
            raise ValueError("slot IDs must be unique within the offer")
        return self


class CallbackEnvelope(BaseModel):
    schema_version: Literal["1.0"]
    event_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    occurred_at: AwareDatetime


class PartnerDecision(CallbackEnvelope):
    type: Literal["accepted", "rejected", "in_progress"]
    data: dict = Field(default_factory=dict)


class FailureReason(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


class PartnerFailed(CallbackEnvelope):
    type: Literal["failed"]
    data: FailureReason


class SlotsOffered(CallbackEnvelope):
    type: Literal["slots_offered"]
    data: SlotOffer


DocumentKind = Literal["completion_report", "invoice"]


class RepairReport(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    summary: str = Field(min_length=1, max_length=2000)


class RepairInvoice(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    invoice_number: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=2000)
    amount_cents: int = Field(strict=True, ge=0)
    currency: Literal["EUR"]


class RepairCompleted(CallbackEnvelope):
    type: Literal["completed"]
    data: RepairReport


class InvoiceReady(CallbackEnvelope):
    type: Literal["invoice_ready"]
    data: RepairInvoice


PartnerEvent = Annotated[
    PartnerDecision | PartnerFailed | SlotsOffered | RepairCompleted | InvoiceReady, Field(discriminator="type")
]
