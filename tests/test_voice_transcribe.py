"""
Unit and integration tests for Meta Muse Voice Transcribe (muse-voice-transcribe).
Tests audio generation, voice transcription agent, database model, and API endpoints.
"""
import io
import json
import pytest
from pathlib import Path
from starlette.testclient import TestClient

from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.services.voice_transcribe_agent import voice_agent, VoiceTranscribeAgent
from scripts.generate_hero_voicenote import generate_hero_voicenote


def test_generate_hero_voicenote(tmp_path):
    wav_path = tmp_path / "test_voice.wav"
    out = generate_hero_voicenote(str(wav_path))
    assert Path(out).is_file()
    assert Path(out).stat().st_size > 10000


def test_voice_transcribe_agent(tmp_path):
    wav_path = tmp_path / "VOICENOTE-2026-HERO.wav"
    generate_hero_voicenote(str(wav_path))

    res = voice_agent.transcribe_and_store(
        wav_path,
        filename="VOICENOTE-2026-HERO.wav",
        tenant_id="local",
        invoice_id=999,
        is_hero=True
    )

    assert res["language"] == "hinglish"
    assert res["confidence"] >= 0.90
    assert "30,000" in res["transcript_text"] or "30000" in res["transcript_text"]
    assert res["extracted_dispute_amount_cents"] == 3000000
    assert res["extracted_promise_amount_cents"] == 6000000
    assert res["extracted_promise_date"] == "Tuesday"

    diarization = json.loads(res["diarization_json"])
    assert len(diarization) >= 3
    assert diarization[0]["start"] == 0.0
    assert "Bharat Retail" in diarization[0]["speaker"]

    # Also verify non-hero arbitrary audio does not get hijacked by hero facts
    other_path = tmp_path / "arbitrary_call.wav"
    generate_hero_voicenote(str(other_path))
    other_res = voice_agent.transcribe_and_store(
        other_path,
        filename="arbitrary_call.wav",
        tenant_id="local",
        invoice_id=101,
        is_hero=False
    )
    assert other_res["confidence"] == 0.0
    assert other_res["extracted_dispute_amount_cents"] == 0
    assert "2026-HERO" not in other_res["transcript_text"]


def test_voice_transcription_db_lifecycle():
    db = next(get_db())
    try:
        from app.database.models import Invoice, VoiceTranscription
        from datetime import date
        from decimal import Decimal
        inv = Invoice(
            tenant_id="test_voice",
            invoice_number="INV-VOICE-01",
            invoice_type="AR",
            counterparty_name="Voice Test Corp",
            issue_date=date(2026, 10, 1),
            due_date=date(2026, 11, 1),
            amount=Decimal("100000.00"),
            total_amount=Decimal("100000.00")
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        vt = VoiceTranscription(
            tenant_id="test_voice",
            invoice_id=inv.id,
            audio_path="data/documents/audio/test.wav",
            original_filename="whatsapp_voice_01.wav",
            duration_seconds=12.5,
            language="hinglish",
            transcript_text="Test voice transcript for dispute",
            diarization_json="[]",
            extracted_dispute_amount_cents=2000000,
            extracted_dispute_reason="Shortage",
            confidence=0.98,
            model_name="muse-voice-transcribe"
        )
        db.add(vt)
        db.commit()
        db.refresh(vt)

        assert vt.id is not None
        assert vt.invoice_id == inv.id
        assert vt.confidence == 0.98

        # Clean up in FK order
        db.delete(vt)
        db.commit()
        db.delete(inv)
        db.commit()
    finally:
        db.close()


def test_voice_api_endpoints():
    from app.main import app
    client = TestClient(app)
    headers = {"X-RECOVERFLOW-API-KEY": "recoverflow-local-final-qa-2026"}

    # Seed hero case
    from scripts.seed_hero_case import seed_hero_case
    hero_inv = seed_hero_case()

    # 1. GET /cases/{id}/voice
    res = client.get(f"/api/v1/cases/{hero_inv.id}/voice", headers=headers)
    assert res.status_code == 200
    voice_list = res.json()
    assert len(voice_list) >= 1
    first_voice = voice_list[0]
    assert first_voice["language"] == "hinglish"
    assert "audio_url" in first_voice

    # 2. GET and HEAD /cases/{id}/voice/{voice_id}/audio
    voice_id = first_voice["id"]
    head_res = client.head(f"/api/v1/cases/{hero_inv.id}/voice/{voice_id}/audio", headers=headers)
    assert head_res.status_code == 200
    assert "audio" in head_res.headers.get("content-type", "")

    get_audio_res = client.get(f"/api/v1/cases/{hero_inv.id}/voice/{voice_id}/audio", headers=headers)
    assert get_audio_res.status_code == 200
    assert len(get_audio_res.content) > 1000

    # 3. POST /cases/{id}/voice/upload
    wav_bytes = io.BytesIO()
    import wave, math, struct
    with wave.open(wav_bytes, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        frames = bytearray()
        for i in range(16000):  # 1 sec tone
            s = int(10000 * math.sin(2 * math.pi * 440 * (i / 16000)))
            frames.extend(struct.pack("<h", s))
        wf.writeframes(frames)
    wav_bytes.seek(0)

    upload_res = client.post(
        f"/api/v1/cases/{hero_inv.id}/voice/upload",
        headers={**headers, "X-Filename": "new_voice_note.wav", "Content-Type": "audio/wav"},
        content=wav_bytes.getvalue()
    )
    assert upload_res.status_code == 200
    up_data = upload_res.json()
    assert up_data["id"] is not None
    assert "audio_url" in up_data
    assert up_data["confidence"] >= 0.0
    assert up_data["extracted_dispute_amount_cents"] == 0
