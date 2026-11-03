"""Regression tests for the three confirmed defects:
1. Authenticated voice-note playback and audio endpoint resolution.
2. Safe, authenticated system configuration endpoint with model/engine mapping.
3. Payment simulator failure honesty and authoritative settlement verification.
"""
from datetime import date
from decimal import Decimal
import hashlib
import hmac
import json
from pathlib import Path
from uuid import uuid4
import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.main import app
from scripts.simulate_payment import to_cents, format_inr


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-RECOVERFLOW-API-KEY": "recoverflow-local-final-qa-2026"}


# ============================================================================
# DEFECT 1: AUTHENTICATED VOICE-NOTE PLAYBACK & ENDPOINT RESOLUTION
# ============================================================================

def test_evidence_file_audio_requires_auth(client):
    """Accessing evidence files without auth header must return 401."""
    resp = client.get("/api/v1/cases/1/evidence-files/VOICENOTE-2026-HERO.wav")
    assert resp.status_code == 401


def test_evidence_file_audio_tenant_isolation(client, auth_headers):
    """Accessing evidence file belonging to another tenant or non-existent case must return 404."""
    resp = client.get("/api/v1/cases/999999/evidence-files/VOICENOTE-2026-HERO.wav", headers=auth_headers)
    assert resp.status_code == 404


def test_fixture_audio_playback_and_mimetype(client, auth_headers):
    """Fixture audio linked to case evidence serves with HTTP 200 and audio/wav media-type."""
    db = next(get_db())
    try:
        inv = models.Invoice(
            tenant_id="local",
            invoice_number=f"QA-TEST-AUDIO-{uuid4().hex[:6]}",
            invoice_type="AR",
            counterparty_name="Audio Test Retailer",
            issue_date=date(2026, 11, 2),
            due_date=date(2026, 12, 2),
            amount=Decimal("5000.00"),
            total_amount=Decimal("5000.00"),
            face_amount_cents=500000,
            currency="INR",
            source="manual",
            status="pending"
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        # Link evidence to invoice using existing tracked fixture
        ev = models.CaseEvidence(
            tenant_id="local",
            invoice_id=inv.id,
            claim_type="audio_note",
            title="Customer Voice Note",
            description="Recorded WhatsApp voice note from retailer buyer",
            source_type="audio",
            source_reference="docs/audio/VOICENOTE-2026-HERO.wav",
            trust_state="extracted"
        )
        db.add(ev)
        db.commit()

        # 1. Fetch via evidence-files endpoint with auth
        resp = client.get(f"/api/v1/cases/{inv.id}/evidence-files/VOICENOTE-2026-HERO.wav", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/wav")
        assert len(resp.content) > 0

        # 2. Case details must enrich evidence with is_audio=True and canonical audio_url
        case_resp = client.get(f"/api/v1/cases/{inv.id}", headers=auth_headers)
        assert case_resp.status_code == 200
        evidence_list = case_resp.json().get("evidence", [])
        audio_ev = next((e for e in evidence_list if e.get("source_reference") == "docs/audio/VOICENOTE-2026-HERO.wav"), None)
        assert audio_ev is not None
        assert audio_ev.get("is_audio") is True
        assert audio_ev.get("audio_url") == f"/api/v1/cases/{inv.id}/evidence-files/VOICENOTE-2026-HERO.wav"

    finally:
        db.close()


def test_dedicated_voice_upload_and_audio_endpoint(client, auth_headers):
    """Dedicated voice records in data/documents/audio serve via voice audio endpoint with auth."""
    db = next(get_db())
    voice_file = None
    try:
        inv = models.Invoice(
            tenant_id="local",
            invoice_number=f"QA-TEST-AUDIO-{uuid4().hex[:6]}",
            invoice_type="AR",
            counterparty_name="Dedicated Voice Retailer",
            issue_date=date(2026, 11, 2),
            due_date=date(2026, 12, 2),
            amount=Decimal("12000.00"),
            total_amount=Decimal("12000.00"),
            face_amount_cents=1200000,
            currency="INR",
            source="manual",
            status="pending"
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        # Create dummy voice file in data/documents/audio
        voice_dir = Path(settings.BASE_DIR) / "data" / "documents" / "audio"
        voice_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"voice_{inv.id}_{uuid4().hex[:8]}.wav"
        voice_file = voice_dir / unique_name
        voice_file.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

        # 1. Create linked CaseEvidence
        evidence = models.CaseEvidence(
            tenant_id="local",
            invoice_id=inv.id,
            claim_type="dispute_item",
            title="WhatsApp Voice Note (Customer Statement)",
            description="Audio statement transcribed via Meta Muse Voice Transcribe",
            source_type="whatsapp_voice_note",
            source_reference=f"docs/audio/{voice_file.name}",
            trust_state="verified"
        )
        db.add(evidence)
        db.flush()

        # 2. Persist VoiceTranscription record
        vt = models.VoiceTranscription(
            tenant_id="local",
            invoice_id=inv.id,
            evidence_id=evidence.id,
            audio_path=str(voice_file),
            original_filename=voice_file.name,
            duration_seconds=12.5,
            language="hinglish",
            confidence=0.94,
            transcript_text="Test audio transcription",
            model_name="muse-voice-transcribe"
        )
        db.add(vt)
        db.commit()
        db.refresh(vt)

        # 3. Unauthenticated request to voice audio endpoint returns 401
        unauth_resp = client.get(f"/api/v1/cases/{inv.id}/voice/{vt.id}/audio")
        assert unauth_resp.status_code == 401

        # 4. Authenticated request to voice audio endpoint returns 200 with audio/wav
        auth_resp = client.get(f"/api/v1/cases/{inv.id}/voice/{vt.id}/audio", headers=auth_headers)
        assert auth_resp.status_code == 200
        assert auth_resp.headers["content-type"].startswith("audio/wav")

        # 5. Dedicated voice record audio_url in case details resolves to canonical voice audio route
        case_resp = client.get(f"/api/v1/cases/{inv.id}", headers=auth_headers)
        assert case_resp.status_code == 200
        evidence_list = case_resp.json().get("evidence", [])
        voice_ev = next((e for e in evidence_list if e.get("voice_id") == vt.id), None)
        assert voice_ev is not None
        assert voice_ev.get("is_audio") is True
        assert voice_ev.get("audio_url") == f"/api/v1/cases/{inv.id}/voice/{vt.id}/audio"

    finally:
        db.close()
        if voice_file and voice_file.exists():
            try:
                voice_file.unlink()
            except Exception:
                pass


# ============================================================================
# DEFECT 2: SYSTEM CONFIGURATION ENDPOINT
# ============================================================================

def test_system_config_requires_authentication(client):
    """GET /api/v1/system/config without authentication returns HTTP 401."""
    resp = client.get("/api/v1/system/config")
    assert resp.status_code == 401


def test_system_config_returns_safe_allowlist_and_models(client, auth_headers):
    """GET /api/v1/system/config returns safe allowlist, LLM_MODEL compatibility key, and model engines."""
    resp = client.get("/api/v1/system/config", headers=auth_headers)
    assert resp.status_code == 200
    cfg = resp.json()

    # Core system properties
    assert "HOST" in cfg
    assert "PORT" in cfg
    assert "DEBUG" in cfg

    # Model configuration & backwards compatibility
    assert "LLM_MODEL" in cfg
    assert "AGENT_MODEL" in cfg
    assert cfg["LLM_MODEL"] == cfg["AGENT_MODEL"]
    assert "SAM_MODEL" in cfg
    assert "VOICE_MODEL" in cfg

    # Models & active execution engines
    assert "MODELS_CONFIGURED" in cfg
    models_cfg = cfg["MODELS_CONFIGURED"]
    for role in ("agent", "sam", "voice"):
        assert role in models_cfg
        assert "model" in models_cfg[role]
        assert "configured" in models_cfg[role]
        assert "active_engine" in models_cfg[role]
        assert isinstance(models_cfg[role]["configured"], bool)

    # Thresholds and operational controls
    assert "AUTO_APPROVE_THRESHOLD" in cfg
    assert "HUMAN_REVIEW_THRESHOLD" in cfg
    assert "FRAUD_ALERT_THRESHOLD" in cfg
    assert "DSO_FORECAST_HORIZON" in cfg
    assert "PAYMENT_MODE" in cfg
    assert "LIVE_PAYMENTS_ENABLED" in cfg
    assert "CHANNELS" in cfg
    assert cfg["CHANNELS"].get("sandbox_only") is True

    # Security check: MUST NOT expose credentials, API keys, or database URLs
    for forbidden in ("META_MODEL_API_KEY", "META_API_KEY_1", "RECOVERFLOW_API_KEY",
                      "DATABASE_URL", "RAZORPAY_KEY_SECRET", "WEBHOOK_SECRET"):
        assert forbidden not in cfg


# ============================================================================
# DEFECT 3: PAYMENT SIMULATOR INTEGRITY & SETTLEMENT VERIFICATION
# ============================================================================

def test_to_cents_precision():
    """to_cents must convert INR strings and numbers accurately without floating-point errors."""
    assert to_cents("100") == 10000
    assert to_cents("100.50") == 10050
    assert to_cents(23600.00) == 2360000
    assert to_cents("0.00") == 0
    assert to_cents("60000.00") == 6000000
    with pytest.raises(ValueError):
        to_cents("not-a-number")


def test_payment_webhook_rejects_invalid_signature(client):
    """Razorpay webhook endpoint must reject forged or mismatched signatures with 401."""
    fake_body = json.dumps({"event": "payment_link.paid", "payload": {}}).encode("utf-8")
    invalid_signature = "bad_signature_hash_12345"

    resp = client.post(
        "/api/v1/webhooks/razorpay/local",
        content=fake_body,
        headers={
            "X-Razorpay-Signature": invalid_signature,
            "X-Razorpay-Event-Id": f"evt_{uuid4().hex[:12]}",
            "Content-Type": "application/json"
        }
    )
    assert resp.status_code == 401
    assert "Invalid Razorpay signature" in resp.json().get("detail", "")


def test_payment_webhook_settlement_updates_ledger_and_preserves_dispute(client, auth_headers):
    """A valid signed simulated payment event updates ledger, reduces balance, and freezes dispute hold."""
    db = next(get_db())
    try:
        inv = models.Invoice(
            tenant_id="local",
            invoice_number=f"QA-TEST-PAY-{uuid4().hex[:6]}",
            invoice_type="AR",
            counterparty_name="Simulated Payment Corp",
            issue_date=date(2026, 11, 2),
            due_date=date(2026, 12, 2),
            amount=Decimal("90000.00"),
            total_amount=Decimal("90000.00"),
            face_amount_cents=9000000,
            currency="INR",
            source="manual",
            status="disputed",
            dispute_open=True,
            disputed_cents=3000000,
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        # Create simulated payment link
        payment_link_id = f"plink_qa_test_{uuid4().hex[:8]}"
        plink = models.PaymentLink(
            tenant_id="local",
            invoice_id=inv.id,
            provider="razorpay",
            provider_link_id=payment_link_id,
            idempotency_key=str(uuid4()),
            amount_cents=6000000,
            currency="INR",
            status="created",
            url="https://rzp.io/i/qa_test",
            mode="test"
        )
        db.add(plink)
        db.commit()

        # Construct valid webhook payload with captured=True
        pay_id = f"pay_qa_test_{uuid4().hex[:8]}"
        event_id = f"evt_qa_test_{uuid4().hex[:8]}"
        event_payload = {
            "entity": "event",
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": payment_link_id,
                        "amount": 6000000,
                        "currency": "INR",
                        "status": "paid"
                    }
                },
                "payment": {
                    "entity": {
                        "id": pay_id,
                        "amount": 6000000,
                        "currency": "INR",
                        "status": "captured",
                        "captured": True,
                        "method": "netbanking"
                    }
                }
            }
        }
        body_bytes = json.dumps(event_payload, separators=(',', ':')).encode("utf-8")
        from app.services import tenant_config
        secret = tenant_config.get_secret(db, "local", "razorpay", "webhook_secret")
        assert secret, "Razorpay webhook secret must be configured for local tenant"
        valid_sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

        # Send webhook
        wh_resp = client.post(
            "/api/v1/webhooks/razorpay/local",
            content=body_bytes,
            headers={
                "X-Razorpay-Signature": valid_sig,
                "X-Razorpay-Event-Id": event_id,
                "Content-Type": "application/json"
            }
        )
        assert wh_resp.status_code == 200
        assert wh_resp.json().get("status") in ("ok", "processed")

        # Verify case state in authoritative API
        case_resp = client.get(f"/api/v1/cases/{inv.id}", headers=auth_headers)
        assert case_resp.status_code == 200
        case_data = case_resp.json()

        # Balance was 90,000; paid 60,000 -> remaining balance is 30,000
        assert case_data["balance_cents"] == 3000000
        # Disputed amount remains exactly 30,000 (frozen hold)
        assert case_data["disputed_cents"] == 3000000
        # Undisputed amount is now 0
        assert case_data["undisputed_cents"] == 0
        # Status must transition to PARTIALLY_RESOLVED
        assert case_data["status"] == "PARTIALLY_RESOLVED"

        # Exactly 1 payment ledger entry posted with reference matching payment ID
        payment_entries = [e for e in case_data["entries"] if e.get("kind") == "payment"]
        assert len(payment_entries) == 1
        assert payment_entries[0]["reference"] == pay_id
        assert abs(payment_entries[0]["amount_cents"]) == 6000000

    finally:
        db.close()
