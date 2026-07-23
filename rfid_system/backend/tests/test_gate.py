"""Phase 3 tests: entry/exit direction, exit authorization, manual fallback, auth."""
from __future__ import annotations

CAR_STUDENT = [{"uid": "D1 D1", "name": "Car Rider", "role": "Student", "transport": "car"}]


def _tap(client, uid, ts, status="accepted"):
    return client.post(
        "/api/logs", json={"uid": uid, "status": status, "timestamp": ts}
    )


def test_first_tap_is_entry(client):
    res = _tap(client, "D9 D9", "2026-07-23T08:00:00+05:30")
    assert res.status_code == 200
    assert res.json()["direction"] == "entry"
    assert res.headers["X-Direction"] == "entry"


def test_direction_toggles_entry_then_exit(client):
    client.post("/api/roster", json=CAR_STUDENT)
    entry = _tap(client, "D1 D1", "2026-07-23T08:00:00+05:30")
    assert entry.json()["direction"] == "entry"

    exit_ = _tap(client, "D1 D1", "2026-07-23T14:00:00+05:30")
    body = exit_.json()
    assert body["direction"] == "exit"
    assert body["transport"] == "car"
    assert body["authorization"] == "Authorised to go by car"
    assert exit_.headers["X-Direction"] == "exit"
    assert exit_.headers["X-Transport-Authorization"] == "Authorised to go by car"


def test_third_tap_toggles_back_to_entry(client):
    expected = ["entry", "exit", "entry"]
    for ts, want in zip(["08:00", "14:00", "15:30"], expected):
        res = _tap(client, "D3 D3", f"2026-07-23T{ts}:00+05:30")
        assert res.json()["direction"] == want


def test_rapid_second_tap_is_duplicate(client):
    first = _tap(client, "D2 D2", "2026-07-23T08:00:00+05:30")
    assert first.json()["direction"] == "entry"

    second = _tap(client, "D2 D2", "2026-07-23T08:00:30+05:30")
    body = second.json()
    assert body["event"]["status"] == "duplicate"
    assert body["direction"] == "entry"  # not toggled by an accidental double read


def test_rejected_card_has_no_direction(client):
    res = client.post("/api/logs", json={"uid": "FF FF FF", "status": "rejected"})
    assert res.json()["direction"] is None
    assert res.json()["event"]["direction"] is None
    assert res.headers["X-Direction"] == ""


def test_entry_has_no_authorization(client):
    client.post("/api/roster", json=CAR_STUDENT)
    res = _tap(client, "D1 D1", "2026-07-23T08:00:00+05:30")
    assert res.json()["authorization"] is None


# --- Manual fallback and role auth ---------------------------------------------


def test_manual_entry_open_and_attributed_when_no_keys(client):
    res = client.post(
        "/api/manual-entry",
        json={"uid": "M1 M1", "status": "accepted", "person": {"uid": "M1 M1", "name": "Walk In"}},
    )
    assert res.status_code == 200
    details = res.json()["event"]["details"]
    assert details["manual"] is True
    assert details["recorded_by"] == "staff"


def test_manual_entry_requires_key_when_configured(client, api_keys):
    no_key = client.post("/api/manual-entry", json={"uid": "M2 M2", "status": "accepted"})
    assert no_key.status_code == 401

    wrong_role = client.post(
        "/api/manual-entry",
        json={"uid": "M2 M2", "status": "accepted"},
        headers={"X-API-Key": "guard-key"},
    )
    assert wrong_role.status_code == 403

    ok = client.post(
        "/api/manual-entry",
        json={"uid": "M2 M2", "status": "accepted"},
        headers={"X-API-Key": "office-key"},
    )
    assert ok.status_code == 200
    assert ok.json()["event"]["details"]["recorded_by"] == "office"


def test_manual_recorded_by_is_preserved(client, api_keys):
    res = client.post(
        "/api/manual-entry",
        json={"uid": "M3 M3", "status": "accepted", "recorded_by": "Front Office Desk"},
        headers={"X-API-Key": "teacher-key"},
    )
    assert res.json()["event"]["details"]["recorded_by"] == "Front Office Desk"


def test_roster_write_requires_key_when_configured(client, api_keys):
    person = [{"uid": "R1 R1", "name": "N", "role": "Student", "transport": "walk"}]
    denied = client.post("/api/roster", json=person)
    assert denied.status_code == 401

    allowed = client.post("/api/roster", json=person, headers={"X-API-Key": "admin-key"})
    assert allowed.status_code == 200
