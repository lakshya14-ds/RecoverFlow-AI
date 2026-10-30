from decimal import Decimal
"""
RecoverFlow - Receivables and Collections
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db_manager import get_db
from app.database import models
from app.agents.dunning_communication import run_dunning_agent
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy import or_
from app.auth import Identity, get_identity
from app.config import settings
from app.services.receivables import balance_cents, split_balance
from app.services.negotiation import guard_outbound
from app.services.case_lifecycle import checkpoint

router = APIRouter(prefix="/dunning", tags=["Dunning"])


class DraftEdit(BaseModel):
    subject: str = Field(min_length=1)
    body: str = Field(min_length=1)


class ManualContact(BaseModel):
    channel: Literal["email", "phone", "other"]
    reference: str = Field(min_length=3, max_length=120)


def _check_contact(db: Session, invoice: models.Invoice) -> int:
    if not invoice or invoice.invoice_type != "AR" or invoice.status in ("cancelled", "disputed"):
        raise HTTPException(status_code=409, detail="Only open receivables can be contacted")
    if invoice.investigation_hold or invoice.requires_human_review or invoice.dispute_open or invoice.contact_suppressed or invoice.contact_opt_out:
        raise HTTPException(status_code=409, detail="Contact is paused pending review or customer request")
    balance = balance_cents(db, invoice)
    if balance <= 0:
        raise HTTPException(status_code=409, detail="Receivable has no outstanding balance")
    return balance


def _check_recent_contact(db: Session, invoice: models.Invoice) -> None:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=settings.CONTACT_COOLDOWN_DAYS)
    recent = db.query(models.DunningCampaign).filter(
        models.DunningCampaign.tenant_id == invoice.tenant_id,
        models.DunningCampaign.invoice_id == invoice.id,
        models.DunningCampaign.status.in_(("sent", "contacted_manually")),
        or_(models.DunningCampaign.email_sent_at >= cutoff,
            models.DunningCampaign.contacted_at >= cutoff),
    ).first()
    if recent:
        raise HTTPException(status_code=409, detail="Contact cooldown is still active")

@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db), limit: int = 50,
                   identity: Identity = Depends(get_identity)):
    return db.query(models.DunningCampaign).filter(
        models.DunningCampaign.tenant_id == identity.tenant_id).limit(max(1, min(limit, 200))).all()

@router.post("/trigger-stage")
def trigger_dunning_stage(invoice_id: int, stage: int, db: Session = Depends(get_db),
                          identity: Identity = Depends(get_identity)):
    invoice = db.query(models.Invoice).filter(models.Invoice.id == invoice_id).first()
    if not invoice or invoice.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Invoice not found")
    balance = _check_contact(db, invoice)
    if stage not in (1, 2, 3, 4):
        raise HTTPException(status_code=422, detail="Stage must be 1 through 4")
    days_overdue = (datetime.now(timezone.utc).date() - invoice.due_date).days
    if days_overdue <= 0:
        raise HTTPException(status_code=409, detail="Invoice is not overdue")
    policy = db.get(models.CollectionPolicy, identity.tenant_id)
    thresholds = ((policy.stage1_days, policy.stage2_days,
                   policy.stage3_days, policy.stage4_days) if policy and policy.enabled else
                  (settings.DUNNING_STAGE1_DAYS, settings.DUNNING_STAGE2_DAYS,
                   settings.DUNNING_STAGE3_DAYS, settings.DUNNING_STAGE4_DAYS))
    threshold = thresholds[stage - 1]
    if days_overdue < threshold:
        raise HTTPException(status_code=409, detail="Invoice has not reached this stage")
    existing = db.query(models.DunningCampaign).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id, campaign_stage=stage).filter(
        models.DunningCampaign.status.in_(("draft", "approved", "sent", "contacted_manually"))).first()
    if existing:
        raise HTTPException(status_code=409, detail="This collection stage already exists")
        
    # Generate a collection draft.
    state = {
        "invoice_data": {
            "invoice_number": invoice.invoice_number,
            "counterparty_name": invoice.counterparty_name,
            "total_amount": Decimal(balance) / 100,
            "currency": invoice.currency or "USD",
            "due_date": str(invoice.due_date),
            "days_overdue": days_overdue
        },
        "dunning_stage": stage
    }
    
    result = run_dunning_agent(state)
    
    # Save the draft.
    campaign = models.DunningCampaign(
        tenant_id=identity.tenant_id,
        invoice_id=invoice.id,
        campaign_stage=stage,
        days_overdue=days_overdue,
        tone=result["email_data"]["tone"],
        email_subject=result["email_data"]["subject"],
        email_body=result["email_data"]["body"],
        balance_cents_at_draft=balance,
        generated_by=identity.actor,
        status="draft"
    )
    db.add(campaign)
    db.flush()
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="dunning_drafted",
                             entity_type="campaign", entity_id=str(campaign.id)))
    db.commit()
    
    return {"status": "success", "campaign_stage": stage, "email_data": result["email_data"]}


@router.put("/campaigns/{campaign_id}")
def edit_campaign(campaign_id: int, payload: DraftEdit, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    campaign = db.get(models.DunningCampaign, campaign_id)
    if not campaign or campaign.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in ("draft", "approved"):
        raise HTTPException(status_code=409, detail="Only an unsent draft can be edited")
    invoice = db.get(models.Invoice, campaign.invoice_id)
    split = split_balance(db, invoice)
    allowed, reason = guard_outbound(payload.body, split["disputed_cents"], split["undisputed_cents"])
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    campaign.email_subject = payload.subject
    campaign.email_body = payload.body
    campaign.generated_by = identity.actor
    campaign.status = "draft"
    campaign.approved_by = None
    campaign.approved_at = None
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="dunning_edited", entity_type="campaign",
                             entity_id=str(campaign_id)))
    db.commit()
    return {"status": "draft", "campaign_id": campaign.id}


@router.post("/campaigns/{campaign_id}/approve")
def approve_campaign(campaign_id: int, db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    campaign = db.get(models.DunningCampaign, campaign_id)
    if not campaign or campaign.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    from app.services import team_ops
    _sod_ok, _sod_reason = team_ops.sod_allows(
        db, identity.tenant_id, campaign.generated_by, identity.actor,
        "campaign approval", f"campaign:{campaign_id}")
    if not _sod_ok:
        raise HTTPException(status_code=409, detail=_sod_reason)
    if campaign.status != "draft":
        raise HTTPException(status_code=409, detail="Campaign is not a draft")
    invoice = db.get(models.Invoice, campaign.invoice_id)
    balance = _check_contact(db, invoice)
    if campaign.balance_cents_at_draft != balance:
        raise HTTPException(status_code=409, detail="Draft balance changed; refresh the draft")
    split = split_balance(db, invoice)
    from app.services.multilingual import verify_outbound_body
    try:
        verify_outbound_body(db, invoice, campaign.email_body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    checkpoint(db, invoice, "draft_approved", identity.actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, "staff:approval", identity.actor)
    campaign.status = "approved"
    campaign.approved_by = identity.actor
    campaign.approved_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="dunning_approved", entity_type="campaign",
                             entity_id=str(campaign_id)))
    db.commit()
    return {"status": "approved", "campaign_id": campaign.id}


@router.post("/campaigns/{campaign_id}/refresh")
def refresh_campaign(campaign_id: int, db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    campaign = db.get(models.DunningCampaign, campaign_id)
    if not campaign or campaign.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status not in ("draft", "approved"):
        raise HTTPException(status_code=409, detail="Contacted campaigns cannot be refreshed")
    invoice = db.get(models.Invoice, campaign.invoice_id)
    balance = _check_contact(db, invoice)
    result = run_dunning_agent({
        "invoice_data": {
            "invoice_number": invoice.invoice_number,
            "counterparty_name": invoice.counterparty_name,
            "total_amount": Decimal(balance) / 100,
            "currency": invoice.currency or "USD",
            "due_date": str(invoice.due_date),
            "days_overdue": (datetime.now(timezone.utc).date() - invoice.due_date).days,
        }, "dunning_stage": campaign.campaign_stage,
    })
    campaign.email_subject = result["email_data"]["subject"]
    campaign.email_body = result["email_data"]["body"]
    campaign.balance_cents_at_draft = balance
    campaign.status = "draft"
    campaign.approved_by = None
    campaign.approved_at = None
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="dunning_refreshed", entity_type="campaign",
                             entity_id=str(campaign_id)))
    db.commit()
    return {"status": "draft", "campaign_id": campaign.id}


@router.post("/campaigns/{campaign_id}/record-contact")
def record_manual_contact(campaign_id: int, payload: ManualContact,
                          db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    campaign = db.get(models.DunningCampaign, campaign_id)
    if not campaign or campaign.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "approved" or not campaign.approved_by:
        raise HTTPException(status_code=409, detail="Approve the draft before recording contact")
    invoice = db.get(models.Invoice, campaign.invoice_id)
    balance = _check_contact(db, invoice)
    if campaign.balance_cents_at_draft != balance:
        raise HTTPException(status_code=409, detail="Draft balance changed; refresh and approve it again")
    _check_recent_contact(db, invoice)
    campaign.status = "contacted_manually"
    campaign.contacted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    campaign.contact_channel = payload.channel
    campaign.contact_reference = payload.reference
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="manual_contact_recorded", entity_type="campaign",
                             entity_id=str(campaign_id), details=f"{payload.channel}: {payload.reference}"))
    db.commit()
    return {"status": "contacted_manually", "campaign_id": campaign.id}


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(campaign_id: int, db: Session = Depends(get_db),
                        identity: Identity = Depends(get_identity)):
    campaign = db.get(models.DunningCampaign, campaign_id)
    if not campaign or campaign.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != "approved" or not campaign.approved_by:
        raise HTTPException(status_code=409, detail="A staff member must approve the draft before sending")
    invoice = db.get(models.Invoice, campaign.invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id or not invoice.counterparty_email:
        raise HTTPException(status_code=409, detail="Invoice is ineligible or recipient email is missing")
    balance = _check_contact(db, invoice)
    if campaign.balance_cents_at_draft != balance:
        raise HTTPException(status_code=409, detail="Draft balance changed; refresh and approve it again")
    _check_recent_contact(db, invoice)
    split = split_balance(db, invoice)
    from app.services.multilingual import verify_outbound_body
    try:
        verify_outbound_body(db, invoice, campaign.email_body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    checkpoint(db, invoice, "draft_sandbox_sent", identity.actor)
    campaign.status = "sandbox_sent"
    campaign.email_sent = False
    campaign.email_to = None
    campaign.email_sent_at = None
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="dunning_sandbox_queued",
                             entity_type="campaign", entity_id=str(campaign.id)))
    db.commit()
    return {"status": "sandbox_sent", "campaign_id": campaign.id,
            "channel": "SIMULATED email sandbox outbox"}
