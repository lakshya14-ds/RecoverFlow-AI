"""Milestone 1: deterministic supervisor, durable tasks, contracts, budgets."""
import csv
import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base, get_db
from app.main import app
from app.services import specialists, supervisor
from app.services.receivables import post_entry, split_balance


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def api(db, monkeypatch):
    def override():
        yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "test-key")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", "")
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


HEADERS = {"X-RECOVERFLOW-API-KEY": "test-key"}


def invoice(db, amount="1000.00", disputed=0):
    row = models.Invoice(tenant_id="local", invoice_number="INV-P1", invoice_type="AR",
        counterparty_name="Synthetic distributor", issue_date=date(2026, 9, 1),
        due_date=date(2026, 10, 15), amount=Decimal(amount), total_amount=Decimal(amount),
        face_amount_cents=int(Decimal(amount) * 100), disputed_cents=disputed, currency="INR")
    db.add(row)
    db.flush()
    return row


def sourced(db, row):
    db.add(models.CaseEvidence(tenant_id="local", invoice_id=row.id, claim_type="invoice_total",
        title="Invoice", description="Synthetic", source_type="staff_record",
        source_reference="synthetic-invoice.pdf", amount_cents=100000, verified=True,
        trust_state="verified", decided_by="staff", decision_reason="Seeded for test"))
    db.commit()


def test_output_contract_rejects_bad_output():
    good = {"case_id": 1, "case_version": "v", "specialist": "resolution",
            "sources": [], "claims": [], "confidence": 0.5, "uncertainty": [],
            "proposed_action": None, "reason": "r", "escalate": False,
            "escalation_conditions": [], "findings": {}}
    assert specialists.check_output(dict(good))["specialist"] == "resolution"
    bad = dict(good)
    del bad["reason"]
    with pytest.raises(specialists.OutputRejected, match="missing"):
        specialists.check_output(bad)
    with pytest.raises(specialists.OutputRejected, match="Confidence"):
        specialists.check_output({**good, "confidence": 2})
    with pytest.raises(specialists.OutputRejected, match="escalation_conditions"):
        specialists.check_output({**good, "escalate": True})
    with pytest.raises(specialists.OutputRejected, match="Unknown specialist"):
        specialists.check_output({**good, "specialist": "ledger_poster"})


def test_tool_allowlist_denies_unauthorized_use(db):
    ctx = {"specialist": "resolution", "tenant_id": "local", "invoice_id": None,
           "task_id": 0, "actor": "test", "model_calls": 0, "model_budget": 2}
    with pytest.raises(specialists.ToolDenied, match="not allowed"):
        specialists.call_tool(db, ctx, "ledger_post")
    denied = db.query(models.AuditEvent).filter_by(action="specialist_tool").one()
    assert "DENIED" in denied.details


def test_model_budget_is_enforced_before_any_call(db):
    ctx = {"specialist": "communication", "tenant_id": "local", "invoice_id": None,
           "task_id": 0, "actor": "test", "model_calls": 2, "model_budget": 2}
    with pytest.raises(specialists.BudgetExhausted, match="budget"):
        specialists.call_tool(db, ctx, "model_classify", text="namaste")


def test_reassess_is_idempotent_for_duplicate_triggers(db):
    row = invoice(db)
    sourced(db, row)
    first = supervisor.reassess(db, row, "test")
    second = supervisor.reassess(db, row, "test")
    assert first["outcome"] == "queued"
    assert second["outcome"] == "duplicate"
    assert first["task_id"] == second["task_id"]
    assert db.query(models.SupervisorTask).count() == 1


def test_resolution_communication_verification_chain(db):
    row = invoice(db)
    sourced(db, row)
    kinds = []
    for _ in range(3):
        queued = supervisor.reassess(db, row, "test")
        assert queued["outcome"] == "queued"
        kinds.append(queued["kind"])
        outcome = supervisor.run_task(db, queued["task_id"])
        assert outcome["outcome"] == "done", outcome
        db.commit()
    assert kinds == ["resolution", "communication", "verification"]
    assert supervisor.reassess(db, row, "test")["outcome"] == "steady"
    proposal = db.query(models.AgentProposal).filter_by(
        tenant_id="local", invoice_id=row.id).one()
    assert proposal.draft_text and "undisputed" in proposal.draft_text
    assert split_balance(db, row)["outstanding_cents"] == 100000
    history = db.query(models.SupervisorTask).filter_by(
        tenant_id="local", invoice_id=row.id).order_by(models.SupervisorTask.id).all()
    assert [t.kind for t in history] == kinds
    assert all(json.loads(t.result_json)["case_version"] for t in history)


def test_payment_stales_queued_work_and_requeues_fresh(db):
    row = invoice(db)
    sourced(db, row)
    queued = supervisor.reassess(db, row, "test")
    post_entry(db, row, kind="payment", amount="100", source="manual",
               reference="P1-STALE", actor="staff")
    db.commit()
    outcome = supervisor.run_task(db, queued["task_id"])
    assert outcome["outcome"] in ("stale", "stale_at_pickup")
    fresh = supervisor.reassess(db, row, "test")
    assert fresh["outcome"] == "duplicate"
    statuses = {t.id: t.status for t in db.query(models.SupervisorTask).all()}
    assert statuses[queued["task_id"]] == "stale"


def test_retry_exhaustion_holds_the_case(db, monkeypatch):
    def boom(db, task, ctx, task_input):
        raise RuntimeError("simulated specialist crash")
    monkeypatch.setitem(specialists.RUNNERS, "resolution", boom)
    row = invoice(db)
    sourced(db, row)
    queued = supervisor.reassess(db, row, "test")
    outcomes = [supervisor.run_task(db, queued["task_id"])["outcome"] for _ in range(3)]
    assert outcomes == ["queued", "queued", "failed"]
    assert row.investigation_hold
    assert "failed after 3 attempts" in (row.investigation_reason or "")
    assert db.query(models.AuditEvent).filter_by(action="supervisor_escalated").count() == 1


def test_crash_recovery_replays_a_running_task(db):
    row = invoice(db)
    sourced(db, row)
    queued = supervisor.reassess(db, row, "test")
    task = db.get(models.SupervisorTask, queued["task_id"])
    task.status = "running"
    db.commit()
    assert supervisor.recover_interrupted_tasks(db) == 1
    assert supervisor.run_task(db, task.id)["outcome"] == "done"


def test_pause_resume_retry_and_history_over_api(db, api):
    row = invoice(db)
    sourced(db, row)
    queued = api.post(f"/api/v1/supervisor/cases/{row.id}/reassess", headers=HEADERS,
                      json={"trigger": "test"})
    assert queued.status_code == 200, queued.text
    task_id = queued.json()["task_id"]
    paused = api.post(f"/api/v1/supervisor/tasks/{task_id}/pause", headers=HEADERS)
    assert paused.json()["status"] == "paused"
    skipped = api.post(f"/api/v1/supervisor/tasks/{task_id}/run", headers=HEADERS)
    assert skipped.json()["outcome"] == "paused"
    resumed = api.post(f"/api/v1/supervisor/tasks/{task_id}/resume", headers=HEADERS)
    assert resumed.json()["status"] == "queued"
    ran = api.post(f"/api/v1/supervisor/tasks/{task_id}/run", headers=HEADERS)
    assert ran.json()["outcome"] == "done", ran.text
    history = api.get(f"/api/v1/supervisor/cases/{row.id}/tasks", headers=HEADERS)
    assert history.status_code == 200
    assert [(t["kind"], t["status"]) for t in history.json()] == [
        ("resolution", "done"), ("communication", "queued")]
    failed = models.SupervisorTask(tenant_id="local", invoice_id=row.id, kind="resolution",
        status="failed", idempotency_key="local:manual:1", attempts=3, error="boom")
    db.add(failed)
    db.commit()
    retried = api.post(f"/api/v1/supervisor/tasks/{failed.id}/retry", headers=HEADERS)
    assert retried.json()["status"] == "queued"
    assert db.get(models.SupervisorTask, failed.id).attempts == 0


def test_post_entry_triggers_supervisor_work(db):
    row = invoice(db)
    sourced(db, row)
    post_entry(db, row, kind="payment", amount="100", source="manual",
               reference="P1-TRIGGER", actor="staff")
    task = db.query(models.SupervisorTask).filter_by(
        tenant_id="local", invoice_id=row.id).one()
    assert task.kind == "resolution"
    assert task.trigger.startswith("ledger:payment:")


def test_intake_task_processes_an_upload_and_links_its_case(db, tmp_path):
    csv_path = tmp_path / "p1-intake.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["external_id", "invoice_number",
            "customer_name", "issue_date", "due_date", "amount", "currency"])
        writer.writeheader()
        writer.writerow({"external_id": "P1-EXT-1", "invoice_number": "INV-P1-CSV",
            "customer_name": "Synthetic distributor", "issue_date": "2026-09-01",
            "due_date": "2026-10-01", "amount": "500.00", "currency": "INR"})
    db.add(models.IntakeUpload(id="p1-upload-1", tenant_id="local", actor="staff",
        filename="p1-intake.csv", mime_type="text/csv", source_path=str(csv_path),
        size_bytes=200, status="queued", stage="Uploaded"))
    db.commit()
    queued = supervisor.request_intake_task(db, "local", "p1-upload-1")
    duplicate = supervisor.request_intake_task(db, "local", "p1-upload-1")
    assert duplicate["outcome"] == "duplicate"
    outcome = supervisor.run_task(db, queued["task_id"])
    assert outcome["outcome"] == "done", outcome
    task = db.get(models.SupervisorTask, queued["task_id"])
    assert task.applied is True
    created = db.query(models.Invoice).filter_by(
        tenant_id="local", invoice_number="INV-P1-CSV").one()
    assert task.invoice_id == created.id
    assert json.loads(task.result_json)["findings"]["upload"]["status"] == "ready_for_review"


def test_blocked_cases_escalate_without_new_tasks(db):
    row = invoice(db)
    row.requires_human_review = True
    db.commit()
    assert supervisor.reassess(db, row, "test")["outcome"] == "escalated"
    assert db.query(models.SupervisorTask).count() == 0


def test_dependencies_gate_execution(db):
    row = invoice(db)
    sourced(db, row)
    task = models.SupervisorTask(tenant_id="local", invoice_id=row.id, kind="communication",
        status="queued", idempotency_key="local:dep:1", depends_on_json="[999999]",
        case_version="none")
    db.add(task)
    db.commit()
    assert supervisor.run_task(db, task.id)["outcome"] == "waiting"


def test_staff_review_supersedes_stale_drafts(db, api):
    row = invoice(db, disputed=30000)
    sourced(db, row)
    db.add(models.AgentProposal(
        tenant_id="local", invoice_id=row.id, context_hash="0" * 64,
        engine="template", summary="old", rationale="old",
        action="split_balance_draft", status="proposed",
        balance_cents_at_proposal=100000))
    db.commit()
    evidence = db.query(models.CaseEvidence).filter_by(invoice_id=row.id).first()
    reviewed = api.post(f"/api/v1/cases/{row.id}/dispute-review", headers=HEADERS,
        json={"disputed_amount": "300.00", "evidence_id": evidence.id,
              "reason": "test review keeps dispute open"})
    assert reviewed.status_code == 200, reviewed.text
    assert db.query(models.AgentProposal).one().status == "stale"
    assert db.query(models.AuditEvent).filter_by(action="drafts_superseded").count() == 1
    ctx = {"specialist": "verification", "tenant_id": "local", "invoice_id": row.id,
           "task_id": 0, "actor": "test", "model_calls": 0, "model_budget": 0,
           "case_version": "test"}
    output = specialists.run_verification(db, ctx, {})
    assert output["escalate"] is False, output["findings"]
