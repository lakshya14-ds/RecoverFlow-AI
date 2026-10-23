"""
RecoverFlow - Receivables and Collections
"""
import sqlite3
import logging
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine, event, MetaData
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.engine import Engine
from app.config import settings

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection: sqlite3.Connection, connection_record: object) -> None:
    """Configures SQLite to use WAL mode for better concurrency."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

engine = create_engine(
    f"sqlite:///{settings.APEX_DB_PATH}",
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db() -> None:
    """Initialize the RecoverFlow database from schema.sql when needed."""
    db_path = Path(settings.APEX_DB_PATH)
    if not db_path.exists():
        logging.info("Initializing RecoverFlow database from schema.sql...")
        schema_path = Path(__file__).parent / "schema.sql"
        if schema_path.exists():
            with sqlite3.connect(db_path) as conn:
                with open(schema_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
            logging.info("RecoverFlow database created successfully.")
        else:
            logging.error(f"schema.sql not found at {schema_path}")
    # Keep existing installations usable while adding new ORM-managed tables.
    from app.database import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Add tenant scoping to databases created before this release.
    with sqlite3.connect(db_path) as conn:
        new_columns = {
            "invoices": {
                "face_amount_cents": "INTEGER",
                "source_system": "TEXT",
                "source_record_id": "TEXT",
                "contact_suppressed": "INTEGER NOT NULL DEFAULT 0",
                "contact_opt_out": "INTEGER NOT NULL DEFAULT 0",
                "dispute_open": "INTEGER NOT NULL DEFAULT 0",
            },
            "dunning_campaigns": {
                "approved_by": "TEXT",
                "approved_at": "DATETIME",
                "balance_cents_at_draft": "INTEGER",
                "contacted_at": "DATETIME",
                "contact_channel": "TEXT",
                "contact_reference": "TEXT",
            },
            "processing_jobs": {
                "invoice_type": "TEXT NOT NULL DEFAULT 'AP'",
                "attempts": "INTEGER NOT NULL DEFAULT 0",
                "locked_until": "DATETIME",
            },
        }
        for table, additions in new_columns.items():
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, definition in additions.items():
                if columns and name not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        for table in ("invoices", "reconciliations", "dunning_campaigns", "fraud_alerts",
                      "dso_snapshots", "counterparties", "processing_jobs", "audit_events",
                      "receivable_entries", "customer_messages"):
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if columns and "tenant_id" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'local'")
        job_columns = {row[1] for row in conn.execute("PRAGMA table_info(processing_jobs)")}
        if job_columns and "actor" not in job_columns:
            conn.execute("ALTER TABLE processing_jobs ADD COLUMN actor TEXT NOT NULL DEFAULT 'system'")
        # Older databases had global uniqueness for DSO dates and tax IDs.
        # Rebuild those two tables so separate organizations can use the same values.
        for table, single_column, model in (
            ("dso_snapshots", "snapshot_date", models.DSOSnapshot),
            ("counterparties", "tax_id", models.Counterparty),
        ):
            old_unique = False
            for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
                if index[2]:
                    indexed = [row[2] for row in conn.execute(
                        f"PRAGMA index_info({index[1]})").fetchall()]
                    old_unique = old_unique or indexed == [single_column]
            if old_unique:
                replacement = model.__table__.to_metadata(MetaData(), name=f"{table}_replacement")
                conn.execute(str(CreateTable(replacement).compile(engine)))
                columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
                names = ", ".join(columns)
                conn.execute(f"INSERT INTO {table}_replacement ({names}) SELECT {names} FROM {table}")
                conn.execute(f"DROP TABLE {table}")
                conn.execute(f"ALTER TABLE {table}_replacement RENAME TO {table}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_counterparties_type ON counterparties(type, fraud_flag)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_invoice_external_source ON invoices(tenant_id, source_system, source_record_id) WHERE source_record_id IS NOT NULL")
        for table in ("invoices", "reconciliations", "dunning_campaigns", "fraud_alerts",
                      "dso_snapshots", "counterparties", "processing_jobs", "audit_events",
                      "receivable_entries", "customer_messages"):
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant ON {table}(tenant_id)")

def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
