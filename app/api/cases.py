"""Assisted collection cases, staff-recorded payments, and customer replies."""
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services.receivables import balance_cents, opening_cents, post_entry, split_balance
from app.services.security import detect_prompt_injection

router = APIRouter(prefix="/cases", tags=["Cases"])


class BalanceAdjustment(BaseModel):
    kind: Literal["payment", "credit"]
    amount: Decimal = Field(gt=0, decimal_places=2)
    reference: str = Field(min_length=1, max_length=120)
    note: str = ""


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


class ReverseEntry(BaseModel):
    reason: str = Field(min_length=3)


class ResumeCase(BaseModel):
    reason: str = Field(min_length=3)
    consent_restored: bool = False


def _invoice(db: Session, invoice_id: int, identity: Identity) -> models.Invoice:
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id or invoice.invoice_type != "AR":
        raise HTTPException(status_code=404, detail="Receivable case not found")
    return invoice


def _summary(db: Session, invoice: models.Invoice) -> dict:
    split = split_balance(db, invoice)
    return {
        "invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "customer": invoice.counterparty_name,
        "email": invoice.counterparty_email,
        "phone": invoice.counterparty_phone,
        "currency": invoice.currency or "USD",
        "due_date": invoice.due_date.isoformat(),
        "status": invoice.status,
        "balance_cents": split["outstanding_cents"],
        "invoice_total_cents": split["invoice_total_cents"],
        "received_cents": split["received_cents"],
        "outstanding_cents": split["outstanding_cents"],
        "disputed_cents": split["disputed_cents"],
        "undisputed_cents": split["undisputed_cents"],
        "amounts": {
            "invoice_total": str(split["invoice_total"]),
            "received": str(split["received"]),
            "outstanding": str(split["outstanding"]),
            "disputed": str(split["disputed"]),
            "undisputed": str(split["undisputed"]),
        },
        "source_system": invoice.source_system,
        "contact_suppressed": bool(invoice.contact_suppressed),
        "contact_opt_out": bool(invoice.contact_opt_out),
        "dispute_open": bool(invoice.dispute_open),
        "requires_human_review": bool(invoice.requires_human_review),
    }


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
    return result


@router.get("/{invoice_id}/evidence")
def list_evidence(invoice_id: int, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    _invoice(db, invoice_id, identity)
    return db.query(models.CaseEvidence).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(models.CaseEvidence.id).all()


@router.post("/{invoice_id}/evidence", status_code=201)
def add_evidence(invoice_id: int, payload: EvidenceInput, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    _invoice(db, invoice_id, identity)
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
        verified=True,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    return evidence


@router.post("/{invoice_id}/entries", status_code=201)
def record_entry(invoice_id: int, payload: BalanceAdjustment, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    existing = db.query(models.ReceivableEntry).filter_by(
        tenant_id=identity.tenant_id, source="manual", reference=payload.reference.strip()).first()
    try:
        entry = post_entry(db, invoice, kind=payload.kind, amount=payload.amount,
                           source="manual", reference=payload.reference.strip(),
                           actor=identity.actor, note=payload.note)
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
    is_inj, inj_reason = detect_prompt_injection(payload.body)
    category = "untrusted_evidence" if is_inj else payload.category

    message = models.CustomerMessage(
        tenant_id=identity.tenant_id,
        invoice_id=invoice_id,
        category=category,
        body=payload.body,
        actor=identity.actor,
        is_injection=is_inj,
        rejection_reason=inj_reason,
    )
    db.add(message)

    if is_inj:
        invoice.contact_suppressed = True
        invoice.requires_human_review = True
        db.add(models.AuditEvent(
            tenant_id=identity.tenant_id,
            actor=identity.actor,
            action="injection_attempt_blocked",
            entity_type="invoice",
            entity_id=str(invoice_id),
            details=inj_reason,
        ))
        # Record untrusted evidence record
        db.add(models.CaseEvidence(
            tenant_id=identity.tenant_id,
            invoice_id=invoice_id,
            claim_type="untrusted_customer_message",
            title="Adversarial Injection Attempt Blocked",
            description=f"Customer attempted instruction override: {inj_reason}",
            source_type="customer_message",
            source_reference=f"MSG-{payload.body[:20]}",
            source_snippet=payload.body,
            verified=False,
        ))
    else:
        if payload.category in ("paid_claim", "dispute", "opt_out"):
            invoice.contact_suppressed = True
        if payload.category == "opt_out":
            invoice.contact_opt_out = True
        if payload.category == "dispute":
            invoice.dispute_open = True
            invoice.status = "disputed"
        db.add(models.AuditEvent(
            tenant_id=identity.tenant_id,
            actor=identity.actor,
            action="customer_reply_recorded",
            entity_type="invoice",
            entity_id=str(invoice_id),
            details=payload.category,
        ))

    db.commit()
    return {
        "message_id": message.id,
        "is_injection": is_inj,
        "rejection_reason": inj_reason,
        "contact_suppressed": bool(invoice.contact_suppressed),
        "requires_human_review": bool(invoice.requires_human_review),
    }



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
                                    actor=identity.actor, note=payload.reason)
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
    invoice.dispute_open = False
    balance = balance_cents(db, invoice)
    invoice.status = "paid" if balance == 0 else (
        "partially_matched" if balance < opening_cents(invoice) else "pending")
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="collection_resumed", entity_type="invoice",
                             entity_id=str(invoice_id), details=payload.reason))
    db.commit()
    return _summary(db, invoice)
