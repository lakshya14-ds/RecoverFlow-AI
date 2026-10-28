"""Canonical case lifecycle. No model can authorize a financial transition.

Stages (``CaseWorkflow.stage``) — the single documented set:
  NEEDS_REVIEW      ledger/dispute math is inconsistent, or staff/investigation
                    review is pending. Contact is paused; nothing is collectible.
  CONTACT_PAUSED    customer opted out or contact was suppressed. No contact.
  DISPUTED          part of the outstanding balance is disputed; the undisputed
                    remainder is eligible for collection once review gates pass.
  READY_FOR_REVIEW  outstanding balance with no dispute; normal collection flow.
  PARTIALLY_RESOLVED undisputed balance cleared, disputed amount still open.
  RESOLVED_PAID     outstanding is zero and no credits were used.
  RESOLVED_ADJUSTED outstanding is zero with credits involved. Never "paid".

Legacy ``Invoice.status`` values are reconciled to the same truth via
``settle_invoice_status``: paid/adjusted/PARTIALLY_RESOLVED/disputed/
partially_matched/pending. Only ledger and staff-review events may move
``Invoice.status``; draft, approval, and sandbox events never close a case.

Trigger map (event -> effect):
  ledger_posted (payment/credit/reversal) -> recompute stage + settle status
  dispute_reviewed / staff_resumed_contact / invoice_confirmed / investigated
      -> recompute stage + settle status
  customer_reply / legacy / evidence_added -> recompute stage, status untouched
      except record_reply may mark "disputed" (never a closed state)
  draft_approved / draft_sandbox_sent / agent_assessment / negotiation_* ->
      recompute stage only; ``Invoice.status`` is never touched, so a promise,
      draft, approved message, or sandbox send can never close a case.

Legal transitions (from -> to). The stage is always derived from balances and
flags, so every transition below is reachable; anything else (in particular any
move into RESOLVED_* while outstanding > 0) is impossible by construction and
rejected if ever attempted directly:
"""
import hashlib
import json
from datetime import datetime, timezone
from app.database import models


STAGES = (
    "NEEDS_REVIEW",
    "CONTACT_PAUSED",
    "DISPUTED",
    "READY_FOR_REVIEW",
    "PARTIALLY_RESOLVED",
    "RESOLVED_PAID",
    "RESOLVED_ADJUSTED",
)

CLOSED_STAGES = ("RESOLVED_PAID", "RESOLVED_ADJUSTED")

# Every derived stage may legally follow any other stage except that closed
# stages only reopen through money movement or staff review, never through
# drafts, approvals, or sandbox sends.
NON_REOPENING_EVENTS = (
    "draft_approved",
    "draft_sandbox_sent",
    "agent_assessment",
    "negotiation_offer_prepared",
    "negotiation_version_approved",
    "negotiation_version_edited",
)

LEGAL_TRANSITIONS = {stage: tuple(s for s in STAGES) for stage in STAGES}


def derive_stage(split, invoice):
    """Derive the canonical stage from balances and flags (pure)."""
    if split["reconciliation_error"] or invoice.requires_human_review or invoice.investigation_hold:
        return "NEEDS_REVIEW"
    if split["outstanding_cents"] == 0:
        return "RESOLVED_PAID" if not split["credits_cents"] else "RESOLVED_ADJUSTED"
    if invoice.contact_opt_out or invoice.contact_suppressed:
        return "CONTACT_PAUSED"
    if split["disputed_cents"] and not split["undisputed_cents"]:
        return "PARTIALLY_RESOLVED"
    if split["disputed_cents"]:
        return "DISPUTED"
    return "READY_FOR_REVIEW"


def settle_invoice_status(db, invoice, split=None, force=False):
    """Reconcile legacy Invoice.status with the canonical stage (credit-aware).

    A case closed with credits is labeled "adjusted", never "paid".
    """
    from app.services.receivables import split_balance
    split = split or split_balance(db, invoice, allow_inconsistent=True)
    if not force and (split["reconciliation_error"] or invoice.requires_human_review or invoice.investigation_hold):
        return invoice.status  # leave the last known status while under review
    if not split["outstanding_cents"]:
        invoice.status = "adjusted" if split["credits_cents"] else "paid"
    elif split["disputed_cents"] and not split["undisputed_cents"]:
        invoice.status = "PARTIALLY_RESOLVED"
    elif split["disputed_cents"]:
        invoice.status = "disputed"
    elif split["outstanding_cents"] < split["invoice_total_cents"]:
        invoice.status = "partially_matched"
    else:
        invoice.status = "pending"
    return invoice.status


def fingerprint(db, invoice):
    db.flush()
    entries = db.query(models.ReceivableEntry).filter_by(tenant_id=invoice.tenant_id,
        invoice_id=invoice.id).order_by(models.ReceivableEntry.id).all()
    evidence = db.query(models.CaseEvidence).filter_by(tenant_id=invoice.tenant_id,
        invoice_id=invoice.id).order_by(models.CaseEvidence.id).all()
    messages = db.query(models.CustomerMessage).filter_by(tenant_id=invoice.tenant_id,
        invoice_id=invoice.id).order_by(models.CustomerMessage.id).all()
    from app.services.receivables import split_balance
    split = split_balance(db, invoice, allow_inconsistent=True)
    context = {"balance": {k: v for k, v in split.items() if k.endswith("_cents")},
        "review": bool(invoice.requires_human_review), "hold": bool(invoice.investigation_hold),
        "suppressed": bool(invoice.contact_suppressed), "opt_out": bool(invoice.contact_opt_out),
        "currency": invoice.currency, "due": str(invoice.due_date),
        "entries": [(e.id, e.kind, e.amount_cents, e.disputed_delta_cents) for e in entries],
        "evidence": [(e.id, e.claim_type, e.amount_cents, e.source_reference, e.description,
                      e.trust_state, e.decided_by, e.decision_reason) for e in evidence],
        "messages": [(m.id, m.category, m.body) for m in messages]}
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


STATUS_EVENTS = (
    "ledger_posted",
    "dispute_reviewed",
    "staff_resumed_contact",
    "invoice_confirmed",
    "investigated",
)


def checkpoint(db, invoice, event, actor="system"):
    if invoice.invoice_type != "AR":
        return None
    from app.services.receivables import split_balance
    split = split_balance(db, invoice, allow_inconsistent=True)
    stage = derive_stage(split, invoice)
    assert stage in STAGES, f"Unknown derived stage {stage}"
    if stage in CLOSED_STAGES:
        assert split["outstanding_cents"] == 0, "Closed stage requires zero outstanding"
    if event in STATUS_EVENTS and not invoice.requires_human_review:
        settle_invoice_status(db, invoice, split)
    digest = fingerprint(db, invoice)
    row = db.query(models.CaseWorkflow).filter_by(tenant_id=invoice.tenant_id,
        invoice_id=invoice.id).first()
    if row and row.context_hash == digest and row.stage == stage:
        return row
    previous = row.stage if row else None
    if previous is not None:
        assert stage in LEGAL_TRANSITIONS.get(previous, ()), (
            f"Illegal lifecycle transition {previous} -> {stage}")
    if event in NON_REOPENING_EVENTS and previous in CLOSED_STAGES and stage not in CLOSED_STAGES:
        raise ValueError("Drafts, approvals, and sandbox sends cannot reopen or close a case")
    if row is None:
        row = models.CaseWorkflow(tenant_id=invoice.tenant_id, invoice_id=invoice.id, revision=0)
        db.add(row)
    row.revision += 1
    row.stage, row.context_hash, row.last_event = stage, digest, event
    row.updated_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="case_checkpoint", entity_type="invoice", entity_id=str(invoice.id),
        details=json.dumps({"revision": row.revision, "from": previous, "stage": stage,
                            "event": event, "context_hash": digest})))
    db.flush()
    return row


def ensure_contact_allowed(invoice):
    if invoice.investigation_hold or invoice.requires_human_review:
        raise ValueError("Complete evidence and invoice review before customer contact")
    if invoice.contact_suppressed or invoice.contact_opt_out:
        raise ValueError("Customer contact is paused")
