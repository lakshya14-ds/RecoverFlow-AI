"""P2 D1: accounting import runs — idempotency, conflict queue, provenance,
cursor, and reconciliation reports. Generic profile only; no vendor claims."""
import json
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app

ADMIN = {"X-RECOVERFLOW-API-KEY": "d1-admin"}
EDITOR = {"X-RECOVERFLOW-API-KEY": "d1-editor"}


def _row(external_id, number="INV-D1-1", customer="D1 Party",
         amount="1000.00", due="2026-02-01", currency="INR"):
    return {"external_id": external_id, "invoice_number": number,
            "customer_name": customer, "issue_date": "2026-01-01",
            "due_date": due, "amount": amount, "currency": currency}


@pytest.fixture()
def impdb(monkeypatch, tmp_path):
    db_path = tmp_path / "d1.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "d1-admin")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "d1-editor", "actor": "ed@example.in", "tenant_id": "local",
          "role": "editor"}]))
    db_manager.init_db()
    factory = sessionmaker(bind=engine)
    yield {"client": TestClient(app), "factory": factory, "engine": engine}
    engine.dispose()


def _start(client, rows, key="k1", system="pilot_books", headers=EDITOR):
    res = client.post("/api/v1/imports/runs", headers=headers,
                      json={"source_system": system, "rows": rows,
                            "idempotency_key": key})
    assert res.status_code == 201, res.text
    return res.json()


def test_happy_path_reconciles(impdb):
    client = impdb["client"]
    run = _start(client, [_row("e1"), _row("e2", number="INV-D1-2",
                                            amount="250.50")])
    assert run["status"] == "previewed"
    assert run["duplicate"] is False
    assert len(run["source_hash"]) == 64
    confirmed = client.post(f"/api/v1/imports/runs/{run['id']}/confirm",
                            headers=EDITOR)
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["status"] == "confirmed"
    assert (body["imported"], body["skipped"], body["conflicted"]) == (2, 0, 0)
    totals = body["report"]["totals"]["INR"]
    assert totals == {"source": 125050, "imported": 125050, "skipped": 0,
                      "conflicted": 0, "invalid": 0}
    assert body["cursor"]["external_ids"] == ["e1", "e2"]
    with impdb["factory"]() as db:
        invoices = db.query(models.Invoice).filter_by(
            tenant_id="local", source_system="pilot_books").all()
        assert len(invoices) == 2
        assert db.query(models.AuditEvent).filter_by(
            action="import_run_confirmed").count() == 1


def test_idempotent_replay(impdb):
    client = impdb["client"]
    rows = [_row("e1")]
    first = _start(client, rows, key="replay-me")
    client.post(f"/api/v1/imports/runs/{first['id']}/confirm", headers=EDITOR)
    second = _start(client, rows, key="replay-me")
    assert second["id"] == first["id"]
    assert second["duplicate"] is True
    assert second["status"] == "confirmed"
    with impdb["factory"]() as db:
        assert db.query(models.Invoice).count() == 1
        assert db.query(models.ImportRun).count() == 1


def test_key_reuse_with_different_payload(impdb):
    client = impdb["client"]
    _start(client, [_row("e1")], key="clash")
    res = client.post("/api/v1/imports/runs", headers=EDITOR,
                      json={"source_system": "pilot_books",
                            "rows": [_row("e2")], "idempotency_key": "clash"})
    assert res.status_code == 409
    assert "different payload" in res.json()["detail"]


def test_same_file_twice_skips(impdb):
    client = impdb["client"]
    rows = [_row("e1", amount="100.00")]
    first = _start(client, rows, key="run-a")
    client.post(f"/api/v1/imports/runs/{first['id']}/confirm", headers=EDITOR)
    second = _start(client, rows, key="run-b")
    confirmed = client.post(f"/api/v1/imports/runs/{second['id']}/confirm",
                            headers=EDITOR).json()
    assert confirmed["status"] == "confirmed"
    assert (confirmed["imported"], confirmed["skipped"]) == (0, 1)
    assert confirmed["report"]["totals"]["INR"]["skipped"] == 10000
    with impdb["factory"]() as db:
        assert db.query(models.Invoice).count() == 1


def test_conflict_queues_and_clean_row_imports(impdb):
    client = impdb["client"]
    with impdb["factory"]() as db:
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-OLD", invoice_type="AR",
            counterparty_name="D1 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("1000"),
            total_amount=Decimal("1000"), face_amount_cents=100000,
            currency="INR", source_system="pilot_books",
            source_record_id="e1"))
        db.commit()
    run = _start(client, [_row("e1", number="INV-NEW", amount="555.00"),
                          _row("e2", number="INV-D1-2", amount="10.00")])
    confirmed = client.post(f"/api/v1/imports/runs/{run['id']}/confirm",
                            headers=EDITOR).json()
    assert confirmed["status"] == "partially_confirmed"
    assert (confirmed["imported"], confirmed["conflicted"]) == (1, 1)
    assert len(confirmed["conflicts"]) == 1
    conflict = confirmed["conflicts"][0]
    assert conflict["source_record_id"] == "e1"
    assert "amount" in conflict["reason"]
    assert conflict["existing_invoice_id"] is not None
    queued = client.get("/api/v1/imports/conflicts", headers=EDITOR).json()
    assert [item["id"] for item in queued] == [conflict["id"]]
    resolved = client.post(
        f"/api/v1/imports/conflicts/{conflict['id']}/resolve",
        headers=EDITOR, json={"resolution": "keep_existing"}).json()
    assert resolved["status"] == "resolved"
    assert client.get("/api/v1/imports/conflicts",
                      headers=EDITOR).json() == []
    rerun = client.post(f"/api/v1/imports/runs/{run['id']}/confirm",
                        headers=EDITOR)
    assert rerun.status_code == 200
    assert (rerun.json()["imported"], rerun.json()["skipped"],
            rerun.json()["conflicted"]) == (0, 1, 1)
    with impdb["factory"]() as db:
        assert db.query(models.ImportConflict).count() == 1
        assert db.query(models.Invoice).filter_by(
            source_record_id="e2").count() == 1


def test_invalid_rows_block_confirm(impdb):
    client = impdb["client"]
    run = _start(client, [_row("e1", amount="not-money")])
    assert run["status"] == "invalid"
    assert run["report"]["errors"]
    res = client.post(f"/api/v1/imports/runs/{run['id']}/confirm",
                      headers=EDITOR)
    assert res.status_code == 422
    dup = _start(client, [_row("e1", amount="10.00"),
                          _row("e1", amount="20.00")], key="dup-diff")
    assert dup["status"] == "invalid"
    assert any("appears twice" in err for err in dup["report"]["errors"])


def test_identical_intra_batch_dup_dedupes(impdb):
    client = impdb["client"]
    run = _start(client, [_row("e1", amount="10.00"),
                          _row("e1", amount="10.00")])
    assert run["status"] == "previewed"
    confirmed = client.post(f"/api/v1/imports/runs/{run['id']}/confirm",
                            headers=EDITOR).json()
    assert (confirmed["imported"], confirmed["skipped"]) == (1, 1)
    with impdb["factory"]() as db:
        assert db.query(models.Invoice).count() == 1


def test_report_totals_add_up(impdb):
    client = impdb["client"]
    with impdb["factory"]() as db:
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-K", invoice_type="AR",
            counterparty_name="D1 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("100"),
            total_amount=Decimal("100"), face_amount_cents=10000,
            currency="INR", source_system="pilot_books",
            source_record_id="skip-me"))
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-K", invoice_type="AR",
            counterparty_name="D1 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("100"),
            total_amount=Decimal("100"), face_amount_cents=10000,
            currency="INR", source_system="pilot_books",
            source_record_id="clash-me"))
        db.commit()
    rows = [_row("skip-me", number="INV-K", amount="100.00"),
            _row("clash-me", number="INV-K", amount="999.00"),
            _row("new-me", number="INV-N", amount="5.00")]
    run = _start(client, rows)
    totals = client.post(f"/api/v1/imports/runs/{run['id']}/confirm",
                         headers=EDITOR).json()["report"]["totals"]["INR"]
    assert totals["source"] == (10000 + 99900 + 500)
    assert totals["imported"] == 500
    assert totals["skipped"] == 10000
    assert totals["conflicted"] == 99900
    assert (totals["imported"] + totals["skipped"] + totals["conflicted"]
            + totals["invalid"]) == totals["source"]


def test_strict_confirm_still_raises(impdb):
    client = impdb["client"]
    with impdb["factory"]() as db:
        db.add(models.Invoice(
            tenant_id="local", invoice_number="INV-K", invoice_type="AR",
            counterparty_name="D1 Party", issue_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1), amount=Decimal("100"),
            total_amount=Decimal("100"), face_amount_cents=10000,
            currency="INR", source_system="pilot_books",
            source_record_id="e1"))
        db.commit()
    res = client.post("/api/v1/imports/confirm", headers=EDITOR,
                      json={"source_system": "pilot_books",
                            "rows": [_row("e1", amount="1.00")]})
    assert res.status_code == 422
    assert "conflicting" in res.json()["detail"]


def test_cross_tenant_isolation(impdb):
    client = impdb["client"]
    run = _start(client, [_row("e1")])
    with impdb["factory"]() as db:
        db.query(models.ImportRun).filter_by(id=run["id"]).one().tenant_id = \
            "tenant-b"
        db.commit()
        run_id = run["id"]
    assert client.get(f"/api/v1/imports/runs/{run_id}",
                      headers=ADMIN).status_code == 404
    assert client.post(f"/api/v1/imports/runs/{run_id}/confirm",
                       headers=ADMIN).status_code == 404
    assert client.get("/api/v1/imports/runs", headers=ADMIN).json() == []


def test_unauthenticated_blocked(impdb):
    client = impdb["client"]
    assert client.post("/api/v1/imports/runs",
                       json={"source_system": "x",
                             "rows": [_row("e1")]}).status_code == 401


def test_unknown_profile_rejected(impdb):
    client = impdb["client"]
    res = client.post("/api/v1/imports/runs", headers=EDITOR,
                      json={"source_system": "tally_prime",
                            "profile": "tally_prime", "rows": [_row("e1")]})
    assert res.status_code == 422
    assert "Unknown import profile" in res.json()["detail"]
