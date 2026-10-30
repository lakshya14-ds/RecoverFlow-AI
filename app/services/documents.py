"""Persisted document records: invoice lines, GST splits, notes, support docs.

Extraction output stays alleged until staff acts. Only note posting creates
ledger entries, through the existing post_entry path.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from app.database import models
from app.services.receivables import cents, post_entry


def nonneg_cents(value):
    if value in (None, ""):
        return 0
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Enter a valid monetary amount") from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
        raise ValueError("Amount must be nonnegative with at most two decimals")
    return int(amount * 100)


def persist_invoice_lines(db, invoice, document, upload_id):
    """Store alleged line items plus the GST/freight split. Runs once."""
    existing = db.query(models.InvoiceLineItem).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).count()
    if existing:
        raise ValueError("Invoice lines are already recorded")
    for position, line in enumerate(document.line_items, start=1):
        quantity = None
        if line.quantity:
            try:
                quantity = Decimal(line.quantity)
            except InvalidOperation as exc:
                raise ValueError("Extracted quantity is invalid") from exc
            if quantity <= 0:
                raise ValueError("Extracted quantity is invalid")
        rate_bps = None
        if line.tax_rate:
            rate_bps = int(Decimal(line.tax_rate) * 100)
        db.add(models.InvoiceLineItem(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id,
            line_no=position, sku=(line.sku or "")[:120],
            description=line.description, hsn=line.hsn or None,
            quantity=quantity, unit=(line.unit or "")[:20],
            unit_price_cents=nonneg_cents(line.unit_price) if line.unit_price else None,
            amount_cents=cents(line.amount), tax_rate_bps=rate_bps,
            cgst_cents=nonneg_cents(line.cgst_amount),
            sgst_cents=nonneg_cents(line.sgst_amount),
            igst_cents=nonneg_cents(line.igst_amount),
            source_upload_id=upload_id, status="alleged"))
    invoice.cgst_cents = nonneg_cents(document.cgst_amount)
    invoice.sgst_cents = nonneg_cents(document.sgst_amount)
    invoice.igst_cents = nonneg_cents(document.igst_amount)
    invoice.freight_cents = nonneg_cents(document.shipping_amount)
    db.flush()


def record_supporting_document(db, invoice, doc_type, upload_id, number=None,
                               doc_date=None, summary=None):
    row = models.SupportingDocument(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, doc_type=doc_type,
        number=(number or "")[:200] or None, doc_date=doc_date,
        source_upload_id=upload_id, status="alleged",
        summary_json=json.dumps(summary or {})[:2000])
    db.add(row)
    db.flush()
    return row


def create_note(db, invoice, note_type, number, amount, reason, actor,
               note_date=None, cgst="0", sgst="0", igst="0",
               source_upload_id=None):
    if note_type not in ("credit", "debit"):
        raise ValueError("Note type must be credit or debit")
    if not number or not str(number).strip():
        raise ValueError("Note number is required")
    if not reason or not str(reason).strip():
        raise ValueError("Note reason is required")
    row = models.CreditDebitNote(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, note_type=note_type,
        number=str(number).strip()[:120], note_date=note_date,
        amount_cents=cents(amount), cgst_cents=nonneg_cents(cgst),
        sgst_cents=nonneg_cents(sgst), igst_cents=nonneg_cents(igst),
        reason=str(reason).strip(), source_upload_id=source_upload_id,
        status="alleged", created_by=actor)
    db.add(row)
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="note_recorded", entity_type="credit_debit_note",
        entity_id=f"{note_type}:{str(number).strip()[:120]}",
        details=f"invoice={invoice.invoice_number}; alleged, not posted"))
    db.flush()
    return row


def accept_note(db, note, actor, reason=""):
    if note.status != "alleged":
        raise ValueError("Only alleged notes can be accepted")
    from app.services import team_ops
    allowed, why = team_ops.sod_allows(db, note.tenant_id, note.created_by,
                                       actor, "note acceptance",
                                       f"note:{note.id}")
    if not allowed:
        raise ValueError(why)
    note.status = "staff_accepted"
    note.decided_by = actor
    note.decided_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=note.tenant_id, actor=actor,
        action="note_accepted", entity_type="credit_debit_note",
        entity_id=str(note.id), details=str(reason or "")[:500]))
    db.flush()
    return note


def post_note(db, note, actor):
    if note.status == "posted" and note.entry_id:
        return db.get(models.ReceivableEntry, note.entry_id)
    if note.status != "staff_accepted":
        raise ValueError("Note must be accepted before posting")
    invoice = db.get(models.Invoice, note.invoice_id)
    kind = "credit" if note.note_type == "credit" else "debit"
    entry = post_entry(
        db, invoice, kind=kind, amount=Decimal(note.amount_cents) / 100,
        source="credit_debit_note",
        reference=f"{note.note_type}:{note.number}", actor=actor,
        note=f"{note.note_type} note {note.number}: {note.reason}"[:500],
        currency=invoice.currency or "INR")
    note.status = "posted"
    note.entry_id = entry.id
    note.decided_by = actor
    note.decided_at = datetime.now(timezone.utc)
    db.flush()
    return entry


def cancel_note(db, note, actor, reason):
    if note.status == "posted":
        raise ValueError("Posted notes need a reversal, not cancellation")
    if note.status == "cancelled":
        raise ValueError("Note is already cancelled")
    note.status = "cancelled"
    note.decided_by = actor
    note.decided_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=note.tenant_id, actor=actor,
        action="note_cancelled", entity_type="credit_debit_note",
        entity_id=str(note.id), details=str(reason or "")[:500]))
    db.flush()
    return note


def upsert_invoice_line(db, invoice, actor, line_no=None, sku="", description="",
                        hsn=None, quantity=None, unit="", unit_price=None,
                        amount=None, tax_rate_bps=None, cgst=0, sgst=0,
                        igst=0):
    """Staff-recorded line (verified). Used when extraction cannot reconcile."""
    if not description or not str(description).strip():
        raise ValueError("Line description is required")
    if amount is None:
        raise ValueError("Line amount is required")
    amount_cents = cents(amount)
    qty = None
    if quantity not in (None, ""):
        try:
            qty = Decimal(str(quantity))
        except InvalidOperation as exc:
            raise ValueError("Line quantity is invalid") from exc
        if qty <= 0:
            raise ValueError("Line quantity is invalid")
    price_cents = None
    if unit_price not in (None, ""):
        price_cents = cents(unit_price)
    if tax_rate_bps is not None and not 0 <= int(tax_rate_bps) <= 10000:
        raise ValueError("Line tax rate is invalid")
    if line_no is None:
        used = [row.line_no for row in db.query(models.InvoiceLineItem).filter_by(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id).all()]
        line_no = max(used, default=0) + 1
    row = db.query(models.InvoiceLineItem).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id,
        line_no=line_no).first()
    values = {"sku": str(sku or "")[:120],
              "description": str(description).strip(),
              "hsn": str(hsn).strip()[:16] if hsn else None, "quantity": qty,
              "unit": str(unit or "")[:20], "unit_price_cents": price_cents,
              "amount_cents": amount_cents,
              "tax_rate_bps": int(tax_rate_bps) if tax_rate_bps is not None else None,
              "cgst_cents": nonneg_cents(cgst), "sgst_cents": nonneg_cents(sgst),
              "igst_cents": nonneg_cents(igst), "status": "verified"}
    if row:
        for key, value in values.items():
            setattr(row, key, value)
    else:
        row = models.InvoiceLineItem(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id,
            line_no=line_no, source_upload_id=None, **values)
        db.add(row)
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="invoice_line_recorded", entity_type="invoice_line_item",
        entity_id=f"{invoice.id}:{line_no}"))
    db.flush()
    return row
