"""Safe connection readiness summary; never returns provider credentials."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import Identity, get_identity, require_admin
from app.config import settings
from app.services import meta_whatsapp, razorpay, shopify, tenant_config
from app.database import models
from app.database.db_manager import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/integrations", tags=["integrations"])


class ResolveEvent(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class SecretInput(BaseModel):
    provider: str = Field(pattern="^(razorpay|meta_whatsapp|shopify)$")
    name: str = Field(min_length=1, max_length=60)
    secret_ref: str = Field(min_length=5, max_length=300)
    label: str = Field(default="", max_length=120)


class SettingInput(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=2000)


@router.get("/status")
def status(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    tenant = identity.tenant_id
    connection = db.query(models.IntegrationConnection).filter_by(
        tenant_id=tenant, kind="retail").first()
    shop_secret = tenant_config.get_secret(db, tenant, "shopify", "webhook_secret")
    shop_domain = tenant_config.get_setting(db, tenant, "shopify_shop_domain", default="")
    shop_ready = bool(shop_secret) and shop_domain.endswith(".myshopify.com") \
        and shop_domain.count(".") == 2
    mode_row = db.query(models.TenantSetting).filter_by(
        tenant_id=tenant, key="razorpay_mode").first()
    mode = mode_row.value if mode_row else (settings.RAZORPAY_MODE if tenant == "local" else None)
    key_id = tenant_config.get_setting(db, tenant, "razorpay_key_id", default="") or ""
    wa_app = tenant_config.get_secret(db, tenant, "meta_whatsapp", "app_secret")
    wa_phone = tenant_config.get_setting(db, tenant, "meta_whatsapp_phone_number_id",
                                         default="")
    wa_token = tenant_config.get_secret(db, tenant, "meta_whatsapp", "access_token")
    return {
        "pilot_country": "IN", "pilot_currency": "INR",
        "shopify": {"configured": shop_ready,
                    "store": shop_domain if shop_ready else None,
                    "last_sync_at": connection.last_sync_at if connection else None,
                    "backfill_in_progress": bool(connection and connection.cursor)},
        "razorpay": {"configured": bool(tenant_config.get_secret(
                        db, tenant, "razorpay", "webhook_secret")),
                     "mode": mode,
                     "simulated": bool(key_id.startswith("rzp_test_mock"))},
        "meta_whatsapp": {"inbound_configured": bool(wa_app and wa_phone),
                          "outbound_configured": bool(wa_app and wa_phone and wa_token)},
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


@router.get("/settings")
def list_settings(db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    rows = db.query(models.TenantSetting).filter_by(
        tenant_id=identity.tenant_id).order_by(models.TenantSetting.key).all()
    return {row.key: row.value for row in rows}


@router.put("/settings")
def put_setting(payload: SettingInput, db: Session = Depends(get_db),
                identity: Identity = Depends(require_admin)):
    try:
        row = tenant_config.set_setting(db, identity.tenant_id, payload.key.strip(),
                                        payload.value.strip(), identity.actor)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"key": row.key, "value": row.value}


@router.get("/secrets")
def list_secrets(db: Session = Depends(get_db),
                 identity: Identity = Depends(require_admin)):
    """Secret pointers and resolvability only; values are never returned."""
    return tenant_config.public_secrets(db, identity.tenant_id)


@router.post("/secrets", status_code=201)
def put_secret(payload: SecretInput, db: Session = Depends(get_db),
               identity: Identity = Depends(require_admin)):
    try:
        row = tenant_config.set_secret(db, identity.tenant_id, payload.provider,
                                       payload.name.strip(), payload.secret_ref.strip(),
                                       payload.label.strip(), identity.actor)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"provider": row.provider, "name": row.name, "label": row.label,
            "secret_ref": row.secret_ref,
            "configured": bool(tenant_config.resolve_secret_ref(row.secret_ref))}


@router.delete("/secrets/{provider}/{name}")
def remove_secret(provider: str, name: str, db: Session = Depends(get_db),
                  identity: Identity = Depends(require_admin)):
    removed = tenant_config.delete_secret(db, identity.tenant_id, provider, name,
                                          identity.actor)
    if not removed:
        raise HTTPException(status_code=404, detail="Provider secret not found")
    db.commit()
    return {"status": "removed", "provider": provider, "name": name}
