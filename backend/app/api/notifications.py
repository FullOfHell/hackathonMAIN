"""Notification box and per-recipient preferences for the outbound noreply bot."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db import get_db
from app.services import notifications as svc

router = APIRouter(prefix="/api", tags=["notifications"])

RecipientType = Literal["resident", "owner", "manager"]


class CategoryPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    email: bool
    text: bool


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient_type: RecipientType | None = None
    recipient_id: str | None = None
    telegram_chat_id: str | None = Field(default=None, max_length=64)
    ntfy_topic: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{16,64}$")
    categories: list[CategoryPreference]


@router.get("/notifications")
def list_notifications(recipient_type: RecipientType, recipient_id: str, conn=Depends(get_db)):
    if svc.recipient(conn, recipient_type, recipient_id) is None:
        raise HTTPException(404, "recipient not found")
    return svc.list_notifications(conn, recipient_type, recipient_id)


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: int, conn=Depends(get_db)):
    with conn:
        item = svc.mark_read(conn, notification_id)
    if item is None:
        raise HTTPException(404, "notification not found")
    return item


@router.get("/recipients/{recipient_type}/{recipient_id}/notification-preferences")
def get_preferences(recipient_type: RecipientType, recipient_id: str, conn=Depends(get_db)):
    if svc.recipient(conn, recipient_type, recipient_id) is None:
        raise HTTPException(404, "recipient not found")
    with conn:
        # A private push topic is created on first read so the recipient can subscribe in the ntfy app.
        svc.ensure_ntfy_topic(conn, recipient_type, recipient_id)
    return svc.get_preferences(conn, recipient_type, recipient_id)


@router.put("/recipients/{recipient_type}/{recipient_id}/notification-preferences")
def put_preferences(recipient_type: RecipientType, recipient_id: str, body: PreferencesIn, conn=Depends(get_db)):
    if (body.recipient_type or recipient_type) != recipient_type or (body.recipient_id or recipient_id) != recipient_id:
        raise HTTPException(422, "body recipient does not match the URL")
    if svc.recipient(conn, recipient_type, recipient_id) is None:
        raise HTTPException(404, "recipient not found")
    allowed = set(svc.CATEGORIES[recipient_type])
    unknown = sorted({c.category for c in body.categories} - allowed)
    if unknown:
        raise HTTPException(422, {"unknown_categories": unknown, "allowed_categories": sorted(allowed)})
    with conn:
        contacts = body.model_dump(include={"telegram_chat_id", "ntfy_topic"} & body.model_fields_set)
        svc.save_preferences(conn, recipient_type, recipient_id, [c.model_dump() for c in body.categories], contacts)
    return svc.get_preferences(conn, recipient_type, recipient_id)
