"""Owner action queue: the single next action per case, tenant-wide.

Derived deterministically from stored state (flags, proposals, approvals,
clarifications, explanations, promises, uploads). Read-only; acting stays
with the existing staff endpoints.
"""
from datetime import date, timedelta


def _entry(invoice, outstanding, action, reason, owner, deadline, affected_cents,
           uncertainty, source, approval_required):
    return {"invoice_id": invoice.id, "invoice_number": invoice.invoice_number,
            "customer": invoice.counterparty_name, "action": action, "reason": reason,
            "owner": owner, "deadline": deadline.isoformat() if deadline else None,
            "affected_cents": affected_cents, "outstanding_cents": outstanding,
            "uncertainty": uncertainty, "source": source,
            "approval_required": approval_required}


def next_action(db, invoice):
    """Return the next action dict for one case, or None when steady."""
    from app.database import models
    from app.services.receivables import split_balance
    split = split_balance(db, invoice, allow_inconsistent=True)
    outstanding = split["outstanding_cents"]
    tenant, iid = invoice.tenant_id, invoice.id
    if split["reconciliation_error"] or invoice.requires_human_review \
            or invoice.investigation_hold:
        return _entry(invoice, outstanding, "Complete staff review",
                      invoice.investigation_reason or "Case math or evidence needs review",
                      "staff", date.today() + timedelta(days=2), outstanding,
                      ["amounts frozen until review"], "case flags", False)
    ambiguous = db.query(models.AllocationProposal).join(
        models.AllocationLeg,
        models.AllocationLeg.proposal_id == models.AllocationProposal.id).filter(
        models.AllocationProposal.tenant_id == tenant,
        models.AllocationProposal.status == "ambiguous",
        models.AllocationLeg.invoice_id == iid,
        models.AllocationLeg.status == "pending").first()
    if ambiguous:
        return _entry(invoice, outstanding, "Choose allocation legs",
                      f"Transfer {ambiguous.afis_transaction_id} matches ambiguously",
                      "staff", date.today() + timedelta(days=2),
                      ambiguous.transfer_cents, ["multiple candidate invoices"],
                      f"allocation proposal {ambiguous.id}", True)
    clarification = db.query(models.ClarificationTask).filter_by(
        tenant_id=tenant, invoice_id=iid, status="open").order_by(
        models.ClarificationTask.due_date).first()
    if clarification:
        return _entry(invoice, outstanding, clarification.title,
                      f"One missing fact blocks the case ({clarification.key})",
                      clarification.owner, clarification.due_date,
                      clarification.affected_cents,
                      ["decision blocked until supplied"], "clarification task", False)
    proposal = db.query(models.AgentProposal).filter_by(
        tenant_id=tenant, invoice_id=iid, status="proposed").order_by(
        models.AgentProposal.id).first()
    if proposal:
        return _entry(invoice, outstanding, "Approve the exact draft",
                      f"Proposal {proposal.id} awaits exact-version approval",
                      "staff", date.today() + timedelta(days=1), outstanding,
                      ["draft goes stale if the case changes"], "agent proposal", True)
    campaign = db.query(models.DunningCampaign).filter_by(
        tenant_id=tenant, invoice_id=iid, status="draft").order_by(
        models.DunningCampaign.id).first()
    if campaign:
        return _entry(invoice, outstanding, "Approve the collection draft",
                      f"Stage {campaign.campaign_stage} draft awaits approval",
                      "staff", date.today() + timedelta(days=1), outstanding,
                      ["draft goes stale if the balance changes"],
                      "dunning campaign", True)
    explanation = db.query(models.CompetingExplanation).filter_by(
        tenant_id=tenant, invoice_id=iid, status="open").order_by(
        models.CompetingExplanation.id).first()
    if explanation:
        return _entry(invoice, outstanding, "Resolve competing explanations",
                      f"{explanation.identity or 'item'} has conflicting hypotheses",
                      "staff", date.today() + timedelta(days=2), outstanding,
                      ["no confident auto-resolution"], "competing explanation", False)
    broken = db.query(models.PromiseToPay).filter_by(
        tenant_id=tenant, invoice_id=iid, status="broken").order_by(
        models.PromiseToPay.promised_date).first()
    if broken:
        return _entry(invoice, outstanding, "Follow up a broken promise",
                      f"Promised {broken.promised_cents} cents did not arrive",
                      "staff", date.today() + timedelta(days=1), broken.promised_cents,
                      ["customer commitment failed"], "promise record", False)
    due = db.query(models.PromiseToPay).filter(
        models.PromiseToPay.tenant_id == tenant,
        models.PromiseToPay.invoice_id == iid,
        models.PromiseToPay.status == "confirmed",
        models.PromiseToPay.promised_date <= date.today() + timedelta(days=7)).first()
    if due:
        return _entry(invoice, outstanding, "Monitor a due promise",
                      f"Promised {due.promised_cents} cents falls due {due.promised_date}",
                      "staff", due.promised_date, due.promised_cents,
                      ["nonfinancial until cash arrives"], "promise record", False)
    return None


def queue_for_tenant(db, tenant_id):
    """All cases with a next action, earliest deadline first."""
    from app.database import models
    items = []
    for invoice in db.query(models.Invoice).filter_by(
            tenant_id=tenant_id, invoice_type="AR").all():
        action = next_action(db, invoice)
        if action:
            items.append(action)
    items.sort(key=lambda item: (item["deadline"] or "9999-12-31",
                                 -item["affected_cents"]))
    return items
