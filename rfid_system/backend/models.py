"""Pydantic v2 models for the RFID backend.

These describe the request and response shapes used by the ESP32 firmware and
the web dashboard. Response shapes are kept identical to the original prototype
so the existing frontend keeps working.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from config import settings


def _now_local() -> datetime:
    """Timezone-aware timestamp in the configured local timezone."""
    return settings.now()


class RosterPerson(BaseModel):
    uid: str = Field(..., description="UID in the format sent by the ESP32 (hex pairs).")
    name: str
    role: str
    transport: str = Field(..., description="Mode of transport, affects lateness rules.")
    class_name: str | None = Field(
        None, description="Homeroom or class section shown on the display."
    )
    photo_url: str | None = Field(
        None, description="Optional HTTPS image the dashboard can show for the latest scan."
    )


class AttendanceEvent(BaseModel):
    uid: str
    timestamp: datetime = Field(default_factory=_now_local)
    reader_location: str = Field("main_gate", description="Where the scan occurred.")
    status: str = Field(..., description="One of: accepted, duplicate, rejected, late.")
    details: dict[str, Any] = Field(default_factory=dict)


class EventIn(BaseModel):
    uid: str
    status: str = Field("accepted", description="Defaults to 'accepted' for manual submissions.")
    timestamp: datetime | None = Field(
        None,
        description="Scan time from the device's real clock. When omitted, the server stamps it.",
    )
    person: dict[str, Any] | None = None
    lateness: dict[str, Any] | None = None
    reader_location: str | None = "main_gate"
    manual: bool = Field(
        False, description="True when the event was created from the dashboard, not the ESP32."
    )
    notes: str | None = Field(None, description="Optional free-form notes for manual submissions.")


class EventResponse(BaseModel):
    ok: bool
    event: AttendanceEvent


class RosterResponse(BaseModel):
    roster: list[RosterPerson]
