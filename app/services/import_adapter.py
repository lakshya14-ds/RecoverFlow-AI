"""Provider-neutral accounting import: mapping, preview, and validation.

Profiles map foreign rows to one canonical invoice shape. Preview never
writes; confirm writes through the same idempotent writer as the CSV path and
requires staff authentication. Only the generic profile exists: Tally, Busy,
or Zoho support needs a sanitized export from the target business first and
is explicitly NOT claimed here.
"""
import hashlib
import json
import uuid
from datetime import date, datetime, timezone
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
    from app.services import counterparties
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
            counterparties.link_invoice_party(db, existing)
            skipped += 1
            continue
        amount = Decimal(item["amount_cents"]) / 100
        invoice = models.Invoice(
            tenant_id=tenant_id, invoice_number=item["invoice_number"],
            invoice_type="AR", counterparty_name=item["customer_name"],
            counterparty_email=item["customer_email"],
            issue_date=date.fromisoformat(item["issue_date"]),
            due_date=date.fromisoformat(item["due_date"]),
            amount=amount, total_amount=amount,
            face_amount_cents=item["amount_cents"], currency=item["currency"],
            source=source, source_system=source_system,
            source_record_id=item["external_id"], status="pending")
        db.add(invoice)
        db.flush()
        counterparties.link_invoice_party(db, invoice)
        imported += 1
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="receivables_imported", entity_type="import", entity_id=source_system,
        details=f"imported={imported}; skipped={skipped}; profile={profile_name}"))
    db.flush()
    return {"imported": imported, "skipped": skipped}


def _source_hash(rows):
    canonical = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _conflict_with(existing, item):
    if (existing.invoice_number == item["invoice_number"] and
            existing.counterparty_name == item["customer_name"] and
            existing.due_date == date.fromisoformat(item["due_date"]) and
            opening_cents(existing) == item["amount_cents"] and
            existing.currency == item["currency"]):
        return None
    fields = []
    if existing.invoice_number != item["invoice_number"]:
        fields.append("invoice_number")
    if existing.counterparty_name != item["customer_name"]:
        fields.append("customer_name")
    if existing.due_date != date.fromisoformat(item["due_date"]):
        fields.append("due_date")
    if opening_cents(existing) != item["amount_cents"]:
        fields.append("amount")
    if existing.currency != item["currency"]:
        fields.append("currency")
    return ("External ID already imported with different data "
            f"({', '.join(fields)}); staff must decide")


def start_run(db, tenant_id, actor, rows, source_system, profile_name="generic_csv",
              idempotency_key=None, currency_default=None):
    """Preview a batch and persist the run. Same key returns the same run."""
    key = (idempotency_key or "").strip() or f"run-{uuid.uuid4().hex}"
    digest = _source_hash(rows or [])
    existing = db.query(models.ImportRun).filter_by(
        tenant_id=tenant_id, idempotency_key=key).first()
    if existing:
        if existing.source_hash != digest:
            raise ValueError("Idempotency key was reused with a different payload")
        return existing, True
    preview = preview_import(rows, profile_name, currency_default)
    seen = {}
    for item in preview["mapped"]:
        first = seen.setdefault(item["external_id"], item)
        if first is not item and {k: first[k] for k in first if k != "row"} != {
                k: item[k] for k in item if k != "row"}:
            preview["errors"].append(
                f"Row {item['row']}: external ID {item['external_id']} "
                "appears twice with different data")
    run = models.ImportRun(
        tenant_id=tenant_id, source_system=source_system,
        profile=profile_name, idempotency_key=key, source_hash=digest,
        status="previewed" if not preview["errors"] else "invalid",
        row_count=len(preview["mapped"]),
        payload_json=json.dumps(preview["mapped"]),
        report_json=json.dumps({"errors": preview["errors"]}),
        created_by=actor)
    db.add(run)
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="import_run_started", entity_type="import_run",
        entity_id=source_system,
        details=f"profile={profile_name}; rows={run.row_count}; "
                f"errors={len(preview['errors'])}"))
    db.flush()
    return run, False


def confirm_run(db, run_id, actor):
    """Import clean rows, queue conflicts, write the reconciliation report."""
    from app.services import counterparties
    run = db.query(models.ImportRun).filter_by(id=run_id).first()
    if not run:
        raise ValueError("Import run not found")
    if run.status == "invalid":
        raise ValueError("Run has validation errors; fix the source and start a new run")
    if run.status not in ("previewed", "partially_confirmed"):
        raise ValueError("Run is already confirmed")
    items = json.loads(run.payload_json or "[]")
    imported = skipped = conflicted = 0
    totals = {}
    seen_ids = set()

    def _add(bucket, currency, amount_cents):
        totals.setdefault(currency, {"source": 0, "imported": 0, "skipped": 0,
                                     "conflicted": 0, "invalid": 0})
        totals[currency]["source"] += amount_cents
        totals[currency][bucket] += amount_cents

    for item in items:
        currency = item["currency"]
        if item["external_id"] in seen_ids:
            skipped += 1
            _add("skipped", currency, item["amount_cents"])
            continue
        seen_ids.add(item["external_id"])
        existing = db.query(models.Invoice).filter_by(
            tenant_id=run.tenant_id, source_system=run.source_system,
            source_record_id=item["external_id"]).first()
        if existing:
            reason = _conflict_with(existing, item)
            if reason is None:
                counterparties.link_invoice_party(db, existing)
                skipped += 1
                _add("skipped", currency, item["amount_cents"])
                continue
            queued = db.query(models.ImportConflict).filter_by(
                run_id=run.id,
                source_record_id=item["external_id"]).first()
            if not queued:
                db.add(models.ImportConflict(
                    run_id=run.id, tenant_id=run.tenant_id,
                    source_record_id=item["external_id"],
                    row_number=item["row"], reason=reason,
                    source_data_json=json.dumps(item),
                    existing_invoice_id=existing.id))
            conflicted += 1
            _add("conflicted", currency, item["amount_cents"])
            continue
        amount = Decimal(item["amount_cents"]) / 100
        invoice = models.Invoice(
            tenant_id=run.tenant_id, invoice_number=item["invoice_number"],
            invoice_type="AR", counterparty_name=item["customer_name"],
            counterparty_email=item["customer_email"],
            issue_date=date.fromisoformat(item["issue_date"]),
            due_date=date.fromisoformat(item["due_date"]),
            amount=amount, total_amount=amount,
            face_amount_cents=item["amount_cents"], currency=item["currency"],
            source="accounting_import", source_system=run.source_system,
            source_record_id=item["external_id"], status="pending")
        db.add(invoice)
        db.flush()
        counterparties.link_invoice_party(db, invoice)
        imported += 1
        _add("imported", currency, item["amount_cents"])
    run.imported = imported
    run.skipped = skipped
    run.conflicted = conflicted
    run.status = "confirmed" if conflicted == 0 else "partially_confirmed"
    run.cursor_json = json.dumps({
        "last_row": items[-1]["row"] if items else None,
        "external_ids": sorted(seen_ids)})
    run.report_json = json.dumps({
        "totals": totals,
        "imported": imported, "skipped": skipped, "conflicted": conflicted,
        "source_system": run.source_system, "profile": run.profile,
        "source_hash": run.source_hash})
    run.confirmed_by = actor
    run.confirmed_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=run.tenant_id, actor=actor,
        action="import_run_confirmed", entity_type="import_run",
        entity_id=str(run.id),
        details=f"imported={imported}; skipped={skipped}; "
                f"conflicted={conflicted}"))
    db.flush()
    return run


def resolve_conflict(db, conflict_id, actor, resolution):
    """Staff decision on one queued row. The row stays unimported."""
    conflict = db.query(models.ImportConflict).filter_by(id=conflict_id).first()
    if not conflict:
        raise ValueError("Import conflict not found")
    if conflict.status != "open":
        raise ValueError("Import conflict is already resolved")
    decision = (resolution or "").strip() or "keep_existing"
    if decision not in ("keep_existing", "source_will_fix"):
        raise ValueError("Resolution must be keep_existing or source_will_fix")
    conflict.status = "resolved"
    conflict.resolution = decision
    conflict.resolved_by = actor
    conflict.resolved_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=conflict.tenant_id, actor=actor,
        action="import_conflict_resolved", entity_type="import_conflict",
        entity_id=str(conflict.id), details=decision))
    db.flush()
    return conflict


def run_view(db, run):
    conflicts = db.query(models.ImportConflict).filter_by(
        run_id=run.id).order_by(models.ImportConflict.id).all()
    return {
        "id": run.id, "source_system": run.source_system,
        "profile": run.profile, "idempotency_key": run.idempotency_key,
        "source_hash": run.source_hash, "status": run.status,
        "row_count": run.row_count, "imported": run.imported,
        "skipped": run.skipped, "conflicted": run.conflicted,
        "cursor": json.loads(run.cursor_json) if run.cursor_json else None,
        "report": json.loads(run.report_json) if run.report_json else None,
        "created_by": run.created_by, "confirmed_by": run.confirmed_by,
        "conflicts": [{
            "id": item.id, "source_record_id": item.source_record_id,
            "row_number": item.row_number, "reason": item.reason,
            "existing_invoice_id": item.existing_invoice_id,
            "status": item.status, "resolution": item.resolution,
            "resolved_by": item.resolved_by} for item in conflicts],
    }
