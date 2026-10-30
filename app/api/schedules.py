"""Installment schedules: dated legs over promised cash (nonfinancial)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
from app.database.db_manager import get_db
from app.services import schedules

router = APIRouter(prefix="/cases", tags=["Schedules"])


class LegInput(BaseModel):
    due_date: date
    amount_cents: int = Field(gt=0)


class ScheduleCreate(BaseModel):
    legs: list[LegInput] = Field(min_length=1)
    terms: str = Field(default="", max_length=2000)
    promise_id: int | None = Field(default=None, gt=0)


class ScheduleDecision(BaseModel):
    reason: str = Field(default="", max_length=500)


class RescheduleInput(BaseModel):
    new_due_date: date
    reason: str = Field(default="", max_length=500)


def _invoice(db: Session, invoice_id: int, identity: Identity) -> models.Invoice:
    invoice = db.get(models.Invoice, invoice_id)
    if not invoice or invoice.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Case not found")
    return invoice


def _schedule(db: Session, invoice: models.Invoice,
              schedule_id: int) -> models.InstallmentSchedule:
    schedule = db.get(models.InstallmentSchedule, schedule_id)
    if not schedule or schedule.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return schedule


@router.post("/{invoice_id}/schedules", status_code=201)
def create_schedule(invoice_id: int, payload: ScheduleCreate,
                    db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    try:
        row = schedules.create_schedule(
            db, invoice, identity.actor,
            [item.model_dump() for item in payload.legs],
            terms=payload.terms, promise_id=payload.promise_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return schedules.schedule_view(db, row)


@router.get("/{invoice_id}/schedules")
def list_schedules(invoice_id: int, db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    rows = db.query(models.InstallmentSchedule).filter_by(
        tenant_id=identity.tenant_id, invoice_id=invoice.id).order_by(
        models.InstallmentSchedule.id).all()
    return [schedules.schedule_view(db, row) for row in rows]


@router.get("/{invoice_id}/schedules/{schedule_id}")
def get_schedule(invoice_id: int, schedule_id: int,
                 db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    return schedules.schedule_view(db, _schedule(db, invoice, schedule_id))


@router.post("/{invoice_id}/schedules/{schedule_id}/approve")
def approve_schedule(invoice_id: int, schedule_id: int,
                     payload: ScheduleDecision,
                     db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    try:
        row = schedules.approve_schedule(
            db, _schedule(db, invoice, schedule_id), identity.actor)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return schedules.schedule_view(db, row)


@router.post("/{invoice_id}/schedules/{schedule_id}/cancel")
def cancel_schedule(invoice_id: int, schedule_id: int,
                    payload: ScheduleDecision,
                    db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    try:
        row = schedules.cancel_schedule(
            db, _schedule(db, invoice, schedule_id), identity.actor,
            payload.reason.strip())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return schedules.schedule_view(db, row)


@router.post("/{invoice_id}/schedules/{schedule_id}/legs/{leg_id}/reschedule")
def reschedule_leg(invoice_id: int, schedule_id: int, leg_id: int,
                   payload: RescheduleInput,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    invoice = _invoice(db, invoice_id, identity)
    schedule = _schedule(db, invoice, schedule_id)
    leg = db.get(models.InstallmentLeg, leg_id)
    if not leg or leg.schedule_id != schedule.id:
        raise HTTPException(status_code=404, detail="Leg not found")
    try:
        fresh = schedules.reschedule_leg(db, leg, payload.new_due_date,
                                         identity.actor)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return schedules.leg_view(fresh)
