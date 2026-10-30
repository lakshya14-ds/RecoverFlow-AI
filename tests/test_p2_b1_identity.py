"""P2 B1: counterparty identity — GSTIN, branches, external IDs, duplicates,
staff-confirmed merges, bootstrap, and import linking."""
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app
from app.services.import_adapter import confirm_import

ADMIN = {"X-RECOVERFLOW-API-KEY": "b1-admin"}
GSTIN_A = "27AAPCS1234F1Z5"
GSTIN_B = "29ABCDE1234F2Z6"


@pytest.fixture()
def bizdb(monkeypatch, tmp_path):
    db_path = tmp_path / "b1.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "b1-admin")
    db_manager.init_db()
    client = TestClient(app)
    created = client.post("/api/v1/auth/users", headers=ADMIN, json={
        "email": "ed@example.in", "name": "Ed", "password": "StaffPass1!",
        "role": "editor"})
    assert created.status_code == 201, created.text
    token = client.post("/api/v1/auth/login", json={
        "email": "ed@example.in", "password": "StaffPass1!"}).json()["token"]
    yield {"client": client, "factory": sessionmaker(bind=engine),
           "engine": engine,
           "editor": {"Authorization": f"Bearer {token}"}}
    engine.dispose()


def _party(client, headers, name, **overrides):
    payload = {"name": name, "type": "customer"}
    payload.update(overrides)
    res = client.post("/api/v1/counterparties", headers=headers, json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def _invoice(factory, number, name, invoice_type="AR"):
    with factory() as db:
        row = models.Invoice(
            tenant_id="local", invoice_number=number, invoice_type=invoice_type,
            counterparty_name=name, issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR")
        db.add(row)
        db.commit()
        return row.id


def test_create_and_get_with_gstin(bizdb):
    client = bizdb["client"]
    created = _party(client, ADMIN, "Apex Traders", gstin=GSTIN_A.lower(),
                     legal_name="Apex Traders Pvt Ltd",
                     display_name="Apex", email="apex@example.in",
                     phone="+91-9820012345", billing_address="Mumbai",
                     shipping_address="Mumbai port")
    assert created["gstin"] == GSTIN_A
    assert created["status"] == "active"
    fetched = client.get(f"/api/v1/counterparties/{created['id']}",
                         headers=ADMIN).json()
    assert fetched["branches"] == [] and fetched["external_ids"] == []
    patched = client.patch(f"/api/v1/counterparties/{created['id']}",
                           headers=ADMIN,
                           json={"legal_name": "Apex Traders Private Limited"})
    assert patched.status_code == 200
    assert patched.json()["legal_name"] == "Apex Traders Private Limited"


def test_gstin_validation(bizdb):
    client = bizdb["client"]
    for bad in ("too-short", "27AAPCS123F1Z5", "27AAPCS1234F0Z5",
                "27AAPCS1234F1A5", "99AAPCS1234F1Z5", "00AAPCS1234F1Z5",
                "27aapcs1234f1z!", "27 AAPCS1234F1Z5"):
        res = client.post("/api/v1/counterparties", headers=ADMIN, json={
            "name": f"Bad {bad}", "type": "customer", "gstin": bad})
        assert res.status_code == 422, bad
    blank = _party(client, ADMIN, "No GSTIN Party", gstin="  ")
    assert blank["gstin"] is None
    missing = _party(client, ADMIN, "Missing GSTIN Party")
    assert missing["gstin"] is None


def test_gstin_unique_per_tenant(bizdb):
    client = bizdb["client"]
    _party(client, ADMIN, "First Holder", gstin=GSTIN_A)
    dup = client.post("/api/v1/counterparties", headers=ADMIN, json={
        "name": "Second Holder", "type": "customer", "gstin": GSTIN_A})
    assert dup.status_code == 409
    with bizdb["factory"]() as db:
        db.add(models.Counterparty(tenant_id="tenant-b", name="B Holder",
                                   type="customer", gstin=GSTIN_A,
                                   status="active"))
        db.commit()
        assert db.query(models.Counterparty).filter_by(
            gstin=GSTIN_A).count() == 2


def test_branches(bizdb):
    client = bizdb["client"]
    party = _party(client, ADMIN, "Branched Co", gstin=GSTIN_A)
    first = client.post(f"/api/v1/counterparties/{party['id']}/branches",
                        headers=ADMIN, json={
                            "name": "Karnataka unit", "gstin": GSTIN_B,
                            "billing_address": "Bengaluru"})
    assert first.status_code == 201, first.text
    same_state = client.post(
        f"/api/v1/counterparties/{party['id']}/branches", headers=ADMIN,
        json={"name": "Mumbai unit", "gstin": GSTIN_A})
    assert same_state.status_code == 201  # HQ GSTIN reuse is legitimate
    bad = client.post(f"/api/v1/counterparties/{party['id']}/branches",
                      headers=ADMIN,
                      json={"name": "Bad unit", "gstin": "bogus"})
    assert bad.status_code == 422
    dup = client.post(f"/api/v1/counterparties/{party['id']}/branches",
                      headers=ADMIN, json={"name": "Karnataka unit"})
    assert dup.status_code == 409
    assert client.delete(f"/api/v1/counterparties/branches/{first.json()['id']}",
                         headers=ADMIN).status_code == 200
    fetched = client.get(f"/api/v1/counterparties/{party['id']}",
                         headers=ADMIN).json()
    assert [branch["name"] for branch in fetched["branches"]] == ["Mumbai unit"]


def test_external_ids(bizdb):
    client = bizdb["client"]
    one = _party(client, ADMIN, "Tally Shop")
    two = _party(client, ADMIN, "Other Shop")
    added = client.post(f"/api/v1/counterparties/{one['id']}/external-ids",
                        headers=ADMIN, json={
                            "system": "tally", "external_id": "ACME-001"})
    assert added.status_code == 201, added.text
    clash = client.post(f"/api/v1/counterparties/{two['id']}/external-ids",
                        headers=ADMIN, json={
                            "system": "tally", "external_id": "ACME-001"})
    assert clash.status_code == 409
    bad_system = client.post(
        f"/api/v1/counterparties/{one['id']}/external-ids", headers=ADMIN,
        json={"system": "Tally ERP!", "external_id": "X"})
    assert bad_system.status_code == 422
    assert client.delete(
        f"/api/v1/counterparties/external-ids/{added.json()['id']}",
        headers=ADMIN).status_code == 200


def test_duplicate_suggestions_are_explainable(bizdb):
    client = bizdb["client"]
    anchor = _party(client, ADMIN, "Apex Traders", gstin=GSTIN_A,
                    email="apex@example.in", phone="+91-9820012345")
    fuzzy = _party(client, ADMIN, "Apex Trader", gstin=GSTIN_B,
                   email="apex@example.in", phone="9820012345")
    unrelated = _party(client, ADMIN, "Zebra Foods", gstin="07XYZAB1234C1Z8")
    found = client.get(f"/api/v1/counterparties/{anchor['id']}/duplicates",
                       headers=ADMIN).json()
    names = [item["name"] for item in found]
    assert fuzzy["name"] in names
    fuzzy_row = next(item for item in found
                     if item["counterparty_id"] == fuzzy["id"])
    assert "same email" in fuzzy_row["reasons"]
    assert "same phone" in fuzzy_row["reasons"]
    assert any("name similarity" in reason
               for reason in fuzzy_row["reasons"])
    assert fuzzy_row["score"] > 0
    assert unrelated["name"] not in names


def test_merge_preview_and_confirm(bizdb):
    client = bizdb["client"]
    loser = _party(client, ADMIN, "Old Name Traders")
    winner = _party(client, ADMIN, "New Name Traders")
    invoice_id = _invoice(bizdb["factory"], "INV-B1", "Old Name Traders")
    with bizdb["factory"]() as db:
        db.get(models.Invoice, invoice_id).counterparty_id = loser["id"]
        db.commit()
    client.post(f"/api/v1/counterparties/{loser['id']}/branches",
                headers=ADMIN, json={"name": "Unit"})
    client.post(f"/api/v1/counterparties/{loser['id']}/external-ids",
                headers=ADMIN,
                json={"system": "tally", "external_id": "OLD-1"})
    preview = client.post(f"/api/v1/counterparties/{loser['id']}/merge-preview",
                          headers=ADMIN,
                          json={"winner_id": winner["id"],
                                "reason": "preview"})
    assert preview.status_code == 200, preview.text
    assert [row["invoice_number"] for row in
            preview.json()["invoices"]] == ["INV-B1"]
    done = client.post(f"/api/v1/counterparties/{loser['id']}/merge",
                       headers=ADMIN,
                       json={"winner_id": winner["id"],
                             "reason": "same business, renamed"})
    assert done.status_code == 200, done.text
    assert done.json() == {"loser_id": loser["id"], "winner_id": winner["id"],
                           "moved_invoices": 1, "invoice_ids": [invoice_id]}
    with bizdb["factory"]() as db:
        invoice = db.get(models.Invoice, invoice_id)
        assert invoice.counterparty_id == winner["id"]
        assert invoice.counterparty_name == "Old Name Traders"
        assert db.get(models.Counterparty, loser["id"]).status == "merged"
        assert db.get(models.Counterparty,
                      loser["id"]).merged_into_id == winner["id"]
        merge = db.query(models.CounterpartyMerge).one()
        assert merge.reason == "same business, renamed"
        assert merge.moved_invoices == 1
        assert db.query(models.CounterpartyBranch).filter_by(
            counterparty_id=winner["id"]).count() == 1
        assert db.query(models.CounterpartyExternalId).filter_by(
            counterparty_id=winner["id"]).count() == 1
    locked = client.patch(f"/api/v1/counterparties/{loser['id']}",
                          headers=ADMIN, json={"phone": "1"})
    assert locked.status_code == 409


def test_merge_guards(bizdb):
    client = bizdb["client"]
    editor = bizdb["editor"]
    loser = _party(client, ADMIN, "Merge Loser")
    winner = _party(client, ADMIN, "Merge Winner")
    with bizdb["factory"]() as db:
        foreign = models.Counterparty(tenant_id="tenant-b", name="Foreign",
                                      type="customer", status="active")
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    assert client.post(f"/api/v1/counterparties/{loser['id']}/merge",
                       headers=ADMIN,
                       json={"winner_id": foreign_id,
                             "reason": "cross tenant attempt"}).status_code == 404
    assert client.post(f"/api/v1/counterparties/{loser['id']}/merge",
                       headers=ADMIN,
                       json={"winner_id": loser["id"],
                             "reason": "self merge attempt"}).status_code == 409
    assert client.post(f"/api/v1/counterparties/{loser['id']}/merge",
                       headers=editor,
                       json={"winner_id": winner["id"],
                             "reason": "editor attempt"}).status_code == 403
    merged_once = client.post(f"/api/v1/counterparties/{loser['id']}/merge",
                                headers=ADMIN,
                                json={"winner_id": winner["id"],
                                      "reason": "first merge"})
    assert merged_once.status_code == 200, merged_once.text
    again = client.post(f"/api/v1/counterparties/{loser['id']}/merge",
                        headers=ADMIN,
                        json={"winner_id": winner["id"],
                              "reason": "merge into merged attempt"})
    assert again.status_code == 409


def test_bootstrap_links_and_is_idempotent(bizdb):
    client = bizdb["client"]
    _invoice(bizdb["factory"], "INV-B1A", "Bootstrap Buyer")
    _invoice(bizdb["factory"], "INV-B1B", "Bootstrap Buyer")
    _invoice(bizdb["factory"], "INV-B1C", "Second Buyer")
    _invoice(bizdb["factory"], "BILL-B1", "Supply House", invoice_type="AP")
    first = client.post("/api/v1/counterparties/bootstrap", headers=ADMIN,
                        json={"invoice_type": "AR"})
    assert first.json() == {"created": 2, "linked": 3}
    second = client.post("/api/v1/counterparties/bootstrap", headers=ADMIN,
                         json={"invoice_type": "AR"})
    assert second.json() == {"created": 0, "linked": 0}
    with bizdb["factory"]() as db:
        assert db.query(models.Counterparty).filter_by(
            tenant_id="local", name="Bootstrap Buyer",
            type="customer").count() == 1
        assert db.query(models.Invoice).filter_by(
            invoice_number="BILL-B1").one().counterparty_id is None
    vendors = client.post("/api/v1/counterparties/bootstrap", headers=ADMIN,
                          json={"invoice_type": "AP"})
    assert vendors.json() == {"created": 1, "linked": 1}


def test_import_links_party(bizdb):
    client = bizdb["client"]
    party = _party(client, ADMIN, "Import Buyer")
    with bizdb["factory"]() as db:
        result = confirm_import(
            db, "local", "b1-test",
            [{"external_id": "EXT-B1", "invoice_number": "INV-IMP",
              "customer_name": "Import Buyer", "issue_date": "2026-01-01",
              "due_date": "2026-02-01", "amount": "250.00"}],
            source_system="generic_csv")
        db.commit()
    assert result["imported"] == 1
    with bizdb["factory"]() as db:
        invoice = db.query(models.Invoice).filter_by(
            invoice_number="INV-IMP").one()
        assert invoice.counterparty_id == party["id"]


def test_case_view_shows_counterparty(bizdb):
    client = bizdb["client"]
    party = _party(client, ADMIN, "View Buyer", gstin=GSTIN_A)
    invoice_id = _invoice(bizdb["factory"], "INV-B1V", "View Buyer")
    with bizdb["factory"]() as db:
        db.get(models.Invoice, invoice_id).counterparty_id = party["id"]
        db.commit()
    case = client.get(f"/api/v1/cases/{invoice_id}", headers=ADMIN).json()
    assert case["counterparty"] == {"id": party["id"], "name": "View Buyer",
                                    "display_name": "View Buyer",
                                    "gstin": GSTIN_A, "status": "active"}


def test_cross_tenant_isolation(bizdb):
    client = bizdb["client"]
    with bizdb["factory"]() as db:
        foreign = models.Counterparty(tenant_id="tenant-b", name="Foreign",
                                      type="customer", status="active")
        db.add(foreign)
        db.commit()
        foreign_id = foreign.id
    assert client.get(f"/api/v1/counterparties/{foreign_id}",
                      headers=ADMIN).status_code == 404
    listed = client.get("/api/v1/counterparties", headers=ADMIN).json()
    assert all("Foreign" != row["name"] for row in listed)
