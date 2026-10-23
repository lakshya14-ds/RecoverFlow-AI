"""Opt-in schedule for collection draft creation; no automatic delivery."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db

router = APIRouter(prefix="/policies", tags=["policies"])


class PolicyInput(BaseModel):
    enabled: bool = False
    timezone: str = "Asia/Kolkata"
    run_hour: int = Field(default=9, ge=0, le=23)
    stage1_days: int = Field(default=7, ge=1, le=365)
    stage2_days: int = Field(default=15, ge=1, le=365)
    stage3_days: int = Field(default=30, ge=1, le=365)
    stage4_days: int = Field(default=45, ge=1, le=365)

    @model_validator(mode="after")
    def check_policy(self):
        if not (self.stage1_days < self.stage2_days < self.stage3_days < self.stage4_days):
            raise ValueError("Stage days must increase")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unknown timezone") from exc
        return self


@router.get("/collection")
def get_policy(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    policy = db.get(models.CollectionPolicy, identity.tenant_id)
    return policy or PolicyInput()


@router.put("/collection")
def set_policy(payload: PolicyInput, db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    policy = db.get(models.CollectionPolicy, identity.tenant_id)
    if not policy:
        policy = models.CollectionPolicy(tenant_id=identity.tenant_id)
        db.add(policy)
    for field, value in payload.model_dump().items():
        setattr(policy, field, value)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
                             action="collection_policy_updated", entity_type="policy",
                             entity_id=identity.tenant_id, details=payload.model_dump_json()))
    db.commit()
    db.refresh(policy)
    return policy
