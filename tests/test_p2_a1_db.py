"""P2 A1: versioned migrations, transaction/constraint safety, backup/restore drill.

All databases are isolated tmp files; the live app and its database are untouched.
PostgreSQL has no instance in this environment, so only the SQLite path executes;
the PostgreSQL migration code is reviewed but NOT verified (see docs/ops-backup.md).
"""
import json
import sqlite3
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.database.migrations import REVISIONS, REVISION, migrate, status
from app.main import app
from scripts.db_backup import backup_sqlite, restore_sqlite, verify_backup


def _engine_for(path):
    return create_engine("sqlite:///" + path.as_posix(),
                         connect_args={"check_same_thread": False})


@pytest.fixture()
def migrated_db(monkeypatch, tmp_path):
    """Fresh file database upgraded through the real init_db path."""
    db_path = tmp_path / "a1-test.db"
    engine = _engine_for(db_path)
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    db_manager.init_db()
    yield db_path, engine
    engine.dispose()


def _invoice(**overrides):
    values = {"tenant_id": "local", "invoice_number": "A1-1", "invoice_type": "AR",
              "counterparty_name": "A1 Party", "issue_date": date(2026, 1, 1),
              "due_date": date(2026, 2, 1), "amount": Decimal("100.00"),
              "total_amount": Decimal("100.00")}
    values.update(overrides)
    return models.Invoice(**values)


def _entry(invoice_id, **overrides):
    values = {"tenant_id": "local", "invoice_id": invoice_id, "kind": "payment",
              "amount_cents": 1000, "currency": "INR", "source": "a1",
              "reference": "r1", "actor": "a1-test"}
    values.update(overrides)
    return models.ReceivableEntry(**values)


def test_revision_chain_invariant():
    assert REVISIONS, "revision list must not be empty"
    assert REVISION == REVISIONS[-1]
    assert len(set(REVISIONS)) == len(REVISIONS)


def test_fresh_migrate_records_everything(migrated_db):
    db_path, _ = migrated_db
    connection = sqlite3.connect(str(db_path))
    try:
        applied = [row[0] for row in connection.execute(
            "SELECT revision FROM schema_revisions ORDER BY revision")]
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        connection.close()
    assert applied == sorted(REVISIONS)
    for table in ("supervisor_tasks", "competing_explanations", "clarification_tasks",
                  "unit_rules", "allocation_proposals", "allocation_legs",
                  "payer_aliases", "promises_to_pay"):
        assert table in tables


def test_migrate_is_idempotent(migrated_db):
    _, engine = migrated_db
    migrate(engine, db_manager.Base.metadata)
    report = status(engine)
    assert report["dialect"] == "sqlite"
    assert report["current_revision"] == REVISION
    assert report["applied"] == REVISIONS
    assert report["pending"] == []
    assert report["unknown"] == []


def test_status_on_fresh_file(tmp_path):
    db_path = tmp_path / "fresh.db"
    sqlite3.connect(str(db_path)).close()
    engine = _engine_for(db_path)
    try:
        report = status(engine)
    finally:
        engine.dispose()
    assert report["applied"] == []
    assert report["pending"] == REVISIONS


LEGACY_INVOICES_DDL = (
    "CREATE TABLE invoices (id INTEGER PRIMARY KEY, invoice_number TEXT, "
    "invoice_type TEXT, counterparty_name TEXT, counterparty_email TEXT, "
    "counterparty_tax_id TEXT, issue_date DATE, due_date DATE, received_date DATE, "
    "amount REAL, currency TEXT, tax_amount REAL, total_amount REAL, "
    "description TEXT, po_number TEXT, status TEXT, source TEXT, "
    "source_filename TEXT, source_path TEXT, ocr_confidence FLOAT, "
    "ocr_raw_text TEXT, fraud_score FLOAT, is_duplicate INTEGER, "
    "duplicate_of_id INTEGER, requires_human_review INTEGER, "
    "human_review_notes TEXT, afis_transaction_id INTEGER, axis_classified INTEGER, "
    "created_at DATETIME, updated_at DATETIME)")


def _legacy_row(number, total):
    return (1, number, "AR", "Old Party", "old@example.in", "GSTINOLD", "2026-01-01",
            "2026-02-01", None, 1000.5, "INR", 180.0, total, "legacy desc", "PO-1",
            "pending", "manual", "old.pdf", "/tmp/old.pdf", 0.9, "raw", 0.0, 0, None,
            0, None, None, 0, "2026-01-01 00:00:00", "2026-01-01 00:00:00")


def _write_legacy_db(db_path, number, total):
    connection = sqlite3.connect(str(db_path))
    connection.execute(LEGACY_INVOICES_DDL)
    connection.execute("INSERT INTO invoices VALUES (%s)" % ",".join("?" * 30),
                       _legacy_row(number, total))
    connection.commit()
    connection.close()


def _point_at(monkeypatch, db_path):
    engine = _engine_for(db_path)
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    return engine


def test_legacy_sqlite_upgrade_converts_money_and_backfills_tenant(monkeypatch, tmp_path):
    """A realistically old ORM schema (pre-tenant, REAL money) upgrades fully."""
    db_path = tmp_path / "legacy.db"
    _write_legacy_db(db_path, "OLD-1", 1000.5)
    engine = _point_at(monkeypatch, db_path)
    db_manager.init_db()
    try:
        with db_manager.SessionLocal() as db:
            invoice = db.get(models.Invoice, 1)
            assert invoice.tenant_id == "local"
            assert invoice.total_amount == Decimal("1000.50")
            assert invoice.tax_amount == Decimal("180.00")
        raw = sqlite3.connect(str(db_path))
        try:
            value, typeof = raw.execute(
                "SELECT total_amount, typeof(total_amount) FROM invoices WHERE id=1").fetchone()
        finally:
            raw.close()
        assert (value, typeof) == ("1000.50", "text")
        assert status(engine)["pending"] == []
    finally:
        engine.dispose()


def test_invalid_legacy_money_aborts_without_losing_rows(monkeypatch, tmp_path):
    db_path = tmp_path / "badmoney.db"
    _write_legacy_db(db_path, "BAD-1", "not-a-number")
    engine = _point_at(monkeypatch, db_path)
    with pytest.raises(ValueError, match="[Ii]nvalid.*(money|amount)"):
        db_manager.init_db()
    raw = sqlite3.connect(str(db_path))
    try:
        row = raw.execute("SELECT invoice_number, total_amount FROM invoices").fetchone()
        assert row == ("BAD-1", "not-a-number")
        raw.execute("UPDATE invoices SET total_amount=10.0 WHERE id=1")
        raw.commit()
    finally:
        raw.close()
    db_manager.init_db()  # retry after repair succeeds
    try:
        with db_manager.SessionLocal() as db:
            assert db.get(models.Invoice, 1).total_amount == Decimal("10.00")
        assert status(engine)["pending"] == []
    finally:
        engine.dispose()


def test_duplicate_entry_reference_rejected(migrated_db):
    _, engine = migrated_db
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(_invoice())
        db.flush()
        invoice_id = db.query(models.Invoice).one().id
        db.add(_entry(invoice_id))
        db.flush()
        db.add(_entry(invoice_id))
        with pytest.raises(IntegrityError):
            db.flush()


def test_duplicate_reversal_link_rejected(migrated_db):
    _, engine = migrated_db
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(_invoice())
        db.flush()
        invoice_id = db.query(models.Invoice).one().id
        original = _entry(invoice_id, reference="orig")
        db.add(original)
        db.flush()
        db.add(_entry(invoice_id, kind="reversal", reference="rev1",
                      reversal_of_id=original.id))
        db.flush()
        db.add(_entry(invoice_id, kind="reversal", reference="rev2",
                      reversal_of_id=original.id))
        with pytest.raises(IntegrityError):
            db.flush()


def test_entry_for_missing_invoice_rejected(migrated_db):
    _, engine = migrated_db
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(_entry(999999))
        with pytest.raises(IntegrityError):
            db.flush()


def test_backup_restore_drill_roundtrips_data_and_revisions(migrated_db, tmp_path):
    db_path, engine = migrated_db
    factory = sessionmaker(bind=engine)
    with factory() as db:
        invoice = _invoice()
        db.add(invoice)
        db.flush()
        db.add(_entry(invoice.id))
        db.commit()
    backup_path = tmp_path / "a1-backup.db"
    report = backup_sqlite(db_path, backup_path)
    assert report["integrity"] == "ok"
    assert sorted(report["revisions"]) == sorted(REVISIONS)
    assert report["counts"]["invoices"] == 1
    assert report["counts"]["receivable_entries"] == 1
    restored_path = tmp_path / "a1-restored.db"
    restored = restore_sqlite(backup_path, restored_path)
    assert restored["revisions"] == report["revisions"]
    assert restored["counts"] == report["counts"]
    check_engine = _engine_for(restored_path)
    try:
        check_factory = sessionmaker(bind=check_engine)
        with check_factory() as db:
            assert db.query(models.Invoice).count() == 1
            assert db.query(models.ReceivableEntry).count() == 1
    finally:
        check_engine.dispose()
    with pytest.raises(FileExistsError):
        backup_sqlite(db_path, backup_path)
    with pytest.raises(FileExistsError):
        restore_sqlite(backup_path, restored_path)


def test_migration_status_endpoint_requires_admin(monkeypatch, tmp_path):
    db_path = tmp_path / "a1-api.db"
    engine = _engine_for(db_path)
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "a1-admin-secret")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", json.dumps(
        [{"key": "a1-viewer-secret", "actor": "viewer", "tenant_id": "local",
          "role": "viewer"}]))
    db_manager.init_db()
    try:
        client = TestClient(app)
        admin = client.get("/api/v1/system/migrations",
                           headers={"X-RECOVERFLOW-API-KEY": "a1-admin-secret"})
        assert admin.status_code == 200, admin.text
        body = admin.json()
        assert body["applied"] == REVISIONS
        assert body["pending"] == []
        assert body["dialect"] == "sqlite"
        assert "url" not in body and "URL" not in body
        viewer = client.get("/api/v1/system/migrations",
                            headers={"X-RECOVERFLOW-API-KEY": "a1-viewer-secret"})
        assert viewer.status_code == 403
        anonymous = client.get("/api/v1/system/migrations")
        assert anonymous.status_code == 401
    finally:
        engine.dispose()
