"""Fixed-cent balances and immutable receivable adjustments."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import models


def cents(value: object) -> int:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Enter a valid monetary amount") from exc
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise ValueError("Amount must be positive with at most two decimal places")
    return int(amount * 100)


def opening_cents(invoice: models.Invoice) -> int:
    if invoice.face_amount_cents is not None:
        return invoice.face_amount_cents
    # Existing installations may contain floating-point amounts from the older schema.
    return int(Decimal(str(invoice.total_amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def balance_cents(db: Session, invoice: models.Invoice) -> int:
    adjustments = db.query(func.coalesce(func.sum(models.ReceivableEntry.amount_cents), 0)).filter(
        models.ReceivableEntry.tenant_id == invoice.tenant_id,
        models.ReceivableEntry.invoice_id == invoice.id,
    ).scalar()
    return opening_cents(invoice) + int(adjustments or 0)


def split_balance(db: Session, invoice: models.Invoice) -> dict:
    """Returns fixed-cent and Decimal breakdown for invoice case."""
    opening = opening_cents(invoice)
    adjustments = db.query(func.coalesce(func.sum(models.ReceivableEntry.amount_cents), 0)).filter(
        models.ReceivableEntry.tenant_id == invoice.tenant_id,
        models.ReceivableEntry.invoice_id == invoice.id,
    ).scalar() or 0
    # Ledger adjustments are negative for payments/credits
    received = -int(adjustments) if adjustments < 0 else 0
    outstanding = max(0, opening + int(adjustments))
    disputed = int(getattr(invoice, "disputed_cents", 0) or 0)
    undisputed = max(0, outstanding - disputed)
    return {
        "invoice_total_cents": opening,
        "received_cents": received,
        "outstanding_cents": outstanding,
        "disputed_cents": disputed,
        "undisputed_cents": undisputed,
        "invoice_total": Decimal(opening) / Decimal(100),
        "received": Decimal(received) / Decimal(100),
        "outstanding": Decimal(outstanding) / Decimal(100),
        "disputed": Decimal(disputed) / Decimal(100),
        "undisputed": Decimal(undisputed) / Decimal(100),
    }


def post_entry(db: Session, invoice: models.Invoice, *, kind: str, amount: object,
               source: str, reference: str, actor: str, note: str = "") -> models.ReceivableEntry:
    if invoice.invoice_type != "AR":
        raise ValueError("Receivable entries require an AR invoice")
    if kind not in ("payment", "credit", "reversal"):
        raise ValueError("Unsupported receivable entry kind")
    amount_cents = cents(amount)
    existing = db.query(models.ReceivableEntry).filter_by(
        tenant_id=invoice.tenant_id, source=source, reference=reference).first()
    signed = amount_cents if kind == "reversal" else -amount_cents
    if existing:
        if (existing.invoice_id, existing.kind, existing.amount_cents) == (invoice.id, kind, signed):
            return existing
        raise ValueError("Reference already belongs to a different receivable entry")
    balance = balance_cents(db, invoice)
    if signed < 0 and amount_cents > balance:
        raise ValueError("Amount exceeds the outstanding balance")
    if signed > 0 and balance + signed > opening_cents(invoice):
        raise ValueError("Reversal exceeds the original receivable")
    entry = models.ReceivableEntry(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, kind=kind,
        amount_cents=signed, currency=invoice.currency or "USD", source=source,
        reference=reference, actor=actor, note=note,
    )
    db.add(entry)
    db.flush()
    remaining = balance + signed
    disputed = int(getattr(invoice, "disputed_cents", 0) or 0)
    if not invoice.requires_human_review:
        if remaining == 0:
            invoice.status = "paid"
        elif disputed > 0 and remaining <= disputed:
            invoice.status = "PARTIALLY_RESOLVED"
        elif remaining < opening_cents(invoice):
            invoice.status = "partially_matched"
        else:
            invoice.status = "pending"
    return entry

