"""
Unit and Integration Tests for Database & Authentication System
Tests password hashing, API keys, session tokens, RBAC gates, and auth endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import db_manager, models
from app.main import app
from app.services.auth_security import (
    hash_password,
    verify_password,
    generate_api_key,
    hash_api_key,
)


@pytest.fixture(autouse=True)
def setup_auth_db(monkeypatch, tmp_path):
    """Give auth tests their own database and deterministic bootstrap user."""
    db_path = tmp_path / "auth-test.db"
    engine = create_engine("sqlite:///" + db_path.as_posix(),
                           connect_args={"check_same_thread": False})
    monkeypatch.setattr(settings, "APEX_DB_PATH", str(db_path))
    monkeypatch.setattr(db_manager, "engine", engine)
    monkeypatch.setattr(db_manager, "SessionLocal", sessionmaker(
        autocommit=False, autoflush=False, bind=engine))
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "test-admin-secret")
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_PASSWORD", "TestAdminPassword2026!")
    db_manager.init_db()
    yield
    engine.dispose()


def test_password_hashing():
    """Verify PBKDF2-HMAC-SHA256 password hashing and constant-time validation."""
    pwd = "SecureStaffPassword123!"
    hashed = hash_password(pwd)
    assert hashed.startswith("pbkdf2_sha256$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_api_key_generation():
    """Verify API key formatting, prefix extraction, and SHA-256 hashing."""
    raw_key, prefix, key_hash = generate_api_key(prefix="rf")
    assert raw_key.startswith("rf_")
    assert len(prefix) == 12
    assert key_hash == hash_api_key(raw_key)


def test_auth_login_and_me_endpoint():
    """Verify staff login, session token creation, and profile retrieval via Bearer token."""
    client = TestClient(app)

    # 1. Login with bootstrapped default admin
    res = client.post("/api/v1/auth/login", json={
        "email": "admin@recoverflow.in",
        "password": "TestAdminPassword2026!"
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert "token" in data
    assert data["token"].startswith("rfs_")
    token = data["token"]
    assert data["user"]["email"] == "admin@recoverflow.in"
    assert data["user"]["role"] == "admin"

    # 2. Access /auth/me with Bearer token
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["actor"] == "admin@recoverflow.in"
    assert me_data["role"] == "admin"

    # 3. Invalid password fails with 401
    bad_login = client.post("/api/v1/auth/login", json={
        "email": "admin@recoverflow.in",
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401


def test_user_management_and_rbac():
    """Verify admin can create users and non-admins are restricted."""
    client = TestClient(app)
    admin_headers = {"X-RECOVERFLOW-API-KEY": "test-admin-secret"}

    # 1. Create a viewer user
    new_user_res = client.post("/api/v1/auth/users", headers=admin_headers, json={
        "email": "auditor@retailer.in",
        "name": "Audit Officer",
        "password": "AuditorPassword2026!",
        "role": "viewer"
    })
    assert new_user_res.status_code == 201
    user_info = new_user_res.json()
    assert user_info["email"] == "auditor@retailer.in"
    assert user_info["role"] == "viewer"

    # 2. Login as the new viewer user
    login_res = client.post("/api/v1/auth/login", json={
        "email": "auditor@retailer.in",
        "password": "AuditorPassword2026!"
    })
    assert login_res.status_code == 200
    viewer_token = login_res.json()["token"]
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    # 3. Viewer attempts to create another user -> forbidden 403
    forbidden_res = client.post("/api/v1/auth/users", headers=viewer_headers, json={
        "email": "hacker@test.local",
        "name": "Intruder",
        "password": "Password123!",
        "role": "admin"
    })
    assert forbidden_res.status_code == 403

    # 4. Admin lists users
    users_list = client.get("/api/v1/auth/users", headers=admin_headers)
    assert users_list.status_code == 200
    emails = [u["email"] for u in users_list.json()]
    assert "admin@recoverflow.in" in emails
    assert "auditor@retailer.in" in emails


def test_api_key_lifecycle():
    """Verify generating, authenticating with, and revoking database-backed API keys."""
    client = TestClient(app)
    admin_headers = {"X-RECOVERFLOW-API-KEY": "test-admin-secret"}

    # 1. Create an API key
    key_res = client.post("/api/v1/auth/keys", headers=admin_headers, json={
        "name": "Shopify Integration Key",
        "role": "editor",
        "expires_in_days": 30
    })
    assert key_res.status_code == 201
    key_data = key_res.json()
    raw_key = key_data["raw_key"]
    key_id = key_data["id"]
    assert raw_key.startswith("rf_")

    # 2. Use the generated API key to access protected health / cases endpoints
    custom_key_headers = {"X-RECOVERFLOW-API-KEY": raw_key}
    cases_res = client.get("/api/v1/cases", headers=custom_key_headers)
    assert cases_res.status_code == 200

    # 3. Check profile for the API key
    me_res = client.get("/api/v1/auth/me", headers=custom_key_headers)
    assert me_res.status_code == 200
    assert me_res.json()["actor"] == "key_Shopify Integration Key"

    # 4. Revoke the API key
    revoke_res = client.delete(f"/api/v1/auth/keys/{key_id}", headers=admin_headers)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "revoked"

    # 5. Revoked key now fails authentication
    failed_res = client.get("/api/v1/cases", headers=custom_key_headers)
    assert failed_res.status_code == 401
