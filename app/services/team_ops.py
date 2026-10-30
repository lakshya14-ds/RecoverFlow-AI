"""Team operations: assignment, notes, tasks, escalations, workload, SoD.

Assignments and notes are insert-only; history is never rewritten. SoD
(separation of duties) blocks self-approval only when the tenant has more
than one active staff user; lone operators proceed with an audit note.
"""
from datetime import date, datetime, timezone

from app.database import models


def _user(db, tenant_id, user_id):
    user = db.get(models.User, user_id)
    if not user or user.tenant_id != tenant_id or not user.is_active:
        raise LookupError("Staff user not found")
    return user


def current_assignment(db, tenant_id, invoice_id):
    return db.query(models.CaseAssignment).filter_by(
        tenant_id=tenant_id, invoice_id=invoice_id).order_by(
        models.CaseAssignment.id.desc()).first()


def assign_case(db, invoice, assignee_id, actor, reason):
    user = _user(db, invoice.tenant_id, assignee_id)
    previous = current_assignment(db, invoice.tenant_id, invoice.id)
    row = models.CaseAssignment(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id,
        assignee_user_id=user.id, assignee_email=user.email,
        assigned_by=actor, reason=reason)
    db.add(row)
    before = previous.assignee_email if previous else "unassigned"
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="case_assigned", entity_type="invoice", entity_id=str(invoice.id),
        details=f"before={before}; after={user.email}; reason={reason}"))
    db.flush()
    return row


def add_note(db, invoice, body, actor):
    if not body or not body.strip():
        raise ValueError("Note body is required")
    row = models.StaffNote(tenant_id=invoice.tenant_id, invoice_id=invoice.id,
                           body=body.strip(), created_by=actor)
    db.add(row)
    db.flush()
    return row


def create_task(db, tenant_id, actor, title, assignee_id, invoice_id=None,
               detail="", due_date=None):
    if not title or not title.strip():
        raise ValueError("Task title is required")
    user = _user(db, tenant_id, assignee_id)
    invoice = None
    if invoice_id is not None:
        invoice = db.get(models.Invoice, invoice_id)
        if not invoice or invoice.tenant_id != tenant_id:
            raise LookupError("Case not found")
    row = models.StaffTask(
        tenant_id=tenant_id, invoice_id=invoice.id if invoice else None,
        title=title.strip()[:200], detail=(detail or "").strip(),
        assignee_user_id=user.id, assignee_email=user.email,
        created_by=actor, due_date=due_date)
    db.add(row)
    db.flush()
    return row


def reassign_task(db, task, assignee_id, actor, reason):
    user = _user(db, task.tenant_id, assignee_id)
    before = task.assignee_email
    task.assignee_user_id = user.id
    task.assignee_email = user.email
    db.add(models.AuditEvent(tenant_id=task.tenant_id, actor=actor,
        action="task_reassigned", entity_type="staff_task",
        entity_id=str(task.id),
        details=f"before={before}; after={user.email}; reason={reason}"))
    db.flush()
    return task


def set_task_status(db, task, status, actor):
    if status not in ("done", "cancelled"):
        raise ValueError("Unknown task status")
    if task.status != "open":
        raise ValueError("Only open tasks can be completed or cancelled")
    task.status = status
    task.completed_by = actor
    task.completed_at = datetime.now(timezone.utc)
    db.flush()
    return task


def raise_escalation(db, invoice, reason, deadline, actor):
    if not reason or not reason.strip():
        raise ValueError("Escalation reason is required")
    row = models.CaseEscalation(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id,
        reason=reason.strip(), deadline=deadline, created_by=actor)
    db.add(row)
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="escalation_raised", entity_type="invoice",
        entity_id=str(invoice.id),
        details=f"deadline={deadline.isoformat()}; {reason.strip()}"[:500]))
    db.flush()
    return row


def resolve_escalation(db, escalation, actor):
    if escalation.status == "resolved":
        raise ValueError("Escalation is already resolved")
    escalation.status = "resolved"
    escalation.resolved_by = actor
    escalation.resolved_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=escalation.tenant_id, actor=actor,
        action="escalation_resolved", entity_type="case_escalation",
        entity_id=str(escalation.id)))
    db.flush()
    return escalation


def sweep_overdue_escalations(db, tenant_id, actor):
    """Flip past-deadline open escalations; flag their cases for review."""
    today = date.today()
    rows = db.query(models.CaseEscalation).filter_by(
        tenant_id=tenant_id, status="open").filter(
        models.CaseEscalation.deadline < today).all()
    for row in rows:
        row.status = "escalated"
        invoice = db.get(models.Invoice, row.invoice_id)
        if invoice and invoice.tenant_id == tenant_id:
            invoice.requires_human_review = True
        db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
            action="escalation_overdue", entity_type="case_escalation",
            entity_id=str(row.id),
            details=f"deadline={row.deadline.isoformat()}"))
    db.flush()
    return [row.id for row in rows]


def escalation_overdue(row):
    return row.status == "open" and row.deadline < date.today()


def workload(db, tenant_id):
    """Open work per assignee email: tasks, overdue items, cases, escalations."""
    today = date.today()
    people = {}

    def bucket(email):
        return people.setdefault(email, {"assignee_email": email, "open_tasks": 0,
                                         "overdue_tasks": 0, "assigned_cases": 0,
                                         "open_escalations": 0})

    for task in db.query(models.StaffTask).filter_by(
            tenant_id=tenant_id, status="open").all():
        entry = bucket(task.assignee_email)
        entry["open_tasks"] += 1
        if task.due_date and task.due_date < today:
            entry["overdue_tasks"] += 1
    seen_invoices = set()
    for row in db.query(models.CaseAssignment).filter_by(
            tenant_id=tenant_id).order_by(models.CaseAssignment.id.desc()).all():
        if row.invoice_id in seen_invoices:
            continue
        seen_invoices.add(row.invoice_id)
        bucket(row.assignee_email)["assigned_cases"] += 1
    for row in db.query(models.CaseEscalation).filter_by(
            tenant_id=tenant_id).filter(
            models.CaseEscalation.status.in_(("open", "escalated"))).all():
        current = current_assignment(db, tenant_id, row.invoice_id)
        bucket(current.assignee_email if current else "unassigned")[
            "open_escalations"] += 1
    return sorted(people.values(), key=lambda item: (
        -item["open_escalations"], -item["overdue_tasks"], -item["open_tasks"],
        item["assignee_email"]))


def sod_allows(db, tenant_id, creator, approver, action, entity_id):
    """True unless the same person created and approves with backup available.

    Lone-operator tenants (<2 active users) proceed with an audit note so a
    solo owner is never deadlocked; the conflict is still tested with teams.
    """
    if not creator or creator != approver:
        return True, ""
    staff = db.query(models.User).filter_by(
        tenant_id=tenant_id, is_active=True).count()
    if staff < 2:
        db.add(models.AuditEvent(tenant_id=tenant_id, actor=approver,
            action="sod_skipped_lone_operator", entity_type="approval",
            entity_id=str(entity_id), details=action))
        db.flush()
        return True, ""
    return False, (f"Separation of duties: {approver} created this {action}; "
                   f"another staff member must approve it")
