"""Multi-worker job claims: atomic pickup, leases, heartbeats, backoff,
dead-lettering, and operator replay. One worker's crash never wedges the
queue and never double-executes a job: every claim is a single conditional
UPDATE, so exactly one worker wins.
"""
import os
import socket
from datetime import datetime, timedelta

from sqlalchemy import or_

from app.database import models

LEASE_SECONDS = 300
BACKOFF_CAP_MINUTES = 120
POISON_ATTEMPTS = 3

_scopes = {
    "intake": (models.IntakeUpload, "queued", "processing"),
    "supervisor": (models.SupervisorTask, "queued", "running"),
}

_WORKER_ID = None


def worker_id():
    """Stable-per-process worker identity for lease ownership."""
    global _WORKER_ID
    if _WORKER_ID is None:
        _WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
    return _WORKER_ID


def _now():
    # Naive UTC, matching the codebase convention for SQLite/PG comparison.
    return datetime.utcnow()


def backoff_minutes(attempts):
    """Deterministic exponential backoff: 2, 4, 8 ... capped at 120."""
    return min(2 ** max(1, int(attempts)), BACKOFF_CAP_MINUTES)


def _row_scope(model):
    for scope, (candidate, _q, _r) in _scopes.items():
        if candidate is model:
            return scope
    raise ValueError("Unknown leased model")


def leased_model(scope):
    return _scopes[scope][0]


def get_job(db, scope, job_id):
    return db.get(leased_model(scope), job_id)


def _try_claim(db, model, job_id, worker, now, lease_seconds, queued,
               running, steal):
    """One atomic conditional UPDATE. Returns True when this worker won."""
    from sqlalchemy import update
    if steal:
        predicate = (model.status == running) & (
            model.lease_expires_at.is_not(None)) & (
            model.lease_expires_at < now)
    else:
        predicate = (model.status == queued) & (
            (model.not_before.is_(None)) | (model.not_before <= now))
    result = db.execute(
        update(model).where(model.id == job_id, predicate).values(
            status=running, attempts=model.attempts + 1,
            claimed_by=worker, claimed_at=now, heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            not_before=None))
    db.commit()
    return bool(result.rowcount)


def claim_job(db, scope, job_id, worker=None, lease_seconds=LEASE_SECONDS):
    """Atomically claim one job (or steal its expired lease). Commits.

    Each branch is a single conditional UPDATE, so exactly one worker wins
    even when two pick the same candidate in the same instant."""
    worker = worker or worker_id()
    model, queued, running = _scopes[scope]
    now = _now()
    if _try_claim(db, model, job_id, worker, now, lease_seconds,
                  queued, running, steal=False):
        stolen = False
    elif _try_claim(db, model, job_id, worker, now, lease_seconds,
                    queued, running, steal=True):
        stolen = True
    else:
        return None
    match = db.get(model, job_id)
    db.add(models.AuditEvent(
        tenant_id=match.tenant_id, actor=worker,
        action="job_claimed" if not stolen else "job_lease_stolen",
        entity_type="leased_job", entity_id=f"{scope}:{match.id}",
        details=f"attempt={match.attempts}"))
    db.commit()
    return match


def claim_next(db, scope, tenant_id=None, worker=None,
               lease_seconds=LEASE_SECONDS):
    """Oldest claimable job for one scope. Returns the claimed row or None."""
    worker = worker or worker_id()
    model, queued, running = _scopes[scope]
    now = _now()
    query = db.query(model.id).filter(or_(
        (model.status == queued) & (
            (model.not_before.is_(None)) | (model.not_before <= now)),
        (model.status == running) & (model.lease_expires_at.is_not(None))
        & (model.lease_expires_at < now)))
    if tenant_id is not None:
        query = query.filter(model.tenant_id == tenant_id)
    candidate = query.order_by(model.id).first()
    if not candidate:
        return None
    return claim_job(db, scope, candidate[0], worker, lease_seconds)


def heartbeat(db, scope, job_id, worker=None, lease_seconds=LEASE_SECONDS):
    """Extend a held lease. Only the holding worker may extend it."""
    worker = worker or worker_id()
    model, _queued, _running = _scopes[scope]
    now = _now()
    row = db.query(model).filter_by(id=job_id, claimed_by=worker).first()
    if not row or row.lease_expires_at is None or row.lease_expires_at < now:
        return False
    row.heartbeat_at = now
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    db.commit()
    return True


def release_lease(db, row):
    """Clear lease ownership when a job leaves worker hands. Caller commits."""
    row.claimed_by = None
    row.claimed_at = None
    row.heartbeat_at = None
    row.lease_expires_at = None
    db.flush()


def fail_transient(db, row, error, worker=None):
    """Requeue with backoff. Caller commits."""
    worker = worker or worker_id()
    row.status = "queued"
    row.error = str(error or "transient failure")[:500]
    row.not_before = _now() + timedelta(
        minutes=backoff_minutes(row.attempts or 1))
    release_lease(db, row)
    db.add(models.AuditEvent(
        tenant_id=row.tenant_id, actor=worker, action="job_backoff",
        entity_type="leased_job",
        entity_id=f"{_row_scope(type(row))}:{row.id}",
        details=f"attempt={row.attempts}; {row.error}"[:500]))
    db.flush()
    return row


def fail_poison(db, row, error, worker=None):
    """Park a repeatedly-crashing job in the dead letter queue."""
    worker = worker or worker_id()
    row.status = "dead_letter"
    row.error = str(error or "poison job")[:500]
    release_lease(db, row)
    db.add(models.AuditEvent(
        tenant_id=row.tenant_id, actor=worker, action="job_dead_lettered",
        entity_type="leased_job",
        entity_id=f"{_row_scope(type(row))}:{row.id}",
        details=f"attempts={row.attempts}; {row.error}"[:500]))
    db.flush()
    return row


def retry_job(db, scope, job_id, actor):
    """Operator replay: fresh attempt budget, back to queued. Caller commits."""
    row = get_job(db, scope, job_id)
    if not row:
        raise ValueError("Job not found")
    if row.status not in ("dead_letter", "failed", "needs_attention"):
        raise ValueError("Only failed, dead-letter, or needs-attention jobs retry")
    row.status = "queued"
    row.attempts = 0
    row.error = None
    row.not_before = None
    release_lease(db, row)
    db.add(models.AuditEvent(
        tenant_id=row.tenant_id, actor=actor, action="job_retried",
        entity_type="leased_job", entity_id=f"{scope}:{row.id}"))
    db.flush()
    return row


def dismiss_dead_letter(db, scope, job_id, actor, note=""):
    """Operator accepts a dead job as-is. History stays visible."""
    row = get_job(db, scope, job_id)
    if not row or row.status != "dead_letter":
        raise ValueError("Dead-letter job not found")
    db.add(models.AuditEvent(
        tenant_id=row.tenant_id, actor=actor, action="dead_letter_dismissed",
        entity_type="leased_job", entity_id=f"{scope}:{row.id}",
        details=(note or "")[:500]))
    db.flush()
    return row
