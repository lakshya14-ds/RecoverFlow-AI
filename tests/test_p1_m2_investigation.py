"""Milestone 2: line-level investigation, competing explanations, clarifications."""
import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base, get_db
from app.main import app
from app.services import supervisor
from app.services.investigation import investigate
from app.services.line_matching import (
    convert_quantity,
    match_sku_in_text,
    tax_basis_plausible,
    to_cents,
    to_decimal,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def api(db, monkeypatch):
    def override():
        yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "test-key")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", "")
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


HEADERS = {"X-RECOVERFLOW-API-KEY": "test-key"}


def invoice(db, number="INV-M2", lines=None):
    row = models.Invoice(tenant_id="local", invoice_number=number, invoice_type="AR",
        counterparty_name="Synthetic distributor", issue_date=date(2026, 9, 1),
        due_date=date(2026, 10, 15), amount=Decimal("1000.00"),
        total_amount=Decimal("1000.00"), face_amount_cents=100000,
        disputed_cents=0, currency="INR", source_path="invoice.pdf")
    db.add(row)
    db.flush()
    return row


def _upload(db, kind, name, payload, number="INV-M2"):
    row = models.IntakeUpload(id=name, tenant_id="local", actor="staff", filename=name,
        mime_type="application/pdf", source_path=name, size_bytes=10,
        extraction_json=json.dumps({"document_type": kind, "invoice_reference": number,
                                    **payload}))
    db.add(row)
    db.flush()
    return row


def _invoice_doc(db, lines, number="INV-M2", **extra):
    return _upload(db, "invoice", "invoice.pdf", {"invoice_number": number,
        "line_items": lines, **extra}, number)


def _line(sku, description, quantity, unit_price, amount, unit=""):
    line = {"sku": sku, "description": description, "quantity": str(quantity),
            "unit_price": str(unit_price), "amount": str(amount)}
    if unit:
        line["unit"] = unit
    return line


def test_contradictory_po_lines_store_competing_explanations(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")])
    _upload(db, "purchase_order", "po.pdf", {"line_items": [
        _line("A", "Item A", 10, "70", "700")]})
    _upload(db, "purchase_order", "other-po.pdf", {"line_items": [
        _line("A", "Item A", 10, "80", "800")]})
    with pytest.raises(ValueError, match="Sources disagree"):
        investigate(db, row)
    assert row.investigation_hold
    assert row.disputed_cents == 0
    explanation = db.query(models.CompetingExplanation).filter_by(
        tenant_id="local", invoice_id=row.id, status="open").one()
    hyps = json.loads(explanation.hypotheses_json)
    assert {h["amount_cents"] for h in hyps} == {30000, 20000}
    assert all(h["supporting"] and h["contradicting"] for h in hyps)
    assert all(h["needs_staff"] for h in hyps)


def test_explanation_resolve_api(db, api):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")])
    _upload(db, "purchase_order", "po.pdf", {"line_items": [
        _line("A", "Item A", 10, "70", "700")]})
    _upload(db, "purchase_order", "other-po.pdf", {"line_items": [
        _line("A", "Item A", 10, "80", "800")]})
    with pytest.raises(ValueError, match="Sources disagree"):
        investigate(db, row)
    db.commit()
    explanation = db.query(models.CompetingExplanation).filter_by(status="open").one()
    bad = api.post(f"/api/v1/cases/{row.id}/explanations/{explanation.id}/resolve",
                   headers=HEADERS,
                   json={"hypothesis": "nope", "reason": "Invalid choice here"})
    assert bad.status_code == 422
    done = api.post(f"/api/v1/cases/{row.id}/explanations/{explanation.id}/resolve",
                    headers=HEADERS,
                    json={"hypothesis": "source_0", "reason": "First PO matches the contract"})
    assert done.status_code == 200, done.text
    assert done.json()["resolved_hypothesis"] == "source_0"
    again = api.post(f"/api/v1/cases/{row.id}/explanations/{explanation.id}/resolve",
                     headers=HEADERS,
                     json={"hypothesis": "source_0", "reason": "Second attempt here"})
    assert again.status_code == 409


def test_multi_sku_shortage_attribution_and_ambiguity(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000"),
                      _line("B", "Item B", 5, "100", "500")])
    _upload(db, "message", "msg.pdf", {"text": "We are short by 2 units of sku-a"})
    assert investigate(db, row) == 20000
    assert db.query(models.CaseEvidence).filter_by(
        tenant_id="local", invoice_id=row.id, claim_type="dispute_item").one().amount_cents == 20000

    row2 = invoice(db, number="INV-M2B")
    row2.source_path = "invoice2.pdf"
    _upload(db, "invoice", "invoice2.pdf", {"invoice_number": "INV-M2B", "line_items": [
        _line("A", "Item A", 10, "100", "1000"),
        _line("B", "Item B", 5, "100", "500")]}, "INV-M2B")
    _upload(db, "message", "msg2.pdf", {"text": "We are short by 2 units"}, "INV-M2B")
    with pytest.raises(ValueError, match="does not identify a uniquely priced invoice item"):
        investigate(db, row2)
    clarification = db.query(models.ClarificationTask).filter_by(
        tenant_id="local", invoice_id=row2.id, status="open").one()
    assert clarification.owner == "staff"
    assert "Unsent draft" in (clarification.draft_preview or "")


def test_tax_basis_ambiguity_holds_without_apportion(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")],
                 tax_amount="180", total_amount="1180")
    _upload(db, "purchase_order", "po.pdf", {"total_amount": "1000", "line_items": [
        _line("A", "Item A", 10, "82", "820")]})
    with pytest.raises(ValueError, match="Competing explanations"):
        investigate(db, row)
    assert row.disputed_cents == 0
    explanation = db.query(models.CompetingExplanation).filter_by(status="open").one()
    keys = {h["key"] for h in json.loads(explanation.hypotheses_json)}
    assert keys == {"price_difference", "tax_basis_difference"}


def test_freight_blocks_with_unsent_clarification(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")],
                 shipping_amount="50", total_amount="1050")
    _upload(db, "delivery_note", "dn.pdf", {"line_items": [
        _line("A", "Item A", 8, "100", "800")]})
    with pytest.raises(ValueError, match="tax and freight allocation"):
        investigate(db, row)
    clarification = db.query(models.ClarificationTask).filter_by(status="open").one()
    assert clarification.owner == "staff"
    assert clarification.affected_cents == 20000
    assert "Unsent draft" in (clarification.draft_preview or "")
    assert db.query(models.SandboxOutbox).count() == 0
    assert db.query(models.AgentProposal).count() == 0


def test_unit_mismatch_needs_staff_rule_then_converts(db, api):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000", unit="piece")])
    _upload(db, "delivery_note", "dn.pdf", {"line_items": [
        _line("A", "Item A", 1, "1000", "1000", unit="box")]})
    with pytest.raises(ValueError, match="Unit mismatch"):
        investigate(db, row)
    assert db.query(models.ClarificationTask).filter_by(status="open").one().key == "unit:a"
    created = api.post(f"/api/v1/cases/{row.id}/unit-rules", headers=HEADERS,
                       json={"from_unit": "box", "to_unit": "piece", "factor": "10"})
    assert created.status_code == 201, created.text

    row2 = invoice(db, number="INV-M2C")
    row2.source_path = "invoice3.pdf"
    _upload(db, "invoice", "invoice3.pdf", {"invoice_number": "INV-M2C", "line_items": [
        _line("A", "Item A", 12, "100", "1200", unit="piece")]}, "INV-M2C")
    _upload(db, "delivery_note", "dn3.pdf", {"line_items": [
        _line("A", "Item A", 1, "1000", "1000", unit="box")]}, "INV-M2C")
    assert investigate(db, row2) == 20000


def test_duplicate_supporting_document_counted_once(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")])
    lines = [_line("A", "Item A", 10, "70", "700")]
    _upload(db, "purchase_order", "po.pdf", {"line_items": lines})
    _upload(db, "purchase_order", "po-copy.pdf", {"line_items": lines})
    assert investigate(db, row) == 30000
    assert db.query(models.CaseEvidence).filter_by(
        tenant_id="local", invoice_id=row.id, claim_type="dispute_item").count() == 1
    assert db.query(models.AuditEvent).filter_by(
        action="investigation_duplicate_skipped").count() == 1


def test_unreadable_document_requests_readable_copy(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")])
    _upload(db, "purchase_order", "po.pdf", {"line_items": []})
    with pytest.raises(ValueError, match="Unreadable purchase_order"):
        investigate(db, row)
    clarification = db.query(models.ClarificationTask).filter_by(status="open").one()
    assert clarification.owner == "staff"
    assert "readable purchase order" in clarification.title


def test_new_evidence_overturns_old_proposal(db):
    from app.services.release4_orchestrator import prepare_draft
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")])
    db.add(models.CaseEvidence(tenant_id="local", invoice_id=row.id, claim_type="invoice_total",
        title="Invoice", description="Synthetic", source_type="staff_record",
        source_reference="synthetic-invoice.pdf", amount_cents=100000, verified=True,
        trust_state="verified", decided_by="staff", decision_reason="Seeded for test"))
    db.commit()
    first = prepare_draft(db, row)
    db.commit()
    _upload(db, "purchase_order", "po.pdf", {"line_items": [
        _line("A", "Item A", 10, "70", "700")]})
    assert investigate(db, row) == 30000
    from app.services import controlled_agent
    _, digest, _ = controlled_agent.snapshot(db, row)
    assert digest != first.context_hash
    for _ in range(4):
        queued = supervisor.reassess(db, row, "test")
        assert queued["outcome"] == "queued"
        outcome = supervisor.run_task(db, queued["task_id"])
        db.commit()
        if queued["kind"] == "verification":
            assert outcome["outcome"] == "escalated", outcome
            result = json.loads(db.get(models.SupervisorTask,
                                       queued["task_id"]).result_json)
            stale = next(c for c in result["findings"]["checks"]
                         if c["name"] == "no_stale_split_drafts")
            assert stale["pass"] is False
            assert str(first.id) in stale["detail"]
            return
    raise AssertionError("verification task never ran")


def test_absent_source_links_fail_verification(db):
    from app.services.case_lifecycle import fingerprint
    row = invoice(db)
    db.add(models.CaseEvidence(tenant_id="local", invoice_id=row.id, claim_type="invoice_total",
        title="Sourceless", description="No source link", source_type="staff_record",
        source_reference="", amount_cents=100000, trust_state="alleged"))
    db.commit()
    task = models.SupervisorTask(tenant_id="local", invoice_id=row.id, kind="verification",
        status="queued", idempotency_key="local:m2:verify:1",
        case_version=fingerprint(db, row))
    db.add(task)
    db.commit()
    assert supervisor.run_task(db, task.id)["outcome"] == "escalated"
    result = json.loads(db.get(models.SupervisorTask, task.id).result_json)
    linked = next(c for c in result["findings"]["checks"] if c["name"] == "evidence_linked")
    assert linked["pass"] is False


def test_damage_claim_stays_allegation_with_clarification(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")])
    _upload(db, "message", "msg.pdf", {"text": "3 units of sku-a arrived damaged"})
    assert investigate(db, row) == 0
    from app.services.receivables import split_balance
    assert split_balance(db, row)["outstanding_cents"] == 100000
    damage = db.query(models.CaseEvidence).filter_by(
        tenant_id="local", invoice_id=row.id, claim_type="damage_claim").one()
    assert damage.trust_state == "alleged"
    clarification = db.query(models.ClarificationTask).filter_by(status="open").one()
    assert clarification.owner == "customer"
    assert "Unsent draft" in (clarification.draft_preview or "")
    assert db.query(models.ReceivableEntry).count() == 0
    assert db.query(models.SandboxOutbox).count() == 0


def test_full_delivery_creates_no_zero_claim(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")])
    _upload(db, "purchase_order", "po.pdf", {"line_items": [
        _line("A", "Item A", 10, "90", "900")]})
    _upload(db, "delivery_note", "dn.pdf", {"line_items": [
        _line("A", "Item A", 10, "100", "1000")]})
    assert investigate(db, row) == 10000
    assert row.investigation_hold is False
    assert db.query(models.CompetingExplanation).count() == 0
    assert db.query(models.CaseEvidence).filter_by(
        tenant_id="local", invoice_id=row.id, claim_type="dispute_item").count() == 1


def test_damage_allegation_is_idempotent(db):
    row = invoice(db)
    _invoice_doc(db, [_line("A", "Item A", 10, "100", "1000")])
    _upload(db, "message", "msg.pdf", {"text": "3 units of sku-a arrived damaged"})
    assert investigate(db, row) == 0
    assert investigate(db, row) == 0
    assert db.query(models.CaseEvidence).filter_by(
        tenant_id="local", invoice_id=row.id, claim_type="damage_claim").count() == 1
    assert db.query(models.ClarificationTask).filter_by(status="open").count() == 1


def test_stage_separation_allegation_to_posted(db, api):
    row = invoice(db)
    db.commit()
    created = api.post(f"/api/v1/cases/{row.id}/evidence", headers=HEADERS,
        json={"claim_type": "dispute_item", "title": "Claim",
              "description": "Alleged shortage", "source_type": "customer_message",
              "source_reference": "MSG-1", "amount_cents": 5000})
    assert created.json()["trust_state"] == "alleged"
    evidence_id = created.json()["id"]
    verified = api.post(f"/api/v1/cases/{row.id}/evidence/{evidence_id}/review",
                        headers=HEADERS,
                        json={"trust_state": "verified", "reason": "Checked the source line"})
    assert verified.json()["trust_state"] == "verified"
    accepted = api.post(f"/api/v1/cases/{row.id}/evidence/{evidence_id}/review",
                        headers=HEADERS,
                        json={"trust_state": "accepted",
                              "reason": "Authorised for the dispute decision"})
    assert accepted.json()["trust_state"] == "accepted"
    assert db.query(models.ReceivableEntry).count() == 0
    posted = api.post(f"/api/v1/cases/{row.id}/entries", headers=HEADERS,
        json={"kind": "payment", "amount": "100.00", "reference": "M2-POST-1"})
    assert posted.status_code == 201, posted.text
    entry = db.query(models.ReceivableEntry).one()
    assert entry.allocation == "undisputed_first"
    assert db.get(models.CaseEvidence, evidence_id).trust_state == "accepted"


def test_clarification_api_lifecycle(db, api):
    row = invoice(db)
    db.add(models.CaseEvidence(tenant_id="local", invoice_id=row.id, claim_type="invoice_total",
        title="Invoice", description="Synthetic", source_type="staff_record",
        source_reference="synthetic.pdf", amount_cents=100000, trust_state="verified"))
    db.commit()
    evidence_id = db.query(models.CaseEvidence).one().id
    created = api.post(f"/api/v1/cases/{row.id}/clarifications", headers=HEADERS,
        json={"title": "Obtain the signed delivery note for SKU-A",
              "owner": "customer", "source": "customer", "affected_cents": 20000})
    assert created.status_code == 201, created.text
    assert created.json()["duplicate"] is False
    duplicate = api.post(f"/api/v1/cases/{row.id}/clarifications", headers=HEADERS,
        json={"title": "Obtain the signed delivery note for SKU-A",
              "owner": "customer", "source": "customer", "affected_cents": 20000})
    assert duplicate.json()["duplicate"] is True
    fulfilled = api.post(
        f"/api/v1/cases/{row.id}/clarifications/{created.json()['id']}/fulfill",
        headers=HEADERS, json={"evidence_id": evidence_id})
    assert fulfilled.status_code == 200, fulfilled.text
    closed = api.post(
        f"/api/v1/cases/{row.id}/clarifications/{created.json()['id']}/fulfill",
        headers=HEADERS, json={"evidence_id": evidence_id})
    assert closed.status_code == 409


def test_unit_rule_api_validation(db, api):
    row = invoice(db)
    db.commit()
    created = api.post(f"/api/v1/cases/{row.id}/unit-rules", headers=HEADERS,
                       json={"from_unit": "box", "to_unit": "piece", "factor": "10"})
    assert created.status_code == 201, created.text
    same = api.post(f"/api/v1/cases/{row.id}/unit-rules", headers=HEADERS,
                    json={"from_unit": "box", "to_unit": "piece", "factor": "10"})
    assert same.status_code == 201
    assert same.json()["id"] == created.json()["id"]
    conflict = api.post(f"/api/v1/cases/{row.id}/unit-rules", headers=HEADERS,
                        json={"from_unit": "box", "to_unit": "piece", "factor": "12"})
    assert conflict.status_code == 409
    bad = api.post(f"/api/v1/cases/{row.id}/unit-rules", headers=HEADERS,
                   json={"from_unit": "box", "to_unit": "piece", "factor": "0"})
    assert bad.status_code == 422
    listed = api.get(f"/api/v1/cases/{row.id}/unit-rules", headers=HEADERS)
    assert [r["factor"] for r in listed.json()] == ["10"]


def test_line_matching_pure_rules():
    converted, rule = convert_quantity(to_decimal("2"), "box", "piece",
                                       [("box", "piece", "10")])
    assert converted == to_decimal("20")
    assert rule == ("box", "piece", "10")
    same, _ = convert_quantity(to_decimal("2"), "Box", "box", [])
    assert same == to_decimal("2")
    with pytest.raises(ValueError, match="Unit mismatch"):
        convert_quantity(to_decimal("2"), "box", "piece", [])
    assert tax_basis_plausible({"tax_amount": "180", "total_amount": "1180"},
                               {"total_amount": "1000"}, to_decimal("180")) is True
    assert tax_basis_plausible({"tax_amount": "180", "total_amount": "1180"},
                               {"total_amount": "1000"}, to_decimal("200")) is False
    assert tax_basis_plausible({"total_amount": "1180"},
                               {"total_amount": "1000"}, to_decimal("180")) is False
    with pytest.raises(ValueError, match="rounding"):
        to_cents(to_decimal("10.005"))
    assert match_sku_in_text("short by 2 units of sku-a", ["a", "b"]) == ["a"]
    assert match_sku_in_text("short by 2 units", ["a", "b"]) == []
