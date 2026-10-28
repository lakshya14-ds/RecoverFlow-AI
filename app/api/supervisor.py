"""Tenant-scoped supervisor task history and review gates."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.cases import _invoice as _case_invoice
from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services import supervisor

router = APIRouter(prefix="/supervisor", tags=["Supervisor"])


class ReassessInput(BaseModel):
    trigger: str = Field(min_length=1, max_length=200)


class RunDueInput(BaseModel):
    limit: int = Field(default=5, ge=1, le=25)


def _task(db: Session, task_id: int, identity: Identity) -> models.SupervisorTask:
    task = db.get(models.SupervisorTask, task_id)
    if not task or task.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Supervisor task not found")
    return task


def _public(task: models.SupervisorTask) -> dict:
    return {"id": task.id, "invoice_id": task.invoice_id, "kind": task.kind,
            "status": task.status, "trigger": task.trigger,
            "attempts": task.attempts, "max_attempts": task.max_attempts,
            "model_calls": task.model_calls, "model_budget": task.model_budget,
            "case_version": task.case_version, "applied": bool(task.applied),
            "error": task.error, "result": task.result_json,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None}


@router.post("/cases/{invoice_id}/reassess")
def reassess_case(invoice_id: int, payload: ReassessInput,
                  db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    invoice = _case_invoice(db, invoice_id, identity)
    outcome = supervisor.reassess(db, invoice, payload.trigger, identity.actor)
    db.commit()
    if outcome.get("task_id"):
        outcome["task"] = _public(db.get(models.SupervisorTask, outcome["task_id"]))
    return outcome


@router.get("/cases/{invoice_id}/tasks")
def case_tasks(invoice_id: int, db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    _case_invoice(db, invoice_id, identity)
    rows = db.query(models.SupervisorTask).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice_id).order_by(
        models.SupervisorTask.id).all()
    return [_public(row) for row in rows]


@router.get("/queue")
def owner_queue(db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    from app.services.action_queue import queue_for_tenant
    return queue_for_tenant(db, identity.tenant_id)


@router.get("/tasks")
def list_tasks(status: str | None = None, kind: str | None = None,
               db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    query = db.query(models.SupervisorTask).filter_by(tenant_id=identity.tenant_id)
    if status:
        query = query.filter_by(status=status)
    if kind:
        query = query.filter_by(kind=kind)
    return [_public(row) for row in query.order_by(
        models.SupervisorTask.id.desc()).limit(200).all()]


@router.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db),
             identity: Identity = Depends(get_identity)):
    return _public(_task(db, task_id, identity))


@router.post("/tasks/{task_id}/pause")
def pause(task_id: int, db: Session = Depends(get_db),
          identity: Identity = Depends(get_identity)):
    try:
        task = supervisor.pause_task(db, _task(db, task_id, identity), identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _public(task)


@router.post("/tasks/{task_id}/resume")
def resume(task_id: int, db: Session = Depends(get_db),
           identity: Identity = Depends(get_identity)):
    try:
        task = supervisor.resume_task(db, _task(db, task_id, identity), identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _public(task)


@router.post("/tasks/{task_id}/retry")
def retry(task_id: int, db: Session = Depends(get_db),
          identity: Identity = Depends(get_identity)):
    try:
        task = supervisor.retry_task(db, _task(db, task_id, identity), identity.actor)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _public(task)


@router.post("/tasks/{task_id}/run")
def run(task_id: int, db: Session = Depends(get_db),
        identity: Identity = Depends(get_identity)):
    task = _task(db, task_id, identity)
    outcome = supervisor.run_task(db, task.id, identity.actor)
    if task.invoice_id and outcome.get("outcome") in ("done", "stale"):
        invoice = db.get(models.Invoice, task.invoice_id)
        if invoice and invoice.tenant_id == identity.tenant_id:
            supervisor.reassess(db, invoice, f"task:{task.kind}:{task.id}", identity.actor)
    db.commit()
    outcome["task"] = _public(db.get(models.SupervisorTask, task.id))
    return outcome


@router.post("/run-due")
def run_due(payload: RunDueInput, db: Session = Depends(get_db),
            identity: Identity = Depends(get_identity)):
    outcomes = supervisor.run_due_tasks(db, identity.tenant_id,
                                        limit=payload.limit, actor=identity.actor)
    db.commit()
    return {"processed": len(outcomes), "outcomes": outcomes}
