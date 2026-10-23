"""Release 3 controlled agent: deterministic decisions, optional Gemini wording, bounded internal work."""
import hashlib
import json
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth import Identity
from app.config import settings
from app.database import models
from app.services import gemini_agent
from app.services.receivables import balance_cents

logger = logging.getLogger(__name__)


def utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _conversation(db: Session, invoice: models.Invoice) -> tuple[list[dict], models.InboundMessage | None]:
    inbound = db.query(models.InboundMessage).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).order_by(
        models.InboundMessage.received_at.desc()).limit(12).all()
    recorded = db.query(models.CustomerMessage).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).order_by(
        models.CustomerMessage.created_at.desc()).limit(12).all()
    sent = db.query(models.OutboundMessage).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).order_by(
        models.OutboundMessage.created_at.desc()).limit(12).all()
    items = []
    for row in inbound:
        items.append({"id": f"in:{row.id}", "at": row.received_at.isoformat(),
                      "direction": "customer", "status": row.status,
                      "text": row.body[:500]})
    for row in recorded:
        if row.actor.startswith("meta_whatsapp:"):
            continue
        items.append({"id": f"recorded:{row.id}", "at": row.created_at.isoformat(),
                      "direction": "customer", "category": row.category,
                      "text": row.body[:500]})
    for row in sent:
        if row.status != "sent":
            continue
        items.append({"id": f"out:{row.id}", "at": row.created_at.isoformat(),
                      "direction": "staff", "text": row.body[:500]})
    items.sort(key=lambda item: item["at"])
    return items[-20:], inbound[0] if inbound else None


def snapshot(db: Session, invoice: models.Invoice) -> tuple[dict, str, models.InboundMessage | None]:
    messages, latest = _conversation(db, invoice)
    balance = balance_cents(db, invoice)
    facts = {
        "invoice_id": invoice.id, "invoice_number": invoice.invoice_number[:80],
        "status": invoice.status, "balance_cents": balance,
        "currency": invoice.currency, "due_date": invoice.due_date.isoformat(),
        "source_system": invoice.source_system,
        "contact_suppressed": bool(invoice.contact_suppressed),
        "contact_opt_out": bool(invoice.contact_opt_out),
        "dispute_open": bool(invoice.dispute_open),
        "requires_human_review": bool(invoice.requires_human_review),
        "messages": messages,
    }
    # Include campaign state so an executed draft invalidates old proposals.
    facts["campaigns"] = [{"id": row.id, "stage": row.campaign_stage,
                           "status": row.status} for row in db.query(models.DunningCampaign).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).order_by(
        models.DunningCampaign.id.desc()).limit(10).all()]
    digest = hashlib.sha256(json.dumps(facts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return facts, digest, latest


def _choice(db: Session, invoice: models.Invoice, facts: dict,
            latest: models.InboundMessage | None) -> tuple[str, list[str]]:
    flags = []
    if facts["balance_cents"] <= 0 or invoice.status == "paid":
        flags.append("no_outstanding_balance")
    if invoice.contact_opt_out:
        flags.append("customer_opted_out")
    if invoice.dispute_open or invoice.status == "disputed":
        flags.append("open_dispute")
    if invoice.requires_human_review:
        flags.append("case_review_required")
    if invoice.contact_suppressed:
        flags.append("contact_paused")
    if invoice.source_system == "shopify" and settings.RAZORPAY_KEY_ID.startswith("rzp_test_mock"):
        flags.append("mock_payment_environment")
    blocking = {"no_outstanding_balance", "customer_opted_out", "open_dispute",
                "case_review_required"}
    if set(flags) & blocking:
        return "staff_review" if flags[0] != "no_outstanding_balance" else "no_action", flags
    latest_at = (latest.received_at.replace(tzinfo=timezone.utc)
                 if latest and latest.received_at.tzinfo is None else
                 latest.received_at if latest else None)
    if latest and (invoice.contact_suppressed or
                   datetime.now(timezone.utc) - latest_at < timedelta(hours=24)):
        category = db.query(models.CustomerMessage.category).filter_by(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id,
            actor="meta_whatsapp:" + latest.external_id).scalar()
        if latest.status == "triaged" and category in ("question", "needs_time"):
            if datetime.now(timezone.utc) - latest_at < timedelta(hours=24):
                return "reply_draft", flags
        return "staff_review", flags + ["inbound_needs_review"]
    if invoice.contact_suppressed:
        return "staff_review", flags
    from app.api.dunning import _check_contact, _check_recent_contact
    try:
        _check_contact(db, invoice)
        _check_recent_contact(db, invoice)
    except HTTPException:
        return "no_action", flags + ["collection_gate_active"]
    if _eligible_collection_stage(db, invoice) is not None:
        return "collection_draft", flags
    return "no_action", flags


def _eligible_collection_stage(db: Session, invoice: models.Invoice) -> int | None:
    days = (date.today() - invoice.due_date).days
    collection = db.get(models.CollectionPolicy, invoice.tenant_id)
    thresholds = ((collection.stage1_days, collection.stage2_days,
                   collection.stage3_days, collection.stage4_days)
                  if collection and collection.enabled else
                  (settings.DUNNING_STAGE1_DAYS, settings.DUNNING_STAGE2_DAYS,
                   settings.DUNNING_STAGE3_DAYS, settings.DUNNING_STAGE4_DAYS))
    existing = db.query(models.DunningCampaign).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).all()
    if any(row.status in ("draft", "approved") for row in existing):
        return None
    return next((i for i in range(1, 5) if days >= thresholds[i - 1] and
                 not any(row.campaign_stage == i for row in existing)), None)


def _fallback(facts: dict, action: str) -> tuple[str, str, str]:
    balance = f"{facts['currency']} {facts['balance_cents'] / 100:.2f}"
    lines = [f"Invoice {facts['invoice_number']} has a ledger balance of {balance} and is {facts['status']}."]
    if facts["messages"]:
        last = facts["messages"][-1]
        lines.append(f"Latest {last['direction']} message: {last['text'][:200]}")
    rationale = {
        "no_action": "No routine collection action is currently eligible.",
        "staff_review": "A staff member must review the case before the next action.",
        "reply_draft": "The recent triaged customer question can receive a staff-approved acknowledgement.",
        "collection_draft": "The overdue receivable may receive an internal draft; sending still requires approval.",
    }[action]
    draft = ("Thank you for your message. Our team has received your question and "
             "will review the account before following up." if action == "reply_draft" else "")
    return " ".join(lines)[:1200], rationale, draft


def _daily_count(db: Session, model, tenant_id: str) -> int:
    today = utc_naive().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.query(model).filter(model.tenant_id == tenant_id,
                                  model.created_at >= today).count()


def assess(db: Session, tenant_id: str, invoice_id: int, actor: str,
           *, automatic: bool = False) -> models.AgentProposal:
    policy = db.get(models.AgentPolicy, tenant_id)
    if not policy or not policy.enabled or (automatic and not policy.auto_assess):
        raise HTTPException(status_code=409, detail="Controlled agent is not enabled")
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != tenant_id or invoice.invoice_type != "AR":
        raise HTTPException(status_code=404, detail="Receivable case not found")
    facts, digest, latest = snapshot(db, invoice)
    existing = db.query(models.AgentProposal).filter_by(
        tenant_id=tenant_id, invoice_id=invoice_id, context_hash=digest).first()
    if existing:
        return existing
    if _daily_count(db, models.AgentProposal, tenant_id) >= policy.max_assessments_per_day:
        raise HTTPException(status_code=429, detail="Daily agent assessment limit reached")
    action, flags = _choice(db, invoice, facts, latest)
    summary, rationale, reply = _fallback(facts, action)
    engine = "rules_only"
    if gemini_agent.configured():
        try:
            wording = gemini_agent.generate(facts, action)
            summary, rationale = wording.summary, wording.rationale
            if action == "reply_draft" and gemini_agent.safe_reply(wording.reply_draft):
                reply = wording.reply_draft
            engine = settings.AGENT_MODEL
        except Exception:
            logger.exception("Gemini assessment failed for invoice %s; using rules-only wording", invoice_id)
            flags.append("model_unavailable")
            engine = "rules_fallback"
    proposal = models.AgentProposal(
        tenant_id=tenant_id, invoice_id=invoice_id,
        inbound_id=latest.id if action == "reply_draft" and latest else None,
        context_hash=digest, engine=engine, summary=summary, rationale=rationale,
        action=action, draft_text=reply or None,
        status="closed" if action == "no_action" else "proposed",
        risk_flags=json.dumps(flags), balance_cents_at_proposal=facts["balance_cents"])
    db.add(proposal)
    db.flush()
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
                             action="agent_assessed", entity_type="agent_proposal",
                             entity_id=str(proposal.id), details=f"{engine}:{action}"))
    db.commit()
    db.refresh(proposal)
    if automatic and policy.auto_execute_internal and engine != "rules_fallback" and action != "no_action":
        try:
            execute_internal(db, proposal, "case_note", "controlled_agent")
            if action == "collection_draft":
                execute_internal(db, proposal, "collection_draft", "controlled_agent")
        except HTTPException as exc:
            logger.info("Agent internal action skipped for proposal %s: %s", proposal.id, exc.detail)
    return proposal


def _fresh(db: Session, proposal: models.AgentProposal) -> models.Invoice:
    invoice = db.get(models.Invoice, proposal.invoice_id)
    if not invoice or invoice.tenant_id != proposal.tenant_id:
        raise HTTPException(status_code=404, detail="Case not found")
    _, digest, _ = snapshot(db, invoice)
    if digest != proposal.context_hash:
        proposal.status = "stale"
        db.commit()
        raise HTTPException(status_code=409, detail="Case changed; request a new agent assessment")
    return invoice


def execute_internal(db: Session, proposal: models.AgentProposal, action: str,
                     actor: str) -> models.AgentExecution:
    if action not in ("case_note", "collection_draft"):
        raise HTTPException(status_code=422, detail="Only internal actions are allowed")
    if proposal.status in ("rejected", "stale", "closed"):
        raise HTTPException(status_code=409, detail="Proposal is not actionable")
    prior = db.query(models.AgentExecution).filter_by(
        tenant_id=proposal.tenant_id, proposal_id=proposal.id, action=action).first()
    if prior:
        return prior
    policy = db.get(models.AgentPolicy, proposal.tenant_id)
    if not policy or not policy.enabled:
        raise HTTPException(status_code=409, detail="Controlled agent is disabled")
    if actor == "controlled_agent" and not policy.auto_execute_internal:
        raise HTTPException(status_code=409, detail="Automatic internal actions are disabled")
    if actor == "controlled_agent" and _daily_count(
            db, models.AgentExecution, proposal.tenant_id) >= policy.max_internal_actions_per_day:
        raise HTTPException(status_code=429, detail="Daily internal action limit reached")
    invoice = _fresh(db, proposal)
    result_id = None
    if action == "case_note":
        note = models.AgentCaseNote(
            tenant_id=proposal.tenant_id, invoice_id=invoice.id, proposal_id=proposal.id,
            body=f"Automated summary; verify against source messages. {proposal.summary}"[:1500])
        db.add(note)
        db.flush()
        result_id = note.id
    else:
        if proposal.action != "collection_draft" or invoice.contact_suppressed or invoice.contact_opt_out or invoice.dispute_open or invoice.requires_human_review:
            raise HTTPException(status_code=409, detail="Case is not eligible for a collection draft")
        if proposal.balance_cents_at_proposal > policy.max_balance_cents:
            raise HTTPException(status_code=409, detail="Case balance exceeds the agent limit")
        from app.api.dunning import _check_contact, _check_recent_contact, trigger_dunning_stage
        _check_contact(db, invoice)
        _check_recent_contact(db, invoice)
        stage = _eligible_collection_stage(db, invoice)
        if stage is None:
            raise HTTPException(status_code=409, detail="No collection stage is eligible")
        trigger_dunning_stage(invoice.id, stage, db,
                              Identity(actor, proposal.tenant_id, "editor"))
        campaign = db.query(models.DunningCampaign).filter_by(
            tenant_id=proposal.tenant_id, invoice_id=invoice.id,
            campaign_stage=stage, status="draft").order_by(
            models.DunningCampaign.id.desc()).first()
        campaign.generated_by = f"controlled_agent:{proposal.id}"
        result_id = campaign.id
        proposal.status = "draft_created"
        proposal.executed_at = utc_naive()
    execution = models.AgentExecution(tenant_id=proposal.tenant_id,
        proposal_id=proposal.id, action=action, actor=actor, result_id=result_id)
    db.add(execution)
    db.add(models.AuditEvent(tenant_id=proposal.tenant_id, actor=actor,
        action="agent_" + action, entity_type="agent_proposal",
        entity_id=str(proposal.id), details=str(result_id)))
    db.commit()
    db.refresh(execution)
    return execution


def scan_enabled(db: Session) -> int:
    """Worker pass; explicit per-tenant opt-in and budget constrain AI calls."""
    count = 0
    for policy in db.query(models.AgentPolicy).filter_by(enabled=True, auto_assess=True).all():
        cases = db.query(models.Invoice).filter_by(
            tenant_id=policy.tenant_id, invoice_type="AR").order_by(
            models.Invoice.updated_at.desc()).limit(50).all()
        for invoice in cases:
            try:
                before = db.query(models.AgentProposal).filter_by(
                    tenant_id=policy.tenant_id, invoice_id=invoice.id).count()
                assess(db, policy.tenant_id, invoice.id, "controlled_agent", automatic=True)
                after = db.query(models.AgentProposal).filter_by(
                    tenant_id=policy.tenant_id, invoice_id=invoice.id).count()
                count += after - before
            except HTTPException as exc:
                if exc.status_code == 429:
                    break
                logger.info("Agent skipped invoice %s: %s", invoice.id, exc.detail)
            except Exception:
                db.rollback()
                logger.exception("Controlled agent assessment failed for invoice %s", invoice.id)
    return count
