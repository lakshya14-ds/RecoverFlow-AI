"""Staff triage and two-way WhatsApp replies, templates, consent, delivery."""
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services.comms import (CHANNELS, LANGUAGES, CommsBlocked,
                                check_template_send, render_template,
                                toggle_on)
from app.services.negotiation import guard_outbound
from app.services.receivables import split_balance

router = APIRouter(prefix="/messages", tags=["messages"])


class TriageInput(BaseModel):
    invoice_id: int
    category: Literal["question", "needs_time", "paid_claim", "dispute", "opt_out", "other"]


class ReplyInput(BaseModel):
    body: str = Field(min_length=1, max_length=4096)
    idempotency_key: UUID
    language: str = Field(default="en", max_length=16)
    template_id: Optional[int] = None
    variables: list[str] = Field(default_factory=list)


class TemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    language: str = Field(default="en", max_length=16)
    category: str = Field(default="utility", max_length=32)
    body: str = Field(min_length=1, max_length=2000)


class PreferenceInput(BaseModel):
    invoice_id: int
    channel: str = Field(max_length=16)
    opted_in: bool = True
    basis: str = Field(default="explicit", max_length=16)
    language: str = Field(default="en", max_length=16)


def _validate_template_body(body):
    import re
    numbers = sorted({int(n) for n in re.findall(r"{{(\d+)}}", body)})
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError("Template variables must be sequential {{1}}..{{n}}")
    if len(re.findall(r"{{", body)) != len(numbers):
        raise ValueError("Template has malformed variable placeholders")


def _invoice(db, invoice_id, tenant_id):
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != tenant_id or invoice.invoice_type != "AR":
        raise HTTPException(status_code=404, detail="Receivable not found")
    return invoice


def _template(db, template_id, tenant_id):
    template = db.get(models.MessageTemplate, template_id)
    if not template or template.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


def _outbound_view(row):
    return {"id": row.id, "invoice_id": row.invoice_id,
            "inbound_id": row.inbound_id, "provider": row.provider,
            "provider_message_id": row.provider_message_id,
            "recipient": row.recipient, "body": row.body,
            "language": row.language, "template_id": row.template_id,
            "status": row.status,
            "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
            "failure_reason": row.failure_reason,
            "held_until": row.held_until.isoformat() if row.held_until else None}


@router.get("/inbox")
def inbox(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    return db.query(models.InboundMessage).filter_by(tenant_id=identity.tenant_id).order_by(
        models.InboundMessage.received_at.desc()).limit(100).all()


@router.post("/{message_id}/triage")
def triage(message_id: int, payload: TriageInput, db: Session = Depends(get_db),
           identity: Identity = Depends(get_identity)):
    from app.services.customer_messages import record_customer_message
    incoming = db.get(models.InboundMessage, message_id)
    invoice = db.get(models.Invoice, payload.invoice_id)
    if not incoming or incoming.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Message not found")
    if not invoice or invoice.tenant_id != identity.tenant_id or invoice.invoice_type != "AR":
        raise HTTPException(status_code=404, detail="Receivable not found")
    if incoming.status == "triaged":
        raise HTTPException(status_code=409, detail="Message has already been triaged")
    incoming.invoice_id = invoice.id
    incoming.status = "triaged"
    invoice.contact_suppressed = True
    # The shared path routes the reply into the case lifecycle: dispute and
    # opt-out flags, injection screening, checkpoint, supervisor reassessment.
    record_customer_message(
        db, identity.tenant_id, "meta_whatsapp:" + incoming.external_id,
        invoice, payload.category, incoming.body, source="meta_whatsapp")
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="inbound_message_triaged", entity_type="message",
                             entity_id=str(message_id), details=payload.category))
    db.commit()
    return {"status": "triaged", "invoice_id": invoice.id}


def _live_send_or_sandbox(db, identity, outgoing, channel):
    """Attempt a live provider send when explicitly enabled, else sandbox."""
    from app.services import meta_whatsapp
    enabled = toggle_on(db, identity.tenant_id, "whatsapp_enabled")
    if channel == "email":
        enabled = enabled and toggle_on(db, identity.tenant_id, "email_enabled")
    if not enabled:
        outgoing.provider = "sandbox_" + channel
        outgoing.status = "sandbox_sent"
        return "sandbox"
    if channel != "whatsapp" or identity.tenant_id != "local":
        raise CommsBlocked("Live send is wired for the pilot WhatsApp number only")
    if not meta_whatsapp.outbound_configured():
        raise CommsBlocked("WhatsApp provider is not configured")
    outgoing.provider = "meta_whatsapp"
    outgoing.status = "sending"
    db.flush()
    try:
        outgoing.provider_message_id = meta_whatsapp.send_reply(outgoing)
    except Exception as exc:
        outgoing.status = "failed"
        outgoing.failure_reason = f"Provider send failed: {exc}"[:500]
        db.flush()
        raise CommsBlocked("Provider send failed; recorded for retry") from exc
    outgoing.status = "sent"
    return "live"


@router.post("/{message_id}/reply", status_code=201)
def reply(message_id: int, payload: ReplyInput, db: Session = Depends(get_db),
          identity: Identity = Depends(get_identity)):
    incoming = db.get(models.InboundMessage, message_id)
    if not incoming or incoming.tenant_id != identity.tenant_id or incoming.status != "triaged":
        raise HTTPException(status_code=404, detail="Triaged inbound message not found")
    invoice = db.get(models.Invoice, incoming.invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id or invoice.contact_opt_out:
        raise HTTPException(status_code=409, detail="Customer contact is not allowed")
    split = split_balance(db, invoice)
    if invoice.investigation_hold:
        raise HTTPException(status_code=409, detail="Investigation requires staff review")
    language = (payload.language or "en").strip().lower()
    if language not in LANGUAGES:
        raise HTTPException(status_code=422, detail="Language must be en, hi, or hinglish")
    received_at = incoming.received_at.replace(tzinfo=timezone.utc) if incoming.received_at.tzinfo is None else incoming.received_at
    expired = datetime.now(timezone.utc) - received_at >= timedelta(hours=24)
    template = None
    body = payload.body
    held_until = None
    if expired and payload.template_id is None:
        raise HTTPException(status_code=409, detail="Customer service window has expired; use an approved template")
    if payload.template_id is not None:
        template = _template(db, payload.template_id, identity.tenant_id)
        try:
            body = render_template(template.body, payload.variables)
            _, held_until = check_template_send(
                db, identity.tenant_id, invoice, "whatsapp", template, language)
        except CommsBlocked as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    allowed, reason = guard_outbound(body, split["disputed_cents"], split["undisputed_cents"])
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    key = str(payload.idempotency_key)
    previous = db.query(models.OutboundMessage).filter_by(
        tenant_id=identity.tenant_id, idempotency_key=key).first()
    if previous:
        if previous.inbound_id != message_id or previous.body != body:
            raise HTTPException(status_code=409, detail="Idempotency key belongs to another reply")
        return previous
    outgoing = models.OutboundMessage(
        tenant_id=identity.tenant_id, inbound_id=message_id, invoice_id=invoice.id,
        idempotency_key=key, provider="sandbox_whatsapp", recipient=incoming.sender,
        body=body, language=language, template_id=template.id if template else None,
        status="sandbox_sent")
    db.add(outgoing)
    db.flush()
    if held_until is not None:
        outgoing.status = "held_quiet_hours"
        outgoing.held_until = held_until
        db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                                 action="message_held_quiet_hours", entity_type="message",
                                 entity_id=str(outgoing.id)))
        db.commit()
        db.refresh(outgoing)
        return outgoing
    try:
        mode = _live_send_or_sandbox(db, identity, outgoing, "whatsapp")
    except CommsBlocked as exc:
        db.rollback()
        raise HTTPException(status_code=502 if "failed" in str(exc).lower()
                            else 409, detail=str(exc)) from exc
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="whatsapp_reply_sandbox_queued" if mode == "sandbox"
                             else "whatsapp_reply_sent",
                             entity_type="message", entity_id=str(outgoing.id)))
    db.commit()
    db.refresh(outgoing)
    return outgoing


@router.get("/outbound")
def outbound_list(invoice_id: Optional[int] = None, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    query = db.query(models.OutboundMessage).filter_by(tenant_id=identity.tenant_id)
    if invoice_id is not None:
        _invoice(db, invoice_id, identity.tenant_id)
        query = query.filter_by(invoice_id=invoice_id)
    rows = query.order_by(models.OutboundMessage.id).limit(200).all()
    return [_outbound_view(row) for row in rows]


@router.post("/outbound/{outbound_id}/release")
def release_held(outbound_id: int, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    from app.services.comms import in_quiet_hours, quiet_window
    row = db.get(models.OutboundMessage, outbound_id)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Message not found")
    if row.status != "held_quiet_hours":
        raise HTTPException(status_code=409, detail="Only held messages can be released")
    invoice = db.get(models.Invoice, row.invoice_id)
    if not invoice or invoice.contact_opt_out:
        raise HTTPException(status_code=409, detail="Customer contact is not allowed")
    start, end = quiet_window(db, identity.tenant_id)
    if in_quiet_hours(start, end):
        raise HTTPException(status_code=409, detail="Quiet hours are still in effect")
    row.held_until = None
    try:
        mode = _live_send_or_sandbox(db, identity, row, "whatsapp")
    except CommsBlocked as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="message_released", entity_type="message",
                             entity_id=str(row.id),
                             details="sandbox" if mode == "sandbox" else "live"))
    db.commit()
    db.refresh(row)
    return row


@router.get("/templates")
def list_templates(db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    rows = db.query(models.MessageTemplate).filter_by(
        tenant_id=identity.tenant_id).order_by(models.MessageTemplate.id).all()
    return [{"id": row.id, "name": row.name, "language": row.language,
             "category": row.category, "body": row.body, "status": row.status,
             "created_by": row.created_by, "approved_by": row.approved_by}
            for row in rows]


@router.post("/templates", status_code=201)
def create_template(payload: TemplateInput, db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    language = payload.language.strip().lower()
    if language not in LANGUAGES:
        raise HTTPException(status_code=422, detail="Language must be en, hi, or hinglish")
    if payload.category.strip().lower() not in ("utility", "marketing", "authentication"):
        raise HTTPException(status_code=422, detail="Category must be utility, marketing, or authentication")
    try:
        _validate_template_body(payload.body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if db.query(models.MessageTemplate).filter_by(
            tenant_id=identity.tenant_id, name=payload.name.strip()).first():
        raise HTTPException(status_code=409, detail="Template name already exists")
    row = models.MessageTemplate(
        tenant_id=identity.tenant_id, name=payload.name.strip(),
        language=language, category=payload.category.strip().lower(),
        body=payload.body, status="draft", created_by=identity.actor)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "status": row.status}


@router.post("/templates/{template_id}/approve")
def approve_template(template_id: int, db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    template = _template(db, template_id, identity.tenant_id)
    if template.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft templates can be approved")
    template.status = "approved"
    template.approved_by = identity.actor
    template.approved_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="template_approved", entity_type="message_template",
                             entity_id=str(template.id)))
    db.commit()
    return {"id": template.id, "status": template.status}


@router.post("/templates/{template_id}/archive")
def archive_template(template_id: int, db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    template = _template(db, template_id, identity.tenant_id)
    template.status = "archived"
    db.commit()
    return {"id": template.id, "status": template.status}


@router.get("/preferences")
def get_preferences(invoice_id: int, db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity.tenant_id)
    rows = db.query(models.CommsPreference).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).all()
    return [{"channel": row.channel, "opted_in": row.opted_in,
             "basis": row.basis, "language": row.language}
            for row in rows]


@router.put("/preferences")
def set_preference(payload: PreferenceInput, db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    from app.services.comms import BASES
    invoice = _invoice(db, payload.invoice_id, identity.tenant_id)
    channel = payload.channel.strip().lower()
    if channel not in CHANNELS:
        raise HTTPException(status_code=422, detail="Channel must be whatsapp or email")
    if payload.basis.strip().lower() not in BASES:
        raise HTTPException(status_code=422, detail="Basis must be explicit, implicit, or contract")
    if payload.language.strip().lower() not in LANGUAGES:
        raise HTTPException(status_code=422, detail="Language must be en, hi, or hinglish")
    row = db.query(models.CommsPreference).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id,
        channel=channel).first()
    if row:
        row.opted_in = payload.opted_in
        row.basis = payload.basis.strip().lower()
        row.language = payload.language.strip().lower()
        row.updated_by = identity.actor
    else:
        row = models.CommsPreference(
            tenant_id=identity.tenant_id, invoice_id=invoice.id,
            channel=channel, opted_in=payload.opted_in,
            basis=payload.basis.strip().lower(),
            language=payload.language.strip().lower(),
            updated_by=identity.actor)
        db.add(row)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="comms_preference_updated",
                             entity_type="comms_preference",
                             entity_id=f"{invoice.id}:{channel}",
                             details=f"opted_in={payload.opted_in}"))
    db.commit()
    return {"channel": row.channel, "opted_in": row.opted_in,
            "basis": row.basis, "language": row.language}
