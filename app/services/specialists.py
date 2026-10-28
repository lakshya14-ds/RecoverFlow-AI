"""Specialist contracts, tool gateway, and bounded specialist runners.

Every specialist output carries case/version/sources/claims/confidence/
proposed action/reason/escalation. Model output may classify and draft
wording; money, postings, approvals, and waivers stay server-side.

M1 scope: model use is classification only (`model_classify`); wording stays
a deterministic server template so outputs are reproducible offline.
Multilingual model wording arrives in M4.
"""
import json
import re
import time
from decimal import Decimal
from datetime import datetime, timezone

from app.database import models

SPECIALISTS = ("intake", "investigation", "reconciliation", "resolution",
               "communication", "verification")

REQUIRED_OUTPUT_KEYS = ("case_id", "case_version", "specialist", "sources",
                        "claims", "confidence", "uncertainty", "proposed_action",
                        "reason", "escalate", "escalation_conditions", "findings")


class ToolDenied(Exception):
    """A specialist attempted a tool outside its allowlist."""


class BudgetExhausted(Exception):
    """A task exceeded its model-call budget."""


class OutputRejected(Exception):
    """A specialist output violated its contract."""


TOOL_ALLOWLIST = {
    "intake": ("evidence_list", "intake_process_upload", "case_describe"),
    "investigation": ("ledger_read_split", "evidence_list", "investigation_run",
                      "case_describe"),
    "reconciliation": ("ledger_read_split", "ledger_list_entries",
                       "reconciliation_list_pending", "match_score_candidates",
                       "evidence_list", "case_describe"),
    "resolution": ("ledger_read_split", "ledger_list_entries", "evidence_list",
                   "case_describe"),
    "communication": ("ledger_read_split", "evidence_list", "message_describe",
                      "draft_describe", "draft_prepare", "model_classify",
                      "model_draft_wording", "case_describe"),
    "verification": ("ledger_read_split", "ledger_read_raw",
                     "ledger_list_entries", "evidence_list", "draft_describe",
                     "case_describe"),
}

# Deliberately unregistered: ledger_post, ledger_reverse, evidence_accept,
# message_send, approval_grant, credit_approve, balance_waive. Any attempt to
# call them fails closed in call_tool.


def check_output(output: dict) -> dict:
    """Validate a specialist output against its contract (pure)."""
    if not isinstance(output, dict):
        raise OutputRejected("Specialist output must be an object")
    missing = [key for key in REQUIRED_OUTPUT_KEYS if key not in output]
    if missing:
        raise OutputRejected("Output is missing: " + ", ".join(missing))
    if output["specialist"] not in SPECIALISTS:
        raise OutputRejected("Unknown specialist: " + repr(output["specialist"]))
    if not isinstance(output["confidence"], (int, float)) or not 0 <= output["confidence"] <= 1:
        raise OutputRejected("Confidence must be a number between 0 and 1")
    for key in ("sources", "claims", "uncertainty", "escalation_conditions"):
        if not isinstance(output[key], list):
            raise OutputRejected(f"Output field {key} must be a list")
    if not isinstance(output["escalate"], bool):
        raise OutputRejected("Output field escalate must be boolean")
    if output["escalate"] and not output["escalation_conditions"]:
        raise OutputRejected("Escalation requires escalation_conditions")
    if not isinstance(output["findings"], dict):
        raise OutputRejected("Output field findings must be an object")
    return output


def _invoice(db, ctx):
    invoice = db.get(models.Invoice, ctx["invoice_id"]) if ctx.get("invoice_id") else None
    if ctx.get("invoice_id") and (not invoice or invoice.tenant_id != ctx["tenant_id"]):
        raise ValueError("Receivable case not found")
    return invoice


def _audit_tool(db, ctx, tool, detail=""):
    db.add(models.AuditEvent(tenant_id=ctx["tenant_id"], actor=ctx.get("actor", "supervisor"),
        action="specialist_tool", entity_type="supervisor_task",
        entity_id=str(ctx.get("task_id")), details=f"{ctx['specialist']}:{tool} {detail}"[:500]))


def call_tool(db, ctx, name, **kwargs):
    """Invoke a registered tool if the specialist's allowlist permits it."""
    allowed = TOOL_ALLOWLIST.get(ctx["specialist"], ())
    if name not in allowed or name not in TOOLS:
        _audit_tool(db, ctx, name, "DENIED")
        db.flush()
        raise ToolDenied(f"Tool {name} is not allowed for {ctx['specialist']}")
    return TOOLS[name](db, ctx, **kwargs)


# --- Read tools (all specialists get the subset they need) ---

def _tool_ledger_read_split(db, ctx):
    from app.services.receivables import split_balance
    invoice = _invoice(db, ctx)
    split = split_balance(db, invoice, allow_inconsistent=True)
    return {key: value for key, value in split.items() if key.endswith("_cents") or key == "reconciliation_error"}


def _tool_ledger_read_raw(db, ctx):
    """Independent recomputation straight from stored rows (no split_balance)."""
    invoice = _invoice(db, ctx)
    entries = db.query(models.ReceivableEntry).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).all()
    opening = invoice.face_amount_cents
    if opening is None:
        from decimal import Decimal
        opening = int(Decimal(str(invoice.total_amount)) * 100)
    outstanding = opening + sum(entry.amount_cents for entry in entries)
    return {"invoice_total_cents": opening, "outstanding_cents": outstanding,
            "disputed_cents": int(invoice.disputed_cents or 0), "entry_count": len(entries)}


def _tool_ledger_list_entries(db, ctx):
    invoice = _invoice(db, ctx)
    return [{"id": e.id, "kind": e.kind, "amount_cents": e.amount_cents,
             "allocation": e.allocation, "disputed_delta_cents": e.disputed_delta_cents,
             "currency": e.currency, "source": e.source, "reference": e.reference}
            for e in db.query(models.ReceivableEntry).filter_by(
                tenant_id=invoice.tenant_id, invoice_id=invoice.id).order_by(
                models.ReceivableEntry.id).all()]


def _tool_evidence_list(db, ctx):
    invoice = _invoice(db, ctx)
    return [{"id": e.id, "claim_type": e.claim_type, "title": e.title,
             "source_type": e.source_type, "source_reference": e.source_reference,
             "amount_cents": e.amount_cents, "trust_state": e.trust_state,
             "decided_by": e.decided_by, "currency": e.currency}
            for e in db.query(models.CaseEvidence).filter_by(
                tenant_id=invoice.tenant_id, invoice_id=invoice.id).order_by(
                models.CaseEvidence.id).all()]


def _tool_case_describe(db, ctx):
    from app.services.case_lifecycle import derive_stage
    from app.services.receivables import split_balance
    invoice = _invoice(db, ctx)
    split = split_balance(db, invoice, allow_inconsistent=True)
    workflow = db.query(models.CaseWorkflow).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).first()
    return {"id": invoice.id, "invoice_number": invoice.invoice_number,
            "status": invoice.status, "stage": derive_stage(split, invoice),
            "currency": invoice.currency, "due_date": invoice.due_date.isoformat(),
            "contact_suppressed": bool(invoice.contact_suppressed),
            "contact_opt_out": bool(invoice.contact_opt_out),
            "requires_human_review": bool(invoice.requires_human_review),
            "investigation_hold": bool(invoice.investigation_hold),
            "workflow_revision": workflow.revision if workflow else 0}


def _tool_draft_describe(db, ctx):
    invoice = _invoice(db, ctx)
    proposals = db.query(models.AgentProposal).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).order_by(
        models.AgentProposal.id.desc()).limit(5).all()
    described = []
    for proposal in proposals:
        version = db.query(models.ProposalDraftVersion).filter_by(
            tenant_id=invoice.tenant_id, proposal_id=proposal.id).order_by(
            models.ProposalDraftVersion.version_number.desc()).first()
        described.append({"proposal_id": proposal.id, "action": proposal.action,
            "status": proposal.status, "context_hash": proposal.context_hash,
            "version": version.version_number if version else None,
            "version_hash": version.version_hash if version else None,
            "version_status": version.status if version else None})
    return described


def _tool_message_describe(db, ctx):
    invoice = _invoice(db, ctx)
    return [{"id": m.id, "category": m.category, "body": m.body[:500],
             "is_injection": bool(m.is_injection)}
            for m in db.query(models.CustomerMessage).filter_by(
                tenant_id=invoice.tenant_id, invoice_id=invoice.id).order_by(
                models.CustomerMessage.id).all()]


def _tool_reconciliation_list_pending(db, ctx):
    invoice = _invoice(db, ctx)
    return [{"id": r.id, "afis_transaction_id": r.afis_transaction_id,
             "match_type": r.match_type, "confidence_score": r.confidence_score,
             "matched_amount": str(r.matched_amount)}
            for r in db.query(models.Reconciliation).filter_by(
                tenant_id=invoice.tenant_id, invoice_id=invoice.id,
                status="pending_review").all()]


# --- Write-scoped tools (each wraps one existing authorized path) ---

def _tool_intake_process_upload(db, ctx, upload_id: str):
    from app.services import intake_pipeline
    row = db.get(models.IntakeUpload, upload_id)
    if not row or row.tenant_id != ctx["tenant_id"]:
        raise ValueError("Upload not found")
    if row.status != "queued":
        return {"upload_id": upload_id, "status": row.status,
                "detail": "Already claimed or processed; no duplicate work"}
    job = intake_pipeline.claim_job(db, upload_id)
    if job is None:
        return {"upload_id": upload_id, "status": "processing",
                "detail": "Claimed by another worker"}
    intake_pipeline.process_job(db, job)
    finished = db.get(models.IntakeUpload, upload_id)
    linked = None
    if finished.extraction_json:
        import json as _json
        try:
            document = _json.loads(finished.extraction_json)
        except ValueError:
            document = {}
        reference = document.get("invoice_reference") or document.get("invoice_number")
        if reference:
            match = db.query(models.Invoice).filter_by(
                tenant_id=ctx["tenant_id"], invoice_number=reference).all()
            if len(match) == 1:
                linked = match[0].id
    if linked is None:
        match = db.query(models.Invoice).filter_by(
            tenant_id=ctx["tenant_id"], source_path=finished.source_path).first()
        linked = match.id if match else None
    return {"upload_id": upload_id, "status": finished.status, "stage": finished.stage,
            "error": finished.error, "cases_created": finished.cases_created,
            "linked_invoice_id": linked}


def _tool_investigation_run(db, ctx):
    from app.services.investigation import investigate
    invoice = _invoice(db, ctx)
    try:
        disputed = investigate(db, invoice)
    except ValueError as exc:
        db.flush()
        return {"held": True, "reason": str(exc)[:500],
                "disputed_cents": int(invoice.disputed_cents or 0)}
    return {"held": False, "reason": "",
            "disputed_cents": int(disputed)}


def _tool_match_score_candidates(db, ctx, limit: int = 5):
    from app.skills.match_invoice_payment import match_invoice_to_payment
    invoice = _invoice(db, ctx)
    try:
        from app.plugins.afis_reader import AFISReader
        from datetime import date as _date, timedelta as _td
        start = invoice.issue_date - _td(days=30)
        end = invoice.due_date + _td(days=60)
        txns = AFISReader().get_transactions(
            start.isoformat(), end.isoformat(),
            tx_type="income" if invoice.invoice_type == "AR" else "expense")
    except Exception as exc:
        return {"available": False, "reason": f"AFIS read unavailable: {exc}"[:200],
                "candidates": []}
    used = {row[0] for row in db.query(models.Reconciliation.afis_transaction_id).filter(
        models.Reconciliation.tenant_id == invoice.tenant_id,
        models.Reconciliation.status == "approved").all()}
    txns = [tx for tx in txns if tx.get("id") not in used]
    scored = match_invoice_to_payment(
        {"total_amount": str(invoice.total_amount),
         "due_date": invoice.due_date.isoformat()}, txns)[:limit]
    candidates = []
    for match in scored:
        if match.get("match_type") == "none":
            continue
        candidates.append({"transaction_id": match.get("afis_transaction_id"),
            "score": match.get("confidence_score"), "match_type": match.get("match_type"),
            "amount": str(match.get("matched_amount", "")),
            "variance": str(match.get("variance_amount", "")),
            "explanation": match.get("explanation", "")})
    return {"available": True, "candidates": candidates}


def _tool_draft_prepare(db, ctx):
    from app.services.release4_orchestrator import prepare_draft
    invoice = _invoice(db, ctx)
    try:
        proposal = prepare_draft(db, invoice)
    except ValueError as exc:
        return {"prepared": False, "reason": str(exc)[:500]}
    db.flush()
    version = db.query(models.ProposalDraftVersion).filter_by(
        tenant_id=invoice.tenant_id, proposal_id=proposal.id).order_by(
        models.ProposalDraftVersion.version_number.desc()).first()
    return {"prepared": True, "proposal_id": proposal.id,
            "version": version.version_number if version else None,
            "version_hash": version.version_hash if version else None}


def _tool_model_classify(db, ctx, text: str):
    from app.services import meta_agent
    from app.services.negotiation import classify_inbound
    if ctx.get("model_calls", 0) >= ctx.get("model_budget", 0):
        raise BudgetExhausted("Model-call budget exhausted")
    if not meta_agent.configured():
        return {"engine": "rules_fallback", "classification": classify_inbound(text)}
    try:
        classification = meta_agent.classify_intent(text, role="intent")
    except Exception:
        return {"engine": "rules_fallback", "classification": classify_inbound(text)}
    ctx["model_calls"] = ctx.get("model_calls", 0) + 1
    return {"engine": "model", "classification": classification}


def _tool_model_draft_wording(db, ctx, carrier: str, language: str):
    """Rephrase fact-free carrier sentences only; facts are server-spliced."""
    from app.services import meta_agent
    from app.services.security import detect_prompt_injection
    if ctx.get("model_calls", 0) >= ctx.get("model_budget", 0):
        raise BudgetExhausted("Model-call budget exhausted")
    if not carrier.strip() or not meta_agent.configured():
        return {"engine": "template", "text": carrier}
    try:
        wording = meta_agent.generate(
            {"carrier": carrier[:500], "language": language}, "collection_wording",
            role="drafter")
        candidate = (wording.reply_draft or "").strip()
    except Exception:
        return {"engine": "template", "text": carrier}
    ctx["model_calls"] = ctx.get("model_calls", 0) + 1
    if (not candidate or len(candidate) > 500 or detect_prompt_injection(candidate)[0]
            or re.search(r"\d|https?://|www\.|@|upi|bank account", candidate, re.I)):
        return {"engine": "template", "text": carrier}
    return {"engine": "model", "text": candidate}


TOOLS = {
    "ledger_read_split": _tool_ledger_read_split,
    "ledger_read_raw": _tool_ledger_read_raw,
    "ledger_list_entries": _tool_ledger_list_entries,
    "evidence_list": _tool_evidence_list,
    "case_describe": _tool_case_describe,
    "draft_describe": _tool_draft_describe,
    "message_describe": _tool_message_describe,
    "reconciliation_list_pending": _tool_reconciliation_list_pending,
    "intake_process_upload": _tool_intake_process_upload,
    "investigation_run": _tool_investigation_run,
    "match_score_candidates": _tool_match_score_candidates,
    "draft_prepare": _tool_draft_prepare,
    "model_classify": _tool_model_classify,
    "model_draft_wording": _tool_model_draft_wording,
}


def _base_output(ctx, case_version, findings=None):
    return {"case_id": ctx.get("invoice_id"), "case_version": case_version,
            "specialist": ctx["specialist"], "sources": [], "claims": [],
            "confidence": 0.0, "uncertainty": [], "proposed_action": None,
            "reason": "", "escalate": False, "escalation_conditions": [],
            "findings": findings or {}}


# --- Specialist runners (one per contract; advisory unless noted) ---

def run_intake(db, ctx, task_input):
    """Process one queued upload, then link it to its case (existing path)."""
    upload_id = task_input.get("upload_id")
    if not upload_id:
        raise ValueError("Intake task requires input.upload_id")
    started_version = ctx.get("case_version_hint")
    result = call_tool(db, ctx, "intake_process_upload", upload_id=upload_id)
    output = _base_output(ctx, started_version, {"upload": result})
    output["sources"] = [f"/api/v1/intake/uploads/{upload_id}/file"]
    output["confidence"] = 1.0 if result["status"] == "ready_for_review" else 0.5
    if result.get("linked_invoice_id"):
        output["case_id"] = result["linked_invoice_id"]
        output["proposed_action"] = "reassess_case"
        output["reason"] = "Upload processed and linked; reassess the case"
    elif result["status"] == "needs_attention":
        output["proposed_action"] = "staff_review"
        output["reason"] = result.get("error") or "Upload needs staff attention"
        output["escalate"] = True
        output["escalation_conditions"] = ["intake_needs_attention"]
        output["uncertainty"] = [result.get("error") or "unprocessed upload"]
    else:
        output["reason"] = "Upload processed without a linked case"
    return check_output(output)


def run_investigation(db, ctx, task_input):
    """Run the existing document investigation (existing path)."""
    split = call_tool(db, ctx, "ledger_read_split")
    evidence = call_tool(db, ctx, "evidence_list")
    result = call_tool(db, ctx, "investigation_run")
    invoice = _invoice(db, ctx)
    explanations = [{"id": e.id, "identity": e.identity, "category": e.category,
                     "status": e.status, "hypotheses": json.loads(e.hypotheses_json or "[]")}
                    for e in db.query(models.CompetingExplanation).filter_by(
                        tenant_id=invoice.tenant_id, invoice_id=invoice.id).all()]
    clarifications = [{"id": c.id, "key": c.key, "title": c.title, "owner": c.owner,
                       "status": c.status, "affected_cents": c.affected_cents}
                      for c in db.query(models.ClarificationTask).filter_by(
                          tenant_id=invoice.tenant_id, invoice_id=invoice.id).all()]
    output = _base_output(ctx, ctx["case_version"], {
        "split_cents": split, "disputed_cents": result["disputed_cents"],
        "held": result["held"], "explanations": explanations,
        "clarifications": clarifications})
    output["sources"] = [e["source_reference"] for e in evidence if e["source_reference"]]
    output["claims"] = [e["id"] for e in evidence if e["claim_type"] == "dispute_item"]
    if result["held"]:
        output.update(confidence=0.4, proposed_action="staff_review",
                       reason=result["reason"], escalate=True,
                       escalation_conditions=["investigation_hold"],
                       uncertainty=[result["reason"]])
    else:
        output.update(confidence=0.85, proposed_action="continue",
                       reason=f"Investigation settled dispute at {result['disputed_cents']} cents")
    return check_output(output)


def run_reconciliation(db, ctx, task_input):
    """Score read-only AFIS match candidates; staff approve any posting."""
    pending = call_tool(db, ctx, "reconciliation_list_pending")
    scored = call_tool(db, ctx, "match_score_candidates")
    invoice = _invoice(db, ctx)
    legs = [{"proposal_id": leg.proposal_id, "amount_cents": leg.amount_cents,
             "status": leg.status}
            for leg in db.query(models.AllocationLeg).filter_by(
                tenant_id=invoice.tenant_id, invoice_id=invoice.id,
                status="pending").all()]
    proposals = {p.id: p.status for p in db.query(models.AllocationProposal).filter_by(
        tenant_id=invoice.tenant_id).all()}
    ambiguous = sorted({leg["proposal_id"] for leg in legs
                        if proposals.get(leg["proposal_id"]) == "ambiguous"})
    output = _base_output(ctx, ctx["case_version"], {
        "pending": pending, "candidates": scored.get("candidates", []),
        "afis_available": scored.get("available", False),
        "allocation_legs": legs, "ambiguous_proposals": ambiguous})
    output["sources"] = [f"afis:{c.get('transaction_id')}" for c in scored.get("candidates", [])]
    candidates = scored.get("candidates", [])
    exact = [c for c in candidates if (c.get("score") or 0) >= 0.9]
    if not scored.get("available", False):
        output.update(confidence=0.3, proposed_action="continue",
                       reason="AFIS unavailable; nothing to match",
                       uncertainty=["afis_unavailable"])
    elif not pending and not candidates:
        output.update(confidence=0.9, proposed_action="continue",
                       reason="No pending reconciliations or candidates")
    elif exact and len(exact) == 1 and not pending:
        output.update(confidence=0.75, proposed_action="staff_review",
                       reason="One exact candidate awaits staff approval")
    else:
        output.update(confidence=0.45, proposed_action="staff_review",
                       reason="Ambiguous or pending matches need staff choice",
                       escalate=True,
                       escalation_conditions=["ambiguous_match"],
                       uncertainty=["multiple_or_pending_candidates"])
    if ambiguous:
        output.update(confidence=min(output["confidence"], 0.45),
                       proposed_action="staff_review",
                       reason=f"Ambiguous allocation proposals need staff choice: {ambiguous}",
                       escalate=True,
                       escalation_conditions=["ambiguous_match"],
                       uncertainty=list(output["uncertainty"]) + ["ambiguous_proposals"])
    return check_output(output)


def run_resolution(db, ctx, task_input):
    """Compute the collectible request from server facts; propose, never post."""
    case = call_tool(db, ctx, "case_describe")
    split = call_tool(db, ctx, "ledger_read_split")
    evidence = call_tool(db, ctx, "evidence_list")
    trusted_invoice = any(e["claim_type"] == "invoice_total" and e["source_reference"]
                          for e in evidence)
    invoice = _invoice(db, ctx)
    open_clarifications = db.query(models.ClarificationTask).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, status="open").count()
    output = _base_output(ctx, ctx["case_version"], {
        "stage": case["stage"], "split_cents": split,
        "trusted_invoice_source": trusted_invoice,
        "open_clarifications": open_clarifications})
    output["sources"] = [e["source_reference"] for e in evidence if e["source_reference"]]
    blocked = case["investigation_hold"] or case["requires_human_review"] or \
        case["contact_suppressed"] or case["contact_opt_out"]
    if blocked or split.get("reconciliation_error"):
        output.update(confidence=0.5, proposed_action="staff_review",
                       reason="Case is paused or inconsistent; staff owns the next move",
                       escalate=True, escalation_conditions=["case_blocked"],
                       uncertainty=["contact_or_review_block"])
    elif not trusted_invoice:
        output.update(confidence=0.4, proposed_action="staff_review",
                       reason="Invoice amount has no clickable source",
                       escalate=True, escalation_conditions=["missing_source"],
                       uncertainty=["no_invoice_source"])
    elif split.get("undisputed_cents", 0) <= 0:
        output.update(confidence=0.9, proposed_action="none",
                       reason="No undisputed balance remains")
    else:
        output.update(confidence=0.85, proposed_action="prepare_communication",
                       reason=f"Request undisputed {split['undisputed_cents']} cents only")
    if open_clarifications:
        output["uncertainty"].append(f"{open_clarifications} clarification(s) still open")
    open_promises = db.query(models.PromiseToPay).filter(
        models.PromiseToPay.tenant_id == invoice.tenant_id,
        models.PromiseToPay.invoice_id == invoice.id,
        models.PromiseToPay.status.in_(("alleged", "confirmed"))).count()
    output["findings"]["open_promises"] = open_promises
    if open_promises:
        output["uncertainty"].append(
            f"{open_promises} open promise(s); nonfinancial, amounts unaffected")
    return check_output(output)


def _rephrase_carrier(db, ctx, prose, language):
    """Rephrase fact-free carrier spans; money spans are server-spliced back."""
    spans = [match.span() for match in re.compile(
        r"(?:\b(?:inr|usd|eur|gbp|rs\.?|rupees)\s*|[₹$€£]\s*)[0-9][0-9,]*(?:\.[0-9]+)?",
        re.I).finditer(prose)]
    if not spans:
        return prose, "template"
    parts, cursor, engine = [], 0, "template"
    for start, end in spans:
        parts.append(prose[cursor:start])
        parts.append(prose[start:end])
        cursor = end
    parts.append(prose[cursor:])
    for index in range(0, len(parts), 2):
        if not parts[index].strip():
            continue
        try:
            result = call_tool(db, ctx, "model_draft_wording",
                               carrier=parts[index], language=language)
        except BudgetExhausted:
            break
        parts[index] = result["text"]
        engine = result["engine"] if result["engine"] == "model" else engine
    return "".join(parts), engine


def run_communication(db, ctx, task_input):
    """Build a validated structured message, then prepare an unsent draft."""
    from app.services import multilingual as _ml
    case = call_tool(db, ctx, "case_describe")
    split = call_tool(db, ctx, "ledger_read_split")
    evidence = call_tool(db, ctx, "evidence_list")
    messages = call_tool(db, ctx, "message_describe")
    classification, language = "none", "en"
    if messages:
        classified = call_tool(db, ctx, "model_classify", text=messages[-1]["body"])
        classification = classified.get("classification", "none")
        language = _ml.detect_language(messages[-1]["body"])
    invoice = _invoice(db, ctx)
    money = f"{case['currency']} {Decimal(split['undisputed_cents']) / 100:,.2f}"
    disputed_money = f"{case['currency']} {Decimal(split['disputed_cents']) / 100:,.2f}"
    message = _ml.build_message(
        recipient="customer_on_file", channel="sandbox", language=language,
        requested_cents=split["undisputed_cents"], currency=case["currency"],
        installment_dates=[], dispute_statement=disputed_money if split["disputed_cents"] else "",
        commitments=[], source_ids=[e["id"] for e in evidence],
        case_version=ctx["case_version"])
    message["customer_intent"] = classification
    output = _base_output(ctx, ctx["case_version"], {"message": message})
    output["sources"] = [e["source_reference"] for e in evidence if e["source_reference"]]
    try:
        _ml.check_message(message, invoice, split, ctx["case_version"])
    except ValueError as exc:
        output.update(confidence=0.3, proposed_action="staff_review",
                       reason=f"Structured message invalid: {exc}", escalate=True,
                       escalation_conditions=["wording_blocked"], uncertainty=[str(exc)])
        return check_output(output)
    prose = _ml.render_message(message, invoice.invoice_number)
    engine = "template"
    if task_input.get("model_wording"):
        prose, engine = _rephrase_carrier(db, ctx, prose, language)
    output["findings"].update({"prose": prose, "engine": engine,
                               "requested": money})
    try:
        _ml.validate_prose(prose, message, invoice, split)
    except ValueError as exc:
        output.update(confidence=0.3, proposed_action="staff_review",
                       reason=f"Rendered wording invalid: {exc}", escalate=True,
                       escalation_conditions=["wording_blocked"], uncertainty=[str(exc)])
        return check_output(output)
    prepared = call_tool(db, ctx, "draft_prepare")
    if not prepared.get("prepared"):
        output.update(confidence=0.5, proposed_action="staff_review",
                       reason=prepared.get("reason", "Draft not eligible"),
                       escalate=True, escalation_conditions=["draft_ineligible"],
                       uncertainty=[prepared.get("reason", "")])
        return check_output(output)
    output["findings"]["proposal_id"] = prepared.get("proposal_id")
    output.update(confidence=0.85, proposed_action="staff_approval",
                   reason="Unsent draft prepared; staff must approve the exact version")
    return check_output(output)


def run_verification(db, ctx, task_input):
    """Independently re-derive balances and check links, drafts, and claims."""
    split = call_tool(db, ctx, "ledger_read_split")
    raw = call_tool(db, ctx, "ledger_read_raw")
    evidence = call_tool(db, ctx, "evidence_list")
    drafts = call_tool(db, ctx, "draft_describe")
    checks = []
    checks.append({"name": "ledger_recomputed",
                   "pass": raw["outstanding_cents"] == split["outstanding_cents"]
                           and raw["disputed_cents"] == split["disputed_cents"],
                   "detail": f"raw={raw['outstanding_cents']}/{raw['disputed_cents']}"})
    sourceless = [e["id"] for e in evidence if not e["source_reference"]]
    checks.append({"name": "evidence_linked", "pass": not sourceless,
                   "detail": f"sourceless={sourceless}"})
    from app.services import controlled_agent as _agent
    invoice = _invoice(db, ctx)
    try:
        _facts, digest, _latest = _agent.snapshot(db, invoice)
    except ValueError:
        digest = None
    stale_drafts = [d["proposal_id"] for d in drafts
                    if d["status"] == "proposed" and digest
                    and d["context_hash"] != digest
                    and d["action"] == "split_balance_draft"]
    void = [d for d in drafts if d["status"] not in ("proposed", "approved", "stale",
            "sandbox_sent", "rejected", "closed", "draft_created")]
    checks.append({"name": "no_stale_split_drafts", "pass": not stale_drafts,
                   "detail": f"stale={stale_drafts}"})
    checks.append({"name": "known_draft_states", "pass": not void,
                   "detail": f"unknown={[d['proposal_id'] for d in void]}"})
    open_explanations = [e.id for e in db.query(models.CompetingExplanation).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, status="open").all()]
    checks.append({"name": "explanations_resolved", "pass": not open_explanations,
                   "detail": f"open={open_explanations}"})
    failed = [c["name"] for c in checks if not c["pass"]]
    output = _base_output(ctx, ctx["case_version"], {"checks": checks})
    output["sources"] = [e["source_reference"] for e in evidence if e["source_reference"]]
    if failed:
        output.update(confidence=0.35, proposed_action="staff_review",
                       reason="Verification failed: " + ", ".join(failed),
                       escalate=True, escalation_conditions=["verification_failed"],
                       uncertainty=failed)
    else:
        output.update(confidence=0.95, proposed_action="none",
                       reason="Independent checks passed")
    return check_output(output)


RUNNERS = {
    "intake": run_intake,
    "investigation": run_investigation,
    "reconciliation": run_reconciliation,
    "resolution": run_resolution,
    "communication": run_communication,
    "verification": run_verification,
}


def run_specialist(db, task, ctx, task_input):
    """Dispatch one task to its specialist runner with timing."""
    runner = RUNNERS.get(task.kind)
    if runner is None:
        raise OutputRejected(f"Unknown specialist: {task.kind}")
    started = time.monotonic()
    output = runner(db, ctx, task_input or {})
    output["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    output["model_calls"] = ctx.get("model_calls", 0)
    return check_output(output)
