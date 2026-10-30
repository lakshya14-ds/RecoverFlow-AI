"""P2 D2: Razorpay behind a disabled-by-default live gate — signed webhooks,
idempotency, failures, refunds/chargebacks, settlements, discrepancy queue.
Mock/test keys only; no real charge, no sandbox account needed."""
import hashlib
import hmac
import json
import time
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app
from app.services.receivables import split_balance

ADMIN = {"X-RECOVERFLOW-API-KEY": "d2-admin"}
EDITOR = {"X-RECOVERFLOW-API-KEY": "d2-editor"}
SECRET = "whsec-synthetic-d2"


@pytest.fixture()
def paydb(monkeypatch, tmp_path):
    db_path = tmp_path / "d2.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "d2-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "d2-editor", "actor": "ed@example.in", "tenant_id": "local",
          "role": "editor"}]))
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_mock_d2")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "mock-secret")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "RAZORPAY_MODE", "test")
    monkeypatch.setattr(settings, "RAZORPAY_LIVE_ENABLED", False)
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-D2", invoice_type="AR",
            counterparty_name="D2 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR"))
        db.commit()
        invoice = db.query(models.Invoice).one().id
    yield {"client": TestClient(app), "factory": factory, "engine": engine,
           "invoice": invoice}
    engine.dispose()


def _send(client, payload, event_id, secret=SECRET, tenant="local"):
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        f"/api/v1/webhooks/razorpay/{tenant}", content=body,
        headers={"X-Razorpay-Signature": sig,
                 "X-Razorpay-Event-Id": event_id,
                 "Content-Type": "application/json"})


def _paid(link_id, amount_cents, payment_id="pay_test1", captured=True,
          currency="INR", link_amount=None):
    return {
        "event": "payment_link.paid",
        "payload": {
            "payment": {"entity": {
                "id": payment_id, "status": "captured" if captured else "created",
                "captured": captured, "amount": amount_cents,
                "currency": currency}},
            "payment_link": {"entity": {
                "id": link_id, "amount": link_amount or amount_cents,
                "currency": currency}}}}


def _link(client, invoice, amount_cents=None):
    res = client.post("/api/v1/payments/links", headers=ADMIN,
                      json={"invoice_id": invoice,
                            "idempotency_key": str(uuid.uuid4()),
                            **({"amount_cents": amount_cents}
                               if amount_cents else {})})
    assert res.status_code == 201, res.text
    return res.json()


def test_status_labels(paydb, monkeypatch):
    client = paydb["client"]
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    assert client.get("/api/v1/payments/razorpay/status",
                      headers=EDITOR).json()["state"] == "not_configured"
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_mock_d2")
    body = client.get("/api/v1/payments/razorpay/status",
                      headers=EDITOR).json()
    assert body["state"] == "mock"
    assert body["mode"] == "test"
    assert body["live_enabled"] is False
    assert SECRET not in json.dumps(body)
    assert "mock-secret" not in json.dumps(body)


def test_live_gate_blocks(paydb, monkeypatch):
    client = paydb["client"]
    monkeypatch.setattr(settings, "RAZORPAY_MODE", "live")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_abc123")
    res = client.post("/api/v1/payments/links", headers=ADMIN,
                      json={"invoice_id": paydb["invoice"],
                            "idempotency_key": str(uuid.uuid4())})
    assert res.status_code == 503
    hooked = _send(client, {"event": "payment_link.paid", "payload": {}},
                   "evt-live-1")
    assert hooked.status_code == 503


def test_signature_and_shape_guards(paydb):
    client = paydb["client"]
    body = json.dumps({"event": "payment_link.paid"}).encode()
    bad = client.post("/api/v1/webhooks/razorpay/local", content=body,
                      headers={"X-Razorpay-Signature": "0" * 64,
                               "X-Razorpay-Event-Id": "evt-bad"})
    assert bad.status_code == 401
    assert client.post("/api/v1/webhooks/razorpay/local", content=body,
                       headers={"X-Razorpay-Signature": "0" * 64}
                       ).status_code in (401, 422)
    big = b"x" * (1024 * 1024 + 1)
    sig = hmac.new(SECRET.encode(), big, hashlib.sha256).hexdigest()
    assert client.post("/api/v1/webhooks/razorpay/local", content=big,
                       headers={"X-Razorpay-Signature": sig,
                                "X-Razorpay-Event-Id": "evt-big"}
                       ).status_code == 413


def test_paid_flow_and_duplicate_delivery(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    link = _link(client, invoice)
    assert link["mode"] == "test"
    payload = _paid(link["provider_link_id"], 100000)
    first = _send(client, payload, "evt-paid-1")
    assert first.json()["status"] == "processed"
    again = _send(client, payload, "evt-paid-1")
    assert again.json()["status"] == "processed"
    with paydb["factory"]() as db:
        entries = db.query(models.ReceivableEntry).filter_by(
            invoice_id=invoice, source="razorpay").all()
        assert len(entries) == 1
        assert db.get(models.Invoice, invoice).status == "paid"
        event = db.query(models.ProviderEvent).filter_by(
            event_id="evt-paid-1").one()
        assert event.mode == "test"
        assert event.resource_id == "pay_test1"


def test_partial_payment(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    link = _link(client, invoice, amount_cents=40000)
    res = _send(client, _paid(link["provider_link_id"], 40000,
                              payment_id="pay_part1"), "evt-part-1")
    assert res.json()["status"] == "processed"
    with paydb["factory"]() as db:
        assert db.query(models.PaymentLink).get(link["id"]).status == \
            "partially_paid"
        assert split_balance(
            db, db.get(models.Invoice, invoice))["outstanding_cents"] == 60000


def test_ambiguous_payments_park_without_posting(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    link = _link(client, invoice)
    lid = link["provider_link_id"]
    cases = [
        ("evt-amb-1", _paid(lid, 100000, captured=False)),
        ("evt-amb-2", _paid(lid, 99999)),
        ("evt-amb-3", _paid(lid, 100000, currency="USD")),
        ("evt-amb-4", _paid("plink_unknown", 100000)),
        ("evt-amb-5", _paid(lid, 100000, payment_id="bad-id")),
    ]
    for event_id, payload in cases:
        res = _send(client, payload, event_id)
        assert res.json()["status"] == "needs_review", event_id
    with paydb["factory"]() as db:
        assert db.query(models.ReceivableEntry).filter_by(
            invoice_id=invoice).count() == 0


def test_event_id_reuse_with_different_payload(paydb):
    client = paydb["client"]
    link = _link(client, paydb["invoice"])
    _send(client, _paid(link["provider_link_id"], 100000), "evt-reuse-1")
    clash = _send(client, _paid(link["provider_link_id"], 100000,
                                payment_id="pay_other"), "evt-reuse-1")
    assert clash.status_code == 409


def test_payment_failed_records_without_posting(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    link = _link(client, invoice)
    payload = {"event": "payment.failed",
               "payload": {
                   "payment": {"entity": {
                       "id": "pay_fail1",
                       "error_description": "Insufficient funds"}},
                   "payment_link": {"entity": {"id": link["provider_link_id"]}}}}
    res = _send(client, payload, "evt-fail-1")
    assert res.json()["status"] == "processed"
    with paydb["factory"]() as db:
        assert db.query(models.ReceivableEntry).filter_by(
            invoice_id=invoice).count() == 0
        assert "Insufficient funds" in (
            db.query(models.PaymentLink).get(link["id"]).last_error or "")
        assert db.query(models.AuditEvent).filter_by(
            action="payment_failed").count() == 1


def test_refund_before_payment_then_reversal(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    link = _link(client, invoice)
    refund = {"event": "refund.processed",
              "payload": {
                  "refund": {"entity": {"payment_id": "pay_ooo1",
                                        "amount": 100000}},
                  "payment": {"entity": {"id": "pay_ooo1"}}}}
    parked = _send(client, refund, "evt-ref-1")
    assert parked.json()["status"] == "needs_review"
    queued = client.get("/api/v1/payments/discrepancies",
                        headers=EDITOR).json()
    assert len(queued) == 1
    assert queued[0]["kind"] == "refund_unposted"
    assert queued[0]["invoice_id"] is None
    early = client.post(
        f"/api/v1/payments/discrepancies/{queued[0]['id']}/resolve",
        headers=ADMIN, json={"action": "post_reversal"})
    assert early.status_code == 409
    _send(client, _paid(link["provider_link_id"], 100000,
                        payment_id="pay_ooo1"), "evt-ooo-2")
    with paydb["factory"]() as db:
        assert db.query(models.PaymentDiscrepancy).filter_by(
            status="open").count() == 1
    assert client.post(
        f"/api/v1/payments/discrepancies/{queued[0]['id']}/resolve",
        headers=EDITOR, json={"action": "dismiss"}).status_code == 403
    done = client.post(
        f"/api/v1/payments/discrepancies/{queued[0]['id']}/resolve",
        headers=ADMIN, json={"action": "post_reversal",
                             "note": "verified with provider dashboard"})
    assert done.json()["status"] == "resolved"
    assert done.json()["resolution"].startswith("reversal:")
    with paydb["factory"]() as db:
        row = db.get(models.Invoice, invoice)
        assert split_balance(db, row)["outstanding_cents"] == 100000
        reversal = db.query(models.ReceivableEntry).filter_by(
            invoice_id=invoice, kind="reversal").one()
        assert reversal.reversal_of_id is not None
        event = db.query(models.ProviderEvent).filter_by(
            event_id="evt-ref-1").one()
        assert event.status == "resolved"


def test_refund_dismiss_posts_nothing(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    _send(client, {"event": "payment.refunded",
                   "payload": {"payment": {"entity": {
                       "id": "pay_dup_ref", "amount": 5000}}}},
            "evt-ref-2")
    queued = client.get("/api/v1/payments/discrepancies",
                        headers=EDITOR).json()
    assert len(queued) == 1
    done = client.post(
        f"/api/v1/payments/discrepancies/{queued[0]['id']}/resolve",
        headers=ADMIN, json={"action": "dismiss",
                             "note": "duplicate notification"})
    assert done.json()["status"] == "resolved"
    with paydb["factory"]() as db:
        assert db.query(models.ReceivableEntry).filter_by(
            invoice_id=invoice).count() == 0


def test_chargeback_and_settlement_webhook_park(paydb):
    client = paydb["client"]
    dispute = {"event": "dispute.created",
               "payload": {"dispute": {"entity": {
                   "payment_id": "pay_cb1", "amount": 100000}}}}
    assert _send(client, dispute, "evt-cb-1").json()["status"] == \
        "needs_review"
    queued = client.get("/api/v1/payments/discrepancies",
                        headers=EDITOR).json()
    assert queued[0]["kind"] == "chargeback"
    settle = {"event": "settlement.processed", "payload": {"id": "setl_1"}}
    res = _send(client, settle, "evt-setl-1")
    assert res.json()["status"] == "needs_review"


def test_settlement_matching(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    link = _link(client, invoice)
    _send(client, _paid(link["provider_link_id"], 100000,
                        payment_id="pay_setl_ok"), "evt-setl-ok")
    report = client.post("/api/v1/payments/settlements", headers=EDITOR,
                         json={"settlement_ref": "setl_test_1",
                               "lines": [
                                   {"payment_reference": "pay_setl_ok",
                                    "settled_amount": "1000.00",
                                    "fee": "23.60"},
                                   {"payment_reference": "pay_ghost",
                                    "settled_amount": "10.00"}]})
    assert report.status_code == 201, report.text
    body = report.json()
    assert (body["matched"], body["short"], body["unmatched"]) == (1, 0, 1)
    assert body["lines"][1]["status"] == "unmatched"
    dup = client.post("/api/v1/payments/settlements", headers=EDITOR,
                      json={"settlement_ref": "setl_test_1",
                            "lines": [{"payment_reference": "pay_setl_ok",
                                       "settled_amount": "1000.00"}]})
    assert dup.status_code == 409
    queued = client.get("/api/v1/payments/discrepancies",
                        headers=EDITOR).json()
    assert [item["kind"] for item in queued] == ["settlement_unmatched"]


def test_settlement_short_queues(paydb):
    client = paydb["client"]
    link = _link(client, paydb["invoice"])
    _send(client, _paid(link["provider_link_id"], 100000,
                        payment_id="pay_short1"), "evt-short-1")
    report = client.post("/api/v1/payments/settlements", headers=EDITOR,
                         json={"settlement_ref": "setl_test_2",
                               "lines": [{"payment_reference": "pay_short1",
                                          "settled_amount": "999.00"}]})
    assert report.json()["short"] == 1
    queued = client.get("/api/v1/payments/discrepancies",
                        headers=EDITOR).json()
    assert queued[0]["kind"] == "settlement_short"
    assert queued[0]["expected_cents"] == 100000
    assert queued[0]["actual_cents"] == 99900
    bad_action = client.post(
        f"/api/v1/payments/discrepancies/{queued[0]['id']}/resolve",
        headers=ADMIN, json={"action": "post_reversal"})
    assert bad_action.status_code == 409


def test_cross_tenant_guards(paydb):
    client = paydb["client"]
    assert client.post("/api/v1/webhooks/razorpay/tenant-b", content=b"{}",
                       headers={"X-Razorpay-Signature": "x",
                                "X-Razorpay-Event-Id": "e"}).status_code == 503
    assert client.post("/api/v1/webhooks/razorpay/not_a tenant!", content=b"{}",
                       headers={"X-Razorpay-Signature": "x",
                                "X-Razorpay-Event-Id": "e"}).status_code == 404


def test_stale_event_still_processes_once(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    link = _link(client, paydb["invoice"])
    payload = _paid(link["provider_link_id"], 100000,
                    payment_id="pay_stale1")
    payload["created_at"] = int(time.time()) - 48 * 3600
    assert _send(client, payload, "evt-stale-1").json()["status"] == \
        "processed"
    assert _send(client, payload, "evt-stale-1").json()["status"] == \
        "processed"
    with paydb["factory"]() as db:
        assert db.query(models.ReceivableEntry).filter_by(
            invoice_id=invoice).count() == 1
