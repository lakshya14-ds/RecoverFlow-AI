"""P2 D3: comms policy — templates, consent, quiet hours, language, delivery
tracking, and replies routed into the case lifecycle. Sandbox unless a
channel is explicitly enabled (and live HTTP is never attempted in tests)."""
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app

ADMIN = {"X-RECOVERFLOW-API-KEY": "d3-admin"}
EDITOR = {"X-RECOVERFLOW-API-KEY": "d3-editor"}
APP_SECRET = "meta-app-secret-d3"
PHONE_ID = "1234567890"
IST = ZoneInfo("Asia/Kolkata")


@pytest.fixture()
def commdb(monkeypatch, tmp_path):
    db_path = tmp_path / "d3.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "d3-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "d3-editor", "actor": "ed@example.in", "tenant_id": "local",
          "role": "editor"}]))
    monkeypatch.setattr(settings, "META_WHATSAPP_APP_SECRET", APP_SECRET)
    monkeypatch.setattr(settings, "META_WHATSAPP_PHONE_NUMBER_ID", PHONE_ID)
    monkeypatch.setattr(settings, "WHATSAPP_ENABLED", False)
    monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-D3", invoice_type="AR",
            counterparty_name="D3 Party",
            counterparty_phone="+91-98765-43210",
            counterparty_email="party@example.in",
            issue_date=date(2026, 1, 1), due_date=date(2026, 2, 1),
            amount=Decimal("1000"), total_amount=Decimal("1000"),
            face_amount_cents=100000, currency="INR"))
        db.commit()
        invoice = db.query(models.Invoice).one().id
    yield {"client": TestClient(app), "factory": factory, "engine": engine,
           "invoice": invoice}
    engine.dispose()


def _inbound(commdb, body="Where is my bill?", received_at=None):
    with commdb["factory"]() as db:
        row = models.InboundMessage(
            tenant_id="local", provider="meta_whatsapp",
            external_id="wamid." + uuid.uuid4().hex[:12],
            sender="919876543210", body=body, status="needs_review",
            received_at=received_at or datetime.now(timezone.utc))
        db.add(row)
        db.commit()
        return row.id


def _triaged(commdb, category="question", **kwargs):
    client = commdb["client"]
    message_id = _inbound(commdb, **kwargs)
    res = client.post(f"/api/v1/messages/{message_id}/triage", headers=EDITOR,
                      json={"invoice_id": commdb["invoice"],
                            "category": category})
    assert res.status_code == 200, res.text
    return message_id


def _template(client, name="bill_reminder", body="Namaste, invoice {{1}} of INR {{2}} is due.",
              language="en"):
    created = client.post("/api/v1/messages/templates", headers=EDITOR,
                          json={"name": name, "language": language,
                                "category": "utility", "body": body})
    assert created.status_code == 201, created.text
    approved = client.post(
        f"/api/v1/messages/templates/{created.json()['id']}/approve",
        headers=ADMIN)
    assert approved.status_code == 200, approved.text
    return created.json()["id"]


def _consent(client, invoice, channel="whatsapp", language="en"):
    res = client.put("/api/v1/messages/preferences", headers=EDITOR,
                     json={"invoice_id": invoice, "channel": channel,
                           "opted_in": True, "basis": "explicit",
                           "language": language})
    assert res.status_code == 200, res.text


def _reply(client, message_id, body="Hello", key=None, **extra):
    return client.post(f"/api/v1/messages/{message_id}/reply", headers=EDITOR,
                       json={"body": body,
                             "idempotency_key": key or str(uuid.uuid4()),
                             **extra})


def test_template_lifecycle(commdb):
    client = commdb["client"]
    created = client.post("/api/v1/messages/templates", headers=EDITOR,
                          json={"name": "t1", "body": "Hi {{1}}"})
    assert created.json()["status"] == "draft"
    template_id = created.json()["id"]
    assert client.post(f"/api/v1/messages/templates/{template_id}/approve",
                       headers=EDITOR).status_code == 403
    assert client.post("/api/v1/messages/templates", headers=EDITOR,
                       json={"name": "t1", "body": "Hi"}).status_code == 409
    assert client.post("/api/v1/messages/templates", headers=EDITOR,
                       json={"name": "bad", "body": "Hi {{2}}"}) \
        .status_code == 422
    assert client.post("/api/v1/messages/templates", headers=EDITOR,
                       json={"name": "bad2", "body": "Hi {{x}}"}) \
        .status_code == 422
    assert client.post("/api/v1/messages/templates", headers=EDITOR,
                       json={"name": "bad3", "body": "Hi",
                             "language": "xx"}).status_code == 422
    assert client.post(f"/api/v1/messages/templates/{template_id}/approve",
                       headers=ADMIN).json()["status"] == "approved"
    assert client.post(f"/api/v1/messages/templates/{template_id}/archive",
                       headers=ADMIN).json()["status"] == "archived"
    names = [item["name"] for item in
             client.get("/api/v1/messages/templates",
                        headers=EDITOR).json()]
    assert "t1" in names


def test_preferences(commdb):
    client = commdb["client"]
    invoice = commdb["invoice"]
    assert client.get("/api/v1/messages/preferences",
                      params={"invoice_id": invoice},
                      headers=EDITOR).json() == []
    _consent(client, invoice, language="hi")
    prefs = client.get("/api/v1/messages/preferences",
                       params={"invoice_id": invoice},
                       headers=EDITOR).json()
    assert prefs == [{"channel": "whatsapp", "opted_in": True,
                      "basis": "explicit", "language": "hi"}]
    bad = client.put("/api/v1/messages/preferences", headers=EDITOR,
                     json={"invoice_id": invoice, "channel": "sms",
                           "opted_in": True})
    assert bad.status_code == 422
    assert client.put("/api/v1/messages/preferences", headers=EDITOR,
                      json={"invoice_id": 99999, "channel": "whatsapp",
                            "opted_in": True}).status_code == 404


def test_triage_routes_into_lifecycle(commdb):
    client = commdb["client"]
    invoice = commdb["invoice"]
    message_id = _inbound(commdb, body="Two cartons were missing")
    res = client.post(f"/api/v1/messages/{message_id}/triage", headers=EDITOR,
                      json={"invoice_id": invoice, "category": "dispute"})
    assert res.status_code == 200
    with commdb["factory"]() as db:
        row = db.get(models.Invoice, invoice)
        assert row.dispute_open is True
        assert row.status == "disputed"
        message = db.query(models.CustomerMessage).filter_by(
            invoice_id=invoice).one()
        assert message.source == "meta_whatsapp"
        assert message.category == "dispute"
        assert db.query(models.AuditEvent).filter(
            models.AuditEvent.action.in_(
                ["supervisor_task_queued", "supervisor_reassessed"])).count() >= 1
    again = client.post(f"/api/v1/messages/{message_id}/triage",
                        headers=EDITOR,
                        json={"invoice_id": invoice, "category": "dispute"})
    assert again.status_code == 409


def test_in_window_reply_sandbox(commdb):
    client = commdb["client"]
    message_id = _triaged(commdb)
    key = str(uuid.uuid4())
    res = _reply(client, message_id, body="Your bill is ready.", key=key,
                 language="hi")
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "sandbox_sent"
    assert res.json()["language"] == "hi"
    assert res.json()["provider"] == "sandbox_whatsapp"
    replay = _reply(client, message_id, body="Your bill is ready.", key=key)
    assert replay.json()["id"] == res.json()["id"]
    clash = _reply(client, message_id, body="Different words", key=key)
    assert clash.status_code == 409
    with commdb["factory"]() as db:
        assert db.query(models.OutboundMessage).count() == 1


def test_expired_window_needs_template(commdb):
    client = commdb["client"]
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    message_id = _triaged(commdb, received_at=old)
    assert _reply(client, message_id).status_code == 409


def test_template_reply_after_expiry(commdb):
    client = commdb["client"]
    invoice = commdb["invoice"]
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    message_id = _triaged(commdb, received_at=old)
    template_id = _template(client)
    no_consent = _reply(client, message_id, template_id=template_id,
                        variables=["INV-D3", "1000"])
    assert no_consent.status_code == 409
    _consent(client, invoice)
    short = _reply(client, message_id, template_id=template_id,
                   variables=["INV-D3"])
    assert short.status_code == 409
    sent = _reply(client, message_id, template_id=template_id,
                  variables=["INV-D3", "1000"])
    assert sent.status_code == 201, sent.text
    assert "INV-D3" in sent.json()["body"]
    assert sent.json()["template_id"] == template_id
    assert sent.json()["status"] == "sandbox_sent"


def test_template_guards(commdb):
    client = commdb["client"]
    invoice = commdb["invoice"]
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    message_id = _triaged(commdb, received_at=old)
    _consent(client, invoice)
    draft = client.post("/api/v1/messages/templates", headers=EDITOR,
                        json={"name": "draft", "body": "Hi {{1}}"}).json()["id"]
    assert _reply(client, message_id, template_id=draft,
                  variables=["x"]).status_code == 409
    hindi = _template(client, name="hindi", language="hi",
                      body="Namaste {{1}}")
    mismatch = _reply(client, message_id, template_id=hindi,
                      variables=["INV-D3"], language="en")
    assert mismatch.status_code == 409
    waive = _template(client, name="waive",
                      body="We cancel {{1}} as you asked.")
    _consent(client, invoice)
    blocked = _reply(client, message_id, template_id=waive,
                     variables=["INV-D3"])
    assert blocked.status_code == 409
    with commdb["factory"]() as db:
        row = db.get(models.Invoice, invoice)
        row.contact_opt_out = True
        db.commit()
    template_id = _template(client, name="ok2", body="Hi {{1}}")
    assert _reply(client, message_id, template_id=template_id,
                  variables=["x"]).status_code == 409


def _quiet_now(client):
    now = datetime.now(timezone.utc).astimezone(IST)
    start = (now - timedelta(hours=1)).strftime("%H:%M")
    end = (now + timedelta(hours=1)).strftime("%H:%M")
    for key, value in (("comms_quiet_start", start),
                       ("comms_quiet_end", end)):
        res = client.put("/api/v1/integrations/settings", headers=ADMIN,
                         json={"key": key, "value": value})
        assert res.status_code == 200, res.text


def test_quiet_hours_hold_and_release(commdb):
    client = commdb["client"]
    invoice = commdb["invoice"]
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    message_id = _triaged(commdb, received_at=old)
    template_id = _template(client)
    _consent(client, invoice)
    _quiet_now(client)
    held = _reply(client, message_id, template_id=template_id,
                  variables=["INV-D3", "1000"])
    assert held.json()["status"] == "held_quiet_hours"
    assert held.json()["held_until"]
    outbound_id = held.json()["id"]
    assert client.post(f"/api/v1/messages/outbound/{outbound_id}/release",
                       headers=EDITOR).status_code == 409
    fresh_id = _triaged(commdb)
    assert _reply(client, fresh_id, body="Quick answer").json()["status"] == \
        "sandbox_sent"
    later = datetime.now(timezone.utc).astimezone(IST)
    open_start = (later + timedelta(hours=2)).strftime("%H:%M")
    open_end = (later + timedelta(hours=3)).strftime("%H:%M")
    client.put("/api/v1/integrations/settings", headers=ADMIN,
               json={"key": "comms_quiet_start", "value": open_start})
    client.put("/api/v1/integrations/settings", headers=ADMIN,
               json={"key": "comms_quiet_end", "value": open_end})
    released = client.post(f"/api/v1/messages/outbound/{outbound_id}/release",
                           headers=EDITOR)
    assert released.json()["status"] == "sandbox_sent"
    assert client.post(f"/api/v1/messages/outbound/{outbound_id}/release",
                       headers=EDITOR).status_code == 409


def test_live_gate(commdb):
    client = commdb["client"]
    message_id = _triaged(commdb)
    res = client.put("/api/v1/integrations/settings", headers=ADMIN,
                     json={"key": "whatsapp_enabled", "value": "true"})
    assert res.status_code == 200
    blocked = _reply(client, message_id, body="Hello live")
    assert blocked.status_code in (409, 502)
    with commdb["factory"]() as db:
        assert db.query(models.OutboundMessage).count() == 0
    bad = client.put("/api/v1/integrations/settings", headers=ADMIN,
                     json={"key": "whatsapp_enabled", "value": "maybe"})
    assert bad.status_code == 422


def _meta_status(commdb, statuses):
    client = commdb["client"]
    payload = {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": PHONE_ID},
        "statuses": statuses}}]}]}
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(APP_SECRET.encode(), body,
                               hashlib.sha256).hexdigest()
    return client.post("/api/v1/webhooks/meta-whatsapp/local", content=body,
                       headers={"X-Hub-Signature-256": sig,
                                "Content-Type": "application/json"})


def test_delivery_receipts(commdb):
    client = commdb["client"]
    invoice = commdb["invoice"]
    message_id = _triaged(commdb)
    sent = _reply(client, message_id, body="Status me")
    outbound_id = sent.json()["id"]
    with commdb["factory"]() as db:
        row = db.get(models.OutboundMessage, outbound_id)
        row.provider = "meta_whatsapp"
        row.provider_message_id = "wamid.abc123"
        row.status = "sent"
        db.commit()
    res = _meta_status(commdb, [{"id": "wamid.abc123", "status": "delivered"}])
    assert res.json()["status_updates"] == 1
    with commdb["factory"]() as db:
        row = db.get(models.OutboundMessage, outbound_id)
        assert row.status == "delivered"
        assert row.delivered_at is not None
    res = _meta_status(commdb, [{"id": "wamid.abc123", "status": "failed",
                                 "errors": [{"code": 131047,
                                             "title": "Re-engagement window"}]}])
    assert res.json()["status_updates"] == 1
    with commdb["factory"]() as db:
        row = db.get(models.OutboundMessage, outbound_id)
        assert row.status == "failed"
        assert "131047" in (row.failure_reason or "")
    res = _meta_status(commdb, [{"id": "wamid.unknown", "status": "read"}])
    assert res.json()["ignored"] == 1
    listed = client.get("/api/v1/messages/outbound",
                        params={"invoice_id": invoice},
                        headers=EDITOR).json()
    assert listed[0]["status"] == "failed"


def test_cross_tenant_and_guards(commdb):
    client = commdb["client"]
    with commdb["factory"]() as db:
        db.add(models.Invoice(
            tenant_id="tenant-b", invoice_number="B-1", invoice_type="AR",
            counterparty_name="B", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("10"),
            total_amount=Decimal("10"), face_amount_cents=1000,
            currency="INR"))
        db.add(models.MessageTemplate(
            tenant_id="tenant-b", name="foreign", language="en",
            category="utility", body="Hi", status="approved",
            created_by="x"))
        db.commit()
        foreign_template = db.query(models.MessageTemplate).filter_by(
            tenant_id="tenant-b").one().id
    message_id = _triaged(commdb)
    assert _reply(client, message_id, template_id=foreign_template,
                  variables=["x"]).status_code in (404, 409)
    assert client.get("/api/v1/messages/outbound",
                      params={"invoice_id": 99999},
                      headers=EDITOR).status_code == 404
    assert client.post("/api/v1/messages/outbound/99999/release",
                       headers=EDITOR).status_code == 404
