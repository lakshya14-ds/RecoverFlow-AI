"""Restartable local invoice worker. Run with: python -m app.worker."""
import argparse
import logging
import time
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, update

from app.api.invoices import process_invoice_pipeline
from app.database import models
from app.database.db_manager import SessionLocal, init_db
from app.services.receivables import balance_cents, opening_cents

LEASE = timedelta(minutes=15)


def run_once() -> bool:
    """Claim one queued or expired job atomically and process it."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with SessionLocal() as db:
        db.execute(update(models.ProcessingJob).where(
            models.ProcessingJob.status.in_(("queued", "processing")),
            models.ProcessingJob.attempts >= 3,
            or_(models.ProcessingJob.locked_until.is_(None),
                models.ProcessingJob.locked_until <= now),
        ).values(status="failed", error="Processing retry limit reached", locked_until=None))
        db.commit()
        candidates = db.query(models.ProcessingJob.id).filter(
            models.ProcessingJob.status.in_(("queued", "processing")),
            models.ProcessingJob.attempts < 3,
            or_(models.ProcessingJob.locked_until.is_(None),
                models.ProcessingJob.locked_until <= now),
        ).order_by(models.ProcessingJob.created_at).limit(10).all()
        job_id = None
        for (candidate_id,) in candidates:
            claimed = db.execute(update(models.ProcessingJob).where(
                models.ProcessingJob.id == candidate_id,
                models.ProcessingJob.status.in_(("queued", "processing")),
                models.ProcessingJob.attempts < 3,
                or_(models.ProcessingJob.locked_until.is_(None),
                    models.ProcessingJob.locked_until <= now),
            ).values(status="processing", locked_until=now + LEASE,
                     attempts=models.ProcessingJob.attempts + 1))
            db.commit()
            if claimed.rowcount:
                job_id = candidate_id
                break
    if not job_id:
        return False
    process_invoice_pipeline(job_id)
    return True


def refresh_dso_snapshots() -> None:
    """Save a daily invoice-based DSO estimate for tenants with recent AR sales."""
    today = date.today()
    start = today - timedelta(days=29)
    with SessionLocal() as db:
        tenants = [row[0] for row in db.query(models.Invoice.tenant_id).filter_by(
            invoice_type="AR").distinct().all()]
        for tenant in tenants:
            invoices = db.query(models.Invoice).filter_by(tenant_id=tenant, invoice_type="AR").all()
            recent_sales_cents = sum(opening_cents(row) for row in invoices
                                     if start <= row.issue_date <= today and row.status != "cancelled")
            if recent_sales_cents <= 0:
                continue
            open_items = [(row, balance_cents(db, row)) for row in invoices
                          if row.status != "cancelled"]
            ar_cents = sum(max(0, balance) for _, balance in open_items)
            overdue = [(row, balance) for row, balance in open_items
                       if row.due_date < today and balance > 0]
            snapshot = db.query(models.DSOSnapshot).filter_by(
                tenant_id=tenant, snapshot_date=today).first()
            if not snapshot:
                snapshot = models.DSOSnapshot(tenant_id=tenant, snapshot_date=today)
                db.add(snapshot)
            snapshot.dso_days = round(ar_cents / recent_sales_cents * 30, 2)
            snapshot.ar_balance = ar_cents / 100
            snapshot.revenue_30d = recent_sales_cents / 100
            snapshot.overdue_amount = sum(balance for _, balance in overdue) / 100
            snapshot.overdue_count = len(overdue)
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process one job and refresh today's DSO")
    args = parser.parse_args()
    init_db()
    last_snapshot = None
    while True:
        if last_snapshot != date.today():
            refresh_dso_snapshots()
            last_snapshot = date.today()
        worked = run_once()
        if args.once:
            break
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
