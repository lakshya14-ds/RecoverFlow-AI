"""Razorpay Payment Links and verified payment allocation for the India pilot."""
import hashlib
import hmac
import json
from decimal import Decimal
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.database import models
from app.services.receivables import balance_cents, post_entry


def configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and
                settings.RAZORPAY_WEBHOOK_SECRET)


def validate_mode() -> None:
    mode = settings.RAZORPAY_MODE.lower()
    if mode not in ("test", "live") or not settings.RAZORPAY_KEY_ID.startswith(f"rzp_{mode}_"):
        raise RuntimeError("Razorpay key does not match RAZORPAY_MODE")


def create_remote_link(link: models.PaymentLink, invoice: models.Invoice) -> dict:
    if not configured():
        raise RuntimeError("Razorpay credentials and webhook secret are not configured")
    validate_mode()
    if settings.RAZORPAY_KEY_ID.startswith("rzp_test_mock"):
        return {"id": f"plink_mock_{link.id}", "url": f"https://rzp.io/i/mock_{link.id}"}
    expires_at = link.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    payload = {
        "amount": link.amount_cents, "currency": "INR", "accept_partial": False,
        "expire_by": int(expires_at.timestamp()),
        "reference_id": f"rf-{link.id}",
        "description": f"RecoverFlow receivable {invoice.invoice_number}"[:200],
        "customer": {"name": invoice.counterparty_name[:120],
                     **({"email": invoice.counterparty_email} if invoice.counterparty_email else {})},
        "notify": {"sms": False, "email": False}, "reminder_enable": False,
    }
    with httpx.Client(timeout=15) as client:
        response = client.post("https://api.razorpay.com/v1/payment_links/", json=payload,
                               auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        response.raise_for_status()
        result = response.json()
    url = result.get("short_url", "")
    parsed = urlparse(url)
    if not result.get("id") or parsed.scheme != "https" or parsed.hostname not in (
            "rzp.io", "www.rzp.io", "razorpay.com", "www.razorpay.com"):
        raise RuntimeError("Razorpay returned an invalid payment link")
    return {"id": result["id"], "url": url}


def cancel_remote_link(link: models.PaymentLink) -> None:
    if not configured() or not link.provider_link_id:
        raise RuntimeError("Razorpay link cannot be cancelled without its provider ID")
    validate_mode()
    if settings.RAZORPAY_KEY_ID.startswith("rzp_test_mock"):
        return
    with httpx.Client(timeout=15) as client:
        response = client.post(
            f"https://api.razorpay.com/v1/payment_links/{link.provider_link_id}/cancel",
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        response.raise_for_status()
        result = response.json()
    if result.get("id") != link.provider_link_id or result.get("status") != "cancelled":
        raise RuntimeError("Razorpay did not confirm cancellation")


def find_remote_link(link: models.PaymentLink) -> dict | None:
    """Recover a timed-out creation by the unique reference ID without creating again."""
    if not configured():
        raise RuntimeError("Razorpay is not configured")
    validate_mode()
    if settings.RAZORPAY_KEY_ID.startswith("rzp_test_mock"):
        return {"id": link.provider_link_id or f"plink_mock_{link.id}", "url": link.url or f"https://rzp.io/i/mock_{link.id}", "status": "created"}
    reference = f"rf-{link.id}"
    with httpx.Client(timeout=15) as client:
        response = client.get("https://api.razorpay.com/v1/payment_links/",
                              params={"reference_id": reference},
                              auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        response.raise_for_status()
        candidates = response.json().get("payment_links", [])
    matches = [row for row in candidates if row.get("reference_id") == reference]
    if not matches:
        return None
    if len(matches) != 1:
        raise RuntimeError("Multiple Razorpay links use this reference ID")
    row = matches[0]
    url = row.get("short_url", "")
    parsed = urlparse(url)
    if (not row.get("id") or row.get("amount") != link.amount_cents or
            row.get("currency") != link.currency or parsed.scheme != "https" or
            parsed.hostname not in ("rzp.io", "www.rzp.io", "razorpay.com", "www.razorpay.com")):
        raise RuntimeError("Razorpay link details do not match this receivable")
    return {"id": row["id"], "url": url, "status": row.get("status")}


def verify_signature(body: bytes, signature: str) -> bool:
    if not settings.RAZORPAY_WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), body,
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def process_event(db: Session, tenant_id: str, event_id: str, body: bytes) -> models.ProviderEvent:
    """Called only after raw-body signature verification. Never infer payment from a redirect."""
    digest = hashlib.sha256(body).hexdigest()
    existing = db.query(models.ProviderEvent).filter_by(
        tenant_id=tenant_id, kind="payment", provider="razorpay", event_id=event_id).first()
    if existing:
        if existing.body_sha256 != digest:
            raise ValueError("Webhook event ID was reused with a different payload")
        return existing
    event = models.ProviderEvent(tenant_id=tenant_id, kind="payment", provider="razorpay",
                                 event_id=event_id, body_sha256=digest, status="processing")
    db.add(event)
    db.flush()
    try:
        data = json.loads(body)
        event_type = data.get("event")
        if event_type in ("refund.processed", "payment.refunded", "dispute.created",
                          "dispute.under_review"):
            payload = data.get("payload") or {}
            refund = (payload.get("refund") or {}).get("entity") or {}
            payment = (payload.get("payment") or {}).get("entity") or {}
            dispute = (payload.get("dispute") or {}).get("entity") or {}
            payment_id = refund.get("payment_id") or payment.get("id") or dispute.get("payment_id")
            entry = db.query(models.ReceivableEntry).filter_by(
                tenant_id=tenant_id, source="razorpay", reference=payment_id).first()
            if entry:
                invoice = db.get(models.Invoice, entry.invoice_id)
                invoice.contact_suppressed = True
                invoice.requires_human_review = True
            event.status = "needs_review"
            event.error = "Refund or dispute requires a verified ledger review"
        elif event_type in ("payment_link.cancelled", "payment_link.expired"):
            remote_link = data["payload"]["payment_link"]["entity"]
            link = db.query(models.PaymentLink).filter_by(
                tenant_id=tenant_id, provider="razorpay", provider_link_id=remote_link["id"]).first()
            if not link:
                raise ValueError("Payment link is not known to this tenant")
            link.status = "cancelled" if event_type.endswith("cancelled") else "expired"
            event.status = "processed"
        elif event_type not in ("payment_link.paid", "payment_link.partially_paid"):
            event.status = "ignored"
        else:
            payload = data["payload"]
            payment = payload["payment"]["entity"]
            remote_link = payload["payment_link"]["entity"]
            link = db.query(models.PaymentLink).filter_by(
                tenant_id=tenant_id, provider="razorpay", provider_link_id=remote_link["id"]).first()
            if not link:
                raise ValueError("Payment link is not known to this tenant")
            invoice = db.get(models.Invoice, link.invoice_id)
            if not invoice or invoice.tenant_id != tenant_id or invoice.invoice_type != "AR":
                raise ValueError("Linked receivable is missing")
            if payment.get("status") != "captured" or payment.get("captured") is not True:
                raise ValueError("Payment has not been captured")
            amount_cents = payment.get("amount")
            if (type(amount_cents) is not int or amount_cents <= 0 or
                    payment.get("currency") != link.currency or
                    remote_link.get("currency") != link.currency or
                    remote_link.get("amount") != link.amount_cents):
                raise ValueError("Payment amount or currency does not match the link")
            payment_id = payment.get("id")
            if not isinstance(payment_id, str) or not payment_id.startswith("pay_"):
                raise ValueError("Payment ID is missing")
            post_entry(db, invoice, kind="payment", amount=Decimal(amount_cents) / 100,
                       source="razorpay", reference=payment_id,
                       actor="razorpay_webhook", note=f"link:{link.provider_link_id}",
                       currency=link.currency)
            if invoice.source_system == "shopify":
                # Shopify remains read-only. Staff must reconcile its balance with
                # the local ledger before this case can resume contact.
                invoice.requires_human_review = True
                invoice.contact_suppressed = True
            link.status = "paid" if balance_cents(db, invoice) == 0 else "partially_paid"
            event.status = "processed"
            db.add(models.AuditEvent(tenant_id=tenant_id, actor="razorpay_webhook",
                                     action="payment_reconciled", entity_type="invoice",
                                     entity_id=str(invoice.id), details=payment_id))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        # A verified but ambiguous event is retained for staff review without allocating funds.
        db.rollback()
        event = models.ProviderEvent(tenant_id=tenant_id, kind="payment", provider="razorpay",
                                     event_id=event_id, body_sha256=digest,
                                     status="needs_review", error=str(exc)[:500])
        db.add(event)
    event.processed_at = datetime.now(timezone.utc)
    db.commit()
    return event
