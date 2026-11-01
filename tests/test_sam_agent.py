"""Tests for Meta SAM 3.1 perception integration."""
import os
import json
from pathlib import Path
from decimal import Decimal
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import models
from app.database.models import Base
from app.services import sam_agent
from scripts.generate_hero_challan import generate_hero_challan


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_sam_pod_concepts():
    assert "stamp_signature" in sam_agent.POD_CONCEPTS
    assert "receiving_notes" in sam_agent.POD_CONCEPTS
    assert "damaged_goods" in sam_agent.POD_CONCEPTS
    assert "stamp" in sam_agent.POD_CONCEPTS["stamp_signature"]["prompt"]


def test_segment_synthetic_challan_bytes():
    png_path, _ = generate_hero_challan()
    assert os.path.exists(png_path)
    challan_bytes = Path(png_path).read_bytes()

    results = sam_agent.segment_image_bytes(
        challan_bytes,
        mime_type="image/png",
        filename_hint="CHALLAN-2026-HERO.png"
    )

    assert len(results) == 3
    concepts = {r.concept for r in results}
    assert concepts == {"stamp_signature", "receiving_notes", "damaged_goods"}

    for r in results:
        assert 0.0 <= r.bbox["ymin"] < r.bbox["ymax"] <= 1.0
        assert 0.0 <= r.bbox["xmin"] < r.bbox["xmax"] <= 1.0
        assert r.confidence >= 0.90
        assert os.path.exists(r.crop_path)
        assert Path(r.crop_path).stat().st_size > 50  # Valid cropped PNG
        assert "/segments/file/" in r.crop_url


def test_segment_evidence_db_lifecycle(test_db):
    invoice = models.Invoice(
        tenant_id="local",
        invoice_number="INV-SAM-TEST-001",
        invoice_type="AR",
        counterparty_name="Metro Retail",
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31),
        amount=Decimal("100000.00"),
        total_amount=Decimal("100000.00"),
        face_amount_cents=10000000,
        currency="INR",
        status="disputed",
    )
    test_db.add(invoice)
    test_db.flush()

    generate_hero_challan()
    evidence = models.CaseEvidence(
        tenant_id="local",
        invoice_id=invoice.id,
        claim_type="dispute_item",
        title="Delivery Challan POD",
        description="Physical proof of delivery challan",
        source_type="delivery_challan",
        source_reference="docs/challan/CHALLAN-2026-HERO.png",
        amount_cents=3000000,
        verified=True,
        trust_state="verified"
    )
    test_db.add(evidence)
    test_db.commit()
    test_db.refresh(evidence)

    # 1. Run segmentation
    segments = sam_agent.segment_evidence(test_db, evidence)
    assert len(segments) == 3

    # Query directly from DB
    persisted = test_db.query(models.EvidenceSegment).filter_by(
        tenant_id="local", evidence_id=evidence.id
    ).all()
    assert len(persisted) == 3
    persisted_concepts = {p.concept for p in persisted}
    assert "stamp_signature" in persisted_concepts

    # 2. Idempotent re-segmentation cleans old records
    re_segments = sam_agent.segment_evidence(test_db, evidence)
    assert len(re_segments) == 3
    persisted_after = test_db.query(models.EvidenceSegment).filter_by(
        tenant_id="local", evidence_id=evidence.id
    ).all()
    assert len(persisted_after) == 3


def test_sam_api_endpoints():
    from app.main import app
    client = TestClient(app)
    headers = {"X-RECOVERFLOW-API-KEY": "recoverflow-local-final-qa-2026"}

    # Run seed to ensure hero case is in database
    from scripts.seed_hero_case import seed_hero_case
    seed_hero_case()

    # Get hero case
    cases_resp = client.get("/api/v1/cases", headers=headers)
    assert cases_resp.status_code == 200
    cases = cases_resp.json()
    hero_case = next(c for c in cases if c["invoice_number"] == "INV-2026-HERO")
    hero_id = hero_case["invoice_id"]

    # Get case details with evidence
    detail_resp = client.get(f"/api/v1/cases/{hero_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert "evidence" in detail

    challan_ev = next(
        (ev for ev in detail["evidence"] if "challan" in (ev.get("source_reference") or "").lower()),
        None
    )
    assert challan_ev is not None, "Hero case should have challan evidence"
    evidence_id = challan_ev["id"]

    # 1. Test POST /segment
    post_seg = client.post(f"/api/v1/cases/{hero_id}/evidence/{evidence_id}/segment", headers=headers)
    assert post_seg.status_code == 200
    seg_data = post_seg.json()
    assert len(seg_data) == 3
    assert any(s["concept"] == "stamp_signature" for s in seg_data)

    # 2. Test GET /segments
    get_segs = client.get(f"/api/v1/cases/{hero_id}/evidence/{evidence_id}/segments", headers=headers)
    assert get_segs.status_code == 200
    assert len(get_segs.json()) == 3

    # 3. Test GET segment crop image file
    crop_url = seg_data[0]["crop_url"]
    file_resp = client.get(crop_url, headers=headers)
    assert file_resp.status_code == 200
    assert file_resp.headers["content-type"] == "image/png"
    assert len(file_resp.content) > 50

