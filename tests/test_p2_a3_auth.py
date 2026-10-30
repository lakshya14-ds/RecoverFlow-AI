"""P2 A3: login throttling, session rotation/revocation, admin-issued recovery,
and admin-only payment posting. Isolated database; the live app is untouched.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app

ADMIN = {"X-RECOVERFLOW-API-KEY": "a3-admin"}


@pytest.fixture()
def authdb(monkeypatch, tmp_path):
    db_path = tmp_path / "a3.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "a3-admin")
    db_manager.init_db()
    client = TestClient(app)
    for email, name, role in (("ed@example.in", "Ed", "editor"),
                              ("ed2@example.in", "Ed Two", "editor"),
                              ("vw@example.in", "Vw", "viewer")):
        created = client.post("/api/v1/auth/users", headers=ADMIN, json={
            "email": email, "name": name, "password": "StaffPass1!",
            "role": role})
        assert created.status_code == 201, created.text
    yield {"client": client,
           "factory": sessionmaker(bind=engine), "engine": engine}
    engine.dispose()


def _login(client, email, password):
    return client.post("/api/v1/auth/login",
                       json={"email": email, "password": password})


def test_login_throttle_and_window_expiry(authdb):
    client = authdb["client"]
    for _ in range(5):
        assert _login(client, "ed@example.in", "WrongPass1!").status_code == 401
    assert _login(client, "ed@example.in", "WrongPass1!").status_code == 429
    assert _login(client, "ed@example.in", "StaffPass1!").status_code == 429
    assert _login(client, "other@example.in", "WrongPass1!").status_code == 401
    with authdb["factory"]() as db:
        for row in db.query(models.LoginAttempt).all():
            row.created_at = row.created_at - timedelta(minutes=16)
        db.commit()
    assert _login(client, "ed@example.in", "StaffPass1!").status_code == 200


def test_ip_throttle_across_emails(authdb):
    client = authdb["client"]
    for index in range(20):
        res = _login(client, f"ghost{index}@example.in", "WrongPass1!")
        assert res.status_code == 401
    assert _login(client, "ghost20@example.in", "WrongPass1!").status_code == 429


def test_rotate_session(authdb):
    client = authdb["client"]
    old = _login(client, "ed@example.in", "StaffPass1!").json()["token"]
    rotated = client.post("/api/v1/auth/rotate",
                          headers={"Authorization": f"Bearer {old}"})
    assert rotated.status_code == 200, rotated.text
    new = rotated.json()["token"]
    assert new != old
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {new}"}).status_code == 200
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.post("/api/v1/auth/rotate", headers=ADMIN).status_code == 409


def test_sessions_list_and_revoke(authdb):
    client = authdb["client"]
    first = _login(client, "ed@example.in", "StaffPass1!").json()["token"]
    second = _login(client, "ed@example.in", "StaffPass1!").json()["token"]
    listed = client.get("/api/v1/auth/sessions",
                        headers={"Authorization": f"Bearer {second}"}).json()
    assert len(listed) == 2
    assert sum(1 for row in listed if row["current"]) == 1
    assert first not in str(listed) and second not in str(listed)
    other = next(row for row in listed if not row["current"])
    revoked = client.delete(f"/api/v1/auth/sessions/{other['id']}",
                            headers={"Authorization": f"Bearer {second}"})
    assert revoked.status_code == 200
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {first}"}).status_code == 401
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {second}"}).status_code == 200
    foreign = _login(client, "ed2@example.in", "StaffPass1!").json()["token"]
    foreign_id = client.get(
        "/api/v1/auth/sessions",
        headers={"Authorization": f"Bearer {foreign}"}).json()[0]["id"]
    assert client.delete(f"/api/v1/auth/sessions/{foreign_id}",
                         headers={"Authorization": f"Bearer {second}"}).status_code == 404
    assert client.delete("/api/v1/auth/sessions/999999",
                         headers={"Authorization": f"Bearer {second}"}).status_code == 404


def test_revoke_all_sessions(authdb):
    client = authdb["client"]
    tokens = [_login(client, "ed@example.in", "StaffPass1!").json()["token"]
              for _ in range(2)]
    res = client.post("/api/v1/auth/revoke-all",
                      headers={"Authorization": f"Bearer {tokens[0]}"})
    assert res.json() == {"status": "revoked_all", "count": 2}
    for token in tokens:
        assert client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_recovery_flow(authdb):
    client = authdb["client"]
    users = {row["email"]: row["id"] for row in
             client.get("/api/v1/auth/users", headers=ADMIN).json()}
    issued = client.post(f"/api/v1/auth/users/{users['ed@example.in']}/recovery",
                         headers=ADMIN)
    assert issued.status_code == 201, issued.text
    token = issued.json()["recovery_token"]
    assert token.startswith("rfr_")
    with authdb["factory"]() as db:
        stored = db.query(models.UserRecoveryToken).one()
        assert stored.token_hash != token
    before = _login(client, "ed@example.in", "StaffPass1!").json()["token"]
    done = client.post("/api/v1/auth/recover",
                       json={"token": token, "new_password": "BrandNewPass2!"})
    assert done.status_code == 200, done.text
    assert _login(client, "ed@example.in", "BrandNewPass2!").status_code == 200
    assert _login(client, "ed@example.in", "StaffPass1!").status_code == 401
    assert client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {before}"}).status_code == 401
    reuse = client.post("/api/v1/auth/recover",
                        json={"token": token, "new_password": "AnotherPass3!"})
    assert reuse.status_code == 422
    with authdb["factory"]() as db:
        foreign = models.User(tenant_id="tenant-b", email="b@example.in",
                              name="B", password_hash="x", role="editor")
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    assert client.post(f"/api/v1/auth/users/{foreign_id}/recovery",
                       headers=ADMIN).status_code == 404


def test_recovery_token_expiry(authdb):
    client = authdb["client"]
    users = {row["email"]: row["id"] for row in
             client.get("/api/v1/auth/users", headers=ADMIN).json()}
    token = client.post(
        f"/api/v1/auth/users/{users['ed@example.in']}/recovery",
        headers=ADMIN).json()["recovery_token"]
    with authdb["factory"]() as db:
        row = db.query(models.UserRecoveryToken).one()
        row.expires_at = row.expires_at - timedelta(hours=2)
        db.commit()
    res = client.post("/api/v1/auth/recover",
                      json={"token": token, "new_password": "BrandNewPass2!"})
    assert res.status_code == 422


def _invoice_id(authdb):
    with authdb["factory"]() as db:
        row = models.Invoice(
            tenant_id="local", invoice_number="A3-1", invoice_type="AR",
            counterparty_name="A3 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR")
        db.add(row)
        db.commit()
        return row.id


def test_payment_endpoints_require_admin(authdb):
    client = authdb["client"]
    invoice_id = _invoice_id(authdb)
    editor = {"Authorization": f"Bearer {_login(client, 'ed@example.in', 'StaffPass1!').json()['token']}"}
    viewer = {"Authorization": f"Bearer {_login(client, 'vw@example.in', 'StaffPass1!').json()['token']}"}
    entry = {"kind": "payment", "amount": "10.00", "reference": "a3e1",
             "currency": "INR"}
    assert client.post(f"/api/v1/cases/{invoice_id}/entries", headers=editor,
                       json=entry).status_code == 403
    assert client.post(f"/api/v1/cases/{invoice_id}/entries", headers=viewer,
                       json=entry).status_code == 403
    created = client.post(f"/api/v1/cases/{invoice_id}/entries", headers=ADMIN,
                          json=entry)
    assert created.status_code == 201, created.text
    with authdb["factory"]() as db:
        db.add(models.AllocationProposal(
            tenant_id="local", afis_transaction_id="A3-T1", transfer_cents=100,
            currency="INR", created_by="a3-test"))
        db.add(models.Reconciliation(
            tenant_id="local", invoice_id=invoice_id, afis_transaction_id=77,
            match_type="exact", confidence_score=1.0,
            matched_amount=Decimal("10.00")))
        db.add(models.IntakeUpload(
            id="a3-upload", tenant_id="local", actor="a3-test",
            filename="r.pdf", mime_type="application/pdf",
            source_path="r.pdf", size_bytes=8))
        db.commit()
        proposal_id = db.query(models.AllocationProposal).one().id
        recon_id = db.query(models.Reconciliation).one().id
    assert client.post(f"/api/v1/allocations/proposals/{proposal_id}/approve",
                       headers=editor, json={"legs": []}).status_code == 403
    assert client.post(f"/api/v1/reconciliation/{recon_id}/approve",
                       headers=editor).status_code == 403
    assert client.post("/api/v1/intake/uploads/a3-upload/confirm-receipt",
                       headers=editor).status_code == 403


def test_viewer_read_only_and_api_key_sessions(authdb):
    client = authdb["client"]
    invoice_id = _invoice_id(authdb)
    viewer = {"Authorization": f"Bearer {_login(client, 'vw@example.in', 'StaffPass1!').json()['token']}"}
    assert client.get(f"/api/v1/cases/{invoice_id}",
                      headers=viewer).status_code == 200
    assert client.post(f"/api/v1/cases/{invoice_id}/replies", headers=viewer,
                       json={"category": "other", "body": "hi"}).status_code == 403
    assert client.get("/api/v1/auth/sessions", headers=ADMIN).status_code == 409
    assert client.post("/api/v1/auth/revoke-all", headers=ADMIN).status_code == 409
