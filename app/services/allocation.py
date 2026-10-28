"""Candidate allocation of verified transfers across invoices.

Scoring is deterministic and explainable: every candidate carries reasons and
evidence. Nothing here posts to the ledger; staff approval posts each leg
through the existing post_entry path. AFIS transfers carry no tenant or
currency of their own, so proposals record both explicitly and legs can never
cross them.
"""
import json
from datetime import date
from decimal import Decimal

from app.database import models

CLEAR_SCORE = 0.65
CLEAR_MARGIN = 0.1
LEG_THRESHOLD = 0.5


def _cents(amount) -> int:
    return int((Decimal(str(amount)) * 100).to_integral_value())


def get_transfer(transfer_id: str):
    """Fetch one AFIS transfer by id (income side only for AR allocation)."""
    from app.plugins.afis_reader import AFISReader
    for txn in AFISReader().get_transactions("1900-01-01", "2100-12-31", tx_type="income",
                                             limit=100000):
        if str(txn.get("id")) == str(transfer_id):
            return txn
    return None


def unmatched_transfers(db, tenant_id, limit=100):
    """AFIS income transfers without a proposal in this tenant."""
    from app.plugins.afis_reader import AFISReader
    txns = AFISReader().get_transactions("1900-01-01", "2100-12-31", tx_type="income",
                                         limit=limit)
    known = {row[0] for row in db.query(
        models.AllocationProposal.afis_transaction_id).filter_by(tenant_id=tenant_id).all()}
    return [txn for txn in txns if str(txn.get("id")) not in known]


def _txn_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def score_candidates(db, tenant_id, txn, currency="INR"):
    """Score open invoices against one transfer. Pure reads, no writes."""
    from app.services.receivables import split_balance
    description = str(txn.get("description") or "")
    folded = description.casefold()
    transfer_cents = _cents(txn.get("amount") or 0)
    txn_day = _txn_date(txn.get("date"))
    aliases = {(a.alias or "").casefold(): a.counterparty_name
               for a in db.query(models.PayerAlias).filter_by(tenant_id=tenant_id).all()}
    invoices = db.query(models.Invoice).filter_by(
        tenant_id=tenant_id, invoice_type="AR").all()
    candidates = []
    for invoice in invoices:
        if (invoice.currency or "INR") != currency:
            continue
        split = split_balance(db, invoice, allow_inconsistent=True)
        if split["reconciliation_error"] or split["outstanding_cents"] <= 0:
            continue
        outstanding = split["outstanding_cents"]
        score, reasons, uncertainty, evidence = 0.0, [], [], {"invoice_id": invoice.id}
        if invoice.invoice_number and invoice.invoice_number.casefold() in folded:
            score += 0.5
            reasons.append(f"reference {invoice.invoice_number} in description")
            evidence["reference"] = invoice.invoice_number
        else:
            uncertainty.append("no invoice reference")
        payer = (invoice.counterparty_name or "").casefold()
        if payer and payer in folded:
            score += 0.3
            reasons.append(f"payer {invoice.counterparty_name} in description")
            evidence["payer"] = invoice.counterparty_name
        else:
            matched = [alias for alias, name in aliases.items()
                       if alias and alias in folded and name == invoice.counterparty_name]
            if matched:
                score += 0.25
                reasons.append(f"payer alias {matched[0]} in description")
                evidence["payer_alias"] = matched[0]
            else:
                uncertainty.append("payer not identified")
        if transfer_cents == outstanding:
            score += 0.3
            reasons.append("transfer equals outstanding")
        elif transfer_cents < outstanding:
            score += 0.15
            reasons.append("partial transfer against outstanding")
        else:
            score += 0.1
            reasons.append("transfer exceeds outstanding; split or residual")
        if txn_day and invoice.due_date:
            gap = abs((txn_day - invoice.due_date).days)
            if gap <= 7:
                score += 0.05
                reasons.append(f"date within {gap}d of due date")
            else:
                uncertainty.append(f"date differs {gap}d from due date")
        candidates.append({"invoice_id": invoice.id,
                           "invoice_number": invoice.invoice_number,
                           "score": round(score, 3), "outstanding_cents": outstanding,
                           "reasons": reasons, "uncertainty": uncertainty,
                           "evidence": evidence})
    same_amount = {}
    for candidate in candidates:
        same_amount.setdefault(candidate["outstanding_cents"], []).append(candidate)
    for group in same_amount.values():
        if len(group) > 1:
            for candidate in group:
                if "reference" not in candidate["evidence"]:
                    candidate["uncertainty"].append(
                        f"repeated amount on {len(group)} open invoices")
    candidates.sort(key=lambda item: (-item["score"], item["invoice_id"]))
    return candidates


def draft_legs(candidates, transfer_cents):
    """Greedy leg draft over clear candidates, capped by the transfer."""
    legs, remaining = [], transfer_cents
    for candidate in candidates:
        if remaining <= 0 or candidate["score"] < LEG_THRESHOLD:
            continue
        amount = min(remaining, candidate["outstanding_cents"])
        if amount <= 0:
            continue
        legs.append({"invoice_id": candidate["invoice_id"], "amount_cents": amount,
                     "reasons": candidate["reasons"]})
        remaining -= amount
    return legs


def _proposal_status(candidates):
    if not candidates or candidates[0]["score"] < LEG_THRESHOLD:
        return "ambiguous"
    referenced = [c for c in candidates
                  if "reference" in c.get("evidence", {}) and c["score"] >= LEG_THRESHOLD]
    if len(referenced) >= 2:
        return "proposed"
    if candidates[0]["score"] >= CLEAR_SCORE and (
            len(candidates) == 1
            or candidates[0]["score"] - candidates[1]["score"] > CLEAR_MARGIN):
        return "proposed"
    return "ambiguous"


def propose(db, tenant_id, transfer_id, actor, currency="INR"):
    """Create (or return) the candidate proposal for one transfer."""
    existing = db.query(models.AllocationProposal).filter_by(
        tenant_id=tenant_id, afis_transaction_id=str(transfer_id)).first()
    if existing:
        return existing, True
    txn = get_transfer(transfer_id)
    if txn is None:
        raise ValueError("Verified transfer not found")
    transfer_cents = _cents(txn.get("amount") or 0)
    if transfer_cents <= 0:
        raise ValueError("Only incoming transfers can be allocated")
    candidates = score_candidates(db, tenant_id, txn, currency)
    proposal = models.AllocationProposal(
        tenant_id=tenant_id, afis_transaction_id=str(transfer_id),
        transfer_cents=transfer_cents, currency=currency,
        transfer_date=str(txn.get("date") or "")[:20],
        description=str(txn.get("description") or "")[:2000],
        status=_proposal_status(candidates),
        candidates_json=json.dumps(candidates), created_by=actor)
    db.add(proposal)
    db.flush()
    for leg in draft_legs(candidates, transfer_cents):
        db.add(models.AllocationLeg(
            tenant_id=tenant_id, proposal_id=proposal.id,
            invoice_id=leg["invoice_id"], amount_cents=leg["amount_cents"],
            status="pending", reason="; ".join(leg["reasons"])[:500]))
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="allocation_proposed", entity_type="allocation_proposal",
        entity_id=str(proposal.id),
        details=f"transfer={transfer_id}; status={proposal.status}"))
    db.flush()
    return proposal, False


def residual_cents(db, proposal):
    applied = sum(leg.amount_cents for leg in db.query(models.AllocationLeg).filter_by(
        proposal_id=proposal.id, status="applied").all())
    return proposal.transfer_cents - applied


def _settle_status(db, proposal):
    if proposal.status == "rejected":
        return proposal.status
    legs = db.query(models.AllocationLeg).filter_by(proposal_id=proposal.id).all()
    if any(leg.status == "applied" for leg in legs):
        proposal.status = "applied" if residual_cents(db, proposal) == 0 else "partially_applied"
    return proposal.status


def approve(db, proposal, actor, legs=None, reason=""):
    """Staff approval: validate every leg, then post through post_entry."""
    from app.services.receivables import post_entry, split_balance
    if proposal.status == "rejected":
        raise ValueError("Proposal was rejected")
    if legs is not None:
        for item in legs:
            invoice = db.get(models.Invoice, item["invoice_id"])
            if not invoice or invoice.tenant_id != proposal.tenant_id:
                raise ValueError("Leg invoice not found in this tenant")
            if (invoice.currency or "INR") != proposal.currency:
                raise ValueError("Leg currency must match the transfer currency")
            if item.get("allocation", "undisputed_first") not in (
                    "undisputed_first", "disputed_first", "undisputed", "disputed"):
                raise ValueError("Unknown leg allocation policy")
            if int(item["amount_cents"]) <= 0:
                raise ValueError("Leg amounts must be positive")
        if sum(int(item["amount_cents"]) for item in legs) > residual_cents(db, proposal):
            raise ValueError("Legs exceed the transfer residual")
        db.query(models.AllocationLeg).filter_by(
            proposal_id=proposal.id, status="pending").delete()
        for item in legs:
            db.add(models.AllocationLeg(
                tenant_id=proposal.tenant_id, proposal_id=proposal.id,
                invoice_id=item["invoice_id"], amount_cents=int(item["amount_cents"]),
                allocation=item.get("allocation", "undisputed_first"),
                status="pending", reason="staff-selected leg"))
        db.flush()
    pending = db.query(models.AllocationLeg).filter_by(
        proposal_id=proposal.id, status="pending").order_by(
        models.AllocationLeg.id).all()
    if not pending:
        _settle_status(db, proposal)
        db.flush()
        return proposal
    if sum(leg.amount_cents for leg in pending) > residual_cents(db, proposal):
        raise ValueError("Legs exceed the transfer residual")
    for leg in pending:
        if leg.amount_cents <= 0:
            raise ValueError("Leg amounts must be positive")
        invoice = db.get(models.Invoice, leg.invoice_id)
        split = split_balance(db, invoice, allow_inconsistent=True)
        if split["reconciliation_error"]:
            raise ValueError(f"Invoice {invoice.invoice_number} needs reconciliation first")
        if leg.amount_cents > split["outstanding_cents"]:
            raise ValueError(f"Leg exceeds the outstanding on {invoice.invoice_number}")
        entry = post_entry(db, invoice, kind="payment",
                           amount=Decimal(leg.amount_cents) / 100,
                           source="allocated_transfer",
                           reference=f"{proposal.afis_transaction_id}:{invoice.id}",
                           actor=actor, note=f"AFIS transfer {proposal.afis_transaction_id}",
                           allocation=leg.allocation, currency=proposal.currency)
        leg.status = "applied"
        leg.entry_id = entry.id
    proposal.decided_by = actor
    proposal.decision_reason = reason[:500] if reason else "staff-approved allocation"
    _settle_status(db, proposal)
    db.add(models.AuditEvent(tenant_id=proposal.tenant_id, actor=actor,
        action="allocation_approved", entity_type="allocation_proposal",
        entity_id=str(proposal.id),
        details=f"legs={len(pending)}; status={proposal.status}"))
    db.flush()
    return proposal


def reject(db, proposal, actor, reason):
    if proposal.status in ("applied", "partially_applied"):
        raise ValueError("Applied allocations cannot be rejected; reverse the entries")
    proposal.status = "rejected"
    proposal.decided_by = actor
    proposal.decision_reason = reason[:500]
    for leg in db.query(models.AllocationLeg).filter_by(
            proposal_id=proposal.id, status="pending").all():
        leg.status = "rejected"
    db.add(models.AuditEvent(tenant_id=proposal.tenant_id, actor=actor,
        action="allocation_rejected", entity_type="allocation_proposal",
        entity_id=str(proposal.id), details=reason[:500]))
    db.flush()
    return proposal
