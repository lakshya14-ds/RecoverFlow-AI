"""Reports calculated from persisted records."""
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.db_manager import get_db
from app.database import models
from app.auth import Identity, get_identity
from app.services.receivables import balance_cents

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/ar-aging")
def get_ar_aging(db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    buckets = {"current": 0.0, "1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    invoices = db.query(models.Invoice).filter(
        models.Invoice.invoice_type == "AR",
        models.Invoice.tenant_id == identity.tenant_id,
        models.Invoice.status.notin_(("paid", "cancelled")),
    ).all()
    today = date.today()
    for invoice in invoices:
        overdue = (today - invoice.due_date).days
        key = ("current" if overdue <= 0 else "1-30" if overdue <= 30 else
               "31-60" if overdue <= 60 else "61-90" if overdue <= 90 else "90+")
        buckets[key] += max(0, balance_cents(db, invoice)) / 100
    return {**buckets, "total": sum(buckets.values()), "invoice_count": len(invoices)}


@router.get("/summary")
def get_summary(db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    latest = db.query(models.DSOSnapshot).filter(
        models.DSOSnapshot.tenant_id == identity.tenant_id).order_by(
        models.DSOSnapshot.snapshot_date.desc()).first()
    pending = db.query(func.count(models.Reconciliation.id)).filter(
        models.Reconciliation.status == "pending_review",
        models.Reconciliation.tenant_id == identity.tenant_id).scalar()
    alerts = db.query(func.count(models.FraudAlert.id)).filter(
        models.FraudAlert.status == "open",
        models.FraudAlert.tenant_id == identity.tenant_id).scalar()
    reviews = db.query(func.count(models.Invoice.id)).filter(
        models.Invoice.requires_human_review.is_(True),
        models.Invoice.tenant_id == identity.tenant_id).scalar()
    return {"dso_days": latest.dso_days if latest else None,
            "dso_as_of": latest.snapshot_date.isoformat() if latest else None,
            "pending_reconciliations": pending, "open_fraud_alerts": alerts,
            "invoices_needing_review": reviews}
