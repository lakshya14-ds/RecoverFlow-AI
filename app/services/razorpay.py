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
    if mode == "live" and not settings.RAZORPAY_LIVE_ENABLED:
        raise RuntimeError("Razorpay live mode is disabled; enable it explicitly first")


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


def verify_signature(body: bytes, signature: str, secret: str | None = None) -> bool:
    key = secret if secret is not None else settings.RAZORPAY_WEBHOOK_SECRET
    if not key or not signature:
        return False
    expected = hmac.new(key.encode(), body,
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def process_event(db: Session, tenant_id: str, event_id: str, body: bytes,
                  mode: str = "test") -> models.ProviderEvent:
    """Called only after raw-body signature verification. Never infer payment from a redirect."""
    digest = hashlib.sha256(body).hexdigest()
    mode = mode if mode in ("test", "live") else "test"
    existing = db.query(models.ProviderEvent).filter_by(
        tenant_id=tenant_id, kind="payment", provider="razorpay", event_id=event_id).first()
    if existing:
        if existing.body_sha256 != digest:
            raise ValueError("Webhook event ID was reused with a different payload")
        return existing
    event = models.ProviderEvent(tenant_id=tenant_id, kind="payment", provider="razorpay",
                                 event_id=event_id, body_sha256=digest, status="processing",
                                 mode=mode)
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
            event.resource_id = payment_id
            queue_discrepancy(db, tenant_id, event_id, event_type, payment_id,
                              refund, payment, dispute,
                              entry.invoice_id if entry else None)
            event.status = "needs_review"
            event.error = "Refund or dispute requires a verified ledger review"
        elif event_type in ("payment_link.cancelled", "payment_link.expired"):
            remote_link = data["payload"]["payment_link"]["entity"]
            link = db.query(models.PaymentLink).filter_by(
                tenant_id=tenant_id, provider="razorpay", provider_link_id=remote_link["id"]).first()
            if not link:
                raise ValueError("Payment link is not known to this tenant")
            link.status = "cancelled" if event_type.endswith("cancelled") else "expired"
            event.resource_id = remote_link["id"]
            event.status = "processed"
        elif event_type == "payment.failed":
            failed = ((data.get("payload") or {}).get("payment") or {}).get("entity") or {}
            event.resource_id = failed.get("id")
            event.error = (failed.get("error_description")
                           or "Payment failed; no ledger effect")
            nested = ((data.get("payload") or {}).get("payment_link") or {}).get("entity") or {}
            if nested.get("id"):
                known = db.query(models.PaymentLink).filter_by(
                    tenant_id=tenant_id, provider="razorpay",
                    provider_link_id=nested["id"]).first()
                if known:
                    known.last_error = str(event.error)[:500]
            db.add(models.AuditEvent(tenant_id=tenant_id, actor="razorpay_webhook",
                                     action="payment_failed", entity_type="invoice",
                                     entity_id=str(failed.get("id") or "unknown"),
                                     details=str(event.error)[:500]))
            event.status = "processed"
        elif event_type.startswith("settlement."):
            # Settlement payloads need staff matching against posted entries;
            # they are parked, never auto-applied.
            event.status = "needs_review"
            event.error = "Settlement report needs staff matching (see /payments/settlements)"
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
            event.resource_id = payment_id
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
                                     status="needs_review", error=str(exc)[:500],
                                     mode=mode)
        db.add(event)
    event.processed_at = datetime.now(timezone.utc)
    db.commit()
    return event


def queue_discrepancy(db, tenant_id, event_id, event_type, payment_id,
                      refund, payment, dispute, invoice_id):
    """Park one refund/chargeback for staff. Idempotent per event. No posting."""
    parked = db.query(models.PaymentDiscrepancy).filter_by(
        tenant_id=tenant_id, provider="razorpay", event_id=event_id).first()
    if parked:
        return parked
    kind = ("chargeback" if str(event_type).startswith("dispute.")
            else "refund_unposted")
    entity = dispute if kind == "chargeback" else (refund or payment)
    amount = entity.get("amount")
    row = models.PaymentDiscrepancy(
        tenant_id=tenant_id, provider="razorpay", kind=kind,
        reference=payment_id or "unknown",
        invoice_id=invoice_id,
        expected_cents=amount if type(amount) is int else None,
        event_id=event_id,
        note=f"{event_type}: staff must verify before any reversal")
    db.add(row)
    db.flush()
    return row


def status_for_tenant(db, tenant_id):
    """Honest provider state: not_configured, test, mock, live_disabled, live."""
    from app.services import tenant_config
    mode = tenant_config.get_setting(db, tenant_id, "razorpay_mode", default="test") or "test"
    key_id = tenant_config.get_setting(db, tenant_id, "razorpay_key_id", default="") or ""
    secret_ok = bool(tenant_config.get_secret(db, tenant_id, "razorpay", "webhook_secret"))
    mock = key_id.startswith("rzp_test_mock")
    if not key_id or not secret_ok:
        state = "not_configured"
    elif mode == "live" and not settings.RAZORPAY_LIVE_ENABLED:
        state = "live_disabled"
    elif mode == "live":
        state = "live"
    elif mock:
        state = "mock"
    else:
        state = "test"
    events = db.query(models.ProviderEvent).filter_by(
        tenant_id=tenant_id, kind="payment", provider="razorpay").all()
    counts = {}
    for event in events:
        counts[event.status] = counts.get(event.status, 0) + 1
    open_discs = db.query(models.PaymentDiscrepancy).filter_by(
        tenant_id=tenant_id, provider="razorpay", status="open").count()
    return {"provider": "razorpay", "state": state, "mode": mode,
            "key_id": key_id, "webhook_configured": secret_ok,
            "live_enabled": bool(settings.RAZORPAY_LIVE_ENABLED),
            "event_counts": counts, "open_discrepancies": open_discs,
            "sandbox_note": "Mock and test keys never move real money"}


def match_settlement(db, tenant_id, actor, settlement_ref, lines):
    """Match provider settlement lines against posted entries. No posting.

    Each line: payment_reference, settled_amount (Decimal), fee (Decimal, 0).
    Returns the report; mismatches queue as discrepancies."""
    from decimal import InvalidOperation as DecimalInvalidOperation
    from sqlalchemy.exc import IntegrityError
    report = {"settlement_ref": settlement_ref, "matched": 0, "short": 0,
              "unmatched": 0, "lines": []}
    for number, line in enumerate(lines, start=1):
        reference = str(line.get("payment_reference") or "").strip()
        if not reference:
            raise ValueError(f"Line {number}: payment_reference is required")
        try:
            settled = int(Decimal(str(line.get("settled_amount"))) * 100)
            fee = int(Decimal(str(line.get("fee", "0"))) * 100)
        except (ValueError, TypeError, DecimalInvalidOperation) as exc:
            raise ValueError(f"Line {number}: amounts must be decimal values") from exc
        if settled < 0 or fee < 0:
            raise ValueError(f"Line {number}: amounts must not be negative")
        entry = db.query(models.ReceivableEntry).filter_by(
            tenant_id=tenant_id, source="razorpay", reference=reference,
            kind="payment").first()
        if entry is None:
            status = "unmatched"
            expected = None
            currency = "INR"
        else:
            expected = -entry.amount_cents
            currency = link_currency(db, entry) or "INR"
            status = "matched" if settled == expected else "short"
        row = models.SettlementLine(
            tenant_id=tenant_id, provider="razorpay",
            settlement_ref=settlement_ref, payment_reference=reference,
            expected_cents=expected if expected is not None else 0,
            settled_cents=settled, fee_cents=fee, currency=currency,
            status=status)
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(
                f"Line {number}: settlement line already recorded") from exc
        if status != "matched":
            parked = db.query(models.PaymentDiscrepancy).filter_by(
                tenant_id=tenant_id, provider="razorpay", event_id=None,
                reference=reference, status="open").first()
            if not parked:
                db.add(models.PaymentDiscrepancy(
                    tenant_id=tenant_id, provider="razorpay",
                    kind=f"settlement_{status}", reference=reference,
                    invoice_id=entry.invoice_id if entry else None,
                    expected_cents=expected, actual_cents=settled,
                    currency=currency,
                    note=f"Settlement {settlement_ref} line {number}"))
                db.flush()
        report[status] += 1
        report["lines"].append({"payment_reference": reference,
                                "status": status, "expected_cents": expected,
                                "settled_cents": settled})
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="settlement_matched", entity_type="settlement",
        entity_id=settlement_ref,
        details=f"matched={report['matched']}; short={report['short']}; "
                f"unmatched={report['unmatched']}"))
    db.flush()
    return report


def link_currency(db, entry):
    invoice = db.get(models.Invoice, entry.invoice_id)
    return invoice.currency if invoice else None


def resolve_discrepancy(db, discrepancy_id, actor, action, note=""):
    """Staff resolution. post_reversal writes a linked reversal; else none."""
    disc = db.query(models.PaymentDiscrepancy).filter_by(id=discrepancy_id).first()
    if not disc:
        raise ValueError("Discrepancy not found")
    if disc.status != "open":
        raise ValueError("Discrepancy is already resolved")
    action = (action or "").strip()
    if action not in ("post_reversal", "dismiss"):
        raise ValueError("Action must be post_reversal or dismiss")
    if action == "post_reversal":
        if disc.kind not in ("refund_unposted", "chargeback"):
            raise ValueError("Only refunds and chargebacks post reversals")
        entry = db.query(models.ReceivableEntry).filter_by(
            tenant_id=disc.tenant_id, source="razorpay",
            reference=disc.reference, kind="payment").first()
        if not entry:
            raise ValueError("Original payment is not posted yet; wait for it first")
        invoice = db.get(models.Invoice, entry.invoice_id)
        reversed_entry = post_entry(
            db, invoice, kind="reversal",
            amount=Decimal(-entry.amount_cents) / 100, source="reversal",
            reference=str(entry.id), actor=actor,
            note=(note or f"{disc.kind} {disc.reference}")[:500],
            reversal_of_id=entry.id)
        disc.resolution = f"reversal:{reversed_entry.id}"
    else:
        disc.resolution = (note or "dismissed after review")[:500]
    disc.status = "resolved"
    disc.resolved_by = actor
    disc.resolved_at = datetime.now(timezone.utc)
    if disc.event_id:
        event = db.query(models.ProviderEvent).filter_by(
            tenant_id=disc.tenant_id, kind="payment", provider="razorpay",
            event_id=disc.event_id).first()
        if event and event.status == "needs_review":
            event.status = "resolved"
            event.resolution_note = disc.resolution
            event.resolved_by = actor
    db.add(models.AuditEvent(tenant_id=disc.tenant_id, actor=actor,
        action="discrepancy_resolved", entity_type="payment_discrepancy",
        entity_id=str(disc.id), details=disc.resolution))
    db.flush()
    return disc
