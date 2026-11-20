"""API request/response models. Shared team contract: see Docs/Reltix_Hackathon_Project_Plan.md §5."""
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Required, TypedDict

IssueType = Annotated[str, Field(max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
Urgency = Literal["low", "normal", "high"]
Channel = Literal["portal_chat", "voice", "email", "manager"]

MissingIntakeField = Literal["heating_symptom", "hot_water_affected", "availability_preferences"]
IntakeExcerpt = Annotated[str, Field(min_length=1, max_length=160)]


def normalize_intake_text(text: str) -> str:
    return " ".join(text.split()).casefold()


class IntakeRequest(BaseModel):
    model_config = ConfigDict(strict=True, str_strip_whitespace=True, extra="forbid")

    report: str = Field(min_length=3, max_length=1950)
    hot_water_affected: bool | None = None


class IntakeResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    symptoms: list[IntakeExcerpt] = Field(max_length=12, json_schema_extra={"uniqueItems": True})
    urgency: Urgency | None
    availability_preferences: list[IntakeExcerpt] = Field(max_length=8, json_schema_extra={"uniqueItems": True})
    missing_information: list[MissingIntakeField] = Field(max_length=3, json_schema_extra={"uniqueItems": True})
    safety_signal: Literal["none", "possible_gas_leak"]

    @model_validator(mode="after")
    def validate_excerpts(self):
        for items in (self.symptoms, self.availability_preferences, self.missing_information):
            normalized = {normalize_intake_text(item) for item in items}
            if "" in normalized or len(normalized) != len(items):
                raise ValueError("intake items must be nonblank and unique")
        return self


class IntakeResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    source: Literal["model", "fallback"]
    result: IntakeResult

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


class BuildingJobScope(BaseModel):
    request_id: str
    scope: Literal["building_heating"]


class ResidentAction(BaseModel):
    resident_id: str


_EMAIL_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_DOMAIN_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL_PATTERN = rf"^{_EMAIL_ATOM}(?:\.{_EMAIL_ATOM})*@{_DOMAIN_LABEL}(?:\.{_DOMAIN_LABEL})+$"
_PHONE_GROUP = r"(?:[0-9]+|\([0-9]+\))"


def _validate_phone_length(phone: str) -> str:
    if not 7 <= sum(char.isdigit() for char in phone) <= 15:
        raise ValueError("phone must contain 7 to 15 digits")
    return phone


class ResidentProfilePatch(TypedDict, total=False):
    """The acting ID simulates resident identity in the demo. Omit fields to keep their values."""
    __pydantic_config__ = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True,
                                     json_schema_extra={"minProperties": 2})

    acting_resident_id: Required[Annotated[str, Field(min_length=1)]]
    name: Annotated[str, Field(min_length=1, max_length=120)]
    email: Annotated[str, Field(max_length=254, pattern=_EMAIL_PATTERN)]
    phone: Annotated[str, Field(max_length=40, pattern=rf"^\+?{_PHONE_GROUP}(?:[ .-]?{_PHONE_GROUP})*$"),
                     AfterValidator(_validate_phone_length)]
    preferred_contact: Annotated[str, Field(pattern=r"^(portal|email)$")]


class ResidentProfile(BaseModel):
    id: str
    unit_id: str
    name: str
    email: str | None
    phone: str | None
    preferred_contact: str | None
    move_in: str | None


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
