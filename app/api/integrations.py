"""Safe connection readiness summary; never returns provider credentials."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import Identity, get_identity
from app.config import settings
from app.services import meta_whatsapp, razorpay, shopify
from app.database import models
from app.database.db_manager import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/integrations", tags=["integrations"])


class ResolveEvent(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


@router.get("/status")
def status(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    local = identity.tenant_id == "local"
    connection = db.query(models.IntegrationConnection).filter_by(
        tenant_id=identity.tenant_id, kind="retail").first()
    return {
        "pilot_country": "IN", "pilot_currency": "INR",
        "shopify": {"configured": local and shopify.configured(),
                    "store": settings.SHOPIFY_SHOP_DOMAIN if local and shopify.configured() else None,
                    "last_sync_at": connection.last_sync_at if connection else None,
                    "backfill_in_progress": bool(connection and connection.cursor)},
        "razorpay": {"configured": local and razorpay.configured(),
                     "mode": settings.RAZORPAY_MODE if local else None,
                     "simulated": bool(local and settings.RAZORPAY_KEY_ID.startswith("rzp_test_mock"))},
        "meta_whatsapp": {"inbound_configured": local and meta_whatsapp.configured(),
                          "outbound_configured": local and meta_whatsapp.outbound_configured()},
    }


@router.get("/events")
def events(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    return db.query(models.ProviderEvent).filter_by(tenant_id=identity.tenant_id).order_by(
        models.ProviderEvent.created_at.desc()).limit(100).all()


@router.post("/events/{event_id}/resolve")
def resolve_event(event_id: int, payload: ResolveEvent, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    event = db.get(models.ProviderEvent, event_id)
    if not event or event.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Provider event not found")
    if event.status != "needs_review":
        raise HTTPException(status_code=409, detail="Only a reviewed exception can be resolved")
    event.status = "resolved"
    event.resolution_note = payload.reason
    event.resolved_by = identity.actor
    event.processed_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="provider_event_resolved", entity_type="provider_event",
                             entity_id=str(event.id), details=payload.reason))
    db.commit()
    return {"status": "resolved", "event_id": event.id}
