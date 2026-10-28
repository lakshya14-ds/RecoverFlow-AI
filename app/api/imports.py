"""Provider-neutral retailer receivable import for the assisted release."""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database.db_manager import get_db
from app.services import import_adapter

router = APIRouter(prefix="/imports", tags=["Imports"])
REQUIRED = {"external_id", "invoice_number", "customer_name", "issue_date", "due_date", "amount"}


class PreviewInput(BaseModel):
    profile: str = "generic_csv"
    rows: list[dict] = Field(min_length=1, max_length=500)


class ConfirmInput(BaseModel):
    profile: str = "generic_csv"
    source_system: str = Field(min_length=1, max_length=50)
    rows: list[dict] = Field(min_length=1, max_length=500)


@router.get("/profiles")
def list_profiles(identity: Identity = Depends(get_identity)):
    _ = identity
    return import_adapter.profiles()


@router.post("/preview")
def preview(payload: PreviewInput, identity: Identity = Depends(get_identity)):
    _ = identity
    try:
        return import_adapter.preview_import(payload.rows, payload.profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/confirm", status_code=201)
def confirm(payload: ConfirmInput, db: Session = Depends(get_db),
            identity: Identity = Depends(get_identity)):
    try:
        result = import_adapter.confirm_import(
            db, identity.tenant_id, identity.actor, payload.rows,
            payload.source_system.strip(), payload.profile)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate external receivable ID") from exc
    db.commit()
    return result


@router.post("/receivables/csv")
async def import_receivables(request: Request, db: Session = Depends(get_db),
                             identity: Identity = Depends(get_identity)):
    if request.headers.get("content-type", "").split(";")[0] not in ("text/csv", "application/csv"):
        raise HTTPException(status_code=415, detail="Send a UTF-8 CSV file")
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > 2 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV is too large")
        chunks.append(chunk)
    try:
        reader = csv.DictReader(io.StringIO(b"".join(chunks).decode("utf-8-sig")))
        if not REQUIRED.issubset(reader.fieldnames or []):
            raise ValueError("CSV must include: " + ", ".join(sorted(REQUIRED)))
        rows = list(reader)
        if not rows or len(rows) > 500:
            raise ValueError("CSV must contain between 1 and 500 records")
        result = import_adapter.confirm_import(
            db, identity.tenant_id, identity.actor, rows, "csv",
            currency_default="USD", source="retail_import")
        db.commit()
        return result
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate external receivable ID") from exc
