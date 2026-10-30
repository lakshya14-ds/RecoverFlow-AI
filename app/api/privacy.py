"""Admin-only subject-request API (access/export/correction/deletion)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import Identity, require_admin
from app.database.db_manager import get_db
from app.services import privacy

router = APIRouter(prefix="/privacy", tags=["Privacy"])


class PrivacyRequestCreate(BaseModel):
    kind: str = ""
    subject_type: str = ""
    subject_ref: int = 0
    details: dict = {}


class RejectBody(BaseModel):
    reason: str = ""


@router.post("/requests")
def create_request(body: PrivacyRequestCreate,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(require_admin)):
    try:
        row = privacy.create_request(db, identity.tenant_id, body.kind,
                                     body.subject_type, body.subject_ref,
                                     body.details, identity.actor)
        db.commit()
    except privacy.PrivacyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return privacy.request_view(row)


@router.get("/requests")
def list_requests(status: str = "",
                  db: Session = Depends(get_db),
                  identity: Identity = Depends(require_admin)):
    return [privacy.request_view(r)
            for r in privacy.list_requests(db, identity.tenant_id, status)]


@router.get("/requests/{request_id}")
def get_request(request_id: int,
                db: Session = Depends(get_db),
                identity: Identity = Depends(require_admin)):
    try:
        row = privacy.get_request(db, identity.tenant_id, request_id)
    except privacy.PrivacyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return privacy.request_view(row)


@router.post("/requests/{request_id}/review")
def mark_review(request_id: int,
                db: Session = Depends(get_db),
                identity: Identity = Depends(require_admin)):
    try:
        row = privacy.mark_in_review(
            db, privacy.get_request(db, identity.tenant_id, request_id),
            identity.actor)
        db.commit()
    except privacy.PrivacyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return privacy.request_view(row)


@router.post("/requests/{request_id}/fulfill")
def fulfill_request(request_id: int,
                    db: Session = Depends(get_db),
                    identity: Identity = Depends(require_admin)):
    try:
        row = privacy.get_request(db, identity.tenant_id, request_id)
        result = privacy.fulfill_request(db, row, identity.actor)
        db.commit()
    except privacy.PrivacyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return {"request": privacy.request_view(row), "result": result}


@router.post("/requests/{request_id}/reject")
def reject_request(request_id: int, body: RejectBody,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(require_admin)):
    try:
        row = privacy.reject_request(
            db, privacy.get_request(db, identity.tenant_id, request_id),
            identity.actor, body.reason)
        db.commit()
    except privacy.PrivacyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return privacy.request_view(row)


@router.get("/deletion-check")
def deletion_check(subject_type: str = "", subject_ref: int = 0,
                   db: Session = Depends(get_db),
                   identity: Identity = Depends(require_admin)):
    """Preview deletion blocks without changing anything."""
    try:
        blocks = privacy.check_deletion(db, identity.tenant_id, subject_type,
                                        subject_ref, identity.actor)
    except privacy.PrivacyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"subject_type": subject_type, "subject_ref": subject_ref,
            "blocked": bool(blocks), "blocks": blocks}
