"""Tests for the existing attendance API (health, roster, logs).

These lock in the behaviour and response shapes the dashboard depends on, and
verify the Phase 1 modernisation: timezone-aware timestamps and the storage
abstraction.
"""
from __future__ import annotations

from datetime import datetime, timedelta

SAMPLE_ROSTER = [
    {
        "uid": "AA 11 BB 22",
        "name": "Test Student One",
        "role": "Student",
        "transport": "walk",
        "class_name": "Grade 9 - Z",
        "photo_url": None,
    },
    {
        "uid": "CC 33 DD 44",
        "name": "Test Teacher Two",
        "role": "Teacher",
        "transport": "bus",
        "class_name": "Test Department",
        "photo_url": None,
    },
]


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_roster_roundtrip(client):
    post = client.post("/api/roster", json=SAMPLE_ROSTER)
    assert post.status_code == 200
    assert post.json()["roster"][0]["uid"] == "AA 11 BB 22"

    get = client.get("/api/roster")
    assert get.status_code == 200
    roster = get.json()["roster"]
    assert [p["uid"] for p in roster] == ["AA 11 BB 22", "CC 33 DD 44"]
    assert roster[1]["transport"] == "bus"


def test_roster_rejects_missing_required_field(client):
    bad = [{"uid": "EE 55", "name": "No Role Or Transport"}]
    res = client.post("/api/roster", json=bad)
    assert res.status_code == 422


def test_post_log_looks_up_person_from_roster(client):
    client.post("/api/roster", json=SAMPLE_ROSTER)

    res = client.post(
        "/api/logs",
        json={"uid": "AA 11 BB 22", "status": "accepted", "timestamp": "2026-07-08T07:30:00+05:30"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["event"]["details"]["person"]["name"] == "Test Student One"
    assert body["event"]["status"] == "accepted"


def test_post_log_records_manual_attribution(client):
    res = client.post(
        "/api/logs",
        json={
            "uid": "ZZ 99 ZZ 99",
            "status": "accepted",
            "manual": True,
            "notes": "Forgot card, verified by office",
            "person": {"uid": "ZZ 99 ZZ 99", "name": "Walk In", "role": "Student"},
        },
    )
    assert res.status_code == 200
    details = res.json()["event"]["details"]
    assert details["manual"] is True
    assert details["notes"] == "Forgot card, verified by office"
    assert details["person"]["name"] == "Walk In"


def test_logs_persist_and_list(client):
    client.post("/api/logs", json={"uid": "AA 11 BB 22", "status": "accepted"})
    client.post("/api/logs", json={"uid": "CC 33 DD 44", "status": "late"})

    events = client.get("/api/logs").json()["events"]
    assert len(events) == 2
    assert {e["uid"] for e in events} == {"AA 11 BB 22", "CC 33 DD 44"}


def test_timestamp_is_timezone_aware_ist(client):
    res = client.post("/api/logs", json={"uid": "AA 11 BB 22", "status": "accepted"})
    ts = res.json()["event"]["timestamp"]
    parsed = datetime.fromisoformat(ts)
    assert parsed.tzinfo is not None
    # Default configured timezone is India Standard Time, UTC+5:30.
    assert parsed.utcoffset() == timedelta(minutes=330)


def test_device_supplied_timestamp_is_preserved(client):
    res = client.post(
        "/api/logs",
        json={
            "uid": "AA 11 BB 22",
            "status": "late",
            "timestamp": "2026-07-23T08:10:30+05:30",
            "lateness": {"late": True, "minutes": 5},
        },
    )
    assert res.status_code == 200
    event = res.json()["event"]
    parsed = datetime.fromisoformat(event["timestamp"])
    assert parsed.utcoffset() == timedelta(minutes=330)
    assert parsed.hour == 8 and parsed.minute == 10 and parsed.second == 30
    assert event["details"]["lateness"] == {"late": True, "minutes": 5}


def test_naive_device_timestamp_gets_local_timezone(client):
    res = client.post(
        "/api/logs",
        json={"uid": "AA 11 BB 22", "status": "accepted", "timestamp": "2026-07-23T08:10:30"},
    )
    assert res.status_code == 200
    parsed = datetime.fromisoformat(res.json()["event"]["timestamp"])
    assert parsed.utcoffset() == timedelta(minutes=330)


def test_storage_isolation_between_data_dirs(tmp_path):
    """A store in one dir does not see records written to another dir."""
    from storage import Storage

    a = Storage(tmp_path / "a")
    b = Storage(tmp_path / "b")
    a.ensure_initialised()
    b.ensure_initialised()

    a.logs.append({"uid": "X", "status": "accepted"})
    assert len(a.logs.all()) == 1
    assert b.logs.all() == []
