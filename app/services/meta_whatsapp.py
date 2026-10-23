"""Meta WhatsApp Cloud API inbox and staff replies inside the customer service window."""
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import models


def configured() -> bool:
    return bool(settings.META_WHATSAPP_APP_SECRET and settings.META_WHATSAPP_VERIFY_TOKEN and
                settings.META_WHATSAPP_PHONE_NUMBER_ID)


def outbound_configured() -> bool:
    return configured() and bool(settings.META_WHATSAPP_ACCESS_TOKEN and
                                 re.fullmatch(r"v\d+\.\d+", settings.META_GRAPH_API_VERSION))


def verify_signature(body: bytes, signature: str) -> bool:
    if not configured() or not signature.startswith("sha256="):
        return False
    expected = hmac.new(settings.META_WHATSAPP_APP_SECRET.encode(), body,
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature[7:], expected)


def normalize_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def receive(db: Session, body: bytes, tenant_id: str = "local") -> dict:
    """Record signed inbound text, pause matching cases, and wait for staff triage."""
    payload = json.loads(body)
    received = duplicated = ignored = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            if str((value.get("metadata") or {}).get("phone_number_id")) != settings.META_WHATSAPP_PHONE_NUMBER_ID:
                ignored += 1
                continue
            for message in value.get("messages", []):
                if message.get("type") != "text" or not message.get("id"):
                    ignored += 1
                    continue
                message_id = message["id"]
                if db.query(models.InboundMessage).filter_by(
                        tenant_id=tenant_id, provider="meta_whatsapp",
                        external_id=message_id).first():
                    duplicated += 1
                    continue
                sender = normalize_phone(message.get("from", ""))
                content = (message.get("text") or {}).get("body", "")[:10000]
                if not sender or not content:
                    ignored += 1
                    continue
                candidates = [invoice for invoice in db.query(models.Invoice).filter_by(
                    tenant_id=tenant_id, invoice_type="AR").all()
                    if normalize_phone(invoice.counterparty_phone or "") == sender]
                for invoice in candidates:
                    invoice.contact_suppressed = True
                    if content.strip().lower() in ("stop", "unsubscribe", "opt out"):
                        invoice.contact_opt_out = True
                linked = candidates[0] if len(candidates) == 1 else None
                inbound = models.InboundMessage(
                    tenant_id=tenant_id, provider="meta_whatsapp", external_id=message_id,
                    sender=sender, body=content, invoice_id=linked.id if linked else None,
                    status="needs_review" if linked else "unassigned")
                db.add(inbound)
                db.add(models.AuditEvent(tenant_id=tenant_id, actor="meta_whatsapp_webhook",
                                         action="inbound_message_received", entity_type="message",
                                         entity_id=message_id))
                received += 1
    db.commit()
    return {"received": received, "duplicated": duplicated, "ignored": ignored}


def send_reply(outbound: models.OutboundMessage) -> str:
    if not outbound_configured():
        raise RuntimeError("Meta WhatsApp Cloud API is not configured")
    url = (f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/"
           f"{settings.META_WHATSAPP_PHONE_NUMBER_ID}/messages")
    data = {"messaging_product": "whatsapp", "to": outbound.recipient,
            "type": "text", "text": {"preview_url": False, "body": outbound.body}}
    with httpx.Client(timeout=15) as client:
        response = client.post(url, json=data,
                               headers={"Authorization": f"Bearer {settings.META_WHATSAPP_ACCESS_TOKEN}"})
        response.raise_for_status()
        result = response.json()
    message_id = (result.get("messages") or [{}])[0].get("id")
    if not message_id:
        raise RuntimeError("Meta did not confirm the outbound message")
    return message_id
