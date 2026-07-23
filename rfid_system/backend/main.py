"""FastAPI backend for the ESP32 RFID attendance system.

This service provides a REST API that the ESP32 firmware and the web dashboard
call to store and read attendance events and the roster. Persistence lives
behind the Storage abstraction (see storage.py) so the JSON backend can be
swapped later without changing these route handlers.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from auth import require_role
from config import settings
from laptop_service import (
    SETTABLE_LAPTOP_STATUSES,
    active_loans_for,
    end_of_local_day,
    format_duration,
    held_seconds,
    is_request_expired,
)
from models import (
    AttendanceEvent,
    EventIn,
    EventResponse,
    IssueIn,
    Laptop,
    LaptopIn,
    LaptopPatch,
    Loan,
    LoanRequestIn,
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


# --- Laptop borrowing ----------------------------------------------------------


def _get_loan_or_404(loans: list[dict[str, Any]], loan_id: str) -> dict[str, Any]:
    for loan in loans:
        if loan.get("id") == loan_id:
            return loan
    raise HTTPException(status_code=404, detail="Loan not found")


def _get_laptop(laptops: list[dict[str, Any]], asset_code: str) -> dict[str, Any] | None:
    for laptop in laptops:
        if laptop.get("asset_code") == asset_code:
            return laptop
    return None


def _apply_lazy_expiry(storage: Storage, now) -> list[dict[str, Any]]:
    """Expire approved requests past their deadline, persisting the change."""
    loans = storage.loans.all()
    changed = False
    for loan in loans:
        if is_request_expired(loan, now):
            loan["state"] = "expired"
            loan["closed_reason"] = "not collected by the deadline"
            changed = True
    if changed:
        storage.loans.replace(loans)
    return loans


@app.post("/api/laptops", response_model=Laptop, status_code=201)
def register_laptop(
    payload: LaptopIn,
    role: str | None = Depends(require_role("helper", "admin")),
    storage: Storage = Depends(get_storage),
) -> Laptop:
    laptops = storage.laptops.all()
    if _get_laptop(laptops, payload.asset_code) is not None:
        raise HTTPException(status_code=409, detail=f"Laptop {payload.asset_code} already registered")
    laptop = Laptop(asset_code=payload.asset_code, status="available", notes=payload.notes)
    laptops.append(laptop.model_dump(mode="json"))
    storage.laptops.replace(laptops)
    return laptop


@app.get("/api/laptops")
def list_laptops(
    status: str | None = None, storage: Storage = Depends(get_storage)
) -> dict[str, list[dict[str, Any]]]:
    laptops = storage.laptops.all()
    if status:
        laptops = [lp for lp in laptops if lp.get("status") == status]
    return {"laptops": laptops}


@app.patch("/api/laptops/{asset_code}", response_model=Laptop)
def patch_laptop(
    asset_code: str,
    payload: LaptopPatch,
    role: str | None = Depends(require_role("helper", "admin")),
    storage: Storage = Depends(get_storage),
) -> Laptop:
    laptops = storage.laptops.all()
    laptop = _get_laptop(laptops, asset_code)
    if laptop is None:
        raise HTTPException(status_code=404, detail=f"Laptop {asset_code} not registered")
    if payload.status is not None:
        if payload.status not in SETTABLE_LAPTOP_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"status must be one of {sorted(SETTABLE_LAPTOP_STATUSES)}",
            )
        if laptop.get("status") == "on_loan" and payload.status != "available":
            raise HTTPException(
                status_code=409,
                detail="Laptop is on loan; record a return before changing its status",
            )
        laptop["status"] = payload.status
    if payload.notes is not None:
        laptop["notes"] = payload.notes
    storage.laptops.replace(laptops)
    return Laptop(**laptop)


@app.post("/api/loans/request", response_model=Loan, status_code=201)
def request_loan(
    payload: LoanRequestIn, storage: Storage = Depends(get_storage)
) -> Loan:
    """Student raises a borrow request (open, like a card tap at a kiosk)."""
    now = settings.now()
    loans = storage.loans.all()
    active = active_loans_for(loans, payload.student_uid, now)
    if len(active) >= settings.max_concurrent_loans:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Student already has {len(active)} active loan(s); "
                f"the limit is {settings.max_concurrent_loans}"
            ),
        )
    name = payload.student_name
    if not name:
        person = _lookup_person(storage, payload.student_uid)
        if person:
            name = person.get("name")
    loan = Loan(
        id=uuid.uuid4().hex[:12],
        student_uid=payload.student_uid,
        student_name=name,
        state="requested",
        requested_at=now,
    )
    loans.append(loan.model_dump(mode="json"))
    storage.loans.replace(loans)
    return loan


@app.get("/api/loans")
def list_loans(
    state: str | None = None,
    student_uid: str | None = None,
    storage: Storage = Depends(get_storage),
) -> dict[str, list[dict[str, Any]]]:
    loans = _apply_lazy_expiry(storage, settings.now())
    if state:
        loans = [loan for loan in loans if loan.get("state") == state]
    if student_uid:
        loans = [loan for loan in loans if loan.get("student_uid") == student_uid]
    return {"loans": loans}


@app.get("/api/loans/outstanding")
def outstanding_loans(storage: Storage = Depends(get_storage)) -> dict[str, list[dict[str, Any]]]:
    now = settings.now()
    loans = _apply_lazy_expiry(storage, now)
    outstanding = []
    for loan in loans:
        if loan.get("state") != "issued":
            continue
        seconds = held_seconds(loan, now)
        outstanding.append(
            {
                "id": loan.get("id"),
                "student_uid": loan.get("student_uid"),
                "student_name": loan.get("student_name"),
                "asset_code": loan.get("asset_code"),
                "issued_at": loan.get("issued_at"),
                "issued_by": loan.get("issued_by"),
                "held_seconds": seconds,
                "held_for": format_duration(seconds),
            }
        )
    return {"outstanding": outstanding}


@app.post("/api/loans/{loan_id}/approve", response_model=Loan)
def approve_loan(
    loan_id: str,
    role: str | None = Depends(require_role("teacher", "admin")),
    storage: Storage = Depends(get_storage),
) -> Loan:
    now = settings.now()
    loans = storage.loans.all()
    loan = _get_loan_or_404(loans, loan_id)
    if loan.get("state") != "requested":
        raise HTTPException(status_code=409, detail=f"Loan is {loan.get('state')}, cannot approve")
    loan["state"] = "approved"
    loan["approved_by"] = role or "teacher"
    loan["approved_at"] = now.isoformat()
    loan["collection_deadline"] = end_of_local_day(now).isoformat()
    storage.loans.replace(loans)
    return Loan(**loan)


@app.post("/api/loans/{loan_id}/deny", response_model=Loan)
def deny_loan(
    loan_id: str,
    role: str | None = Depends(require_role("teacher", "admin")),
    storage: Storage = Depends(get_storage),
) -> Loan:
    loans = storage.loans.all()
    loan = _get_loan_or_404(loans, loan_id)
    if loan.get("state") != "requested":
        raise HTTPException(status_code=409, detail=f"Loan is {loan.get('state')}, cannot deny")
    loan["state"] = "denied"
    loan["denied_by"] = role or "teacher"
    loan["closed_reason"] = "denied by teacher"
    storage.loans.replace(loans)
    return Loan(**loan)


@app.post("/api/loans/{loan_id}/issue", response_model=Loan)
def issue_loan(
    loan_id: str,
    payload: IssueIn,
    role: str | None = Depends(require_role("helper", "admin")),
    storage: Storage = Depends(get_storage),
) -> Loan:
    now = settings.now()
    loans = storage.loans.all()
    loan = _get_loan_or_404(loans, loan_id)
    if loan.get("state") != "approved":
        raise HTTPException(status_code=409, detail=f"Loan is {loan.get('state')}, cannot issue")
    if is_request_expired(loan, now):
        raise HTTPException(status_code=409, detail="Approved request has expired (not collected in time)")

    laptops = storage.laptops.all()
    laptop = _get_laptop(laptops, payload.asset_code)
    if laptop is None:
        raise HTTPException(status_code=404, detail=f"Laptop {payload.asset_code} not registered")
    if laptop.get("status") != "available":
        raise HTTPException(
            status_code=409, detail=f"Laptop {payload.asset_code} is {laptop.get('status')}"
        )

    loan["state"] = "issued"
    loan["asset_code"] = payload.asset_code
    loan["issued_by"] = role or "helper"
    loan["issued_at"] = now.isoformat()
    laptop["status"] = "on_loan"
    storage.laptops.replace(laptops)
    storage.loans.replace(loans)
    return Loan(**loan)


@app.post("/api/loans/{loan_id}/return", response_model=Loan)
def return_loan(
    loan_id: str,
    role: str | None = Depends(require_role("helper", "admin")),
    storage: Storage = Depends(get_storage),
) -> Loan:
    now = settings.now()
    loans = storage.loans.all()
    loan = _get_loan_or_404(loans, loan_id)
    if loan.get("state") != "issued":
        raise HTTPException(status_code=409, detail=f"Loan is {loan.get('state')}, cannot return")

    loan["state"] = "returned"
    loan["returned_by"] = role or "helper"
    loan["returned_at"] = now.isoformat()

    laptops = storage.laptops.all()
    laptop = _get_laptop(laptops, loan.get("asset_code"))
    if laptop is not None and laptop.get("status") == "on_loan":
        laptop["status"] = "available"
        storage.laptops.replace(laptops)
    storage.loans.replace(loans)
    return Loan(**loan)


@app.post("/api/loans/{loan_id}/cancel", response_model=Loan)
def cancel_loan(
    loan_id: str,
    role: str | None = Depends(require_role("office", "teacher", "admin")),
    storage: Storage = Depends(get_storage),
) -> Loan:
    loans = storage.loans.all()
    loan = _get_loan_or_404(loans, loan_id)
    if loan.get("state") not in ("requested", "approved"):
        raise HTTPException(status_code=409, detail=f"Loan is {loan.get('state')}, cannot cancel")
    loan["state"] = "cancelled"
    loan["closed_reason"] = "cancelled by staff"
    storage.loans.replace(loans)
    return Loan(**loan)


@app.post("/api/loans/{loan_id}/expire", response_model=Loan)
def expire_loan(
    loan_id: str,
    role: str | None = Depends(require_role("office", "helper", "admin")),
    storage: Storage = Depends(get_storage),
) -> Loan:
    loans = storage.loans.all()
    loan = _get_loan_or_404(loans, loan_id)
    if loan.get("state") != "approved":
        raise HTTPException(status_code=409, detail=f"Loan is {loan.get('state')}, cannot expire")
    loan["state"] = "expired"
    loan["closed_reason"] = "expired manually"
    storage.loans.replace(loans)
    return Loan(**loan)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
