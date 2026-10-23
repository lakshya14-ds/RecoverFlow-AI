"""Staff triage and two-way WhatsApp replies."""
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services import meta_whatsapp

router = APIRouter(prefix="/messages", tags=["messages"])


class TriageInput(BaseModel):
    invoice_id: int
    category: Literal["question", "needs_time", "paid_claim", "dispute", "opt_out", "other"]


class ReplyInput(BaseModel):
    body: str = Field(min_length=1, max_length=4096)
    idempotency_key: UUID


@router.get("/inbox")
def inbox(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    return db.query(models.InboundMessage).filter_by(tenant_id=identity.tenant_id).order_by(
        models.InboundMessage.received_at.desc()).limit(100).all()


@router.post("/{message_id}/triage")
def triage(message_id: int, payload: TriageInput, db: Session = Depends(get_db),
           identity: Identity = Depends(get_identity)):
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
    if payload.category == "opt_out":
        invoice.contact_opt_out = True
    if payload.category == "dispute":
        invoice.dispute_open = True
        invoice.status = "disputed"
    db.add(models.CustomerMessage(tenant_id=identity.tenant_id, invoice_id=invoice.id,
                                   category=payload.category, body=incoming.body,
                                   actor="meta_whatsapp:" + incoming.external_id))
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="inbound_message_triaged", entity_type="message",
                             entity_id=str(message_id), details=payload.category))
    db.commit()
    return {"status": "triaged", "invoice_id": invoice.id}


@router.post("/{message_id}/reply", status_code=201)
def reply(message_id: int, payload: ReplyInput, db: Session = Depends(get_db),
          identity: Identity = Depends(get_identity)):
    if identity.tenant_id != "local" or not meta_whatsapp.outbound_configured():
        raise HTTPException(status_code=503, detail="Meta WhatsApp is not configured")
    incoming = db.get(models.InboundMessage, message_id)
    if not incoming or incoming.tenant_id != identity.tenant_id or incoming.status != "triaged":
        raise HTTPException(status_code=404, detail="Triaged inbound message not found")
    invoice = db.get(models.Invoice, incoming.invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id or invoice.contact_opt_out:
        raise HTTPException(status_code=409, detail="Customer contact is not allowed")
    received_at = incoming.received_at.replace(tzinfo=timezone.utc) if incoming.received_at.tzinfo is None else incoming.received_at
    if datetime.now(timezone.utc) - received_at >= timedelta(hours=24):
        raise HTTPException(status_code=409, detail="Customer service window has expired; use an approved template")
    key = str(payload.idempotency_key)
    previous = db.query(models.OutboundMessage).filter_by(
        tenant_id=identity.tenant_id, idempotency_key=key).first()
    if previous:
        if previous.inbound_id != message_id or previous.body != payload.body:
            raise HTTPException(status_code=409, detail="Idempotency key belongs to another reply")
        return previous
    outgoing = models.OutboundMessage(
        tenant_id=identity.tenant_id, inbound_id=message_id, invoice_id=invoice.id,
        idempotency_key=key, provider="meta_whatsapp", recipient=incoming.sender,
        body=payload.body, status="sending")
    db.add(outgoing)
    db.commit()
    db.refresh(outgoing)
    try:
        outgoing.provider_message_id = meta_whatsapp.send_reply(outgoing)
    except Exception as exc:
        outgoing.status = "needs_review"
        db.commit()
        raise HTTPException(status_code=502, detail="WhatsApp send is unresolved; check Meta before retrying") from exc
    outgoing.status = "sent"
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="whatsapp_reply_sent", entity_type="message",
                             entity_id=str(outgoing.id)))
    db.commit()
    db.refresh(outgoing)
    return outgoing
