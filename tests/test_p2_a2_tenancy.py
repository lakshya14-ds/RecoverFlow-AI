"""P2 A2: tenant isolation — cross-tenant negatives, per-tenant secrets and
webhooks, per-tenant AFIS files, and private evidence files.

Two businesses share one isolated database: `local` and `tenant-b`. Every
lookup must enforce business identity; secrets must never leak.
"""
import hashlib
import hmac
import json
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app

LOCAL = {"X-RECOVERFLOW-API-KEY": "a2-local-admin"}
B_ADMIN = {"X-RECOVERFLOW-API-KEY": "a2-b-admin"}
VIEWER = {"X-RECOVERFLOW-API-KEY": "a2-viewer"}


@pytest.fixture()
def two_tenant(monkeypatch, tmp_path):
    db_path = tmp_path / "a2.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "a2-local-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps([
        {"key": "a2-b-admin", "actor": "b_admin", "tenant_id": "tenant-b",
         "role": "admin"},
        {"key": "a2-viewer", "actor": "viewer", "tenant_id": "local",
         "role": "viewer"},
    ]))
    intake_dir = tmp_path / "intake"
    intake_dir.mkdir()
    monkeypatch.setattr(settings, "INTAKE_STORAGE_PATH", str(intake_dir))
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        local_inv = models.Invoice(
            tenant_id="local", invoice_number="L-1", invoice_type="AR",
            counterparty_name="Local Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR", requires_human_review=True)
        b_inv = models.Invoice(
            tenant_id="tenant-b", invoice_number="B-1", invoice_type="AR",
            counterparty_name="B Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("2000"),
            total_amount=Decimal("2000"), face_amount_cents=200000,
            currency="INR")
        db.add_all([local_inv, b_inv])
        db.flush()
        stored = intake_dir / "up-local.pdf"
        stored.write_bytes(b"%PDF-1.4")
        db.add(models.IntakeUpload(
            id="up-local", tenant_id="local", actor="a2", filename="l.pdf",
            mime_type="application/pdf", source_path=str(stored), size_bytes=8,
            status="ready_for_review", stage="Ready for review"))
        db.commit()
        ids = {"local": local_inv.id, "b": b_inv.id}
    yield {"engine": engine, "factory": factory, "ids": ids, "tmp": tmp_path}
    engine.dispose()


def _afis_file(path, rows):
    connection = sqlite3.connect(str(path))
    connection.execute("CREATE TABLE transactions (id TEXT PRIMARY KEY, date TEXT,"
                       " description TEXT, amount REAL, category TEXT)")
    for txn_id, day, description, amount in rows:
        connection.execute("INSERT INTO transactions VALUES (?,?,?,?,?)",
                           (txn_id, day, description, amount, "bank"))
    connection.commit()
    connection.close()


def test_case_list_isolation(two_tenant):
    client = TestClient(app)
    own = client.get("/api/v1/cases", headers=B_ADMIN)
    assert own.status_code == 200
    assert [row["invoice_number"] for row in own.json()] == ["B-1"]


def test_cross_tenant_case_read_404(two_tenant):
    client = TestClient(app)
    res = client.get(f"/api/v1/cases/{two_tenant['ids']['local']}", headers=B_ADMIN)
    assert res.status_code == 404


def test_cross_tenant_reply_write_404(two_tenant):
    client = TestClient(app)
    res = client.post(f"/api/v1/cases/{two_tenant['ids']['local']}/replies",
                      headers=B_ADMIN,
                      json={"category": "dispute", "body": "not my invoice"})
    assert res.status_code == 404


def test_cross_tenant_dispute_review_404(two_tenant):
    client = TestClient(app)
    res = client.post(f"/api/v1/cases/{two_tenant['ids']['local']}/dispute-review",
                      headers=B_ADMIN,
                      json={"disputed_amount": "1.00", "evidence_id": 1,
                            "reason": "cross tenant attempt"})
    assert res.status_code == 404


def test_upload_and_file_cross_tenant_404(two_tenant):
    client = TestClient(app)
    assert client.get("/api/v1/intake/uploads/up-local",
                      headers=B_ADMIN).status_code == 404
    assert client.get("/api/v1/intake/uploads/up-local/file",
                      headers=B_ADMIN).status_code == 404
    own = client.get("/api/v1/intake/uploads/up-local/file", headers=LOCAL)
    assert own.status_code == 200
    assert own.content == b"%PDF-1.4"


def _signed(secret, body):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_unknown_tenant_webhook_not_configured(two_tenant):
    client = TestClient(app)
    res = client.post("/api/v1/webhooks/razorpay/tenant-zzz",
                      headers={"X-Razorpay-Event-Id": "e1"},
                      content=b"{}")
    assert res.status_code == 503


def test_malformed_tenant_rejected(two_tenant):
    client = TestClient(app)
    res = client.post("/api/v1/webhooks/razorpay/-bad",
                      headers={"X-Razorpay-Event-Id": "e1"},
                      content=b"{}")
    assert res.status_code == 404


def test_tenant_webhook_verifies_and_replays_safely(two_tenant, monkeypatch):
    monkeypatch.setenv("A2_B_RZP_SECRET", "b-webhook-secret-value")
    with two_tenant["factory"]() as db:
        db.add(models.TenantSecret(
            tenant_id="tenant-b", provider="razorpay", name="webhook_secret",
            secret_ref="env:A2_B_RZP_SECRET", label="B store",
            created_by="a2-test"))
        db.commit()
    client = TestClient(app)
    body = json.dumps({"event": "refund.processed",
                       "payload": {"refund": {"entity": {
                           "payment_id": "pay_unknown"}}}}).encode()
    headers = {"X-Razorpay-Event-Id": "evt-b1",
               "X-Razorpay-Signature": _signed("b-webhook-secret-value", body)}
    first = client.post("/api/v1/webhooks/razorpay/tenant-b", headers=headers,
                        content=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "needs_review"
    replay = client.post("/api/v1/webhooks/razorpay/tenant-b", headers=headers,
                         content=body)
    assert replay.status_code == 200
    assert replay.json()["status"] == "needs_review"
    tampered = client.post(
        "/api/v1/webhooks/razorpay/tenant-b",
        headers={"X-Razorpay-Event-Id": "evt-b1",
                 "X-Razorpay-Signature": _signed("b-webhook-secret-value", b"{}")},
        content=b"{}")
    assert tampered.status_code == 409
    with two_tenant["factory"]() as db:
        events = db.query(models.ProviderEvent).filter_by(
            tenant_id="tenant-b", provider="razorpay").all()
        assert len(events) == 1
        assert "b-webhook-secret-value" not in (events[0].error or "")


def test_webhook_wrong_secret_rejected(two_tenant, monkeypatch):
    monkeypatch.setenv("A2_B_RZP_SECRET", "b-webhook-secret-value")
    with two_tenant["factory"]() as db:
        db.add(models.TenantSecret(
            tenant_id="tenant-b", provider="razorpay", name="webhook_secret",
            secret_ref="env:A2_B_RZP_SECRET", label="B store",
            created_by="a2-test"))
        db.commit()
    client = TestClient(app)
    body = b"{}"
    res = client.post("/api/v1/webhooks/razorpay/tenant-b",
                      headers={"X-Razorpay-Event-Id": "evt-b2",
                               "X-Razorpay-Signature": _signed("wrong-secret", body)},
                      content=body)
    assert res.status_code == 401


def test_secret_values_never_returned(two_tenant, monkeypatch):
    monkeypatch.setenv("A2_LEAK_SECRET", "LEAK-VALUE-zzz-12345")
    client = TestClient(app)
    created = client.post("/api/v1/integrations/secrets", headers=LOCAL, json={
        "provider": "razorpay", "name": "webhook_secret",
        "secret_ref": "env:A2_LEAK_SECRET", "label": "leak probe"})
    assert created.status_code == 201, created.text
    assert "LEAK-VALUE-zzz-12345" not in created.text
    listed = client.get("/api/v1/integrations/secrets", headers=LOCAL)
    assert listed.status_code == 200
    assert "LEAK-VALUE-zzz-12345" not in listed.text
    row = next(item for item in listed.json()
               if item["provider"] == "razorpay" and item["name"] == "webhook_secret")
    assert row["secret_ref"] == "env:A2_LEAK_SECRET"
    assert row["configured"] is True
    assert client.post("/api/v1/integrations/secrets", headers=VIEWER, json={
        "provider": "razorpay", "name": "key_secret",
        "secret_ref": "env:X", "label": ""}).status_code == 403
    assert client.get("/api/v1/integrations/secrets",
                      headers=VIEWER).status_code == 403


def test_setting_validation(two_tenant, tmp_path):
    client = TestClient(app)
    bad_path = client.put("/api/v1/integrations/settings", headers=LOCAL, json={
        "key": "afis_db_path", "value": str(tmp_path / "missing.db")})
    assert bad_path.status_code == 422
    bad_key = client.put("/api/v1/integrations/settings", headers=LOCAL, json={
        "key": "not_a_setting", "value": "x"})
    assert bad_key.status_code == 422
    real = tmp_path / "afis-empty.db"
    real.write_bytes(b"")
    good = client.put("/api/v1/integrations/settings", headers=LOCAL, json={
        "key": "afis_db_path", "value": str(real)})
    assert good.status_code == 200, good.text
    assert client.put("/api/v1/integrations/settings", headers=VIEWER, json={
        "key": "afis_db_path", "value": str(real)}).status_code == 403


def test_afis_files_are_tenant_bound(two_tenant, tmp_path):
    path_l = tmp_path / "afis-l.db"
    path_b = tmp_path / "afis-b.db"
    _afis_file(path_l, [("LA1", "2026-10-20", "NEFT L-1", 500.00)])
    _afis_file(path_b, [("BA1", "2026-10-20", "NEFT B-1", 700.00)])
    client = TestClient(app)
    assert client.put("/api/v1/integrations/settings", headers=LOCAL, json={
        "key": "afis_db_path", "value": str(path_l)}).status_code == 200
    assert client.put("/api/v1/integrations/settings", headers=B_ADMIN, json={
        "key": "afis_db_path", "value": str(path_b)}).status_code == 200
    local_txns = client.get("/api/v1/allocations/transfers/unmatched",
                            headers=LOCAL).json()
    b_txns = client.get("/api/v1/allocations/transfers/unmatched",
                        headers=B_ADMIN).json()
    assert [txn["id"] for txn in local_txns] == ["LA1"]
    assert [txn["id"] for txn in b_txns] == ["BA1"]
    foreign = client.post("/api/v1/allocations/proposals", headers=B_ADMIN,
                          json={"afis_transaction_id": "LA1"})
    assert foreign.status_code == 409
    own = client.post("/api/v1/allocations/proposals", headers=LOCAL,
                      json={"afis_transaction_id": "LA1"})
    assert own.status_code == 201, own.text


def test_evidence_file_is_tenant_bound(two_tenant, monkeypatch, tmp_path):
    docs = tmp_path / "docs" / "invoices"
    docs.mkdir(parents=True)
    (docs / "FIX-A2.pdf").write_bytes(b"%PDF-A2")
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    with two_tenant["factory"]() as db:
        db.add(models.CaseEvidence(
            tenant_id="local", invoice_id=two_tenant["ids"]["local"],
            claim_type="invoice_total", title="Invoice", description="A2 fixture",
            source_type="staff_record",
            source_reference="docs/invoices/FIX-A2.pdf",
            amount_cents=100000, verified=True, trust_state="verified",
            currency="INR"))
        db.commit()
    client = TestClient(app)
    invoice_id = two_tenant["ids"]["local"]
    own = client.get(f"/api/v1/cases/{invoice_id}/evidence-files/FIX-A2.pdf",
                     headers=LOCAL)
    assert own.status_code == 200
    assert own.content == b"%PDF-A2"
    assert client.get(f"/api/v1/cases/{invoice_id}/evidence-files/FIX-A2.pdf",
                      headers=B_ADMIN).status_code == 404
    assert client.get(f"/api/v1/cases/{invoice_id}/evidence-files/OTHER.pdf",
                      headers=LOCAL).status_code == 404


def test_invoice_review_ignores_foreign_rows(two_tenant):
    with two_tenant["factory"]() as db:
        db.add(models.ReceivableEntry(
            tenant_id="tenant-b", invoice_id=two_tenant["ids"]["local"],
            kind="payment", amount_cents=100, currency="INR", source="rogue",
            reference="rogue-1", actor="a2-test"))
        db.commit()
    client = TestClient(app)
    payload = {"invoice_number": "L-1", "invoice_type": "AR",
               "counterparty_name": "Local Party",
               "issue_date": "2026-01-01", "due_date": "2026-02-01",
               "total_amount": "1000.00", "currency": "INR"}
    reviewed = client.put(f"/api/v1/invoices/{two_tenant['ids']['local']}/review",
                          headers=LOCAL, json=payload)
    assert reviewed.status_code == 200, reviewed.text
    with two_tenant["factory"]() as db:
        assert db.query(models.ReceivableEntry).filter_by(
            tenant_id="tenant-b", reference="rogue-1").count() == 1
        invoice = db.get(models.Invoice, two_tenant["ids"]["local"])
        invoice.requires_human_review = True
        db.add(models.ReceivableEntry(
            tenant_id="local", invoice_id=invoice.id, kind="payment",
            amount_cents=100, currency="INR", source="own",
            reference="own-1", actor="a2-test"))
        db.commit()
    blocked = client.put(f"/api/v1/invoices/{two_tenant['ids']['local']}/review",
                         headers=LOCAL, json=payload)
    assert blocked.status_code == 409


def test_integration_status_is_per_tenant(two_tenant, monkeypatch):
    monkeypatch.setenv("A2_B_RZP_SECRET", "b-webhook-secret-value")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "META_WHATSAPP_APP_SECRET", "")
    monkeypatch.setattr(settings, "SHOPIFY_WEBHOOK_SECRET", "")
    monkeypatch.setattr(settings, "SHOPIFY_SHOP_DOMAIN", "")
    with two_tenant["factory"]() as db:
        db.add(models.TenantSecret(
            tenant_id="tenant-b", provider="razorpay", name="webhook_secret",
            secret_ref="env:A2_B_RZP_SECRET", label="B store",
            created_by="a2-test"))
        db.commit()
    client = TestClient(app)
    mine = client.get("/api/v1/integrations/status", headers=B_ADMIN).json()
    assert mine["razorpay"]["configured"] is True
    assert mine["razorpay"]["mode"] is None
    assert mine["shopify"]["configured"] is False
    other = client.get("/api/v1/integrations/status", headers=LOCAL).json()
    assert other["razorpay"]["configured"] is False
