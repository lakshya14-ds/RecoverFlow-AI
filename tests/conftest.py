"""Self-initializing test fixtures: isolated DB, sandbox channels, fixed secrets.

Test environment variables are set before any application import so settings
and the database engine bind to an isolated temporary SQLite file. Every run
builds the full schema automatically; no manual database initialization is
needed, and the developer database is never touched.

Note: DATABASE_URL points at an isolated temp *file* rather than
`sqlite:///:memory:` on purpose. API tests seed data in the main thread and
read it through TestClient worker threads; an in-memory SQLite database is
per-connection, so the app threads would see an empty database. A temp file
keeps full isolation with correct cross-thread visibility.
"""
import os
import tempfile

_test_db_file = tempfile.NamedTemporaryFile(
    prefix="recoverflow-test-", suffix=".db", delete=False)
_test_db_file.close()

os.environ["RECOVERFLOW_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///" + _test_db_file.name.replace("\\", "/")
os.environ["JWT_SECRET"] = "test-jwt-secret-key-32-chars-minimum-len"
os.environ["API_KEY"] = "test-staff-key"
os.environ["CHANNELS_SANDBOX_ONLY"] = "true"

import pytest  # noqa: E402

from app.database import Base, engine, init_db  # noqa: E402


@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Build the full schema on the isolated test database for every run."""
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(_test_db_file.name + suffix)
        except OSError:
            pass
