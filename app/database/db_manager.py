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

db_url = settings.DATABASE_URL or f"sqlite:///{settings.APEX_DB_PATH}"
is_sqlite = db_url.startswith("sqlite")

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
    """Configures SQLite to use WAL mode for better concurrency when running SQLite."""
    if hasattr(dbapi_connection, "cursor") and type(dbapi_connection).__module__.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

if is_sqlite:
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        db_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_pre_ping=True
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db() -> None:
    """Initialize the RecoverFlow database schema and tables."""
    from app.database import models  # noqa: F401
    from app.services.auth_security import hash_password, hash_api_key

    db_path = Path(settings.APEX_DB_PATH)
    if is_sqlite and not db_path.exists():
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
    Base.metadata.create_all(bind=engine)
    # Add tenant scoping to databases created before this release.
    with sqlite3.connect(db_path) as conn:
        new_columns = {
            "invoices": {
                "face_amount_cents": "INTEGER",
                "counterparty_phone": "TEXT",
                "source_system": "TEXT",
                "source_record_id": "TEXT",
                "source_order_id": "TEXT",
                "contact_suppressed": "INTEGER NOT NULL DEFAULT 0",
                "contact_opt_out": "INTEGER NOT NULL DEFAULT 0",
                "dispute_open": "INTEGER NOT NULL DEFAULT 0",
                "disputed_cents": "INTEGER NOT NULL DEFAULT 0",
            },
            "customer_messages": {
                "is_injection": "INTEGER NOT NULL DEFAULT 0",
                "rejection_reason": "TEXT",
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
            "provider_events": {
                "resource_id": "TEXT",
                "resolution_note": "TEXT",
                "resolved_by": "TEXT",
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

    # Bootstrap default admin user and API key if not present
    with SessionLocal() as db:
        admin_user = db.query(models.User).filter_by(email="admin@recoverflow.in").first()
        if not admin_user:
            admin_user = models.User(
                tenant_id="local",
                email="admin@recoverflow.in",
                name="System Administrator",
                password_hash=hash_password("RecoverFlowAdmin2026!"),
                role="admin",
                is_active=True,
            )
            db.add(admin_user)
            db.flush()

            # If an environment API key is present, also seed it into user_api_keys if not present
            if settings.RECOVERFLOW_API_KEY:
                k_hash = hash_api_key(settings.RECOVERFLOW_API_KEY)
                existing_key = db.query(models.UserApiKey).filter_by(key_hash=k_hash).first()
                if not existing_key:
                    admin_key = models.UserApiKey(
                        tenant_id="local",
                        user_id=admin_user.id,
                        name="Default Admin Key",
                        key_prefix=settings.RECOVERFLOW_API_KEY[:8] if len(settings.RECOVERFLOW_API_KEY) >= 8 else "rf_admin",
                        key_hash=k_hash,
                        role="admin",
                        is_active=True,
                    )
                    db.add(admin_key)
            db.commit()
            logging.info("Bootstrapped initial admin user: admin@recoverflow.in")


def get_db() -> Generator[Session, None, None]:
    """Dependency for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
