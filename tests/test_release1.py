"""Release 1 assisted collections: import, balance, review, and durable jobs."""
from datetime import date, timedelta
from types import SimpleNamespace
import sys
from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base, get_db
from app.database import db_manager
from app.main import app
from app.skills.extract_invoice_fields import extract_invoice_fields
from app.skills.generate_dunning_email import generate_dunning_email
from app import worker
from app.api import invoices


def _client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "release-one-secret")
    return TestClient(app), factory


def _headers():
    return {"X-RECOVERFLOW-API-KEY": "release-one-secret"}


def test_import_balance_reply_and_draft_approval(monkeypatch):
    client, factory = _client(monkeypatch)
    due = date.today() - timedelta(days=10)
    issue = due - timedelta(days=30)
    csv_body = ("external_id,invoice_number,customer_name,customer_email,issue_date,due_date,amount,currency\n"
                f"sale-1,R-1,Customer,buyer@example.com,{issue},{due},100.00,USD\n")
    try:
        first = client.post("/api/v1/imports/receivables/csv", headers={**_headers(), "Content-Type": "text/csv"}, content=csv_body)
        assert first.status_code == 200, first.text
        assert first.json() == {"imported": 1, "skipped": 0}
        repeated = client.post("/api/v1/imports/receivables/csv", headers={**_headers(), "Content-Type": "text/csv"}, content=csv_body)
        assert repeated.json() == {"imported": 0, "skipped": 1}
        case = client.get("/api/v1/cases", headers=_headers()).json()[0]
        invoice_id = case["invoice_id"]
        assert case["balance_cents"] == 10000
        entry = client.post(f"/api/v1/cases/{invoice_id}/entries", headers=_headers(),
                            json={"kind": "payment", "amount": "40.00", "reference": "receipt-1"})
        assert entry.status_code == 201, entry.text
        assert entry.json()["balance_cents"] == 6000
        same = client.post(f"/api/v1/cases/{invoice_id}/entries", headers=_headers(),
                           json={"kind": "payment", "amount": "40.00", "reference": "receipt-1"})
        assert same.status_code == 201 and same.json()["balance_cents"] == 6000
        aging = client.get("/api/v1/reports/ar-aging", headers=_headers()).json()
        assert aging["total"] == 60
        draft = client.post(f"/api/v1/dunning/trigger-stage?invoice_id={invoice_id}&stage=1", headers=_headers())
        assert draft.status_code == 200, draft.text
        assert "USD 60.00" in draft.json()["email_data"]["body"]
        with factory() as db:
            campaign_id = db.query(models.DunningCampaign.id).first()[0]
        assert client.post(f"/api/v1/dunning/campaigns/{campaign_id}/send", headers=_headers()).status_code == 409
        second = client.post(f"/api/v1/cases/{invoice_id}/entries", headers=_headers(),
                             json={"kind": "payment", "amount": "10.00", "reference": "receipt-2"})
        assert second.status_code == 201
        assert client.post(f"/api/v1/dunning/campaigns/{campaign_id}/approve", headers=_headers()).status_code == 409
        assert client.post(f"/api/v1/dunning/campaigns/{campaign_id}/refresh", headers=_headers()).status_code == 200
        assert client.post(f"/api/v1/dunning/campaigns/{campaign_id}/approve", headers=_headers()).status_code == 200
        reply = client.post(f"/api/v1/cases/{invoice_id}/replies", headers=_headers(),
                            json={"category": "opt_out", "body": "Please stop emailing me."})
        assert reply.status_code == 201
        assert client.post(f"/api/v1/dunning/campaigns/{campaign_id}/send", headers=_headers()).status_code == 409
        assert client.post(f"/api/v1/cases/{invoice_id}/resume", headers=_headers(),
                           json={"reason": "Customer called to discuss"}).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_reconciliation_allocates_once(monkeypatch):
    client, factory = _client(monkeypatch)
    try:
        with factory() as db:
            for number in ("A", "B"):
                invoice = models.Invoice(tenant_id="local", invoice_number=number, invoice_type="AR",
                    counterparty_name="Customer", issue_date=date.today() - timedelta(days=35),
                    due_date=date.today() - timedelta(days=5), amount=100, total_amount=100,
                    face_amount_cents=10000, status="pending")
                db.add(invoice)
                db.flush()
                db.add(models.Reconciliation(tenant_id="local", invoice_id=invoice.id,
                    afis_transaction_id=7, match_type="test", confidence_score=.97,
                    matched_amount=40, status="pending_review"))
            db.commit()
            ids = [row[0] for row in db.query(models.Reconciliation.id).order_by(models.Reconciliation.id).all()]
        assert client.post(f"/api/v1/reconciliation/{ids[0]}/approve", headers=_headers()).status_code == 200
        assert client.post(f"/api/v1/reconciliation/{ids[1]}/approve", headers=_headers()).status_code == 409
        cases = client.get("/api/v1/cases", headers=_headers()).json()
        assert sorted(item["balance_cents"] for item in cases) == [6000, 10000]
    finally:
        app.dependency_overrides.clear()


def test_ocr_uses_its_dependencies(monkeypatch):
    monkeypatch.setitem(sys.modules, "pdf2image", SimpleNamespace(convert_from_path=lambda *a, **k: [object()]))
    monkeypatch.setitem(sys.modules, "pytesseract", SimpleNamespace(
        pytesseract=SimpleNamespace(tesseract_cmd=""),
        image_to_string=lambda *a, **k: "Customer\nInvoice INV123\n01/01/2026 01/31/2026\n$120.00"))
    fields = extract_invoice_fields("sample.pdf")
    assert fields.total_amount == 120
    assert fields.counterparty_name == "Customer"


def test_worker_claims_persisted_job(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(models.ProcessingJob(id="persisted", tenant_id="local", source_path="invoice.pdf", status="queued"))
        db.commit()
    monkeypatch.setattr(worker, "SessionLocal", factory)
    def complete(job_id):
        with factory() as db:
            job = db.get(models.ProcessingJob, job_id)
            job.status = "completed"
            db.commit()
    monkeypatch.setattr(worker, "process_invoice_pipeline", complete)
    assert worker.run_once() is True
    assert worker.run_once() is False
    with factory() as db:
        job = db.get(models.ProcessingJob, "persisted")
        assert job.status == "completed" and job.attempts == 1


def test_dso_snapshot_uses_outstanding_balance(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        invoice = models.Invoice(tenant_id="local", invoice_number="DSO-1", invoice_type="AR",
            counterparty_name="Customer", issue_date=date.today() - timedelta(days=5),
            due_date=date.today() - timedelta(days=1), amount=100, total_amount=100,
            face_amount_cents=10000, status="partially_matched")
        db.add(invoice)
        db.flush()
        db.add(models.ReceivableEntry(tenant_id="local", invoice_id=invoice.id,
            kind="payment", amount_cents=-4000, currency="USD", source="manual",
            reference="dso-receipt", actor="staff"))
        db.commit()
    monkeypatch.setattr(worker, "SessionLocal", factory)
    worker.refresh_dso_snapshots()
    with factory() as db:
        snapshot = db.query(models.DSOSnapshot).one()
        assert snapshot.dso_days == 18
        assert snapshot.ar_balance == 60
        assert snapshot.overdue_amount == 60


def test_ar_pdf_waits_for_staff_confirmation(monkeypatch):
    client, factory = _client(monkeypatch)
    monkeypatch.setattr(invoices, "SessionLocal", factory)
    with factory() as db:
        db.add(models.ProcessingJob(id="ar-job", tenant_id="local", actor="staff",
                                    source_path="sample.pdf", invoice_type="AR", status="queued"))
        db.commit()
    state = {"invoice_data": {"invoice_number": "AR-11", "counterparty_name": "Customer",
             "issue_date": "2026-01-01", "due_date": "2026-01-10", "total_amount": 100},
             "extracted_confidence": .9, "requires_human_review": False}
    monkeypatch.setattr(invoices, "recoverflow_orchestrator", SimpleNamespace(invoke=lambda _: state))
    try:
        invoices.process_invoice_pipeline("ar-job")
        job = client.get("/api/v1/invoices/jobs/ar-job", headers=_headers()).json()
        assert job["status"] == "needs_review"
        invoice_id = job["invoice_id"]
        assert client.post(f"/api/v1/dunning/trigger-stage?invoice_id={invoice_id}&stage=1",
                           headers=_headers()).status_code == 409
        reviewed = client.put(f"/api/v1/invoices/{invoice_id}/review", headers=_headers(), json={
            "invoice_number": "AR-11", "invoice_type": "AR", "counterparty_name": "Customer",
            "issue_date": "2026-01-01", "due_date": "2026-01-10", "total_amount": "100.00",
            "currency": "USD"})
        assert reviewed.status_code == 200, reviewed.text
        assert client.get("/api/v1/invoices/jobs/ar-job", headers=_headers()).json()["status"] == "completed"
    finally:
        app.dependency_overrides.clear()


def test_reversal_requires_admin_and_cannot_repeat(monkeypatch):
    client, factory = _client(monkeypatch)
    try:
        with factory() as db:
            invoice = models.Invoice(tenant_id="local", invoice_number="REV-1", invoice_type="AR",
                counterparty_name="Customer", issue_date=date.today() - timedelta(days=30),
                due_date=date.today() - timedelta(days=1), amount=100, total_amount=100,
                face_amount_cents=10000)
            db.add(invoice)
            db.commit()
            invoice_id = invoice.id
        posted = client.post(f"/api/v1/cases/{invoice_id}/entries", headers=_headers(),
                             json={"kind": "payment", "amount": "40.00", "reference": "receipt-reverse"})
        entry_id = posted.json()["entry_id"]
        path = f"/api/v1/cases/{invoice_id}/entries/{entry_id}/reverse"
        reversed_result = client.post(path, headers=_headers(), json={"reason": "Receipt was voided"})
        assert reversed_result.status_code == 201, reversed_result.text
        assert reversed_result.json()["balance_cents"] == 10000
        assert client.post(path, headers=_headers(), json={"reason": "Receipt was voided"}).status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_manual_contact_is_recorded_and_cooldown_applies(monkeypatch):
    client, factory = _client(monkeypatch)
    try:
        with factory() as db:
            invoice = models.Invoice(tenant_id="local", invoice_number="CONTACT-1", invoice_type="AR",
                counterparty_name="Customer", issue_date=date.today() - timedelta(days=70),
                due_date=date.today() - timedelta(days=50), amount=100, total_amount=100,
                face_amount_cents=10000)
            db.add(invoice)
            db.commit()
            invoice_id = invoice.id
        for stage in (1, 2):
            result = client.post(f"/api/v1/dunning/trigger-stage?invoice_id={invoice_id}&stage={stage}",
                                 headers=_headers())
            assert result.status_code == 200, result.text
        with factory() as db:
            ids = [row[0] for row in db.query(models.DunningCampaign.id).order_by(models.DunningCampaign.id).all()]
        for campaign_id in ids:
            assert client.post(f"/api/v1/dunning/campaigns/{campaign_id}/approve", headers=_headers()).status_code == 200
        first = client.post(f"/api/v1/dunning/campaigns/{ids[0]}/record-contact", headers=_headers(),
                            json={"channel": "phone", "reference": "call-log-1"})
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "contacted_manually"
        blocked = client.post(f"/api/v1/dunning/campaigns/{ids[1]}/record-contact", headers=_headers(),
                              json={"channel": "email", "reference": "outbox-2"})
        assert blocked.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_existing_schema_gains_release_one_columns(tmp_path, monkeypatch):
    path = tmp_path / "existing.db"
    schema = Path(db_manager.__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with sqlite3.connect(path) as conn:
        conn.executescript(schema)
    monkeypatch.setattr(settings, "APEX_DB_PATH", str(path))
    monkeypatch.setattr(db_manager, "engine", create_engine(f"sqlite:///{path}"))
    db_manager.init_db()
    with sqlite3.connect(path) as conn:
        invoice_columns = {row[1] for row in conn.execute("PRAGMA table_info(invoices)")}
        campaign_columns = {row[1] for row in conn.execute("PRAGMA table_info(dunning_campaigns)")}
        job_columns = {row[1] for row in conn.execute("PRAGMA table_info(processing_jobs)")}
        assert {"face_amount_cents", "source_system", "contact_opt_out"} <= invoice_columns
        assert {"approved_by", "balance_cents_at_draft", "contacted_at"} <= campaign_columns
        assert {"invoice_type", "attempts", "locked_until"} <= job_columns
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='receivable_entries'").fetchone()


def test_collection_templates_make_no_legal_claims():
    invoice = {"invoice_number": "R-1", "total_amount": 100, "due_date": "2026-01-01"}
    for stage in (3, 4):
        result = generate_dunning_email(invoice, {"name": "Customer"}, 50, stage, "Store")
        body = result["body"].lower()
        assert "legal action" not in body
        assert "legal department" not in body
        assert "referred" not in body
