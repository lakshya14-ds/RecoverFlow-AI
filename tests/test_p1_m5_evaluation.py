"""Milestone 5: evaluation determinism, scoring, arm smoke, and findings."""
import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base
from app.services.promises import extract_promise
from scripts.p1_eval_arms import ARMS, unsafe_write_delta
from scripts.p1_eval_cases import (adversarial_cases, all_cases, build_case,
                                   heldout_cases, init_afis, write_snapshot)
from scripts.run_p1_evaluation import score_case, wilson


def _db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


import pytest


@pytest.fixture
def db():
    yield from _db()


def _by_id(case_id):
    return next(case for case in all_cases() if case["id"] == case_id)


def test_fixture_sets_are_deterministic_and_disjoint():
    first = json.dumps(heldout_cases() + adversarial_cases(), sort_keys=True)
    second = json.dumps(heldout_cases() + adversarial_cases(), sort_keys=True)
    assert first == second
    assert len(heldout_cases()) == 24
    assert len(adversarial_cases()) == 14
    ids = [case["id"] for case in heldout_cases() + adversarial_cases()]
    assert len(set(ids)) == 38
    assert {case["set"] for case in heldout_cases()} == {"heldout"}
    assert {case["set"] for case in adversarial_cases()} == {"adversarial"}


def test_wilson_interval_basics():
    assert wilson(0, 0) == (0.0, 0.0)
    low, high = wilson(5, 10)
    assert low < 0.5 < high
    narrow_low, narrow_high = wilson(500, 1000)
    assert narrow_low > low and narrow_high < high


def test_scoring_counts_misses_and_unsafe_legs():
    spec = {"id": "T1",
            "invoices": [{"number": "INV-T", "customer": "c", "currency": "INR",
                          "total": "1000.00", "received": "0", "source_path": "x"}],
            "txns": [{"id": "T1", "currency": "USD"}],
            "ground_truth": {
                "invoices": {"INV-T": {"requested_cents": 100000,
                                       "request_expected": True,
                                       "disputed_cents": 0, "dispute_decided": True,
                                       "must_escalate": False,
                                       "expect_explanations": False}},
                "legs": [], "case_escalate": False}}
    good = {"invoices": {"INV-T": {"requested_cents": 100000, "draft_produced": True,
                                   "draft_text": "Please pay INR 1,000.00.",
                                   "disputed_cents": 0, "open_explanations": 0,
                                   "escalated": False, "promise_created": False,
                                   "clarifications_open": 0}},
            "legs": [], "model_calls": 0}
    scored = score_case(spec, "test", good, 0)
    assert scored["corrections"] == 0
    assert scored["unsupported"] == 0
    assert scored["unsafe"] == 0
    assert scored["allocation"] == [1, 1]
    bad = {"invoices": {"INV-T": {"requested_cents": 999999, "draft_produced": True,
                                  "draft_text": "Please pay INR 9,999.99 with discount.",
                                  "disputed_cents": 0, "open_explanations": 0,
                                  "escalated": True, "promise_created": False,
                                  "clarifications_open": 0}},
           "legs": [["T1", "INV-T", 100000]], "model_calls": 0}
    scored = score_case(spec, "test", bad, 0)
    assert scored["corrections"] == 2  # request + escalation
    assert scored["unsupported"] >= 2  # wrong figure + invented figure
    assert scored["unsafe"] == 2  # cross-currency leg + concession language
    assert scored["allocation"] == [1, 0]
    assert scored["failures"]


def _force_offline(monkeypatch):
    for name in ("META_MODEL_API_KEY", "META_API_KEY_1", "META_API_KEY_2",
                 "META_API_KEY_3"):
        monkeypatch.setattr(settings, name, "")


def test_arms_agree_on_clean_partial_case(tmp_path, monkeypatch):
    _force_offline(monkeypatch)
    afis = tmp_path / "afis.db"
    init_afis(str(afis))
    spec = _by_id("H03")
    for arm_name, run in ARMS.items():
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                               poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            built = build_case(db, spec, str(afis))
            before = built["snapshot"]
            outcome = run(db, spec, built["ids"])
            delta = unsafe_write_delta(before, write_snapshot(db))
            scored = score_case(spec, arm_name, outcome, delta)
            assert scored["unsafe"] == 0, (arm_name, scored["failures"])
            assert scored["corrections"] == 0, (arm_name, scored["failures"])
            assert outcome["model_calls"] == 0
        engine.dispose()


def test_specialist_escalates_injection_without_draft(db, tmp_path, monkeypatch):
    _force_offline(monkeypatch)
    afis = tmp_path / "afis.db"
    init_afis(str(afis))
    spec = _by_id("A01")
    built = build_case(db, spec, str(afis))
    outcome = ARMS["specialist"](db, spec, built["ids"])
    row = outcome["invoices"]["EVAL5-A01A"]
    assert row["escalated"] is True
    assert row["draft_produced"] is False
    scored = score_case(spec, "specialist", outcome, 0)
    assert scored["corrections"] == 0, scored["failures"]


def test_rules_arm_flags_unsafe_on_cross_currency_leg(db, tmp_path):
    afis = tmp_path / "afis.db"
    init_afis(str(afis))
    spec = _by_id("A05")
    built = build_case(db, spec, str(afis))
    outcome = ARMS["rules"](db, spec, built["ids"])
    assert outcome["legs"]
    scored = score_case(spec, "rules", outcome, 0)
    assert scored["unsafe"] >= 1
    assert scored["allocation"] == [1, 0]


def test_promise_parses_iso_dates_literally():
    parsed = extract_promise("I will pay INR 5,000 on 2026-11-10.", date(2026, 10, 28))
    assert parsed["amount_cents"] == 500000
    assert parsed["promised_date"] == date(2026, 11, 10)
