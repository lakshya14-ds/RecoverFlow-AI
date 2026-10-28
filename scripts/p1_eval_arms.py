"""Three evaluation arms over identical fixture cases.

- rules: naive single pass. Demands the full outstanding balance, allocates by
  exact invoice-number match with no currency check, never escalates, writes
  nothing. This is the baseline the other arms must beat on hard cases.
- single: one competent pass over the same service functions the specialist
  tools wrap (investigate, allocation propose, structured-message
  build/render/validate, multilingual classify, promise extraction). No task
  loop, no independent verification, no retries.
- specialist: the real supervisor loop (reassess + run tasks to a terminal
  outcome) with allocation proposed per arrived transfer first.

Arms are told which transfers arrived for the case (arrival scoping); matching
is theirs to do. Arms must never post ledger entries, approve, or send; the
scorer counts any such write as an unsafe action.
"""
from decimal import Decimal

from app.database import models
from app.services import multilingual as ml
from app.services.allocation import propose as propose_allocation
from app.services.case_lifecycle import fingerprint
from app.services.investigation import investigate
from app.services.promises import create_from_message
from app.services.receivables import split_balance

from scripts.p1_eval_cases import TENANT, write_snapshot

TERMINAL = ("steady", "complete", "escalated", "ignored", "failed")
MAX_STEPS = 12


def _split(db, invoice):
    return split_balance(db, invoice, allow_inconsistent=True)


def _new_open_explanations(db, invoice_id):
    return db.query(models.CompetingExplanation).filter_by(
        tenant_id=TENANT, invoice_id=invoice_id, status="open").count()


def _blank_invoice_outcome():
    return {"requested_cents": None, "draft_produced": False, "draft_text": "",
            "disputed_cents": 0, "open_explanations": 0, "escalated": False,
            "promise_created": False, "clarifications_open": 0}


def run_rules_arm(db, spec, ids):
    """Naive baseline: full demand, exact-reference allocation, no escalation."""
    outcome = {"invoices": {}, "legs": [], "model_calls": 0}
    splits = {number: _split(db, db.get(models.Invoice, invoice_id))
              for number, invoice_id in ids.items()}
    for number, invoice_id in ids.items():
        row = _blank_invoice_outcome()
        requested = splits[number]["outstanding_cents"]
        row["requested_cents"] = requested
        row["draft_produced"] = True
        row["draft_text"] = (
            f"Please pay the full outstanding "
            f"{db.get(models.Invoice, invoice_id).currency or 'INR'} "
            f"{Decimal(requested) / 100:,.2f} immediately.")
        row["disputed_cents"] = 0
        outcome["invoices"][number] = row
    for txn in spec["txns"]:
        remaining = int(Decimal(str(txn["amount"])) * 100)
        folded = str(txn["description"] or "").casefold()
        for number in sorted(ids):
            if remaining <= 0:
                break
            if number.casefold() not in folded:
                continue
            amount = min(remaining, splits[number]["outstanding_cents"])
            if amount <= 0:
                continue
            outcome["legs"].append([txn["id"], number, amount])
            remaining -= amount
    return outcome


def _single_invoice(db, invoice, number):
    row = _blank_invoice_outcome()
    messages = db.query(models.CustomerMessage).filter_by(
        tenant_id=TENANT, invoice_id=invoice.id).order_by(
        models.CustomerMessage.id).all()
    if invoice.requires_human_review or invoice.contact_suppressed or any(
            message.is_injection for message in messages):
        row["escalated"] = True
        row["disputed_cents"] = int(invoice.disputed_cents or 0)
        return row, messages
    try:
        disputed = investigate(db, invoice)
    except ValueError:
        db.commit()
        row["escalated"] = True
        row["disputed_cents"] = int(invoice.disputed_cents or 0)
        row["open_explanations"] = _new_open_explanations(db, invoice.id)
        return row, messages
    db.commit()
    row["disputed_cents"] = int(disputed)
    row["open_explanations"] = _new_open_explanations(db, invoice.id)
    if messages and ml.classify_multilingual(messages[-1].body or "") == "commitment":
        try:
            _, duplicate = create_from_message(db, invoice, messages[-1],
                                               actor="single_eval_arm")
            row["promise_created"] = True
        except ValueError:
            pass
        db.commit()
    return row, messages


def _single_draft(db, invoice, number, messages):
    split = _split(db, invoice)
    if split["undisputed_cents"] <= 0:
        return None, ""
    language = ml.detect_language(messages[-1].body) if messages else "en"
    evidence = db.query(models.CaseEvidence).filter_by(
        tenant_id=TENANT, invoice_id=invoice.id).all()
    version = fingerprint(db, invoice)
    disputed_money = (f"{invoice.currency or 'INR'} "
                      f"{Decimal(split['disputed_cents']) / 100:,.2f}")
    message = ml.build_message(
        recipient="customer_on_file", channel="sandbox", language=language,
        requested_cents=split["undisputed_cents"], currency=invoice.currency or "INR",
        installment_dates=[],
        dispute_statement=disputed_money if split["disputed_cents"] else "",
        commitments=[], source_ids=[row.id for row in evidence],
        case_version=version)
    ml.check_message(message, invoice, split, version)
    prose = ml.render_message(message, invoice.invoice_number)
    ml.validate_prose(prose, message, invoice, split)
    return split["undisputed_cents"], prose


def run_single_arm(db, spec, ids):
    """One competent pass: investigate, propose, validate, draft or escalate."""
    from app.services.allocation import propose as propose_transfer
    outcome = {"invoices": {}, "legs": [], "model_calls": 0}
    ambiguous_txn = False
    for txn in spec["txns"]:
        try:
            proposal, _ = propose_transfer(db, TENANT, txn["id"], "single_eval_arm")
            db.commit()
        except ValueError:
            continue
        if proposal.status == "ambiguous":
            ambiguous_txn = True
    if not ambiguous_txn:
        for txn in spec["txns"]:
            proposal = db.query(models.AllocationProposal).filter_by(
                tenant_id=TENANT, afis_transaction_id=txn["id"]).first()
            if proposal is None or proposal.status != "proposed":
                continue
            for leg in db.query(models.AllocationLeg).filter_by(
                    proposal_id=proposal.id).order_by(models.AllocationLeg.id).all():
                invoice = db.get(models.Invoice, leg.invoice_id)
                outcome["legs"].append([txn["id"], invoice.invoice_number,
                                       leg.amount_cents])
    for number, invoice_id in ids.items():
        invoice = db.get(models.Invoice, invoice_id)
        row, messages = _single_invoice(db, invoice, number)
        if ambiguous_txn:
            row["escalated"] = True
        if not row["escalated"]:
            try:
                requested, prose = _single_draft(db, invoice, number, messages)
            except ValueError:
                row["escalated"] = True
            else:
                if requested is not None:
                    row["requested_cents"] = requested
                    row["draft_produced"] = True
                    row["draft_text"] = prose
        row["clarifications_open"] = db.query(models.ClarificationTask).filter_by(
            tenant_id=TENANT, invoice_id=invoice.id, status="open").count()
        outcome["invoices"][number] = row
    db.commit()
    return outcome


def run_specialist_arm(db, spec, ids):
    """Real supervisor loop per invoice after proposing arrived transfers."""
    from app.services import supervisor
    outcome = {"invoices": {}, "legs": [], "model_calls": 0}
    for txn in spec["txns"]:
        try:
            propose_allocation(db, TENANT, txn["id"], "specialist_eval_arm")
            db.commit()
        except ValueError:
            db.rollback()
    for number, invoice_id in ids.items():
        row = _blank_invoice_outcome()
        for _ in range(MAX_STEPS):
            invoice = db.get(models.Invoice, invoice_id)
            result = supervisor.reassess(db, invoice, "eval5", actor="eval5")
            db.commit()
            if result["outcome"] in TERMINAL:
                if result["outcome"] == "escalated":
                    row["escalated"] = True
                break
            task_id = result.get("task_id")
            if not task_id:
                break
            ran = supervisor.run_task(db, task_id, actor="eval5")
            db.commit()
            if ran["outcome"] in ("escalated", "failed"):
                row["escalated"] = True
        invoice = db.get(models.Invoice, invoice_id)
        if invoice.investigation_hold or invoice.requires_human_review:
            row["escalated"] = True
        tasks = db.query(models.SupervisorTask).filter_by(
            tenant_id=TENANT, invoice_id=invoice.id).all()
        if any(task.status in ("escalated", "failed") for task in tasks):
            row["escalated"] = True
        outcome["model_calls"] += sum(task.model_calls or 0 for task in tasks)
        row["disputed_cents"] = _split(db, invoice)["disputed_cents"]
        row["open_explanations"] = _new_open_explanations(db, invoice.id)
        row["clarifications_open"] = db.query(models.ClarificationTask).filter_by(
            tenant_id=TENANT, invoice_id=invoice.id, status="open").count()
        row["promise_created"] = db.query(models.PromiseToPay).filter_by(
            tenant_id=TENANT, invoice_id=invoice.id).count() > 0
        latest = None
        for task in tasks:
            if task.kind != "communication" or task.status != "done":
                continue
            if latest is None or task.id > latest.id:
                latest = task
        if latest is not None:
            import json
            findings = json.loads(latest.result_json or "{}").get("findings", {})
            message = findings.get("message", {})
            if "requested_cents" in message:
                row["requested_cents"] = message["requested_cents"]
                row["draft_produced"] = True
                row["draft_text"] = findings.get("prose", "")
        outcome["invoices"][number] = row
    for txn in spec["txns"]:
        proposal = db.query(models.AllocationProposal).filter_by(
            tenant_id=TENANT, afis_transaction_id=txn["id"]).first()
        if proposal is None or proposal.status != "proposed":
            continue
        for leg in db.query(models.AllocationLeg).filter_by(
                proposal_id=proposal.id).order_by(models.AllocationLeg.id).all():
            invoice = db.get(models.Invoice, leg.invoice_id)
            outcome["legs"].append([txn["id"], invoice.invoice_number, leg.amount_cents])
    db.commit()
    return outcome


ARMS = {"rules": run_rules_arm, "single": run_single_arm,
        "specialist": run_specialist_arm}


def unsafe_write_delta(before, after):
    return sum(max(0, after[key] - before[key]) for key in before)
