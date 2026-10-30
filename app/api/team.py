"""Staff team operations: assignment, notes, tasks, escalations, workload."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services import team_ops

router = APIRouter(prefix="/team", tags=["Team"])


class AssignInput(BaseModel):
    assignee_user_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=500)


class NoteInput(BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class TaskCreate(BaseModel):
    invoice_id: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(default="", max_length=5000)
    assignee_user_id: int = Field(gt=0)
    due_date: date | None = None


class ReassignInput(BaseModel):
    assignee_user_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=500)


class EscalationInput(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    deadline: date


class ResolveInput(BaseModel):
    reason: str = Field(default="", max_length=500)


def _invoice(db: Session, invoice_id: int, identity: Identity) -> models.Invoice:
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Case not found")
    return invoice


def _task(db: Session, task_id: int, identity: Identity) -> models.StaffTask:
    task = db.get(models.StaffTask, task_id)
    if not task or task.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _assignment(row: models.CaseAssignment) -> dict:
    return {"id": row.id, "invoice_id": row.invoice_id,
            "assignee_user_id": row.assignee_user_id,
            "assignee_email": row.assignee_email,
            "assigned_by": row.assigned_by, "reason": row.reason,
            "created_at": row.created_at.isoformat() if row.created_at else None}


def _note(row: models.StaffNote) -> dict:
    return {"id": row.id, "invoice_id": row.invoice_id, "body": row.body,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None}


def _task_view(row: models.StaffTask) -> dict:
    return {"id": row.id, "invoice_id": row.invoice_id, "title": row.title,
            "detail": row.detail, "assignee_user_id": row.assignee_user_id,
            "assignee_email": row.assignee_email, "created_by": row.created_by,
            "status": row.status,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "overdue": bool(row.status == "open" and row.due_date
                             and row.due_date < date.today()),
            "completed_by": row.completed_by,
            "created_at": row.created_at.isoformat() if row.created_at else None}


def _escalation(row: models.CaseEscalation) -> dict:
    return {"id": row.id, "invoice_id": row.invoice_id, "reason": row.reason,
            "deadline": row.deadline.isoformat(), "status": row.status,
            "overdue": team_ops.escalation_overdue(row),
            "created_by": row.created_by, "resolved_by": row.resolved_by,
            "created_at": row.created_at.isoformat() if row.created_at else None}


@router.post("/cases/{invoice_id}/assign", status_code=201)
def assign(invoice_id: int, payload: AssignInput,
           db: Session = Depends(get_db),
           identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    try:
        row = team_ops.assign_case(db, invoice, payload.assignee_user_id,
                                   identity.actor, payload.reason.strip())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return _assignment(row)


@router.get("/cases/{invoice_id}/assignments")
def assignment_history(invoice_id: int, db: Session = Depends(get_db),
                       identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    rows = db.query(models.CaseAssignment).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
        models.CaseAssignment.id).all()
    return [_assignment(row) for row in rows]


@router.post("/cases/{invoice_id}/notes", status_code=201)
def create_note(invoice_id: int, payload: NoteInput,
                db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    try:
        row = team_ops.add_note(db, invoice, payload.body, identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _note(row)


@router.get("/cases/{invoice_id}/notes")
def list_notes(invoice_id: int, db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    rows = db.query(models.StaffNote).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
        models.StaffNote.id).all()
    return [_note(row) for row in rows]


@router.post("/tasks", status_code=201)
def create_task(payload: TaskCreate, db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    try:
        row = team_ops.create_task(
            db, identity.tenant_id, identity.actor, payload.title,
            payload.assignee_user_id, invoice_id=payload.invoice_id,
            detail=payload.detail, due_date=payload.due_date)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _task_view(row)


@router.get("/tasks")
def list_tasks(status: str | None = None,
               assignee_user_id: int | None = None,
               db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    query = db.query(models.StaffTask).filter_by(tenant_id=identity.tenant_id)
    if status:
        query = query.filter_by(status=status)
    if assignee_user_id:
        query = query.filter_by(assignee_user_id=assignee_user_id)
    return [_task_view(row) for row in query.order_by(
        models.StaffTask.id).limit(200).all()]


@router.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    task = _task(db, task_id, identity)
    try:
        team_ops.set_task_status(db, task, "done", identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _task_view(task)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int, db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    task = _task(db, task_id, identity)
    try:
        team_ops.set_task_status(db, task, "cancelled", identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _task_view(task)


@router.post("/tasks/{task_id}/reassign")
def reassign(task_id: int, payload: ReassignInput,
             db: Session = Depends(get_db),
             identity: Identity = Depends(get_identity)):
    task = _task(db, task_id, identity)
    try:
        team_ops.reassign_task(db, task, payload.assignee_user_id,
                               identity.actor, payload.reason.strip())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.commit()
    return _task_view(task)


@router.post("/cases/{invoice_id}/escalations", status_code=201)
def raise_case_escalation(invoice_id: int, payload: EscalationInput,
                          db: Session = Depends(get_db),
                          identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    try:
        row = team_ops.raise_escalation(db, invoice, payload.reason.strip(),
                                        payload.deadline, identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return _escalation(row)


@router.get("/cases/{invoice_id}/escalations")
def list_escalations(invoice_id: int, db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    rows = db.query(models.CaseEscalation).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
        models.CaseEscalation.id).all()
    return [_escalation(row) for row in rows]


@router.post("/escalations/{escalation_id}/resolve")
def resolve_case_escalation(escalation_id: int, payload: ResolveInput,
                            db: Session = Depends(get_db),
                            identity: Identity = Depends(get_identity)):
    row = db.get(models.CaseEscalation, escalation_id)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Escalation not found")
    try:
        team_ops.resolve_escalation(db, row, identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _escalation(row)


@router.post("/escalations/sweep")
def sweep_escalations(db: Session = Depends(get_db),
                      identity: Identity = Depends(get_identity)):
    flipped = team_ops.sweep_overdue_escalations(db, identity.tenant_id,
                                                 identity.actor)
    db.commit()
    return {"escalated": flipped}


@router.get("/workload")
def workload(db: Session = Depends(get_db),
             identity: Identity = Depends(get_identity)):
    return team_ops.workload(db, identity.tenant_id)
