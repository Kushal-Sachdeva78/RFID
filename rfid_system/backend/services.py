"""Domain logic that is worth unit testing on its own.

Keeping direction and authorization here (rather than in route handlers or in
firmware) means the ESP32 stays thin and this logic is directly testable.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from config import settings

# Transport modes and the message shown to the gate guard on exit.
TRANSPORT_AUTHORIZATION = {
    "walk": "Authorised to walk home",
    "car": "Authorised to go by car",
    "bus": "Authorised to take the bus",
}


def authorization_for(transport: str | None) -> str:
    if not transport:
        return "Transport not on record"
    return TRANSPORT_AUTHORIZATION.get(transport.strip().lower(), f"Transport: {transport}")


def _as_aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=settings.tz) if dt.tzinfo is None else dt


def _local_date(dt: datetime) -> date:
    return _as_aware(dt).astimezone(settings.tz).date()


def compute_lateness(timestamp: datetime, transport: str | None) -> tuple[bool, int]:
    """Return (is_late, minutes_late) against the configured cutoff.

    Second resolution: an arrival one second past the cutoff is late. Bus riders
    are exempt because the bus arrival time is not their fault.
    """
    if transport and transport.strip().lower() == "bus":
        return False, 0
    local = _as_aware(timestamp).astimezone(settings.tz)
    cutoff_seconds = settings.late_hour * 3600 + settings.late_minute * 60
    now_seconds = local.hour * 3600 + local.minute * 60 + local.second
    if now_seconds > cutoff_seconds:
        return True, (now_seconds - cutoff_seconds) // 60
    return False, 0


def late_days_in_cycle(
    events: list[dict[str, Any]], uid: str, when: datetime
):
    """Count distinct late arrival days for a student in the cycle of `when`.

    Returns (count, cycle, sorted_dates). A strike is a late day, so multiple
    late reads on one date count once.
    """
    cycle = settings.cycle_for(_local_date(_as_aware(when)))
    if cycle is None:
        return 0, None, []

    late_dates: set[str] = set()
    for event in events:
        if event.get("uid") != uid:
            continue
        if event.get("status") != "late":
            continue
        if (event.get("direction") or "entry") != "entry":
            continue
        raw_ts = event.get("timestamp")
        if not raw_ts:
            continue
        try:
            event_dt = _as_aware(datetime.fromisoformat(raw_ts))
        except (ValueError, TypeError):
            continue
        day = _local_date(event_dt)
        if cycle.contains(day):
            late_dates.add(day.isoformat())

    return len(late_dates), cycle, sorted(late_dates)


def classify_direction(
    prior_events: list[dict[str, Any]], uid: str, timestamp: datetime
) -> tuple[str, bool]:
    """Decide entry vs exit for a single reader using a per-day toggle.

    Returns (direction, is_duplicate). The first tap of the local day is an
    entry; each later tap alternates. A tap within the debounce window of the
    previous tap is treated as a duplicate (an accidental double read) and does
    not toggle the direction.
    """
    timestamp = _as_aware(timestamp)
    today = _local_date(timestamp)

    todays: list[tuple[datetime, dict[str, Any]]] = []
    for event in prior_events:
        if event.get("uid") != uid:
            continue
        raw_ts = event.get("timestamp")
        if not raw_ts:
            continue
        try:
            event_dt = _as_aware(datetime.fromisoformat(raw_ts))
        except (ValueError, TypeError):
            continue
        if _local_date(event_dt) == today:
            todays.append((event_dt, event))

    if not todays:
        return "entry", False

    todays.sort(key=lambda pair: pair[0])
    last_dt, last_event = todays[-1]
    last_direction = last_event.get("direction") or "entry"

    if abs((timestamp - last_dt).total_seconds()) < settings.debounce_seconds:
        return last_direction, True

    next_direction = "exit" if last_direction == "entry" else "entry"
    return next_direction, False
