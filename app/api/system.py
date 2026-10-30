"""
RecoverFlow - Receivables and Collections
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.auth import Identity, get_identity, require_admin
from app.config import settings
from app.database import db_manager
from app.database import migrations
from app.database.db_manager import get_db

router = APIRouter(prefix="/system", tags=["System"])

@router.get("/health")
def health_check():
    """Confirm that the application and API are responding."""
    return {"status": "ok", "service": "RecoverFlow"}


@router.get("/migrations")
def migration_status(identity: Identity = Depends(require_admin)):
    """Admin-only migration state. Never exposes the database URL (it may hold a password)."""
    return migrations.status(db_manager.engine)

def _job_category(error):
    return (error or "").split(":")[0][:80] or None


def _job_view(row, scope, full=False):
    created = row.created_at
    age_seconds = None
    if created:
        if getattr(created, "tzinfo", None) is None:
            created = created.replace(tzinfo=timezone.utc)
        age_seconds = max(
            0, int((datetime.now(timezone.utc) - created).total_seconds()))
    view = {"scope": scope, "id": row.id, "tenant_id": row.tenant_id,
            "status": row.status, "attempts": row.attempts,
            "age_seconds": age_seconds, "claimed_by": row.claimed_by,
            "error_category": _job_category(row.error)}
    if full:
        view["error"] = row.error
        view["not_before"] = row.not_before.isoformat() if row.not_before else None
        view["lease_expires_at"] = row.lease_expires_at.isoformat() \
            if row.lease_expires_at else None
    return view


@router.get("/jobs")
def list_jobs(scope: str = "", status: str = "",
              db: Session = Depends(get_db),
              identity: Identity = Depends(get_identity)):
    """Operator queue view. Error details stay on the single-job endpoint."""
    from app.services import worker_lease
    scopes = [scope] if scope else ["intake", "supervisor"]
    for name in scopes:
        if name not in ("intake", "supervisor"):
            raise HTTPException(status_code=422, detail="Unknown job scope")
    rows = []
    for name in scopes:
        model = worker_lease.leased_model(name)
        query = db.query(model).filter_by(tenant_id=identity.tenant_id)
        if status:
            query = query.filter_by(status=status)
        rows.extend(_job_view(row, name)
                    for row in query.order_by(model.id).limit(200).all())
    return rows


@router.get("/jobs/{scope}/{job_id}")
def get_job(scope: str, job_id: str, db: Session = Depends(get_db),
            identity: Identity = Depends(get_identity)):
    from app.database import models as _models
    from app.services import worker_lease
    if scope not in ("intake", "supervisor"):
        raise HTTPException(status_code=422, detail="Unknown job scope")
    try:
        key = int(job_id) if scope == "supervisor" else job_id
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad job id") from None
    row = worker_lease.get_job(db, scope, key)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    db.add(_models.AuditEvent(
        tenant_id=identity.tenant_id, actor=identity.actor,
        action="job_detail_viewed", entity_type="leased_job",
        entity_id=f"{scope}:{key}"))
    db.commit()
    return _job_view(row, scope, full=True)


class JobRetry(BaseModel):
    scope: str
    id: str


@router.post("/jobs/retry")
def retry_job(payload: JobRetry, db: Session = Depends(get_db),
              identity: Identity = Depends(require_admin)):
    from app.services import worker_lease
    if payload.scope not in ("intake", "supervisor"):
        raise HTTPException(status_code=422, detail="Unknown job scope")
    try:
        key = int(payload.id) if payload.scope == "supervisor" else payload.id
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad job id") from None
    row = worker_lease.get_job(db, payload.scope, key)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        retried = worker_lease.retry_job(db, payload.scope, key, identity.actor)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _job_view(retried, payload.scope)


class DeadLetterResolve(BaseModel):
    scope: str
    id: str
    decision: str = "requeue"
    note: str = ""


@router.post("/jobs/dead-letter/resolve")
def resolve_dead_letter(payload: DeadLetterResolve,
                        db: Session = Depends(get_db),
                        identity: Identity = Depends(require_admin)):
    from app.services import worker_lease
    if payload.scope not in ("intake", "supervisor"):
        raise HTTPException(status_code=422, detail="Unknown job scope")
    if payload.decision not in ("requeue", "dismiss"):
        raise HTTPException(status_code=422,
                            detail="Decision must be requeue or dismiss")
    try:
        key = int(payload.id) if payload.scope == "supervisor" else payload.id
    except ValueError:
        raise HTTPException(status_code=422, detail="Bad job id") from None
    row = worker_lease.get_job(db, payload.scope, key)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        if payload.decision == "requeue":
            resolved = worker_lease.retry_job(db, payload.scope, key,
                                              identity.actor)
        else:
            resolved = worker_lease.dismiss_dead_letter(
                db, payload.scope, key, identity.actor,
                payload.note.strip())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return _job_view(resolved, payload.scope)


@router.get("/metrics")
def ops_metrics(db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    """Tenant-scoped operational snapshot. Counts and ages; no customer data."""
    from app.services import ops_metrics as _metrics
    return _metrics.collect_metrics(db, identity.tenant_id)


@router.get("/alerts")
def ops_alerts(db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    """Evaluated alert rules with owner, severity, and first response."""
    from app.services import ops_metrics as _metrics
    return _metrics.evaluate_alerts(db, identity.tenant_id)


@router.get("/economics")
def unit_economics(period_days: int = 30,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(require_admin)):
    """Unit-economics report. Prices are admin-set assumptions; unit prices
    are business-confidential, so this stays admin-only."""
    from app.services import economics as _economics
    try:
        return _economics.collect_report(db, identity.tenant_id, period_days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class PurgeDocuments(BaseModel):
    dry_run: bool = True


@router.post("/documents/purge")
def purge_documents(payload: PurgeDocuments,
                    db: Session = Depends(get_db),
                    identity: Identity = Depends(require_admin)):
    """Retention purge for this tenant's stored documents. Dry run by default;
    holds and live rows are always skipped. Schedule via cron, not by hand."""
    from app.database import models
    from app.services import document_store
    plan = document_store.purge_expired_documents(
        db, identity.tenant_id, identity.actor, dry_run=payload.dry_run)
    if not payload.dry_run and plan:
        db.add(models.AuditEvent(
            tenant_id=identity.tenant_id, actor=identity.actor,
            action="documents_purged", entity_type="stored_document",
            entity_id=f"{len(plan)} docs"))
    db.commit()
    return {"dry_run": payload.dry_run, "purged": plan}


@router.get("/config")
def get_config():
    """Return non-sensitive configuration values."""
    safe_config = {
        "HOST": settings.HOST,
        "PORT": settings.PORT,
        "LLM_MODEL": settings.LLM_MODEL,
        "DEBUG": settings.DEBUG,
        "AUTO_APPROVE_THRESHOLD": settings.AUTO_APPROVE_THRESHOLD,
        "FRAUD_ALERT_THRESHOLD": settings.FRAUD_ALERT_THRESHOLD,
        "DSO_FORECAST_HORIZON": settings.DSO_FORECAST_HORIZON
    }
    return safe_config
