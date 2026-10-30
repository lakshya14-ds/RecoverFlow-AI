from app.services.case_lifecycle import checkpoint
"""Bounded, typed upload intake. Bytes are never served from the web root."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.services.receivables import post_entry
from app.services.release4_orchestrator import prepare_draft

router = APIRouter(prefix="/intake", tags=["Intake"])
MIMES = {
    ".csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
}


def _validate(data: bytes, suffix: str, filename: str) -> None:
    from app.services.document_store import DocumentRejected, validate_content
    try:
        validate_content(data, suffix, filename, portal=False)
    except DocumentRejected as exc:
        if str(exc) == "Empty upload":
            raise HTTPException(status_code=422, detail=str(exc))
        raise HTTPException(status_code=415, detail=str(exc))


def _public(row: models.IntakeUpload) -> dict:
    return {"id": row.id, "filename": row.filename, "mime_type": row.mime_type,
            "size_bytes": row.size_bytes, "status": row.status, "stage": row.stage,
            "stages": json.loads(row.stages_json or '["Uploaded"]'),
            "error": row.error, "attempts": row.attempts,
            "cases_created": row.cases_created,
            "extraction": json.loads(row.extraction_json) if row.extraction_json else None,
            "created_at": row.created_at.isoformat() if row.created_at else None}


@router.post("/uploads", status_code=202)
async def upload(request: Request, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    raw_name = request.headers.get("x-filename", "")
    filename = raw_name.replace("\\", "/").split("/")[-1]
    if not filename or len(filename) > 120 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]*", filename):
        raise HTTPException(status_code=422, detail="Use a short ASCII filename")
    suffix = Path(filename).suffix.lower()
    mime = request.headers.get("content-type", "").split(";")[0].lower()
    if suffix not in MIMES or mime not in MIMES[suffix]:
        raise HTTPException(status_code=415, detail="File extension and MIME type do not match")
    queued = db.query(models.IntakeUpload).filter(
        models.IntakeUpload.tenant_id == identity.tenant_id,
        models.IntakeUpload.status.in_(("queued", "processing"))).count()
    if queued >= 200:
        raise HTTPException(status_code=429, detail="Intake queue is full; retry later")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds upload size cap")
        chunks.append(chunk)
    data = b"".join(chunks)
    _validate(data, suffix, filename)
    storage = Path(settings.INTAKE_STORAGE_PATH)
    storage.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    stored = storage / (job_id + suffix)
    stored.write_bytes(data)
    try:
        row = models.IntakeUpload(id=job_id, tenant_id=identity.tenant_id,
                                  actor=identity.actor, filename=filename,
                                  mime_type=mime, source_path=str(stored),
                                  size_bytes=size, status="queued", stage="Uploaded",
                                  sha256=hashlib.sha256(data).hexdigest())
        db.add(row)
        db.add(models.AuditEvent(tenant_id=identity.tenant_id,
            actor=identity.actor, action="intake_uploaded", entity_type="intake_upload",
            entity_id=job_id, details=f"mime={mime}; bytes={size}"))
        db.commit()
    except Exception:
        db.rollback()
        stored.unlink(missing_ok=True)
        raise
    from app.services.supervisor import request_intake_task
    request_intake_task(db, identity.tenant_id, job_id, identity.actor)
    db.commit()
    return _public(row)


@router.get("/uploads")
def list_uploads(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    rows = db.query(models.IntakeUpload).filter_by(tenant_id=identity.tenant_id).order_by(
        models.IntakeUpload.created_at.desc()).limit(100).all()
    return {"uploads": [_public(row) for row in rows],
            "summary": {"files_processed": sum(row.status in ("ready_for_review", "needs_attention") for row in rows),
                        "cases_created": sum(row.cases_created for row in rows),
                        "items_needing_review": sum(row.status == "needs_attention" for row in rows)}}


@router.get("/uploads/{job_id}")
def get_upload(job_id: str, db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    row = db.get(models.IntakeUpload, job_id)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Upload not found")
    return _public(row)


@router.get("/uploads/{job_id}/file")
def get_upload_file(job_id: str, db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    row = db.get(models.IntakeUpload, job_id)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Upload not found")
    path = Path(row.source_path).resolve()
    storage = Path(settings.INTAKE_STORAGE_PATH).resolve()
    if storage not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Stored file not found")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if row.sha256 is None:
        row.sha256 = digest
    elif row.sha256 != digest:
        raise HTTPException(
            status_code=409,
            detail="Stored file failed its integrity check; quarantined for review")
    db.add(models.AuditEvent(tenant_id=identity.tenant_id,
        actor=identity.actor, action="intake_file_downloaded",
        entity_type="intake_upload", entity_id=row.id))
    db.commit()
    return FileResponse(path, media_type=row.mime_type, filename=row.filename)


@router.post("/uploads/{job_id}/confirm-invoice")
def confirm_invoice(job_id: str, db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    row = db.get(models.IntakeUpload, job_id)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Upload not found")
    if row.cases_created != 1:
        raise HTTPException(status_code=409, detail="Select one invoice to confirm")
    invoice = db.query(models.Invoice).filter_by(tenant_id=identity.tenant_id,
        source_path=row.source_path).first()
    if not invoice:
        raise HTTPException(status_code=409, detail="Uploaded invoice not found")
    invoice.requires_human_review = False
    if invoice.status == "pending_review":
        invoice.status = "pending"
    for evidence in db.query(models.CaseEvidence).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id,
        claim_type="invoice_total").all():
        if evidence.source_reference == f"/api/v1/intake/uploads/{job_id}/file":
            evidence.verified = True
            evidence.trust_state = "verified"
            evidence.decided_by = identity.actor
            evidence.decided_at = datetime.now(timezone.utc)
            evidence.decision_reason = "Staff confirmed the extracted invoice after review"
            evidence.currency = evidence.currency or invoice.currency or "INR"
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="uploaded_invoice_confirmed", entity_type="invoice",
        entity_id=str(invoice.id), details=f"upload_id={job_id}"))
    db.flush()
    try:
        prepare_draft(db, invoice)
    except ValueError:
        pass
    checkpoint(db, invoice, "invoice_confirmed", identity.actor)
    db.commit()
    return {"invoice_id": invoice.id, "confirmed": True}


@router.post("/uploads/{job_id}/confirm-receipt")
def confirm_receipt(job_id: str, db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    row = db.get(models.IntakeUpload, job_id)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Upload not found")
    try:
        if identity.role != "admin":
            raise HTTPException(status_code=403, detail="Admin approval required")
        document = json.loads(row.extraction_json or "{}")
        if document.get("document_type") != "receipt" or not document.get("invoice_reference"):
            raise ValueError("Upload is not a matched receipt")
        candidates = db.query(models.Invoice).filter_by(
            tenant_id=identity.tenant_id,
            invoice_number=document["invoice_reference"]).all()
        if len(candidates) != 1:
            raise ValueError("Receipt has no unique invoice match")
        invoice = candidates[0]
        entry = post_entry(db, invoice, kind="payment", amount=document["total_amount"],
            source="staff_confirmed_upload", reference=job_id, actor=identity.actor,
            note="Staff confirmed uploaded receipt; not an autonomous payment post",
            currency=document.get("currency") or invoice.currency or "INR")
        for evidence in db.query(models.CaseEvidence).filter_by(
            tenant_id=identity.tenant_id, invoice_id=invoice.id,
            claim_type="received_payment",
            source_reference=f"/api/v1/intake/uploads/{job_id}/file").all():
            evidence.verified = True
            evidence.trust_state = "accepted"
            evidence.decided_by = identity.actor
            evidence.decided_at = datetime.now(timezone.utc)
            evidence.decision_reason = f"Staff-confirmed receipt posted as ledger entry {entry.id}"
            evidence.currency = invoice.currency or "INR"
        row.status = "ready_for_review"
        row.stage = "Ready for review"
        row.error = None
        stages = json.loads(row.stages_json or '["Uploaded"]')
        stages.append("Ready for review")
        row.stages_json = json.dumps(stages)
        db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
            action="uploaded_receipt_confirmed", entity_type="invoice",
            entity_id=str(invoice.id), details=f"upload_id={job_id}; entry_id={entry.id}"))
        try:
            prepare_draft(db, invoice)
        except ValueError:
            pass
        db.commit()
        return {"invoice_id": invoice.id, "entry_id": entry.id,
                "status": invoice.status, "source": "staff-confirmed receipt"}
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/uploads/{job_id}/retry")
def retry_upload(job_id: str, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    row = db.get(models.IntakeUpload, job_id)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Upload not found")
    if row.status != "needs_attention" or row.cases_created:
        raise HTTPException(status_code=409, detail="Only failed files without created cases can be retried")
    row.status = "queued"
    row.stage = "Uploaded"
    row.stages_json = '["Uploaded"]'
    row.error = None
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="intake_retried", entity_type="intake_upload", entity_id=job_id))
    db.commit()
    return _public(row)
