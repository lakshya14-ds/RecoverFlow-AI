"""Invoice upload, durable processing results, and listing."""
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional, Literal
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, model_validator

from app.agents.orchestrator import recoverflow_orchestrator
from app.config import settings
from app.database import models
from app.database.db_manager import get_db, SessionLocal
from app.plugins.pdf_storage import PDFStorage
from app.auth import Identity, get_identity
from app.services.receivables import cents

router = APIRouter(prefix="/invoices", tags=["Invoices"])


class ManualInvoice(BaseModel):
    invoice_number: str = Field(min_length=1)
    invoice_type: Literal["AP", "AR"]
    counterparty_name: str = Field(min_length=1)
    counterparty_email: Optional[str] = None
    issue_date: date
    due_date: date
    total_amount: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.due_date < self.issue_date:
            raise ValueError("Due date must be on or after issue date")
        self.currency = self.currency.upper()
        if not self.currency.isalpha():
            raise ValueError("Currency must be a three-letter code")
        return self


def _set_job(job_id: str, status: str, error: Optional[str] = None) -> None:
    with SessionLocal() as db:
        job = db.get(models.ProcessingJob, job_id)
        if job:
            job.status = status
            job.error = error
            if status not in ("queued", "processing"):
                job.locked_until = None
            if status in ("needs_review", "failed"):
                db.add(models.AuditEvent(
                    tenant_id=job.tenant_id, actor=job.actor,
                    action="invoice_job_" + status, entity_type="processing_job",
                    entity_id=job.id, details=error,
                ))
            db.commit()


def process_invoice_pipeline(job_id: str) -> None:
    """Process an uploaded PDF and persist a queryable outcome."""
    with SessionLocal() as db:
        job = db.get(models.ProcessingJob, job_id)
        if not job:
            return
        if job.invoice_id is not None or job.status in ("completed", "needs_review"):
            return
        file_path = job.source_path
        invoice_type = job.invoice_type or "AP"
    _set_job(job_id, "processing")
    try:
        result = recoverflow_orchestrator.invoke({"invoice_path": file_path,
                                                  "invoice_type": invoice_type,
                                                  "tenant_id": job.tenant_id, "errors": []})
        data = result.get("invoice_data") or {}
        required = ("invoice_number", "counterparty_name", "issue_date", "due_date", "total_amount")
        missing = [key for key in required if data.get(key) is None or data.get(key) == ""]
        if missing:
            errors = "; ".join(result.get("errors", []))
            _set_job(job_id, "needs_review",
                     "Missing extracted fields: " + ", ".join(missing) +
                     ("; " + errors if errors else ""))
            return
        issue_date = date.fromisoformat(data["issue_date"])
        due_date = date.fromisoformat(data["due_date"])
        amount_cents = cents(data["total_amount"])
        amount = amount_cents / 100
        if amount <= 0 or due_date < issue_date:
            _set_job(job_id, "needs_review", "Invalid amount or invoice dates")
            return
        with SessionLocal() as db:
            invoice = models.Invoice(
                tenant_id=job.tenant_id,
                invoice_number=data["invoice_number"], invoice_type=invoice_type,
                counterparty_name=data["counterparty_name"],
                issue_date=issue_date, due_date=due_date,
                amount=amount, total_amount=amount, face_amount_cents=amount_cents,
                source="api_upload", source_path=file_path,
                ocr_raw_text=data.get("raw_text"),
                ocr_confidence=result.get("extracted_confidence", 0.0),
                fraud_score=result.get("fraud_score", 0.0),
                is_duplicate=bool(result.get("is_duplicate")),
                duplicate_of_id=result.get("duplicate_of_id"),
                requires_human_review=(invoice_type == "AR" or bool(result.get("requires_human_review"))),
                status="pending_review" if invoice_type == "AR" or result.get("requires_human_review") else "pending",
            )
            db.add(invoice)
            db.flush()
            if result.get("is_duplicate"):
                db.add(models.FraudAlert(
                    tenant_id=job.tenant_id,
                    invoice_id=invoice.id, alert_type="duplicate", severity="high",
                    fraud_score=1.0, description="Potential duplicate invoice",
                    features_flagged="invoice_number,counterparty_name,total_amount",
                ))
            elif result.get("fraud_score", 0.0) > settings.FRAUD_ALERT_THRESHOLD:
                db.add(models.FraudAlert(
                    tenant_id=job.tenant_id, invoice_id=invoice.id,
                    alert_type="amount_anomaly", severity="medium",
                    fraud_score=result["fraud_score"],
                    description="Invoice amount differs from available history; review required",
                    features_flagged="total_amount",
                ))
            if result.get("matched_afis_id"):
                db.add(models.Reconciliation(
                    tenant_id=job.tenant_id,
                    invoice_id=invoice.id, afis_transaction_id=result["matched_afis_id"],
                    match_type=result.get("match_type") or "amount_date",
                    confidence_score=result.get("reconciliation_confidence", 0.0),
                    matched_amount=result.get("matched_amount") or amount,
                    variance_amount=result.get("variance_amount") or 0.0,
                    status="pending_review",
                ))
            job = db.get(models.ProcessingJob, job_id)
            job.invoice_id = invoice.id
            job.status = "needs_review" if invoice.requires_human_review else "completed"
            job.locked_until = None
            job.error = "; ".join(result.get("errors", [])) or None
            db.add(models.AuditEvent(
                tenant_id=job.tenant_id,
                actor=job.actor, action="invoice_processed", entity_type="invoice",
                entity_id=str(invoice.id), details=job.status,
            ))
            db.commit()
    except Exception as exc:
        logging.exception("Invoice processing failed for job %s", job_id)
        with SessionLocal() as db:
            job = db.get(models.ProcessingJob, job_id)
            if job and (job.attempts or 0) < 3:
                job.status = "queued"
                job.error = str(exc)
                job.locked_until = datetime.now(timezone.utc) + timedelta(seconds=2 ** (job.attempts or 1))
                db.commit()
            else:
                _set_job(job_id, "failed", str(exc))


@router.post("/upload", status_code=202)
async def upload_invoice(request: Request, invoice_type: Literal["AP", "AR"] = "AR",
                         identity: Identity = Depends(get_identity)):
    """Accept a bounded PDF as the raw request body."""
    if request.headers.get("content-type", "").split(";")[0] != "application/pdf":
        raise HTTPException(status_code=415, detail="PDF required")
    temp_dir = Path(settings.INCOMING_STORAGE_PATH)
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"{uuid.uuid4()}.pdf"
    total = 0
    signature = b""
    try:
        with temp_path.open("wb") as output:
            async for chunk in request.stream():
                total += len(chunk)
                if total > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="PDF too large")
                if len(signature) < 5:
                    signature += chunk[:5 - len(signature)]
                output.write(chunk)
        if signature != b"%PDF-":
            raise HTTPException(status_code=415, detail="Invalid PDF signature")
        stored = PDFStorage().store_pdf(str(temp_path))
        if not stored:
            raise HTTPException(status_code=500, detail="Unable to store PDF")
    finally:
        temp_path.unlink(missing_ok=True)
    job_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(models.ProcessingJob(id=job_id, tenant_id=identity.tenant_id,
                                    actor=identity.actor,
                                    source_path=stored, invoice_type=invoice_type,
                                    status="queued"))
        db.add(models.AuditEvent(
            tenant_id=identity.tenant_id, actor=identity.actor, action="invoice_uploaded",
            entity_type="processing_job", entity_id=job_id,
        ))
        db.commit()
    return {"status": "queued", "job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db),
            identity: Identity = Depends(get_identity)):
    job = db.get(models.ProcessingJob, job_id)
    if not job or job.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"id": job.id, "status": job.status, "invoice_id": job.invoice_id,
            "invoice_type": job.invoice_type, "attempts": job.attempts, "error": job.error}


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: str, db: Session = Depends(get_db),
              identity: Identity = Depends(get_identity)):
    job = db.get(models.ProcessingJob, job_id)
    if not job or job.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.invoice_id is not None or job.status not in ("failed", "needs_review"):
        raise HTTPException(status_code=409, detail="Only failed jobs without an invoice can be retried")
    job.status = "queued"
    job.attempts = 0
    job.locked_until = None
    job.error = None
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="invoice_job_retried", entity_type="processing_job",
                             entity_id=job_id))
    db.commit()
    return {"id": job.id, "status": "queued"}


@router.post("/manual", status_code=201)
def create_manual_invoice(payload: ManualInvoice, db: Session = Depends(get_db),
                          identity: Identity = Depends(get_identity)):
    existing = db.query(models.Invoice).filter(
        models.Invoice.tenant_id == identity.tenant_id,
        models.Invoice.invoice_number == payload.invoice_number,
        models.Invoice.counterparty_name == payload.counterparty_name,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Invoice already exists for this counterparty")
    invoice = models.Invoice(
        tenant_id=identity.tenant_id, invoice_number=payload.invoice_number,
        invoice_type=payload.invoice_type, counterparty_name=payload.counterparty_name,
        counterparty_email=payload.counterparty_email,
        issue_date=payload.issue_date, due_date=payload.due_date,
        amount=float(payload.total_amount), total_amount=float(payload.total_amount),
        face_amount_cents=cents(payload.total_amount),
        currency=payload.currency,
        source="manual", status="pending",
    )
    db.add(invoice)
    db.flush()
    db.add(models.AuditEvent(
        tenant_id=identity.tenant_id, actor=identity.actor,
        action="invoice_created", entity_type="invoice", entity_id=str(invoice.id),
    ))
    db.commit()
    return {"id": invoice.id, "status": invoice.status}


@router.put("/{invoice_id}/review")
def confirm_extracted_invoice(invoice_id: int, payload: ManualInvoice,
                              db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not invoice.requires_human_review:
        raise HTTPException(status_code=409, detail="Invoice is not awaiting review")
    if db.query(models.ReceivableEntry).filter_by(invoice_id=invoice_id).first():
        raise HTTPException(status_code=409, detail="Balance entries prevent amount changes")
    invoice.invoice_number = payload.invoice_number
    invoice.invoice_type = payload.invoice_type
    invoice.counterparty_name = payload.counterparty_name
    invoice.counterparty_email = payload.counterparty_email
    invoice.issue_date = payload.issue_date
    invoice.due_date = payload.due_date
    invoice.total_amount = float(payload.total_amount)
    invoice.amount = float(payload.total_amount)
    invoice.face_amount_cents = cents(payload.total_amount)
    invoice.currency = payload.currency
    invoice.requires_human_review = False
    invoice.status = "pending"
    job = db.query(models.ProcessingJob).filter_by(invoice_id=invoice_id).first()
    if job:
        job.status = "completed"
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="invoice_reviewed", entity_type="invoice",
                             entity_id=str(invoice_id)))
    db.commit()
    return {"id": invoice.id, "status": invoice.status}


@router.get("/")
def list_invoices(status: Optional[str] = None, type: Optional[str] = None,
                  db: Session = Depends(get_db), limit: int = 50,
                  identity: Identity = Depends(get_identity)):
    query = db.query(models.Invoice).filter(models.Invoice.tenant_id == identity.tenant_id)
    if status:
        query = query.filter(models.Invoice.status == status)
    if type:
        query = query.filter(models.Invoice.invoice_type == type)
    return query.order_by(models.Invoice.created_at.desc()).limit(max(1, min(limit, 200))).all()
