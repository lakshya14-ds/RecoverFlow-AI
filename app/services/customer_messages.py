"""One recording path for customer messages, staff-typed or portal-submitted.

Both channels share the same semantics: injection screening, dispute and
opt-out flags, audit events, lifecycle checkpoint, and supervisor
reassessment. Recording a message never moves money.
"""
from datetime import datetime, timezone

from app.database import models
from app.services.case_lifecycle import checkpoint
from app.services.security import detect_prompt_injection


def record_customer_message(db, tenant_id, actor, invoice, category, body,
                            source="staff"):
    """Persist a customer message and its side effects. Caller commits."""
    is_inj, inj_reason = detect_prompt_injection(body)
    if is_inj:
        category = "untrusted_evidence"

    message = models.CustomerMessage(
        tenant_id=tenant_id,
        invoice_id=invoice.id,
        category=category,
        body=body,
        actor=actor,
        is_injection=is_inj,
        rejection_reason=inj_reason,
        source=source,
    )
    db.add(message)

    if is_inj:
        invoice.contact_suppressed = True
        invoice.requires_human_review = True
        db.add(models.AuditEvent(
            tenant_id=tenant_id,
            actor=actor,
            action="injection_attempt_blocked",
            entity_type="invoice",
            entity_id=str(invoice.id),
            details=inj_reason,
        ))
        # Record rejected claim: checked by policy, unusable for financial action.
        db.add(models.CaseEvidence(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            claim_type="untrusted_customer_message",
            title="Adversarial Injection Attempt Blocked",
            description=f"Customer attempted instruction override: {inj_reason}",
            source_type="customer_message",
            source_reference=f"MSG-{body[:20]}",
            source_snippet=body,
            verified=False,
            trust_state="rejected",
            decided_by=actor,
            decided_at=datetime.now(timezone.utc),
            decision_reason=inj_reason or "Policy rejected an instruction override",
            currency=invoice.currency or "INR",
        ))
    else:
        if category in ("paid_claim", "dispute", "opt_out"):
            invoice.contact_suppressed = True
        if category == "opt_out":
            invoice.contact_opt_out = True
        if category == "dispute":
            # A customer allegation reserves attention, never money: it marks the
            # case disputed and pauses contact; only staff review sets the amount.
            invoice.dispute_open = True
            invoice.status = "disputed"
        db.add(models.AuditEvent(
            tenant_id=tenant_id,
            actor=actor,
            action="customer_reply_recorded",
            entity_type="invoice",
            entity_id=str(invoice.id),
            details=category,
        ))

    checkpoint(db, invoice, "customer_reply", actor)
    from app.services.supervisor import request_reassessment
    request_reassessment(db, invoice, f"reply:{category}", actor)
    db.flush()
    return {
        "message_id": message.id,
        "is_injection": is_inj,
        "rejection_reason": inj_reason,
        "contact_suppressed": bool(invoice.contact_suppressed),
        "requires_human_review": bool(invoice.requires_human_review),
    }
