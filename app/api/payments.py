"""Staff-created Razorpay links. Provider callbacks, not redirects, post payments."""
from uuid import UUID
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services.receivables import balance_cents, split_balance
from app.services import razorpay

router = APIRouter(prefix="/payments", tags=["payments"])


class LinkRequest(BaseModel):
    invoice_id: int
    idempotency_key: UUID
    amount_cents: int | None = None


@router.get("/links")
def list_links(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    return db.query(models.PaymentLink).filter_by(tenant_id=identity.tenant_id).order_by(
        models.PaymentLink.created_at.desc()).limit(100).all()


@router.post("/links", status_code=201)
def create_link(payload: LinkRequest, db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    if identity.tenant_id != "local" or not razorpay.configured():
        raise HTTPException(status_code=503, detail="Razorpay is not configured for this tenant")
    from app.config import settings as _settings
    from app.services import tenant_config as _tenants
    link_mode = _tenants.get_setting(db, identity.tenant_id, "razorpay_mode", default="test") or "test"
    if link_mode == "live" and not _settings.RAZORPAY_LIVE_ENABLED:
        raise HTTPException(status_code=503, detail="Razorpay live mode is disabled")
    key = str(payload.idempotency_key)
    previous = db.query(models.PaymentLink).filter_by(
        tenant_id=identity.tenant_id, idempotency_key=key).first()
    if previous:
        if previous.invoice_id != payload.invoice_id:
            raise HTTPException(status_code=409, detail="Idempotency key belongs to another invoice")
        return previous
    invoice = db.get(models.Invoice, payload.invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id or invoice.invoice_type != "AR":
        raise HTTPException(status_code=404, detail="Receivable not found")
    if invoice.requires_human_review or invoice.status == "cancelled" or invoice.currency != "INR":
        raise HTTPException(status_code=409, detail="Case is not eligible for an INR payment link")
    
    split = split_balance(db, invoice)
    outstanding = split["outstanding_cents"]
    undisputed = split["undisputed_cents"]

    if outstanding <= 0:
        raise HTTPException(status_code=409, detail="Receivable is already paid")

    if invoice.dispute_open or invoice.status == "disputed":
        if undisputed <= 0:
            raise HTTPException(status_code=409, detail="All outstanding funds are disputed; cannot generate payment link")
        target_amount = payload.amount_cents or undisputed
    else:
        target_amount = payload.amount_cents or outstanding

    if target_amount <= 0 or target_amount > outstanding:
        raise HTTPException(status_code=409, detail="Link amount exceeds the outstanding balance")

    active = db.query(models.PaymentLink).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).filter(
        models.PaymentLink.status.in_(("creating", "open", "partially_paid", "needs_review"))).first()
    if active:
        raise HTTPException(status_code=409, detail="An active or unresolved link already exists")
    link = models.PaymentLink(tenant_id=identity.tenant_id, invoice_id=invoice.id,
                              provider="razorpay", idempotency_key=key,
                              amount_cents=target_amount, currency="INR", status="creating",
                              mode=link_mode if link_mode in ("test", "live") else "test",
                              expires_at=datetime.now(timezone.utc) + timedelta(days=7))
    db.add(link)
    db.commit()
    db.refresh(link)
    try:
        result = razorpay.create_remote_link(link, invoice)
    except Exception as exc:
        # A timeout can occur after remote creation. Do not make another link automatically.
        link.status = "needs_review"
        db.commit()
        raise HTTPException(status_code=502, detail="Link creation is unresolved; check Razorpay by reference ID") from exc
    link.provider_link_id = result["id"]
    link.url = result["url"]
    link.status = "open"
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="payment_link_created", entity_type="invoice",
                             entity_id=str(invoice.id), details=link.provider_link_id))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Provider link already recorded") from exc
    db.refresh(link)
    return link


@router.post("/links/{link_id}/cancel")
def cancel_link(link_id: int, db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    link = db.get(models.PaymentLink, link_id)
    if not link or link.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Payment link not found")
    if link.status == "cancelled":
        return link
    if link.status not in ("open", "partially_paid", "needs_review") or not link.provider_link_id:
        raise HTTPException(status_code=409, detail="Link cannot be cancelled from its current state")
    try:
        razorpay.cancel_remote_link(link)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Razorpay did not confirm cancellation") from exc
    link.status = "cancelled"
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="payment_link_cancelled", entity_type="payment_link",
                             entity_id=str(link.id)))
    db.commit()
    db.refresh(link)
    return link


@router.post("/links/{link_id}/recover")
def recover_link(link_id: int, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    link = db.get(models.PaymentLink, link_id)
    if not link or link.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Payment link not found")
    if link.provider_link_id or link.status not in ("creating", "needs_review"):
        raise HTTPException(status_code=409, detail="Only unresolved creations can be recovered")
    try:
        remote = razorpay.find_remote_link(link)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not verify the link in Razorpay") from exc
    if not remote:
        raise HTTPException(status_code=409, detail="No link found by reference ID; check Razorpay before retrying")
    link.provider_link_id = remote["id"]
    link.url = remote["url"]
    link.status = "open" if remote["status"] == "created" else "needs_review"
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="payment_link_recovered", entity_type="payment_link",
                             entity_id=str(link.id), details=link.provider_link_id))
    db.commit()
    db.refresh(link)
    return link


@router.post("/intent")
def legacy_intent():
    raise HTTPException(status_code=410, detail="Use POST /payments/links for receivables")


@router.post("/schedule")
def legacy_schedule():
    raise HTTPException(status_code=410, detail="Outgoing payments are outside RecoverFlow collections")


@router.get("/razorpay/status")
def razorpay_status(db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    return razorpay.status_for_tenant(db, identity.tenant_id)


@router.get("/discrepancies")
def list_discrepancies(status: str = "open", db: Session = Depends(get_db),
                       identity: Identity = Depends(get_identity)):
    if status not in ("open", "resolved"):
        raise HTTPException(status_code=422, detail="Status must be open or resolved")
    rows = db.query(models.PaymentDiscrepancy).filter_by(
        tenant_id=identity.tenant_id, status=status).order_by(
        models.PaymentDiscrepancy.id).all()
    return [{"id": row.id, "provider": row.provider, "kind": row.kind,
             "reference": row.reference, "invoice_id": row.invoice_id,
             "expected_cents": row.expected_cents,
             "actual_cents": row.actual_cents, "currency": row.currency,
             "event_id": row.event_id, "note": row.note,
             "status": row.status, "resolution": row.resolution,
             "resolved_by": row.resolved_by} for row in rows]


class DiscrepancyResolve(BaseModel):
    action: str = "dismiss"
    note: str = ""


@router.post("/discrepancies/{discrepancy_id}/resolve")
def resolve_discrepancy(discrepancy_id: int, payload: DiscrepancyResolve,
                        db: Session = Depends(get_db),
                        identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    disc = db.get(models.PaymentDiscrepancy, discrepancy_id)
    if not disc or disc.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Discrepancy not found")
    try:
        resolved = razorpay.resolve_discrepancy(
            db, disc.id, identity.actor, payload.action.strip(),
            (payload.note or "").strip())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"id": resolved.id, "status": resolved.status,
            "resolution": resolved.resolution}


class SettlementInput(BaseModel):
    settlement_ref: str
    lines: list = []


@router.post("/settlements", status_code=201)
def upload_settlement(payload: SettlementInput, db: Session = Depends(get_db),
                      identity: Identity = Depends(get_identity)):
    if not payload.settlement_ref.strip() or not payload.lines or len(payload.lines) > 500:
        raise HTTPException(status_code=422, detail="Settlement needs a reference and 1-500 lines")
    try:
        report = razorpay.match_settlement(
            db, identity.tenant_id, identity.actor,
            payload.settlement_ref.strip(), payload.lines)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return report
