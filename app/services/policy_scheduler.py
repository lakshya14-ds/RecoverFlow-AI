"""Deterministic daily drafting under tenant policy; staff still approve and send."""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth import Identity
from app.database import models
from app.api.dunning import _check_contact, _check_recent_contact, trigger_dunning_stage

logger = logging.getLogger(__name__)


def create_due_drafts(db: Session, *, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    created = 0
    policies = db.query(models.CollectionPolicy).filter_by(enabled=True).all()
    for policy in policies:
        local = now.astimezone(ZoneInfo(policy.timezone))
        if local.hour != policy.run_hour:
            continue
        thresholds = (policy.stage1_days, policy.stage2_days,
                      policy.stage3_days, policy.stage4_days)
        invoices = db.query(models.Invoice).filter_by(
            tenant_id=policy.tenant_id, invoice_type="AR").order_by(
            models.Invoice.due_date).limit(200).all()
        for invoice in invoices:
            days_overdue = (local.date() - invoice.due_date).days
            if days_overdue < thresholds[0]:
                continue
            try:
                _check_contact(db, invoice)
                _check_recent_contact(db, invoice)
            except HTTPException:
                continue
            existing = db.query(models.DunningCampaign).filter_by(
                tenant_id=policy.tenant_id, invoice_id=invoice.id).all()
            if any(item.status in ("draft", "approved") for item in existing):
                continue
            stage = next((i for i in range(1, 5) if days_overdue >= thresholds[i - 1]
                          and not any(item.campaign_stage == i for item in existing)), None)
            if stage is None:
                continue
            try:
                trigger_dunning_stage(invoice.id, stage, db,
                                      Identity("policy_scheduler", policy.tenant_id, "editor"))
                created += 1
            except HTTPException as exc:
                logger.info("Skipped policy draft for invoice %s: %s", invoice.id, exc.detail)
    return created
