"""P2 B3: installment schedules — legs, waterfall application, late/missed,
reschedule/cancel/reversal, and the schedule-vs-ledger split."""
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app
from app.services import schedules
from app.services.receivables import split_balance

ADMIN = {"X-RECOVERFLOW-API-KEY": "b3-admin"}
BOSS = {"X-RECOVERFLOW-API-KEY": "b3-boss"}


@pytest.fixture()
def paydb(monkeypatch, tmp_path):
    db_path = tmp_path / "b3.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "b3-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "b3-boss", "actor": "boss@example.in", "tenant_id": "local",
          "role": "admin"}]))
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    with factory() as db:
        for email in ("s1@example.in", "s2@example.in"):
            db.add(models.User(tenant_id="local", email=email, name=email,
                               password_hash="x", role="editor"))
        row = models.Invoice(
            tenant_id="local", invoice_number="INV-B3", invoice_type="AR",
            counterparty_name="B3 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR")
        db.add(row)
        db.commit()
        invoice_id = row.id
    yield {"client": TestClient(app), "factory": factory, "engine": engine,
           "invoice": invoice_id}
    engine.dispose()


def _legs(*pairs):
    return [{"due_date": day.isoformat(), "amount_cents": cents}
            for day, cents in pairs]


def _active(client, invoice_id, legs, **kwargs):
    created = client.post(f"/api/v1/cases/{invoice_id}/schedules",
                          headers=ADMIN, json={"legs": legs, **kwargs})
    assert created.status_code == 201, created.text
    approved = client.post(
        f"/api/v1/cases/{invoice_id}/schedules/{created.json()['id']}/approve",
        headers=BOSS, json={})
    assert approved.status_code == 200, approved.text
    return approved.json()


def _pay(client, invoice_id, amount, reference):
    res = client.post(f"/api/v1/cases/{invoice_id}/entries", headers=ADMIN,
                      json={"kind": "payment", "amount": amount,
                            "reference": reference, "currency": "INR"})
    assert res.status_code == 201, res.text
    return res.json()


def test_create_and_approve(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    future = date.today() + timedelta(days=10)
    created = client.post(f"/api/v1/cases/{invoice}/schedules",
                          headers=ADMIN,
                          json={"legs": _legs((future, 50000),
                                              (future, 50000)),
                                "terms": "Two halves"})
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "proposed"
    schedule_id = created.json()["id"]
    blocked = client.post(
        f"/api/v1/cases/{invoice}/schedules/{schedule_id}/approve",
        headers=ADMIN, json={})
    assert blocked.status_code == 409
    assert "Separation of duties" in blocked.json()["detail"]
    approved = client.post(
        f"/api/v1/cases/{invoice}/schedules/{schedule_id}/approve",
        headers=BOSS, json={})
    assert approved.json()["status"] == "active"
    over = client.post(f"/api/v1/cases/{invoice}/schedules", headers=ADMIN,
                       json={"legs": _legs((future, 150000))})
    assert over.status_code == 409
    assert client.post(f"/api/v1/cases/{invoice}/schedules", headers=ADMIN,
                       json={"legs": []}).status_code == 422
    assert client.post(f"/api/v1/cases/{invoice}/schedules", headers=ADMIN,
                       json={"legs": _legs((future, 1000)),
                             "promise_id": 999999}).status_code == 404
    with paydb["factory"]() as db:
        assert db.get(models.Invoice, invoice).status == "pending"


def test_promise_link(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    with paydb["factory"]() as db:
        db.add(models.PromiseToPay(
            tenant_id="local", invoice_id=invoice, promised_cents=100000,
            promised_date=date.today(), source_text="will pay in halves",
            status="confirmed", confirmed_by="boss@example.in"))
        db.commit()
        promise_id = db.query(models.PromiseToPay).one().id
        foreign_invoice = models.Invoice(
            tenant_id="local", invoice_number="INV-B3X", invoice_type="AR",
            counterparty_name="Other", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("10"),
            total_amount=Decimal("10"), face_amount_cents=1000,
            currency="INR")
        db.add(foreign_invoice)
        db.flush()
        db.add(models.PromiseToPay(
            tenant_id="local", invoice_id=foreign_invoice.id,
            promised_cents=1000, promised_date=date.today(),
            source_text="other", status="alleged"))
        db.commit()
        foreign_promise = db.query(models.PromiseToPay).filter(
            models.PromiseToPay.invoice_id == foreign_invoice.id).one().id
    future = date.today() + timedelta(days=10)
    linked = client.post(f"/api/v1/cases/{invoice}/schedules", headers=ADMIN,
                         json={"legs": _legs((future, 100000)),
                               "promise_id": promise_id})
    assert linked.json()["promise_id"] == promise_id
    assert client.post(f"/api/v1/cases/{invoice}/schedules", headers=ADMIN,
                       json={"legs": _legs((future, 1000)),
                             "promise_id": foreign_promise}).status_code == 404


def test_payment_waterfalls_oldest_first(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    first = date.today() + timedelta(days=10)
    second = date.today() + timedelta(days=20)
    view = _active(client, invoice, _legs((first, 50000), (second, 50000)))
    _pay(client, invoice, "700.00", "b3-waterfall")
    got = client.get(f"/api/v1/cases/{invoice}/schedules/{view['id']}",
                     headers=ADMIN).json()
    assert [(leg["status"], leg["paid_cents"]) for leg in got["legs"]] == [
        ("paid", 50000), ("partial", 20000)]
    assert got["remaining_cents"] == 30000
    with paydb["factory"]() as db:
        split = split_balance(db, db.get(models.Invoice, invoice))
        assert split["outstanding_cents"] == 30000
        assert split["received_cents"] == 70000


def test_exact_pay_completes_but_ledger_owns_closure(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    future = date.today() + timedelta(days=10)
    view = _active(client, invoice, _legs((future, 100000)))
    with paydb["factory"]() as db:
        assert db.get(models.Invoice, invoice).status == "pending"
    _pay(client, invoice, "1000.00", "b3-full")
    got = client.get(f"/api/v1/cases/{invoice}/schedules/{view['id']}",
                     headers=ADMIN).json()
    assert got["status"] == "completed"
    with paydb["factory"]() as db:
        assert db.get(models.Invoice, invoice).status == "paid"


def test_overpay_leaves_residual_unapplied(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    future = date.today() + timedelta(days=10)
    view = _active(client, invoice, _legs((future, 50000)))
    _pay(client, invoice, "600.00", "b3-overpay")
    got = client.get(f"/api/v1/cases/{invoice}/schedules/{view['id']}",
                     headers=ADMIN).json()
    assert got["legs"][0]["status"] == "paid"
    assert got["remaining_cents"] == 0
    with paydb["factory"]() as db:
        total = sum(row.amount_cents for row in
                    db.query(models.InstallmentApplication).all())
        assert total == 50000
        assert split_balance(
            db, db.get(models.Invoice, invoice))["outstanding_cents"] == 40000


def test_reversal_unapplies_with_history(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    future = date.today() + timedelta(days=10)
    view = _active(client, invoice,
                   _legs((future, 50000), (future, 50000)))
    entry = _pay(client, invoice, "1000.00", "b3-reversed")
    assert client.get(f"/api/v1/cases/{invoice}/schedules/{view['id']}",
                      headers=ADMIN).json()["status"] == "completed"
    undone = client.post(
        f"/api/v1/cases/{invoice}/entries/{entry['entry_id']}/reverse",
        headers=ADMIN, json={"reason": "payment bounced"})
    assert undone.status_code == 201, undone.text
    got = client.get(f"/api/v1/cases/{invoice}/schedules/{view['id']}",
                     headers=ADMIN).json()
    assert got["status"] == "active"
    assert [(leg["status"], leg["paid_cents"]) for leg in got["legs"]] == [
        ("pending", 0), ("pending", 0)]
    with paydb["factory"]() as db:
        rows = db.query(models.InstallmentApplication).all()
        assert len(rows) == 2 and all(row.reversed for row in rows)
        assert split_balance(
            db, db.get(models.Invoice, invoice))["outstanding_cents"] == 100000


def test_reschedule_and_cancel(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    first = date.today() + timedelta(days=10)
    second = date.today() + timedelta(days=20)
    view = _active(client, invoice, _legs((first, 50000), (second, 50000)))
    leg_id = view["legs"][0]["id"]
    moved = client.post(
        f"/api/v1/cases/{invoice}/schedules/{view['id']}/legs/{leg_id}/reschedule",
        headers=ADMIN,
        json={"new_due_date": (date.today() + timedelta(days=30)).isoformat()})
    assert moved.status_code == 200, moved.text
    assert moved.json()["supersedes_id"] == leg_id
    got = client.get(f"/api/v1/cases/{invoice}/schedules/{view['id']}",
                     headers=ADMIN).json()
    assert got["legs"][0]["status"] == "rescheduled"
    assert got["total_cents"] == 100000
    _pay(client, invoice, "500.00", "b3-partial")
    paid_id = next(leg["id"] for leg in client.get(
        f"/api/v1/cases/{invoice}/schedules/{view['id']}",
        headers=ADMIN).json()["legs"] if leg["status"] == "paid")
    assert client.post(
        f"/api/v1/cases/{invoice}/schedules/{view['id']}/legs/{paid_id}/reschedule",
        headers=ADMIN,
        json={"new_due_date": first.isoformat()}).status_code == 409
    cancelled = client.post(
        f"/api/v1/cases/{invoice}/schedules/{view['id']}/cancel",
        headers=ADMIN, json={"reason": "buyer renegotiating"})
    assert cancelled.json()["status"] == "cancelled"
    assert {leg["status"] for leg in cancelled.json()["legs"]} == {
        "paid", "rescheduled", "cancelled"}
    with paydb["factory"]() as db:
        assert split_balance(
            db, db.get(models.Invoice, invoice))["outstanding_cents"] == 50000


def test_late_and_missed_computed(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    view = _active(client, invoice, _legs(
        (date.today() - timedelta(days=1), 10000),
        (date.today() - timedelta(days=40), 10000),
        (date.today() + timedelta(days=5), 10000)))
    flags = [(leg["late"], leg["missed"]) for leg in view["legs"]]
    assert flags == [(True, False), (True, True), (False, False)]


def test_credit_does_not_apply(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    future = date.today() + timedelta(days=10)
    view = _active(client, invoice, _legs((future, 100000)))
    res = client.post(f"/api/v1/cases/{invoice}/entries", headers=ADMIN,
                      json={"kind": "credit", "amount": "200.00",
                            "reference": "b3-credit", "currency": "INR"})
    assert res.status_code == 201, res.text
    got = client.get(f"/api/v1/cases/{invoice}/schedules/{view['id']}",
                     headers=ADMIN).json()
    assert got["paid_cents"] == 0
    with paydb["factory"]() as db:
        assert db.query(models.InstallmentApplication).count() == 0


def test_apply_is_idempotent(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    future = date.today() + timedelta(days=10)
    _active(client, invoice, _legs((future, 50000), (future, 50000)))
    entry = _pay(client, invoice, "500.00", "b3-idem")
    with paydb["factory"]() as db:
        row = db.query(models.ReceivableEntry).filter_by(
            reference="b3-idem").one()
        assert schedules.apply_entry(db, row) == []
        assert db.query(models.InstallmentApplication).count() == 1
    assert entry["entry_id"] == row.id


def test_waterfall_across_schedules_without_double_count(paydb):
    client = paydb["client"]
    invoice = paydb["invoice"]
    future = date.today() + timedelta(days=10)
    first = _active(client, invoice, _legs((future, 30000)))
    second = _active(client, invoice, _legs((future, 30000)))
    _pay(client, invoice, "500.00", "b3-two")
    got_first = client.get(f"/api/v1/cases/{invoice}/schedules/{first['id']}",
                           headers=ADMIN).json()
    got_second = client.get(
        f"/api/v1/cases/{invoice}/schedules/{second['id']}",
        headers=ADMIN).json()
    assert got_first["paid_cents"] == 30000
    assert got_second["paid_cents"] == 20000
    with paydb["factory"]() as db:
        total = sum(row.amount_cents for row in
                    db.query(models.InstallmentApplication).all())
        assert total == 50000


def test_cross_tenant_isolation(paydb):
    client = paydb["client"]
    with paydb["factory"]() as db:
        foreign = models.Invoice(
            tenant_id="tenant-b", invoice_number="B-9", invoice_type="AR",
            counterparty_name="B Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("100"),
            total_amount=Decimal("100"), face_amount_cents=10000,
            currency="INR")
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    future = date.today() + timedelta(days=10)
    assert client.post(f"/api/v1/cases/{foreign_id}/schedules", headers=ADMIN,
                       json={"legs": _legs((future, 1000))}).status_code == 404
    assert client.get(f"/api/v1/cases/{foreign_id}/schedules",
                      headers=ADMIN).status_code == 404
