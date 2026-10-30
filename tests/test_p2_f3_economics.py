"""P2 F3: unit-economics report — measured usage stays separate from
priced assumptions; computed lines, sensitivity, and pending inputs."""
import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app

ADMIN = {"X-RECOVERFLOW-API-KEY": "f3-admin"}


@pytest.fixture()
def f3db(monkeypatch, tmp_path):
    db_path = tmp_path / "f3.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "f3-admin")
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    now = datetime.utcnow()
    old = now - timedelta(days=60)
    with factory() as db:
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-F3", invoice_type="AR",
            counterparty_name="Acme Traders",
            issue_date=date(2026, 1, 1), due_date=date(2026, 2, 1),
            amount=Decimal("2000"), total_amount=Decimal("2000"),
            face_amount_cents=200000, currency="INR"))
        db.commit()
        invoice = db.query(models.Invoice).one().id
        db.add(models.SupervisorTask(
            tenant_id="local", invoice_id=invoice, kind="resolution",
            status="done", idempotency_key="local:f3:a",
            model_calls=1500, elapsed_ms=45000, created_at=now))
        db.add(models.SupervisorTask(
            tenant_id="local", invoice_id=invoice, kind="verification",
            status="done", idempotency_key="local:f3:b",
            model_calls=500, elapsed_ms=15000, created_at=now))
        db.add(models.SupervisorTask(
            tenant_id="other", invoice_id=None, kind="resolution",
            status="done", idempotency_key="other:f3:x",
            model_calls=99999, created_at=now))
        db.add(models.SupervisorTask(
            tenant_id="local", invoice_id=invoice, kind="resolution",
            status="done", idempotency_key="local:f3:old",
            model_calls=777, created_at=old))
        inbound = models.InboundMessage(
            tenant_id="local", provider="meta_whatsapp",
            external_id="wamid.f3seed", sender="919811111111",
            body="seed", status="triaged", invoice_id=invoice)
        db.add(inbound)
        db.flush()
        for key, status in (("local:f3:m1", "sent"), ("local:f3:m2", "sent"),
                            ("local:f3:m3", "failed")):
            db.add(models.OutboundMessage(
                tenant_id="local", inbound_id=inbound.id, invoice_id=invoice,
                idempotency_key=key, provider="meta_whatsapp",
                recipient="919811111111", body="nudge", status=status,
                created_at=now))
        db.add(models.ReceivableEntry(
            tenant_id="local", invoice_id=invoice, kind="payment",
            amount_cents=-50000, currency="INR", source="razorpay",
            reference="pay_f31", actor="webhook", created_at=now))
        db.add(models.ReceivableEntry(
            tenant_id="local", invoice_id=invoice, kind="payment",
            amount_cents=-150000, currency="INR", source="razorpay",
            reference="pay_f32", actor="webhook", created_at=now))
        db.add(models.ReceivableEntry(
            tenant_id="local", invoice_id=invoice, kind="payment",
            amount_cents=-10000, currency="USD", source="manual",
            reference="man_f33", actor="staff", created_at=now))
        db.add(models.ReceivableEntry(
            tenant_id="local", invoice_id=invoice, kind="reversal",
            amount_cents=50000, currency="INR", source="reversal",
            reference="2", actor="staff", created_at=now))
        db.add(models.StoredDocument(
            id="f30000000000000000000000000001", tenant_id="local",
            invoice_id=invoice, origin="staff",
            original_filename="scan.pdf", stored_name="s.pdf",
            mime_type="application/pdf", size_bytes=1073741824,
            sha256="ab" * 32, scan_status="clean", uploaded_by="staff"))
        db.add(models.StoredDocument(
            id="f30000000000000000000000000002", tenant_id="local",
            invoice_id=invoice, origin="staff",
            original_filename="gone.pdf", stored_name="g.pdf",
            mime_type="application/pdf", size_bytes=999999,
            sha256="cd" * 32, scan_status="clean", uploaded_by="staff",
            deleted_at=now))
        db.add(models.IntakeUpload(
            id="f3-intake", tenant_id="local", actor="staff",
            filename="upload.csv", mime_type="text/csv",
            source_path="/tmp/f3.csv", size_bytes=100, status="done",
            stage="Done", created_at=now))
        db.commit()
    yield {"client": TestClient(app), "factory": factory, "engine": engine,
           "invoice": invoice}
    engine.dispose()


def _report(f3db, days=30):
    resp = f3db["client"].get("/api/v1/system/economics",
                              params={"period_days": days}, headers=ADMIN)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _set_price(f3db, key, value):
    resp = f3db["client"].put("/api/v1/integrations/settings",
                              json={"key": key, "value": value}, headers=ADMIN)
    assert resp.status_code == 200, resp.text


def test_measured_usage_counts_only_this_tenant_and_window(f3db):
    measured = _report(f3db)["measured"]
    assert measured["model_calls"] == 2000
    assert measured["model_tasks"] == 2
    assert measured["model_elapsed_ms_total"] == 60000
    assert measured["outbound_messages"] == {
        "total": 3, "by_status": {"sent": 2, "failed": 1}}
    assert measured["posted_payments"]["count"] == 3
    assert measured["posted_payments"]["volume_cents_by_currency"] == {
        "INR": 200000, "USD": 10000}
    assert measured["posted_payments"]["reversals"] == 1
    # Live rows only: the soft-deleted document's bytes are excluded.
    assert measured["storage_bytes"] == {"documents": 1073741824,
                                         "intake": 100}
    assert measured["cases_with_tasks"] == 1


def test_default_assumptions_are_zero_and_flagged(f3db):
    report = _report(f3db)
    assert report["currency"] == "INR"
    for key, entry in report["assumptions"].items():
        assert entry["value"] == "0", key
        # The local tenant reads the global config fallback (also zero);
        # other tenants without overrides report source "default".
        assert entry["source"] == "global_setting", key
    assert report["computed"]["total"] == "0.00"
    assert report["computed"]["per_case"] == "0.00"
    assert any("willingness_to_pay" in item for item in report["pending"])
    assert any("unit price" in item for item in report["pending"])
    assert any("not instrumented" in item for item in report["pending"])
    assert any("USD" in item for item in report["pending"])


def test_priced_assumptions_drive_computed_lines(f3db):
    _set_price(f3db, "cost_per_1k_model_calls", "40")
    _set_price(f3db, "cost_per_outbound_msg", "0.80")
    _set_price(f3db, "cost_payment_fee_pct", "2")
    _set_price(f3db, "cost_payment_fee_flat", "3")
    _set_price(f3db, "cost_per_gb_month_storage", "20")
    _set_price(f3db, "cost_monthly_infra", "1500")
    _set_price(f3db, "cost_monthly_support", "3000")
    report = _report(f3db)
    assert report["assumptions"]["cost_per_1k_model_calls"]["source"] == \
        "tenant_setting"
    lines = report["computed"]["lines"]
    # 2000 calls @ 40/1k = 80; 3 msgs @ 0.80 = 2.40;
    # INR 2000 @ 2% + 2 INR payments @ 3 = 46 (USD excluded, never converted);
    # ~1 GB-month @ 20 ~= 20.00.
    assert lines["model"] == "80.00"
    assert lines["messaging"] == "2.40"
    assert lines["payment_fees"] == "46.00"
    assert lines["storage"] == "20.00"
    assert lines["infra"] == "1500.00"
    assert lines["support"] == "3000.00"
    assert report["computed"]["total"] == "4648.40"
    assert report["computed"]["per_case"] == "4648.40"
    assert report["computed"]["per_business"] == "4648.40"


def test_changing_a_price_leaves_measured_usage_stable(f3db):
    before = _report(f3db)["measured"]
    _set_price(f3db, "cost_per_1k_model_calls", "999")
    after = _report(f3db)
    assert after["measured"] == before
    assert after["computed"]["lines"]["model"] == "1998.00"


def test_sensitivity_scales_variable_lines_only(f3db):
    _set_price(f3db, "cost_per_1k_model_calls", "40")
    _set_price(f3db, "cost_monthly_infra", "1500")
    report = _report(f3db)
    # Variable 80.00, fixed 1500.00.
    assert report["sensitivity"]["volume_up_20pct"]["total"] == "1596.00"
    assert report["sensitivity"]["volume_down_20pct"]["total"] == "1564.00"


def test_invalid_price_and_window_are_rejected(f3db):
    bad = f3db["client"].put("/api/v1/integrations/settings",
                             json={"key": "cost_per_1k_model_calls",
                                   "value": "-5"},
                             headers=ADMIN)
    assert bad.status_code == 422
    bad_pct = f3db["client"].put("/api/v1/integrations/settings",
                                 json={"key": "cost_payment_fee_pct",
                                       "value": "101"},
                                 headers=ADMIN)
    assert bad_pct.status_code == 422
    bad_cur = f3db["client"].put("/api/v1/integrations/settings",
                                 json={"key": "cost_currency", "value": "xx"},
                                 headers=ADMIN)
    assert bad_cur.status_code == 422
    bad_window = f3db["client"].get(
        "/api/v1/system/economics", params={"period_days": 400},
        headers=ADMIN)
    assert bad_window.status_code == 400
    assert _report(f3db)["computed"]["total"] == "0.00"
