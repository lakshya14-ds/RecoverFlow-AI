"""P2 E1: durable workers — atomic claims, leases, heartbeats, backoff,
dead letters, operator replay, and no-duplicate execution under races."""
import hashlib
import hmac
import json
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app
from app.services import specialists, supervisor, worker_lease

ADMIN = {"X-RECOVERFLOW-API-KEY": "e1-admin"}
EDITOR = {"X-RECOVERFLOW-API-KEY": "e1-editor"}
SECRET = "whsec-synthetic-e1"


@pytest.fixture()
def workdb(monkeypatch, tmp_path):
    db_path = tmp_path / "e1.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "e1-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "e1-editor", "actor": "ed@example.in", "tenant_id": "local",
          "role": "editor"}]))
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_mock_e1")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "mock-secret")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", SECRET)
    monkeypatch.setattr(settings, "RAZORPAY_MODE", "test")
    monkeypatch.setattr(settings, "RAZORPAY_LIVE_ENABLED", False)
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-E1", invoice_type="AR",
            counterparty_name="E1 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR"))
        db.commit()
        invoice = db.query(models.Invoice).one().id
    yield {"client": TestClient(app), "factory": factory, "engine": engine,
           "invoice": invoice}
    engine.dispose()


def _upload(factory, job_id="job-1", status="queued"):
    with factory() as db:
        db.add(models.IntakeUpload(
            id=job_id, tenant_id="local", actor="staff",
            filename="in.csv", mime_type="text/csv",
            source_path="/nonexistent/in.csv", size_bytes=10,
            status=status, stage="Uploaded"))
        db.commit()


def _task(factory, kind="resolution", status="queued", max_attempts=3,
          key=None):
    with factory() as db:
        row = models.SupervisorTask(
            tenant_id="local", invoice_id=None, kind=kind, status=status,
            max_attempts=max_attempts,
            idempotency_key=key or f"local:e1:{uuid.uuid4().hex}")
        db.add(row)
        db.commit()
        return row.id


def _naive_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stub_ok(db, ctx, task_input):
    return {"case_id": 0, "case_version": 1, "specialist": "resolution",
            "sources": [], "claims": [], "confidence": 0.9,
            "uncertainty": [], "proposed_action": "none", "reason": "stub",
            "escalate": False, "escalation_conditions": [], "findings": {}}


def test_startup_recovery_preserves_other_workers_active_leases(workdb, monkeypatch):
    from app.services import intake_pipeline
    monkeypatch.setattr(intake_pipeline, "SessionLocal", workdb["factory"])
    _upload(workdb["factory"])
    task_id = _task(workdb["factory"])
    with workdb["factory"]() as db:
        worker_lease.claim_job(db, "intake", "job-1", "other-worker")
        worker_lease.claim_job(db, "supervisor", task_id, "other-worker")
        assert supervisor.recover_interrupted_tasks(db) == 0
        assert intake_pipeline.recover_interrupted_jobs() == 0
        db.expire_all()
        assert db.get(models.SupervisorTask, task_id).status == "running"
        assert db.get(models.IntakeUpload, "job-1").status == "processing"


def test_background_tick_recovers_expired_supervisor_lease(workdb, monkeypatch):
    task_id = _task(workdb["factory"])
    calls = []
    def run(db, ctx, task_input):
        calls.append(ctx)
        return _stub_ok(db, ctx, task_input)
    monkeypatch.setitem(specialists.RUNNERS, "resolution", run)
    with workdb["factory"]() as db:
        task = worker_lease.claim_job(db, "supervisor", task_id, "dead-worker")
        task.lease_expires_at = _naive_utc() - timedelta(seconds=1)
        db.commit()
    outcomes = supervisor.run_due_thread()
    assert any(row["task_id"] == task_id and row["outcome"] == "done" for row in outcomes)
    assert len(calls) == 1
    with workdb["factory"]() as db:
        assert db.get(models.SupervisorTask, task_id).attempts == 2


def test_simultaneous_intake_claim_single_winner(workdb):
    _upload(workdb["factory"])
    barrier = threading.Barrier(2)
    winners = []

    def race(worker):
        factory = workdb["factory"]
        with factory() as db:
            barrier.wait(timeout=10)
            if worker_lease.claim_job(db, "intake", "job-1",
                                      worker=worker):
                winners.append(worker)

    threads = [threading.Thread(target=race, args=(f"w{i}",))
               for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(winners) == 1
    with workdb["factory"]() as db:
        assert db.get(models.IntakeUpload, "job-1").attempts == 1


def test_simultaneous_supervisor_run_executes_once(workdb, monkeypatch):
    task_id = _task(workdb["factory"])
    calls = []
    orig = specialists.RUNNERS["resolution"]

    def counting(db, ctx, task_input):
        calls.append(task_id)
        return _stub_ok(db, ctx, task_input)

    monkeypatch.setitem(specialists.RUNNERS, "resolution", counting)
    barrier = threading.Barrier(2)
    outcomes = []

    def race(worker):
        factory = workdb["factory"]
        with factory() as db:
            barrier.wait(timeout=10)
            outcomes.append(supervisor.run_task(
                db, task_id, worker=worker)["outcome"])
            db.commit()

    threads = [threading.Thread(target=race, args=(f"w{i}",))
               for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert "done" in outcomes
    loser = [o for o in outcomes if o != "done"]
    # The loser may observe the live lease (claimed/running) or arrive after
    # the winner committed (done without executing). Exactly-once is proven
    # by the call count and attempts below, not by which interleave won.
    assert loser in (["claimed"], ["running"], [])
    assert calls == [task_id]
    with workdb["factory"]() as db:
        assert db.get(models.SupervisorTask, task_id).attempts == 1
    monkeypatch.setitem(specialists.RUNNERS, "resolution", orig)


def test_crash_then_lease_steal(workdb):
    _upload(workdb["factory"])
    with workdb["factory"]() as db:
        claimed = worker_lease.claim_job(db, "intake", "job-1",
                                         worker="crashed-1",
                                         lease_seconds=300)
        assert claimed is not None
        assert worker_lease.claim_job(db, "intake", "job-1",
                                      worker="w2") is None
    with workdb["factory"]() as db:
        row = db.get(models.IntakeUpload, "job-1")
        row.lease_expires_at = _naive_utc() - timedelta(seconds=1)
        db.commit()
    with workdb["factory"]() as db:
        stolen = worker_lease.claim_job(db, "intake", "job-1", worker="w2")
        assert stolen is not None
        assert stolen.attempts == 2
        assert db.query(models.AuditEvent).filter_by(
            action="job_lease_stolen").count() == 1


def test_heartbeat_extends_and_guards_holder(workdb):
    task_id = _task(workdb["factory"])
    with workdb["factory"]() as db:
        worker_lease.claim_job(db, "supervisor", task_id, worker="w1",
                               lease_seconds=60)
        first = db.get(models.SupervisorTask, task_id).lease_expires_at
        assert worker_lease.heartbeat(db, "supervisor", task_id, worker="w1",
                                      lease_seconds=600) is True
        assert db.get(models.SupervisorTask,
                      task_id).lease_expires_at > first
        assert worker_lease.heartbeat(db, "supervisor", task_id,
                                      worker="impostor") is False
    with workdb["factory"]() as db:
        row = db.get(models.SupervisorTask, task_id)
        row.lease_expires_at = _naive_utc() - timedelta(seconds=1)
        db.commit()
        assert worker_lease.heartbeat(db, "supervisor", task_id,
                                      worker="w1") is False


def test_backoff_skips_until_ready(workdb):
    _upload(workdb["factory"])
    with workdb["factory"]() as db:
        row = db.get(models.IntakeUpload, "job-1")
        row.attempts = 1
        worker_lease.fail_transient(db, row, "flaky", worker="w1")
        db.commit()
        assert row.not_before > _naive_utc()
    with workdb["factory"]() as db:
        assert worker_lease.claim_next(db, "intake", worker="w2") is None
    with workdb["factory"]() as db:
        row = db.get(models.IntakeUpload, "job-1")
        row.not_before = _naive_utc() - timedelta(seconds=1)
        db.commit()
    with workdb["factory"]() as db:
        assert worker_lease.claim_next(
            db, "intake", worker="w2") is not None


def test_intake_poison_parks_and_worker_continues(workdb, monkeypatch):
    from app.services import intake_pipeline
    _upload(workdb["factory"], "a-poison")
    _upload(workdb["factory"], "z-healthy")

    def boom(db, job):
        raise RuntimeError("segfault smell")

    monkeypatch.setattr(intake_pipeline, "_process_csv", boom)
    monkeypatch.setattr(intake_pipeline, "SessionLocal", workdb["factory"])
    for _ in range(3):
        assert intake_pipeline.process_one(worker="w1") is True
        with workdb["factory"]() as db:
            row = db.get(models.IntakeUpload, "a-poison")
            if row.status == "queued":
                row.not_before = _naive_utc() - timedelta(seconds=1)
                db.commit()
    with workdb["factory"]() as db:
        poison = db.get(models.IntakeUpload, "a-poison")
        assert poison.status == "dead_letter"
        assert poison.attempts == 3
        assert db.query(models.AuditEvent).filter_by(
            action="job_dead_lettered").count() == 1

    def fine(db, job):
        job.status = "Ready for review"
        job.stage = "Ready for review"

    monkeypatch.setattr(intake_pipeline, "_process_csv", fine)
    assert intake_pipeline.process_one(worker="w1") is True
    with workdb["factory"]() as db:
        assert db.get(models.IntakeUpload, "z-healthy").status == \
            "Ready for review"


def test_supervisor_poison_vs_transient(workdb, monkeypatch):
    poison_id = _task(workdb["factory"], max_attempts=10,
                      key="local:e1:poison")
    slow_id = _task(workdb["factory"], max_attempts=3, key="local:e1:slow")

    def boom(db, ctx, task_input):
        if ctx.get("task_id") == poison_id:
            raise RuntimeError("deterministic crash")
        raise TimeoutError("slow provider")

    monkeypatch.setitem(specialists.RUNNERS, "resolution", boom)
    for _ in range(3):
        with workdb["factory"]() as db:
            row = db.get(models.SupervisorTask, poison_id)
            row.not_before = None
            db.commit()
            assert supervisor.run_task(
                db, poison_id, worker="w1")["outcome"] in ("queued",
                                                           "dead_letter")
            db.commit()
    with workdb["factory"]() as db:
        assert db.get(models.SupervisorTask, poison_id).status == \
            "dead_letter"
    outcomes = []
    for _ in range(3):
        with workdb["factory"]() as db:
            row = db.get(models.SupervisorTask, slow_id)
            row.not_before = None
            db.commit()
            outcomes.append(supervisor.run_task(db, slow_id,
                                                worker="w1")["outcome"])
            db.commit()
    assert outcomes == ["queued", "queued", "failed"]
    with workdb["factory"]() as db:
        assert db.get(models.SupervisorTask, slow_id).status == "failed"


def test_operator_retry_and_dismiss(workdb):
    _upload(workdb["factory"])
    task_id = _task(workdb["factory"])
    client = workdb["client"]
    with workdb["factory"]() as db:
        for row in (db.get(models.IntakeUpload, "job-1"),
                    db.get(models.SupervisorTask, task_id)):
            row.status = "dead_letter"
            row.attempts = 3
            row.error = "boom"
        db.commit()
    assert client.post("/api/v1/system/jobs/retry", headers=EDITOR,
                       json={"scope": "intake",
                             "id": "job-1"}).status_code == 403
    retried = client.post("/api/v1/system/jobs/retry", headers=ADMIN,
                          json={"scope": "intake", "id": "job-1"})
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempts"] == 0
    dismissed = client.post("/api/v1/system/jobs/dead-letter/resolve",
                            headers=ADMIN,
                            json={"scope": "supervisor",
                                  "id": str(task_id),
                                  "decision": "dismiss",
                                  "note": "known bad payload"})
    assert dismissed.json()["status"] == "dead_letter"
    listed = client.get("/api/v1/system/jobs",
                        params={"status": "dead_letter"},
                        headers=EDITOR).json()
    assert [item["id"] for item in listed] == [task_id]
    assert "error" not in listed[0]
    assert listed[0]["error_category"] == "boom"
    full = client.get(f"/api/v1/system/jobs/supervisor/{task_id}",
                      headers=EDITOR).json()
    assert full["error"] == "boom"
    with workdb["factory"]() as db:
        assert db.query(models.AuditEvent).filter_by(
            action="dead_letter_dismissed").count() == 1
        assert db.query(models.AuditEvent).filter_by(
            action="job_detail_viewed").count() == 1
    assert client.post("/api/v1/system/jobs/retry", headers=ADMIN,
                       json={"scope": "intake",
                             "id": "job-1"}).status_code == 409


def test_concurrent_webhook_posts_once(workdb):
    client = workdb["client"]
    invoice = workdb["invoice"]
    created = client.post("/api/v1/payments/links", headers=ADMIN,
                          json={"invoice_id": invoice,
                                "idempotency_key": str(uuid.uuid4())})
    assert created.status_code == 201, created.text
    payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment": {"entity": {
                "id": "pay_race1", "status": "captured", "captured": True,
                "amount": 100000, "currency": "INR"}},
            "payment_link": {"entity": {
                "id": created.json()["provider_link_id"], "amount": 100000,
                "currency": "INR"}}}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    barrier = threading.Barrier(2)
    statuses = []

    def deliver():
        barrier.wait(timeout=10)
        res = TestClient(app).post(
            "/api/v1/webhooks/razorpay/local", content=body,
            headers={"X-Razorpay-Signature": sig,
                     "X-Razorpay-Event-Id": "evt-race-1",
                     "Content-Type": "application/json"})
        statuses.append(res.status_code)

    threads = [threading.Thread(target=deliver) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert sorted(statuses) == [200, 200]
    with workdb["factory"]() as db:
        assert db.query(models.ReceivableEntry).filter_by(
            invoice_id=invoice, source="razorpay").count() == 1
        assert db.query(models.ProviderEvent).filter_by(
            event_id="evt-race-1").count() == 1


def test_run_due_skips_backoff(workdb, monkeypatch):
    ready_id = _task(workdb["factory"], key="local:e1:ready")
    _task(workdb["factory"], key="local:e1:waiting")
    monkeypatch.setitem(specialists.RUNNERS, "resolution", _stub_ok)
    with workdb["factory"]() as db:
        waiting = db.query(models.SupervisorTask).filter_by(
            idempotency_key="local:e1:waiting").one()
        waiting.not_before = _naive_utc() + timedelta(hours=1)
        db.commit()
    with workdb["factory"]() as db:
        outcomes = supervisor.run_due_tasks(db, "local", actor="w1")
        db.commit()
    assert [item["task_id"] for item in outcomes] == [ready_id]
    with workdb["factory"]() as db:
        assert db.get(models.SupervisorTask, ready_id).status == "done"
        assert db.query(models.SupervisorTask).filter_by(
            idempotency_key="local:e1:waiting").one().status == "queued"


def test_pause_and_retry_clear_leases(workdb):
    task_id = _task(workdb["factory"])
    with workdb["factory"]() as db:
        worker_lease.claim_job(db, "supervisor", task_id, worker="w1")
        task = db.get(models.SupervisorTask, task_id)
        supervisor.pause_task(db, task, "boss")
        db.commit()
        assert task.claimed_by is None
        task.status = "failed"
        db.commit()
        supervisor.retry_task(db, task, "boss")
        db.commit()
        assert (task.status, task.attempts, task.not_before,
                task.claimed_by) == ("queued", 0, None, None)
