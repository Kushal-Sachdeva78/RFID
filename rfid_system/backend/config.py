"""Runtime configuration for the RFID attendance backend.

All values come from environment variables with safe defaults so the repository
runs with no setup and no credentials. This module deliberately uses only the
Python standard library.

Timezone note: the deployment is a school in India, and India Standard Time has
no daylight saving, so a fixed UTC+5:30 offset is exactly correct all year. Using
a fixed offset avoids depending on the system timezone database (which is absent
on Windows without the extra tzdata package). Both the offset and the display
name are configurable.
"""
from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

BASE_DIR = pathlib.Path(__file__).resolve().parent


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class LearningCycle:
    """A named date range used for strike tracking (inclusive of both ends)."""

    name: str
    start: date
    end: date

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end


@dataclass(frozen=True)
class Settings:
    data_dir: pathlib.Path
    tz_name: str
    tz_offset_minutes: int
    late_hour: int
    late_minute: int
    learning_cycles: tuple[LearningCycle, ...]
    debounce_seconds: int
    # Maps an API key to a role. Empty means auth is disabled (dev default).
    # Configure with RFID_API_KEYS, a JSON object of {"key": "role"}.
    # Prototype-grade only: a shared header key is not real user authentication.
    api_keys: dict[str, str]

    @property
    def tz(self) -> timezone:
        return timezone(timedelta(minutes=self.tz_offset_minutes), self.tz_name)

    def now(self) -> datetime:
        """Current wall-clock time as a timezone-aware datetime."""
        return datetime.now(self.tz)

    def cycle_for(self, day: date) -> LearningCycle | None:
        """Return the learning cycle containing the given date, or None."""
        for cycle in self.learning_cycles:
            if cycle.contains(day):
                return cycle
        return None


def _default_cycles() -> tuple[LearningCycle, ...]:
    """Learning cycles, overridable with the RFID_LEARNING_CYCLES env var.

    The default is the real cycle supplied by the project owner: 08 Jul 2026 to
    15 Oct 2026. Override with a JSON array, for example:
    RFID_LEARNING_CYCLES='[{"name":"Cycle 1","start":"2026-07-08","end":"2026-10-15"}]'
    """
    raw = os.environ.get("RFID_LEARNING_CYCLES")
    if raw:
        parsed = json.loads(raw)
        return tuple(
            LearningCycle(
                name=str(entry["name"]),
                start=date.fromisoformat(entry["start"]),
                end=date.fromisoformat(entry["end"]),
            )
            for entry in parsed
        )
    return (
        LearningCycle(
            name="Cycle 1 (2026)",
            start=date(2026, 7, 8),
            end=date(2026, 10, 15),
        ),
    )


def _load_api_keys() -> dict[str, str]:
    raw = os.environ.get("RFID_API_KEYS")
    if not raw:
        return {}
    parsed = json.loads(raw)
    return {str(key): str(role) for key, role in parsed.items()}


def load_settings() -> Settings:
    data_dir_raw = os.environ.get("RFID_DATA_DIR")
    data_dir = pathlib.Path(data_dir_raw) if data_dir_raw else (BASE_DIR / "data")
    return Settings(
        data_dir=data_dir,
        tz_name=os.environ.get("RFID_TZ_NAME", "Asia/Kolkata"),
        tz_offset_minutes=_env_int("RFID_TZ_OFFSET_MINUTES", 330),
        late_hour=_env_int("RFID_LATE_HOUR", 8),
        late_minute=_env_int("RFID_LATE_MINUTE", 5),
        learning_cycles=_default_cycles(),
        debounce_seconds=_env_int("RFID_SCAN_DEBOUNCE_SECONDS", 60),
        api_keys=_load_api_keys(),
    )


settings = load_settings()
