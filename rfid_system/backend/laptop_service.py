"""Laptop borrowing state machine helpers (pure, unit tested).

Loan lifecycle:
    requested -> approved -> issued -> returned
    requested -> denied
    approved  -> expired      (collection deadline passed)
    requested/approved -> cancelled

Laptop asset lifecycle:
    available <-> on_loan            (issue / return)
    available -> under_repair -> available
    any -> retired                   (not reissuable)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from config import settings

# Loan states that count against a student's concurrent-loan limit.
ACTIVE_LOAN_STATES = {"requested", "approved", "issued"}
# Terminal states.
CLOSED_LOAN_STATES = {"denied", "returned", "expired", "cancelled"}
# Laptop statuses a helper may set via PATCH.
SETTABLE_LAPTOP_STATUSES = {"available", "under_repair", "retired"}


def _as_aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=settings.tz) if dt.tzinfo is None else dt


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _as_aware(value)
    try:
        return _as_aware(datetime.fromisoformat(str(value)))
    except (ValueError, TypeError):
        return None


def end_of_local_day(dt: datetime) -> datetime:
    """Collection deadline: end of the local day the request was approved."""
    local = _as_aware(dt).astimezone(settings.tz)
    return local.replace(hour=23, minute=59, second=59, microsecond=0)


def is_request_expired(loan: dict[str, Any], now: datetime) -> bool:
    """True when an approved but uncollected request is past its deadline."""
    if loan.get("state") != "approved":
        return False
    deadline = _parse(loan.get("collection_deadline"))
    if deadline is None:
        return False
    return _as_aware(now) > deadline


def held_seconds(loan: dict[str, Any], now: datetime) -> int | None:
    """Seconds a currently issued unit has been held, or None if not issued."""
    if loan.get("state") != "issued":
        return None
    issued_at = _parse(loan.get("issued_at"))
    if issued_at is None:
        return None
    return int((_as_aware(now) - issued_at).total_seconds())


def format_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    seconds = max(0, seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def active_loans_for(loans: list[dict[str, Any]], student_uid: str, now: datetime) -> list[dict[str, Any]]:
    """Loans that still occupy one of the student's concurrent-loan slots.

    An approved request that has already expired does not count.
    """
    result = []
    for loan in loans:
        if loan.get("student_uid") != student_uid:
            continue
        if loan.get("state") not in ACTIVE_LOAN_STATES:
            continue
        if is_request_expired(loan, now):
            continue
        result.append(loan)
    return result
