"""Credit/debit notes, invoice lines, and supporting documents."""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity, require_admin
from app.database import models
from app.database.db_manager import get_db
from app.services import documents
from app.services.receivables import cents

router = APIRouter(prefix="/cases", tags=["Documents"])


class NoteCreate(BaseModel):
    note_type: Literal["credit", "debit"]
    number: str = Field(min_length=1, max_length=120)
    note_date: date | None = None
    amount: Decimal = Field(gt=0, decimal_places=2)
    cgst: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    sgst: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    igst: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    reason: str = Field(min_length=5, max_length=1000)


class NoteDecision(BaseModel):
    reason: str = Field(default="", max_length=500)


class LineInput(BaseModel):
    line_no: int | None = Field(default=None, gt=0)
    sku: str = Field(default="", max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    hsn: str | None = Field(default=None, max_length=16)
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str = Field(default="", max_length=20)
    unit_price: Decimal | None = Field(default=None, gt=0, decimal_places=2)
    amount: Decimal = Field(gt=0, decimal_places=2)
    tax_rate_bps: int | None = Field(default=None, ge=0, le=10000)
    cgst: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    sgst: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)
    igst: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2)


def _invoice(db: Session, invoice_id: int, identity: Identity) -> models.Invoice:
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Case not found")
    return invoice


def _note(db: Session, invoice: models.Invoice, note_id: int) -> models.CreditDebitNote:
    note = db.get(models.CreditDebitNote, note_id)
    if not note or note.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


def _note_view(note: models.CreditDebitNote) -> dict:
    return {"id": note.id, "invoice_id": note.invoice_id,
            "note_type": note.note_type, "number": note.number,
            "note_date": note.note_date.isoformat() if note.note_date else None,
            "amount_cents": note.amount_cents, "cgst_cents": note.cgst_cents,
            "sgst_cents": note.sgst_cents, "igst_cents": note.igst_cents,
            "reason": note.reason, "status": note.status,
            "entry_id": note.entry_id, "created_by": note.created_by,
            "decided_by": note.decided_by}


@router.get("/{invoice_id}/line-items")
def list_lines(invoice_id: int, db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    rows = db.query(models.InvoiceLineItem).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
        models.InvoiceLineItem.line_no).all()
    return [{"id": row.id, "line_no": row.line_no, "sku": row.sku,
             "description": row.description, "hsn": row.hsn,
             "quantity": str(row.quantity) if row.quantity is not None else None,
             "unit": row.unit, "unit_price_cents": row.unit_price_cents,
             "amount_cents": row.amount_cents, "tax_rate_bps": row.tax_rate_bps,
             "cgst_cents": row.cgst_cents, "sgst_cents": row.sgst_cents,
             "igst_cents": row.igst_cents, "status": row.status}
            for row in rows]


@router.post("/{invoice_id}/line-items", status_code=201)
def record_line(invoice_id: int, payload: LineInput,
                db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    try:
        row = documents.upsert_invoice_line(
            db, invoice, identity.actor, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"id": row.id, "line_no": row.line_no, "status": row.status}


@router.get("/{invoice_id}/tax-split")
def tax_split(invoice_id: int, db: Session = Depends(get_db),
              identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    return {"cgst_cents": int(invoice.cgst_cents or 0),
            "sgst_cents": int(invoice.sgst_cents or 0),
            "igst_cents": int(invoice.igst_cents or 0),
            "freight_cents": int(invoice.freight_cents or 0),
            "roundoff_cents": int(invoice.roundoff_cents or 0)}


@router.get("/{invoice_id}/supporting-documents")
def list_supporting(invoice_id: int, db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    rows = db.query(models.SupportingDocument).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
        models.SupportingDocument.id).all()
    return [{"id": row.id, "doc_type": row.doc_type, "number": row.number,
             "doc_date": row.doc_date.isoformat() if row.doc_date else None,
             "source_upload_id": row.source_upload_id, "status": row.status,
             "summary": row.summary_json} for row in rows]


@router.get("/{invoice_id}/notes")
def list_notes(invoice_id: int, db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    rows = db.query(models.CreditDebitNote).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
        models.CreditDebitNote.id).all()
    return [_note_view(row) for row in rows]


@router.post("/{invoice_id}/notes", status_code=201)
def create_note(invoice_id: int, payload: NoteCreate,
                db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    try:
        row = documents.create_note(
            db, invoice, payload.note_type, payload.number.strip(),
            payload.amount, payload.reason.strip(), identity.actor,
            note_date=payload.note_date, cgst=payload.cgst,
            sgst=payload.sgst, igst=payload.igst)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409,
                            detail="Note number already used") from exc
    db.commit()
    return _note_view(row)


@router.post("/{invoice_id}/notes/{note_id}/accept")
def accept_note(invoice_id: int, note_id: int, payload: NoteDecision,
                db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    note = _note(db, invoice, note_id)
    try:
        documents.accept_note(db, note, identity.actor, payload.reason.strip())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _note_view(note)


@router.post("/{invoice_id}/notes/{note_id}/post")
def post_note(invoice_id: int, note_id: int,
              db: Session = Depends(get_db),
              identity: Identity = Depends(require_admin)):
    invoice = _invoice(db, invoice_id, identity)
    note = _note(db, invoice, note_id)
    try:
        entry = documents.post_note(db, note, identity.actor)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"entry_id": entry.id, "kind": entry.kind,
            "amount_cents": entry.amount_cents, "note": _note_view(note)}


@router.post("/{invoice_id}/notes/{note_id}/cancel")
def cancel_note(invoice_id: int, note_id: int, payload: NoteDecision,
                db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    note = _note(db, invoice, note_id)
    try:
        documents.cancel_note(db, note, identity.actor,
                              payload.reason.strip())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _note_view(note)


def _stored_doc(db: Session, invoice: models.Invoice, doc_id: str):
    doc = db.get(models.StoredDocument, doc_id)
    if not doc or doc.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{invoice_id}/stored-documents")
def list_stored_documents(invoice_id: int, db: Session = Depends(get_db),
                          identity: Identity = Depends(get_identity)):
    from app.services import document_store
    invoice = _invoice(db, invoice_id, identity)
    docs = db.query(models.StoredDocument).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
        models.StoredDocument.id).all()
    return [document_store.doc_view(doc) for doc in docs
            if doc.deleted_at is None]


@router.get("/{invoice_id}/stored-documents/{doc_id}/file")
def download_stored_document(invoice_id: int, doc_id: str,
                             request: Request,
                             db: Session = Depends(get_db),
                             identity: Identity = Depends(get_identity)):
    from app.services import document_store
    invoice = _invoice(db, invoice_id, identity)
    doc = _stored_doc(db, invoice, doc_id)
    if doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.scan_status == "quarantined":
        raise HTTPException(status_code=403,
                            detail="Document is quarantined; reads are blocked")
    try:
        path = document_store.document_path(doc)
    except document_store.DocumentRejected:
        raise HTTPException(status_code=404, detail="Stored file is missing")
    document_store.log_access(
        db, doc, identity.actor, "download",
        request.client.host if request.client else None)
    db.commit()
    return FileResponse(path, media_type=doc.mime_type,
                        filename=doc.original_filename)


@router.post("/{invoice_id}/stored-documents/{doc_id}/release")
def release_stored_document(invoice_id: int, doc_id: str,
                            db: Session = Depends(get_db),
                            identity: Identity = Depends(require_admin)):
    from app.services import document_store
    invoice = _invoice(db, invoice_id, identity)
    doc = _stored_doc(db, invoice, doc_id)
    try:
        document_store.release_document(db, doc, identity.actor)
    except document_store.DocumentRejected as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return document_store.doc_view(doc)


@router.post("/{invoice_id}/stored-documents/{doc_id}/quarantine")
def quarantine_stored_document(invoice_id: int, doc_id: str,
                               payload: NoteDecision,
                               db: Session = Depends(get_db),
                               identity: Identity = Depends(get_identity)):
    from app.services import document_store
    invoice = _invoice(db, invoice_id, identity)
    doc = _stored_doc(db, invoice, doc_id)
    try:
        document_store.quarantine_document(db, doc, identity.actor,
                                           payload.reason.strip())
    except document_store.DocumentRejected as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return document_store.doc_view(doc)


class HoldDecision(BaseModel):
    hold: bool = True
    reason: str = Field(default="", max_length=500)


@router.post("/{invoice_id}/stored-documents/{doc_id}/hold")
def hold_stored_document(invoice_id: int, doc_id: str, payload: HoldDecision,
                         db: Session = Depends(get_db),
                         identity: Identity = Depends(get_identity)):
    from app.services import document_store
    invoice = _invoice(db, invoice_id, identity)
    doc = _stored_doc(db, invoice, doc_id)
    document_store.set_hold(db, doc, identity.actor, payload.hold,
                            payload.reason.strip())
    db.commit()
    return document_store.doc_view(doc)


@router.delete("/{invoice_id}/stored-documents/{doc_id}")
def delete_stored_document(invoice_id: int, doc_id: str,
                           db: Session = Depends(get_db),
                           identity: Identity = Depends(require_admin)):
    from app.services import document_store
    invoice = _invoice(db, invoice_id, identity)
    doc = _stored_doc(db, invoice, doc_id)
    try:
        document_store.delete_document(db, doc, identity.actor)
    except document_store.DocumentRejected as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return document_store.doc_view(doc)
