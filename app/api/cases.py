"""Assisted collection cases, staff-recorded payments, and customer replies."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.services.receivables import balance_cents, post_entry, split_balance
from app.services.case_lifecycle import checkpoint, settle_invoice_status
from app.services.security import detect_prompt_injection

router = APIRouter(prefix="/cases", tags=["Cases"])


class BalanceAdjustment(BaseModel):
    kind: Literal["payment", "credit"]
    amount: Decimal = Field(gt=0, decimal_places=2)
    reference: str = Field(min_length=1, max_length=120)
    note: str = ""
    allocation: Literal["undisputed_first", "disputed_first", "undisputed", "disputed"] = "undisputed_first"
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class CustomerReply(BaseModel):
    category: Literal["question", "needs_time", "paid_claim", "dispute", "opt_out", "untrusted_evidence", "other"]
    body: str = Field(min_length=1)


class EvidenceInput(BaseModel):
    claim_type: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1)
    source_type: str = Field(min_length=1, max_length=50)
    source_reference: str = Field(min_length=1, max_length=150)
    source_snippet: str = ""
    amount_cents: int | None = None
    trust_state: Literal["alleged", "extracted", "verified"] = "alleged"
    decision_reason: str = ""
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class EvidenceReview(BaseModel):
    trust_state: Literal["verified", "accepted", "rejected"]
    reason: str = Field(min_length=5, max_length=1000)
    amount_cents: int | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class ExplanationResolve(BaseModel):
    hypothesis: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=5, max_length=1000)


class ClarificationInput(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    owner: Literal["staff", "customer"]
    source: str = Field(min_length=3, max_length=300)
    due_date: str = ""
    affected_cents: int = Field(default=0, ge=0)


class ClarificationFulfill(BaseModel):
    evidence_id: int = Field(gt=0)


class UnitRuleInput(BaseModel):
    from_unit: str = Field(min_length=1, max_length=50)
    to_unit: str = Field(min_length=1, max_length=50)
    factor: str = Field(min_length=1, max_length=30)


class PromiseInput(BaseModel):
    message_id: int = Field(gt=0)


class PromiseCancel(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ReverseEntry(BaseModel):
    reason: str = Field(min_length=3)


class ResumeCase(BaseModel):
    reason: str = Field(min_length=3)
    consent_restored: bool = False


class DisputeReview(BaseModel):
    disputed_amount: Decimal = Field(ge=0, decimal_places=2)
    evidence_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=1000)


class AliasInput(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    canonical_sku: str = Field(min_length=1, max_length=200)


def _invoice(db: Session, invoice_id: int, identity: Identity) -> models.Invoice:
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id or invoice.invoice_type != "AR":
        raise HTTPException(status_code=404, detail="Receivable case not found")
    return invoice


def _party_view(db: Session, invoice: models.Invoice):
    if not invoice.counterparty_id:
        return None
    party = db.get(models.Counterparty, invoice.counterparty_id)
    if not party or party.tenant_id != invoice.tenant_id:
        return None
    return {"id": party.id, "name": party.name,
            "display_name": party.display_name or party.name,
            "gstin": party.gstin, "status": party.status}


def _summary(db: Session, invoice: models.Invoice) -> dict:
    split = split_balance(db, invoice, allow_inconsistent=True)
    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer": invoice.counterparty_name,
        "counterparty": _party_view(db, invoice),
        "email": invoice.counterparty_email,
        "phone": invoice.counterparty_phone,
        "currency": invoice.currency or "INR",
        "due_date": invoice.due_date.isoformat(),
        "status": invoice.status,
        "balance_cents": split["outstanding_cents"],
        "invoice_total_cents": split["invoice_total_cents"],
        "received_cents": split["received_cents"],
        "credits_cents": split["credits_cents"],
        "unallocated_adjustments_cents": split["unallocated_adjustments_cents"],
        "outstanding_cents": split["outstanding_cents"],
        "disputed_cents": split["disputed_cents"],
        "undisputed_cents": split["undisputed_cents"],
        "amounts": {
            "invoice_total": str(split["invoice_total"]),
            "received": str(split["received"]),
            "credits": str(split["credits"]),
            "outstanding": str(split["outstanding"]),
            "disputed": str(split["disputed"]),
            "undisputed": str(split["undisputed"]),
        },
        "source_system": invoice.source_system,
        "contact_suppressed": bool(invoice.contact_suppressed),
        "contact_opt_out": bool(invoice.contact_opt_out),
        "dispute_open": bool(invoice.dispute_open),
        "requires_human_review": bool(invoice.requires_human_review),
        "investigation_hold": bool(invoice.investigation_hold),
        "investigation_reason": invoice.investigation_reason,
        "reconciliation_error": split["reconciliation_error"],
    }


EVIDENCE_DOC_DIRS = ("invoices", "po")


@router.get("/{invoice_id}/evidence-files/{filename}")
def get_evidence_file(invoice_id: int, filename: str,
                      db: Session = Depends(get_db),
                      identity: Identity = Depends(get_identity)):
    """Serve a synthetic doc fixture linked to this tenant's own evidence row."""
    invoice = _invoice(db, invoice_id, identity)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.pdf", filename or ""):
        raise HTTPException(status_code=404, detail="Evidence file not found")
    refs = {row.source_reference for row in db.query(models.CaseEvidence).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).all()}
    match = next((f"docs/{d}/{filename}" for d in EVIDENCE_DOC_DIRS
                  if f"docs/{d}/{filename}" in refs), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Evidence file not found")
    docs_root = (Path(settings.BASE_DIR) / "docs").resolve()
    path = (docs_root / match[5:]).resolve()
    if docs_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence file not found")
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.get("")
def list_cases(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    invoices = db.query(models.Invoice).filter_by(
        tenant_id=identity.tenant_id, invoice_type="AR").order_by(models.Invoice.due_date).limit(200).all()
    return [_summary(db, invoice) for invoice in invoices]


@router.get("/{invoice_id}")
def get_case(invoice_id: int, db: Session = Depends(get_db),
             identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    result = _summary(db, invoice)
    result["workflow"] = db.query(models.CaseWorkflow).filter_by(tenant_id=identity.tenant_id, invoice_id=invoice_id).first()
    result["investigation_reason"] = invoice.investigation_reason
    result["line_items"] = [{
        "line_no": row.line_no, "sku": row.sku, "description": row.description,
        "hsn": row.hsn,
        "quantity": str(row.quantity) if row.quantity is not None else None,
        "unit": row.unit, "unit_price_cents": row.unit_price_cents,
        "amount_cents": row.amount_cents, "tax_rate_bps": row.tax_rate_bps,
        "cgst_cents": row.cgst_cents, "sgst_cents": row.sgst_cents,
        "igst_cents": row.igst_cents, "status": row.status} for row in
        db.query(models.InvoiceLineItem).filter_by(
            tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
            models.InvoiceLineItem.line_no).all()]
    result["tax_split"] = {"cgst_cents": int(invoice.cgst_cents or 0),
                           "sgst_cents": int(invoice.sgst_cents or 0),
                           "igst_cents": int(invoice.igst_cents or 0),
                           "freight_cents": int(invoice.freight_cents or 0),
                           "roundoff_cents": int(invoice.roundoff_cents or 0)}
    result["credit_debit_notes"] = [{
        "id": row.id, "note_type": row.note_type, "number": row.number,
        "amount_cents": row.amount_cents, "status": row.status,
        "entry_id": row.entry_id} for row in
        db.query(models.CreditDebitNote).filter_by(
            tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
            models.CreditDebitNote.id).all()]
    result["supporting_documents"] = [{
        "id": row.id, "doc_type": row.doc_type, "number": row.number,
        "status": row.status, "summary": json.loads(row.summary_json or "{}")}
        for row in db.query(models.SupportingDocument).filter_by(
            tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
            models.SupportingDocument.id).all()]
    result["entries"] = db.query(models.ReceivableEntry).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(models.ReceivableEntry.id).all()
    result["messages"] = db.query(models.CustomerMessage).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(models.CustomerMessage.id).all()
    result["evidence"] = db.query(models.CaseEvidence).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(models.CaseEvidence.id).all()
    result["campaigns"] = db.query(models.DunningCampaign).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(models.DunningCampaign.id).all()
    result["agent_notes"] = db.query(models.AgentCaseNote).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(models.AgentCaseNote.id).all()
    result["explanations"] = db.query(models.CompetingExplanation).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(
        models.CompetingExplanation.id).all()
    result["clarifications"] = db.query(models.ClarificationTask).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(
        models.ClarificationTask.id).all()
    result["promises"] = db.query(models.PromiseToPay).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(
        models.PromiseToPay.id).all()
    return result


@router.get("/{invoice_id}/evidence")
def list_evidence(invoice_id: int, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    _invoice(db, invoice_id, identity)
    return db.query(models.CaseEvidence).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(models.CaseEvidence.id).all()


@router.post("/{invoice_id}/investigate")
def investigate_case(invoice_id: int, db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    from app.services.investigation import investigate
    invoice = _invoice(db, invoice_id, identity)
    try:
        investigate(db, invoice)
    except ValueError as exc:
        db.commit()  # Preserve the conflict and its evidence; never silently clear it.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _summary(db, invoice)


def _supersede_proposed_drafts(db: Session, invoice, actor: str) -> list:
    """Mark superseded drafts stale when staff review moves the case.

    Any later action on these proposals would 409 through the freshness
    check anyway; the explicit transition keeps the verification gate
    honest instead of failing forever on drafts nobody will touch.
    """
    from app.services.controlled_agent import snapshot
    try:
        _, digest, _ = snapshot(db, invoice)
    except ValueError:
        return []
    rows = db.query(models.AgentProposal).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, status="proposed").all()
    stale_ids = []
    for row in rows:
        if row.context_hash != digest:
            row.status = "stale"
            stale_ids.append(row.id)
    if stale_ids:
        db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
                                 action="drafts_superseded", entity_type="invoice",
                                 entity_id=str(invoice.id),
                                 details=",".join(str(i) for i in stale_ids)))
    return stale_ids


@router.post("/{invoice_id}/dispute-review")
def review_dispute(invoice_id: int, payload: DisputeReview, db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    from app.services.investigation import document_digest
    invoice = _invoice(db, invoice_id, identity)
    evidence = db.get(models.CaseEvidence, payload.evidence_id)
    if not evidence or evidence.tenant_id != identity.tenant_id or evidence.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Case evidence not found")
    amount = int(payload.disputed_amount * 100)
    if amount > balance_cents(db, invoice):
        raise HTTPException(status_code=409, detail="Dispute exceeds outstanding balance")
    prior = invoice.disputed_cents
    invoice.disputed_cents = amount
    invoice.dispute_open = amount > 0
    invoice.investigation_hold = False
    invoice.investigation_reason = None
    invoice.investigation_decision_hash = document_digest(db, invoice)
    settle_invoice_status(db, invoice, force=True)
    db.add(models.CaseEvidence(tenant_id=identity.tenant_id, invoice_id=invoice.id,
        claim_type="dispute_item", title="Staff-reviewed open dispute", description=payload.reason,
        source_type="staff_review", source_reference=evidence.source_reference,
        amount_cents=amount, verified=True, trust_state="accepted",
        decided_by=identity.actor, decided_at=datetime.now(timezone.utc),
        decision_reason=payload.reason, currency=invoice.currency or "INR"))
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="dispute_reviewed", entity_type="invoice", entity_id=str(invoice.id),
        details=f"old_cents={prior}; new_cents={amount}; evidence_id={evidence.id}; reason={payload.reason}"))
    _supersede_proposed_drafts(db, invoice, identity.actor)
    checkpoint(db, invoice, "dispute_reviewed", identity.actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "staff:dispute_review", identity.actor)
    db.commit()
    return _summary(db, invoice)


@router.post("/{invoice_id}/item-alias")
def register_alias(invoice_id: int, payload: AliasInput, db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    from app.services.investigation import normalize
    _invoice(db, invoice_id, identity)
    alias, canonical = normalize(payload.alias), normalize(payload.canonical_sku)
    if not alias or not canonical:
        raise HTTPException(status_code=422, detail="Alias and SKU must contain letters or digits")
    row = db.query(models.ItemAlias).filter_by(tenant_id=identity.tenant_id, alias=alias).first()
    if row and row.canonical_sku != canonical:
        raise HTTPException(status_code=409, detail="Alias is already assigned to a different SKU")
    if not row:
        row = models.ItemAlias(tenant_id=identity.tenant_id, alias=alias,
            canonical_sku=canonical, approved_by=identity.actor)
        db.add(row)
        db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
            action="item_alias_approved", entity_type="invoice", entity_id=str(invoice_id),
            details=f"{alias} -> {canonical}"))
    db.commit()
    return {"alias": row.alias, "canonical_sku": row.canonical_sku}


@router.post("/{invoice_id}/evidence", status_code=201)
def add_evidence(invoice_id: int, payload: EvidenceInput, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    if payload.trust_state == "verified" and not payload.decision_reason.strip():
        raise HTTPException(status_code=422, detail="A reason is required to mark evidence verified")
    decided = payload.trust_state == "verified"
    evidence = models.CaseEvidence(
        tenant_id=identity.tenant_id,
        invoice_id=invoice_id,
        claim_type=payload.claim_type,
        title=payload.title,
        description=payload.description,
        source_type=payload.source_type,
        source_reference=payload.source_reference,
        source_snippet=payload.source_snippet,
        amount_cents=payload.amount_cents,
        verified=decided,
        trust_state=payload.trust_state,
        decided_by=identity.actor if decided else None,
        decided_at=datetime.now(timezone.utc) if decided else None,
        decision_reason=payload.decision_reason or None,
        currency=payload.currency or invoice.currency or "INR",
    )
    db.add(evidence)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="evidence_added", entity_type="case_evidence", entity_id=str(invoice_id),
        details=f"trust={payload.trust_state}; ref={payload.source_reference}"))
    checkpoint(db, invoice, "evidence_added", identity.actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "staff:evidence_added", identity.actor)
    db.commit()
    db.refresh(evidence)
    return evidence


@router.post("/{invoice_id}/evidence/{evidence_id}/review")
def review_evidence(invoice_id: int, evidence_id: int, payload: EvidenceReview,
                    db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    evidence = db.get(models.CaseEvidence, evidence_id)
    if not evidence or evidence.tenant_id != identity.tenant_id or evidence.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Case evidence not found")
    if evidence.trust_state == "accepted" and payload.trust_state == "accepted":
        raise HTTPException(status_code=409, detail="Evidence is already accepted")
    evidence.trust_state = payload.trust_state
    evidence.verified = payload.trust_state in ("verified", "accepted")
    evidence.decided_by = identity.actor
    evidence.decided_at = datetime.now(timezone.utc)
    evidence.decision_reason = payload.reason
    if payload.amount_cents is not None:
        evidence.amount_cents = payload.amount_cents
    if payload.currency is not None:
        evidence.currency = payload.currency
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="evidence_decision", entity_type="case_evidence", entity_id=str(evidence.id),
        details=f"trust={payload.trust_state}; reason={payload.reason}"))
    checkpoint(db, invoice, "evidence_added", identity.actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "staff:evidence_review", identity.actor)
    db.commit()
    db.refresh(evidence)
    return evidence


@router.post("/{invoice_id}/explanations/{explanation_id}/resolve")
def resolve_explanation(invoice_id: int, explanation_id: int, payload: ExplanationResolve,
                        db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    import json as _json
    invoice = _invoice(db, invoice_id, identity)
    row = db.get(models.CompetingExplanation, explanation_id)
    if not row or row.tenant_id != identity.tenant_id or row.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Competing explanation not found")
    if row.status != "open":
        raise HTTPException(status_code=409, detail="Explanation is already resolved")
    keys = [h.get("key") for h in _json.loads(row.hypotheses_json or "[]")]
    if payload.hypothesis not in keys:
        raise HTTPException(status_code=422, detail="Unknown hypothesis key")
    row.status = "resolved"
    row.resolved_hypothesis = payload.hypothesis
    row.resolved_by = identity.actor
    row.resolution_reason = payload.reason
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="explanation_resolved", entity_type="competing_explanation",
        entity_id=str(row.id), details=f"chose={payload.hypothesis}; reason={payload.reason}"))
    checkpoint(db, invoice, "evidence_added", identity.actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "staff:explanation", identity.actor)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status,
            "resolved_hypothesis": row.resolved_hypothesis}


@router.post("/{invoice_id}/clarifications", status_code=201)
def create_clarification(invoice_id: int, payload: ClarificationInput,
                         db: Session = Depends(get_db),
                         identity: Identity = Depends(get_identity)):
    from datetime import date as _date
    invoice = _invoice(db, invoice_id, identity)
    try:
        due = _date.fromisoformat(payload.due_date) if payload.due_date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Due date must be YYYY-MM-DD")
    key = f"staff:{payload.title[:80]}:{payload.source[:80]}"
    existing = db.query(models.ClarificationTask).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id, key=key,
        status="open").first()
    if existing:
        return {"id": existing.id, "status": existing.status, "duplicate": True}
    row = models.ClarificationTask(
        tenant_id=identity.tenant_id, invoice_id=invoice.id, key=key,
        title=payload.title, owner=payload.owner, source=payload.source,
        due_date=due, affected_cents=payload.affected_cents, status="open",
        draft_preview=(f"Unsent draft - {payload.title} (invoice "
                       f"{invoice.invoice_number}). Staff must review and approve "
                       f"before any customer contact."),
        created_by=identity.actor)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "duplicate": False}


@router.post("/{invoice_id}/clarifications/{clarification_id}/fulfill")
def fulfill_clarification(invoice_id: int, clarification_id: int, payload: ClarificationFulfill,
                          db: Session = Depends(get_db),
                          identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    row = db.get(models.ClarificationTask, clarification_id)
    if not row or row.tenant_id != identity.tenant_id or row.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Clarification task not found")
    if row.status != "open":
        raise HTTPException(status_code=409, detail="Clarification is already closed")
    evidence = db.get(models.CaseEvidence, payload.evidence_id)
    if not evidence or evidence.tenant_id != identity.tenant_id or evidence.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Case evidence not found")
    row.status = "fulfilled"
    row.fulfilled_evidence_id = evidence.id
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="clarification_fulfilled", entity_type="clarification_task",
        entity_id=str(row.id), details=f"evidence_id={evidence.id}"))
    checkpoint(db, invoice, "evidence_added", identity.actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "staff:clarification", identity.actor)
    db.commit()
    return {"id": row.id, "status": row.status}


@router.get("/{invoice_id}/unit-rules")
def list_unit_rules(invoice_id: int, db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    _invoice(db, invoice_id, identity)
    return db.query(models.UnitRule).filter_by(
        tenant_id=identity.tenant_id).order_by(models.UnitRule.id).all()


@router.post("/{invoice_id}/unit-rules", status_code=201)
def create_unit_rule(invoice_id: int, payload: UnitRuleInput,
                     db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    from decimal import Decimal as _Decimal, InvalidOperation as _InvalidOperation
    from app.services.investigation import normalize
    invoice = _invoice(db, invoice_id, identity)
    source, target = normalize(payload.from_unit), normalize(payload.to_unit)
    if not source or not target or source == target:
        raise HTTPException(status_code=422, detail="Units must differ and contain letters or digits")
    try:
        factor = _Decimal(payload.factor)
    except _InvalidOperation:
        raise HTTPException(status_code=422, detail="Factor must be a positive decimal")
    if not factor.is_finite() or factor <= 0:
        raise HTTPException(status_code=422, detail="Factor must be a positive decimal")
    existing = db.query(models.UnitRule).filter_by(
        tenant_id=identity.tenant_id, from_unit=source, to_unit=target).first()
    if existing:
        if existing.factor != format(factor.normalize(), "f"):
            raise HTTPException(status_code=409, detail="A different factor is already approved")
        return existing
    row = models.UnitRule(tenant_id=identity.tenant_id, from_unit=source,
        to_unit=target, factor=format(factor.normalize(), "f"),
        approved_by=identity.actor)
    db.add(row)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="unit_rule_approved", entity_type="invoice", entity_id=str(invoice.id),
        details=f"{source} -> {target} x{row.factor}"))
    db.commit()
    db.refresh(row)
    return row


@router.post("/{invoice_id}/promises", status_code=201)
def record_promise(invoice_id: int, payload: PromiseInput,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    from app.services import promises
    invoice = _invoice(db, invoice_id, identity)
    message = db.get(models.CustomerMessage, payload.message_id)
    if not message or message.tenant_id != identity.tenant_id \
            or message.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Customer message not found")
    try:
        row, duplicate = promises.create_from_message(db, invoice, message, identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "duplicate": duplicate,
            "promised_cents": row.promised_cents,
            "promised_date": row.promised_date.isoformat() if row.promised_date else None,
            "extraction_confidence": row.extraction_confidence}


@router.post("/{invoice_id}/promises/{promise_id}/confirm")
def confirm_promise(invoice_id: int, promise_id: int,
                    db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    from app.services import promises
    invoice = _invoice(db, invoice_id, identity)
    row = db.get(models.PromiseToPay, promise_id)
    if not row or row.tenant_id != identity.tenant_id or row.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Promise not found")
    try:
        promises.confirm(db, row, identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "staff:promise", identity.actor)
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/{invoice_id}/promises/{promise_id}/remind")
def remind_promise(invoice_id: int, promise_id: int,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    from app.services import promises
    invoice = _invoice(db, invoice_id, identity)
    row = db.get(models.PromiseToPay, promise_id)
    if not row or row.tenant_id != identity.tenant_id or row.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Promise not found")
    try:
        promises.remind(db, row, identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"id": row.id, "status": row.status, "reminders_sent": row.reminders_sent}


@router.post("/{invoice_id}/promises/{promise_id}/cancel")
def cancel_promise(invoice_id: int, promise_id: int, payload: PromiseCancel,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    from app.services import promises
    invoice = _invoice(db, invoice_id, identity)
    row = db.get(models.PromiseToPay, promise_id)
    if not row or row.tenant_id != identity.tenant_id or row.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Promise not found")
    try:
        promises.cancel(db, row, identity.actor, payload.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/{invoice_id}/entries", status_code=201)
def record_entry(invoice_id: int, payload: BalanceAdjustment, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin approval required")
    existing = db.query(models.ReceivableEntry).filter_by(
        tenant_id=identity.tenant_id, source="manual", reference=payload.reference.strip()).first()
    try:
        entry = post_entry(db, invoice, kind=payload.kind, amount=payload.amount,
                           source="manual", reference=payload.reference.strip(),
                           actor=identity.actor, note=payload.note, allocation=payload.allocation,
                           currency=payload.currency)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not existing:
        db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                                 action="receivable_" + payload.kind, entity_type="invoice",
                                 entity_id=str(invoice_id), details=payload.reference))
        for link in db.query(models.PaymentLink).filter_by(
                tenant_id=identity.tenant_id, invoice_id=invoice_id).filter(
                models.PaymentLink.status.in_(("open", "partially_paid"))).all():
            link.status = "needs_review"
    db.commit()
    return {"entry_id": entry.id, "balance_cents": balance_cents(db, invoice)}


@router.post("/{invoice_id}/replies", status_code=201)
def record_reply(invoice_id: int, payload: CustomerReply, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    from app.services.customer_messages import record_customer_message
    result = record_customer_message(
        db, identity.tenant_id, identity.actor, invoice,
        payload.category, payload.body, source="staff")
    db.commit()
    return result



@router.post("/{invoice_id}/entries/{entry_id}/reverse", status_code=201)
def reverse_entry(invoice_id: int, entry_id: int, payload: ReverseEntry,
                  db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin approval required")
    invoice = _invoice(db, invoice_id, identity)
    original = db.get(models.ReceivableEntry, entry_id)
    if not original or original.tenant_id != identity.tenant_id or original.invoice_id != invoice_id or original.amount_cents >= 0:
        raise HTTPException(status_code=404, detail="Payment or credit entry not found")
    if db.query(models.ReceivableEntry).filter_by(
        tenant_id=identity.tenant_id, source="reversal", reference=str(entry_id)).first():
        raise HTTPException(status_code=409, detail="Entry was already reversed")
    try:
        reversed_entry = post_entry(db, invoice, kind="reversal", amount=Decimal(-original.amount_cents) / 100,
                                    source="reversal", reference=str(original.id),
                                    actor=identity.actor, note=payload.reason,
                                    reversal_of_id=original.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="receivable_reversed", entity_type="receivable_entry",
                             entity_id=str(entry_id), details=payload.reason))
    db.commit()
    return {"entry_id": reversed_entry.id, "balance_cents": balance_cents(db, invoice)}


@router.post("/{invoice_id}/resume")
def resume_case(invoice_id: int, payload: ResumeCase, db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin approval required")
    invoice = _invoice(db, invoice_id, identity)
    if invoice.requires_human_review:
        raise HTTPException(status_code=409, detail="Complete case review before resuming contact")
    if invoice.contact_opt_out and not payload.consent_restored:
        raise HTTPException(status_code=409, detail="Document restored contact permission before resuming")
    invoice.contact_suppressed = False
    invoice.contact_opt_out = False
    invoice.dispute_open = bool(invoice.disputed_cents)
    settle_invoice_status(db, invoice, force=True)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="collection_resumed", entity_type="invoice",
                             entity_id=str(invoice_id), details=payload.reason))
    _supersede_proposed_drafts(db, invoice, identity.actor)
    checkpoint(db, invoice, "staff_resumed_contact", identity.actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "staff:resume", identity.actor)
    db.commit()
    return _summary(db, invoice)
