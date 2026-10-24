"""Release 2 safety checks use fake provider responses; no account or network is needed."""
import hashlib
import hmac
import json
import base64
import httpx
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base, get_db
from app.database import db_manager
from app.main import app
from app.services import shopify
from app.services.policy_scheduler import create_due_drafts


def client_with_db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "test-key")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", "")
    return TestClient(app), factory


def invoice(factory, **extra):
    with factory() as db:
        inv = models.Invoice(tenant_id="local", invoice_number="RF-2", invoice_type="AR",
            counterparty_name="Customer", counterparty_phone="+91 9876543210",
            issue_date=date.today() - timedelta(days=40),
            due_date=date.today() - timedelta(days=20),
            amount=100, total_amount=100, face_amount_cents=10000, currency="INR", **extra)
        db.add(inv)
        db.commit()
        return inv.id


def test_razorpay_link_and_signed_webhook_are_idempotent(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_fake")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "private-test")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "webhook-test")
    from app.services import razorpay
    monkeypatch.setattr(razorpay, "create_remote_link", lambda *_: {
        "id": "plink_test", "url": "https://rzp.io/i/test"})
    try:
        inv_id = invoice(factory)
        key = str(uuid4())
        created = client.post("/api/v1/payments/links", headers={"X-RECOVERFLOW-API-KEY": "test-key"},
                              json={"invoice_id": inv_id, "idempotency_key": key})
        assert created.status_code == 201, created.text
        assert created.json()["url"] == "https://rzp.io/i/test"
        assert client.post("/api/v1/payments/links", headers={"X-RECOVERFLOW-API-KEY": "test-key"},
                           json={"invoice_id": inv_id, "idempotency_key": key}).json()["id"] == created.json()["id"]
        payload = {"event": "payment_link.paid", "payload": {
            "payment_link": {"entity": {"id": "plink_test", "amount": 10000, "currency": "INR"}},
            "payment": {"entity": {"id": "pay_test", "amount": 10000,
                                   "currency": "INR", "status": "captured", "captured": True}}}}
        body = json.dumps(payload).encode()
        path = "/api/v1/webhooks/razorpay/local"
        assert client.post(path, content=body, headers={"X-Razorpay-Event-Id": "evt_test",
                           "X-Razorpay-Signature": "bad"}).status_code == 401
        headers = {"X-Razorpay-Event-Id": "evt_test", "X-Razorpay-Signature":
                   hmac.new(b"webhook-test", body, hashlib.sha256).hexdigest()}
        assert client.post(path, content=body, headers=headers).json()["status"] == "processed"
        assert client.post(path, content=body, headers=headers).json()["status"] == "processed"
        with factory() as db:
            assert db.query(models.ReceivableEntry).count() == 1
            assert db.get(models.Invoice, inv_id).status == "paid"
        refund = json.dumps({"event": "refund.processed", "payload": {
            "refund": {"entity": {"payment_id": "pay_test", "id": "rfnd_test"}}}}).encode()
        refund_headers = {"X-Razorpay-Event-Id": "evt_refund",
                          "X-Razorpay-Signature": hmac.new(b"webhook-test", refund,
                                                                hashlib.sha256).hexdigest()}
        assert client.post(path, content=refund, headers=refund_headers).json()["status"] == "needs_review"
        with factory() as db:
            assert db.query(models.ReceivableEntry).count() == 1
            assert db.get(models.Invoice, inv_id).contact_suppressed
    finally:
        app.dependency_overrides.clear()


def test_razorpay_mismatch_needs_review_without_ledger_entry(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_fake")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "private-test")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "webhook-test")
    try:
        inv_id = invoice(factory)
        with factory() as db:
            db.add(models.PaymentLink(tenant_id="local", invoice_id=inv_id,
                provider="razorpay", provider_link_id="plink_test", idempotency_key="test",
                url="https://rzp.io/i/test", amount_cents=10000, currency="INR", status="open"))
            db.commit()
        payload = {"event": "payment_link.paid", "payload": {
            "payment_link": {"entity": {"id": "plink_test", "amount": 10000, "currency": "INR"}},
            "payment": {"entity": {"id": "pay_mismatch", "amount": 11000,
                                   "currency": "INR", "status": "captured", "captured": True}}}}
        body = json.dumps(payload).encode()
        result = client.post("/api/v1/webhooks/razorpay/local", content=body, headers={
            "X-Razorpay-Event-Id": "evt_mismatch",
            "X-Razorpay-Signature": hmac.new(b"webhook-test", body, hashlib.sha256).hexdigest()})
        assert result.status_code == 200 and result.json()["status"] == "needs_review"
        with factory() as db:
            assert db.query(models.ReceivableEntry).count() == 0
    finally:
        app.dependency_overrides.clear()


def test_razorpay_payment_pauses_shopify_case_for_balance_confirmation(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_fake")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "private-test")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "webhook-test")
    try:
        inv_id = invoice(factory, source_system="shopify",
                         source_record_id="gid://shopify/PaymentSchedule/1",
                         source_order_id="gid://shopify/Order/1")
        with factory() as db:
            db.add(models.PaymentLink(tenant_id="local", invoice_id=inv_id,
                provider="razorpay", provider_link_id="plink_shopify", idempotency_key="shopify",
                url="https://rzp.io/i/test", amount_cents=10000, currency="INR", status="open"))
            db.commit()
        body = json.dumps({"event": "payment_link.paid", "payload": {
            "payment_link": {"entity": {"id": "plink_shopify", "amount": 10000, "currency": "INR"}},
            "payment": {"entity": {"id": "pay_shopify", "amount": 10000,
                                   "currency": "INR", "status": "captured", "captured": True}}}}).encode()
        signature = hmac.new(b"webhook-test", body, hashlib.sha256).hexdigest()
        response = client.post("/api/v1/webhooks/razorpay/local", content=body, headers={
            "X-Razorpay-Event-Id": "evt_shopify_payment", "X-Razorpay-Signature": signature})
        assert response.status_code == 200 and response.json()["status"] == "processed"
        with factory() as db:
            case = db.get(models.Invoice, inv_id)
            assert case.status == "paid"
            assert case.requires_human_review and case.contact_suppressed
            assert db.query(models.ReceivableEntry).count() == 1
    finally:
        app.dependency_overrides.clear()


def test_shopify_sync_imports_only_credit_term_inr_and_flags_balance_change(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    record = {"id": "gid://shopify/Order/1", "name": "#1001", "createdAt": "2026-10-01T00:00:00Z",
        "email": "customer@example.com", "phone": "+919876543210",
        "customer": {"displayName": "Customer"},
        "paymentTerms": {"paymentSchedules": {"nodes": [{"id": "gid://shopify/PaymentSchedule/1",
            "dueAt": "2026-10-20T00:00:00Z", "balanceDue": {"amount": "100.00", "currencyCode": "INR"}}]}}}
    monkeypatch.setattr(shopify, "fetch_page", lambda *_: {"nodes": [record],
                                                            "pageInfo": {"hasNextPage": False}})
    try:
        with factory() as db:
            assert shopify.import_orders(db, "local")["imported"] == 1
            assert shopify.import_orders(db, "local")["unchanged"] == 1
            record["paymentTerms"]["paymentSchedules"]["nodes"][0]["balanceDue"]["amount"] = "80.00"
            assert shopify.import_orders(db, "local")["review"] == 1
            inv = db.query(models.Invoice).filter_by(source_system="shopify").one()
            assert inv.contact_suppressed and inv.requires_human_review
            assert db.query(models.ReceivableEntry).count() == 0
    finally:
        app.dependency_overrides.clear()


def test_meta_inbound_suppresses_contact_and_deduplicates(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    monkeypatch.setattr(settings, "META_WHATSAPP_APP_SECRET", "meta-secret")
    monkeypatch.setattr(settings, "META_WHATSAPP_VERIFY_TOKEN", "verify-token")
    monkeypatch.setattr(settings, "META_WHATSAPP_PHONE_NUMBER_ID", "12345")
    try:
        inv_id = invoice(factory)
        body = json.dumps({"entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": "12345"},
            "messages": [{"id": "wamid.1", "from": "919876543210", "type": "text",
                          "text": {"body": "STOP"}}]}}]}]}).encode()
        headers = {"X-Hub-Signature-256": "sha256=" +
                   hmac.new(b"meta-secret", body, hashlib.sha256).hexdigest()}
        path = "/api/v1/webhooks/meta-whatsapp/local"
        assert client.post(path, content=body, headers={"X-Hub-Signature-256": "bad"}).status_code == 401
        assert client.post(path, content=body, headers=headers).json()["received"] == 1
        assert client.post(path, content=body, headers=headers).json()["duplicated"] == 1
        with factory() as db:
            inv = db.get(models.Invoice, inv_id)
            assert inv.contact_opt_out and inv.contact_suppressed
            incoming = db.query(models.InboundMessage).one()
            assert incoming.invoice_id == inv_id
        triage = client.post(f"/api/v1/messages/{incoming.id}/triage",
                             headers={"X-RECOVERFLOW-API-KEY": "test-key"},
                             json={"invoice_id": inv_id, "category": "opt_out"})
        assert triage.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_opt_in_policy_creates_one_draft_only(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    try:
        invoice(factory)
        now = datetime.now(timezone.utc)
        with factory() as db:
            db.add(models.CollectionPolicy(tenant_id="local", enabled=True, timezone="UTC",
                                           run_hour=now.hour))
            db.commit()
            assert create_due_drafts(db, now=now) == 1
            assert create_due_drafts(db, now=now) == 0
            campaign = db.query(models.DunningCampaign).one()
            assert campaign.status == "draft" and not campaign.email_sent
    finally:
        app.dependency_overrides.clear()


def test_signed_shopify_update_pauses_case_and_deduplicates(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    monkeypatch.setattr(settings, "SHOPIFY_SHOP_DOMAIN", "pilot.myshopify.com")
    monkeypatch.setattr(settings, "SHOPIFY_ADMIN_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(settings, "SHOPIFY_WEBHOOK_SECRET", "shopify-secret")
    try:
        inv_id = invoice(factory, source_system="shopify",
                         source_record_id="gid://shopify/PaymentSchedule/1",
                         source_order_id="gid://shopify/Order/1")
        body = json.dumps({"id": 1}).encode()
        signature = base64.b64encode(hmac.new(b"shopify-secret", body, hashlib.sha256).digest()).decode()
        headers = {"X-Shopify-Hmac-Sha256": signature,
                   "X-Shopify-Shop-Domain": "pilot.myshopify.com",
                   "X-Shopify-Webhook-Id": "hook-1", "X-Shopify-Topic": "orders/paid"}
        path = "/api/v1/webhooks/shopify/local"
        assert client.post(path, content=body, headers={**headers,
            "X-Shopify-Hmac-Sha256": "invalid"}).status_code == 401
        first = client.post(path, content=body, headers=headers)
        assert first.status_code == 200 and first.json()["cases_paused"] == 1
        assert client.post(path, content=body, headers=headers).json()["status"] == "needs_review"
        with factory() as db:
            assert db.query(models.ProviderEvent).count() == 1
            inv = db.get(models.Invoice, inv_id)
            assert inv.contact_suppressed and inv.requires_human_review
    finally:
        app.dependency_overrides.clear()


def test_staff_whatsapp_reply_is_idempotent_and_requires_recent_inbound(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    from app.services import meta_whatsapp
    monkeypatch.setattr(meta_whatsapp, "outbound_configured", lambda: True)
    calls = []
    monkeypatch.setattr(meta_whatsapp, "send_reply", lambda outgoing: calls.append(outgoing.id) or "wamid.out")
    try:
        inv_id = invoice(factory)
        with factory() as db:
            db.add(models.InboundMessage(tenant_id="local", provider="meta_whatsapp",
                external_id="wamid.in", sender="919876543210", body="Can I pay tomorrow?",
                invoice_id=inv_id, status="triaged", received_at=datetime.now(timezone.utc)))
            db.commit()
            incoming_id = db.query(models.InboundMessage.id).one()[0]
        payload = {"body": "Yes, please use the link when ready.", "idempotency_key": str(uuid4())}
        path = f"/api/v1/messages/{incoming_id}/reply"
        headers = {"X-RECOVERFLOW-API-KEY": "test-key"}
        assert client.post(path, json=payload, headers=headers).status_code == 201
        assert client.post(path, json=payload, headers=headers).status_code == 201
        assert len(calls) == 0  # Release 4 keeps replies in the sandbox.
        with factory() as db:
            outgoing = db.query(models.OutboundMessage).one()
            assert outgoing.status == "sandbox_sent"
            assert outgoing.provider == "sandbox_whatsapp"
        with factory() as db:
            db.get(models.InboundMessage, incoming_id).received_at = (
                datetime.now(timezone.utc) - timedelta(hours=25))
            db.commit()
        assert client.post(path, json={**payload, "idempotency_key": str(uuid4())},
                           headers=headers).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_shopify_case_requires_fresh_matching_balance_before_resume(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    monkeypatch.setattr(shopify, "configured", lambda: True)
    order = {"id": "gid://shopify/Order/1", "cancelledAt": None,
             "paymentTerms": {"paymentSchedules": {"nodes": [{
                 "id": "gid://shopify/PaymentSchedule/1", "dueAt": str(date.today()) + "T00:00:00Z",
                 "balanceDue": {"amount": "80.00", "currencyCode": "INR"}}]}}}
    monkeypatch.setattr(shopify, "fetch_order", lambda *_: order)
    try:
        inv_id = invoice(factory, source_system="shopify",
                         source_record_id="gid://shopify/PaymentSchedule/1",
                         source_order_id="gid://shopify/Order/1",
                         requires_human_review=True, contact_suppressed=True)
        headers = {"X-RECOVERFLOW-API-KEY": "test-key"}
        assert client.post(f"/api/v1/cases/{inv_id}/resume", headers=headers,
                           json={"reason": "Reviewed"}).status_code == 409
        path = f"/api/v1/sync/shopify/cases/{inv_id}/confirm"
        assert client.post(path, headers=headers, json={"reason": "Checked in Shopify"}).status_code == 409
        order["paymentTerms"]["paymentSchedules"]["nodes"][0]["balanceDue"]["amount"] = "100.00"
        assert client.post(path, headers=headers, json={"reason": "Checked in Shopify"}).status_code == 409
        confirmed = client.post(path, headers=headers, json={
            "reason": "Checked in Shopify", "accept_due_date_change": True})
        assert confirmed.status_code == 200, confirmed.text
        with factory() as db:
            inv = db.get(models.Invoice, inv_id)
            assert not inv.requires_human_review and inv.contact_suppressed
        assert client.post(f"/api/v1/cases/{inv_id}/resume", headers=headers,
                           json={"reason": "Balance checked and contact approved"}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_release2_tables_and_columns_migrate_existing_database(tmp_path, monkeypatch):
    path = tmp_path / "previous-release.db"
    schema = Path(db_manager.__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with sqlite3.connect(path) as conn:
        conn.executescript(schema)
    monkeypatch.setattr(settings, "APEX_DB_PATH", str(path))
    monkeypatch.setattr(db_manager, "engine", create_engine(f"sqlite:///{path}"))
    db_manager.init_db()
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(invoices)")}
        assert {"counterparty_phone", "source_order_id"} <= columns
        for table in ("integration_connections", "payment_links", "provider_events",
                      "collection_policies", "inbound_messages", "outbound_messages"):
            assert conn.execute("SELECT name FROM sqlite_master WHERE name=?", (table,)).fetchone()


def test_razorpay_request_uses_paise_and_seven_day_expiry(monkeypatch):
    from app.services import razorpay
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_fake")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "hook-secret")
    monkeypatch.setattr(settings, "RAZORPAY_MODE", "test")
    expiry = datetime.now(timezone.utc) + timedelta(days=7)
    observed = {}
    def handler(request):
        observed.update(json.loads(request.content))
        assert request.url.path == "/v1/payment_links/"
        return httpx.Response(200, json={"id": "plink_1", "short_url": "https://rzp.io/i/1"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(razorpay.httpx, "Client", lambda **_: client)
    link = models.PaymentLink(id=1, amount_cents=12345, currency="INR", expires_at=expiry)
    inv = models.Invoice(invoice_number="RF-123", counterparty_name="Customer")
    assert razorpay.create_remote_link(link, inv)["id"] == "plink_1"
    assert observed["amount"] == 12345 and observed["currency"] == "INR"
    assert observed["expire_by"] == int(expiry.timestamp())
    assert observed["notify"] == {"sms": False, "email": False}


def test_uncertain_razorpay_creation_recovers_by_reference_without_new_link(monkeypatch):
    client, factory = client_with_db(monkeypatch)
    from app.services import razorpay
    try:
        inv_id = invoice(factory)
        with factory() as db:
            db.add(models.PaymentLink(tenant_id="local", invoice_id=inv_id,
                provider="razorpay", idempotency_key="recover-test", amount_cents=10000,
                currency="INR", status="needs_review"))
            db.commit()
            link_id = db.query(models.PaymentLink.id).one()[0]
        monkeypatch.setattr(razorpay, "find_remote_link", lambda link: {
            "id": "plink_recovered", "url": "https://rzp.io/i/recovered", "status": "created"})
        path = f"/api/v1/payments/links/{link_id}/recover"
        result = client.post(path, headers={"X-RECOVERFLOW-API-KEY": "test-key"})
        assert result.status_code == 200 and result.json()["status"] == "open"
        assert client.post(path, headers={"X-RECOVERFLOW-API-KEY": "test-key"}).status_code == 409
        with factory() as db:
            assert db.query(models.PaymentLink).count() == 1
    finally:
        app.dependency_overrides.clear()
