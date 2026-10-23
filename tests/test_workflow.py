from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.api import invoices
from app.agents.orchestrator import route_after_semantic
from app.agents.semantic_approval import evaluate_invoice
from app.agents.dunning_communication import run_dunning_agent
from app.database import models
from app.database.db_manager import Base
from app.database import db_manager
from app.config import settings
from app.main import app
from app.database.db_manager import get_db
import sqlite3


def _session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'recoverflow-test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(invoices, "SessionLocal", factory)
    return factory


def test_pipeline_saves_real_dates_and_match(tmp_path, monkeypatch):
    factory = _session(tmp_path, monkeypatch)
    with factory() as db:
        db.add(models.ProcessingJob(id="job-1", source_path="sample.pdf", tenant_id="team-a"))
        db.commit()
    state = {
        "invoice_data": {
            "invoice_number": "INV-101", "counterparty_name": "Vendor",
            "issue_date": "2026-01-01", "due_date": "2026-01-30",
            "total_amount": 120.0,
        },
        "extracted_confidence": 0.9, "matched_afis_id": 8,
        "matched_amount": 120.0, "reconciliation_confidence": 0.97,
        "match_type": "exact_amount_date", "requires_human_review": False,
    }
    monkeypatch.setattr(invoices, "recoverflow_orchestrator", SimpleNamespace(invoke=lambda _: state))
    invoices.process_invoice_pipeline("job-1")
    with factory() as db:
        job = db.get(models.ProcessingJob, "job-1")
        invoice = db.get(models.Invoice, job.invoice_id)
        assert job.status == "completed"
        assert invoice.issue_date == date(2026, 1, 1)
        assert invoice.tenant_id == "team-a"
        assert db.query(models.Reconciliation).filter_by(invoice_id=invoice.id).count() == 1


def test_manual_review_cannot_be_cleared():
    result = evaluate_invoice({}, {"total_amount": 6000, "counterparty_name": "Vendor"})
    assert result["semantic_approval_status"] == "MANUAL_REVIEW"
    assert route_after_semantic({
        "requires_human_review": True, "semantic_approval_status": "AUTO_APPROVE",
        "matched_afis_id": 8,
    }) == "human_review"


def test_dunning_draft_is_not_sent():
    result = run_dunning_agent({
        "invoice_data": {
            "invoice_number": "AR-1", "counterparty_name": "Customer",
            "total_amount": 120.0, "due_date": "2026-01-01", "days_overdue": 10,
        },
        "dunning_stage": 1,
    })
    assert result["dunning_email_sent"] is False


def test_legacy_unique_date_migrates_for_tenants(tmp_path, monkeypatch):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE dso_snapshots (id INTEGER PRIMARY KEY, snapshot_date DATE NOT NULL UNIQUE, dso_days REAL NOT NULL, ar_balance REAL NOT NULL, revenue_30d REAL NOT NULL)")
    monkeypatch.setattr(settings, "APEX_DB_PATH", str(path))
    monkeypatch.setattr(db_manager, "engine", create_engine(f"sqlite:///{path}"))
    db_manager.init_db()
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO dso_snapshots (tenant_id, snapshot_date, dso_days, ar_balance, revenue_30d) VALUES ('a', '2026-01-01', 30, 100, 100)")
        conn.execute("INSERT INTO dso_snapshots (tenant_id, snapshot_date, dso_days, ar_balance, revenue_30d) VALUES ('b', '2026-01-01', 40, 100, 100)")
        assert conn.execute("SELECT COUNT(*) FROM dso_snapshots").fetchone()[0] == 2


def test_api_isolates_tenants_and_viewer_cannot_write(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        for tenant in ("a", "b"):
            db.add(models.Invoice(
                tenant_id=tenant, invoice_number=f"INV-{tenant}", invoice_type="AR",
                counterparty_name="Customer", issue_date=date(2026, 1, 1),
                due_date=date(2026, 1, 30), amount=100, total_amount=100,
            ))
        db.commit()
    def override_db():
        with factory() as db:
            yield db
    monkeypatch.setattr(settings, "APEX_API_KEY", "")
    monkeypatch.setattr(settings, "APEX_API_KEYS_JSON",
                        '[{"key":"key-a","actor":"alice","tenant_id":"a","role":"viewer"},'
                        '{"key":"key-b","actor":"bob","tenant_id":"b","role":"admin"}]')
    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        a = client.get("/api/v1/invoices/", headers={"X-APEX-API-KEY": "key-a"})
        b = client.get("/api/v1/invoices/", headers={"X-APEX-API-KEY": "key-b"})
        assert [row["invoice_number"] for row in a.json()] == ["INV-a"]
        assert [row["invoice_number"] for row in b.json()] == ["INV-b"]
        assert client.post("/api/v1/payments/intent",
                           headers={"X-APEX-API-KEY": "key-a"}).status_code == 403
    finally:
        app.dependency_overrides.clear()
