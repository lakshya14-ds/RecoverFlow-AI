"""Installment schedules: promised cash broken into dated legs.

Schedules are NONFINANCIAL: they never touch cash, balances, or case stages.
Verified payments auto-apply to legs (oldest due first); reversals un-apply
while keeping history rows. Late/missed are computed at read time.
"""
from datetime import date, datetime, timedelta, timezone

from app.database import models
from app.services.receivables import split_balance

MISSED_AFTER_DAYS = 30


def _legs(db, schedule_id):
    return db.query(models.InstallmentLeg).filter_by(
        schedule_id=schedule_id).order_by(models.InstallmentLeg.seq).all()


def _recalc_leg(db, leg):
    paid = sum(row.amount_cents for row in
               db.query(models.InstallmentApplication).filter_by(
                   leg_id=leg.id, reversed=False).all())
    leg.paid_cents = paid
    if leg.status in ("rescheduled", "cancelled"):
        return leg
    if paid >= leg.amount_cents:
        leg.status = "paid"
    elif paid > 0:
        leg.status = "partial"
    else:
        leg.status = "pending"
    return leg


def _maybe_complete(db, schedule):
    if schedule.status != "active":
        return schedule
    legs = _legs(db, schedule.id)
    if legs and all(leg.status in ("paid", "cancelled") for leg in legs):
        schedule.status = "completed"
        db.add(models.AuditEvent(tenant_id=schedule.tenant_id,
            actor="installment_engine", action="schedule_completed",
            entity_type="installment_schedule",
            entity_id=str(schedule.id)))
    return schedule


def create_schedule(db, invoice, actor, legs, terms="", promise_id=None):
    if not legs:
        raise ValueError("Schedule needs at least one leg")
    parsed = []
    for position, leg in enumerate(legs, start=1):
        try:
            amount = int(leg["amount_cents"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Leg amounts must be positive integers") from exc
        if amount <= 0:
            raise ValueError("Leg amounts must be positive")
        due = leg.get("due_date")
        if not isinstance(due, date):
            raise ValueError("Leg due dates are required")
        parsed.append((position, due, amount))
    split = split_balance(db, invoice)
    if sum(amount for _, _, amount in parsed) > split["outstanding_cents"]:
        raise ValueError("Schedule total exceeds the outstanding balance")
    promise = None
    if promise_id is not None:
        promise = db.get(models.PromiseToPay, promise_id)
        if not promise or promise.tenant_id != invoice.tenant_id \
                or promise.invoice_id != invoice.id:
            raise LookupError("Promise not found")
    schedule = models.InstallmentSchedule(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id,
        promise_id=promise.id if promise else None,
        terms=(terms or "")[:2000], status="proposed", created_by=actor)
    db.add(schedule)
    db.flush()
    for position, due, amount in parsed:
        db.add(models.InstallmentLeg(
            schedule_id=schedule.id, seq=position, due_date=due,
            amount_cents=amount, paid_cents=0, status="pending"))
    db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor=actor,
        action="schedule_created", entity_type="installment_schedule",
        entity_id=str(schedule.id),
        details=f"legs={len(parsed)}; invoice={invoice.invoice_number}"))
    db.flush()
    return schedule


def approve_schedule(db, schedule, actor):
    if schedule.status != "proposed":
        raise ValueError("Only proposed schedules can be approved")
    from app.services import team_ops
    allowed, why = team_ops.sod_allows(
        db, schedule.tenant_id, schedule.created_by, actor,
        "schedule approval", f"schedule:{schedule.id}")
    if not allowed:
        raise ValueError(why)
    schedule.status = "active"
    schedule.approved_by = actor
    schedule.approved_at = datetime.now(timezone.utc)
    db.add(models.AuditEvent(tenant_id=schedule.tenant_id, actor=actor,
        action="schedule_approved", entity_type="installment_schedule",
        entity_id=str(schedule.id)))
    db.flush()
    return schedule


def cancel_schedule(db, schedule, actor, reason):
    if schedule.status not in ("proposed", "active"):
        raise ValueError("Only proposed or active schedules can be cancelled")
    for leg in _legs(db, schedule.id):
        if leg.status in ("pending", "partial"):
            leg.status = "cancelled"
    schedule.status = "cancelled"
    db.add(models.AuditEvent(tenant_id=schedule.tenant_id, actor=actor,
        action="schedule_cancelled", entity_type="installment_schedule",
        entity_id=str(schedule.id), details=str(reason or "")[:500]))
    db.flush()
    return schedule


def reschedule_leg(db, leg, new_due_date, actor):
    if leg.status != "pending":
        raise ValueError("Only pending legs can be rescheduled")
    schedule = db.get(models.InstallmentSchedule, leg.schedule_id)
    if not schedule or schedule.status != "active":
        raise ValueError("Only legs of active schedules reschedule")
    leg.status = "rescheduled"
    siblings = _legs(db, schedule.id)
    fresh = models.InstallmentLeg(
        schedule_id=schedule.id, seq=max(item.seq for item in siblings) + 1,
        due_date=new_due_date, amount_cents=leg.amount_cents, paid_cents=0,
        status="pending", supersedes_id=leg.id)
    db.add(fresh)
    db.add(models.AuditEvent(tenant_id=schedule.tenant_id, actor=actor,
        action="leg_rescheduled", entity_type="installment_leg",
        entity_id=str(leg.id),
        details=f"new_due={new_due_date.isoformat()}; new_leg_seq={fresh.seq}"))
    db.flush()
    _recalc_leg(db, leg)
    _recalc_leg(db, fresh)
    db.flush()
    return fresh


def apply_entry(db, entry):
    """Waterfall one payment entry across active schedules, oldest due first."""
    if entry.kind != "payment":
        return []
    invoice = db.get(models.Invoice, entry.invoice_id)
    if not invoice:
        return []
    applied = sum(row.amount_cents for row in
                  db.query(models.InstallmentApplication).filter_by(
                      entry_id=entry.id, reversed=False).all())
    remaining = -entry.amount_cents - applied
    if remaining <= 0:
        return []
    created = []
    schedules = db.query(models.InstallmentSchedule).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id,
        status="active").order_by(models.InstallmentSchedule.id).all()
    for schedule in schedules:
        legs = db.query(models.InstallmentLeg).filter_by(
            schedule_id=schedule.id).filter(
            models.InstallmentLeg.status.in_(("pending", "partial"))).order_by(
            models.InstallmentLeg.due_date,
            models.InstallmentLeg.seq).all()
        for leg in legs:
            if remaining <= 0:
                break
            room = leg.amount_cents - leg.paid_cents
            if room <= 0:
                continue
            take = min(room, remaining)
            row = db.query(models.InstallmentApplication).filter_by(
                entry_id=entry.id, leg_id=leg.id, reversed=False).first()
            if row:
                row.amount_cents += take
            else:
                row = models.InstallmentApplication(
                    leg_id=leg.id, entry_id=entry.id, amount_cents=take)
                db.add(row)
            db.flush()
            _recalc_leg(db, leg)
            remaining -= take
            created.append(row)
        _maybe_complete(db, schedule)
        if remaining <= 0:
            break
    db.flush()
    return created


def unapply_entry(db, entry):
    """A reversal un-applies the original payment, keeping history rows."""
    if entry.kind != "reversal" or not entry.reversal_of_id:
        return []
    original = db.get(models.ReceivableEntry, entry.reversal_of_id)
    if not original or original.invoice_id != entry.invoice_id:
        return []
    flipped = []
    touched = set()
    rows = db.query(models.InstallmentApplication).filter_by(
        entry_id=original.id, reversed=False).all()
    for row in rows:
        row.reversed = True
    # Sessions run with autoflush=False: the flips must hit the database
    # before _recalc_leg re-queries, or legs keep their paid totals.
    db.flush()
    for row in rows:
        leg = db.get(models.InstallmentLeg, row.leg_id)
        if leg:
            _recalc_leg(db, leg)
            touched.add(leg.schedule_id)
        flipped.append(row)
    for schedule_id in touched:
        schedule = db.get(models.InstallmentSchedule, schedule_id)
        if schedule and schedule.status == "completed" and any(
                leg.status in ("pending", "partial")
                for leg in _legs(db, schedule.id)):
            schedule.status = "active"
            db.add(models.AuditEvent(tenant_id=schedule.tenant_id,
                actor="installment_engine", action="schedule_reopened",
                entity_type="installment_schedule",
                entity_id=str(schedule.id)))
    db.flush()
    return flipped


def apply_posting(db, entry):
    if entry.kind == "payment":
        return apply_entry(db, entry)
    if entry.kind == "reversal":
        return unapply_entry(db, entry)
    return []


def leg_view(leg):
    today = date.today()
    active = leg.status in ("pending", "partial")
    return {"id": leg.id, "seq": leg.seq,
            "due_date": leg.due_date.isoformat(),
            "amount_cents": leg.amount_cents, "paid_cents": leg.paid_cents,
            "remaining_cents": leg.amount_cents - leg.paid_cents if active else 0,
            "status": leg.status,
            "late": bool(active and leg.due_date < today),
            "missed": bool(active and leg.due_date
                            < today - timedelta(days=MISSED_AFTER_DAYS)),
            "supersedes_id": leg.supersedes_id}


def schedule_view(db, schedule):
    legs = _legs(db, schedule.id)
    views = [leg_view(leg) for leg in legs]
    live = [leg for leg in legs if leg.status != "rescheduled"]
    return {"id": schedule.id, "invoice_id": schedule.invoice_id,
            "promise_id": schedule.promise_id, "terms": schedule.terms,
            "status": schedule.status, "created_by": schedule.created_by,
            "approved_by": schedule.approved_by,
            "total_cents": sum(leg.amount_cents for leg in live),
            "paid_cents": sum(leg.paid_cents for leg in legs),
            "remaining_cents": sum(item["remaining_cents"] for item in views),
            "legs": views}
