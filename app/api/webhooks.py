"""Public provider callbacks; each endpoint verifies the provider signature first."""
import hmac
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.db_manager import get_db
import hashlib
import json
from app.services import razorpay, meta_whatsapp, shopify, tenant_config
from app.database import models

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _tenant(tenant_id: str) -> str:
    try:
        return tenant_config.check_tenant_slug(tenant_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Unknown tenant")


@router.post("/razorpay/{tenant_id}")
async def razorpay_callback(tenant_id: str, request: Request,
                            db: Session = Depends(get_db),
                            signature: str = Header(default="", alias="X-Razorpay-Signature"),
                            event_id: str = Header(default="", alias="X-Razorpay-Event-Id")):
    tenant_id = _tenant(tenant_id)
    secret = tenant_config.get_secret(db, tenant_id, "razorpay", "webhook_secret")
    if not secret:
        raise HTTPException(status_code=503, detail="Razorpay webhook is not configured")
    from app.config import settings as _settings
    mode = tenant_config.get_setting(db, tenant_id, "razorpay_mode", default="test") or "test"
    if mode == "live" and not _settings.RAZORPAY_LIVE_ENABLED:
        raise HTTPException(status_code=503, detail="Razorpay live webhooks are disabled")
    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Webhook payload too large")
    if not razorpay.verify_signature(body, signature, secret=secret):
        raise HTTPException(status_code=401, detail="Invalid Razorpay signature")
    if not event_id or len(event_id) > 120:
        raise HTTPException(status_code=422, detail="Missing Razorpay event ID")
    try:
        event = razorpay.process_event(db, tenant_id, event_id, body, mode=mode)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except IntegrityError:
        # A concurrent worker won the same event ID: converge on its row
        # instead of double-processing. Different bytes still 409.
        db.rollback()
        winner = db.query(models.ProviderEvent).filter_by(
            tenant_id=tenant_id, kind="payment", provider="razorpay",
            event_id=event_id).first()
        if not winner:
            raise HTTPException(
                status_code=503,
                detail="Concurrent delivery collided; retry the webhook") from None
        if winner.body_sha256 != hashlib.sha256(body).hexdigest():
            raise HTTPException(
                status_code=409,
                detail="Webhook event ID was reused with a different payload")
        return {"event_id": winner.event_id, "status": winner.status,
                "duplicate": True}
    return {"event_id": event.event_id, "status": event.status}


@router.post("/inbound")
async def legacy_inbound():
    raise HTTPException(status_code=503, detail="Inbound provider is not configured")


@router.post("/shopify/{tenant_id}")
async def shopify_callback(tenant_id: str, request: Request, db: Session = Depends(get_db),
                           signature: str = Header(default="", alias="X-Shopify-Hmac-Sha256"),
                           event_id: str = Header(default="", alias="X-Shopify-Webhook-Id"),
                           shop_domain: str = Header(default="", alias="X-Shopify-Shop-Domain"),
                           topic: str = Header(default="", alias="X-Shopify-Topic")):
    tenant_id = _tenant(tenant_id)
    secret = tenant_config.get_secret(db, tenant_id, "shopify", "webhook_secret")
    domain = tenant_config.get_setting(db, tenant_id, "shopify_shop_domain", default="")
    if not secret or not (domain.endswith(".myshopify.com") and domain.count(".") == 2):
        raise HTTPException(status_code=503, detail="Shopify webhook is not configured")
    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Webhook payload too large")
    if (shop_domain.lower() != domain.lower() or
            not shopify.verify_signature(body, signature, secret=secret)):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook")
    if not event_id or len(event_id) > 120:
        raise HTTPException(status_code=422, detail="Missing Shopify webhook ID")
    digest = hashlib.sha256(body).hexdigest()
    existing = db.query(models.ProviderEvent).filter_by(
        tenant_id=tenant_id, kind="retail", provider="shopify", event_id=event_id).first()
    if existing:
        if existing.body_sha256 != digest:
            raise HTTPException(status_code=409, detail="Webhook ID was reused with different content")
        return {"event_id": event_id, "status": existing.status}
    try:
        payload = json.loads(body)
        order_id = int(payload["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid Shopify order payload") from exc
    gid = f"gid://shopify/Order/{order_id}"
    changed = 0
    if topic in ("orders/update", "orders/paid", "orders/cancelled", "orders/edited"):
        invoices = db.query(models.Invoice).filter_by(
            tenant_id=tenant_id, source_system="shopify", source_order_id=gid).all()
        for invoice in invoices:
            invoice.contact_suppressed = True
            invoice.requires_human_review = True
            changed += 1
    status = "needs_review" if changed else ("queued" if topic == "orders/create" else "ignored")
    db.add(models.ProviderEvent(tenant_id=tenant_id, kind="retail", provider="shopify",
                                event_id=event_id, resource_id=gid,
                                body_sha256=digest, status=status))
    db.commit()
    return {"event_id": event_id, "status": status, "cases_paused": changed}


@router.get("/meta-whatsapp/{tenant_id}")
def verify_meta(tenant_id: str, request: Request, db: Session = Depends(get_db)):
    tenant_id = _tenant(tenant_id)
    params = request.query_params
    token = tenant_config.get_secret(db, tenant_id, "meta_whatsapp", "verify_token")
    if (not token or params.get("hub.mode") != "subscribe" or
            not hmac.compare_digest(params.get("hub.verify_token", ""), token)):
        raise HTTPException(status_code=403, detail="Meta verification failed")
    return PlainTextResponse(params.get("hub.challenge", ""))


@router.post("/meta-whatsapp/{tenant_id}")
async def meta_callback(tenant_id: str, request: Request, db: Session = Depends(get_db),
                        signature: str = Header(default="", alias="X-Hub-Signature-256")):
    tenant_id = _tenant(tenant_id)
    secret = tenant_config.get_secret(db, tenant_id, "meta_whatsapp", "app_secret")
    phone = tenant_config.get_setting(db, tenant_id, "meta_whatsapp_phone_number_id",
                                      default="")
    if not secret or not phone:
        raise HTTPException(status_code=503, detail="Meta WhatsApp is not configured")
    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Webhook payload too large")
    if not meta_whatsapp.verify_signature(body, signature, app_secret=secret):
        raise HTTPException(status_code=401, detail="Invalid Meta signature")
    try:
        return meta_whatsapp.receive(db, body, tenant_id, phone_number_id=phone)
    except (ValueError, TypeError, KeyError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail="Invalid Meta webhook payload") from exc
