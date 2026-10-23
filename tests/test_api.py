"""
RecoverFlow - Receivables and Collections
"""
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_system_health():
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "RecoverFlow"

def test_system_config(monkeypatch):
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "test-secret")
    response = client.get("/api/v1/system/config", headers={"X-RECOVERFLOW-API-KEY": "test-secret"})
    assert response.status_code == 200
    assert "PORT" in response.json()

def test_api_rejects_missing_key(monkeypatch):
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "test-secret")
    response = client.get("/api/v1/system/config")
    assert response.status_code == 401
