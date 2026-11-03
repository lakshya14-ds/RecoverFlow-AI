"""Regression tests for evidence integrity and honest reporting:
1. Evidence-grounded executive summaries without fabricated facts.
2. Prevention of synthetic/hero crops on CSVs or missing files.
"""
from datetime import date
from decimal import Decimal
import io
import json
from pathlib import Path
from PIL import Image

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import models
from app.database.db_manager import get_db
from app.main import app
from scripts.seed_hero_case import seed_hero_case


@pytest.fixture
def api_client():
    client = TestClient(app)
    return client


@pytest.fixture
def auth_headers():
    return {"X-RECOVERFLOW-API-KEY": "recoverflow-local-final-qa-2026"}


def test_manual_invoice_executive_summary_has_no_hero_facts(api_client, auth_headers):
    """A fresh manual invoice must not leak hero facts (valves, PO-2026-HERO, RTGS, Tuesday, ₹30k)."""
    db = next(get_db())
    try:
        # Create manual invoice similar to QA-20261102-CODEX-001
        inv = models.Invoice(
            tenant_id="local",
            invoice_number="QA-TEST-MANUAL-001",
            invoice_type="AR",
            counterparty_name="Acme Supplies Ltd",
            issue_date=date(2026, 11, 2),
            due_date=date(2026, 12, 2),
            amount=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
            face_amount_cents=100000,
            currency="INR",
            source="manual",
            status="pending"
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        resp = api_client.get(f"/api/v1/cases/{inv.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "executive_summary" in data
        summary = data["executive_summary"]
        text = summary["text"]
        rec = summary["recommended_next_step"]

        # 1. Must contain clear insufficient verified evidence statement
        assert "Insufficient verified evidence to summarize delivery details or payment commitments." in text
        assert "Customer Acme Supplies Ltd was billed" in text
        assert "QA-TEST-MANUAL-001" in text

        # 2. Must not contain any fabricated hero facts
        assert "PO-2026-HERO" not in text
        assert "valve" not in text.lower()
        assert "missing units" not in text.lower()
        assert "tuesday" not in text.lower()
        assert "rtgs" not in text.lower()
        assert "30,000" not in text
        assert "30,000" not in rec

        # 3. Label must accurately reflect generation method
        assert summary["generation_label"] == "Deterministic Summary"
        assert summary["generation_method"] == "deterministic_summary"

        # 4. Accounting amounts must match backend math exactly
        assert data["invoice_total_cents"] == 100000
        assert data["outstanding_cents"] == 100000
        assert data["disputed_cents"] == 0
        assert data["undisputed_cents"] == 100000

        # Clean up
        db.delete(inv)
        db.commit()
    finally:
        db.close()


def test_paused_and_held_case_recommendations_require_staff_review(api_client, auth_headers):
    """A paused or held case must recommend staff review, not immediate collection."""
    db = next(get_db())
    try:
        inv = models.Invoice(
            tenant_id="local",
            invoice_number="QA-TEST-PAUSED-001",
            invoice_type="AR",
            counterparty_name="Paused Customer Corp",
            issue_date=date(2026, 11, 2),
            due_date=date(2026, 12, 2),
            amount=Decimal("5000.00"),
            total_amount=Decimal("5000.00"),
            face_amount_cents=500000,
            currency="INR",
            source="manual",
            status="pending",
            contact_suppressed=True
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        resp = api_client.get(f"/api/v1/cases/{inv.id}", headers=auth_headers)
        assert resp.status_code == 200
        summary = resp.json()["executive_summary"]
        assert "Customer contact is paused" in summary["recommended_next_step"]
        assert "Staff review required" in summary["recommended_next_step"]
        assert summary["can_collect"] is False

        # Now test investigation hold
        inv.contact_suppressed = False
        inv.investigation_hold = True
        db.commit()

        resp2 = api_client.get(f"/api/v1/cases/{inv.id}", headers=auth_headers)
        summary2 = resp2.json()["executive_summary"]
        assert "Investigation hold active" in summary2["recommended_next_step"]
        assert "Staff reconciliation required" in summary2["recommended_next_step"]
        assert summary2["can_collect"] is False

        # Clean up
        db.delete(inv)
        db.commit()
    finally:
        db.close()


def test_dispute_allegation_vs_verified_trust_states(api_client, auth_headers):
    """Unverified allegations must be labeled as allegations; verified claims as verified."""
    db = next(get_db())
    try:
        inv = models.Invoice(
            tenant_id="local",
            invoice_number="QA-TEST-DISPUTE-001",
            invoice_type="AR",
            counterparty_name="Dispute Testing Retailer",
            issue_date=date(2026, 11, 2),
            due_date=date(2026, 12, 2),
            amount=Decimal("10000.00"),
            total_amount=Decimal("10000.00"),
            face_amount_cents=1000000,
            currency="INR",
            source="manual",
            status="disputed",
            disputed_cents=200000
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        # 1. Add unverified (alleged) evidence
        alleged_ev = models.CaseEvidence(
            tenant_id="local",
            invoice_id=inv.id,
            claim_type="dispute_item",
            title="Customer Phone Complaint",
            description="Alleged damaged carton",
            source_type="phone_call",
            source_reference="CALL-NOTE-001",
            amount_cents=200000,
            verified=False,
            trust_state="alleged"
        )
        db.add(alleged_ev)
        db.commit()

        resp1 = api_client.get(f"/api/v1/cases/{inv.id}", headers=auth_headers)
        text1 = resp1.json()["executive_summary"]["text"]
        assert "unverified deduction" in text1.lower()
        assert "allegation pending staff review" in text1.lower()

        # 2. Update to verified
        alleged_ev.trust_state = "verified"
        alleged_ev.verified = True
        db.commit()

        resp2 = api_client.get(f"/api/v1/cases/{inv.id}", headers=auth_headers)
        text2 = resp2.json()["executive_summary"]["text"]
        assert "verified deduction" in text2.lower()
        assert "held on freeze" in text2.lower()

        # Clean up
        db.delete(alleged_ev)
        db.delete(inv)
        db.commit()
    finally:
        db.close()


def test_csv_segmentation_rejected_with_400(api_client, auth_headers):
    """Segmenting a plain CSV must return HTTP 400 and not produce synthetic crops or shortage claims."""
    db = next(get_db())
    try:
        inv = models.Invoice(
            tenant_id="local",
            invoice_number="QA-TEST-CSV-001",
            invoice_type="AR",
            counterparty_name="CSV Customer",
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

        # Add CSV evidence
        csv_ev = models.CaseEvidence(
            tenant_id="local",
            invoice_id=inv.id,
            claim_type="invoice_total",
            title="Invoices CSV Upload",
            description="Imported billing sheet",
            source_type="csv_upload",
            source_reference="docs/imports/test_invoices.csv",
            amount_cents=500000,
            verified=True,
            trust_state="verified"
        )
        db.add(csv_ev)
        db.commit()
        db.refresh(csv_ev)

        # Attempt visual proof extraction on CSV
        resp = api_client.post(
            f"/api/v1/cases/{inv.id}/evidence/{csv_ev.id}/segment",
            headers=auth_headers
        )
        assert resp.status_code == 400
        assert "Visual proof extraction is only supported for image (PNG, JPG) and PDF documents" in resp.json()["detail"]

        # Balances must be completely unchanged
        db.refresh(inv)
        assert inv.face_amount_cents == 500000
        assert inv.disputed_cents == 0

        # No segments created
        segs = db.query(models.EvidenceSegment).filter_by(tenant_id="local", evidence_id=csv_ev.id).all()
        assert len(segs) == 0

        # Clean up
        db.delete(csv_ev)
        db.delete(inv)
        db.commit()
    finally:
        db.close()


def test_missing_file_segmentation_fails_and_never_substitutes_hero(api_client, auth_headers):
    """A missing document source must return 404 and never substitute the hero challan."""
    db = next(get_db())
    try:
        inv = models.Invoice(
            tenant_id="local",
            invoice_number="QA-TEST-MISSING-DOC-001",
            invoice_type="AR",
            counterparty_name="Missing Doc Customer",
            issue_date=date(2026, 11, 2),
            due_date=date(2026, 12, 2),
            amount=Decimal("3000.00"),
            total_amount=Decimal("3000.00"),
            face_amount_cents=300000,
            currency="INR",
            source="manual",
            status="pending"
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        ghost_ev = models.CaseEvidence(
            tenant_id="local",
            invoice_id=inv.id,
            claim_type="dispute_item",
            title="Nonexistent POD",
            description="Missing file on disk",
            source_type="delivery_challan",
            source_reference="docs/challan/GHOST_CHALLAN_NOT_FOUND.png",
            amount_cents=100000,
            verified=False,
            trust_state="alleged"
        )
        db.add(ghost_ev)
        db.commit()
        db.refresh(ghost_ev)

        resp = api_client.post(
            f"/api/v1/cases/{inv.id}/evidence/{ghost_ev.id}/segment",
            headers=auth_headers
        )
        assert resp.status_code == 404
        assert "not accessible on the server" in resp.json()["detail"]

        # Ensure no segments were created from hero challan
        segs = db.query(models.EvidenceSegment).filter_by(tenant_id="local", evidence_id=ghost_ev.id).all()
        assert len(segs) == 0

        # Clean up
        db.delete(ghost_ev)
        db.delete(inv)
        db.commit()
    finally:
        db.close()


def test_image_segmentation_unconfigured_model_produces_unverified_preview(api_client, auth_headers, tmp_path):
    """When Meta SAM API is unconfigured, image segmentation creates unverified preview crops with 0.0 confidence."""
    # Create a real test PNG
    test_img = Image.new("RGB", (600, 800), color=(245, 245, 245))
    png_path = tmp_path / "actual_test_pod.png"
    test_img.save(png_path, format="PNG")

    db = next(get_db())
    try:
        inv = models.Invoice(
            tenant_id="local",
            invoice_number="QA-TEST-IMAGE-001",
            invoice_type="AR",
            counterparty_name="Real Image Customer",
            issue_date=date(2026, 11, 2),
            due_date=date(2026, 12, 2),
            amount=Decimal("4000.00"),
            total_amount=Decimal("4000.00"),
            face_amount_cents=400000,
            currency="INR",
            source="manual",
            status="pending"
        )
        db.add(inv)
        db.commit()
        db.refresh(inv)

        ev = models.CaseEvidence(
            tenant_id="local",
            invoice_id=inv.id,
            claim_type="dispute_item",
            title="Real Physical Receipt",
            description="Scanned goods receipt note",
            source_type="goods_receipt",
            source_reference=str(png_path.resolve()),
            amount_cents=100000,
            verified=False,
            trust_state="alleged"
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        # Run segmentation
        resp = api_client.post(
            f"/api/v1/cases/{inv.id}/evidence/{ev.id}/segment",
            headers=auth_headers
        )
        assert resp.status_code == 200
        seg_data = resp.json()

        # Must have preview crops without fabricated confidence or shortage
        assert len(seg_data) >= 1
        for s in seg_data:
            assert s["processing_method"] == "deterministic_preview"
            assert s["verification_state"] == "unverified"
            assert s["confidence"] == 0.0
            assert "Unverified document crop preview" in s["notes"]
            assert "shortage of 10 sets" not in s["notes"].lower()

        # Clean up
        db.query(models.EvidenceSegment).filter_by(tenant_id="local", evidence_id=ev.id).delete()
        db.delete(ev)
        db.delete(inv)
        db.commit()
    finally:
        db.close()


def test_hero_case_fixture_provenance_intact(api_client, auth_headers):
    """The seeded hero case INV-2026-HERO must retain its benchmark fixture provenance."""
    hero_inv = seed_hero_case()
    resp = api_client.get(f"/api/v1/cases/{hero_inv.id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    summary = data["executive_summary"]
    # Check hero facts are properly represented in the hero case
    assert "PO-2026-HERO" in summary["text"]
    assert "240,000" in summary["text"]
    assert "150,000" in summary["text"]
    assert "30,000" in summary["text"]
    assert "60,000" in summary["text"]
    assert "Tuesday" in summary["text"]

    # Check challan segments have fixture provenance
    challan_ev = next(ev for ev in data["evidence"] if "challan" in (ev.get("source_reference") or "").lower())
    assert len(challan_ev["segments"]) == 3
    for s in challan_ev["segments"]:
        assert s["processing_method"] in ("fixture", "sam_api")
        assert s["confidence"] >= 0.90

