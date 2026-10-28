"""Provider-neutral accounting import: mapping, preview, and validation.

Profiles map foreign rows to one canonical invoice shape. Preview never
writes; confirm writes through the same idempotent writer as the CSV path and
requires staff authentication. Only the generic profile exists: Tally, Busy,
or Zoho support needs a sanitized export from the target business first and
is explicitly NOT claimed here.
"""
from datetime import date
from decimal import Decimal, InvalidOperation

from app.database import models
from app.services.receivables import cents, opening_cents

CANONICAL_REQUIRED = ("external_id", "invoice_number", "customer_name",
                      "issue_date", "due_date", "amount")

PROFILES = {
    "generic_csv": {
        "description": "Generic UTF-8 CSV with canonical headers",
        "columns": {name: [name] for name in CANONICAL_REQUIRED},
        "optional_columns": {"customer_email": ["customer_email"],
                             "currency": ["currency"]},
        "currency_default": "INR",
    },
}


def profiles():
    return {name: {"description": profile["description"],
                   "columns": sorted(set(sum(profile["columns"].values(), [])))}
            for name, profile in PROFILES.items()}


def _pick(row, accepted):
    for header in accepted:
        if header in row and str(row[header] or "").strip():
            return str(row[header]).strip()
    return ""


def map_row(row, profile_name="generic_csv", currency_default=None):
    """Map one foreign row to canonical shape (pure, no writes)."""
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown import profile: {profile_name}")
    profile = PROFILES[profile_name]
    canonical = {name: _pick(row, profile["columns"][name]) for name in CANONICAL_REQUIRED}
    for name, accepted in profile["optional_columns"].items():
        canonical[name] = _pick(row, accepted)
    if not canonical["currency"]:
        canonical["currency"] = currency_default or profile["currency_default"]
    return canonical


def validate_row(canonical, number):
    """Validate one canonical row; returns normalized values or raises."""
    for name in ("external_id", "invoice_number", "customer_name"):
        if not canonical[name]:
            raise ValueError(f"Row {number}: external ID, invoice number, and customer are required")
    try:
        issue = date.fromisoformat(canonical["issue_date"])
        due = date.fromisoformat(canonical["due_date"])
    except ValueError:
        raise ValueError(f"Row {number}: issue and due dates must be YYYY-MM-DD")
    if due < issue:
        raise ValueError(f"Row {number}: due date precedes issue date")
    try:
        amount_cents = cents(canonical["amount"])
    except (ValueError, InvalidOperation, TypeError):
        raise ValueError(f"Row {number}: amount must be a positive value with two decimals")
    currency = (canonical["currency"] or "").strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError(f"Row {number}: currency must be a three-letter code")
    return {"external_id": canonical["external_id"],
            "invoice_number": canonical["invoice_number"],
            "customer_name": canonical["customer_name"],
            "customer_email": (canonical["customer_email"] or "").strip() or None,
            "issue_date": issue, "due_date": due, "amount_cents": amount_cents,
            "currency": currency}


def preview_import(rows, profile_name="generic_csv", currency_default=None):
    """Map and validate rows without writing. Cap 500 rows."""
    if profile_name not in PROFILES:
        raise ValueError(f"Unknown import profile: {profile_name}")
    if not rows or len(rows) > 500:
        raise ValueError("Import must contain between 1 and 500 records")
    mapped, errors = [], []
    for number, row in enumerate(rows, start=2):
        try:
            normalized = validate_row(map_row(row, profile_name, currency_default), number)
            mapped.append({**normalized, "row": number,
                           "issue_date": normalized["issue_date"].isoformat(),
                           "due_date": normalized["due_date"].isoformat()})
        except ValueError as exc:
            errors.append(str(exc))
    return {"mapped": mapped, "errors": errors,
            "valid": not errors, "profile": profile_name}


def confirm_import(db, tenant_id, actor, rows, source_system, profile_name="generic_csv",
                   currency_default=None, source="accounting_import"):
    """Write validated rows idempotently; conflicts raise, nothing partial."""
    preview = preview_import(rows, profile_name, currency_default)
    if preview["errors"]:
        raise ValueError(preview["errors"][0])
    imported = skipped = 0
    for item in preview["mapped"]:
        existing = db.query(models.Invoice).filter_by(
            tenant_id=tenant_id, source_system=source_system,
            source_record_id=item["external_id"]).first()
        if existing:
            if (existing.invoice_number != item["invoice_number"] or
                existing.counterparty_name != item["customer_name"] or
                existing.due_date != date.fromisoformat(item["due_date"]) or
                opening_cents(existing) != item["amount_cents"] or
                existing.currency != item["currency"]):
                raise ValueError(f"Row {item['row']}: external ID has conflicting invoice data")
            skipped += 1
            continue
        amount = Decimal(item["amount_cents"]) / 100
        db.add(models.Invoice(
            tenant_id=tenant_id, invoice_number=item["invoice_number"],
            invoice_type="AR", counterparty_name=item["customer_name"],
            counterparty_email=item["customer_email"],
            issue_date=date.fromisoformat(item["issue_date"]),
            due_date=date.fromisoformat(item["due_date"]),
            amount=amount, total_amount=amount,
            face_amount_cents=item["amount_cents"], currency=item["currency"],
            source=source, source_system=source_system,
            source_record_id=item["external_id"], status="pending"))
        db.flush()
        imported += 1
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="receivables_imported", entity_type="import", entity_id=source_system,
        details=f"imported={imported}; skipped={skipped}; profile={profile_name}"))
    db.flush()
    return {"imported": imported, "skipped": skipped}
