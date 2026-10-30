"""P2 E2: ops metrics and alerts — counts and ages only, never customer
data; alert rules fire and clear on real state."""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app

ADMIN = {"X-RECOVERFLOW-API-KEY": "e2-admin"}
EDITOR = {"X-RECOVERFLOW-API-KEY": "e2-editor"}


@pytest.fixture()
def opsdb(monkeypatch, tmp_path):
    db_path = tmp_path / "e2.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "e2-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "e2-editor", "actor": "ed@example.in", "tenant_id": "local",
          "role": "editor"}]))
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-E2", invoice_type="AR",
            counterparty_name="Secret Customer Name",
            counterparty_phone="+91-SECRET-PHONE",
            issue_date=date(2026, 1, 1), due_date=date(2026, 2, 1),
            amount=Decimal("1000"), total_amount=Decimal("1000"),
            face_amount_cents=100000, currency="INR"))
        db.commit()
        invoice = db.query(models.Invoice).one().id
    yield {"client": TestClient(app), "factory": factory, "engine": engine,
           "invoice": invoice}
    engine.dispose()


def _seed(opsdb):
    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=2)
    with opsdb["factory"]() as db:
        db.add(models.IntakeUpload(
            id="stuck-1", tenant_id="local", actor="staff",
            filename="stuck.csv", mime_type="text/csv",
            source_path="/tmp/stuck.csv", size_bytes=10, status="queued",
            stage="Uploaded", created_at=old))
        db.add(models.SupervisorTask(
            tenant_id="local", invoice_id=opsdb["invoice"],
            kind="resolution", status="dead_letter",
            idempotency_key="local:e2:dead",
            error="RuntimeError: poisoned payload"))
        db.add(models.SupervisorTask(
            tenant_id="local", invoice_id=opsdb["invoice"],
            kind="verification", status="done",
            idempotency_key="local:e2:done", model_calls=4,
            elapsed_ms=90000))
        for index in range(6):
            db.add(models.ProviderEvent(
                tenant_id="local", kind="payment", provider="razorpay",
                event_id=f"evt-need-{index}", body_sha256="x" * 64,
                status="needs_review", mode="test"))
        inbound = models.InboundMessage(
            tenant_id="local", provider="meta_whatsapp",
            external_id="wamid.e2seed", sender="919999999999",
            body="seed", status="triaged",
            invoice_id=opsdb["invoice"])
        db.add(inbound)
        db.flush()
        db.add(models.OutboundMessage(
            tenant_id="local", inbound_id=inbound.id,
            invoice_id=opsdb["invoice"], idempotency_key="local:e2:msg",
            provider="meta_whatsapp", recipient="919999999999",
            body="hello", status="failed",
            failure_reason="131047 Re-engagement window"))
        db.add(models.PaymentDiscrepancy(
            tenant_id="local", provider="razorpay",
            kind="settlement_short", reference="pay_x",
            invoice_id=opsdb["invoice"], expected_cents=100,
            actual_cents=90, currency="INR"))
        db.add(models.AllocationProposal(
            tenant_id="local", afis_transaction_id="txn-e2",
            transfer_cents=100, currency="INR", status="proposed",
            created_by="allocator"))
        db.commit()


def test_metrics_counts_without_customer_data(opsdb):
    _seed(opsdb)
    client = opsdb["client"]
    body = client.get("/api/v1/system/metrics", headers=EDITOR).json()
    assert body["queues"]["intake"]["queued"]["count"] == 1
    assert body["queues"]["intake"]["queued"]["oldest_age_seconds"] > 3600
    assert body["dead_letters"] == {"intake": 0, "supervisor": 1}
    assert body["provider_events_24h"]["razorpay"]["needs_review"] == 6
    assert body["models_24h"]["model_calls"] == 4
    assert body["models_24h"]["latency_ms"]["max"] == 90000
    assert body["models_24h"]["cost"] == "not_tracked"
    assert body["messages_24h"]["failed"] == 1
    assert body["discrepancies"]["payment_discrepancies"] == {
        "settlement_short": 1}
    assert body["discrepancies"]["open_allocation_proposals"] == 1
    dumped = json.dumps(body)
    for secret in ("Secret Customer Name", "+91-SECRET-PHONE", "INV-E2",
                   "919999999999", "pay_x", "poisoned payload",
                   "Re-engagement window", "hello"):
        assert secret not in dumped
    assert client.get("/api/v1/system/metrics").status_code == 401


def test_alerts_fire_and_carry_runbook_fields(opsdb):
    _seed(opsdb)
    client = opsdb["client"]
    alerts = {item["name"]: item
              for item in client.get("/api/v1/system/alerts",
                                     headers=EDITOR).json()}
    assert alerts["intake_queue_stalled"]["state"] == "firing"
    assert alerts["supervisor_queue_stalled"]["state"] == "ok"
    assert alerts["dead_letters_present"]["state"] == "firing"
    assert alerts["provider_review_backlog"]["state"] == "firing"
    assert alerts["model_latency_high"]["state"] == "ok"
    assert alerts["delivery_failures"]["state"] == "firing"
    assert alerts["unreconciled_settlements"]["state"] == "firing"
    assert alerts["allocation_backlog"]["state"] == "ok"
    for item in alerts.values():
        assert item["severity"] in ("high", "medium")
        assert item["owner"]
        assert item["first_response"]
        assert item["state"] in ("firing", "ok")


def test_alerts_clear_when_state_heals(opsdb):
    _seed(opsdb)
    client = opsdb["client"]
    with opsdb["factory"]() as db:
        db.get(models.IntakeUpload, "stuck-1").status = "Ready for review"
        db.query(models.SupervisorTask).filter_by(
            idempotency_key="local:e2:dead").one().status = "failed"
        db.query(models.ProviderEvent).update({"status": "processed"})
        db.query(models.OutboundMessage).update({"status": "delivered"})
        db.query(models.PaymentDiscrepancy).update({"status": "resolved"})
        db.commit()
    alerts = {item["name"]: item["state"]
              for item in client.get("/api/v1/system/alerts",
                                     headers=EDITOR).json()}
    assert alerts == {
        "intake_queue_stalled": "ok", "supervisor_queue_stalled": "ok",
        "dead_letters_present": "ok", "provider_review_backlog": "ok",
        "model_latency_high": "ok", "delivery_failures": "ok",
        "unreconciled_settlements": "ok", "allocation_backlog": "ok"}


def test_tenant_scoping(opsdb):
    _seed(opsdb)
    client = opsdb["client"]
    with opsdb["factory"]() as db:
        db.add(models.IntakeUpload(
            id="foreign-1", tenant_id="tenant-b", actor="staff",
            filename="f.csv", mime_type="text/csv", source_path="/tmp/f.csv",
            size_bytes=10, status="dead_letter", stage="Dead letter"))
        db.commit()
    body = client.get("/api/v1/system/metrics", headers=EDITOR).json()
    assert body["dead_letters"] == {"intake": 0, "supervisor": 1}
    jobs = client.get("/api/v1/system/jobs", headers=EDITOR).json()
    assert {item["tenant_id"] for item in jobs} == {"local"}
    assert client.get("/api/v1/system/jobs/intake/foreign-1",
                      headers=ADMIN).status_code == 404
