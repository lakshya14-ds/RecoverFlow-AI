"""
RecoverFlow - Receivables and Collections
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db_manager import get_db
from app.database import models
from app.auth import Identity, get_identity

router = APIRouter(prefix="/fraud", tags=["Fraud"])

@router.get("/alerts")
def list_fraud_alerts(status: str = "open", db: Session = Depends(get_db), limit: int = 50,
                      identity: Identity = Depends(get_identity)):
    query = db.query(models.FraudAlert).filter(models.FraudAlert.tenant_id == identity.tenant_id)
    if status:
        query = query.filter(models.FraudAlert.status == status)
    return query.limit(max(1, min(limit, 200))).all()

@router.post("/{alert_id}/resolve")
def resolve_fraud_alert(alert_id: int, resolution: str, db: Session = Depends(get_db),
                        identity: Identity = Depends(get_identity)):
    alert = db.query(models.FraudAlert).filter(models.FraudAlert.id == alert_id).first()
    if not alert or alert.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    alert.status = "resolved"
    alert.resolution_notes = resolution
    
    # An alert resolution does not clear independent invoice review reasons.
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="fraud_alert_resolved", entity_type="fraud_alert",
                             entity_id=str(alert.id), details=resolution))
    db.commit()
    return {"status": "success", "message": "Alert resolved"}
