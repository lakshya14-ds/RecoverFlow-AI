"""Single-invoice customer portal: tokens, rate limits, safe summaries.

A token grants exactly one invoice's fixed capability set: view the safe
summary, file a dispute, attach evidence, submit a payment reference. No
portal action posts money, approves anything, or sees staff internals.
"""
import secrets
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.database import models
from app.services.auth_security import hash_api_key
from app.services.receivables import split_balance


class PortalError(ValueError):
    """reason is one of: invalid, expired, revoked, throttled."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _naive_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive(value):
    return value.replace(tzinfo=None) if getattr(value, "tzinfo", None) else value


def issue_token(db, invoice, actor, hours=None):
    """Create a token. Returns (row, raw_token); the raw value shows once."""
    raw = "rfp_" + secrets.token_urlsafe(32)
    row = models.PortalToken(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id,
        token_hash=hash_api_key(raw), prefix=raw[:12], created_by=actor,
        created_at=_naive_utc(),
        expires_at=_naive_utc() + timedelta(
            hours=hours if hours is not None
            else settings.PORTAL_TOKEN_EXPIRE_HOURS))
    db.add(row)
    db.add(models.AuditEvent(
        tenant_id=invoice.tenant_id, actor=actor, action="portal_token_issued",
        entity_type="portal_token", entity_id=row.prefix,
        details=f"invoice={invoice.invoice_number}"))
    db.flush()
    return row, raw


def revoke_token(db, token, actor, reason=""):
    token.revoked_at = _naive_utc()
    token.revoked_by = actor
    token.revoke_reason = (reason or "")[:500]
    db.add(models.AuditEvent(
        tenant_id=token.tenant_id, actor=actor, action="portal_token_revoked",
        entity_type="portal_token", entity_id=token.prefix,
        details=(reason or "")[:500]))
    db.flush()
    return token


def _prune_attempts(db, now):
    db.query(models.PortalAttempt).filter(
        models.PortalAttempt.created_at
        < now - timedelta(hours=24)).delete()


def verify_token(db, raw_token, ip):
    """Authenticate one portal request. Raises PortalError; logs attempts."""
    now = _naive_utc()
    since = now - timedelta(minutes=settings.PORTAL_WINDOW_MINUTES)
    _prune_attempts(db, now)
    ip_guesses = db.query(models.PortalAttempt).filter(
        models.PortalAttempt.ip == (ip or "unknown"),
        models.PortalAttempt.success.is_(False),
        models.PortalAttempt.created_at >= since).count()
    if ip_guesses >= settings.PORTAL_GUESS_LIMIT:
        raise PortalError("throttled")
    row = None
    if raw_token:
        row = db.query(models.PortalToken).filter_by(
            token_hash=hash_api_key(raw_token)).first()
    if row is None:
        db.add(models.PortalAttempt(
            token_id=None, ip=ip or "unknown", success=False,
            created_at=now))
        db.commit()
        raise PortalError("invalid")
    if row.revoked_at is not None:
        raise PortalError("revoked")
    if _as_naive(row.expires_at) < now:
        raise PortalError("expired")
    token_hits = db.query(models.PortalAttempt).filter(
        models.PortalAttempt.token_id == row.id,
        models.PortalAttempt.success.is_(True),
        models.PortalAttempt.created_at >= since).count()
    ip_hits = db.query(models.PortalAttempt).filter(
        models.PortalAttempt.ip == (ip or "unknown"),
        models.PortalAttempt.success.is_(True),
        models.PortalAttempt.created_at >= since).count()
    if (token_hits >= settings.PORTAL_TOKEN_LIMIT
            or ip_hits >= settings.PORTAL_IP_LIMIT):
        raise PortalError("throttled")
    db.add(models.PortalAttempt(
        token_id=row.id, ip=ip or "unknown", success=True, created_at=now))
    row.last_used_at = now
    row.use_count = (row.use_count or 0) + 1
    db.commit()
    return row


def customer_status(invoice, split):
    if (invoice.status or "").lower() == "paid":
        return "paid"
    if (invoice.status or "").lower() in ("adjusted", "written_off"):
        return "adjusted"
    if invoice.dispute_open or (invoice.status or "").lower() == "disputed":
        return "disputed"
    if split["received_cents"] > 0 and split["outstanding_cents"] > 0:
        return "partially_paid"
    if split["outstanding_cents"] <= 0:
        return "paid"
    return "open"


def safe_summary(db, token, invoice):
    """Only the customer's own bill + their own submissions. No staff data."""
    split = split_balance(db, invoice)
    submissions = [{
        "id": message.id,
        "category": message.category,
        "created_at": message.created_at.isoformat()
        if message.created_at else None,
        "review": ("under_review" if invoice.requires_human_review
                   or invoice.investigation_hold else "recorded"),
    } for message in db.query(models.CustomerMessage).filter_by(
        tenant_id=token.tenant_id, invoice_id=invoice.id,
        source="portal").order_by(models.CustomerMessage.id).all()]
    return {
        "invoice_number": invoice.invoice_number,
        "counterparty_name": invoice.counterparty_name,
        "issue_date": invoice.issue_date.isoformat()
        if invoice.issue_date else None,
        "due_date": invoice.due_date.isoformat()
        if invoice.due_date else None,
        "currency": invoice.currency or "INR",
        "total": str(split["invoice_total"]),
        "received": str(split["received"]),
        "outstanding": str(split["outstanding"]),
        "disputed": str(split["disputed"]),
        "undisputed": str(split["undisputed"]),
        "status": customer_status(invoice, split),
        "access_expires_at": _as_naive(token.expires_at).isoformat(),
        "submissions": submissions,
    }
