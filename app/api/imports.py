"""Provider-neutral retailer receivable import for the assisted release."""
import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services.receivables import cents, opening_cents

router = APIRouter(prefix="/imports", tags=["Imports"])
REQUIRED = {"external_id", "invoice_number", "customer_name", "issue_date", "due_date", "amount"}


@router.post("/receivables/csv")
async def import_receivables(request: Request, db: Session = Depends(get_db),
                             identity: Identity = Depends(get_identity)):
    if request.headers.get("content-type", "").split(";")[0] not in ("text/csv", "application/csv"):
        raise HTTPException(status_code=415, detail="Send a UTF-8 CSV file")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV is too large")
        chunks.append(chunk)
    try:
        reader = csv.DictReader(io.StringIO(b"".join(chunks).decode("utf-8-sig")))
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("CSV must include: " + ", ".join(sorted(REQUIRED)))
        rows = list(reader)
        if not rows or len(rows) > 500:
            raise ValueError("CSV must contain between 1 and 500 records")
        imported = skipped = 0
        for number, row in enumerate(rows, start=2):
            external_id = (row["external_id"] or "").strip()
            invoice_number = (row["invoice_number"] or "").strip()
            customer = (row["customer_name"] or "").strip()
            if not external_id or not invoice_number or not customer:
                raise ValueError(f"Row {number}: external ID, invoice number, and customer are required")
            issue = date.fromisoformat(row["issue_date"])
            due = date.fromisoformat(row["due_date"])
            if due < issue:
                raise ValueError(f"Row {number}: due date precedes issue date")
            amount_cents = cents(row["amount"])
            currency = (row.get("currency") or "USD").strip().upper()
            if len(currency) != 3 or not currency.isalpha():
                raise ValueError(f"Row {number}: currency must be a three-letter code")
            existing = db.query(models.Invoice).filter_by(
                tenant_id=identity.tenant_id, source_system="csv",
                source_record_id=external_id).first()
            if existing:
                if (existing.invoice_number != invoice_number or
                    existing.counterparty_name != customer or existing.due_date != due or
                    opening_cents(existing) != amount_cents or existing.currency != currency):
                    raise ValueError(f"Row {number}: external ID has conflicting invoice data")
                skipped += 1
                continue
            invoice = models.Invoice(
                tenant_id=identity.tenant_id, invoice_number=invoice_number,
                invoice_type="AR", counterparty_name=customer,
                counterparty_email=(row.get("customer_email") or "").strip() or None,
                issue_date=issue, due_date=due, amount=amount_cents / 100,
                total_amount=amount_cents / 100, face_amount_cents=amount_cents,
                currency=currency, source="retail_import", source_system="csv",
                source_record_id=external_id, status="pending",
            )
            db.add(invoice)
            db.flush()
            imported += 1
        db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                                 action="receivables_imported", entity_type="import",
                                 entity_id="csv", details=f"imported={imported}; skipped={skipped}"))
        db.commit()
        return {"imported": imported, "skipped": skipped}
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate external receivable ID") from exc
