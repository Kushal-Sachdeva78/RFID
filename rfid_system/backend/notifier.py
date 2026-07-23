"""Pluggable teacher notification for the three-strike rule.

The default backend writes to a file and stdout, so the repository needs no
credentials to run. An SMTP backend is available and is configured purely from
environment variables, so no secrets are ever committed. Tests use FakeNotifier.

Select the backend with RFID_NOTIFIER: "log" (default), "smtp", or "none".
"""
from __future__ import annotations

import os
import pathlib
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Protocol


@dataclass
class StrikeNotification:
    student_name: str
    student_uid: str
    class_section: str | None
    cycle_name: str
    strike_count: int
    late_dates: list[str]
    teacher_name: str | None
    teacher_email: str | None
    created_at: datetime

    def subject(self) -> str:
        return f"Attendance alert: {self.student_name} has {self.strike_count} late arrivals"

    def body(self) -> str:
        who = self.student_name
        if self.class_section:
            who += f" ({self.class_section})"
        lines = [
            f"{who} has reached {self.strike_count} late arrivals in {self.cycle_name}.",
            "",
            "Late arrival dates:",
            *[f"  - {d}" for d in self.late_dates],
            "",
            f"UID: {self.student_uid}",
        ]
        if self.teacher_name:
            lines.insert(0, f"To: {self.teacher_name}")
        return "\n".join(lines)


class Notifier(Protocol):
    def notify(self, notification: StrikeNotification) -> None:
        ...


class LogNotifier:
    """Default backend: append to a file and print. No credentials required."""

    def __init__(self, path: pathlib.Path | str) -> None:
        self._path = pathlib.Path(path)

    def notify(self, notification: StrikeNotification) -> None:
        block = (
            f"[{notification.created_at.isoformat()}] "
            f"{notification.subject()}\n{notification.body()}\n"
            + ("-" * 60)
            + "\n"
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(block)
        print(block, flush=True)


class SmtpNotifier:
    """SMTP backend configured entirely from environment variables."""

    def __init__(self) -> None:
        self.host = os.environ.get("SMTP_HOST", "")
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")
        self.sender = os.environ.get("SMTP_FROM", self.user)
        self.use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() != "false"

    def notify(self, notification: StrikeNotification) -> None:
        if not self.host or not notification.teacher_email:
            # Nothing to send to, or SMTP not configured. Do not raise; a missing
            # notifier must never break attendance recording.
            return
        message = EmailMessage()
        message["Subject"] = notification.subject()
        message["From"] = self.sender
        message["To"] = notification.teacher_email
        message.set_content(notification.body())
        with smtplib.SMTP(self.host, self.port) as server:
            if self.use_tls:
                server.starttls()
            if self.user:
                server.login(self.user, self.password)
            server.send_message(message)


class NullNotifier:
    def notify(self, notification: StrikeNotification) -> None:
        return


class FakeNotifier:
    """Records notifications in memory for tests."""

    def __init__(self) -> None:
        self.sent: list[StrikeNotification] = []

    def notify(self, notification: StrikeNotification) -> None:
        self.sent.append(notification)


def build_notifier() -> Notifier:
    import config

    backend = os.environ.get("RFID_NOTIFIER", "log").strip().lower()
    if backend == "smtp":
        return SmtpNotifier()
    if backend == "none":
        return NullNotifier()
    return LogNotifier(config.settings.data_dir / "notifications.log")


_notifier: Notifier | None = None


def get_notifier() -> Notifier:
    """Dependency returning a shared notifier. Overridable in tests."""
    global _notifier
    if _notifier is None:
        _notifier = build_notifier()
    return _notifier
