"""FastAPI backend for the ESP32 RFID attendance system.

This service provides a REST API that the ESP32 firmware can call to
store attendance events. Data is persisted to a JSON file so that the
front-end dashboard can display the events and the roster that the
hardware uses can be synchronized with the web application.
"""
from __future__ import annotations

import json
import pathlib
from datetime import datetime
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

BASE_DIR = pathlib.Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data"
LOG_PATH = DATA_PATH / "attendance_logs.json"
ROSTER_PATH = DATA_PATH / "roster.json"

DATA_PATH.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="ESP32 RFID Attendance Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RosterPerson(BaseModel):
    uid: str = Field(..., description="UID in the same format as sent by the ESP32 (hex pairs).")
    name: str
    role: str
    transport: str = Field(..., description="Mode of transport, affects lateness rules.")


class AttendanceEvent(BaseModel):
    uid: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    reader_location: str = Field("main_gate", description="Where the scan occurred.")
    status: str = Field(..., description="One of: accepted, duplicate, rejected, late.")
    details: Dict[str, Any] = Field(default_factory=dict)


class EventIn(BaseModel):
    uid: str
    status: str
    person: Dict[str, Any] | None = None
    lateness: Dict[str, Any] | None = None
    reader_location: str | None = "main_gate"


class EventResponse(BaseModel):
    ok: bool
    event: AttendanceEvent


class RosterResponse(BaseModel):
    roster: List[RosterPerson]


def _load_json(path: pathlib.Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to read {path.name}: {exc}")


def _save_json(path: pathlib.Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


@app.on_event("startup")
async def ensure_files() -> None:
    if not LOG_PATH.exists():
        _save_json(LOG_PATH, [])
    if not ROSTER_PATH.exists():
        _save_json(ROSTER_PATH, [])


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"status": "ok"}


@app.get("/api/roster", response_model=RosterResponse)
def get_roster() -> RosterResponse:
    roster_data = _load_json(ROSTER_PATH, [])
    return RosterResponse(roster=[RosterPerson(**person) for person in roster_data])


@app.post("/api/roster", response_model=RosterResponse)
def upsert_roster(people: List[RosterPerson]) -> RosterResponse:
    _save_json(ROSTER_PATH, [person.dict() for person in people])
    return RosterResponse(roster=people)


@app.get("/api/logs")
def get_logs() -> Dict[str, List[AttendanceEvent]]:
    logs = _load_json(LOG_PATH, [])
    return {"events": [AttendanceEvent(**event) for event in logs]}


@app.post("/api/logs", response_model=EventResponse)
def register_event(event_in: EventIn) -> EventResponse:
    logs = _load_json(LOG_PATH, [])

    event = AttendanceEvent(
        uid=event_in.uid,
        status=event_in.status,
        reader_location=event_in.reader_location or "main_gate",
        details={
            "person": event_in.person,
            "lateness": event_in.lateness,
        },
    )

    logs.append(json.loads(event.json()))
    _save_json(LOG_PATH, logs)

    return EventResponse(ok=True, event=event)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
