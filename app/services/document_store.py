"""Private evidence document store. Bytes live outside the web root.

One validation and storage path for staff intake uploads and customer portal
evidence. Every file gets a random stored name, a SHA-256 hash, a scan
status, and an access log. Reads are authorized per call; quarantined or
deleted rows never serve bytes.
"""
import csv
import hashlib
import io
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings
from app.database import models

PORTAL_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}
STAFF_SUFFIXES = PORTAL_SUFFIXES | {".csv"}

DANGEROUS_SUFFIXES = {".exe", ".bat", ".cmd", ".com", ".msi", ".js", ".vbs",
                      ".ps1", ".scr", ".reg", ".dll", ".app", ".action",
                      ".zip", ".rar", ".7z", ".tar", ".gz", ".html", ".htm",
                      ".svg", ".xml"}

SUFFIX_MIMES = {
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


class DocumentRejected(ValueError):
    """Raised when an upload fails policy. Message is safe to show."""


def validate_content(data: bytes, suffix: str, filename: str, *, portal: bool) -> str:
    """Policy scan: type allowlist, magic bytes, dangerous names. Returns MIME."""
    allowed = PORTAL_SUFFIXES if portal else STAFF_SUFFIXES
    if suffix not in allowed:
        raise DocumentRejected("File type is not accepted as evidence")
    extra = [part.lower() for part in Path(filename).suffixes[:-1]]
    if any(part in DANGEROUS_SUFFIXES for part in extra):
        raise DocumentRejected("Filenames must not hide executable types")
    if not data:
        raise DocumentRejected("Empty upload")
    if suffix == ".pdf" and not data.startswith(b"%PDF-"):
        raise DocumentRejected("Invalid PDF signature")
    if suffix in (".jpg", ".jpeg") and not data.startswith(b"\xff\xd8\xff"):
        raise DocumentRejected("Invalid JPEG signature")
    if suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DocumentRejected("Invalid PNG signature")
    if suffix == ".csv":
        try:
            decoded = data.decode("utf-8-sig")
            if "\x00" in decoded:
                raise ValueError("NUL byte")
            headers = next(csv.reader(io.StringIO(decoded)), [])
            if len(headers) < 2 or any(not cell.strip() for cell in headers):
                raise ValueError("CSV header is missing")
        except (UnicodeDecodeError, csv.Error, ValueError) as exc:
            raise DocumentRejected("Invalid UTF-8 CSV") from exc
    return SUFFIX_MIMES[suffix]


def storage_root() -> Path:
    root = Path(settings.DOCUMENT_STORAGE_PATH)
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def document_path(doc) -> Path:
    root = storage_root()
    path = (root / doc.tenant_id / doc.stored_name).resolve()
    if root not in path.parents or not path.is_file():
        raise DocumentRejected("Stored file is missing")
    return path


def log_access(db, doc, actor, action, ip=None):
    db.add(models.DocumentAccessLog(
        tenant_id=doc.tenant_id, doc_id=doc.id, actor=actor,
        action=action, ip=ip))


def store_document(db, *, tenant_id, invoice_id, origin, filename, data,
                   uploaded_by, portal_token_id=None, portal=False):
    """Validate, hash, and persist one evidence file. Caller commits."""
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise DocumentRejected("File exceeds upload size cap")
    suffix = Path(filename).suffix.lower()
    mime = validate_content(data, suffix, filename, portal=portal)
    digest = hashlib.sha256(data).hexdigest()
    doc_id = uuid.uuid4().hex
    stored_name = doc_id + suffix
    tenant_dir = storage_root() / tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    (tenant_dir / stored_name).write_bytes(data)
    now = datetime.now(timezone.utc)
    if portal:
        scan_status, scanned_by, detail = (
            "pending", None, "Awaiting staff release")
    else:
        scan_status, scanned_by, detail = (
            "clean", "policy-v1", "Staff channel; type/size/signature checks passed")
    doc = models.StoredDocument(
        id=doc_id, tenant_id=tenant_id, invoice_id=invoice_id, origin=origin,
        original_filename=filename[:120], stored_name=stored_name,
        mime_type=mime, size_bytes=len(data), sha256=digest,
        scan_status=scan_status, scanned_by=scanned_by, scanned_at=now,
        scan_detail=detail, uploaded_by=uploaded_by,
        portal_token_id=portal_token_id, uploaded_at=now,
        retention_expires_at=now + timedelta(days=settings.DOC_RETENTION_DAYS))
    db.add(doc)
    db.flush()
    log_access(db, doc, uploaded_by, "stored")
    return doc


def readable_document(db, doc_id, tenant_id):
    """Fetch a tenant-owned doc that is allowed to serve bytes, or None."""
    doc = db.get(models.StoredDocument, doc_id)
    if (not doc or doc.tenant_id != tenant_id or doc.deleted_at is not None
            or doc.scan_status == "quarantined"):
        return None
    return doc


def doc_view(doc):
    return {"doc_id": doc.id, "invoice_id": doc.invoice_id,
            "origin": doc.origin, "filename": doc.original_filename,
            "mime_type": doc.mime_type, "size_bytes": doc.size_bytes,
            "sha256": doc.sha256, "scan_status": doc.scan_status,
            "scanned_by": doc.scanned_by,
            "scanned_at": doc.scanned_at.isoformat() if doc.scanned_at else None,
            "scan_detail": doc.scan_detail, "uploaded_by": doc.uploaded_by,
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            "retention_expires_at": doc.retention_expires_at.isoformat()
            if doc.retention_expires_at else None,
            "hold": bool(doc.hold), "hold_reason": doc.hold_reason,
            "deleted_at": doc.deleted_at.isoformat() if doc.deleted_at else None}


def release_document(db, doc, actor):
    """Staff release a pending portal upload for case use. Caller commits."""
    if doc.deleted_at is not None:
        raise DocumentRejected("Deleted documents cannot be released")
    if doc.scan_status == "quarantined":
        raise DocumentRejected("Quarantined documents need a fresh upload")
    if doc.scan_status == "clean":
        raise DocumentRejected("Document is already released")
    now = datetime.now(timezone.utc)
    doc.scan_status = "clean"
    doc.scanned_by = actor
    doc.scanned_at = now
    doc.scan_detail = "Released by staff after review"
    log_access(db, doc, actor, "released")
    db.flush()
    return doc


def quarantine_document(db, doc, actor, reason=""):
    """Block reads immediately. Safe direction: any staff may quarantine."""
    if doc.deleted_at is not None:
        raise DocumentRejected("Deleted documents cannot be quarantined")
    doc.scan_status = "quarantined"
    doc.scanned_by = actor
    doc.scanned_at = datetime.now(timezone.utc)
    doc.scan_detail = (reason or "Quarantined by staff")[:500]
    log_access(db, doc, actor, "quarantined")
    db.flush()
    return doc


def set_hold(db, doc, actor, hold, reason=""):
    doc.hold = bool(hold)
    doc.hold_reason = (reason or "")[:500] if hold else None
    log_access(db, doc, actor, "hold_set" if hold else "hold_cleared")
    db.flush()
    return doc


def delete_document(db, doc, actor):
    """Soft delete: bytes removed, row stays for the audit trail."""
    if doc.deleted_at is not None:
        raise DocumentRejected("Document is already deleted")
    if doc.hold:
        raise DocumentRejected("Document is on retention hold")
    try:
        document_path(doc).unlink(missing_ok=True)
    except DocumentRejected:
        pass
    doc.deleted_at = datetime.now(timezone.utc)
    log_access(db, doc, actor, "deleted")
    db.flush()
    return doc


def purge_expired_documents(db, tenant_id, actor, dry_run=True):
    """Delete bytes for docs past retention, skipping holds. Returns the plan."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    candidates = db.query(models.StoredDocument).filter(
        models.StoredDocument.tenant_id == tenant_id,
        models.StoredDocument.deleted_at.is_(None),
        models.StoredDocument.hold.is_(False),
        models.StoredDocument.retention_expires_at.is_not(None),
        models.StoredDocument.retention_expires_at < now).all()
    plan = [{"doc_id": doc.id, "filename": doc.original_filename,
             "retention_expires_at": doc.retention_expires_at.isoformat()}
            for doc in candidates]
    if not dry_run:
        for doc in candidates:
            delete_document(db, doc, actor)
    return plan
