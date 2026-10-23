"""Staff controls for proposals, internal actions and reviewed customer replies."""
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.services import controlled_agent, gemini_agent

router = APIRouter(prefix="/agent", tags=["Controlled agent"])


class PolicyInput(BaseModel):
    enabled: bool = False
    auto_assess: bool = False
    auto_execute_internal: bool = False
    max_assessments_per_day: int = Field(default=20, ge=1, le=100)
    max_internal_actions_per_day: int = Field(default=5, ge=1, le=25)
    max_balance_cents: int = Field(default=100000, ge=100, le=100000000)


class RejectInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SendInput(BaseModel):
    body: str = Field(min_length=1, max_length=500)


def _proposal(db: Session, proposal_id: int, identity: Identity) -> models.AgentProposal:
    proposal = db.get(models.AgentProposal, proposal_id)
    if not proposal or proposal.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Agent proposal not found")
    return proposal


@router.get("/status")
def status(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    policy = db.get(models.AgentPolicy, identity.tenant_id)
    return {"model": settings.AGENT_MODEL if gemini_agent.configured() else "rules_only",
            "model_configured": gemini_agent.configured(), "policy": policy}


@router.put("/policy")
def update_policy(payload: PolicyInput, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    if identity.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    policy = db.get(models.AgentPolicy, identity.tenant_id)
    if not policy:
        policy = models.AgentPolicy(tenant_id=identity.tenant_id)
        db.add(policy)
    for key, value in payload.model_dump().items():
        setattr(policy, key, value)
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="agent_policy_updated", entity_type="agent_policy",
        entity_id=identity.tenant_id, details=str(payload.model_dump())))
    db.commit()
    db.refresh(policy)
    return policy


@router.post("/cases/{invoice_id}/assess", status_code=201)
def assess_case(invoice_id: int, db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    return controlled_agent.assess(db, identity.tenant_id, invoice_id, identity.actor)


@router.get("/proposals")
def proposals(db: Session = Depends(get_db), identity: Identity = Depends(get_identity),
              limit: int = 50):
    return db.query(models.AgentProposal).filter_by(tenant_id=identity.tenant_id).order_by(
        models.AgentProposal.id.desc()).limit(max(1, min(limit, 100))).all()


@router.get("/cases/{invoice_id}/notes")
def notes(invoice_id: int, db: Session = Depends(get_db),
          identity: Identity = Depends(get_identity)):
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Case not found")
    return db.query(models.AgentCaseNote).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(
        models.AgentCaseNote.id.desc()).limit(50).all()


@router.post("/proposals/{proposal_id}/internal/{action}")
def execute_internal(proposal_id: int, action: Literal["case_note", "collection_draft"],
                     db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    proposal = _proposal(db, proposal_id, identity)
    return controlled_agent.execute_internal(db, proposal, action, identity.actor)


@router.post("/proposals/{proposal_id}/reject")
def reject(proposal_id: int, payload: RejectInput, db: Session = Depends(get_db),
           identity: Identity = Depends(get_identity)):
    proposal = _proposal(db, proposal_id, identity)
    if proposal.status in ("sent", "rejected", "closed", "draft_created"):
        raise HTTPException(status_code=409, detail="Proposal cannot be rejected now")
    proposal.status = "rejected"
    proposal.reviewed_by = identity.actor
    proposal.review_note = payload.reason
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="agent_proposal_rejected", entity_type="agent_proposal",
        entity_id=str(proposal.id), details=payload.reason))
    db.commit()
    return {"status": "rejected", "proposal_id": proposal.id}


@router.post("/proposals/{proposal_id}/send-reply")
def send_reviewed_reply(proposal_id: int, payload: SendInput,
                        db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    """Explicit staff action. Reuse Release 2's 24h, opt-out and idempotency gates."""
    proposal = _proposal(db, proposal_id, identity)
    if proposal.action != "reply_draft" or not proposal.inbound_id:
        raise HTTPException(status_code=409, detail="Proposal is not a reply draft")
    key = uuid5(NAMESPACE_URL, f"recoverflow:{identity.tenant_id}:agent-reply:{proposal.id}")
    if proposal.status == "sent":
        prior = db.query(models.OutboundMessage).filter_by(
            tenant_id=identity.tenant_id, idempotency_key=str(key)).first()
        if prior and prior.status == "sent":
            return prior
    if proposal.status != "proposed":
        raise HTTPException(status_code=409, detail="Proposal is not open for review")
    controlled_agent._fresh(db, proposal)
    from app.api.messages import ReplyInput, reply
    outbound = reply(proposal.inbound_id,
                     ReplyInput(body=payload.body, idempotency_key=key), db, identity)
    if outbound.status != "sent":
        raise HTTPException(status_code=409, detail="Reply send needs provider review")
    proposal.status = "sent"
    proposal.reviewed_by = identity.actor
    proposal.review_note = "Staff reviewed and sent a reply"
    proposal.executed_at = controlled_agent.utc_naive()
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action="agent_reply_approved_sent", entity_type="agent_proposal",
        entity_id=str(proposal.id), details=str(outbound.id)))
    db.commit()
    db.refresh(outbound)
    return outbound
