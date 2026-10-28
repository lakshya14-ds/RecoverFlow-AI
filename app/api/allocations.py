"""Tenant-scoped transfer allocation proposals and payer aliases."""
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services import allocation

router = APIRouter(prefix="/allocations", tags=["Allocations"])


class ProposeInput(BaseModel):
    afis_transaction_id: str = Field(min_length=1, max_length=120)
    currency: str = Field(default="INR", min_length=3, max_length=3)


class LegInput(BaseModel):
    invoice_id: int = Field(gt=0)
    amount_cents: int = Field(gt=0)
    allocation: Literal["undisputed_first", "disputed_first", "undisputed", "disputed"] = "undisputed_first"


class ApproveInput(BaseModel):
    legs: list[LegInput] | None = None
    reason: str = ""


class RejectInput(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class PayerAliasInput(BaseModel):
    alias: str = Field(min_length=1, max_length=200)
    counterparty_name: str = Field(min_length=1, max_length=200)


def _proposal(db: Session, proposal_id: int, identity: Identity) -> models.AllocationProposal:
    proposal = db.get(models.AllocationProposal, proposal_id)
    if not proposal or proposal.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Allocation proposal not found")
    return proposal


def _public(db: Session, proposal: models.AllocationProposal) -> dict:
    legs = db.query(models.AllocationLeg).filter_by(proposal_id=proposal.id).order_by(
        models.AllocationLeg.id).all()
    return {"id": proposal.id, "afis_transaction_id": proposal.afis_transaction_id,
            "transfer_cents": proposal.transfer_cents, "currency": proposal.currency,
            "transfer_date": proposal.transfer_date, "description": proposal.description,
            "status": proposal.status, "residual_cents": allocation.residual_cents(db, proposal),
            "candidates": json.loads(proposal.candidates_json or "[]"),
            "decided_by": proposal.decided_by, "decision_reason": proposal.decision_reason,
            "legs": [{"id": leg.id, "invoice_id": leg.invoice_id,
                      "amount_cents": leg.amount_cents, "allocation": leg.allocation,
                      "status": leg.status, "reason": leg.reason,
                      "entry_id": leg.entry_id} for leg in legs]}


@router.get("/transfers/unmatched")
def unmatched_transfers(limit: int = 100, db: Session = Depends(get_db),
                        identity: Identity = Depends(get_identity)):
    return allocation.unmatched_transfers(db, identity.tenant_id, limit=min(max(limit, 1), 500))


@router.post("/proposals", status_code=201)
def propose(payload: ProposeInput, db: Session = Depends(get_db),
            identity: Identity = Depends(get_identity)):
    try:
        proposal, duplicate = allocation.propose(
            db, identity.tenant_id, payload.afis_transaction_id.strip(),
            identity.actor, payload.currency.upper())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    body = _public(db, proposal)
    body["duplicate"] = duplicate
    return body


@router.get("/proposals")
def list_proposals(status: str | None = None, db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    query = db.query(models.AllocationProposal).filter_by(tenant_id=identity.tenant_id)
    if status:
        query = query.filter_by(status=status)
    return [_public(db, row) for row in query.order_by(
        models.AllocationProposal.id.desc()).limit(200).all()]


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: int, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    return _public(db, _proposal(db, proposal_id, identity))


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(proposal_id: int, payload: ApproveInput,
                     db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    proposal = _proposal(db, proposal_id, identity)
    if proposal.status == "ambiguous" and payload.legs is None:
        raise HTTPException(status_code=409,
                            detail="Ambiguous proposal: staff must choose explicit legs")
    try:
        allocation.approve(db, proposal, identity.actor,
                           legs=[item.model_dump() for item in payload.legs]
                           if payload.legs is not None else None,
                           reason=payload.reason)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _public(db, proposal)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, payload: RejectInput,
                    db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    proposal = _proposal(db, proposal_id, identity)
    try:
        allocation.reject(db, proposal, identity.actor, payload.reason)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _public(db, proposal)


@router.get("/payer-aliases")
def list_payer_aliases(db: Session = Depends(get_db),
                       identity: Identity = Depends(get_identity)):
    return db.query(models.PayerAlias).filter_by(
        tenant_id=identity.tenant_id).order_by(models.PayerAlias.id).all()


@router.post("/payer-aliases", status_code=201)
def create_payer_alias(payload: PayerAliasInput, db: Session = Depends(get_db),
                       identity: Identity = Depends(get_identity)):
    from app.services.investigation import normalize
    alias = normalize(payload.alias)
    if not alias:
        raise HTTPException(status_code=422, detail="Alias must contain letters or digits")
    existing = db.query(models.PayerAlias).filter_by(
        tenant_id=identity.tenant_id, alias=alias).first()
    if existing:
        if existing.counterparty_name != payload.counterparty_name.strip():
            raise HTTPException(status_code=409,
                                detail="Alias is already assigned to a different payer")
        return existing
    row = models.PayerAlias(tenant_id=identity.tenant_id, alias=alias,
        counterparty_name=payload.counterparty_name.strip(), approved_by=identity.actor)
    db.add(row)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="payer_alias_approved", entity_type="payer_alias", entity_id="0",
        details=f"{alias} -> {row.counterparty_name}"))
    db.commit()
    db.refresh(row)
    return row
