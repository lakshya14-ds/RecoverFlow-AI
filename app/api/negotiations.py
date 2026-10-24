"""Per-case negotiation, with sandbox-only outbound messages."""
from typing import Literal
import httpx

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.services import gemini_agent, negotiation
from app.services.receivables import split_balance

router = APIRouter(prefix="/negotiations", tags=["Negotiation"])


class SettingsInput(BaseModel):
    mode: Literal["manual", "delegate"] = "manual"
    max_instalments: int | None = Field(default=None, ge=1, le=12)
    max_extension_days: int | None = Field(default=None, ge=0, le=365)
    min_first_percent: int | None = Field(default=None, ge=1, le=100)
    settlement_discount_allowed: bool | None = None
    max_ai_rounds: int | None = Field(default=None, ge=1, le=10)


class BodyInput(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    instalments: int | None = Field(default=None, ge=1, le=24)
    extension_days: int | None = Field(default=None, ge=0, le=730)


class ApproveInput(BaseModel):
    body_hash: str = Field(min_length=64, max_length=64)


def _invoice(db: Session, invoice_id: int, identity: Identity):
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id or invoice.invoice_type != "AR":
        raise HTTPException(status_code=404, detail="Case not found")
    return invoice


def _session(db: Session, invoice_id: int, identity: Identity):
    invoice = _invoice(db, invoice_id, identity)
    session = db.query(models.NegotiationSession).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Negotiation is not configured")
    return invoice, session


def _audit(db, identity, invoice_id, action, detail=""):
    db.add(models.AuditEvent(tenant_id=identity.tenant_id, actor=identity.actor,
        action=action, entity_type="invoice", entity_id=str(invoice_id), details=detail))


def _state(db, invoice, session):
    turns = db.query(models.NegotiationTurn).filter_by(session_id=session.id,
        tenant_id=session.tenant_id).order_by(models.NegotiationTurn.id).all()
    return {"invoice_id": invoice.id, "mode": session.mode, "status": session.status,
            "round_count": session.round_count,
            "bounds": {"max_instalments": session.max_instalments,
                       "max_extension_days": session.max_extension_days,
                       "min_first_percent": session.min_first_percent,
                       "settlement_discount_allowed": session.settlement_discount_allowed,
                       "max_ai_rounds": session.max_ai_rounds},
            "balance": split_balance(db, invoice),
            "transcript": [{"id": turn.id, "direction": turn.direction,
                            "actor": turn.actor, "body": turn.body,
                            "body_hash": turn.body_hash, "status": turn.status,
                            "supersedes_id": turn.supersedes_id} for turn in turns]}


@router.put("/cases/{invoice_id}")
def configure(invoice_id: int, payload: SettingsInput, db: Session = Depends(get_db),
              identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    session = db.query(models.NegotiationSession).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).first()
    old_mode = session.mode if session else None
    if not session:
        session = models.NegotiationSession(tenant_id=identity.tenant_id,
            invoice_id=invoice_id)
        db.add(session)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(session, key, value)
    session.status = "active"
    db.flush()
    _audit(db, identity, invoice_id, "negotiation_handover" if old_mode and old_mode != payload.mode
           else "negotiation_configured", f"{old_mode or 'new'}->{payload.mode}")
    db.commit()
    return _state(db, invoice, session)


@router.get("/cases/{invoice_id}")
def get_case(invoice_id: int, db: Session = Depends(get_db),
             identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    session = db.query(models.NegotiationSession).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).first()
    if not session:
        return {"invoice_id": invoice.id, "configured": False,
                "mode": "manual", "status": "not_started", "round_count": 0,
                "bounds": {"max_instalments": 3, "max_extension_days": 30,
                           "min_first_percent": 30, "settlement_discount_allowed": False,
                           "max_ai_rounds": 3}, "balance": split_balance(db, invoice),
                "transcript": []}
    return _state(db, invoice, session)


@router.post("/cases/{invoice_id}/copilot")
def copilot(invoice_id: int, db: Session = Depends(get_db),
            identity: Identity = Depends(get_identity)):
    invoice, session = _session(db, invoice_id, identity)
    if session.mode != "manual" or session.status != "active":
        raise HTTPException(status_code=409, detail="Co-pilot suggestions require an active Manual case")
    latest = db.query(models.NegotiationTurn).filter_by(session_id=session.id,
        direction="inbound").order_by(models.NegotiationTurn.id.desc()).first()
    if latest:
        safe_kind = negotiation.classify_inbound(latest.body)
        if safe_kind in ("injection", "anger", "legal_threat", "dispute", "ambiguous"):
            return {"suggestions": [], "escalation": safe_kind}
        if gemini_agent.configured():
            try:
                model_kind = gemini_agent.classify_intent(latest.body, role="copilot")
                if model_kind in ("injection", "anger", "legal_threat", "dispute", "ambiguous"):
                    return {"suggestions": [], "escalation": model_kind}
            except (RuntimeError, httpx.HTTPError, ValueError):
                pass
    suggestions = []
    for round_number in range(1, min(3, session.max_ai_rounds) + 1):
        offer = negotiation.offer_ladder(db, invoice, session, round_number)
        body = negotiation.phrase_offer(invoice, offer)
        allowed, reason = negotiation.guard_outbound(body, offer["disputed_cents"], offer["undisputed_cents"])
        if not allowed:
            raise HTTPException(status_code=409, detail=reason)
        suggestions.append({"body": body, "offer": offer, "engine": "rules_fallback"})
    return {"suggestions": suggestions}


@router.post("/cases/{invoice_id}/manual/send")
def manual_send(invoice_id: int, payload: BodyInput, db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    invoice, session = _session(db, invoice_id, identity)
    if session.mode != "manual" or session.status != "active":
        raise HTTPException(status_code=409, detail="Take over an active case before staff sends")
    split = split_balance(db, invoice)
    allowed, reason = negotiation.guard_outbound(payload.body, split["disputed_cents"], split["undisputed_cents"])
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    warnings = []
    if payload.instalments and payload.instalments > session.max_instalments:
        warnings.append("Staff instalment count exceeds AI bounds")
    if payload.extension_days and payload.extension_days > session.max_extension_days:
        warnings.append("Staff extension exceeds AI bounds")
    turn = models.NegotiationTurn(tenant_id=identity.tenant_id,
        session_id=session.id, direction="outbound", actor=identity.actor,
        body=payload.body, body_hash=negotiation.body_hash(payload.body),
        status="sandbox_sent", approved_by=identity.actor)
    db.add(turn)
    db.flush()
    _audit(db, identity, invoice_id, "manual_message_sandbox_sent",
           f"turn_id={turn.id}; warnings={len(warnings)}")
    db.commit()
    return {"turn_id": turn.id, "status": "sandbox_sent", "warnings": warnings,
            "channel": "SIMULATED sandbox outbox"}


@router.post("/cases/{invoice_id}/delegate/step")
def delegate_step(invoice_id: int, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    invoice, session = _session(db, invoice_id, identity)
    if session.mode != "delegate" or session.status != "active":
        raise HTTPException(status_code=409, detail="AI negotiation is not active")
    if db.query(models.NegotiationTurn).filter_by(session_id=session.id,
        status="pending_approval").first():
        raise HTTPException(status_code=409, detail="Approve the pending offer before preparing another")
    if session.round_count >= session.max_ai_rounds:
        session.status = "escalated"
        _audit(db, identity, invoice_id, "negotiation_escalated", "max rounds")
        db.commit()
        return _state(db, invoice, session)
    try:
        offer = negotiation.offer_ladder(db, invoice, session, session.round_count + 1)
    except ValueError as exc:
        session.status = "escalated"
        _audit(db, identity, invoice_id, "negotiation_escalated", str(exc))
        db.commit()
        return _state(db, invoice, session)
    body = negotiation.phrase_offer(invoice, offer)
    allowed, reason = negotiation.guard_outbound(body, offer["disputed_cents"], offer["undisputed_cents"])
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    policy = db.get(models.AgentPolicy, identity.tenant_id)
    auto_sandbox = bool(policy and policy.autonomy_mode == "auto_send_sandbox")
    turn = models.NegotiationTurn(tenant_id=identity.tenant_id,
        session_id=session.id, direction="outbound", actor="negotiator_agent",
        body=body, body_hash=negotiation.body_hash(body),
        status="sandbox_sent" if auto_sandbox else "pending_approval")
    db.add(turn)
    session.round_count += 1
    db.flush()
    _audit(db, identity, invoice_id, "negotiation_offer_prepared",
           f"round={session.round_count}; status={turn.status}; turn_id={turn.id}")
    db.commit()
    return {"turn_id": turn.id, "body": body, "offer": offer,
            "status": turn.status, "channel": "SIMULATED sandbox outbox"}


@router.post("/cases/{invoice_id}/turns/{turn_id}/approve")
def approve_turn(invoice_id: int, turn_id: int, payload: ApproveInput,
                 db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    _, session = _session(db, invoice_id, identity)
    turn = db.get(models.NegotiationTurn, turn_id)
    if not turn or turn.session_id != session.id or turn.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Current draft version is not pending approval")
    if turn.body_hash != payload.body_hash:
        raise HTTPException(status_code=409, detail="Draft version hash changed")
    turn.status = "sandbox_sent"
    turn.approved_by = identity.actor
    _audit(db, identity, invoice_id, "negotiation_version_approved",
           f"turn_id={turn.id}; hash={turn.body_hash}")
    db.commit()
    return {"turn_id": turn.id, "status": turn.status, "channel": "SIMULATED sandbox outbox"}


@router.post("/cases/{invoice_id}/turns/{turn_id}/edit")
def edit_turn(invoice_id: int, turn_id: int, payload: BodyInput,
              db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    invoice, session = _session(db, invoice_id, identity)
    old = db.get(models.NegotiationTurn, turn_id)
    if not old or old.session_id != session.id or old.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Only pending drafts can be edited")
    split = split_balance(db, invoice)
    allowed, reason = negotiation.guard_outbound(payload.body,
        split["disputed_cents"], split["undisputed_cents"])
    if not allowed:
        raise HTTPException(status_code=409, detail=reason)
    old.status = "superseded"
    new = models.NegotiationTurn(tenant_id=identity.tenant_id,
        session_id=session.id, direction="outbound", actor=identity.actor,
        body=payload.body, body_hash=negotiation.body_hash(payload.body),
        supersedes_id=old.id, status="pending_approval")
    db.add(new)
    db.flush()
    _audit(db, identity, invoice_id, "negotiation_version_edited",
           f"old={old.id}; new={new.id}")
    db.commit()
    return {"turn_id": new.id, "body_hash": new.body_hash, "status": new.status}


@router.post("/cases/{invoice_id}/incoming")
def simulated_incoming(invoice_id: int, payload: BodyInput,
                       db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    invoice, session = _session(db, invoice_id, identity)
    kind = negotiation.classify_inbound(payload.body)
    classifier = "rules_fallback"
    if kind not in ("injection", "anger", "legal_threat", "dispute") and gemini_agent.configured():
        try:
            model_kind = gemini_agent.classify_intent(payload.body, role="intent")
            classifier = settings.AGENT_MODEL
            if model_kind in ("injection", "anger", "legal_threat", "dispute"):
                kind = model_kind  # The model may only increase scrutiny.
        except (RuntimeError, httpx.HTTPError, ValueError):
            pass
    turn = models.NegotiationTurn(tenant_id=identity.tenant_id,
        session_id=session.id, direction="inbound", actor="SIMULATED customer",
        body=payload.body, body_hash=negotiation.body_hash(payload.body), status=kind)
    db.add(turn)
    if kind in ("injection", "anger", "legal_threat", "ambiguous", "dispute"):
        session.status = "escalated"
    db.flush()
    _audit(db, identity, invoice_id, "simulated_customer_message",
           f"turn_id={turn.id}; classification={kind}; classifier={classifier}")
    db.commit()
    return {"turn_id": turn.id, "classification": kind, "status": session.status,
            "case_status": invoice.status, "source": "SIMULATED customer",
            "classifier": classifier}


@router.post("/cases/{invoice_id}/{action}")
def control(invoice_id: int, action: Literal["pause", "take-over", "stop"],
            db: Session = Depends(get_db), identity: Identity = Depends(get_identity)):
    invoice, session = _session(db, invoice_id, identity)
    if action == "pause":
        session.status = "paused"
    elif action == "take-over":
        session.mode = "manual"
        session.status = "active"
    else:
        session.status = "stopped"
    _audit(db, identity, invoice_id, "negotiation_" + action,
           f"mode={session.mode}; status={session.status}")
    db.commit()
    return _state(db, invoice, session)
