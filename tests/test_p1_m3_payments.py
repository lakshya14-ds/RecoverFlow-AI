"""Milestone 3: transfer allocation, ambiguity, and promise tracking."""
import json
import sqlite3
from datetime import date, timedelta
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
from app.services import supervisor
from app.services.promises import extract_promise, refresh
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


@pytest.fixture
def afis(tmp_path, monkeypatch):
    path = tmp_path / "afis.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE transactions (id TEXT PRIMARY KEY, date TEXT,"
                       " description TEXT, amount REAL, category TEXT)")
    connection.commit()
    connection.close()
    monkeypatch.setattr(settings, "AFIS_DB_PATH", str(path))
    return path


def add_txn(path, txn_id, day, description, amount):
    connection = sqlite3.connect(path)
    connection.execute("INSERT INTO transactions VALUES (?,?,?,?,?)",
                       (txn_id, day, description, amount, "bank"))
    connection.commit()
    connection.close()


HEADERS = {"X-RECOVERFLOW-API-KEY": "test-key"}


def invoice(db, number, amount="1000.00", currency="INR",
            customer="Synthetic distributor", tenant="local"):
    row = models.Invoice(tenant_id=tenant, invoice_number=number, invoice_type="AR",
        counterparty_name=customer, issue_date=date(2026, 9, 1),
        due_date=date(2026, 10, 15), amount=Decimal(amount),
        total_amount=Decimal(amount), face_amount_cents=int(Decimal(amount) * 100),
        disputed_cents=0, currency=currency)
    db.add(row)
    db.flush()
    return row


def test_split_one_transfer_across_two_invoices(db, api, afis):
    first = invoice(db, "INV-M3A")
    second = invoice(db, "INV-M3B")
    db.commit()
    add_txn(afis, "T1", "2026-10-20", "NEFT INV-M3A INV-M3B", 1500.00)
    proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                        json={"afis_transaction_id": "T1"})
    assert proposed.status_code == 201, proposed.text
    body = proposed.json()
    assert body["status"] == "proposed"
    assert [(leg["invoice_id"], leg["amount_cents"]) for leg in body["legs"]] == [
        (first.id, 100000), (second.id, 50000)]
    approved = api.post(f"/api/v1/allocations/proposals/{body['id']}/approve",
                        headers=HEADERS, json={"reason": "Split across both references"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "applied"
    assert approved.json()["residual_cents"] == 0
    assert split_balance(db, first)["outstanding_cents"] == 0
    assert split_balance(db, second)["outstanding_cents"] == 50000
    entries = db.query(models.ReceivableEntry).filter_by(source="allocated_transfer").all()
    assert sorted(-e.amount_cents for e in entries) == [50000, 100000]


def test_several_transfers_against_one_invoice(db, api, afis):
    row = invoice(db, "INV-M3C")
    db.commit()
    for txn_id, amount in (("T2", 400.00), ("T3", 300.00)):
        add_txn(afis, txn_id, "2026-10-20", f"UPI {txn_id} INV-M3C", amount)
        proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                            json={"afis_transaction_id": txn_id})
        assert proposed.json()["status"] == "proposed"
        approved = api.post(
            f"/api/v1/allocations/proposals/{proposed.json()['id']}/approve",
            headers=HEADERS, json={})
        assert approved.status_code == 200, approved.text
    assert split_balance(db, row)["outstanding_cents"] == 30000
    add_txn(afis, "T4", "2026-10-21", "UPI T4 INV-M3C", 500.00)
    proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                        json={"afis_transaction_id": "T4"})
    proposal_id = proposed.json()["id"]
    over = api.post(f"/api/v1/allocations/proposals/{proposal_id}/approve", headers=HEADERS,
                    json={"legs": [{"invoice_id": row.id, "amount_cents": 50000}]})
    assert over.status_code == 409
    partial = api.post(f"/api/v1/allocations/proposals/{proposal_id}/approve",
                       headers=HEADERS, json={})
    assert partial.status_code == 200, partial.text
    assert partial.json()["status"] == "partially_applied"
    assert partial.json()["residual_cents"] == 20000
    assert split_balance(db, row)["outstanding_cents"] == 0


def test_duplicate_proposal_and_approve_are_idempotent(db, api, afis):
    row = invoice(db, "INV-M3D")
    db.commit()
    add_txn(afis, "T5", "2026-10-20", "NEFT INV-M3D", 1000.00)
    first = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                     json={"afis_transaction_id": "T5"})
    second = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                      json={"afis_transaction_id": "T5"})
    assert second.json()["duplicate"] is True
    assert second.json()["id"] == first.json()["id"]
    approved = api.post(f"/api/v1/allocations/proposals/{first.json()['id']}/approve",
                        headers=HEADERS, json={})
    assert approved.json()["status"] == "applied"
    again = api.post(f"/api/v1/allocations/proposals/{first.json()['id']}/approve",
                     headers=HEADERS, json={})
    assert again.json()["status"] == "applied"
    assert db.query(models.ReceivableEntry).filter_by(
        tenant_id="local", source="allocated_transfer").count() == 1
    assert split_balance(db, row)["outstanding_cents"] == 0


def test_reversed_leg_keeps_books_consistent(db, api, afis):
    row = invoice(db, "INV-M3E")
    db.commit()
    add_txn(afis, "T6", "2026-10-20", "NEFT INV-M3E", 500.00)
    proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                        json={"afis_transaction_id": "T6"})
    proposal_id = proposed.json()["id"]
    approved = api.post(f"/api/v1/allocations/proposals/{proposal_id}/approve",
                        headers=HEADERS, json={})
    entry_id = approved.json()["legs"][0]["entry_id"]
    reversed_ = api.post(f"/api/v1/cases/{row.id}/entries/{entry_id}/reverse",
                         headers=HEADERS, json={"reason": "Transfer recalled by bank"})
    assert reversed_.status_code == 201, reversed_.text
    assert split_balance(db, row)["outstanding_cents"] == 100000
    detail = api.get(f"/api/v1/allocations/proposals/{proposal_id}", headers=HEADERS)
    assert detail.json()["status"] == "applied"
    assert detail.json()["legs"][0]["status"] == "applied"


def test_ambiguous_match_needs_explicit_staff_legs(db, api, afis):
    first = invoice(db, "INV-M3F")
    invoice(db, "INV-M3G")
    db.commit()
    add_txn(afis, "T7", "2026-01-05", "CASH DEPOSIT", 500.00)
    proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                        json={"afis_transaction_id": "T7"})
    body = proposed.json()
    assert body["status"] == "ambiguous"
    assert any("repeated amount" in note
               for candidate in body["candidates"] for note in candidate["uncertainty"])
    blocked = api.post(f"/api/v1/allocations/proposals/{body['id']}/approve",
                       headers=HEADERS, json={})
    assert blocked.status_code == 409
    chosen = api.post(f"/api/v1/allocations/proposals/{body['id']}/approve",
                      headers=HEADERS,
                      json={"legs": [{"invoice_id": first.id, "amount_cents": 50000}],
                            "reason": "Staff matched the deposit slip"})
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["status"] == "applied"
    assert split_balance(db, first)["outstanding_cents"] == 50000


def test_tenant_and_currency_guards(db, api, afis):
    row = invoice(db, "INV-M3H")
    foreign = invoice(db, "INV-M3X", tenant="other")
    dollar = invoice(db, "INV-M3U", currency="USD")
    db.commit()
    add_txn(afis, "T8", "2026-10-20", "NEFT INV-M3H", 500.00)
    proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                        json={"afis_transaction_id": "T8"})
    numbers = [c["invoice_number"] for c in proposed.json()["candidates"]]
    assert numbers == ["INV-M3H"]
    assert "INV-M3U" not in numbers
    wrong_currency = api.post(
        f"/api/v1/allocations/proposals/{proposed.json()['id']}/approve", headers=HEADERS,
        json={"legs": [{"invoice_id": dollar.id, "amount_cents": 10000}]})
    assert wrong_currency.status_code == 409
    wrong_tenant = api.post(
        f"/api/v1/allocations/proposals/{proposed.json()['id']}/approve", headers=HEADERS,
        json={"legs": [{"invoice_id": foreign.id, "amount_cents": 10000}]})
    assert wrong_tenant.status_code == 409
    assert split_balance(db, row)["outstanding_cents"] == 100000


def test_payer_alias_and_match_reasons(db, api, afis):
    row = invoice(db, "INV-M3I", customer="Apex Enterprises")
    invoice(db, "INV-M3J", customer="Other Buyer")
    db.commit()
    created = api.post("/api/v1/allocations/payer-aliases", headers=HEADERS,
                       json={"alias": "apex", "counterparty_name": "Apex Enterprises"})
    assert created.status_code == 201, created.text
    add_txn(afis, "T9", "2026-10-20", "NEFT apex INV-M3I", 1000.00)
    proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                        json={"afis_transaction_id": "T9"})
    body = proposed.json()
    assert body["status"] == "proposed"
    match = next(c for c in body["candidates"] if c["invoice_id"] == row.id)
    assert any("apex" in reason for reason in match["reasons"])
    other = next(c for c in body["candidates"] if c["invoice_number"] == "INV-M3J")
    assert "no invoice reference" in other["uncertainty"]


def test_missing_reference_and_date_reasons(db, api, afis):
    row = invoice(db, "INV-M3K")
    db.commit()
    add_txn(afis, "T10", "2026-01-05", "CASH DEPOSIT", 1000.00)
    proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                        json={"afis_transaction_id": "T10"})
    match = next(c for c in proposed.json()["candidates"] if c["invoice_id"] == row.id)
    assert "no invoice reference" in match["uncertainty"]
    assert any("date differs" in note for note in match["uncertainty"])


def test_promise_lifecycle_broken_then_kept(db, api):
    row = invoice(db, "INV-M3L")
    db.commit()
    reply = api.post(f"/api/v1/cases/{row.id}/replies", headers=HEADERS,
        json={"category": "needs_time", "body": "Will pay Rs 5000 by Friday"})
    recorded = api.post(f"/api/v1/cases/{row.id}/promises", headers=HEADERS,
        json={"message_id": reply.json()["message_id"]})
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["status"] == "alleged"
    assert recorded.json()["extraction_confidence"] == 0.9
    assert recorded.json()["promised_cents"] == 500000
    promise_id = recorded.json()["id"]
    confirmed = api.post(f"/api/v1/cases/{row.id}/promises/{promise_id}/confirm",
                         headers=HEADERS)
    assert confirmed.json()["status"] == "confirmed"
    reminded = api.post(f"/api/v1/cases/{row.id}/promises/{promise_id}/remind",
                        headers=HEADERS)
    assert reminded.json()["reminders_sent"] == 1
    assert split_balance(db, row)["received_cents"] == 0
    assert split_balance(db, row)["outstanding_cents"] == 100000
    db.get(models.PromiseToPay, promise_id).promised_date = date.today() - timedelta(days=1)
    db.commit()
    refresh(db, row)
    assert db.get(models.PromiseToPay, promise_id).status == "broken"

    reply2 = api.post(f"/api/v1/cases/{row.id}/replies", headers=HEADERS,
        json={"category": "needs_time", "body": "Paying Rs 200 tomorrow"})
    second = api.post(f"/api/v1/cases/{row.id}/promises", headers=HEADERS,
        json={"message_id": reply2.json()["message_id"]})
    assert second.json()["promised_cents"] == 20000
    post_entry(db, row, kind="payment", amount="200", source="manual",
               reference="M3-KEPT", actor="staff")
    db.commit()
    assert db.get(models.PromiseToPay, second.json()["id"]).status == "kept"


def test_promise_never_touches_cash_or_stage(db, api):
    from app.services.case_lifecycle import checkpoint
    row = invoice(db, "INV-M3M")
    db.commit()
    reply = api.post(f"/api/v1/cases/{row.id}/replies", headers=HEADERS,
        json={"category": "needs_time", "body": "Will pay Rs 1000 tomorrow"})
    recorded = api.post(f"/api/v1/cases/{row.id}/promises", headers=HEADERS,
        json={"message_id": reply.json()["message_id"]})
    api.post(f"/api/v1/cases/{row.id}/promises/{recorded.json()['id']}/confirm",
             headers=HEADERS)
    split = split_balance(db, row)
    assert (split["received_cents"], split["outstanding_cents"]) == (0, 100000)
    assert row.status == "pending"
    assert checkpoint(db, row, "test").stage == "READY_FOR_REVIEW"


def test_reconciliation_specialist_escalates_ambiguous(db, api, afis):
    row = invoice(db, "INV-M3N")
    db.commit()
    add_txn(afis, "T11", "2026-01-05", "NEFT INV-M3N", 1500.00)
    proposed = api.post("/api/v1/allocations/proposals", headers=HEADERS,
                        json={"afis_transaction_id": "T11"})
    assert proposed.json()["status"] == "ambiguous"
    assert any(leg["invoice_id"] == row.id for leg in proposed.json()["legs"])
    queued = supervisor.reassess(db, row, "test")
    assert queued["kind"] == "reconciliation"
    outcome = supervisor.run_task(db, queued["task_id"])
    assert outcome["outcome"] == "escalated", outcome
    result = json.loads(db.get(models.SupervisorTask, queued["task_id"]).result_json)
    assert "ambiguous_match" in result["escalation_conditions"]


def test_razorpay_stays_unconfigured_without_keys(api, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    response = api.post("/api/v1/payments/links", headers=HEADERS,
        json={"invoice_id": 1,
              "idempotency_key": "12345678-1234-5678-1234-567812345678"})
    assert response.status_code == 503


def test_promise_extraction_rules():
    friday = extract_promise("Will pay Rs 5000 by Friday")
    assert friday["amount_cents"] == 500000
    assert friday["promised_date"].weekday() == 4
    assert friday["confidence"] == 0.9
    assert extract_promise("Paying ₹200 tomorrow")["confidence"] == 0.9
    assert extract_promise("Will pay Rs 100")["confidence"] == 0.6
    assert extract_promise("Will pay on Monday")["confidence"] == 0.4
    with pytest.raises(ValueError, match="No promised amount"):
        extract_promise("Thanks for calling")
