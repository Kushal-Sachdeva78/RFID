"""Phase 4 tests: second-resolution lateness and three-strike notification."""
from __future__ import annotations


def _entry(client, uid, ts, transport="walk", name="Student"):
    return client.post(
        "/api/logs",
        json={
            "uid": uid,
            "status": "accepted",
            "timestamp": ts,
            "person": {"uid": uid, "name": name, "transport": transport},
        },
    )


def test_walk_student_after_cutoff_is_late(client):
    res = _entry(client, "W1 W1", "2026-07-08T08:10:30+05:30")
    body = res.json()
    assert body["event"]["status"] == "late"
    assert body["event"]["details"]["lateness"] == {"late": True, "minutes": 5}


def test_arrival_before_cutoff_is_on_time(client):
    res = _entry(client, "O1 O1", "2026-07-08T07:50:00+05:30")
    assert res.json()["event"]["status"] == "accepted"
    assert res.json()["event"]["details"]["lateness"]["late"] is False


def test_one_second_past_cutoff_is_late(client):
    res = _entry(client, "S1 S1", "2026-07-08T08:05:01+05:30")
    assert res.json()["event"]["status"] == "late"


def test_bus_rider_is_exempt_from_lateness(client):
    res = _entry(client, "B1 B1", "2026-07-08T08:30:00+05:30", transport="bus")
    body = res.json()
    assert body["event"]["status"] == "accepted"
    assert body["event"]["details"]["lateness"]["late"] is False


def _seed_strike_student(storage):
    storage.roster.replace(
        [
            {
                "uid": "LS LS",
                "name": "Late Student",
                "role": "Student",
                "transport": "walk",
                "class_name": "Grade 10 - A",
            }
        ]
    )
    storage.class_teachers.replace(
        [
            {
                "class_section": "Grade 10 - A",
                "teacher_name": "Teacher Charlie",
                "teacher_email": "grade10a.teacher@example.com",
            }
        ]
    )


def test_third_late_arrival_notifies_class_teacher(client, storage, fake_notifier):
    _seed_strike_student(storage)
    for day in ["08", "09", "10"]:
        res = client.post(
            "/api/logs",
            json={"uid": "LS LS", "status": "accepted", "timestamp": f"2026-07-{day}T08:10:00+05:30"},
        )
        assert res.json()["event"]["status"] == "late"

    assert len(fake_notifier.sent) == 1
    note = fake_notifier.sent[0]
    assert note.strike_count == 3
    assert note.student_name == "Late Student"
    assert note.class_section == "Grade 10 - A"
    assert note.teacher_email == "grade10a.teacher@example.com"
    assert note.cycle_name == "Cycle 1 (2026)"
    assert note.late_dates == ["2026-07-08", "2026-07-09", "2026-07-10"]


def test_two_late_arrivals_do_not_notify(client, storage, fake_notifier):
    _seed_strike_student(storage)
    for day in ["08", "09"]:
        client.post(
            "/api/logs",
            json={"uid": "LS LS", "status": "accepted", "timestamp": f"2026-07-{day}T08:10:00+05:30"},
        )
    assert fake_notifier.sent == []


def test_late_days_in_cycle_dedupes_same_day():
    """A strike is a late day: two late entries on one date count once."""
    from datetime import datetime

    from services import late_days_in_cycle

    events = [
        {"uid": "X", "status": "late", "direction": "entry", "timestamp": "2026-07-08T08:10:00+05:30"},
        {"uid": "X", "status": "late", "direction": "entry", "timestamp": "2026-07-08T08:40:00+05:30"},
        {"uid": "X", "status": "late", "direction": "entry", "timestamp": "2026-07-09T08:10:00+05:30"},
    ]
    when = datetime.fromisoformat("2026-07-09T08:10:00+05:30")
    count, cycle, dates = late_days_in_cycle(events, "X", when)
    assert count == 2
    assert dates == ["2026-07-08", "2026-07-09"]


def test_late_outside_any_cycle_never_strikes(client, storage, fake_notifier):
    _seed_strike_student(storage)
    # June 2026 is before the configured cycle (08 Jul to 15 Oct).
    for day in ["01", "02", "03"]:
        res = client.post(
            "/api/logs",
            json={"uid": "LS LS", "status": "accepted", "timestamp": f"2026-06-{day}T08:10:00+05:30"},
        )
        assert res.json()["event"]["status"] == "late"
    assert fake_notifier.sent == []
