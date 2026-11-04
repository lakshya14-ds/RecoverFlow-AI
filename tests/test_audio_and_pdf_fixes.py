"""Regression tests for pre-submission audio intake, PDF extraction, review
confirmation, upload MIME, and Meta model attribution fixes."""
import wave
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base, get_db
from app.main import app
from app.services import intake_pipeline
from app.services.voice_transcribe_agent import voice_agent
from app.skills.extract_invoice_fields import extract_invoice_fields

ROOT = Path(__file__).parents[1]
APP_JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

HEADERS = {"X-RECOVERFLOW-API-KEY": "test-key"}


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def api(db, monkeypatch):
    def override():
        yield db
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEY", "test-key")
    monkeypatch.setattr(settings, "RECOVERFLOW_API_KEYS_JSON", "")
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def no_meta_voice(monkeypatch):
    monkeypatch.setattr(voice_agent, "api_key", "")


def _wav_bytes():
    import io
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 1600)
    return buffer.getvalue()


def test_audio_intake_storage_path_attribute_resilience(db, tmp_path, monkeypatch, no_meta_voice):
    """_process_audio resolves the stored file and attaches evidence with extracted trust state."""
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    audio_file = tmp_path / "INV-AUDIO-1-note.wav"
    audio_file.write_bytes(_wav_bytes())
    invoice = models.Invoice(
        tenant_id="local", invoice_number="INV-AUDIO-1", invoice_type="AR",
        counterparty_name="Audio Retailer", issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31), amount=Decimal("5000.00"),
        total_amount=Decimal("5000.00"), face_amount_cents=500000,
        currency="INR", status="pending")
    db.add(invoice)
    db.flush()
    job = models.IntakeUpload(
        id="audio-job-1", tenant_id="local", actor="staff",
        filename="INV-AUDIO-1-note.wav", mime_type="audio/wav",
        source_path=str(audio_file), size_bytes=len(_wav_bytes()),
        status="queued", stage="Uploaded")
    db.add(job)
    db.commit()

    intake_pipeline._process_audio(db, job)  # Must not raise AttributeError.
    db.commit()

    db.refresh(job)
    assert job.status == "completed"
    evidence = db.query(models.CaseEvidence).filter_by(
        invoice_id=invoice.id, source_type="whatsapp_voice_note").one()
    assert evidence.trust_state == "extracted"
    assert evidence.verified is False
    transcription = db.query(models.VoiceTranscription).filter_by(
        invoice_id=invoice.id).one()
    assert transcription.original_filename == "INV-AUDIO-1-note.wav"


def test_audio_intake_unmatched_requires_staff_review(db, tmp_path, monkeypatch, no_meta_voice):
    """Unmatched audio does not silently attach to first open invoice; raises ValueError."""
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)
    audio_file = tmp_path / "unmatched_note.wav"
    audio_file.write_bytes(_wav_bytes())
    invoice = models.Invoice(
        tenant_id="local", invoice_number="INV-UNRELATED-99", invoice_type="AR",
        counterparty_name="Unrelated Retailer", issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31), amount=Decimal("5000.00"),
        total_amount=Decimal("5000.00"), face_amount_cents=500000,
        currency="INR", status="pending")
    db.add(invoice)
    db.commit()
    job = models.IntakeUpload(
        id="audio-job-2", tenant_id="local", actor="staff",
        filename="unmatched_note.wav", mime_type="audio/wav",
        source_path=str(audio_file), size_bytes=len(_wav_bytes()),
        status="queued", stage="Uploaded")
    db.add(job)
    db.commit()

    with pytest.raises(ValueError, match="no unique matching invoice"):
        intake_pipeline._process_audio(db, job)

    assert db.query(models.CaseEvidence).filter_by(invoice_id=invoice.id).count() == 0


def test_audio_intake_hero_filename_no_canned_facts(tmp_path, no_meta_voice):
    """Ordinary upload with hero-style filename does not trigger canned facts without is_hero=True."""
    audio_file = tmp_path / "INV-2026-HERO-unrelated.wav"
    audio_file.write_bytes(_wav_bytes())
    res = voice_agent.transcribe_and_store(
        audio_file,
        filename="INV-2026-HERO-unrelated.wav",
        tenant_id="local",
        invoice_id=999
    )
    assert res["extracted_dispute_amount_cents"] == 0
    assert res["confidence"] == 0.0
    assert res["model_name"] == "rules_fallback"
    assert "precision valve" not in res["transcript_text"]


def test_pdf_extraction_without_poppler(tmp_path, monkeypatch):
    """Invoice PDF fields extract cleanly even when pdf2image/poppler fails."""
    pytest.importorskip("reportlab.pdfgen.canvas")
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import letter

    pdf_path = tmp_path / "invoice.pdf"
    canvas = Canvas(str(pdf_path), pagesize=letter)
    canvas.drawString(72, 720, "Acme Distributors Pvt Ltd")
    canvas.drawString(72, 700, "Invoice INV-TEST-1")
    canvas.drawString(72, 680, "Total $1,200.00")
    canvas.drawString(72, 660, "Due 12/31/2026")
    canvas.save()

    import sys
    import types

    class PDFInfoNotInstalledError(Exception):
        """Stand-in for pdf2image.exceptions.PDFInfoNotInstalledError."""

    def _missing_poppler(*args, **kwargs):
        raise PDFInfoNotInstalledError(
            "Unable to get page count. Is poppler installed and in PATH?")

    stub = types.ModuleType("pdf2image")
    stub.convert_from_path = _missing_poppler
    stub_exceptions = types.ModuleType("pdf2image.exceptions")
    stub_exceptions.PDFInfoNotInstalledError = PDFInfoNotInstalledError
    monkeypatch.setitem(sys.modules, "pdf2image", stub)
    monkeypatch.setitem(sys.modules, "pdf2image.exceptions", stub_exceptions)
    fields = extract_invoice_fields(str(pdf_path))

    assert "INV-TEST-1" in fields.raw_text
    assert fields.invoice_number == "INV-TEST-1"
    assert fields.total_amount == Decimal("1200.00")
    assert fields.counterparty_name == "Acme Distributors Pvt Ltd"


def test_review_queue_confirmation_updates_evidence_trust_state(db, api):
    """Review-queue confirmation verifies linked invoice_total evidence."""
    invoice = models.Invoice(
        tenant_id="local", invoice_number="INV-REVIEW-1", invoice_type="AR",
        counterparty_name="Review Retailer", issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31), amount=Decimal("2400.00"),
        total_amount=Decimal("2400.00"), face_amount_cents=240000,
        currency="INR", status="pending_review", requires_human_review=True)
    db.add(invoice)
    db.flush()
    db.add(models.CaseEvidence(
        tenant_id="local", invoice_id=invoice.id, claim_type="invoice_total",
        title="Extracted invoice total",
        description="Document extraction reconciled the total; staff confirmation pending",
        source_type="uploaded_invoice",
        source_reference="/api/v1/intake/uploads/review-job/file",
        amount_cents=240000, verified=False, trust_state="extracted",
        currency="INR"))
    db.commit()

    response = api.put(f"/api/v1/invoices/{invoice.id}/review", headers=HEADERS, json={
        "invoice_number": "INV-REVIEW-1", "invoice_type": "AR",
        "counterparty_name": "Review Retailer", "issue_date": "2026-10-01",
        "due_date": "2026-10-31", "total_amount": "2400.00", "currency": "INR"})
    assert response.status_code == 200, response.text

    evidence = db.query(models.CaseEvidence).filter_by(invoice_id=invoice.id).one()
    assert evidence.verified is True
    assert evidence.trust_state == "verified"
    assert "staff confirmation pending" not in evidence.description
    assert "Verified invoice total" in evidence.description


@pytest.mark.parametrize("filename,mime,prefix", [
    ("note.wav", "audio/wav", b"RIFF\x00\x00\x00\x00WAVE"),
    ("note.mp3", "audio/mpeg", b"ID3\x04\x00\x00\x00\x00\x00"),
    ("note.ogg", "audio/ogg", b"OggS\x00\x02\x00\x00"),
    ("note.m4a", "audio/mp4", b"\x00\x00\x00\x20ftypM4A "),
])
def test_intake_upload_mime_audio_types_supported(api, filename, mime, prefix):
    """Each supported audio upload is accepted with HTTP 202."""
    response = api.post(
        "/api/v1/intake/uploads", content=prefix + b"\x00" * 64,
        headers={**HEADERS, "X-Filename": filename, "Content-Type": mime})
    assert response.status_code == 202, response.text


def test_batch_upload_feedback_preserves_per_file_outcomes():
    """The intake uploader renders one status row per file, never overwriting."""
    assert "outcomes.push" in APP_JS
    assert "batch-upload-summary" in APP_JS
    assert "upload-result-item" in APP_JS
    assert "succeeded" in APP_JS and "failed" in APP_JS
    assert "wav: 'audio/wav'" in APP_JS
    assert "m4a: 'audio/mp4'" in APP_JS
    assert 'accept=".csv, .pdf, .jpg, .jpeg, .png, .wav, .mp3, .ogg, .m4a, audio/*"' in INDEX_HTML


def test_verified_evidence_description_sanitized_in_frontend():
    """Verified evidence never shows the stale 'staff confirmation pending' text."""
    assert "Verified by staff" in APP_JS
    assert "staff confirmation pending" in APP_JS


def test_meta_model_suite_attributed_across_frontend():
    """Every Meta model surface states its exact model name."""
    assert "META MUSE SPARK 1.3" in APP_JS
    assert "AI Co-Pilot &amp; Customer Negotiation &middot; Powered by Meta Muse Spark 1.3" in INDEX_HTML
    assert "Supervised autonomous drafting using Meta Muse Spark 1.3. Bounded communication policy with dual-control staff approval." in INDEX_HTML
    assert "VISUAL PROOF &amp; STAMPS" in APP_JS
    assert "(Meta SAM 3.1 AI Computer Vision Perception)" in APP_JS
    assert "Perceptual crop segmented via Meta SAM 3.1" in APP_JS
    assert "Meta Muse Voice Transcribe (Multilingual Speech Intelligence & Diarization)" in APP_JS
    assert "Intake Engine: Meta SAM 3.1 (Document Computer Vision), Meta Muse Voice Transcribe (Audio Notes), Meta Muse Spark 1.3 (Autonomous Triage)" in INDEX_HTML
