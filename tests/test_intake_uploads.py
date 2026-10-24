"""Local intake accepts only bounded typed files and keeps a durable tracker."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base, get_db
from app.main import app
from app.services import intake_pipeline
from scripts.synthetic_documents import synthetic_pdf


def test_csv_upload_queue_and_source_link(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(intake_pipeline, "SessionLocal", factory)
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "synthetic-intake-test")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", "")
    headers = {"X-RECOVERFLOW-API-KEY": "synthetic-intake-test",
               "X-Filename": "invoices.csv", "Content-Type": "text/csv"}
    csv_data = (b"external_id,invoice_number,customer_name,issue_date,due_date,amount,currency\n"
                b"one,INV-ONE,Synthetic Retailer,2026-01-01,2026-02-01,240000.00,INR\n")
    try:
        client = TestClient(app)
        bad = client.post("/api/v1/intake/uploads", headers={**headers,
            "X-Filename": "receipt.pdf", "Content-Type": "application/pdf"}, content=csv_data)
        assert bad.status_code == 415
        uploaded = client.post("/api/v1/intake/uploads", headers=headers, content=csv_data)
        assert uploaded.status_code == 202, uploaded.text
        job_id = uploaded.json()["id"]
        assert uploaded.json()["stage"] == "Uploaded"
        assert intake_pipeline.process_one()
        status = client.get(f"/api/v1/intake/uploads/{job_id}", headers=headers)
        assert status.status_code == 200
        assert status.json()["stage"] == "Ready for review"
        assert status.json()["stages"] == ["Uploaded", "Extracted", "Matched",
            "Investigated", "Drafted", "Ready for review"]
        assert status.json()["cases_created"] == 1
        source = client.get(f"/api/v1/intake/uploads/{job_id}/file", headers=headers)
        assert source.status_code == 200 and source.content == csv_data
        with factory() as db:
            invoice = db.query(models.Invoice).one()
            assert invoice.face_amount_cents == 24000000
            evidence = db.query(models.CaseEvidence).one()
            assert evidence.source_reference.endswith(f"{job_id}/file")
            assert evidence.verified is False
            proposal = db.query(models.AgentProposal).one()
            assert proposal.action == "split_balance_draft"
            assert db.query(models.ProposalDraftVersion).one().status == "draft"
        auth_headers = {"X-RECOVERFLOW-API-KEY": "synthetic-intake-test"}
        assert client.put("/api/v1/agent/autonomy", headers=auth_headers,
            json={"mode": "auto_prepare"}).status_code == 200
        confirmed = client.post(f"/api/v1/intake/uploads/{job_id}/confirm-invoice", headers=headers)
        assert confirmed.status_code == 200, confirmed.text
        bulk = client.post("/api/v1/agent/bulk-approve", headers=headers)
        assert bulk.status_code == 200, bulk.text
        assert len(bulk.json()["approved"]) == 1
        assert client.put("/api/v1/agent/autonomy", headers=auth_headers,
            json={"mode": "auto_send_sandbox"}).status_code == 200
        second_csv = csv_data.replace(b"qa-1", b"qa-2").replace(b"one,INV-ONE", b"two,INV-TWO")
        second = client.post("/api/v1/intake/uploads", headers={**headers,
            "X-Filename": "second.csv"}, content=second_csv)
        assert second.status_code == 202
        assert intake_pipeline.process_one()
        assert client.post(f"/api/v1/intake/uploads/{second.json()['id']}/confirm-invoice",
            headers=headers).status_code == 200
        outbox = client.get("/api/v1/agent/sandbox-outbox", headers=headers)
        assert outbox.status_code == 200
        assert len(outbox.json()) == 1
        assert outbox.json()[0]["channel"] == "SIMULATED sandbox outbox"
    finally:
        app.dependency_overrides.clear()


def test_po_upload_is_visible_to_investigator_before_transaction_commit(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(intake_pipeline, "SessionLocal", factory)
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "synthetic-po-test")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", "")
    auth = {"X-RECOVERFLOW-API-KEY": "synthetic-po-test"}
    client = TestClient(app)
    try:
        invoice = client.post("/api/v1/intake/uploads", content=synthetic_pdf(number="INV-PO-TEST"),
            headers={**auth, "X-Filename": "invoice.pdf", "Content-Type": "application/pdf"})
        assert invoice.status_code == 202
        assert intake_pipeline.process_one()
        assert client.post(f"/api/v1/intake/uploads/{invoice.json()['id']}/confirm-invoice",
                           headers=auth).status_code == 200
        po = client.post("/api/v1/intake/uploads", content=synthetic_pdf(
            kind="purchase_order", reference="INV-PO-TEST", total="210000.00"),
            headers={**auth, "X-Filename": "po.pdf", "Content-Type": "application/pdf"})
        assert po.status_code == 202
        assert intake_pipeline.process_one()
        assert client.get(f"/api/v1/intake/uploads/{po.json()['id']}", headers=auth).json()["stage"] == "Ready for review"
        with factory() as db:
            invoice_row = db.query(models.Invoice).filter_by(invoice_number="INV-PO-TEST").one()
            assert invoice_row.disputed_cents == 3000000
            disputed = db.query(models.CaseEvidence).filter_by(
                invoice_id=invoice_row.id, claim_type="dispute_item").one()
            assert disputed.source_reference.endswith(f"{po.json()['id']}/file")
    finally:
        app.dependency_overrides.clear()


def test_identical_invoice_retry_is_marked_imported_once(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(intake_pipeline, "SessionLocal", factory)
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "synthetic-duplicate-test")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", "")
    auth = {"X-RECOVERFLOW-API-KEY": "synthetic-duplicate-test",
            "X-Filename": "same.pdf", "Content-Type": "application/pdf"}
    client = TestClient(app)
    try:
        source = synthetic_pdf(number="INV-DUPLICATE")
        for expected_cases in (1, 0):
            response = client.post("/api/v1/intake/uploads", content=source, headers=auth)
            assert response.status_code == 202
            assert intake_pipeline.process_one()
            result = client.get(f"/api/v1/intake/uploads/{response.json()['id']}",
                                headers=auth).json()
            assert result["status"] == "ready_for_review"
            assert result["cases_created"] == expected_cases
        with factory() as db:
            assert db.query(models.Invoice).count() == 1
    finally:
        app.dependency_overrides.clear()

