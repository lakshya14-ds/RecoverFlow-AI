"""Deterministic supervisor over durable specialist tasks.

The supervisor selects the next bounded task from case stage, evidence,
uncertainty, payment state, and staff decisions. Selection is a pure function
of stored state: same case, same next task. Nothing here posts ledger entries,
approves credits, waives balances, or sends messages; specialists are advisory
except for the pre-existing intake/investigation paths they wrap, which keep
their own guards.

Completion and escalation rules live in COMPLETION_RULES / ESCALATION_RULES.
"""
import json
from datetime import datetime, timezone

from app.database import models
from app.services import specialists

COMPLETION_RULES = {
    "closed_case": "Stage is RESOLVED_PAID or RESOLVED_ADJUSTED: no further tasks.",
    "steady_case": "Verification passed on the current case version with no pending need.",
    "blocked_case": "Stage is NEEDS_REVIEW or CONTACT_PAUSED: staff owns the case.",
}

ESCALATION_RULES = {
    "retry_exhausted": "Attempts reached max_attempts: fail, hold contact, staff review.",
    "specialist_escalation": "Specialist output escalate=true: hold contact with its reason.",
    "stale_output": "Case version changed under a task: record as stale, reassess fresh.",
    "tool_denied": "Tool outside the specialist allowlist: fail closed, audit, hold.",
    "ambiguous_match": "No single exact payment candidate: staff choose (M3 deepens this).",
}

TERMINAL = ("done", "failed", "escalated", "stale")
RUNNABLE = ("queued",)


def _now():
    return datetime.now(timezone.utc)


def _audit(db, tenant_id, actor, action, task, details=""):
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor, action=action,
        entity_type="supervisor_task", entity_id=str(task.id if task else 0),
        details=details[:500]))


def _hold(db, invoice, reason, actor):
    invoice.investigation_hold = True
    invoice.investigation_reason = reason[:500]
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="supervisor_escalated", entity_type="invoice",
        entity_id=str(invoice.id), details=reason[:500]))
    from app.services.case_lifecycle import checkpoint
    checkpoint(db, invoice, "supervisor_escalated", actor)


def _tasks_for_version(db, invoice, version):
    return db.query(models.SupervisorTask).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id,
        case_version=version).all()


def select_next(db, invoice):
    """Return (kind, task_input, depends_on, reason) or (None, outcome, reason).

    Deterministic: stage first, then evidence freshness, payment state,
    then the resolution -> communication -> verification chain.
    """
    from app.services.case_lifecycle import derive_stage, fingerprint
    from app.services.receivables import split_balance
    split = split_balance(db, invoice, allow_inconsistent=True)
    stage = derive_stage(split, invoice)
    version = fingerprint(db, invoice)
    if stage in ("RESOLVED_PAID", "RESOLVED_ADJUSTED"):
        return None, "complete", COMPLETION_RULES["closed_case"]
    if stage in ("NEEDS_REVIEW", "CONTACT_PAUSED"):
        return None, "escalated", COMPLETION_RULES["blocked_case"]
    done = {(t.kind, t.status) for t in _tasks_for_version(db, invoice, version)}
    latest = {}
    for task in _tasks_for_version(db, invoice, version):
        if task.status == "done":
            latest[task.kind] = task.id
    # Evidence freshness: new or changed documents invalidate prior decisions.
    from app.services.investigation import document_digest
    if invoice.investigation_decision_hash != document_digest(db, invoice):
        linked = bool(db.query(models.IntakeUpload).filter_by(
            tenant_id=invoice.tenant_id).filter(
            models.IntakeUpload.extraction_json.isnot(None)).first())
        if linked and ("investigation", "done") not in done:
            return ("investigation", {}, [], "Linked documents changed since the last decision")
    if ("reconciliation", "done") not in done:
        pending = db.query(models.Reconciliation).filter_by(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id,
            status="pending_review").first()
        leg = db.query(models.AllocationLeg).filter_by(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id,
            status="pending").first()
        if pending or leg:
            return ("reconciliation", {}, [], "Pending reconciliations need scoring")
    if ("resolution", "done") not in done:
        return ("resolution", {}, [], "Compute the collectible request from server facts")
    if ("communication", "done") not in done:
        deps = [latest["resolution"]] if "resolution" in latest else []
        return ("communication", {}, deps, "Draft the validated request for staff approval")
    if ("verification", "done") not in done:
        deps = [latest[k] for k in ("resolution", "communication") if k in latest]
        return ("verification", {}, deps, "Independently verify the fresh outputs")
    return None, "steady", COMPLETION_RULES["steady_case"]


def _key_for_task(tenant_id, invoice_id, kind, version):
    return f"{tenant_id}:{invoice_id}:{kind}:{version}"


def reassess(db, invoice, trigger, actor="supervisor"):
    """Idempotently queue the next task for the current case version."""
    from app.services.case_lifecycle import fingerprint
    if invoice.invoice_type != "AR":
        return {"outcome": "ignored", "reason": "Not a receivable case"}
    version = fingerprint(db, invoice)
    selected = select_next(db, invoice)
    if selected[0] is None:
        _audit(db, invoice.tenant_id, actor, "supervisor_reassessed", None,
               f"trigger={trigger}; outcome={selected[1]}")
        db.flush()
        return {"outcome": selected[1], "reason": selected[2]}
    kind, task_input, depends_on, reason = selected
    key = _key_for_task(invoice.tenant_id, invoice.id, kind, version)
    existing = db.query(models.SupervisorTask).filter_by(
        tenant_id=invoice.tenant_id, idempotency_key=key).first()
    if existing:
        return {"outcome": "duplicate", "task_id": existing.id,
                "status": existing.status, "kind": kind}
    # Older queued work for this kind is superseded by the new version.
    for stale in db.query(models.SupervisorTask).filter_by(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id, kind=kind,
            status="queued").all():
        if stale.case_version != version:
            stale.status = "stale"
            _audit(db, invoice.tenant_id, actor, "supervisor_task_staled", stale,
                   f"superseded by version {version[:12]}")
    task = models.SupervisorTask(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, kind=kind,
        status="queued", idempotency_key=key, input_json=json.dumps(task_input),
        depends_on_json=json.dumps(depends_on), trigger=str(trigger)[:200],
        case_version=version)
    db.add(task)
    db.flush()
    _audit(db, invoice.tenant_id, actor, "supervisor_task_queued", task,
           f"kind={kind}; trigger={trigger}; {reason}"[:500])
    db.flush()
    return {"outcome": "queued", "task_id": task.id, "kind": kind, "reason": reason}


def request_reassessment(db, invoice, trigger, actor="supervisor"):
    """Trigger hook for ledger, reply, document, and staff-decision events."""
    return reassess(db, invoice, trigger, actor)


def request_intake_task(db, tenant_id, upload_id, actor="supervisor"):
    """Queue durable processing for one upload (idempotent per upload)."""
    key = f"{tenant_id}:upload:{upload_id}"
    existing = db.query(models.SupervisorTask).filter_by(
        tenant_id=tenant_id, idempotency_key=key).first()
    if existing:
        return {"outcome": "duplicate", "task_id": existing.id, "status": existing.status}
    task = models.SupervisorTask(
        tenant_id=tenant_id, invoice_id=None, kind="intake", status="queued",
        idempotency_key=key, input_json=json.dumps({"upload_id": upload_id}),
        trigger="upload")
    db.add(task)
    db.flush()
    _audit(db, tenant_id, actor, "supervisor_task_queued", task, f"kind=intake; upload={upload_id}")
    db.flush()
    return {"outcome": "queued", "task_id": task.id, "kind": "intake"}


def _deps_met(db, task):
    try:
        deps = json.loads(task.depends_on_json or "[]")
    except ValueError:
        return False
    for dep_id in deps:
        dep = db.query(models.SupervisorTask).filter_by(
            tenant_id=task.tenant_id, id=dep_id).first()
        if not dep or dep.status != "done":
            return False
    return True


def _execute(db, task, actor):
    from app.services.case_lifecycle import fingerprint
    invoice = db.get(models.Invoice, task.invoice_id) if task.invoice_id else None
    if task.invoice_id and (not invoice or invoice.tenant_id != task.tenant_id):
        raise ValueError("Receivable case not found")
    version_at_start = fingerprint(db, invoice) if invoice else None
    if task.case_version and version_at_start and task.case_version != version_at_start:
        task.status = "stale"
        task.completed_at = _now()
        _audit(db, task.tenant_id, actor, "supervisor_task_staled", task,
               "Case version changed before pickup")
        db.flush()
        reassess(db, invoice, f"stale:{task.kind}", actor)
        return "stale_at_pickup"
    ctx = {"specialist": task.kind, "tenant_id": task.tenant_id,
           "invoice_id": task.invoice_id, "task_id": task.id, "actor": actor,
           "model_calls": 0, "model_budget": task.model_budget,
           "case_version": version_at_start or task.case_version,
           "case_version_hint": task.case_version}
    task.status = "running"
    task.started_at = _now()
    task.attempts += 1
    if invoice:
        task.case_version = version_at_start
    db.flush()
    try:
        task_input = json.loads(task.input_json or "{}")
    except ValueError:
        task_input = {}
    output = specialists.run_specialist(db, task, ctx, task_input)
    task.model_calls = ctx.get("model_calls", 0)
    elapsed_ms = (output.get("elapsed_ms") or 0)
    if elapsed_ms > task.time_budget_ms:
        raise TimeoutError(f"Task exceeded its {task.time_budget_ms} ms budget")
    if task.kind == "intake" and output.get("case_id") and not task.invoice_id:
        task.invoice_id = output["case_id"]
        invoice = db.get(models.Invoice, task.invoice_id)
        task.case_version = fingerprint(db, invoice) if invoice else task.case_version
    elif invoice and fingerprint(db, invoice) != version_at_start:
        task.status = "stale"
        task.result_json = json.dumps(output)
        task.completed_at = _now()
        _audit(db, task.tenant_id, actor, "supervisor_task_staled", task,
               "Case version changed during execution")
        db.flush()
        reassess(db, invoice, f"stale:{task.kind}", actor)
        return "stale"
    task.result_json = json.dumps(output)
    task.completed_at = _now()
    if output.get("escalate"):
        task.status = "escalated"
        _audit(db, task.tenant_id, actor, "supervisor_task_escalated", task,
               "; ".join(output.get("escalation_conditions", [])))
        if invoice:
            _hold(db, invoice, output.get("reason", "Specialist escalation"), actor)
    else:
        task.status = "done"
        task.applied = task.kind in ("intake", "investigation")
        _audit(db, task.tenant_id, actor, "supervisor_task_done", task,
               f"action={output.get('proposed_action')}")
    db.flush()
    return task.status


def run_task(db, task_id, actor="supervisor"):
    """Execute one queued task with retry, stale, and escalation handling."""
    task = db.get(models.SupervisorTask, task_id)
    if not task:
        raise ValueError("Supervisor task not found")
    if task.status == "paused":
        return {"outcome": "paused", "task_id": task.id}
    if task.status not in RUNNABLE:
        return {"outcome": task.status, "task_id": task.id}
    if not _deps_met(db, task):
        return {"outcome": "waiting", "task_id": task.id}
    try:
        outcome = _execute(db, task, actor)
        return {"outcome": outcome, "task_id": task.id}
    except (specialists.ToolDenied, specialists.OutputRejected) as exc:
        task.status = "failed"
        task.error = f"{type(exc).__name__}: {exc}"[:500]
        task.completed_at = _now()
        _audit(db, task.tenant_id, actor, "supervisor_task_failed", task, task.error)
        invoice = db.get(models.Invoice, task.invoice_id) if task.invoice_id else None
        if invoice:
            _hold(db, invoice, f"Specialist contract violated: {exc}", actor)
        db.flush()
        return {"outcome": "failed", "task_id": task.id, "error": task.error}
    except Exception as exc:  # noqa: BLE001 - bounded retry with audit
        task.error = f"{type(exc).__name__}: {exc}"[:500]
        if task.attempts >= task.max_attempts:
            task.status = "failed"
            task.completed_at = _now()
            _audit(db, task.tenant_id, actor, "supervisor_task_failed", task,
                   f"exhausted after {task.attempts} attempts; {task.error}")
            invoice = db.get(models.Invoice, task.invoice_id) if task.invoice_id else None
            if invoice:
                _hold(db, invoice, f"Task {task.kind} failed after {task.attempts} attempts", actor)
        else:
            task.status = "queued"
            _audit(db, task.tenant_id, actor, "supervisor_task_retry", task,
                   f"attempt {task.attempts}/{task.max_attempts}; {task.error}")
        db.flush()
        return {"outcome": task.status, "task_id": task.id, "error": task.error}


def run_due_tasks(db, tenant_id, limit=5, actor="supervisor"):
    """Run runnable queued tasks oldest-first; returns per-task outcomes."""
    outcomes = []
    queued = db.query(models.SupervisorTask).filter_by(
        tenant_id=tenant_id, status="queued").order_by(
        models.SupervisorTask.id).all()
    for task in queued:
        if len(outcomes) >= max(1, limit):
            break
        if not _deps_met(db, task):
            continue
        outcomes.append(run_task(db, task.id, actor))
        db.flush()
        if task.invoice_id and outcomes[-1]["outcome"] in ("done", "stale"):
            invoice = db.get(models.Invoice, task.invoice_id)
            if invoice and invoice.tenant_id == tenant_id:
                reassess(db, invoice, f"task:{task.kind}:{task.id}", actor)
                db.flush()
    return outcomes


def run_due_thread(limit=5):
    """Self-contained worker tick for the background loop."""
    from app.database.db_manager import SessionLocal
    with SessionLocal() as db:
        try:
            outcomes = []
            tenants = [row[0] for row in db.query(models.SupervisorTask.tenant_id).filter_by(
                status="queued").distinct().all()]
            for tenant in tenants:
                outcomes.extend(run_due_tasks(db, tenant, limit=limit))
            db.commit()
            return outcomes
        except Exception:
            db.rollback()
            raise


def recover_interrupted_tasks(db=None):
    """Return tasks left running by a dead process to the durable queue."""
    from app.database.db_manager import SessionLocal
    owned = db is None
    db = db or SessionLocal()
    try:
        rows = db.query(models.SupervisorTask).filter_by(status="running").all()
        for row in rows:
            row.status = "queued"
            _audit(db, row.tenant_id, "supervisor",
                   "supervisor_task_recovered", row,
                   f"attempts={row.attempts}; replay after restart")
        db.commit()
        return len(rows)
    finally:
        if owned:
            db.close()


def pause_task(db, task, actor):
    if task.status not in ("queued", "running"):
        raise ValueError("Only queued or running tasks can pause")
    task.status = "paused"
    _audit(db, task.tenant_id, actor, "supervisor_task_paused", task, "")
    db.flush()
    return task


def resume_task(db, task, actor):
    if task.status != "paused":
        raise ValueError("Only paused tasks can resume")
    task.status = "queued"
    _audit(db, task.tenant_id, actor, "supervisor_task_resumed", task, "")
    db.flush()
    return task


def retry_task(db, task, actor):
    if task.status != "failed":
        raise ValueError("Only failed tasks can retry")
    task.status = "queued"
    task.attempts = 0
    task.error = None
    _audit(db, task.tenant_id, actor, "supervisor_task_retry", task,
           "manual retry with a fresh attempt budget")
    db.flush()
    return task
