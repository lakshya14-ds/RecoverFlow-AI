"""
RecoverFlow - Receivables and Collections
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db_manager import get_db
from app.database import models
from app.auth import Identity, get_identity
from datetime import datetime, timezone
from app.services.receivables import post_entry

router = APIRouter(prefix="/reconciliation", tags=["Reconciliation"])

@router.get("/pending")
def list_pending_reconciliations(db: Session = Depends(get_db), limit: int = 50,
                                 identity: Identity = Depends(get_identity)):
    query = db.query(models.Reconciliation).filter(
        models.Reconciliation.tenant_id == identity.tenant_id,
        models.Reconciliation.status == "pending_review")
    return query.limit(max(1, min(limit, 200))).all()

@router.post("/{reconciliation_id}/approve")
def approve_reconciliation(reconciliation_id: int, db: Session = Depends(get_db),
                           identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin approval required")
    rec = db.query(models.Reconciliation).filter(models.Reconciliation.id == reconciliation_id).first()
    if not rec or rec.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Reconciliation not found")
    if rec.status != "pending_review":
        raise HTTPException(status_code=409, detail="Reconciliation is not pending")
        
    invoice = db.get(models.Invoice, rec.invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=409, detail="Invoice is unavailable for reconciliation")
    used = db.query(models.Reconciliation).filter(
        models.Reconciliation.tenant_id == identity.tenant_id,
        models.Reconciliation.afis_transaction_id == rec.afis_transaction_id,
        models.Reconciliation.status == "approved",
        models.Reconciliation.id != rec.id,
    ).first()
    if used:
        raise HTTPException(status_code=409, detail="Transaction has already been reconciled")
    if invoice.invoice_type == "AR":
        try:
            post_entry(db, invoice, kind="payment", amount=rec.matched_amount,
                       source="afis", reference=str(rec.afis_transaction_id),
                       actor=identity.actor, note=f"Reconciliation {rec.id}")
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    else:
        invoice.status = "paid" if abs(invoice.total_amount - rec.matched_amount) < Decimal("0.01") else "partially_matched"
    invoice.afis_transaction_id = rec.afis_transaction_id
    rec.status = "approved"
    rec.reviewed_by_human = 1
    rec.approved_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="reconciliation_approved", entity_type="reconciliation",
                             entity_id=str(rec.id)))
    db.commit()
    return {"status": "success", "message": "Reconciliation approved"}
