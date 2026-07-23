"""Phase 5 tests: laptop borrowing state machine, concurrency, expiry, roles."""
from __future__ import annotations


def _register(client, code, **kw):
    return client.post("/api/laptops", json={"asset_code": code, **kw})


def _request(client, uid, name=None):
    body = {"student_uid": uid}
    if name:
        body["student_name"] = name
    return client.post("/api/loans/request", json=body)


def _approve(client, loan_id):
    return client.post(f"/api/loans/{loan_id}/approve")


def _issue(client, loan_id, code):
    return client.post(f"/api/loans/{loan_id}/issue", json={"asset_code": code})


# --- Happy path ----------------------------------------------------------------


def test_full_borrow_flow(client):
    assert _register(client, "LAP-001").status_code == 201

    req = _request(client, "STU 1", "Student One")
    assert req.status_code == 201
    loan_id = req.json()["id"]
    assert req.json()["state"] == "requested"
    assert req.json()["student_name"] == "Student One"

    approved = _approve(client, loan_id)
    assert approved.status_code == 200
    assert approved.json()["state"] == "approved"
    assert approved.json()["collection_deadline"] is not None

    issued = _issue(client, loan_id, "LAP-001")
    assert issued.status_code == 200
    assert issued.json()["state"] == "issued"
    assert issued.json()["asset_code"] == "LAP-001"

    laptops = client.get("/api/laptops").json()["laptops"]
    assert laptops[0]["status"] == "on_loan"

    outstanding = client.get("/api/loans/outstanding").json()["outstanding"]
    assert len(outstanding) == 1
    assert outstanding[0]["asset_code"] == "LAP-001"
    assert outstanding[0]["student_uid"] == "STU 1"
    assert outstanding[0]["held_for"] is not None

    returned = client.post(f"/api/loans/{loan_id}/return")
    assert returned.status_code == 200
    assert returned.json()["state"] == "returned"

    laptops = client.get("/api/laptops").json()["laptops"]
    assert laptops[0]["status"] == "available"
    assert client.get("/api/loans/outstanding").json()["outstanding"] == []


def test_request_fills_name_from_roster(client):
    client.post(
        "/api/roster",
        json=[{"uid": "R7 R7", "name": "Roster Name", "role": "Student", "transport": "walk"}],
    )
    req = _request(client, "R7 R7")
    assert req.json()["student_name"] == "Roster Name"


def test_unit_reissued_after_return(client):
    _register(client, "LAP-9")
    first = _request(client, "A A").json()["id"]
    _approve(client, first)
    _issue(client, first, "LAP-9")
    client.post(f"/api/loans/{first}/return")

    second = _request(client, "B B").json()["id"]
    _approve(client, second)
    again = _issue(client, second, "LAP-9")
    assert again.status_code == 200
    assert again.json()["state"] == "issued"


# --- Concurrency and asset rules -----------------------------------------------


def test_one_active_loan_per_student(client):
    assert _request(client, "STU 2").status_code == 201
    assert _request(client, "STU 2").status_code == 409


def test_duplicate_laptop_rejected(client):
    assert _register(client, "DUP").status_code == 201
    assert _register(client, "DUP").status_code == 409


def test_issue_unknown_laptop_404(client):
    loan_id = _request(client, "C C").json()["id"]
    _approve(client, loan_id)
    assert _issue(client, loan_id, "NOPE").status_code == 404


def test_issue_unavailable_laptop_409(client):
    _register(client, "L1")
    a = _request(client, "A A").json()["id"]
    _approve(client, a)
    _issue(client, a, "L1")

    b = _request(client, "B B").json()["id"]
    _approve(client, b)
    assert _issue(client, b, "L1").status_code == 409


def test_retire_and_repair_laptop(client):
    _register(client, "L5")
    repair = client.patch("/api/laptops/L5", json={"status": "under_repair"})
    assert repair.status_code == 200 and repair.json()["status"] == "under_repair"
    retire = client.patch("/api/laptops/L5", json={"status": "retired"})
    assert retire.json()["status"] == "retired"


def test_cannot_change_status_of_on_loan_unit(client):
    _register(client, "L6")
    loan_id = _request(client, "Z Z").json()["id"]
    _approve(client, loan_id)
    _issue(client, loan_id, "L6")
    assert client.patch("/api/laptops/L6", json={"status": "retired"}).status_code == 409


# --- Invalid transitions -------------------------------------------------------


def test_cannot_approve_twice(client):
    loan_id = _request(client, "D D").json()["id"]
    _approve(client, loan_id)
    assert _approve(client, loan_id).status_code == 409


def test_cannot_issue_unapproved(client):
    _register(client, "X1")
    loan_id = _request(client, "E E").json()["id"]
    assert _issue(client, loan_id, "X1").status_code == 409


def test_deny_and_cancel(client):
    denied = _request(client, "F F").json()["id"]
    assert client.post(f"/api/loans/{denied}/deny").json()["state"] == "denied"

    to_cancel = _request(client, "G G").json()["id"]
    _approve(client, to_cancel)
    assert client.post(f"/api/loans/{to_cancel}/cancel").json()["state"] == "cancelled"


# --- Expiry (uncollected approved request) -------------------------------------


def _inject_stale_approved(storage, uid):
    storage.loans.replace(
        [
            {
                "id": "stale1",
                "student_uid": uid,
                "student_name": "Stale",
                "state": "approved",
                "requested_at": "2026-07-08T09:00:00+05:30",
                "approved_by": "teacher",
                "approved_at": "2026-07-08T09:05:00+05:30",
                "collection_deadline": "2026-07-08T23:59:59+05:30",
            }
        ]
    )


def test_uncollected_request_lazily_expires(client, storage):
    _inject_stale_approved(storage, "H H")
    loans = client.get("/api/loans").json()["loans"]
    assert loans[0]["state"] == "expired"


def test_expired_request_frees_the_slot(client, storage):
    _inject_stale_approved(storage, "H H")
    # A new request succeeds because the stale approval no longer counts.
    assert _request(client, "H H").status_code == 201


def test_cannot_issue_expired_request(client, storage):
    _register(client, "EX1")
    _inject_stale_approved(storage, "H H")
    assert _issue(client, "stale1", "EX1").status_code == 409


def test_manual_expire_endpoint(client):
    loan_id = _request(client, "I I").json()["id"]
    _approve(client, loan_id)
    assert client.post(f"/api/loans/{loan_id}/expire").json()["state"] == "expired"


# --- Permission paths ----------------------------------------------------------


def test_register_laptop_requires_helper(client, api_keys):
    assert client.post("/api/laptops", json={"asset_code": "P1"}).status_code == 401
    assert (
        client.post("/api/laptops", json={"asset_code": "P1"}, headers={"X-API-Key": "office-key"}).status_code
        == 403
    )
    assert (
        client.post("/api/laptops", json={"asset_code": "P1"}, headers={"X-API-Key": "helper-key"}).status_code
        == 201
    )


def test_approve_requires_teacher(client, api_keys):
    loan_id = _request(client, "J J").json()["id"]  # requesting is open
    assert client.post(f"/api/loans/{loan_id}/approve").status_code == 401
    assert (
        client.post(f"/api/loans/{loan_id}/approve", headers={"X-API-Key": "guard-key"}).status_code == 403
    )
    assert (
        client.post(f"/api/loans/{loan_id}/approve", headers={"X-API-Key": "teacher-key"}).status_code == 200
    )


def test_issue_requires_helper(client, api_keys):
    client.post("/api/laptops", json={"asset_code": "H1"}, headers={"X-API-Key": "helper-key"})
    loan_id = _request(client, "K K").json()["id"]
    client.post(f"/api/loans/{loan_id}/approve", headers={"X-API-Key": "teacher-key"})
    assert _issue(client, loan_id, "H1").status_code == 401
    assert (
        client.post(
            f"/api/loans/{loan_id}/issue",
            json={"asset_code": "H1"},
            headers={"X-API-Key": "teacher-key"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/loans/{loan_id}/issue",
            json={"asset_code": "H1"},
            headers={"X-API-Key": "helper-key"},
        ).status_code
        == 200
    )
