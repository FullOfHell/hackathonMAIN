"""Install connector capability manifests from the local demo configuration."""
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from app.db import get_db
from app.schemas import DEFAULT_PROPOSED_FIELDS, REQUIRED_SHARED_FIELDS, SHAREABLE_FIELDS, IssueType

MANIFESTS = Path(__file__).resolve().parents[2] / "seed" / "partner-registrations"
router = APIRouter(tags=["connector capabilities"])


class Capabilities(BaseModel):
    schema_version: Literal["1.0"]
    partner_id: str = Field(min_length=1)
    kind: Literal["delivery", "offer"]
    categories: list[IssueType] = Field(min_length=1)
    regions: list[str] = Field(min_length=1)
    triggers: list[str] = Field(min_length=1)
    required_fields: list[str]
    optional_fields: list[str]
    events: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_delivery_fields(self):
        if self.kind == "delivery":
            required = set(consent_fields(self.required_fields))
            supported = set(SHAREABLE_FIELDS)
            if not set(REQUIRED_SHARED_FIELDS) <= required <= supported:
                raise ValueError("delivery partners must require address, unit and issue and use supported consent fields")
        return self


class Registration(BaseModel):
    name: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    capabilities: Capabilities


def consent_fields(fields: list[str]) -> list[str]:
    return list(dict.fromkeys("prior_heating_case" if field == "previous_record" else field for field in fields))


def sharing_policy(conn, partner_id: str | None) -> dict:
    row = conn.execute("SELECT manifest FROM partner_capabilities WHERE partner_id=?", (partner_id,)).fetchone()
    if not row:
        return {"required_fields": REQUIRED_SHARED_FIELDS, "shareable_fields": SHAREABLE_FIELDS,
                "proposed_fields": DEFAULT_PROPOSED_FIELDS}
    manifest = json.loads(row["manifest"])
    required = consent_fields(manifest["required_fields"])
    optional = consent_fields(manifest["optional_fields"])
    supported = set(required + optional)
    return {"required_fields": required, "shareable_fields": [field for field in SHAREABLE_FIELDS if field in supported],
            "proposed_fields": [field for field in DEFAULT_PROPOSED_FIELDS if field in supported]}


def install_registrations(conn, directory=MANIFESTS):
    for path in sorted(directory.glob("*.json")):
        registration = Registration.model_validate_json(path.read_bytes())
        cap = registration.capabilities
        conn.execute(
            "INSERT INTO partners (id,name,base_url,service_types,regions) VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO NOTHING",
            (cap.partner_id, registration.name, registration.base_url,
             json.dumps(cap.categories), json.dumps(cap.regions)))
        # Preserve region, categories and endpoint overrides of pre-existing demo partners.
        routing = conn.execute("SELECT service_types,regions FROM partners WHERE id=?", (cap.partner_id,)).fetchone()
        manifest = cap.model_copy(update={"categories": json.loads(routing["service_types"]),
                                          "regions": json.loads(routing["regions"])})
        conn.execute("INSERT INTO partner_capabilities VALUES (?,?) ON CONFLICT(partner_id) DO UPDATE "
                     "SET manifest=excluded.manifest", (cap.partner_id, manifest.model_dump_json()))


@router.get("/api/integrations/partners")
def discover_partners(category: str, region: str, trigger: str, conn=Depends(get_db)):
    rows = conn.execute(
        "SELECT p.name,p.base_url,k.manifest FROM partners p JOIN partner_capabilities k ON p.id=k.partner_id "
        "WHERE p.active=1 AND ? IN (SELECT value FROM json_each(p.service_types)) "
        "AND ? IN (SELECT value FROM json_each(p.regions)) "
        "AND ? IN (SELECT value FROM json_each(k.manifest,'$.triggers')) ORDER BY p.name,p.id",
        (category, region, trigger))
    return [{"name": r["name"], "base_url": r["base_url"], "capabilities": json.loads(r["manifest"])} for r in rows]


def local_capabilities(conn, slug: str) -> dict:
    # Keep the original demo route available even when its delivery endpoint is overridden.
    row = conn.execute("SELECT manifest FROM partner_capabilities k JOIN partners p ON p.id=k.partner_id "
                       "WHERE p.base_url=? OR (?='heatfix' AND p.id='p_heatfix') "
                       "ORDER BY (p.id='p_heatfix') DESC,p.id", (f"/partners/{slug}", slug)).fetchone()
    if not row:
        raise HTTPException(404, "partner capabilities not found")
    return json.loads(row["manifest"])


@router.get("/partners/{slug}/connector/capabilities")
def simulated_capabilities(slug: str, conn=Depends(get_db)):
    manifest = local_capabilities(conn, slug)
    return {**manifest, "service_types": manifest["categories"]} if slug == "heatfix" else manifest
