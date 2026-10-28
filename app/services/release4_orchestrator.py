"""Server-owned matching, investigation and unsent draft preparation."""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from app.database import models
from app.services import controlled_agent, negotiation
from app.services.receivables import split_balance


from app.services.investigation import investigate


def prepare_draft(db, invoice):
    """Create a reviewable versioned draft from ledger math and linked evidence."""
    if invoice.due_date >= date.today() or invoice.contact_opt_out or invoice.contact_suppressed:
        raise ValueError("Case is not eligible for an overdue collection draft")
    if invoice.investigation_hold:
        raise ValueError(invoice.investigation_reason or "Investigation requires staff review")
    evidence = db.query(models.CaseEvidence).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).all()
    if not any(row.claim_type == "invoice_total" and row.source_reference for row in evidence):
        raise ValueError("Invoice amount has no clickable source")
    split = split_balance(db, invoice)
    if split["undisputed_cents"] <= 0:
        raise ValueError("No undisputed balance remains")
    if split["received_cents"] and not any(
        row.claim_type == "received_payment" and row.source_reference for row in evidence):
        raise ValueError("Received amount has no clickable source")
    if split["disputed_cents"] and not any(
        row.claim_type == "dispute_item" and row.source_reference for row in evidence):
        raise ValueError("Disputed amount has no clickable source")
    facts, digest, _ = controlled_agent.snapshot(db, invoice)
    prior = db.query(models.AgentProposal).filter_by(tenant_id=invoice.tenant_id,
        invoice_id=invoice.id, context_hash=digest).first()
    if prior:
        return prior
    body = (f"Regarding invoice {invoice.invoice_number}, please arrange payment of the "
            f"undisputed {negotiation.money(split['undisputed_cents'])}.")
    if split["disputed_cents"]:
        body += (f" The disputed {negotiation.money(split['disputed_cents'])} remains "
                 "open for review and is not part of this request.")
    allowed, reason = negotiation.guard_outbound(body, split["disputed_cents"], split["undisputed_cents"])
    if not allowed:
        raise ValueError(reason)
    proposal = models.AgentProposal(tenant_id=invoice.tenant_id,
        invoice_id=invoice.id, context_hash=digest, engine="rules_fallback",
        summary="Source-linked invoice ready for staff review",
        rationale="Only the server-calculated undisputed balance is requested",
        action="split_balance_draft", draft_text=body, status="proposed",
        risk_flags="[]", balance_cents_at_proposal=split["outstanding_cents"])
    db.add(proposal)
    db.flush()
    version = models.ProposalDraftVersion(tenant_id=invoice.tenant_id,
        proposal_id=proposal.id, version_number=1, body=body,
        edited_by="drafter_agent", change_reason="Initial source-linked draft",
        version_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(), status="draft")
    db.add(version)
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor="drafter_agent",
        action="source_linked_draft_prepared", entity_type="agent_proposal",
        entity_id=str(proposal.id),
        details=f"undisputed_cents={split['undisputed_cents']}; disputed_cents={split['disputed_cents']}; engine=rules_fallback"))
    policy = db.get(models.AgentPolicy, invoice.tenant_id)
    high_confidence = (not invoice.requires_human_review and not split["disputed_cents"] and
        any(row.claim_type == "invoice_total" and row.verified for row in evidence))
    if policy and policy.autonomy_mode == "auto_send_sandbox" and high_confidence:
        db.add(models.SandboxOutbox(tenant_id=invoice.tenant_id,
            invoice_id=invoice.id, proposal_id=proposal.id, body=body,
            body_hash=version.version_hash, channel="SIMULATED sandbox outbox"))
        proposal.status = "sandbox_sent"
        db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor="policy_guard",
            action="draft_auto_sandbox_queued", entity_type="agent_proposal",
            entity_id=str(proposal.id), details=f"hash={version.version_hash}"))
    db.flush()
    return proposal
