"""Focused regression tests for the live Chrome QA defect fixes.

Covers: neutral SAM preview concepts on non-POD documents, zero fabricated
confidence, ASCII segment markers, collect-button policy alignment, sandbox
transparency copy, dynamic evidence count, offer-button guard, styled
evaluation output, and self-initializing test fixtures.
"""
import re
from pathlib import Path

import pytest
from PIL import Image

from app.config import settings
from app.database import models
from app.services import sam_agent

ROOT = Path(__file__).parents[1]
APP_JS = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
STYLES_CSS = (ROOT / "frontend" / "styles.css").read_text(encoding="utf-8")

EMOJI_PATTERN = re.compile(
    r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u2B00-\u2BFF\uFE0F"
    r"\u2600-\u2712\u2714\u2716-\u27BF]"
)


@pytest.fixture
def unconfigured_meta(monkeypatch):
    """Force deterministic offline fallback regardless of local .env keys."""
    monkeypatch.setattr(settings, "META_MODEL_API_KEY", "")
    monkeypatch.setattr(settings, "META_API_KEY_1", "")
    monkeypatch.setattr(settings, "META_API_KEY_2", "")
    monkeypatch.setattr(settings, "META_API_KEY_3", "")


def _plain_png(tmp_path, name="doc.png"):
    img = Image.new("RGB", (600, 800), color=(245, 245, 245))
    path = tmp_path / name
    img.save(path, format="PNG")
    return path.read_bytes()


def test_invoice_segmentation_uses_neutral_preview_concepts(unconfigured_meta, tmp_path):
    """Visual extraction on an invoice must not claim POD findings."""
    results = sam_agent.segment_image_bytes(
        _plain_png(tmp_path),
        mime_type="image/png",
        filename_hint="INV-2026-TEST.png",
    )
    assert {r.concept for r in results} == {
        "document_header", "document_totals", "document_signoff"}
    assert {r.label for r in results} == {
        "Document Header & Particulars",
        "Invoice Totals & Calculations",
        "Document Endorsement Region",
    }
    for result in results:
        assert result.confidence == 0.0
        assert result.processing_method == "deterministic_preview"
        assert result.verification_state == "unverified"
        assert "Unverified document crop preview" in result.notes


def test_pod_segmentation_unconfigured_uses_pod_concepts_zero_confidence(
        unconfigured_meta, tmp_path):
    """POD fallback crops keep POD concepts but never fabricate confidence."""
    results = sam_agent.segment_image_bytes(
        _plain_png(tmp_path),
        mime_type="image/png",
        filename_hint="DELIVERY-CHALLAN-123.png",
        source_type="delivery_challan",
    )
    assert {r.concept for r in results} == {
        "stamp_signature", "receiving_notes", "damaged_goods"}
    for result in results:
        assert result.confidence == 0.0
        assert result.processing_method == "deterministic_preview"
        assert result.verification_state == "unverified"
        assert "Unverified document crop preview" in result.notes
        assert "shortage of 10 sets" not in result.notes.lower()


def test_evidence_segment_default_confidence_is_zero():
    """Unverified preview segments default to 0.0, never 0.90-0.95."""
    default = models.EvidenceSegment.__table__.c.confidence.default
    assert default is not None
    assert float(default.arg) == 0.0


def test_frontend_has_zero_emoji():
    """No pictographic emoji may remain in the shipped frontend bundle."""
    for name, text in (("app.js", APP_JS), ("index.html", INDEX_HTML)):
        found = sorted(set(EMOJI_PATTERN.findall(text)))
        assert found == [], f"{name} contains emoji: {[hex(ord(c)) for c in found]}"


def test_sam_chip_markers_and_modal_copy():
    """Segment chips use ASCII markers and honest confidence attribution."""
    for marker in ("[STAMP]", "[NOTE]", "[PHOTO]", "[DOC]"):
        assert marker in APP_JS
    assert "(Seeded Reference)" in APP_JS
    assert "(Meta SAM 3.1 AI Perception)" in APP_JS
    assert "Unverified (0%)" in APP_JS
    assert ("Unverified preview crop \u00b7 Meta SAM 3.1 unconfigured. "
            "Does not establish stamps, signatures, or physical defects.") in APP_JS


def test_collect_button_policy_alignment():
    """Held cases show a blocked-collection tag instead of Collect Now."""
    assert "isHeld" in APP_JS
    assert "canCollect" in APP_JS
    assert "Contact paused by staff" in APP_JS
    assert "Contact held: Active investigation" in APP_JS
    assert "Contact suppressed: Reconciliation mismatch" in APP_JS
    assert "Contact suppressed: Staff review required" in APP_JS
    assert "Undisputed \u00b7 On Hold (Staff Review Required)" in APP_JS
    assert "Collection blocked under policy" in APP_JS
    assert "badge-held" in APP_JS
    assert ".badge-held" in STYLES_CSS


def test_sandbox_and_marketing_copy():
    """Sandbox dispatch is explicit and overreaching claims are replaced."""
    assert ("Dispatches strictly to simulated sandbox outbox. "
            "Dual-control staff review required before external transmission.") in INDEX_HTML
    assert "TLS Encrypted Communication" in INDEX_HTML
    assert "Indian MSME Invoicing Standard (GST Formats)" in INDEX_HTML
    assert "Bounded Policy Guardrails" in INDEX_HTML
    assert "Bank-Grade 256-Bit SSL" not in INDEX_HTML
    assert "MSME SAMADHAAN Ready" not in INDEX_HTML
    assert "Protection Guarantees" not in INDEX_HTML
    assert "Rules Fallback Mode (Deterministic)" in APP_JS


def test_evidence_count_offer_guard_agent_removed():
    """Dynamic evidence count, guarded offer button, no obsolete panel."""
    assert 'id="tab-btn-evidence"' in INDEX_HTML
    assert "(7)" not in INDEX_HTML
    assert "view-agent" not in INDEX_HTML
    assert "agent: 'review'" not in APP_JS
    assert "evCount" in APP_JS
    assert 'Switch mode to "Delegate to AI" to prepare autonomous offers' in APP_JS
    assert "Start negotiation session to enable offers" in APP_JS


def test_evaluation_report_is_styled():
    """The generated evaluation page uses styled cards and tables."""
    html = (ROOT / "frontend" / "evaluation.html").read_text(encoding="utf-8")
    assert "<table" in html
    assert "<pre>" not in html
    assert "Meta Muse Spark 1.3" in html
    assert "Meta SAM 3.1" in html
    assert "Meta Muse Voice" in html
    assert "fallback" in html.lower()
    md = (ROOT / "docs" / "evaluation.md").read_text(encoding="utf-8")
    assert "Meta Muse Spark 1.3" in md
    assert "Meta SAM 3.1" in md


def test_conftest_self_initializes():
    """The test suite bootstraps its own isolated database."""
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert "CHANNELS_SANDBOX_ONLY" in conftest
    assert "init_db" in conftest
