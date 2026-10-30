"""Business identity: counterparties, branches, external IDs, merges."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import Identity, get_identity, require_admin
from app.database import models
from app.database.db_manager import get_db
from app.services import counterparties

router = APIRouter(prefix="/counterparties", tags=["Counterparties"])


class CounterpartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: Literal["customer", "vendor"]
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=1000)
    tax_id: str | None = Field(default=None, max_length=60)
    gstin: str | None = Field(default=None, max_length=15)
    legal_name: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    billing_address: str | None = Field(default=None, max_length=1000)
    shipping_address: str | None = Field(default=None, max_length=1000)


class CounterpartyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: Literal["customer", "vendor"] | None = None
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=1000)
    tax_id: str | None = Field(default=None, max_length=60)
    gstin: str | None = Field(default=None, max_length=15)
    legal_name: str | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, max_length=200)
    billing_address: str | None = Field(default=None, max_length=1000)
    shipping_address: str | None = Field(default=None, max_length=1000)


class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    gstin: str | None = Field(default=None, max_length=15)
    billing_address: str | None = Field(default=None, max_length=1000)
    shipping_address: str | None = Field(default=None, max_length=1000)


class ExternalIdCreate(BaseModel):
    system: str = Field(min_length=1, max_length=40)
    external_id: str = Field(min_length=1, max_length=200)


class MergeInput(BaseModel):
    winner_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=500)


class BootstrapInput(BaseModel):
    invoice_type: Literal["AR", "AP"] = "AR"


def _party(db: Session, party_id: int, identity: Identity) -> models.Counterparty:
    row = db.get(models.Counterparty, party_id)
    if not row or row.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Counterparty not found")
    return row


def _view(row: models.Counterparty) -> dict:
    return {"id": row.id, "name": row.name, "type": row.type,
            "display_name": counterparties.display_name_of(row),
            "legal_name": row.legal_name, "email": row.email,
            "phone": row.phone, "address": row.address, "tax_id": row.tax_id,
            "gstin": row.gstin, "billing_address": row.billing_address,
            "shipping_address": row.shipping_address, "status": row.status,
            "merged_into_id": row.merged_into_id}


@router.post("", status_code=201)
def create_party(payload: CounterpartyCreate, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    try:
        row = counterparties.create_counterparty(
            db, identity.tenant_id, identity.actor, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Counterparty already exists for this tax ID or GSTIN") from exc
    db.commit()
    return _view(row)


@router.get("")
def list_parties(status: str | None = None, db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    query = db.query(models.Counterparty).filter_by(
        tenant_id=identity.tenant_id)
    if status:
        query = query.filter_by(status=status)
    return [_view(row) for row in query.order_by(
        models.Counterparty.name).limit(200).all()]


@router.get("/{party_id}")
def get_party(party_id: int, db: Session = Depends(get_db),
              identity: Identity = Depends(get_identity)):
    row = _party(db, party_id, identity)
    view = _view(row)
    view["branches"] = [{
        "id": branch.id, "name": branch.name, "gstin": branch.gstin,
        "billing_address": branch.billing_address,
        "shipping_address": branch.shipping_address} for branch in
        db.query(models.CounterpartyBranch).filter_by(
            tenant_id=identity.tenant_id, counterparty_id=row.id).order_by(
            models.CounterpartyBranch.name).all()]
    view["external_ids"] = [{
        "id": item.id, "system": item.system,
        "external_id": item.external_id} for item in
        db.query(models.CounterpartyExternalId).filter_by(
            tenant_id=identity.tenant_id, counterparty_id=row.id).order_by(
            models.CounterpartyExternalId.system).all()]
    return view


@router.patch("/{party_id}")
def update_party(party_id: int, payload: CounterpartyUpdate,
                 db: Session = Depends(get_db),
                 identity: Identity = Depends(get_identity)):
    row = _party(db, party_id, identity)
    if row.status == "merged":
        raise HTTPException(status_code=409,
                            detail="Merged counterparties are read-only")
    try:
        counterparties.update_counterparty(
            db, row, identity.actor,
            **{key: value for key, value in payload.model_dump().items()
               if value is not None})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Counterparty already exists for this tax ID or GSTIN") from exc
    db.commit()
    return _view(row)


@router.post("/{party_id}/branches", status_code=201)
def add_branch(party_id: int, payload: BranchCreate,
               db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    row = _party(db, party_id, identity)
    if row.status == "merged":
        raise HTTPException(status_code=409,
                            detail="Merged counterparties are read-only")
    try:
        gstin = counterparties.validate_gstin(payload.gstin)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    branch = models.CounterpartyBranch(
        tenant_id=identity.tenant_id, counterparty_id=row.id,
        name=payload.name.strip(), gstin=gstin,
        billing_address=payload.billing_address,
        shipping_address=payload.shipping_address,
        created_by=identity.actor)
    db.add(branch)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409,
                            detail="Branch name already exists") from exc
    db.commit()
    return {"id": branch.id, "name": branch.name, "gstin": branch.gstin}


@router.delete("/branches/{branch_id}")
def remove_branch(branch_id: int, db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    branch = db.get(models.CounterpartyBranch, branch_id)
    if not branch or branch.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="Branch not found")
    db.delete(branch)
    db.commit()
    return {"status": "removed", "id": branch_id}


@router.post("/{party_id}/external-ids", status_code=201)
def add_external_id(party_id: int, payload: ExternalIdCreate,
                    db: Session = Depends(get_db),
                    identity: Identity = Depends(get_identity)):
    row = _party(db, party_id, identity)
    if row.status == "merged":
        raise HTTPException(status_code=409,
                            detail="Merged counterparties are read-only")
    try:
        system = counterparties.validate_system(payload.system)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    item = models.CounterpartyExternalId(
        tenant_id=identity.tenant_id, counterparty_id=row.id, system=system,
        external_id=payload.external_id.strip(), created_by=identity.actor)
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="External ID already linked in this business") from exc
    db.commit()
    return {"id": item.id, "system": item.system,
            "external_id": item.external_id}


@router.delete("/external-ids/{item_id}")
def remove_external_id(item_id: int, db: Session = Depends(get_db),
                       identity: Identity = Depends(get_identity)):
    item = db.get(models.CounterpartyExternalId, item_id)
    if not item or item.tenant_id != identity.tenant_id:
        raise HTTPException(status_code=404, detail="External ID not found")
    db.delete(item)
    db.commit()
    return {"status": "removed", "id": item_id}


@router.get("/{party_id}/duplicates")
def duplicates(party_id: int, db: Session = Depends(get_db),
               identity: Identity = Depends(get_identity)):
    row = _party(db, party_id, identity)
    return counterparties.suggest_duplicates(db, identity.tenant_id, row)


@router.post("/{party_id}/merge-preview")
def preview_merge(party_id: int, payload: MergeInput,
                  db: Session = Depends(get_db),
                  identity: Identity = Depends(get_identity)):
    try:
        return counterparties.merge_preview(db, identity.tenant_id, party_id,
                                            payload.winner_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{party_id}/merge")
def merge_party(party_id: int, payload: MergeInput,
                db: Session = Depends(get_db),
                identity: Identity = Depends(require_admin)):
    try:
        result = counterparties.merge_counterparties(
            db, identity.tenant_id, party_id, payload.winner_id,
            payload.reason.strip(), identity.actor)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/bootstrap")
def bootstrap(payload: BootstrapInput, db: Session = Depends(get_db),
              identity: Identity = Depends(require_admin)):
    result = counterparties.bootstrap_from_invoices(
        db, identity.tenant_id, identity.actor,
        invoice_type=payload.invoice_type)
    db.commit()
    return result
