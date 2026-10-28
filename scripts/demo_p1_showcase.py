"""One-command P1 multi-agent showcase: evidence, Hinglish claim, conflict,
held payment, clarification, invalidation, approval, SIMULATED payment.

Offline for beat mapping: scripts/demo_hero.py stays the regression demo and is
not modified. This script prints the story and asserts each beat on an isolated
in-memory database with model access forced off. It writes no docs or frontend
files.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import models
from app.database.db_manager import Base, get_db
from app.main import app
from app.services import supervisor
from app.services.allocation import propose as propose_allocation
from app.services.case_lifecycle import fingerprint
from app.services.investigation import investigate
from app.services.multilingual import classify_multilingual, detect_language
from app.services.receivables import post_entry, split_balance


def _ok(response, codes=(200, 201, 202)):
    assert response.status_code in codes, f"HTTP {response.status_code}: {response.text}"
    return response.json()


def _line(sku, description, quantity, unit_price):
    return {"sku": sku, "description": description, "quantity": str(quantity),
            "unit_price": str(unit_price),
            "amount": str(Decimal(quantity) * Decimal(unit_price))}


def _upload(db, tenant, doc_id, kind, number, payload):
    db.add(models.IntakeUpload(
        id=doc_id, tenant_id=tenant, actor="showcase", filename=doc_id + ".pdf",
        mime_type="application/pdf",
        source_path=f"{number}-invoice.pdf" if kind == "invoice" else doc_id + ".pdf",
        size_bytes=10, extraction_json=json.dumps(
            {"document_type": kind, "invoice_reference": number, **payload})))
    db.flush()


def _sourced(db, tenant, invoice):
    from app.services.receivables import split_balance as _split
    db.add(models.CaseEvidence(
        tenant_id=tenant, invoice_id=invoice.id, claim_type="invoice_total",
        title="Invoice", description="Showcase fixture", source_type="staff_record",
        source_reference=f"showcase-{invoice.invoice_number}.pdf",
        amount_cents=invoice.face_amount_cents, verified=True,
        trust_state="verified", decided_by="showcase",
        decision_reason="Seeded fixture", currency=invoice.currency))
    received_cents = _split(db, invoice)["received_cents"]
    if received_cents > 0:
        db.add(models.CaseEvidence(
            tenant_id=tenant, invoice_id=invoice.id, claim_type="received_payment",
            title="Receipt", description="Showcase fixture", source_type="staff_record",
            source_reference=f"showcase-{invoice.invoice_number}-receipt.pdf",
            amount_cents=received_cents, verified=True,
            trust_state="verified", decided_by="showcase",
            decision_reason="Seeded fixture", currency=invoice.currency))
    db.commit()


def _chain(db, invoice):
    for _ in range(12):
        result = supervisor.reassess(db, invoice, "showcase", actor="showcase")
        db.commit()
        if result["outcome"] in ("steady", "complete", "escalated", "ignored", "failed"):
            return result["outcome"]
        if result.get("task_id"):
            supervisor.run_task(db, result["task_id"], actor="showcase")
            db.commit()
    return "unfinished"


def _communication_result(db, tenant, invoice_id):
    tasks = db.query(models.SupervisorTask).filter_by(
        tenant_id=tenant, invoice_id=invoice_id, kind="communication",
        status="done").order_by(models.SupervisorTask.id.desc()).all()
    if not tasks:
        return None
    return json.loads(tasks[0].result_json or "{}").get("findings", {})


def run_showcase():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    tenant = "local"

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    saved = {name: getattr(settings, name) for name in (
        "BASE_DIR", "RECOVERFLOW_API_KEY", "RECOVERFLOW_API_KEYS_JSON",
        "AFIS_DB_PATH", "META_MODEL_API_KEY", "META_API_KEY_1",
        "META_API_KEY_2", "META_API_KEY_3")}
    try:
        with TemporaryDirectory() as temp:
            settings.BASE_DIR = Path(temp)
            settings.RECOVERFLOW_API_KEY = "showcase-key"
            settings.RECOVERFLOW_API_KEYS_JSON = ""
            for name in ("META_MODEL_API_KEY", "META_API_KEY_1", "META_API_KEY_2",
                         "META_API_KEY_3"):
                setattr(settings, name, "")
            afis_path = str(Path(temp) / "showcase-afis.db")
            settings.AFIS_DB_PATH = afis_path
            connection = sqlite3.connect(afis_path)
            connection.execute("CREATE TABLE transactions (id TEXT PRIMARY KEY, date TEXT,"
                               " description TEXT, amount REAL, category TEXT)")
            connection.commit()
            connection.close()
            client = TestClient(app)
            auth = {"X-RECOVERFLOW-API-KEY": "showcase-key"}

            print("P1 showcase: invoice, PO, and delivery evidence on a synthetic case")
            with factory() as db:
                first = models.Invoice(
                    tenant_id=tenant, invoice_number="SHOW-001", invoice_type="AR",
                    counterparty_name="Showcase Distributors",
                    issue_date=date(2026, 9, 1), due_date=date(2026, 10, 15),
                    amount=Decimal("100000"), total_amount=Decimal("100000"),
                    face_amount_cents=10000000, disputed_cents=0, currency="INR",
                    source_path="SHOW-001-invoice.pdf")
                second = models.Invoice(
                    tenant_id=tenant, invoice_number="SHOW-002", invoice_type="AR",
                    counterparty_name="Showcase Distributors",
                    issue_date=date(2026, 9, 1), due_date=date(2026, 10, 15),
                    amount=Decimal("60000"), total_amount=Decimal("60000"),
                    face_amount_cents=6000000, disputed_cents=0, currency="INR",
                    source_path="SHOW-002-invoice.pdf")
                db.add_all([first, second])
                db.flush()
                case_id, sibling_id = first.id, second.id
                post_entry(db, first, kind="payment", amount=Decimal("40000"),
                           source="eval_verified", reference="SHOW-RCPT-1",
                           actor="showcase")
                lines = [_line("SHOW-WDG", "Showcase valve sets", 50, "2000")]
                _upload(db, tenant, "show-invoice", "invoice", "SHOW-001",
                        {"invoice_number": "SHOW-001", "line_items": lines,
                         "currency": "INR"})
                _upload(db, tenant, "show-po", "purchase_order", "SHOW-001",
                        {"line_items": lines, "currency": "INR"})
                delivered = [_line("SHOW-WDG", "Showcase valve sets", 48, "2000")]
                _upload(db, tenant, "show-delivery", "delivery_note", "SHOW-001",
                        {"line_items": delivered, "currency": "INR"})
                _sourced(db, tenant, first)
                _sourced(db, tenant, second)
            print("Case SHOW-001: total 100,000; received 40,000; delivery short 2 units")

            reply = _ok(client.post(f"/api/v1/cases/{case_id}/replies", headers=auth,
                json={"category": "dispute",
                      "body": "2 carton short aaye the, baaki payment next week kar dunga"}))
            assert reply["contact_suppressed"] is True
            language = detect_language("2 carton short aaye the, baaki payment next week kar dunga")
            intent = classify_multilingual("2 carton short aaye the, baaki payment next week kar dunga")
            assert language == "hinglish"
            print(f"Hinglish claim recorded (language={language}, intent={intent}); contact paused")

            _ok(client.post(f"/api/v1/cases/{case_id}/resume", headers=auth,
                            json={"reason": "Showcase: staff triaged a genuine claim"}))
            with factory() as db:
                invoice = db.get(models.Invoice, case_id)
                assert _chain(db, invoice) == "steady"
                findings = _communication_result(db, tenant, case_id)
                assert findings and findings["message"]["requested_cents"] == 5600000
                assert findings["message"]["language"] == "hinglish"
                assert "56,000.00" in findings["prose"] and "4,000.00" in findings["prose"]
                draft_id = findings["proposal_id"]
            print(f"Draft {draft_id}: Hinglish request for undisputed INR 56,000.00 only")

            with factory() as db:
                _upload(db, tenant, "show-conflict", "message", "SHOW-001",
                        {"text": "5 units short on this invoice"})
                invoice = db.get(models.Invoice, case_id)
                try:
                    investigate(db, invoice)
                    raise AssertionError("conflict should hold the case")
                except ValueError as exc:
                    db.commit()
                    print(f"Conflicting explanations held the case: {exc}")
                explanations = db.query(models.CompetingExplanation).filter_by(
                    tenant_id=tenant, invoice_id=case_id, status="open").all()
                assert len(explanations) == 1
                hyps = json.loads(explanations[0].hypotheses_json)
                assert sorted(h["amount_cents"] for h in hyps) == [400000, 1000000]
                explanation_id = explanations[0].id
            print("Sources disagree (400,000 vs 1,000,000 cents); no amount was invented")

            with factory() as db:
                connection = sqlite3.connect(afis_path)
                connection.execute("INSERT INTO transactions VALUES (?,?,?,?,?)",
                                   ("SHOW-T1", "2026-10-18", "NEFT transfer no reference",
                                    60000.00, "bank"))
                connection.commit()
                connection.close()
                proposal, _ = propose_allocation(db, tenant, "SHOW-T1", "showcase")
                db.commit()
                assert proposal.status == "ambiguous"
                legs = db.query(models.AllocationLeg).filter_by(
                    proposal_id=proposal.id).all()
                assert legs == []
                candidates = json.loads(proposal.candidates_json)
                assert any("repeated amount" in " ".join(c["uncertainty"]) for c in candidates)
            print("Ambiguous INR 60,000.00 transfer held for staff (repeated amount, no legs)")

            with factory() as db:
                _upload(db, tenant, "show-damage", "message", "SHOW-001",
                        {"text": "2 units of show-wdg arrived damaged"})
                invoice = db.get(models.Invoice, case_id)
                try:
                    investigate(db, invoice)
                except ValueError:
                    db.commit()
                task = db.query(models.ClarificationTask).filter_by(
                    tenant_id=tenant, invoice_id=case_id, status="open",
                    owner="customer").one()
                assert "damage" in task.title.casefold()
            print(f"Targeted clarification for the customer: {task.title}")

            versions = _ok(client.get(f"/api/v1/agent/proposals/{draft_id}/versions",
                                      headers=auth))
            stale = client.post(f"/api/v1/agent/proposals/{draft_id}/approve", headers=auth,
                                json={"version_number": versions[0]["version_number"],
                                      "version_hash": versions[0]["version_hash"]})
            assert stale.status_code == 409, stale.text
            print("New evidence invalidated the old draft: exact-version approval blocked (409)")

            with factory() as db:
                row = db.get(models.CompetingExplanation, explanation_id)
                hyps = json.loads(row.hypotheses_json)
                winner = next(h for h in hyps if h["amount_cents"] == 400000)
            resolved = _ok(client.post(
                f"/api/v1/cases/{case_id}/explanations/{explanation_id}/resolve",
                headers=auth, json={"hypothesis": winner["key"],
                                    "reason": "Signed delivery note confirms 48 units"}))
            assert resolved["resolved_hypothesis"] == winner["key"]
            with factory() as db:
                evidence_id = db.query(models.CaseEvidence).filter_by(
                    tenant_id=tenant, invoice_id=case_id,
                    claim_type="invoice_total").one().id
            reviewed = _ok(client.post(f"/api/v1/cases/{case_id}/dispute-review",
                headers=auth, json={"disputed_amount": "4000.00",
                                    "evidence_id": evidence_id,
                                    "reason": "Two units short per signed delivery note"}))
            assert reviewed["investigation_hold"] is False
            print("Staff resolved the conflict and set the dispute at INR 4,000.00")

            with factory() as db:
                invoice = db.get(models.Invoice, case_id)
                assert _chain(db, invoice) == "steady"
                findings = _communication_result(db, tenant, case_id)
                assert findings["message"]["requested_cents"] == 5600000
                fresh_id = findings["proposal_id"]
                assert fresh_id != draft_id
            versions = _ok(client.get(f"/api/v1/agent/proposals/{fresh_id}/versions",
                                      headers=auth))
            body = versions[-1]["body"] + " Please share the UTR once paid."
            edited = _ok(client.post(f"/api/v1/agent/proposals/{fresh_id}/edit-draft",
                headers=auth, json={"body": body, "change_reason": "Staff courtesy edit"}))
            approval = _ok(client.post(f"/api/v1/agent/proposals/{fresh_id}/approve",
                headers=auth, json={"version_number": edited["version_number"],
                                    "version_hash": edited["version_hash"]}))
            assert approval["version_hash"] == edited["version_hash"]
            print(f"Staff approved exact draft v{edited['version_number']} "
                  f"hash {edited['version_hash'][:12]}")

            with factory() as db:
                invoice = db.get(models.Invoice, case_id)
                post_entry(db, invoice, kind="payment", amount=Decimal("56000"),
                           source="razorpay_simulated", reference="SIMULATED-SHOW-56000",
                           actor="simulated_payment_event")
                db.commit()
                split = split_balance(db, invoice)
                assert invoice.status == "PARTIALLY_RESOLVED"
                assert split["outstanding"] == Decimal("4000")
                assert split["disputed"] == Decimal("4000")
                held = db.query(models.AllocationProposal).filter_by(
                    tenant_id=tenant, status="ambiguous").count()
            print("SIMULATED verified payment: 56,000 INR; PARTIALLY_RESOLVED; "
                  "4,000 disputed still open; ambiguous transfer still held; "
                  "damage clarification still open")
            print(f"Showcase passed. Ambiguous proposals awaiting staff: {held}.")
    finally:
        app.dependency_overrides.clear()
        for name, value in saved.items():
            setattr(settings, name, value)
        engine.dispose()


if __name__ == "__main__":
    run_showcase()
