"""P2 A4: assignment, notes, tasks, escalations, workload, and SoD approvals."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app
from app.services import team_ops

ADMIN = {"X-RECOVERFLOW-API-KEY": "a4-admin"}


@pytest.fixture()
def teamdb(monkeypatch, tmp_path):
    db_path = tmp_path / "a4.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "a4-admin")
    db_manager.init_db()
    client = TestClient(app)
    tokens, ids = {}, {}
    for email, role in (("s1@example.in", "editor"), ("s2@example.in", "editor"),
                        ("boss@example.in", "admin")):
        created = client.post("/api/v1/auth/users", headers=ADMIN, json={
            "email": email, "name": email.split("@")[0], "password": "StaffPass1!",
            "role": role})
        assert created.status_code == 201, created.text
        ids[email] = created.json()["id"]
        tokens[email] = client.post("/api/v1/auth/login", json={
            "email": email, "password": "StaffPass1!"}).json()["token"]
    factory = sessionmaker(bind=engine)
    with factory() as db:
        row = models.Invoice(
            tenant_id="local", invoice_number="A4-1", invoice_type="AR",
            counterparty_name="A4 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR")
        db.add(row)
        db.commit()
        invoice_id = row.id
    yield {"client": client, "factory": factory, "engine": engine,
           "tokens": tokens, "ids": ids, "invoice": invoice_id}
    engine.dispose()


@pytest.fixture()
def lonedb(monkeypatch, tmp_path):
    """Single-operator tenant: no database users at all."""
    db_path = tmp_path / "a4-lone.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "a4-admin")
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        row = models.Invoice(
            tenant_id="local", invoice_number="LONE-1", invoice_type="AR",
            counterparty_name="Lone Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("500"),
            total_amount=Decimal("500"), face_amount_cents=50000,
            currency="INR")
        db.add(row)
        db.flush()
        db.add(models.AllocationProposal(
            tenant_id="local", afis_transaction_id="LONE-T1",
            transfer_cents=50000, currency="INR", created_by="local_admin",
            status="ambiguous"))
        db.commit()
        proposal_id = db.query(models.AllocationProposal).one().id
        invoice_id = row.id
    yield {"client": TestClient(app), "factory": factory, "engine": engine,
           "invoice": invoice_id, "proposal": proposal_id}
    engine.dispose()


def _auth(tokens, email):
    return {"Authorization": f"Bearer {tokens[email]}"}


def test_assign_and_history(teamdb):
    client = teamdb["client"]
    invoice = teamdb["invoice"]
    first = client.post(f"/api/v1/team/cases/{invoice}/assign", headers=ADMIN,
                        json={"assignee_user_id": teamdb["ids"]["s1@example.in"],
                              "reason": "initial triage duty"})
    assert first.status_code == 201, first.text
    assert first.json()["assignee_email"] == "s1@example.in"
    second = client.post(f"/api/v1/team/cases/{invoice}/assign", headers=ADMIN,
                         json={"assignee_user_id": teamdb["ids"]["s2@example.in"],
                               "reason": "rebalance workload"})
    assert second.status_code == 201
    history = client.get(f"/api/v1/team/cases/{invoice}/assignments",
                         headers=ADMIN).json()
    assert [row["assignee_email"] for row in history] == [
        "s1@example.in", "s2@example.in"]
    with teamdb["factory"]() as db:
        audits = db.query(models.AuditEvent).filter_by(
            action="case_assigned").order_by(models.AuditEvent.id).all()
        assert "before=unassigned; after=s1@example.in" in audits[0].details
        assert "before=s1@example.in; after=s2@example.in" in audits[1].details
        foreign = models.User(tenant_id="tenant-b", email="b@example.in",
                              name="B", password_hash="x", role="editor")
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
        target = db.get(models.User, teamdb["ids"]["s2@example.in"])
        target.is_active = False
        db.commit()
    assert client.post(f"/api/v1/team/cases/{invoice}/assign", headers=ADMIN,
                       json={"assignee_user_id": foreign_id,
                             "reason": "cross tenant attempt"}).status_code == 404
    assert client.post(f"/api/v1/team/cases/{invoice}/assign", headers=ADMIN,
                       json={"assignee_user_id": teamdb["ids"]["s2@example.in"],
                             "reason": "inactive user attempt"}).status_code == 404


def test_notes_append_only(teamdb):
    client = teamdb["client"]
    invoice = teamdb["invoice"]
    for body in ("Called the buyer; asked for UTR.", "UTR received; verifying."):
        res = client.post(f"/api/v1/team/cases/{invoice}/notes", headers=ADMIN,
                          json={"body": body})
        assert res.status_code == 201, res.text
    notes = client.get(f"/api/v1/team/cases/{invoice}/notes",
                       headers=ADMIN).json()
    assert [note["body"] for note in notes] == [
        "Called the buyer; asked for UTR.", "UTR received; verifying."]
    assert client.put(f"/api/v1/team/cases/{invoice}/notes",
                      headers=ADMIN, json={"body": "rewrite"}).status_code == 405


def test_task_lifecycle(teamdb):
    client = teamdb["client"]
    invoice = teamdb["invoice"]
    s1 = teamdb["ids"]["s1@example.in"]
    s2 = teamdb["ids"]["s2@example.in"]
    future = (date.today() + timedelta(days=3)).isoformat()
    created = client.post("/api/v1/team/tasks", headers=ADMIN, json={
        "invoice_id": invoice, "title": "Collect delivery note",
        "assignee_user_id": s1, "due_date": future})
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    done = client.post(f"/api/v1/team/tasks/{task_id}/complete",
                       headers=_auth(teamdb["tokens"], "s2@example.in"))
    assert done.status_code == 200
    assert done.json()["completed_by"] == "s2@example.in"
    assert client.post(f"/api/v1/team/tasks/{task_id}/complete",
                       headers=ADMIN).status_code == 409
    second = client.post("/api/v1/team/tasks", headers=ADMIN, json={
        "title": "Stale follow-up", "assignee_user_id": s1})
    assert client.post(f"/api/v1/team/tasks/{second.json()['id']}/cancel",
                       headers=ADMIN).status_code == 200
    third = client.post("/api/v1/team/tasks", headers=ADMIN, json={
        "title": "Verify UTR", "assignee_user_id": s1})
    moved = client.post(f"/api/v1/team/tasks/{third.json()['id']}/reassign",
                        headers=ADMIN,
                        json={"assignee_user_id": s2, "reason": "s1 is on leave"})
    assert moved.status_code == 200
    assert moved.json()["assignee_email"] == "s2@example.in"
    with teamdb["factory"]() as db:
        audit = db.query(models.AuditEvent).filter_by(
            action="task_reassigned").one()
        assert "before=s1@example.in; after=s2@example.in" in audit.details


def test_overdue_and_sweep(teamdb):
    client = teamdb["client"]
    invoice = teamdb["invoice"]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    task = client.post("/api/v1/team/tasks", headers=ADMIN, json={
        "invoice_id": invoice, "title": "Overdue chase",
        "assignee_user_id": teamdb["ids"]["s1@example.in"],
        "due_date": yesterday}).json()
    assert task["overdue"] is True
    esc = client.post(f"/api/v1/team/cases/{invoice}/escalations",
                      headers=ADMIN,
                      json={"reason": "Buyer stopped responding",
                            "deadline": yesterday}).json()
    assert esc["overdue"] is True
    swept = client.post("/api/v1/team/escalations/sweep", headers=ADMIN).json()
    assert swept == {"escalated": [esc["id"]]}
    with teamdb["factory"]() as db:
        assert db.get(models.CaseEscalation, esc["id"]).status == "escalated"
        assert db.get(models.Invoice, invoice).requires_human_review is True
    resolved = client.post(f"/api/v1/team/escalations/{esc['id']}/resolve",
                           headers=ADMIN, json={"reason": "buyer replied"})
    assert resolved.json()["status"] == "resolved"
    assert client.post(f"/api/v1/team/escalations/{esc['id']}/resolve",
                       headers=ADMIN, json={}).status_code == 409


def test_workload(teamdb):
    client = teamdb["client"]
    invoice = teamdb["invoice"]
    s1 = teamdb["ids"]["s1@example.in"]
    s2 = teamdb["ids"]["s2@example.in"]
    client.post(f"/api/v1/team/cases/{invoice}/assign", headers=ADMIN, json={
        "assignee_user_id": s1, "reason": "owns this case"})
    future = (date.today() + timedelta(days=3)).isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    client.post("/api/v1/team/tasks", headers=ADMIN, json={
        "title": "Current chase", "assignee_user_id": s1,
        "due_date": future})
    client.post("/api/v1/team/tasks", headers=ADMIN, json={
        "title": "Late chase", "assignee_user_id": s2,
        "due_date": yesterday})
    client.post(f"/api/v1/team/cases/{invoice}/escalations", headers=ADMIN,
                json={"reason": "Needs senior eyes", "deadline": future})
    rows = {row["assignee_email"]: row for row in
            client.get("/api/v1/team/workload", headers=ADMIN).json()}
    assert rows["s1@example.in"] == {"assignee_email": "s1@example.in",
                                     "open_tasks": 1, "overdue_tasks": 0,
                                     "assigned_cases": 1, "open_escalations": 1}
    assert rows["s2@example.in"] == {"assignee_email": "s2@example.in",
                                     "open_tasks": 1, "overdue_tasks": 1,
                                     "assigned_cases": 0, "open_escalations": 0}


def test_sod_blocks_self_approval_of_allocation(teamdb):
    client = teamdb["client"]
    boss = _auth(teamdb["tokens"], "boss@example.in")
    with teamdb["factory"]() as db:
        db.add(models.AllocationProposal(
            tenant_id="local", afis_transaction_id="A4-T1",
            transfer_cents=10000, currency="INR",
            created_by="boss@example.in", status="ambiguous"))
        db.commit()
        proposal_id = db.query(models.AllocationProposal).one().id
    blocked = client.post(
        f"/api/v1/allocations/proposals/{proposal_id}/approve",
        headers=boss, json={"legs": []})
    assert blocked.status_code == 409
    assert "Separation of duties" in blocked.json()["detail"]
    other = client.post(
        f"/api/v1/allocations/proposals/{proposal_id}/approve",
        headers=ADMIN, json={"legs": []})
    assert other.status_code == 200, other.text


def test_sod_dunning_edit_then_self_approve_blocked(teamdb):
    client = teamdb["client"]
    s1 = _auth(teamdb["tokens"], "s1@example.in")
    with teamdb["factory"]() as db:
        db.add(models.DunningCampaign(
            tenant_id="local", invoice_id=teamdb["invoice"], campaign_stage=1,
            days_overdue=10, tone="polite", email_subject="Overdue invoice",
            email_body="agent draft", balance_cents_at_draft=100000,
            status="draft", generated_by="recoverflow_agent"))
        db.commit()
        campaign_id = db.query(models.DunningCampaign).one().id
    edited = client.put(f"/api/v1/dunning/campaigns/{campaign_id}", headers=s1,
                        json={"subject": "Overdue invoice",
                              "body": "Regarding invoice A4-1, please arrange "
                                      "payment of the undisputed 1,000.00."})
    assert edited.status_code == 200, edited.text
    with teamdb["factory"]() as db:
        assert db.get(models.DunningCampaign,
                      campaign_id).generated_by == "s1@example.in"
    blocked = client.post(f"/api/v1/dunning/campaigns/{campaign_id}/approve",
                          headers=s1)
    assert blocked.status_code == 409
    assert "Separation of duties" in blocked.json()["detail"]


def test_sod_negotiation_and_draft_approvals(teamdb):
    client = teamdb["client"]
    boss = _auth(teamdb["tokens"], "boss@example.in")
    invoice = teamdb["invoice"]
    with teamdb["factory"]() as db:
        db.add(models.NegotiationSession(tenant_id="local", invoice_id=invoice,
                                         mode="manual", status="active"))
        db.flush()
        session_id = db.query(models.NegotiationSession).one().id
        db.add(models.NegotiationTurn(
            tenant_id="local", session_id=session_id, direction="outbound",
            actor="boss@example.in", body="staff offer",
            body_hash="a" * 64, status="pending_approval"))
        db.add(models.AgentProposal(
            tenant_id="local", invoice_id=invoice, context_hash="ctx-a4",
            engine="template", summary="s", rationale="r", action="draft",
            balance_cents_at_proposal=100000))
        db.flush()
        proposal_id = db.query(models.AgentProposal).one().id
        db.add(models.ProposalDraftVersion(
            tenant_id="local", proposal_id=proposal_id, version_number=1,
            body="agent draft", edited_by="boss@example.in",
            version_hash="b" * 64))
        db.commit()
        turn_id = db.query(models.NegotiationTurn).one().id
    turn = client.post(
        f"/api/v1/negotiations/cases/{invoice}/turns/{turn_id}/approve",
        headers=boss, json={"body_hash": "a" * 64})
    assert turn.status_code == 409
    assert "Separation of duties" in turn.json()["detail"]
    draft = client.post(f"/api/v1/agent/proposals/{proposal_id}/approve",
                        headers=boss,
                        json={"version_number": 1,
                              "version_hash": "b" * 64})
    assert draft.status_code == 409
    assert "Separation of duties" in draft.json()["detail"]


def test_sod_lone_operator_proceeds_with_audit(lonedb):
    client = lonedb["client"]
    res = client.post(
        f"/api/v1/allocations/proposals/{lonedb['proposal']}/approve",
        headers=ADMIN,
        json={"legs": [{"invoice_id": lonedb["invoice"],
                        "amount_cents": 10000,
                        "allocation": "undisputed_first"}]})
    assert res.status_code == 200, res.text
    with lonedb["factory"]() as db:
        assert db.query(models.AuditEvent).filter_by(
            action="sod_skipped_lone_operator").count() == 1
        assert db.query(models.ReceivableEntry).filter_by(
            source="allocated_transfer").count() == 1


def test_sod_allows_matrix(teamdb, lonedb):
    with teamdb["factory"]() as db:
        assert team_ops.sod_allows(db, "local", "agent", "s1@example.in",
                                   "draft approval", "p:1") == (True, "")
        allowed, reason = team_ops.sod_allows(db, "local", "s1@example.in",
                                              "s1@example.in", "draft approval",
                                              "p:1")
        assert allowed is False
        assert "Separation of duties" in reason
    with lonedb["factory"]() as db:
        allowed, _ = team_ops.sod_allows(db, "local", "local_admin",
                                         "local_admin", "draft approval", "p:1")
        assert allowed is True


def test_queue_surfaces_escalation(teamdb):
    client = teamdb["client"]
    invoice = teamdb["invoice"]
    future = (date.today() + timedelta(days=3)).isoformat()
    client.post(f"/api/v1/team/cases/{invoice}/escalations", headers=ADMIN,
                json={"reason": "VIP buyer; handle first", "deadline": future})
    queue = client.get("/api/v1/supervisor/queue", headers=ADMIN).json()
    assert queue[0]["action"] == "Resolve escalation"
    assert queue[0]["invoice_id"] == invoice


def test_team_cross_tenant_isolation(teamdb):
    client = teamdb["client"]
    with teamdb["factory"]() as db:
        foreign_invoice = models.Invoice(
            tenant_id="tenant-b", invoice_number="B-9", invoice_type="AR",
            counterparty_name="B Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("100"),
            total_amount=Decimal("100"), face_amount_cents=10000,
            currency="INR")
        foreign_user = models.User(tenant_id="tenant-b", email="b@example.in",
                                   name="B", password_hash="x", role="editor")
        db.add_all([foreign_invoice, foreign_user])
        db.flush()
        db.add(models.StaffTask(
            tenant_id="tenant-b", title="Foreign task",
            assignee_user_id=foreign_user.id, assignee_email="b@example.in",
            created_by="b@example.in", status="open"))
        db.commit()
        foreign_id = foreign_invoice.id
    assert client.post(f"/api/v1/team/cases/{foreign_id}/assign", headers=ADMIN,
                       json={"assignee_user_id": teamdb["ids"]["s1@example.in"],
                             "reason": "cross tenant attempt"}).status_code == 404
    assert client.post(f"/api/v1/team/cases/{foreign_id}/notes", headers=ADMIN,
                       json={"body": "cross tenant note"}).status_code == 404
    tasks = client.get("/api/v1/team/tasks", headers=ADMIN).json()
    assert all(task["tenant_id"] == "local" if "tenant_id" in task else True
               for task in tasks)
    assert "Foreign task" not in [task["title"] for task in tasks]
