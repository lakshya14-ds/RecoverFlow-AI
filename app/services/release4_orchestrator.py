"""Server-owned matching, investigation and unsent draft preparation."""
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re

from app.database import models
from app.services import controlled_agent, negotiation
from app.services.receivables import split_balance


def _source(job):
    return f"/api/v1/intake/uploads/{job.id}/file"


def _linked_documents(db, invoice):
    rows = db.query(models.IntakeUpload).filter_by(tenant_id=invoice.tenant_id).filter(
        models.IntakeUpload.extraction_json.isnot(None)).all()
    linked = []
    for row in rows:
        try:
            doc = json.loads(row.extraction_json)
        except (TypeError, ValueError):
            continue
        if (doc.get("invoice_reference") == invoice.invoice_number or
            (doc.get("invoice_number") == invoice.invoice_number and
             row.source_path == invoice.source_path)):
            linked.append((row, doc))
    return linked


def investigate(db, invoice) -> int:
    """Only propose a dispute when independent source lines verify its arithmetic."""
    linked = _linked_documents(db, invoice)
    invoice_doc = next((doc for row, doc in linked if row.source_path == invoice.source_path
                        and doc.get("document_type") == "invoice"), None)
    invoice_lines = invoice_doc.get("line_items", []) if invoice_doc else []
    proposed = []
    for row, doc in linked:
        if doc.get("document_type") == "purchase_order" and invoice_lines:
            po_lines = {re.sub(r"\W+", " ", item.get("description", "").lower()).strip(): item
                        for item in doc.get("line_items", [])}
            delta = Decimal(0)
            for item in invoice_lines:
                name = re.sub(r"\W+", " ", item.get("description", "").lower()).strip()
                other = po_lines.get(name)
                if other:
                    try:
                        difference = Decimal(item["amount"]) - Decimal(other["amount"])
                    except (InvalidOperation, KeyError):
                        continue
                    delta += max(Decimal(0), difference)
            if delta > 0:
                proposed.append((int(delta * 100), row, "PO line-item mismatch"))
        if doc.get("document_type") == "message" and invoice_lines:
            text = doc.get("text", "")
            short = re.search(r"(?:short\s+by\s+|missing\s+)(\d+)\s+units|(?:\b(\d+)\s+units\s+short)",
                              text, re.IGNORECASE)
            priced = [line for line in invoice_lines if line.get("unit_price") and line.get("quantity")]
            if short and len(priced) == 1:
                missing = int(short.group(1) or short.group(2))
                quantity = Decimal(priced[0]["quantity"])
                if 0 < missing <= quantity:
                    delta = Decimal(missing) * Decimal(priced[0]["unit_price"])
                    proposed.append((int(delta * 100), row, "Claimed delivery shortfall at invoice unit price"))
    if proposed:
        amounts = {item[0] for item in proposed}
        if len(amounts) != 1:
            raise ValueError("Dispute sources disagree; staff review required")
        amount = amounts.pop()
        outstanding = split_balance(db, invoice)["outstanding_cents"]
        if amount > outstanding:
            raise ValueError("Proposed dispute exceeds outstanding balance")
        invoice.disputed_cents = amount
        invoice.dispute_open = True
        invoice.status = "disputed"
        row = proposed[0][1]
        existing = db.query(models.CaseEvidence).filter_by(
            invoice_id=invoice.id, tenant_id=invoice.tenant_id,
            claim_type="dispute_item", source_reference=_source(row)).first()
        if not existing:
            db.add(models.CaseEvidence(tenant_id=invoice.tenant_id,
                invoice_id=invoice.id, claim_type="dispute_item",
                title="Proposed disputed line item", description=proposed[0][2],
                source_type="uploaded_" + json.loads(row.extraction_json)["document_type"],
                source_reference=_source(row), amount_cents=amount, verified=False))
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor="investigator_agent",
        action="case_investigated", entity_type="invoice", entity_id=str(invoice.id),
        details=f"linked_sources={len(linked)}; proposed_dispute_cents={invoice.disputed_cents or 0}"))
    db.flush()
    return int(invoice.disputed_cents or 0)


def prepare_draft(db, invoice):
    """Create a reviewable versioned draft from ledger math and linked evidence."""
    if invoice.due_date >= date.today() or invoice.contact_opt_out or invoice.contact_suppressed:
        raise ValueError("Case is not eligible for an overdue collection draft")
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
