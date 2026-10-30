"""P2 F1: privacy subject-request workflows — export bundles carry the
subject's data without secrets, corrections stay inside an allowlist, and
deletion erases contact/communication data while keeping ledger rows."""
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

ADMIN = {"X-RECOVERFLOW-API-KEY": "f1-admin"}
EDITOR = {"X-RECOVERFLOW-API-KEY": "f1-editor"}


@pytest.fixture()
def f1db(monkeypatch, tmp_path):
    db_path = tmp_path / "f1.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "f1-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "f1-editor", "actor": "ed@example.in", "tenant_id": "local",
          "role": "editor"}]))
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(models.Counterparty(
            tenant_id="local", name="Acme Traders", type="customer",
            email="acme@example.in", phone="+91-98111-11111",
            address="14 Market Road", display_name="Acme",
            gstin="06ABCDE1234F1Z5"))
        db.add(models.User(tenant_id="local", email="boss@example.in",
                           name="Boss", password_hash="x", role="admin"))
        db.add(models.User(tenant_id="local", email="clerk@example.in",
                           name="Clerk", password_hash="x", role="editor"))
        db.commit()
        cp = db.query(models.Counterparty).filter_by(name="Acme Traders").one()
        boss = db.query(models.User).filter_by(email="boss@example.in").one()
        clerk = db.query(models.User).filter_by(email="clerk@example.in").one()
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-F1", invoice_type="AR",
            counterparty_name="Acme Traders", counterparty_email="acme@example.in",
            counterparty_phone="+91-98111-11111", counterparty_id=cp.id,
            issue_date=date(2026, 1, 1), due_date=date(2026, 2, 1),
            amount=Decimal("1000"), total_amount=Decimal("1000"),
            face_amount_cents=100000, currency="INR", status="paid"))
        db.commit()
        invoice = db.query(models.Invoice).filter_by(invoice_number="INV-F1").one().id
        ids = {"cp": cp.id, "boss": boss.id, "clerk": clerk.id, "invoice": invoice}
    yield {"client": TestClient(app), "factory": factory, "engine": engine, **ids}
    engine.dispose()


def _seed_comms(f1db):
    """Customer + provider messages, evidence, promise, prefs, token, doc."""
    with f1db["factory"]() as db:
        db.add(models.CustomerMessage(
            tenant_id="local", invoice_id=f1db["invoice"], category="dispute",
            body="Short supply of 2 cartons, call +91-98111-11111",
            actor="staff@example.in"))
        inbound = models.InboundMessage(
            tenant_id="local", provider="meta_whatsapp",
            external_id="wamid.f1seed", sender="919811111111",
            body="Paid yesterday, ref UPI/111", status="triaged",
            invoice_id=f1db["invoice"])
        db.add(inbound)
        db.flush()
        db.add(models.OutboundMessage(
            tenant_id="local", inbound_id=inbound.id,
            invoice_id=f1db["invoice"], idempotency_key="local:f1:seed",
            provider="meta_whatsapp", recipient="919811111111",
            body="Reminder: INV-F1 due", status="sent"))
        db.add(models.CaseEvidence(
            tenant_id="local", invoice_id=f1db["invoice"],
            claim_type="dispute_item", title="Short supply",
            description="Customer alleges 2 cartons missing",
            source_type="customer_email", source_reference="portal-upload",
            source_snippet="2 cartons missing, signed Ramesh",
            trust_state="alleged", amount_cents=20000, currency="INR"))
        db.add(models.PromiseToPay(
            tenant_id="local", invoice_id=f1db["invoice"],
            promised_cents=80000, source_text="Will pay Friday - Ramesh",
            extraction_confidence=0.7))
        db.add(models.CommsPreference(
            tenant_id="local", invoice_id=f1db["invoice"],
            channel="whatsapp", opted_in=True, basis="explicit",
            language="hi", updated_by="staff@example.in"))
        db.add(models.PortalToken(
            tenant_id="local", invoice_id=f1db["invoice"],
            token_hash="ab" * 32, prefix="f1prefix",
            created_by="staff@example.in",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=70)))
        db.add(models.StoredDocument(
            id="f10000000000000000000000000001", tenant_id="local",
            invoice_id=f1db["invoice"], origin="portal",
            original_filename="challan.pdf", stored_name="random-name.pdf",
            mime_type="application/pdf", size_bytes=11, sha256="cd" * 32,
            scan_status="pending", uploaded_by="portal"))
        db.commit()


def _create(f1db, kind, subject_type, subject_ref, details=None):
    return f1db["client"].post(
        "/api/v1/privacy/requests",
        json={"kind": kind, "subject_type": subject_type,
              "subject_ref": subject_ref, "details": details or {}},
        headers=ADMIN)


def _walk(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def test_export_bundle_has_data_without_secrets(f1db):
    _seed_comms(f1db)
    created = _create(f1db, "export", "counterparty", f1db["cp"])
    assert created.status_code == 200, created.text
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{created.json()['id']}/fulfill", headers=ADMIN)
    assert fulfilled.status_code == 200, fulfilled.text
    bundle = fulfilled.json()["result"]
    assert bundle["profile"]["email"] == "acme@example.in"
    assert bundle["profile"]["gstin"] == "06ABCDE1234F1Z5"
    assert len(bundle["invoices"]) == 1
    assert bundle["invoices"][0]["total"] == "1000.00"
    assert bundle["customer_messages"][0]["body"].startswith("Short supply")
    assert bundle["inbound_messages"][0]["sender"] == "919811111111"
    assert bundle["outbound_messages"][0]["recipient"] == "919811111111"
    assert bundle["evidence"][0]["trust_state"] == "alleged"
    assert bundle["promises"][0]["source_text"].startswith("Will pay")
    assert bundle["documents"][0]["sha256"] == "cd" * 32
    assert bundle["portal_tokens"][0]["prefix"] == "f1prefix"
    keys = {k.lower() for k in _walk(bundle)}
    for secret in ("password_hash", "key_hash", "token_hash",
                   "body_sha256", "client_secret"):
        assert secret not in keys
    assert fulfilled.json()["request"]["status"] == "fulfilled"


def test_export_is_tenant_scoped(f1db):
    _seed_comms(f1db)
    with f1db["factory"]() as db:
        db.add(models.Counterparty(
            tenant_id="other", name="Acme Traders", type="customer",
            email="other@example.in"))
        db.commit()
        other = db.query(models.Counterparty).filter_by(tenant_id="other").one()
        db.add(models.Invoice(
            tenant_id="other", invoice_number="INV-OTHER", invoice_type="AR",
            counterparty_name="Acme Traders", counterparty_id=other.id,
            issue_date=date(2026, 1, 1), due_date=date(2026, 2, 1),
            amount=Decimal("50"), total_amount=Decimal("50"),
            face_amount_cents=5000, currency="INR"))
        db.commit()
    created = _create(f1db, "access", "counterparty", f1db["cp"])
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{created.json()['id']}/fulfill", headers=ADMIN)
    numbers = [i["invoice_number"] for i in fulfilled.json()["result"]["invoices"]]
    assert numbers == ["INV-F1"]
    # The other tenant's subject id does not resolve in this tenant.
    bad = _create(f1db, "access", "counterparty", 999999)
    assert bad.status_code == 400


def test_correction_applies_allowlisted_fields(f1db):
    created = _create(f1db, "correction", "counterparty", f1db["cp"], {
        "entity": "counterparty",
        "fields": {"phone": "+91-98222-22222", "display_name": "Acme New"}})
    assert created.status_code == 200, created.text
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{created.json()['id']}/fulfill", headers=ADMIN)
    assert fulfilled.status_code == 200, fulfilled.text
    assert fulfilled.json()["result"] == {
        "applied_fields": ["display_name", "phone"]}
    with f1db["factory"]() as db:
        cp = db.query(models.Counterparty).get(f1db["cp"])
        assert cp.phone == "+91-98222-22222"
        assert cp.name == "Acme Traders"
        audit = db.query(models.AuditEvent).filter_by(
            action="privacy_request_fulfilled").all()
        assert audit


def test_correction_rejects_money_identity_and_unknown_fields(f1db):
    for fields in ({"total_invoiced": 0}, {"gstin": "06XXXXX0000X1Z5"},
                   {"name": "Someone Else"}, {"merged_into_id": 1}):
        resp = _create(f1db, "correction", "counterparty", f1db["cp"], {
            "entity": "counterparty", "fields": fields})
        assert resp.status_code == 400, fields
    with f1db["factory"]() as db:
        cp = db.query(models.Counterparty).get(f1db["cp"])
        assert cp.name == "Acme Traders"
        assert cp.gstin == "06ABCDE1234F1Z5"


def test_correction_branch_must_belong_to_subject(f1db):
    with f1db["factory"]() as db:
        db.add(models.Counterparty(
            tenant_id="local", name="Other Party", type="customer"))
        db.commit()
        other = db.query(models.Counterparty).filter_by(name="Other Party").one()
        db.add(models.CounterpartyBranch(
            tenant_id="local", counterparty_id=other.id, name="HQ",
            billing_address="Elsewhere", created_by="staff@example.in"))
        db.commit()
        branch = db.query(models.CounterpartyBranch).filter_by(name="HQ").one().id
    resp = _create(f1db, "correction", "counterparty", f1db["cp"], {
        "entity": "counterparty_branch", "entity_id": branch,
        "fields": {"billing_address": "Forged"}})
    assert resp.status_code == 200
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{resp.json()['id']}/fulfill", headers=ADMIN)
    assert fulfilled.status_code == 400
    assert "does not belong" in fulfilled.text


def test_deletion_blocked_by_open_invoice(f1db):
    with f1db["factory"]() as db:
        db.query(models.Invoice).filter_by(id=f1db["invoice"]).update(
            {"status": "disputed"}, synchronize_session=False)
        db.commit()
    preview = f1db["client"].get(
        "/api/v1/privacy/deletion-check",
        params={"subject_type": "counterparty", "subject_ref": f1db["cp"]},
        headers=ADMIN)
    assert preview.status_code == 200
    assert preview.json()["blocked"] is True
    assert "non-terminal" in preview.json()["blocks"][0]
    created = _create(f1db, "deletion", "counterparty", f1db["cp"])
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{created.json()['id']}/fulfill", headers=ADMIN)
    assert fulfilled.status_code == 400
    with f1db["factory"]() as db:
        cp = db.query(models.Counterparty).get(f1db["cp"])
        assert cp.email == "acme@example.in"


def test_deletion_blocked_by_retention_hold_then_released(f1db):
    _seed_comms(f1db)
    with f1db["factory"]() as db:
        db.query(models.StoredDocument).filter_by(
            id="f10000000000000000000000000001").update(
                {"hold": True, "hold_reason": "tax audit"},
                synchronize_session=False)
        db.commit()
    preview = f1db["client"].get(
        "/api/v1/privacy/deletion-check",
        params={"subject_type": "counterparty", "subject_ref": f1db["cp"]},
        headers=ADMIN)
    assert preview.json()["blocked"] is True
    assert "retention hold" in preview.json()["blocks"][0]
    with f1db["factory"]() as db:
        db.query(models.StoredDocument).filter_by(
            id="f10000000000000000000000000001").update(
                {"hold": False}, synchronize_session=False)
        db.commit()
    created = _create(f1db, "deletion", "counterparty", f1db["cp"])
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{created.json()['id']}/fulfill", headers=ADMIN)
    assert fulfilled.status_code == 200, fulfilled.text


def test_deletion_erases_contact_keeps_ledger(f1db):
    _seed_comms(f1db)
    created = _create(f1db, "deletion", "counterparty", f1db["cp"])
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{created.json()['id']}/fulfill", headers=ADMIN)
    assert fulfilled.status_code == 200, fulfilled.text
    resolution = fulfilled.json()["result"]["resolution"]
    assert "books-of-account" in resolution
    with f1db["factory"]() as db:
        cp = db.query(models.Counterparty).get(f1db["cp"])
        assert cp.email is None and cp.phone is None
        assert cp.address is None and cp.display_name is None
        assert cp.name == "Acme Traders"
        assert cp.gstin == "06ABCDE1234F1Z5"
        invoice = db.query(models.Invoice).get(f1db["invoice"])
        assert invoice.counterparty_email is None
        assert invoice.counterparty_name == "Acme Traders"
        assert invoice.total_amount == Decimal("1000")
        assert invoice.status == "paid"
        msg = db.query(models.CustomerMessage).one()
        assert "privacy request" in msg.body
        inbound = db.query(models.InboundMessage).one()
        assert inbound.sender.startswith("[redacted")
        outbound = db.query(models.OutboundMessage).one()
        assert outbound.recipient.startswith("[redacted")
        evidence = db.query(models.CaseEvidence).one()
        assert evidence.source_snippet is None
        assert evidence.title == "Short supply"
        promise = db.query(models.PromiseToPay).one()
        assert "privacy request" in promise.source_text
        doc = db.query(models.StoredDocument).one()
        assert doc.deleted_at is not None
        token = db.query(models.PortalToken).one()
        assert token.revoked_at is not None
        # Consent records stay: they prove what the business was allowed to do.
        assert db.query(models.CommsPreference).count() == 1
        assert db.query(models.AuditEvent).filter_by(
            action="privacy_request_fulfilled").count() == 1
    # The paid case view still renders after erasure.
    view = f1db["client"].get(f"/api/v1/cases/{f1db['invoice']}", headers=ADMIN)
    assert view.status_code == 200, view.text


def test_staff_deletion_deactivates_login(f1db):
    with f1db["factory"]() as db:
        db.add(models.UserSession(
            tenant_id="local", user_id=f1db["clerk"],
            token_hash="ee" * 32,
            expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
        db.add(models.UserApiKey(
            tenant_id="local", user_id=f1db["clerk"], name="clerk-key",
            key_prefix="rk_ee", key_hash="ff" * 32, role="editor"))
        db.add(models.UserRecoveryToken(
            tenant_id="local", user_id=f1db["clerk"], token_hash="dd" * 32,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            created_by="boss@example.in"))
        db.commit()
    created = _create(f1db, "deletion", "staff_user", f1db["clerk"])
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{created.json()['id']}/fulfill", headers=ADMIN)
    assert fulfilled.status_code == 200, fulfilled.text
    with f1db["factory"]() as db:
        clerk = db.query(models.User).get(f1db["clerk"])
        assert clerk.is_active is False
        assert db.query(models.UserSession).one().is_revoked is True
        assert db.query(models.UserApiKey).one().is_active is False
        assert db.query(models.UserRecoveryToken).one().used_at is not None


def test_staff_self_delete_and_last_admin_are_blocked(f1db):
    own = _create(f1db, "deletion", "staff_user", f1db["boss"])
    # The API-key admin identity is not the boss row, so seed a matching check
    # at the service level instead: the service compares actor email.
    from app.services import privacy as privacy_service
    with f1db["factory"]() as db:
        blocks = privacy_service.check_deletion(
            db, "local", "staff_user", f1db["boss"], "boss@example.in")
        assert any("own login" in b for b in blocks)
    # The boss is the only admin: deletion is blocked even by another actor.
    fulfilled = f1db["client"].post(
        f"/api/v1/privacy/requests/{own.json()['id']}/fulfill", headers=ADMIN)
    assert fulfilled.status_code == 400
    assert "last active admin" in fulfilled.text


def test_reject_needs_reason_and_states_are_terminal(f1db):
    created = _create(f1db, "access", "counterparty", f1db["cp"])
    rid = created.json()["id"]
    review = f1db["client"].post(f"/api/v1/privacy/requests/{rid}/review",
                                 headers=ADMIN)
    assert review.json()["status"] == "in_review"
    empty = f1db["client"].post(f"/api/v1/privacy/requests/{rid}/reject",
                                json={"reason": ""}, headers=ADMIN)
    assert empty.status_code == 400
    rejected = f1db["client"].post(
        f"/api/v1/privacy/requests/{rid}/reject",
        json={"reason": "Requester identity not verified"}, headers=ADMIN)
    assert rejected.json()["status"] == "rejected"
    again = f1db["client"].post(f"/api/v1/privacy/requests/{rid}/fulfill",
                                headers=ADMIN)
    assert again.status_code == 400
    assert "already rejected" in again.text


def test_same_name_does_not_override_explicit_party_link(f1db):
    from app.services import privacy
    with f1db["factory"]() as db:
        other = models.Counterparty(tenant_id="local", name="Acme Traders", type="customer")
        db.add(other)
        db.flush()
        other_invoice = models.Invoice(
            tenant_id="local", invoice_number="INV-OTHER-PARTY", invoice_type="AR",
            counterparty_name="Acme Traders", counterparty_id=other.id,
            counterparty_email="other@example.in", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("100"),
            total_amount=Decimal("100"), face_amount_cents=10000,
            currency="INR", status="pending")
        db.add(other_invoice)
        db.flush()
        bundle = privacy.collect_subject_data(db, "local", "counterparty", f1db["cp"])
        assert [row["id"] for row in bundle["invoices"]] == [f1db["invoice"]]
        assert privacy.check_deletion(db, "local", "counterparty", f1db["cp"]) == []
        req = privacy.create_request(db, "local", "deletion", "counterparty",
                                     f1db["cp"], {}, "admin")
        privacy.fulfill_request(db, req, "admin")
        db.refresh(other_invoice)
        assert other_invoice.counterparty_email == "other@example.in"


def test_editor_cannot_use_privacy_api(f1db):
    denied = f1db["client"].post(
        "/api/v1/privacy/requests",
        json={"kind": "export", "subject_type": "counterparty",
              "subject_ref": f1db["cp"], "details": {}},
        headers=EDITOR)
    assert denied.status_code == 403
    listed = f1db["client"].get("/api/v1/privacy/requests", headers=EDITOR)
    assert listed.status_code == 403
    preview = f1db["client"].get(
        "/api/v1/privacy/deletion-check",
        params={"subject_type": "counterparty", "subject_ref": f1db["cp"]},
        headers=EDITOR)
    assert preview.status_code == 403
