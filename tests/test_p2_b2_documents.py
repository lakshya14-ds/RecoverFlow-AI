"""P2 B2: Indian document model — GST splits, persisted lines, challans,
credit/debit notes, freight/scheme handling, and six reconciliation fixtures.
"""
import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base
from app.main import app
from app.services import vision_extraction
from app.services.documents import persist_invoice_lines
from app.services.intake_pipeline import process_job
from app.services.investigation import investigate
from app.services.receivables import post_entry, split_balance
from app.services.vision_extraction import VisionDocument, validate_document

ADMIN = {"X-RECOVERFLOW-API-KEY": "b2-admin"}
BOSS = {"X-RECOVERFLOW-API-KEY": "b2-boss"}


@pytest.fixture()
def m2db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture()
def apidb(monkeypatch, tmp_path):
    from app.database import db_manager
    db_path = tmp_path / "b2.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "b2-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "b2-boss", "actor": "boss@example.in", "tenant_id": "local",
          "role": "admin"}]))
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        for email in ("s1@example.in", "s2@example.in"):
            db.add(models.User(tenant_id="local", email=email, name=email,
                               password_hash="x", role="editor"))
        row = models.Invoice(
            tenant_id="local", invoice_number="INV-B2A", invoice_type="AR",
            counterparty_name="B2 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR")
        db.add(row)
        db.commit()
        invoice_id = row.id
    yield {"client": TestClient(app), "factory": factory, "engine": engine,
           "invoice": invoice_id}
    engine.dispose()


def _invoice(db, number="INV-B2", face=100000, source="invoice.pdf", **tax):
    row = models.Invoice(
        tenant_id="local", invoice_number=number, invoice_type="AR",
        counterparty_name="B2 Party", issue_date=date(2026, 9, 1),
        due_date=date(2026, 10, 15), amount=Decimal(face) / 100,
        total_amount=Decimal(face) / 100, face_amount_cents=face,
        currency="INR", source_path=source, **tax)
    db.add(row)
    db.flush()
    return row


def _upload(db, kind, name, payload, number="INV-B2"):
    row = models.IntakeUpload(id=name, tenant_id="local", actor="staff",
        filename=name, mime_type="application/pdf", source_path=name,
        size_bytes=10, extraction_json=json.dumps(
            {"document_type": kind, "invoice_reference": number, **payload}))
    db.add(row)
    db.flush()
    return row


def _invoice_doc(db, lines, number="INV-B2", name="invoice.pdf", **extra):
    return _upload(db, "invoice", name,
                   {"invoice_number": number, "line_items": lines, **extra},
                   number)


def _line(sku, description, quantity, unit_price, amount, unit="", **extra):
    line = {"sku": sku, "description": description, "quantity": str(quantity),
            "unit_price": str(unit_price), "amount": str(amount)}
    if unit:
        line["unit"] = unit
    line.update(extra)
    return line


def _persisted(db, invoice, line_no=1, sku="WDG", quantity="10", unit="pcs",
               price_cents=10000, amount_cents=100000, rate_bps=1800,
               cgst=9000, sgst=9000, igst=0):
    db.add(models.InvoiceLineItem(
        tenant_id="local", invoice_id=invoice.id, line_no=line_no, sku=sku,
        description="Widgets", quantity=Decimal(quantity), unit=unit,
        unit_price_cents=price_cents, amount_cents=amount_cents,
        tax_rate_bps=rate_bps, cgst_cents=cgst, sgst_cents=sgst,
        igst_cents=igst, status="alleged"))
    db.flush()


def _vdoc(**overrides):
    base = {"document_type": "invoice", "invoice_number": "INV-V",
            "customer_name": "Buyer", "issue_date": "2026-01-01",
            "due_date": "2026-02-01", "total_amount": "1180.00",
            "tax_amount": "180.00", "currency": "INR",
            "line_items": [{"description": "Widgets", "amount": "1000.00",
                            "quantity": "10", "unit_price": "100.00"}],
            "confidence": {"document_type": 1.0, "total_amount": 1.0,
                           "invoice_number": 1.0, "customer_name": 1.0,
                           "issue_date": 1.0, "due_date": 1.0,
                           "tax_amount": 1.0}}
    base.update(overrides)
    return VisionDocument(**base)


def test_gst_split_must_reconcile_to_tax():
    good = _vdoc(cgst_amount="90.00", sgst_amount="90.00", igst_amount="0.00")
    assert validate_document(good)["total"] == Decimal("1180.00")
    bad = _vdoc(cgst_amount="80.00", sgst_amount="90.00", igst_amount="0.00")
    with pytest.raises(ValueError, match="split does not reconcile"):
        validate_document(bad)
    assert validate_document(_vdoc())["total"] == Decimal("1180.00")


def test_note_types_require_reference_and_total():
    doc = VisionDocument(document_type="credit_note", invoice_reference="INV-X",
                         total_amount="100.00",
                         confidence={"document_type": 1.0, "total_amount": 1.0})
    assert validate_document(doc)["total"] == Decimal("100.00")
    with pytest.raises(ValueError, match="invoice reference"):
        validate_document(VisionDocument(
            document_type="debit_note", total_amount="100.00",
            confidence={"document_type": 1.0, "total_amount": 1.0}))
    with pytest.raises(ValueError, match="Unsupported"):
        validate_document(VisionDocument(
            document_type="fortune_cookie", total_amount="1.00",
            confidence={"document_type": 1.0, "total_amount": 1.0}))


def test_persist_lines_and_tax(m2db):
    row = _invoice(m2db, face=118000)
    doc = _vdoc(cgst_amount="90.00", sgst_amount="90.00", igst_amount="0.00",
                shipping_amount="50.00", total_amount="1230.00")
    doc.confidence["shipping_amount"] = 1.0
    result = validate_document(doc)
    persist_invoice_lines(m2db, row, result["document"], "invoice.pdf")
    assert row.cgst_cents == 9000 and row.sgst_cents == 9000
    assert row.freight_cents == 5000
    line = m2db.query(models.InvoiceLineItem).one()
    assert line.amount_cents == 100000 and line.quantity == Decimal("10")
    assert line.status == "alleged"
    with pytest.raises(ValueError, match="already recorded"):
        persist_invoice_lines(m2db, row, result["document"], "invoice.pdf")


def test_partial_delivery_with_tax_needs_staff_allocation(m2db):
    row = _invoice(m2db, face=118000, cgst_cents=9000, sgst_cents=9000)
    _invoice_doc(m2db, [_line("WDG", "Widgets", 10, "100", "1000")],
                 tax_amount="180.00", total_amount="1180.00")
    _persisted(m2db, row)
    _upload(m2db, "delivery_challan", "challan.pdf", {"line_items": [
        _line("WDG", "Widgets", 7, "100", "700")]})
    with pytest.raises(ValueError, match="tax and freight allocation"):
        investigate(m2db, row)
    assert row.disputed_cents == 0
    assert m2db.query(models.ReceivableEntry).count() == 0
    task = m2db.query(models.ClarificationTask).filter_by(
        tenant_id="local", invoice_id=row.id).one()
    assert "Figures:" in task.draft_preview and "18%" in task.draft_preview
    assert "CGST 90.00" in task.draft_preview


def test_returns_without_tax_claim_directly(m2db):
    row = _invoice(m2db)
    _invoice_doc(m2db, [_line("WDG", "Widgets", 10, "100", "1000")])
    _upload(m2db, "return_note", "return.pdf", {"line_items": [
        _line("WDG", "Widgets", 2, "100", "200")]})
    assert investigate(m2db, row) == 20000
    assert row.disputed_cents == 20000
    assert m2db.query(models.CaseEvidence).filter_by(
        claim_type="dispute_item").one().amount_cents == 20000


def test_wrong_gst_basis_competes_with_price(m2db):
    row = _invoice(m2db, face=118000)
    _invoice_doc(m2db, [_line("WDG", "Widgets", 1, "1180", "1180")],
                 tax_amount="180.00", total_amount="1180.00")
    _upload(m2db, "purchase_order", "po.pdf",
            {"line_items": [_line("WDG", "Widgets", 1, "1000", "1000")],
             "total_amount": "1000.00"})
    with pytest.raises(ValueError, match="Competing explanations"):
        investigate(m2db, row)
    hyps = json.loads(m2db.query(models.CompetingExplanation).one()
                      .hypotheses_json)
    assert {item["key"] for item in hyps} == {"price_difference",
                                              "tax_basis_difference"}
    assert all(item["amount_cents"] == 18000 for item in hyps)


def test_freight_dispute_and_match(m2db):
    row = _invoice(m2db, number="INV-F1", face=100000, freight_cents=50000,
                   source="inv-f1.pdf")
    _invoice_doc(m2db, [_line("WDG", "Widgets", 10, "100", "1000")],
                 number="INV-F1")
    _upload(m2db, "freight_bill", "freight.pdf", {"total_amount": "800.00"},
            number="INV-F1")
    with pytest.raises(ValueError, match="Freight difference"):
        investigate(m2db, row)
    explanation = m2db.query(models.CompetingExplanation).filter_by(
        invoice_id=row.id).one()
    assert explanation.category == "freight"
    assert json.loads(explanation.hypotheses_json)[0]["amount_cents"] == 30000
    clean = _invoice(m2db, number="INV-F2", face=100000, freight_cents=50000,
                     source="inv-f2.pdf")
    _invoice_doc(m2db, [_line("WDG", "Widgets", 10, "100", "1000")],
                 number="INV-F2", name="invoice-f2.pdf")
    _upload(m2db, "freight_bill", "freight2.pdf",
            {"total_amount": "500.00"}, number="INV-F2")
    assert investigate(m2db, clean) == 0
    assert not clean.investigation_hold


def test_scheme_letter_matches_variance(m2db):
    row = _invoice(m2db)
    _invoice_doc(m2db, [_line("WDG", "Widgets", 10, "100", "1000")])
    _upload(m2db, "purchase_order", "po.pdf", {"line_items": [
        _line("WDG", "Widgets", 10, "90", "900")]})
    _upload(m2db, "scheme_letter", "scheme.pdf", {"line_items": [
        _line("WDG", "Widgets", 1, "100", "100")]})
    with pytest.raises(ValueError, match="Competing explanations"):
        investigate(m2db, row)
    hyps = json.loads(m2db.query(models.CompetingExplanation).one()
                      .hypotheses_json)
    assert {item["key"] for item in hyps} == {"price_difference",
                                              "scheme_discount"}


def test_credit_note_is_never_cash(apidb):
    client = apidb["client"]
    invoice_id = apidb["invoice"]
    created = client.post(f"/api/v1/cases/{invoice_id}/notes", headers=ADMIN,
                          json={"note_type": "credit", "number": "CN-1",
                                "amount": "100.00",
                                "reason": "Short supply credit"})
    assert created.status_code == 201, created.text
    note_id = created.json()["id"]
    with apidb["factory"]() as db:
        invoice = db.get(models.Invoice, invoice_id)
        assert split_balance(db, invoice)["received_cents"] == 0
    blocked = client.post(
        f"/api/v1/cases/{invoice_id}/notes/{note_id}/accept", headers=ADMIN,
        json={"reason": "self approval attempt"})
    assert blocked.status_code == 409
    assert "Separation of duties" in blocked.json()["detail"]
    accepted = client.post(
        f"/api/v1/cases/{invoice_id}/notes/{note_id}/accept", headers=BOSS,
        json={"reason": "verified against challan"})
    assert accepted.status_code == 200, accepted.text
    posted = client.post(f"/api/v1/cases/{invoice_id}/notes/{note_id}/post",
                         headers=BOSS)
    assert posted.status_code == 200, posted.text
    assert posted.json()["kind"] == "credit"
    with apidb["factory"]() as db:
        invoice = db.get(models.Invoice, invoice_id)
        split = split_balance(db, invoice)
        assert split["received_cents"] == 0
        assert split["credits_cents"] == 10000
    repost = client.post(f"/api/v1/cases/{invoice_id}/notes/{note_id}/post",
                         headers=BOSS)
    assert repost.json()["entry_id"] == posted.json()["entry_id"]
    second = client.post(f"/api/v1/cases/{invoice_id}/notes", headers=ADMIN,
                         json={"note_type": "credit", "number": "CN-2",
                               "amount": "50.00", "reason": "Unaccepted note"})
    direct = client.post(
        f"/api/v1/cases/{invoice_id}/notes/{second.json()['id']}/post",
        headers=BOSS)
    assert direct.status_code == 409
    third = client.post(f"/api/v1/cases/{invoice_id}/notes", headers=ADMIN,
                        json={"note_type": "credit", "number": "CN-3",
                              "amount": "10.00", "reason": "Mistyped note"})
    assert client.post(
        f"/api/v1/cases/{invoice_id}/notes/{third.json()['id']}/cancel",
        headers=BOSS, json={"reason": "wrong number"}).status_code == 200
    assert client.post(
        f"/api/v1/cases/{invoice_id}/notes/{note_id}/cancel",
        headers=BOSS, json={"reason": "too late"}).status_code == 409


def test_debit_note_increases_outstanding(apidb):
    client = apidb["client"]
    invoice_id = apidb["invoice"]
    created = client.post(f"/api/v1/cases/{invoice_id}/notes", headers=ADMIN,
                          json={"note_type": "debit", "number": "DN-1",
                                "amount": "100.00",
                                "reason": "Extra freight billed"})
    note_id = created.json()["id"]
    client.post(f"/api/v1/cases/{invoice_id}/notes/{note_id}/accept",
                headers=BOSS, json={"reason": "verified"})
    posted = client.post(f"/api/v1/cases/{invoice_id}/notes/{note_id}/post",
                         headers=BOSS)
    assert posted.status_code == 200, posted.text
    with apidb["factory"]() as db:
        invoice = db.get(models.Invoice, invoice_id)
        split = split_balance(db, invoice)
        assert split["outstanding_cents"] == 110000
        assert split["debits_cents"] == 10000
        assert split["received_cents"] == 0
        entry = db.get(models.ReceivableEntry, posted.json()["entry_id"])
        reversal = post_entry(
            db, invoice, kind="reversal", amount=Decimal("100.00"),
            source="reversal", reference=str(entry.id), actor="b2-test",
            reversal_of_id=entry.id)
        db.commit()
        assert split_balance(db, invoice)["outstanding_cents"] == 100000
        assert reversal.amount_cents == -10000
        with pytest.raises(ValueError, match="without allocation"):
            post_entry(db, invoice, kind="debit", amount=Decimal("10.00"),
                       source="x", reference="bad-alloc", actor="b2-test",
                       allocation="disputed")


def test_persisted_lines_drive_investigation(m2db):
    row = _invoice(m2db, source="manual.pdf")
    _persisted(m2db, row)
    _upload(m2db, "purchase_order", "po.pdf", {"line_items": [
        _line("WDG", "Widgets", 10, "70", "700")]})
    assert investigate(m2db, row) == 30000
    assert row.disputed_cents == 30000


def test_case_detail_shows_documents(apidb):
    client = apidb["client"]
    invoice_id = apidb["invoice"]
    with apidb["factory"]() as db:
        invoice = db.get(models.Invoice, invoice_id)
        invoice.cgst_cents = 9000
        db.add(models.InvoiceLineItem(
            tenant_id="local", invoice_id=invoice_id, line_no=1, sku="WDG",
            description="Widgets", quantity=Decimal("10"), unit="pcs",
            unit_price_cents=10000, amount_cents=100000, status="alleged"))
        db.add(models.CreditDebitNote(
            tenant_id="local", invoice_id=invoice_id, note_type="credit",
            number="CN-9", amount_cents=5000, reason="detail check",
            status="alleged", created_by="b2-test"))
        db.add(models.SupportingDocument(
            tenant_id="local", invoice_id=invoice_id, doc_type="freight_bill",
            source_upload_id="up-9", status="alleged",
            summary_json='{"total": "500.00"}'))
        db.commit()
    case = client.get(f"/api/v1/cases/{invoice_id}", headers=ADMIN).json()
    assert len(case["line_items"]) == 1
    assert case["tax_split"]["cgst_cents"] == 9000
    assert case["credit_debit_notes"][0]["number"] == "CN-9"
    assert case["supporting_documents"][0]["doc_type"] == "freight_bill"


def test_delivery_challan_claims_like_delivery_note(m2db):
    row = _invoice(m2db)
    _invoice_doc(m2db, [_line("WDG", "Widgets", 10, "100", "1000")])
    _upload(m2db, "delivery_challan", "challan.pdf", {"line_items": [
        _line("WDG", "Widgets", 8, "100", "800")]})
    assert investigate(m2db, row) == 20000
    assert row.disputed_cents == 20000


def test_staff_records_lines_manually(apidb):
    client = apidb["client"]
    invoice_id = apidb["invoice"]
    created = client.post(f"/api/v1/cases/{invoice_id}/line-items",
                          headers=ADMIN,
                          json={"description": "Widgets", "quantity": "10",
                                "unit_price": "100.00", "amount": "1000.00",
                                "tax_rate_bps": 1800})
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "verified"
    again = client.post(f"/api/v1/cases/{invoice_id}/line-items",
                        headers=ADMIN,
                        json={"line_no": 1, "description": "Widgets revised",
                              "amount": "900.00"})
    assert again.json()["line_no"] == 1
    rows = client.get(f"/api/v1/cases/{invoice_id}/line-items",
                      headers=ADMIN).json()
    assert len(rows) == 1 and rows[0]["amount_cents"] == 90000
    assert client.post(f"/api/v1/cases/{invoice_id}/line-items",
                       headers=ADMIN,
                       json={"description": "Bad", "quantity": "0",
                             "amount": "10.00"}).status_code == 422


def test_intake_persists_new_document_types(m2db, monkeypatch, tmp_path):
    from app.services import intake_pipeline
    uploads = {}
    for name in ("inv.pdf", "cn.pdf", "ch.pdf"):
        path = tmp_path / name
        path.write_bytes(b"%PDF-dummy-" + name.encode())
        row = models.IntakeUpload(
            id=name, tenant_id="local", actor="staff", filename=name,
            mime_type="application/pdf", source_path=str(path), size_bytes=10,
            status="queued", stage="Uploaded")
        m2db.add(row)
        uploads[name] = row
    m2db.commit()
    invoice_doc = validate_document(_vdoc(
        invoice_number="INV-B2I", cgst_amount="90.00", sgst_amount="90.00",
        igst_amount="0.00"))
    note_doc = validate_document(VisionDocument(
        document_type="credit_note", invoice_number="CN-I",
        invoice_reference="INV-B2I", total_amount="100.00",
        confidence={"document_type": 1.0, "total_amount": 1.0}))
    challan_doc = validate_document(VisionDocument(
        document_type="delivery_challan", invoice_reference="INV-B2I",
        confidence={"document_type": 1.0, "total_amount": 1.0}))
    from pathlib import Path as _Path
    returns = {"inv.pdf": {**invoice_doc, "engine": "test"},
               "cn.pdf": {**note_doc, "engine": "test"},
               "ch.pdf": {**challan_doc, "engine": "test"}}
    by_bytes = {(tmp_path / name).read_bytes(): returns[name]
                for name in returns}
    monkeypatch.setattr(intake_pipeline.vision_extraction, "extract",
                        lambda data, mime: by_bytes[data])
    for name in ("inv.pdf", "cn.pdf", "ch.pdf"):
        process_job(m2db, m2db.get(models.IntakeUpload, name))
    invoice = m2db.query(models.Invoice).filter_by(
        invoice_number="INV-B2I").one()
    assert m2db.query(models.InvoiceLineItem).filter_by(
        invoice_id=invoice.id).count() == 1
    assert invoice.cgst_cents == 9000
    note = m2db.query(models.CreditDebitNote).filter_by(
        invoice_id=invoice.id).one()
    assert note.status == "alleged" and note.number == "CN-I"
    assert m2db.query(models.SupportingDocument).filter_by(
        invoice_id=invoice.id, doc_type="delivery_challan").count() == 1
    assert m2db.get(models.IntakeUpload, "inv.pdf").status == "ready_for_review"
