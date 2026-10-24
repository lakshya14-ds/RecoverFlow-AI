import hashlib
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
    max_internal_actions_per_day: int = Field(default=5, ge=1, le=100)
    max_balance_cents: int = Field(default=100000, ge=100, le=100000000)


class RejectInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class SendInput(BaseModel):
    body: str = Field(min_length=1, max_length=500)


class EditDraftInput(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    change_reason: str = Field(default="Staff edit", max_length=500)


class ApproveDraftInput(BaseModel):
    version_number: int = Field(ge=1)
    version_hash: str = Field(min_length=32, max_length=64)


def _proposal(db: Session, proposal_id: int, identity: Identity) -> models.AgentProposal:
    proposal = db.get(models.AgentProposal, proposal_id)
    if not proposal or proposal.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Agent proposal not found")
    return proposal


@router.get("/status")
def status(db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    policy = db.get(models.AgentPolicy, identity.tenant_id)
    return {"model": settings.AGENT_MODEL if gemini_agent.configured() else "rules_only",
            "model_configured": gemini_agent.configured(),
            "rate_limits": gemini_agent.get_rate_limit_status(),
            "policy": policy}


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


@router.get("/proposals/{proposal_id}/versions")
def list_draft_versions(proposal_id: int, db: Session = Depends(get_db),
                        identity: Identity = Depends(get_identity)):
    _proposal(db, proposal_id, identity)
    return db.query(models.ProposalDraftVersion).filter_by(
        tenant_id=identity.tenant_id, proposal_id=proposal_id
    ).order_by(models.ProposalDraftVersion.version_number.asc()).all()


@router.post("/proposals/{proposal_id}/edit-draft")
def edit_proposal_draft(proposal_id: int, payload: EditDraftInput,
                        db: Session = Depends(get_db),
                        identity: Identity = Depends(get_identity)):
    proposal = _proposal(db, proposal_id, identity)
    if proposal.status in ("sent", "closed", "rejected"):
        raise HTTPException(status_code=409, detail=f"Cannot edit draft when proposal is {proposal.status}")

    latest_ver = db.query(models.ProposalDraftVersion).filter_by(
        tenant_id=identity.tenant_id, proposal_id=proposal_id
    ).order_by(models.ProposalDraftVersion.version_number.desc()).first()

    next_num = (latest_ver.version_number + 1) if latest_ver else 1
    v_hash = hashlib.sha256(payload.body.encode("utf-8")).hexdigest()

    version = models.ProposalDraftVersion(
        tenant_id=identity.tenant_id,
        proposal_id=proposal_id,
        version_number=next_num,
        body=payload.body,
        edited_by=identity.actor,
        change_reason=payload.change_reason,
        version_hash=v_hash,
        status="draft",
    )
    db.add(version)

    proposal.draft_text = payload.body
    proposal.status = "proposed"
    proposal.review_note = f"Draft edited to v{next_num}: {payload.change_reason}"
    db.add(models.AuditEvent(
        tenant_id=identity.tenant_id,
        actor=identity.actor,
        action="agent_draft_edited",
        entity_type="proposal_draft_version",
        entity_id=str(version.id),
        details=f"v{next_num}:{v_hash[:12]}",
    ))
    db.commit()
    db.refresh(version)
    return version


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal_draft(proposal_id: int, payload: ApproveDraftInput,
                           db: Session = Depends(get_db),
                           identity: Identity = Depends(get_identity)):
    proposal = _proposal(db, proposal_id, identity)
    version = db.query(models.ProposalDraftVersion).filter_by(
        tenant_id=identity.tenant_id,
        proposal_id=proposal_id,
        version_number=payload.version_number,
    ).first()

    if not version:
        raise HTTPException(status_code=404, detail=f"Draft version {payload.version_number} not found")

    if version.version_hash != payload.version_hash:
        raise HTTPException(status_code=409, detail="Version hash mismatch; draft was modified after display")

    version.status = "approved"
    version.approved_by = identity.actor
    version.approved_at = controlled_agent.utc_naive()

    proposal.status = "approved"
    proposal.reviewed_by = identity.actor
    proposal.review_note = f"Approved draft v{version.version_number} (hash: {version.version_hash[:12]})"

    db.add(models.AuditEvent(
        tenant_id=identity.tenant_id,
        actor=identity.actor,
        action="agent_draft_approved",
        entity_type="proposal_draft_version",
        entity_id=str(version.id),
        details=f"v{version.version_number}:{version.version_hash[:12]}",
    ))
    db.commit()
    return {
        "status": "approved",
        "proposal_id": proposal.id,
        "version_number": version.version_number,
        "version_hash": version.version_hash,
        "approved_by": version.approved_by,
        "approved_at": version.approved_at.isoformat(),
    }

