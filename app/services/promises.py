"""Nonfinancial promise tracking. A promise is a record about future cash,
never cash itself: it cannot change received amounts, balances, or stages.
"""
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.database import models

WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}


def _parse_amount(text):
    match = re.search(r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)"
                      r"|([\d,]+(?:\.\d{1,2})?)\s*(?:rs\.?|inr|rupees)", text, re.I)
    if not match:
        return None
    raw = (match.group(1) or match.group(2) or "").replace(",", "")
    return int(Decimal(raw) * 100)


def _parse_date(text, today):
    lowered = text.casefold()
    if "tomorrow" in lowered:
        return today + timedelta(days=1)
    if "next week" in lowered:
        return today + timedelta(days=7)
    iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text or "")
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass
    for name, weekday in WEEKDAYS.items():
        if re.search(rf"\b{name}\b", lowered):
            delta = (weekday - today.weekday()) % 7 or 7
            return today + timedelta(days=delta)
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text)
    if match:
        day, month = int(match.group(1)), int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            parsed = date(year, month, day)
        except ValueError:
            return None
        if parsed < today:
            try:
                parsed = date(year + 1, month, day)
            except ValueError:
                return None
        return parsed
    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", lowered)
    if match:
        day = int(match.group(1))
        month, year = today.month, today.year
        while True:
            try:
                parsed = date(year, month, day)
            except ValueError:
                month += 1
                if month > 12:
                    month, year = 1, year + 1
                continue
            if parsed >= today:
                return parsed
            month += 1
            if month > 12:
                month, year = 1, year + 1
    return None


def extract_promise(text, today=None):
    """Deterministic amount/date extraction with a stated confidence."""
    today = today or date.today()
    amount = _parse_amount(text or "")
    promised = _parse_date(text or "", today)
    if amount is None and promised is None:
        raise ValueError("No promised amount or date found in the message")
    if amount is not None and promised is not None:
        confidence = 0.9
    elif amount is not None:
        confidence = 0.6
    else:
        confidence = 0.4
    return {"amount_cents": amount or 0, "promised_date": promised,
            "confidence": confidence}


def create_from_message(db, invoice, message, actor="promise_agent"):
    """Record an alleged promise from one customer message (idempotent)."""
    if message.invoice_id != invoice.id or message.tenant_id != invoice.tenant_id:
        raise ValueError("Message does not belong to this case")
    existing = db.query(models.PromiseToPay).filter_by(
        tenant_id=invoice.tenant_id, source_message_id=message.id).first()
    if existing:
        return existing, True
    extracted = extract_promise(message.body or "")
    row = models.PromiseToPay(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id,
        promised_cents=extracted["amount_cents"], promised_date=extracted["promised_date"],
        source_message_id=message.id, source_text=(message.body or "")[:2000],
        extraction_confidence=extracted["confidence"], status="alleged")
    db.add(row)
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="promise_recorded", entity_type="invoice", entity_id=str(invoice.id),
        details=f"cents={row.promised_cents}; confidence={row.extraction_confidence}"))
    db.flush()
    return row, False


def confirm(db, promise, actor):
    if promise.status != "alleged":
        raise ValueError("Only alleged promises can be confirmed")
    promise.status = "confirmed"
    promise.confirmed_by = actor
    promise.confirmed_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=promise.tenant_id, actor=actor,
        action="promise_confirmed", entity_type="promise_to_pay",
        entity_id=str(promise.id), details=f"cents={promise.promised_cents}"))
    db.flush()
    return promise


def remind(db, promise, actor):
    if promise.status not in ("alleged", "confirmed"):
        raise ValueError("Only open promises can be reminded")
    promise.reminders_sent += 1
    promise.last_reminder_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=promise.tenant_id, actor=actor,
        action="promise_reminded", entity_type="promise_to_pay",
        entity_id=str(promise.id), details=f"reminders={promise.reminders_sent}"))
    db.flush()
    return promise


def cancel(db, promise, actor, reason=""):
    if promise.status not in ("alleged", "confirmed"):
        raise ValueError("Only open promises can be cancelled")
    promise.status = "cancelled"
    db.add(models.AuditEvent(tenant_id=promise.tenant_id, actor=actor,
        action="promise_cancelled", entity_type="promise_to_pay",
        entity_id=str(promise.id), details=reason[:500]))
    db.flush()
    return promise


def _covered_cents(db, promise):
    """Net verified payments posted after the promise was recorded."""
    entries = db.query(models.ReceivableEntry).filter(
        models.ReceivableEntry.tenant_id == promise.tenant_id,
        models.ReceivableEntry.invoice_id == promise.invoice_id,
        models.ReceivableEntry.kind == "payment",
        models.ReceivableEntry.created_at >= promise.created_at).all()
    total = 0
    for entry in entries:
        restored = sum(rev.amount_cents for rev in db.query(models.ReceivableEntry).filter_by(
            tenant_id=promise.tenant_id, reversal_of_id=entry.id).all())
        total += -entry.amount_cents - restored
    return total


def refresh(db, invoice):
    """Reassess open promises against verified payments (idempotent)."""
    changed = []
    parties = db.query(models.PromiseToPay).filter(
        models.PromiseToPay.tenant_id == invoice.tenant_id,
        models.PromiseToPay.invoice_id == invoice.id,
        models.PromiseToPay.status.in_(("alleged", "confirmed"))).all()
    for promise in parties:
        if promise.promised_cents and _covered_cents(db, promise) >= promise.promised_cents:
            promise.status = "kept"
            changed.append((promise, "kept"))
        elif promise.promised_date and promise.promised_date < date.today():
            promise.status = "broken"
            promise.broken_at = datetime.now(timezone.utc)
            changed.append((promise, "broken"))
    for promise, outcome in changed:
        db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor="promise_agent",
            action=f"promise_{outcome}", entity_type="promise_to_pay",
            entity_id=str(promise.id), details=f"cents={promise.promised_cents}"))
    db.flush()
    return changed
