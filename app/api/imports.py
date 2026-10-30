"""Provider-neutral retailer receivable import for the assisted release."""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity
from app.database import models
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


class RunInput(BaseModel):
    profile: str = "generic_csv"
    source_system: str = Field(min_length=1, max_length=50)
    rows: list[dict] = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(default="", max_length=120)


class ResolveInput(BaseModel):
    resolution: str = Field(default="keep_existing", max_length=50)


def _run(db: Session, run_id: int, identity: Identity):
    run = db.get(models.ImportRun, run_id)
    if not run or run.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Import run not found")
    return run


@router.post("/runs", status_code=201)
def start_run(payload: RunInput, db: Session = Depends(get_db),
              identity: Identity = Depends(get_identity)):
    try:
        run, duplicate = import_adapter.start_run(
            db, identity.tenant_id, identity.actor, payload.rows,
            payload.source_system.strip(), payload.profile,
            payload.idempotency_key.strip())
    except ValueError as exc:
        db.rollback()
        if "different payload" in str(exc):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    view = import_adapter.run_view(db, run)
    view["duplicate"] = duplicate
    return view


@router.get("/runs")
def list_runs(db: Session = Depends(get_db),
              identity: Identity = Depends(get_identity)):
    runs = db.query(models.ImportRun).filter_by(
        tenant_id=identity.tenant_id).order_by(models.ImportRun.id).all()
    return [import_adapter.run_view(db, run) for run in runs]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db),
            identity: Identity = Depends(get_identity)):
    return import_adapter.run_view(db, _run(db, run_id, identity))


@router.post("/runs/{run_id}/confirm")
def confirm_run(run_id: int, db: Session = Depends(get_db),
                identity: Identity = Depends(get_identity)):
    run = _run(db, run_id, identity)
    try:
        confirmed = import_adapter.confirm_run(db, run.id, identity.actor)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Duplicate external receivable ID") from exc
    db.commit()
    return import_adapter.run_view(db, confirmed)


@router.get("/conflicts")
def list_conflicts(status: str = "open", run_id: int | None = None,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(get_identity)):
    if status not in ("open", "resolved"):
        raise HTTPException(status_code=422, detail="Status must be open or resolved")
    query = db.query(models.ImportConflict).filter_by(
        tenant_id=identity.tenant_id, status=status)
    if run_id is not None:
        _run(db, run_id, identity)
        query = query.filter_by(run_id=run_id)
    return [{"id": item.id, "run_id": item.run_id,
             "source_record_id": item.source_record_id,
             "row_number": item.row_number, "reason": item.reason,
             "existing_invoice_id": item.existing_invoice_id,
             "status": item.status, "resolution": item.resolution,
             "resolved_by": item.resolved_by}
            for item in query.order_by(models.ImportConflict.id).all()]


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(conflict_id: int, payload: ResolveInput,
                     db: Session = Depends(get_db),
                     identity: Identity = Depends(get_identity)):
    conflict = db.get(models.ImportConflict, conflict_id)
    if not conflict or conflict.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Import conflict not found")
    try:
        resolved = import_adapter.resolve_conflict(
            db, conflict.id, identity.actor, payload.resolution.strip())
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    return {"id": resolved.id, "status": resolved.status,
            "resolution": resolved.resolution}
