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


def split_balance(db: Session, invoice: models.Invoice, *, allow_inconsistent: bool = False) -> dict:
    """Returns fixed-cent and Decimal breakdown for invoice case."""
    opening = opening_cents(invoice)
    adjustments = db.query(func.coalesce(func.sum(models.ReceivableEntry.amount_cents), 0)).filter(
        models.ReceivableEntry.tenant_id == invoice.tenant_id,
        models.ReceivableEntry.invoice_id == invoice.id,
    ).scalar() or 0
    entries = db.query(models.ReceivableEntry).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).all()
    by_id = {entry.id: entry for entry in entries}
    net = {"payment": 0, "credit": 0, "unallocated": 0}
    for entry in entries:
        kind = entry.kind
        if kind == "reversal":
            original = by_id.get(entry.reversal_of_id)
            if original is None and entry.source == "reversal" and entry.reference.isdigit():
                original = by_id.get(int(entry.reference))
            kind = original.kind if original else "unallocated"
        net[kind if kind in net else "unallocated"] -= entry.amount_cents
    outstanding = opening + int(adjustments)
    disputed = int(invoice.disputed_cents or 0)
    inconsistent = not 0 <= disputed <= outstanding <= opening
    if inconsistent and not allow_inconsistent:
        raise ValueError("Ledger/dispute allocation is inconsistent; reconcile before continuing")
    values = {"invoice_total": opening, "received": net["payment"],
              "credits": net["credit"], "unallocated_adjustments": net["unallocated"],
              "outstanding": outstanding, "disputed": disputed,
              "undisputed": 0 if inconsistent else outstanding - disputed}
    return {"reconciliation_error": inconsistent,
            **{key + "_cents": value for key, value in values.items()},
            **{key: Decimal(value) / 100 for key, value in values.items()}}


def post_entry(db: Session, invoice: models.Invoice, *, kind: str, amount: object,
               source: str, reference: str, actor: str, note: str = "",
               allocation: str = "undisputed_first", reversal_of_id: int | None = None,
               currency: str | None = None) -> models.ReceivableEntry:
    if invoice.invoice_type != "AR":
        raise ValueError("Receivable entries require an AR invoice")
    if kind not in ("payment", "credit", "reversal"):
        raise ValueError("Unsupported receivable entry kind")
    expected = (invoice.currency or "INR").upper()
    if currency is not None and str(currency).upper() != expected:
        raise ValueError(f"Currency {currency} does not match invoice currency {expected}")
    amount_cents = cents(amount)
    existing = db.query(models.ReceivableEntry).filter_by(
        tenant_id=invoice.tenant_id, source=source, reference=reference).first()
    signed = amount_cents if kind == "reversal" else -amount_cents
    if existing:
        if (existing.invoice_id, existing.kind, existing.amount_cents) == (invoice.id, kind, signed) and (kind == "reversal" or existing.allocation in (allocation, "legacy")):
            return existing
        raise ValueError("Reference already belongs to a different receivable entry")
    # Lock the parent before computing allocations; SQLite serializes writers.
    db.query(models.Invoice).filter_by(id=invoice.id, tenant_id=invoice.tenant_id).with_for_update().one()
    if allocation not in ("undisputed_first", "disputed_first", "undisputed", "disputed"):
        raise ValueError("Unknown allocation policy")
    balance = balance_cents(db, invoice)
    if signed < 0 and amount_cents > balance:
        raise ValueError("Amount exceeds the outstanding balance")
    if signed > 0 and balance + signed > opening_cents(invoice):
        raise ValueError("Reversal exceeds the original receivable")
    disputed = int(invoice.disputed_cents or 0)
    if not 0 <= disputed <= balance:
        raise ValueError("Existing dispute requires allocation review")
    delta = 0
    if kind == "reversal":
        if reversal_of_id is None and source == "reversal" and reference.isdigit():
            reversal_of_id = int(reference)
        original = db.get(models.ReceivableEntry, reversal_of_id) if reversal_of_id else None
        if (not original or original.tenant_id != invoice.tenant_id or
                original.invoice_id != invoice.id or original.kind not in ("payment", "credit") or
                -original.amount_cents != amount_cents):
            raise ValueError("A reversal must exactly reference an original payment or credit")
        if db.query(models.ReceivableEntry).filter_by(tenant_id=invoice.tenant_id,
                                                    reversal_of_id=original.id).first():
            raise ValueError("Entry was already reversed")
        delta = -int(original.disputed_delta_cents or 0)
        allocation = "reverse_original"
    else:
        undisputed = balance - disputed
        if allocation == "undisputed" and amount_cents > undisputed:
            raise ValueError("Amount exceeds the undisputed allocation")
        if allocation == "disputed" and amount_cents > disputed:
            raise ValueError("Amount exceeds the disputed allocation")
        allocated = (min(amount_cents, disputed) if allocation in ("disputed_first", "disputed")
                     else max(0, amount_cents - undisputed))
        delta = -allocated
    if not 0 <= disputed + delta <= balance + signed:
        raise ValueError("Reversal conflicts with current dispute; staff reconciliation required")
    entry = models.ReceivableEntry(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, kind=kind,
        amount_cents=signed, currency=invoice.currency or "INR", source=source,
        reference=reference, actor=actor, note=note, allocation=allocation,
        disputed_delta_cents=delta, reversal_of_id=reversal_of_id,
    )
    db.add(entry)
    invoice.disputed_cents = disputed + delta
    invoice.dispute_open = invoice.disputed_cents > 0
    db.flush()
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="ledger_allocation", entity_type="receivable_entry", entity_id=str(entry.id),
        details=f"kind={kind}; policy={allocation}; disputed_delta_cents={delta}; reversal_of={reversal_of_id}"))
    from app.services.case_lifecycle import checkpoint
    checkpoint(db, invoice, "ledger_posted", actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, f"ledger:{kind}:{entry.id}", actor)
    from app.services.promises import refresh as refresh_promises
    refresh_promises(db, invoice)
    return entry
