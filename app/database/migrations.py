"""Versioned, transactional foundation upgrade for SQLite and PostgreSQL.

Run during a maintenance window, with a backup and only one starting process.
SQLite rebuilds preserve the original constraints, indexes and triggers.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn
from app.database.money import Money

REVISION = "20261113_privacy_v18"
REVISIONS = ["20261027_foundations_v1", "20261028_trust_states_v2",
             "20261029_supervisor_v3", "20261030_investigation_v4",
             "20261031_allocation_v5", "20261101_tenancy_v6",
             "20261102_auth_v7", "20261103_team_v8",
             "20261104_identity_v9", "20261105_documents_v10",
             "20261106_installments_v11", "20261107_portal_v12",
             "20261108_docstore_v13", "20261109_import_runs_v14",
             "20261110_payments_v15", "20261111_comms_v16",
             "20261112_workers_v17", REVISION]
ADDITIONS = {
    "invoices": {"investigation_hold": "BOOLEAN NOT NULL DEFAULT false", "investigation_reason": "TEXT", "investigation_decision_hash": "VARCHAR(64)", "counterparty_id": "INTEGER REFERENCES counterparties(id)",
        "cgst_cents": "INTEGER DEFAULT 0", "sgst_cents": "INTEGER DEFAULT 0", "igst_cents": "INTEGER DEFAULT 0",
        "freight_cents": "INTEGER DEFAULT 0", "roundoff_cents": "INTEGER DEFAULT 0"},
    "receivable_entries": {"allocation": "VARCHAR NOT NULL DEFAULT 'legacy'",
        "disputed_delta_cents": "INTEGER NOT NULL DEFAULT 0", "reversal_of_id": "INTEGER REFERENCES receivable_entries(id)"},
    "negotiation_turns": {"context_hash": "VARCHAR(64)", "offer_json": "TEXT"},
    "counterparties": {"gstin": "VARCHAR(15)", "legal_name": "VARCHAR",
        "display_name": "VARCHAR", "billing_address": "TEXT", "shipping_address": "TEXT",
        "status": "VARCHAR NOT NULL DEFAULT 'active'",
        "merged_into_id": "INTEGER REFERENCES counterparties(id)"},
    "case_evidence": {"trust_state": "VARCHAR NOT NULL DEFAULT 'alleged'",
        "decided_by": "VARCHAR", "decided_at": "TIMESTAMP", "decision_reason": "TEXT",
        "currency": "VARCHAR"},
    "customer_messages": {"source": "VARCHAR NOT NULL DEFAULT 'staff'"},
    "intake_uploads": {"sha256": "VARCHAR(64)"},
    "provider_events": {"mode": "VARCHAR NOT NULL DEFAULT 'test'"},
    "payment_links": {"mode": "VARCHAR NOT NULL DEFAULT 'test'",
                      "last_error": "TEXT"},
    "outbound_messages": {"language": "VARCHAR NOT NULL DEFAULT 'en'",
                          "template_id": "INTEGER REFERENCES message_templates(id)",
                          "delivered_at": "TIMESTAMP", "failure_reason": "TEXT",
                          "held_until": "TIMESTAMP"},
    "intake_uploads": {"claimed_by": "VARCHAR", "claimed_at": "TIMESTAMP",
                       "heartbeat_at": "TIMESTAMP",
                       "lease_expires_at": "TIMESTAMP",
                       "not_before": "TIMESTAMP"},
    "supervisor_tasks": {"claimed_by": "VARCHAR", "claimed_at": "TIMESTAMP",
                         "heartbeat_at": "TIMESTAMP",
                         "lease_expires_at": "TIMESTAMP",
                         "not_before": "TIMESTAMP", "elapsed_ms": "INTEGER"},
}


def _applied(conn, revision):
    return conn.execute(text("SELECT revision FROM schema_revisions WHERE revision=:r"),
                        {"r": revision}).first() is not None


def _sqlite_money(engine, metadata):
    raw = engine.raw_connection()
    try:
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute("BEGIN IMMEDIATE")
        for table in metadata.sorted_tables:
            money = {c.name for c in table.columns if isinstance(c.type, Money)}
            columns = raw.execute(f'PRAGMA table_info("{table.name}")').fetchall()
            if not any(c[1] in money and "CHAR" not in c[2].upper() and "TEXT" not in c[2].upper() for c in columns):
                continue
            original = raw.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table.name,)).fetchone()[0]
            replacement = table.name + "_money_upgrade"
            ddl = re.sub(r'CREATE TABLE\s+(?:"[^\"]+"|\w+)', f'CREATE TABLE "{replacement}"', original, count=1, flags=re.I)
            for name in money:
                ddl = re.sub(rf'(?<!\w)("?{name}"?)\s+(?:FLOAT|REAL|DOUBLE(?: PRECISION)?|NUMERIC(?:\([^)]*\))?)',
                             r'\1 VARCHAR(24)', ddl, flags=re.I)
            artifacts = raw.execute("SELECT sql FROM sqlite_master WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL", (table.name,)).fetchall()
            raw.execute(ddl)
            names = [c[1] for c in columns]
            select = raw.execute(f'SELECT * FROM "{table.name}"')
            quoted = ','.join('"' + n + '"' for n in names)
            insert = f'INSERT INTO "{replacement}" ({quoted}) VALUES ({",".join("?" for _ in names)})'
            while rows := select.fetchmany(500):
                converted = []
                for row in rows:
                    values = list(row)
                    for index, name in enumerate(names):
                        if name in money and values[index] is not None:
                            try:
                                value = Decimal(str(values[index]))
                            except InvalidOperation:
                                raise ValueError(f"Invalid legacy money in {table.name}.{name}")
                            if not value.is_finite():
                                raise ValueError(f"Invalid legacy money in {table.name}.{name}")
                            values[index] = format(value.quantize(Decimal(".01"), rounding=ROUND_HALF_UP), ".2f")
                    converted.append(values)
                raw.executemany(insert, converted)
            raw.execute(f'DROP TABLE "{table.name}"')
            raw.execute(f'ALTER TABLE "{replacement}" RENAME TO "{table.name}"')
            for (ddl,) in artifacts:
                raw.execute(ddl)
        if raw.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Migration failed foreign-key validation")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.close()


def backfill_evidence_trust(conn):
    """Conservative trust backfill: old verified flags never become accepted.

    verified=True  -> verified (source was marked, not proof for money movement)
    verified=False -> alleged  (unchecked claim; model/customer output stays here)
    Staff must explicitly accept a claim (with actor, time, reason) before any
    financial reliance, and ledger postings always use their own authorized path.
    """
    conn.execute(text("UPDATE case_evidence SET trust_state='verified' "
                      "WHERE trust_state='alleged' AND verified=1"))
    # Rows already alleged stay alleged; anything unexpected is left untouched.


def migrate(engine, metadata):
    dialect = engine.dialect.name
    if dialect not in ("sqlite", "postgresql"):
        raise ValueError("Supported databases are SQLite and PostgreSQL")
    with engine.begin() as conn:
        if dialect == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(72635027)"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_revisions (revision VARCHAR(80) PRIMARY KEY)"))
        if _applied(conn, REVISION):
            return
        for table in ("supervisor_tasks", "competing_explanations",
                      "clarification_tasks", "unit_rules", "allocation_proposals",
                      "allocation_legs", "payer_aliases", "promises_to_pay",
                      "tenant_secrets", "tenant_settings", "login_attempts",
                      "user_recovery_tokens", "case_assignments", "staff_tasks",
                      "staff_notes", "case_escalations",
                      "counterparty_branches", "counterparty_external_ids",
                      "counterparty_merges", "invoice_line_items",
                      "credit_debit_notes", "supporting_documents",
                      "installment_schedules", "installment_legs",
                      "installment_applications", "portal_tokens",
                      "portal_attempts", "stored_documents",
                      "document_access_log", "import_runs",
                      "import_conflicts", "payment_discrepancies",
                      "settlement_lines", "message_templates",
                      "comms_preferences", "privacy_requests"):
            if table in metadata.tables:
                metadata.tables[table].create(bind=conn, checkfirst=True)
        for table, additions in ADDITIONS.items():
            columns = {c["name"] for c in inspect(conn).get_columns(table)}
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))
        if dialect == "postgresql":
            # Upgrade known pre-release schemas using the ORM's current column types.
            for table in metadata.sorted_tables:
                actual = {c["name"]: c for c in inspect(conn).get_columns(table.name)}
                for col in table.columns:
                    if col.name not in actual:
                        if not col.nullable and col.default is None:
                            raise ValueError(f"Missing required column {table.name}.{col.name}; explicit data migration required")
                        definition = str(CreateColumn(col).compile(dialect=conn.dialect))
                        if col.default is not None and col.default.is_scalar:
                            value = col.default.arg
                            literal = ("true" if value is True else "false" if value is False else
                                       str(value) if isinstance(value, (int, float)) else "'" + str(value).replace("'", "''") + "'")
                            definition += " DEFAULT " + literal
                        conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {definition}'))
                    elif isinstance(col.type, Money):
                        conn.execute(text(f'ALTER TABLE "{table.name}" ALTER COLUMN "{col.name}" TYPE NUMERIC(20,2) USING ROUND("{col.name}"::numeric, 2)'))
            for table, column in (("dso_snapshots", "snapshot_date"), ("counterparties", "tax_id")):
                for constraint in inspect(conn).get_unique_constraints(table):
                    if constraint["column_names"] == [column]:
                        name = conn.dialect.identifier_preparer.quote(constraint["name"])
                        conn.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT {name}'))
                conn.execute(text(f'CREATE UNIQUE INDEX IF NOT EXISTS "uq_{table}_tenant_value" ON "{table}" (tenant_id, "{column}")'))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_external_source ON invoices(tenant_id, source_system, source_record_id) WHERE source_record_id IS NOT NULL"))
        # Reconnect legacy reversals to their originals before cash/credit reporting.
        rows = conn.execute(text("SELECT id, tenant_id, invoice_id, reference FROM receivable_entries WHERE kind='reversal' AND reversal_of_id IS NULL AND source='reversal'")).mappings().all()
        for row in rows:
            if not str(row["reference"]).isdigit():
                continue
            conn.execute(text("UPDATE receivable_entries SET reversal_of_id=:original WHERE id=:id AND EXISTS (SELECT 1 FROM receivable_entries e WHERE e.id=:original AND e.tenant_id=:tenant AND e.invoice_id=:invoice AND e.kind IN ('payment','credit'))"),
                {"original": int(row["reference"]), "id": row["id"], "tenant": row["tenant_id"], "invoice": row["invoice_id"]})
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_entry_reversal ON receivable_entries(tenant_id, reversal_of_id) WHERE reversal_of_id IS NOT NULL"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_counterparty_tenant_gstin ON counterparties(tenant_id, gstin) WHERE gstin IS NOT NULL"))
    if dialect == "sqlite":
        _sqlite_money(engine, metadata)
    # Existing inconsistent disputes are NOT silently reduced. Flag them for repair.
    with engine.begin() as conn:
        conn.execute(text("UPDATE invoices SET investigation_hold=true, investigation_reason='Legacy dispute allocation requires staff reconciliation' WHERE disputed_cents > COALESCE(face_amount_cents, CAST(ROUND(CAST(total_amount AS NUMERIC)*100) AS BIGINT)) + COALESCE((SELECT SUM(amount_cents) FROM receivable_entries e WHERE e.invoice_id=invoices.id AND e.tenant_id=invoices.tenant_id),0)"))
        backfill_evidence_trust(conn)
        for revision in REVISIONS:
            if not _applied(conn, revision):
                conn.execute(text("INSERT INTO schema_revisions(revision) VALUES (:r)"), {"r": revision})


def status(engine):
    """Read-only migration state. Safe on fresh databases without a revisions table."""
    dialect = engine.dialect.name
    with engine.connect() as conn:
        if not inspect(conn).has_table("schema_revisions"):
            return {"dialect": dialect, "current_revision": REVISION,
                    "applied": [], "pending": list(REVISIONS), "unknown": []}
        rows = conn.execute(text("SELECT revision FROM schema_revisions")).all()
    applied_set = {row[0] for row in rows}
    return {"dialect": dialect, "current_revision": REVISION,
            "applied": [r for r in REVISIONS if r in applied_set],
            "pending": [r for r in REVISIONS if r not in applied_set],
            "unknown": sorted(applied_set - set(REVISIONS))}
