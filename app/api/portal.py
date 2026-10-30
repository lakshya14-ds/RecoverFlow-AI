"""Customer portal: staff-issued single-invoice access, safe summary, disputes,
evidence uploads, and payment-reference claims. No portal action moves money.
"""
import re
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.services import document_store, portal
from app.services.customer_messages import record_customer_message
from app.services.document_store import DocumentRejected

router = APIRouter(tags=["Portal"])


class IssueToken(BaseModel):
    hours: Optional[int] = Field(default=None, gt=0, le=24 * 30)


class RevokeToken(BaseModel):
    reason: str = ""


class PortalDispute(BaseModel):
    body: str = Field(min_length=3, max_length=4000)
    amount: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)


class PortalPaymentReference(BaseModel):
    reference: str = Field(min_length=3, max_length=120)
    amount: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    paid_date: Optional[date] = None
    note: str = Field(default="", max_length=1000)


def _invoice(db, invoice_id, tenant_id):
    invoice = db.get(models.Invoice, invoice_id)
    if (not invoice or invoice.tenant_id != tenant_id
            or invoice.invoice_type != "AR"):
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _token_public(row):
    return {"id": row.id, "prefix": row.prefix, "invoice_id": row.invoice_id,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
            "revoked_by": row.revoked_by, "revoke_reason": row.revoke_reason,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            "use_count": row.use_count or 0}


def _portal_auth(request: Request, db: Session):
    raw = (request.headers.get("X-PORTAL-TOKEN")
           or request.query_params.get("token"))
    ip = request.client.host if request.client else "unknown"
    try:
        token = portal.verify_token(db, raw, ip)
    except portal.PortalError as exc:
        if exc.reason == "throttled":
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Too many portal requests; try again later")
        if exc.reason == "expired":
            raise HTTPException(status_code=status.HTTP_410_GONE,
                                detail="This portal link has expired; ask the business for a new one")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This portal link is invalid or revoked")
    invoice = _invoice(db, token.invoice_id, token.tenant_id)
    return token, invoice


@router.post("/cases/{invoice_id}/portal-tokens", status_code=201)
def issue_portal_token(invoice_id: int, payload: IssueToken,
                       db: Session = Depends(get_db),
                       identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin approval required")
    invoice = _invoice(db, invoice_id, identity.tenant_id)
    row, raw = portal.issue_token(db, invoice, identity.actor, hours=payload.hours)
    db.commit()
    public = _token_public(row)
    public["token"] = raw
    return public


@router.get("/cases/{invoice_id}/portal-tokens")
def list_portal_tokens(invoice_id: int, db: Session = Depends(get_db),
                       identity: Identity = Depends(get_identity)):
    _invoice(db, invoice_id, identity.tenant_id)
    rows = db.query(models.PortalToken).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(
        models.PortalToken.id).all()
    return [_token_public(row) for row in rows]


@router.post("/cases/{invoice_id}/portal-tokens/{token_id}/revoke")
def revoke_portal_token(invoice_id: int, token_id: int, payload: RevokeToken,
                        db: Session = Depends(get_db),
                        identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin approval required")
    _invoice(db, invoice_id, identity.tenant_id)
    row = db.get(models.PortalToken, token_id)
    if (not row or row.tenant_id != identity.tenant_id
            or row.invoice_id != invoice_id):
        raise HTTPException(status_code=404, detail="Portal token not found")
    if row.revoked_at is not None:
        raise HTTPException(status_code=409, detail="Portal token is already revoked")
    portal.revoke_token(db, row, identity.actor, payload.reason)
    db.commit()
    return _token_public(row)


@router.get("/portal/case")
def portal_case(request: Request, db: Session = Depends(get_db)):
    token, invoice = _portal_auth(request, db)
    return portal.safe_summary(db, token, invoice)


@router.post("/portal/disputes", status_code=201)
def portal_dispute(payload: PortalDispute, request: Request,
                   db: Session = Depends(get_db)):
    token, invoice = _portal_auth(request, db)
    result = record_customer_message(
        db, token.tenant_id, "customer_portal", invoice,
        "dispute", payload.body, source="portal")
    invoice.requires_human_review = True
    if payload.amount is not None:
        db.add(models.CaseEvidence(
            tenant_id=token.tenant_id, invoice_id=invoice.id,
            claim_type="dispute_item",
            title="Customer portal dispute",
            description=(f"Customer disputes {payload.amount} "
                         f"{invoice.currency or 'INR'} via the portal. "
                         "Allegation only; staff must verify before any adjustment."),
            source_type="portal_dispute",
            source_reference=f"PORTAL-MSG-{result['message_id']}",
            source_snippet=payload.body[:500],
            amount_cents=int(payload.amount * 100),
            verified=False, trust_state="alleged",
            currency=invoice.currency or "INR"))
    db.add(models.AuditEvent(
        tenant_id=token.tenant_id, actor="customer_portal",
        action="portal_dispute_filed", entity_type="invoice",
        entity_id=str(invoice.id),
        details=f"token={token.prefix}"))
    db.commit()
    return {"message_id": result["message_id"],
            "status": "received; staff will review",
            "is_injection": result["is_injection"]}


@router.post("/portal/payment-references", status_code=201)
def portal_payment_reference(payload: PortalPaymentReference, request: Request,
                             db: Session = Depends(get_db)):
    token, invoice = _portal_auth(request, db)
    parts = [f"Payment reference {payload.reference.strip()}"]
    if payload.amount is not None:
        parts.append(f"amount {payload.amount} {invoice.currency or 'INR'}")
    if payload.paid_date is not None:
        parts.append(f"paid on {payload.paid_date.isoformat()}")
    if payload.note.strip():
        parts.append(payload.note.strip())
    body = ". ".join(parts) + "."
    result = record_customer_message(
        db, token.tenant_id, "customer_portal", invoice,
        "paid_claim", body, source="portal")
    # A submitted reference is a claim until independently verified.
    invoice.requires_human_review = True
    db.add(models.AuditEvent(
        tenant_id=token.tenant_id, actor="customer_portal",
        action="portal_payment_reference_filed", entity_type="invoice",
        entity_id=str(invoice.id),
        details=f"token={token.prefix}"))
    db.commit()
    return {"message_id": result["message_id"],
            "status": "received as an unverified claim; staff will verify",
            "is_injection": result["is_injection"]}


@router.post("/portal/evidence", status_code=201)
async def portal_evidence(request: Request, db: Session = Depends(get_db)):
    token, invoice = _portal_auth(request, db)
    raw_name = request.headers.get("x-filename", "").replace(
        "\\", "/").split("/")[-1]
    if (not raw_name or len(raw_name) > 120
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._ -]*", raw_name)):
        raise HTTPException(status_code=422, detail="Use a short ASCII filename")
    note = request.headers.get("x-note", "")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds upload size cap")
        chunks.append(chunk)
    data = b"".join(chunks)
    try:
        doc = document_store.store_document(
            db, tenant_id=token.tenant_id, invoice_id=invoice.id,
            origin="portal_evidence", filename=raw_name, data=data,
            uploaded_by=f"portal:{token.prefix}",
            portal_token_id=token.id, portal=True)
    except DocumentRejected as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    db.add(models.CaseEvidence(
        tenant_id=token.tenant_id, invoice_id=invoice.id,
        claim_type="customer_document",
        title=f"Portal evidence: {raw_name}",
        description=("Customer-uploaded file awaiting staff release. "
                     "Untrusted evidence; never agent instructions."),
        source_type="portal_upload",
        source_reference=f"DOC-{doc.id}",
        source_snippet=(note.strip()[:500] if note.strip() else raw_name),
        verified=False, trust_state="alleged",
        currency=invoice.currency or "INR"))
    invoice.requires_human_review = True
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "portal_evidence", "customer_portal")
    db.add(models.AuditEvent(
        tenant_id=token.tenant_id, actor="customer_portal",
        action="portal_evidence_uploaded", entity_type="stored_document",
        entity_id=doc.id, details=f"token={token.prefix}; bytes={doc.size_bytes}"))
    db.commit()
    return {"doc_id": doc.id, "filename": raw_name,
            "size_bytes": doc.size_bytes, "sha256": doc.sha256,
            "status": "received; staff will review before use"}


@router.get("/portal/evidence")
def portal_evidence_list(request: Request, db: Session = Depends(get_db)):
    token, invoice = _portal_auth(request, db)
    docs = db.query(models.StoredDocument).filter_by(
        tenant_id=token.tenant_id, invoice_id=invoice.id,
        portal_token_id=token.id).order_by(models.StoredDocument.id).all()
    return [{"doc_id": doc.id, "filename": doc.original_filename,
             "size_bytes": doc.size_bytes, "sha256": doc.sha256,
             "scan_status": doc.scan_status,
             "uploaded_at": doc.uploaded_at.isoformat()
             if doc.uploaded_at else None}
            for doc in docs if doc.deleted_at is None]


@router.get("/portal/evidence/{doc_id}/file")
def portal_evidence_file(doc_id: str, request: Request,
                         db: Session = Depends(get_db)):
    token, invoice = _portal_auth(request, db)
    doc = document_store.readable_document(db, doc_id, token.tenant_id)
    if (not doc or doc.invoice_id != invoice.id
            or doc.portal_token_id != token.id or doc.deleted_at is not None):
        raise HTTPException(status_code=404, detail="Evidence not found")
    try:
        path = document_store.document_path(doc)
    except DocumentRejected:
        raise HTTPException(status_code=404, detail="Evidence not found")
    document_store.log_access(
        db, doc, f"portal:{token.prefix}", "download",
        request.client.host if request.client else None)
    db.commit()
    return FileResponse(path, media_type=doc.mime_type,
                        filename=doc.original_filename)
