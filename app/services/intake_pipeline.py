"""Bounded local intake processor. An uploaded file is always untrusted data."""
import csv
import hashlib
import json
import httpx
from pydantic import ValidationError
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.database import models
from app.database.db_manager import SessionLocal
from app.services.receivables import cents, opening_cents
from app.services.security import detect_prompt_injection
from app.services import vision_extraction
from app.services.gemini_agent import GeminiRateLimitError
from app.services.release4_orchestrator import investigate, prepare_draft

REQUIRED = {"external_id", "invoice_number", "customer_name", "issue_date", "due_date", "amount"}


def _audit(db, job, stage: str, detail: str = ""):
    job.stage = stage
    history = json.loads(job.stages_json or '["Uploaded"]')
    if not history or history[-1] != stage:
        history.append(stage)
    job.stages_json = json.dumps(history)
    db.add(models.AuditEvent(tenant_id=job.tenant_id, actor="intake_agent",
        action="intake_stage", entity_type="intake_upload", entity_id=job.id,
        details=f"stage={stage}; {detail}"[:500]))


def _advance(db, job, invoice):
    try:
        investigate(db, invoice)
        _audit(db, job, "Investigated", f"invoice_id={invoice.id}")
        proposal = prepare_draft(db, invoice)
        _audit(db, job, "Drafted", f"proposal_id={proposal.id}; engine=rules_fallback")
        job.status = "ready_for_review"
        _audit(db, job, "Ready for review", f"proposal_id={proposal.id}")
        job.error = None
    except ValueError as exc:
        job.status = "needs_attention"
        job.error = str(exc)[:500]
        _audit(db, job, "Needs attention", "staff review required")


def _process_csv(db, job):
    with Path(job.source_path).open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("CSV is missing required columns: " + ", ".join(sorted(REQUIRED)))
        rows = list(reader)
    if not rows or len(rows) > 500:
        raise ValueError("CSV must contain 1–500 rows")
    _audit(db, job, "Extracted", f"rows={len(rows)}; confidence=1.0; rules fallback")
    imported = 0
    new_invoices = []
    for row_number, row in enumerate(rows, 2):
        if any(detect_prompt_injection(str(value or ""))[0] for value in row.values()):
            raise ValueError(f"Row {row_number}: adversarial instruction in uploaded data")
        external_id = (row["external_id"] or "").strip()
        number = (row["invoice_number"] or "").strip()
        customer = (row["customer_name"] or "").strip()
        if not external_id or not number or not customer:
            raise ValueError(f"Row {row_number}: missing ID, invoice number, or customer")
        issue = date.fromisoformat(row["issue_date"])
        due = date.fromisoformat(row["due_date"])
        if due < issue:
            raise ValueError(f"Row {row_number}: due date precedes issue date")
        amount_cents = cents(row["amount"])
        currency = (row.get("currency") or "INR").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError(f"Row {row_number}: invalid currency")
        existing = db.query(models.Invoice).filter_by(tenant_id=job.tenant_id,
            source_system="csv", source_record_id=external_id).first()
        if existing:
            if (existing.invoice_number != number or existing.counterparty_name != customer or
                existing.due_date != due or opening_cents(existing) != amount_cents or
                existing.currency != currency):
                raise ValueError(f"Row {row_number}: conflicting external ID")
            continue
        amount = Decimal(amount_cents) / Decimal(100)
        invoice = models.Invoice(tenant_id=job.tenant_id, invoice_number=number,
            invoice_type="AR", counterparty_name=customer,
            issue_date=issue, due_date=due, amount=amount,
            total_amount=amount, face_amount_cents=amount_cents,
            currency=currency, source="upload_csv", source_system="csv",
            source_record_id=external_id, source_path=job.source_path,
            status="pending_review", requires_human_review=True)
        db.add(invoice)
        db.flush()
        db.add(models.CaseEvidence(tenant_id=job.tenant_id, invoice_id=invoice.id,
            claim_type="invoice_total", title="Uploaded CSV invoice amount",
            description="Invoice amount from uploaded CSV row; staff confirmation pending",
            source_type="uploaded_csv", source_reference=f"/api/v1/intake/uploads/{job.id}/file",
            source_snippet=f"Row {row_number}; invoice {number}",
            amount_cents=amount_cents, verified=False))
        new_invoices.append(invoice)
        imported += 1
    job.cases_created = imported
    _audit(db, job, "Matched", "No payment match inferred from invoice CSV")
    if new_invoices:
        failed = []
        for invoice in new_invoices:
            _advance(db, job, invoice)
            if job.status == "needs_attention":
                failed.append(invoice.invoice_number)
        if failed:
            job.status = "needs_attention"
            job.error = "Review invoices: " + ", ".join(failed[:10])
            _audit(db, job, "Needs attention", f"failed_cases={len(failed)}")
    else:
        job.status = "ready_for_review"
        _audit(db, job, "Ready for review", "All CSV rows were already imported")


def _process_vision(db, job):
    validated = vision_extraction.extract(Path(job.source_path).read_bytes(), job.mime_type)
    document = validated["document"]
    job.extraction_json = json.dumps(document.model_dump(), ensure_ascii=False)
    db.flush()  # Investigator queries linked uploads with autoflush disabled.
    _audit(db, job, "Extracted", f"{validated.get('engine', 'Gemini vision')}; server-validated fields and line total")
    if document.document_type == "invoice":
        if not document.issue_date or not document.due_date:
            raise ValueError("Extracted invoice dates are missing")
        issue = date.fromisoformat(document.issue_date)
        due = date.fromisoformat(document.due_date)
        if due < issue:
            raise ValueError("Extracted due date precedes issue date")
        existing = db.query(models.Invoice).filter_by(tenant_id=job.tenant_id,
            invoice_number=document.invoice_number,
            counterparty_name=document.customer_name).all()
        if existing:
            if len(existing) == 1 and existing[0].source_path:
                original = Path(existing[0].source_path)
                if original.is_file() and (hashlib.sha256(original.read_bytes()).digest() ==
                                           hashlib.sha256(Path(job.source_path).read_bytes()).digest()):
                    job.status = "ready_for_review"
                    job.error = None
                    _audit(db, job, "Already imported", f"invoice_id={existing[0].id}; identical file")
                    _audit(db, job, "Ready for review", "Identical invoice file; no new case created")
                    return
            raise ValueError("Invoice already exists; review potential duplicate")
        amount_cents = cents(validated["total"])
        invoice = models.Invoice(tenant_id=job.tenant_id,
            invoice_number=document.invoice_number, invoice_type="AR",
            counterparty_name=document.customer_name, issue_date=issue, due_date=due,
            amount=validated["total"], total_amount=validated["total"],
            face_amount_cents=amount_cents, currency=document.currency,
            source="vision_upload", source_path=job.source_path,
            status="pending_review", requires_human_review=True)
        db.add(invoice)
        db.flush()
        job.cases_created = 1
        db.add(models.CaseEvidence(tenant_id=job.tenant_id, invoice_id=invoice.id,
            claim_type="invoice_total", title="Extracted invoice total",
            description="Document extraction reconciled the total; staff confirmation pending",
            source_type="uploaded_invoice", source_reference=f"/api/v1/intake/uploads/{job.id}/file",
            amount_cents=amount_cents, verified=False))
        _audit(db, job, "Matched", "New invoice; no receipt match inferred")
        _advance(db, job, invoice)
    elif document.document_type in ("receipt", "purchase_order", "message"):
        if not document.invoice_reference:
            raise ValueError("Document has no invoice reference; ambiguous match")
        candidates = db.query(models.Invoice).filter_by(tenant_id=job.tenant_id,
            invoice_number=document.invoice_reference).all()
        if len(candidates) != 1:
            raise ValueError("Document invoice reference has no unique match")
        invoice = candidates[0]
        claim = {"receipt": "received_payment", "purchase_order": "purchase_order",
                 "message": "customer_message"}[document.document_type]
        db.add(models.CaseEvidence(tenant_id=job.tenant_id, invoice_id=invoice.id,
            claim_type=claim, title="Uploaded " + document.document_type,
            description="Machine extracted document; staff confirmation pending",
            source_type="uploaded_" + document.document_type,
            source_reference=f"/api/v1/intake/uploads/{job.id}/file",
            source_snippet=document.text[:250],
            amount_cents=cents(validated["total"]) if validated["total"] else None,
            verified=False))
        _audit(db, job, "Matched", f"invoice_id={invoice.id}; evidence only")
        if document.document_type == "receipt":
            job.status = "needs_attention"
            job.error = "Receipt matched; staff must verify before ledger posting"
            _audit(db, job, "Needs attention", "receipt verification required")
        else:
            _advance(db, job, invoice)


def process_one() -> bool:
    """Claim one DB job; API startup loop calls this with bounded concurrency."""
    with SessionLocal() as db:
        candidate = db.query(models.IntakeUpload.id).filter_by(status="queued").order_by(
            models.IntakeUpload.created_at).first()
        if not candidate:
            return False
        claimed = db.execute(update(models.IntakeUpload).where(
            models.IntakeUpload.id == candidate[0],
            models.IntakeUpload.status == "queued").values(
            status="processing", attempts=models.IntakeUpload.attempts + 1))
        db.commit()
        if not claimed.rowcount:
            return True
        job_id = candidate[0]
    try:
        with SessionLocal() as db:
            job = db.get(models.IntakeUpload, job_id)
            if job.mime_type in ("text/csv", "application/csv", "application/vnd.ms-excel"):
                _process_csv(db, job)
            else:
                _process_vision(db, job)
            db.commit()
    except (ValueError, UnicodeDecodeError, csv.Error, IntegrityError, OSError,
            GeminiRateLimitError, httpx.HTTPError, ValidationError) as exc:
        with SessionLocal() as db:
            job = db.get(models.IntakeUpload, job_id)
            job.status = "needs_attention"
            job.stage = "Needs attention"
            if isinstance(exc, httpx.HTTPStatusError):
                job.error = f"Gemini extraction returned HTTP {exc.response.status_code}; staff review required"
            elif isinstance(exc, httpx.ConnectError):
                job.error = "Gemini connection unavailable; staff review required"
            elif isinstance(exc, (ValueError, GeminiRateLimitError)):
                job.error = str(exc)[:500]
            else:
                job.error = "Document processing failed; staff review required"
            detail = type(exc).__name__
            if isinstance(exc, httpx.HTTPStatusError):
                detail += f"; http_status={exc.response.status_code}"
            _audit(db, job, "Needs attention", detail)
            db.commit()
    except Exception:
        with SessionLocal() as db:
            job = db.get(models.IntakeUpload, job_id)
            job.status = "needs_attention"
            job.stage = "Needs attention"
            job.error = "Document processing failed; staff review required"
            _audit(db, job, "Needs attention", "unexpected processor failure")
            db.commit()
    return True


def recover_interrupted_jobs() -> int:
    """Return jobs interrupted by process shutdown to the durable queue."""
    with SessionLocal() as db:
        rows = db.query(models.IntakeUpload).filter_by(status="processing").all()
        for row in rows:
            row.status = "queued"
            row.stage = "Uploaded"
            row.error = "Worker restarted; processing will retry"
            db.add(models.AuditEvent(tenant_id=row.tenant_id, actor="intake_worker",
                action="intake_requeued_after_restart", entity_type="intake_upload",
                entity_id=row.id))
        db.commit()
        return len(rows)
