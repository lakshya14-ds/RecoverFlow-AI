"""Retail import endpoints for the Shopify India pilot."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import date
from decimal import Decimal, InvalidOperation
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database.db_manager import get_db
from app.services import shopify
from app.database import models
from app.services.receivables import balance_cents, cents

router = APIRouter(prefix="/sync", tags=["sync"])


class ConfirmShopifyCase(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    accept_due_date_change: bool = False


@router.get("/shopify/status")
def shopify_status(identity: Identity = Depends(get_identity)):
    return {"provider": "shopify", "tenant_id": identity.tenant_id,
            "configured": identity.tenant_id == "local" and shopify.configured(),
            "mode": "read_only_credit_terms"}


@router.post("/shopify")
def sync_shopify(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    if identity.tenant_id != "local" or not shopify.configured():
        raise HTTPException(status_code=503, detail="Shopify is not configured for this tenant")
    try:
        return shopify.import_orders(db, identity.tenant_id)
    except (RuntimeError, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/shopify/cases/{invoice_id}/confirm")
def confirm_shopify_case(invoice_id: int, payload: ConfirmShopifyCase,
                         db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id or invoice.source_system != "shopify":
        raise HTTPException(status_code=404, detail="Shopify receivable not found")
    if not shopify.configured() or identity.tenant_id != "local" or not invoice.source_order_id:
        raise HTTPException(status_code=503, detail="Shopify is not configured for this case")
    try:
        order = shopify.fetch_order(invoice.source_order_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not recheck the Shopify order") from exc
    if not order or order.get("cancelledAt"):
        raise HTTPException(status_code=409, detail="Order is missing or cancelled; keep contact paused")
    schedules = ((order.get("paymentTerms") or {}).get("paymentSchedules") or {}).get("nodes") or []
    schedule = next((row for row in schedules if row.get("id") == invoice.source_record_id), None)
    if not schedule:
        raise HTTPException(status_code=409, detail="Payment schedule is missing; keep contact paused")
    money = schedule.get("balanceDue") or {}
    if money.get("currencyCode") != invoice.currency:
        raise HTTPException(status_code=409, detail="Currency changed; keep contact paused")
    try:
        remote_decimal = Decimal(str(money["amount"]))
        if remote_decimal < 0:
            raise ValueError("Negative schedule balance")
        remote_cents = cents(remote_decimal) if remote_decimal > 0 else 0
        remote_due = date.fromisoformat(schedule["dueAt"][:10])
    except (InvalidOperation, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=409, detail="Shopify balance or due date is invalid") from exc
    if balance_cents(db, invoice) != remote_cents:
        raise HTTPException(status_code=409, detail="Balances differ; reconcile entries before confirming")
    if invoice.due_date != remote_due and not payload.accept_due_date_change:
        raise HTTPException(status_code=409, detail="Due date changed; explicitly accept it")
    invoice.due_date = remote_due
    invoice.requires_human_review = False
    # A separate admin resume action documents the decision to contact this customer.
    invoice.contact_suppressed = True
    for event in db.query(models.ProviderEvent).filter_by(
            tenant_id=identity.tenant_id, kind="retail", provider="shopify",
            resource_id=invoice.source_order_id, status="needs_review").all():
        event.status = "resolved"
        event.resolution_note = payload.reason
        event.resolved_by = identity.actor
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="shopify_case_confirmed", entity_type="invoice",
                             entity_id=str(invoice.id), details=payload.reason))
    db.commit()
    return {"invoice_id": invoice.id, "balance_cents": remote_cents,
            "contact_suppressed": True}


@router.post("/erp")
def legacy_erp():
    raise HTTPException(status_code=410, detail="Use POST /sync/shopify")


@router.get("/chart-of-accounts")
def legacy_chart_of_accounts():
    raise HTTPException(status_code=410, detail="Shopify orders do not have a chart of accounts")
