"""FastAPI backend for the ESP32 RFID attendance system.

This service provides a REST API that the ESP32 firmware and the web dashboard
call to store and read attendance events and the roster. Persistence lives
behind the Storage abstraction (see storage.py) so the JSON backend can be
swapped later without changing these route handlers.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from auth import require_role
from config import settings
from models import (
    AttendanceEvent,
    EventIn,
    EventResponse,
    RosterPerson,
    RosterResponse,
)
from notifier import Notifier, StrikeNotification, get_notifier
from services import (
    authorization_for,
    classify_direction,
    compute_lateness,
    late_days_in_cycle,
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


@app.post(
    "/api/roster",
    response_model=RosterResponse,
    dependencies=[Depends(require_role("admin", "office"))],
)
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


def _teacher_for(storage: Storage, class_section: str | None) -> dict[str, Any] | None:
    if not class_section:
        return None
    for teacher in storage.class_teachers.all():
        if teacher.get("class_section") == class_section:
            return teacher
    return None


def _maybe_notify_strike(
    storage: Storage,
    notifier: Notifier,
    uid: str,
    person_details: dict[str, Any] | None,
    when,
) -> None:
    """Notify the class teacher when a student reaches the strike threshold.

    A notifier failure must never break attendance recording, so it is guarded.
    """
    count, cycle, late_dates = late_days_in_cycle(storage.logs.all(), uid, when)
    if cycle is None or count != settings.strike_threshold:
        return

    class_section = (person_details or {}).get("class_name")
    teacher = _teacher_for(storage, class_section)
    notification = StrikeNotification(
        student_name=(person_details or {}).get("name") or uid,
        student_uid=uid,
        class_section=class_section,
        cycle_name=cycle.name,
        strike_count=count,
        late_dates=late_dates,
        teacher_name=(teacher or {}).get("teacher_name"),
        teacher_email=(teacher or {}).get("teacher_email"),
        created_at=settings.now(),
    )
    try:
        notifier.notify(notification)
    except Exception:  # noqa: BLE001 - recording attendance must not fail here
        pass


def _record_event(
    event_in: EventIn, storage: Storage, response: Response, notifier: Notifier
) -> EventResponse:
    """Shared ingest path for both device scans and manual office entries.

    Computes entry/exit direction, second-resolution lateness, and the
    guard-facing transport authorization on the backend, so the ESP32 stays thin
    and this logic is unit tested. Three late arrivals in a learning cycle notify
    the class teacher.
    """
    person_details = event_in.person or _lookup_person(storage, event_in.uid)
    transport = (person_details or {}).get("transport")

    # Use the device's clock when it sends one; otherwise stamp on arrival. A
    # naive timestamp is assumed to be in the configured local timezone.
    timestamp = event_in.timestamp
    if timestamp is not None and timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=settings.tz)
    effective_time = timestamp if timestamp is not None else settings.now()

    prior_events = storage.logs.all()
    status = event_in.status
    lateness_info = event_in.lateness
    direction: str | None
    if status == "rejected":
        # Unknown card: no direction, no lateness, no authorization.
        direction = None
    else:
        direction, is_duplicate = classify_direction(prior_events, event_in.uid, effective_time)
        if is_duplicate:
            status = "duplicate"
        elif direction == "entry":
            # Lateness applies to arrival. The backend is authoritative.
            late, minutes = compute_lateness(effective_time, transport)
            status = "late" if late else "accepted"
            lateness_info = {"late": late, "minutes": minutes}

    authorization = None
    if direction == "exit":
        authorization = authorization_for(transport)

    event_kwargs: dict[str, Any] = {
        "uid": event_in.uid,
        "status": status,
        "reader_location": event_in.reader_location or "main_gate",
        "direction": direction,
        "details": {
            "person": person_details,
            "lateness": lateness_info,
            "manual": event_in.manual,
            "recorded_by": event_in.recorded_by,
            "notes": event_in.notes,
        },
    }
    if timestamp is not None:
        event_kwargs["timestamp"] = timestamp

    event = AttendanceEvent(**event_kwargs)
    storage.logs.append(event.model_dump(mode="json"))

    if status == "late" and direction == "entry":
        _maybe_notify_strike(storage, notifier, event_in.uid, person_details, effective_time)

    # Expose direction and authorization as headers too, so the thin firmware
    # can show a guard banner without parsing JSON.
    response.headers["X-Direction"] = direction or ""
    response.headers["X-Transport-Authorization"] = authorization or ""

    return EventResponse(
        ok=True,
        event=event,
        direction=direction,
        transport=transport if direction == "exit" else None,
        authorization=authorization,
    )


@app.post("/api/logs", response_model=EventResponse)
def register_event(
    event_in: EventIn,
    response: Response,
    storage: Storage = Depends(get_storage),
    notifier: Notifier = Depends(get_notifier),
) -> EventResponse:
    """Device scan ingest. Open, since the ESP32 has no key (by design)."""
    return _record_event(event_in, storage, response, notifier)


@app.post("/api/manual-entry", response_model=EventResponse)
def manual_entry(
    event_in: EventIn,
    response: Response,
    role: str | None = Depends(require_role("office", "teacher", "admin")),
    storage: Storage = Depends(get_storage),
    notifier: Notifier = Depends(get_notifier),
) -> EventResponse:
    """Office-side fallback for a forgotten or lost card.

    Requires a staff role. The event is flagged manual and attributed to the
    staff member who recorded it (recorded_by, falling back to their role).
    """
    event_in.manual = True
    if not event_in.recorded_by:
        event_in.recorded_by = role or "staff"
    return _record_event(event_in, storage, response, notifier)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
