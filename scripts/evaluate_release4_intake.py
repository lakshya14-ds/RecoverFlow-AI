"""Run ten real upload/pipeline trials on synthetic documents without Meta."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database.db_manager import Base, get_db
from app.main import app
from app.services import intake_pipeline
from scripts.synthetic_documents import synthetic_pdf, synthetic_image


def run_intake_evaluation() -> dict:
    header = b"external_id,invoice_number,customer_name,issue_date,due_date,amount,currency\n"
    fixtures = [
        ("good-one.csv", "text/csv", header + b"eval-1,EVAL-CSV-1,Synthetic Retailer,2026-01-01,2026-02-01,80000.00,INR\n", True),
        ("good-two.csv", "text/csv", header + b"eval-2,EVAL-CSV-2,Synthetic Retailer,2026-01-01,2026-02-01,90000.00,INR\n", True),
        ("bad-columns.csv", "text/csv", b"invoice_number,total\nBAD-1,100.00\n", False),
        *[(f"invoice-{index}.pdf", "application/pdf",
           synthetic_pdf(number=f"EVAL-PDF-{index}", total="240000.00"), True)
          for index in (2, 3, 4)],
        ("bad-total.pdf", "application/pdf",
         synthetic_pdf(number="EVAL-BAD", total="240000.00", line_amount="230000.00"), False),
        ("unmatched-receipt.pdf", "application/pdf",
         synthetic_pdf(kind="receipt", reference="UNKNOWN", total="150000.00"), False),
        ("receipt.png", "image/png", synthetic_image(), False),
        ("receipt.jpg", "image/jpeg", synthetic_image("JPEG"), False),
    ]
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    old_factory = intake_pipeline.SessionLocal
    keys = {name: getattr(settings, name) for name in (
        "META_MODEL_API_KEY", "META_API_KEY_1", "META_API_KEY_2", "META_API_KEY_3",
        "RECOVERFLOW_API_KEY", "RECOVERFLOW_API_KEYS_JSON", "BASE_DIR")}
    rows = []
    try:
        with TemporaryDirectory() as temp:
            settings.BASE_DIR = Path(temp)
            settings.RECOVERFLOW_API_KEY = "synthetic-evaluation"
            settings.RECOVERFLOW_API_KEYS_JSON = ""
            for name in ("META_MODEL_API_KEY", "META_API_KEY_1", "META_API_KEY_2", "META_API_KEY_3"):
                setattr(settings, name, "")
            intake_pipeline.SessionLocal = factory
            client = TestClient(app)
            for filename, mime, data, expected in fixtures:
                response = client.post("/api/v1/intake/uploads", content=data, headers={
                    "X-RECOVERFLOW-API-KEY": "synthetic-evaluation",
                    "X-Filename": filename, "Content-Type": mime})
                if response.status_code != 202:
                    rows.append({"file": filename, "expected_review": expected,
                                 "reached_review": False, "reason": f"upload HTTP {response.status_code}"})
                    continue
                intake_pipeline.process_one()
                status = client.get(f"/api/v1/intake/uploads/{response.json()['id']}",
                    headers={"X-RECOVERFLOW-API-KEY": "synthetic-evaluation"}).json()
                rows.append({"file": filename, "expected_review": expected,
                             "reached_review": status["status"] == "ready_for_review",
                             "reason": status.get("error") or "accepted"})
    finally:
        app.dependency_overrides.clear()
        intake_pipeline.SessionLocal = old_factory
        for name, value in keys.items():
            setattr(settings, name, value)
        engine.dispose()
    correct = sum(row["expected_review"] == row["reached_review"] for row in rows)
    reached = sum(row["reached_review"] for row in rows)
    return {"total": len(rows), "correct_triage": correct,
            "reached_review_without_data_entry": reached, "rows": rows}


if __name__ == "__main__":
    result = run_intake_evaluation()
    print(f"Correct triage: {result['correct_triage']}/{result['total']}")
    print(f"Reached Review without human data entry: {result['reached_review_without_data_entry']}/{result['total']}")
    for row in result["rows"]:
        print(f"{row['file']}: {row['reached_review']} ({row['reason']})")
