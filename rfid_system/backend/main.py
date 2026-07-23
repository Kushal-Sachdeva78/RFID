"""FastAPI backend for the ESP32 RFID attendance system.

This service provides a REST API that the ESP32 firmware and the web dashboard
call to store and read attendance events and the roster. Persistence lives
behind the Storage abstraction (see storage.py) so the JSON backend can be
swapped later without changing these route handlers.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models import (
    AttendanceEvent,
    EventIn,
    EventResponse,
    RosterPerson,
    RosterResponse,
)
from storage import Storage

_storage = Storage(settings.data_dir)


def get_storage() -> Storage:
    """Dependency returning the app's Storage. Overridable in tests."""
    return _storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_storage().ensure_initialised()
    yield


app = FastAPI(title="ESP32 RFID Attendance Service", lifespan=lifespan)

# The dashboard is served from a different origin and calls this API with plain
# fetch (no cookies), so credentials are disabled. A wildcard origin with
# credentials enabled is rejected by browsers, so this also fixes that.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok"}


@app.get("/api/roster", response_model=RosterResponse)
def get_roster(storage: Storage = Depends(get_storage)) -> RosterResponse:
    return RosterResponse(roster=[RosterPerson(**person) for person in storage.roster.all()])


@app.post("/api/roster", response_model=RosterResponse)
def upsert_roster(
    people: list[RosterPerson], storage: Storage = Depends(get_storage)
) -> RosterResponse:
    storage.roster.replace([person.model_dump() for person in people])
    return RosterResponse(roster=people)


@app.get("/api/logs")
def get_logs(storage: Storage = Depends(get_storage)) -> dict[str, list[AttendanceEvent]]:
    return {"events": [AttendanceEvent(**event) for event in storage.logs.all()]}


def _lookup_person(storage: Storage, uid: str) -> dict[str, Any] | None:
    """Return the roster entry for the provided UID if one exists."""
    for person in storage.roster.all():
        if person.get("uid") == uid:
            return person
    return None


@app.post("/api/logs", response_model=EventResponse)
def register_event(
    event_in: EventIn, storage: Storage = Depends(get_storage)
) -> EventResponse:
    person_details = event_in.person or _lookup_person(storage, event_in.uid)

    # Use the device's clock when it sends one; otherwise stamp on arrival. A
    # naive timestamp is assumed to be in the configured local timezone.
    timestamp = event_in.timestamp
    if timestamp is not None and timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=settings.tz)

    event_kwargs: dict[str, Any] = {
        "uid": event_in.uid,
        "status": event_in.status,
        "reader_location": event_in.reader_location or "main_gate",
        "details": {
            "person": person_details,
            "lateness": event_in.lateness,
            "manual": event_in.manual,
            "notes": event_in.notes,
        },
    }
    if timestamp is not None:
        event_kwargs["timestamp"] = timestamp

    event = AttendanceEvent(**event_kwargs)

    storage.logs.append(event.model_dump(mode="json"))
    return EventResponse(ok=True, event=event)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
