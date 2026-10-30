"""Data-principal request workflows: access, export, correction, deletion.

F1 privacy readiness. This is an operational workflow, NOT a compliance
claim: DPDP applicability and every deletion decision need legal review
(see docs/privacy.md). Two hard rules hold regardless:

1. Money and ledger identity are never touched here. Correction is limited
   to an allowlist of contact fields; deletion erases contact and
   communication data only. Invoices, ledger entries, names on the books,
   GSTINs and the audit trail are retained as books-of-account records.
2. Deletion is blocked while the subject has a non-terminal invoice or a
   linked document on retention hold. Active portal tokens are revoked as
   part of execution.
"""
import json
from datetime import datetime, timezone

from app.database import models
from app.services import document_store
from app.services.portal import revoke_token

KINDS = ("access", "export", "correction", "deletion")
SUBJECT_TYPES = ("counterparty", "staff_user")
TERMINAL_INVOICE_STATUS = ("paid", "adjusted")
# entity -> correctable fields. Amounts, parties, GSTINs and login identity
# are deliberately absent: they change books or authentication, not contact data.
CORRECTION_ALLOWLIST = {
    "counterparty": {"email", "phone", "address", "display_name",
                     "billing_address", "shipping_address"},
    "counterparty_branch": {"billing_address", "shipping_address"},
    "staff_user": {"name"},
}


class PrivacyError(ValueError):
    """A request is invalid, forbidden, or blocked by retention."""


def _now():
    return datetime.now(timezone.utc)


def _audit(db, tenant_id, actor, action, entity_id, details=""):
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor, action=action,
                             entity_type="privacy_request", entity_id=str(entity_id),
                             details=details[:2000]))


def _subject(db, tenant_id, subject_type, subject_ref):
    model = models.Counterparty if subject_type == "counterparty" else models.User
    row = db.query(model).filter(model.tenant_id == tenant_id,
                                 model.id == subject_ref).first()
    if row is None:
        raise PrivacyError(f"Unknown {subject_type} {subject_ref}")
    return row


def create_request(db, tenant_id, kind, subject_type, subject_ref, details, actor):
    """Open a subject request. Correction details must name entity + fields."""
    if kind not in KINDS:
        raise PrivacyError(f"Unknown request kind {kind!r}")
    if subject_type not in SUBJECT_TYPES:
        raise PrivacyError(f"Unknown subject type {subject_type!r}")
    _subject(db, tenant_id, subject_type, subject_ref)
    if kind == "correction":
        _validate_correction_payload(details, subject_type)
    row = models.PrivacyRequest(tenant_id=tenant_id, kind=kind,
                                subject_type=subject_type, subject_ref=subject_ref,
                                details=json.dumps(details or {}),
                                status="open", created_by=actor)
    db.add(row)
    db.flush()
    _audit(db, tenant_id, actor, "privacy_request_created", row.id,
           f"kind={kind} subject={subject_type}:{subject_ref}")
    db.flush()
    return row


def _validate_correction_payload(details, subject_type):
    if not isinstance(details, dict):
        raise PrivacyError("Correction details must name entity and fields")
    entity = details.get("entity")
    fields = details.get("fields")
    if subject_type == "counterparty" and entity not in ("counterparty", "counterparty_branch"):
        raise PrivacyError("Counterparty correction targets counterparty or counterparty_branch")
    if subject_type == "staff_user" and entity != "staff_user":
        raise PrivacyError("Staff correction targets staff_user only")
    if not isinstance(fields, dict) or not fields:
        raise PrivacyError("Correction needs a non-empty fields object")
    allowed = CORRECTION_ALLOWLIST[entity]
    rejected = sorted(set(fields) - allowed)
    if rejected:
        raise PrivacyError(f"Fields not correctable here: {', '.join(rejected)}")
    for key, value in fields.items():
        if value is not None and (not isinstance(value, str) or len(value) > 2000):
            raise PrivacyError(f"Field {key} must be a short string or null")


def get_request(db, tenant_id, request_id):
    row = db.query(models.PrivacyRequest).filter(
        models.PrivacyRequest.tenant_id == tenant_id,
        models.PrivacyRequest.id == request_id).first()
    if row is None:
        raise PrivacyError(f"Unknown privacy request {request_id}")
    return row


def list_requests(db, tenant_id, status=""):
    query = db.query(models.PrivacyRequest).filter(
        models.PrivacyRequest.tenant_id == tenant_id)
    if status:
        query = query.filter(models.PrivacyRequest.status == status)
    return query.order_by(models.PrivacyRequest.id.desc()).all()


def _counterparty_invoices(db, tenant_id, counterparty):
    """Invoices linked by id plus legacy rows carrying only the name."""
    rows = db.query(models.Invoice).filter(
        models.Invoice.tenant_id == tenant_id).filter(
            (models.Invoice.counterparty_id == counterparty.id) |
            (models.Invoice.counterparty_id.is_(None) &
             (models.Invoice.counterparty_name == counterparty.name))).all()
    return rows


def _iso(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.isoformat()
    return value.isoformat()


def collect_subject_data(db, tenant_id, subject_type, subject_ref):
    """Assemble everything held about one subject. Secrets are never included:
    no password hashes, API key hashes, session token hashes, portal token
    hashes, or portal-attempt IP logs."""
    subject = _subject(db, tenant_id, subject_type, subject_ref)
    if subject_type == "staff_user":
        keys = db.query(models.UserApiKey).filter(
            models.UserApiKey.tenant_id == tenant_id,
            models.UserApiKey.user_id == subject.id).all()
        sessions = db.query(models.UserSession).filter(
            models.UserSession.tenant_id == tenant_id,
            models.UserSession.user_id == subject.id).all()
        recoveries = db.query(models.UserRecoveryToken).filter(
            models.UserRecoveryToken.tenant_id == tenant_id,
            models.UserRecoveryToken.user_id == subject.id).all()
        return {
            "subject_type": subject_type,
            "profile": {"id": subject.id, "email": subject.email, "name": subject.name,
                        "role": subject.role, "is_active": subject.is_active,
                        "created_at": _iso(subject.created_at),
                        "last_login_at": _iso(subject.last_login_at)},
            "api_keys": [{"id": k.id, "name": k.name, "key_prefix": k.key_prefix,
                          "role": k.role, "is_active": k.is_active,
                          "expires_at": _iso(k.expires_at)} for k in keys],
            "sessions": [{"id": s.id, "created_at": _iso(s.created_at),
                          "expires_at": _iso(s.expires_at),
                          "is_revoked": s.is_revoked} for s in sessions],
            "recovery_tokens": [{"id": r.id, "expires_at": _iso(r.expires_at),
                                 "used": r.used_at is not None} for r in recoveries],
        }
    invoices = _counterparty_invoices(db, tenant_id, subject)
    invoice_ids = [i.id for i in invoices]
    branches = db.query(models.CounterpartyBranch).filter(
        models.CounterpartyBranch.tenant_id == tenant_id,
        models.CounterpartyBranch.counterparty_id == subject.id).all()
    external_ids = db.query(models.CounterpartyExternalId).filter(
        models.CounterpartyExternalId.tenant_id == tenant_id,
        models.CounterpartyExternalId.counterparty_id == subject.id).all()
    merges = db.query(models.CounterpartyMerge).filter(
        models.CounterpartyMerge.tenant_id == tenant_id).filter(
            (models.CounterpartyMerge.loser_id == subject.id) |
            (models.CounterpartyMerge.winner_id == subject.id)).all()

    def _linked(model):
        if not invoice_ids:
            return []
        return db.query(model).filter(model.tenant_id == tenant_id,
                                      model.invoice_id.in_(invoice_ids)).all()

    customer_messages = _linked(models.CustomerMessage)
    inbound = _linked(models.InboundMessage)
    outbound = _linked(models.OutboundMessage)
    evidence = _linked(models.CaseEvidence)
    promises = _linked(models.PromiseToPay)
    prefs = _linked(models.CommsPreference)
    docs = _linked(models.StoredDocument)
    tokens = _linked(models.PortalToken)
    return {
        "subject_type": subject_type,
        "profile": {"id": subject.id, "name": subject.name, "type": subject.type,
                    "email": subject.email, "phone": subject.phone,
                    "address": subject.address, "legal_name": subject.legal_name,
                    "display_name": subject.display_name,
                    "billing_address": subject.billing_address,
                    "shipping_address": subject.shipping_address,
                    "gstin": subject.gstin, "status": subject.status},
        "branches": [{"id": b.id, "name": b.name, "gstin": b.gstin,
                      "billing_address": b.billing_address,
                      "shipping_address": b.shipping_address} for b in branches],
        "external_ids": [{"system": e.system, "external_id": e.external_id}
                         for e in external_ids],
        "merges": [{"loser_id": m.loser_id, "winner_id": m.winner_id,
                    "moved_invoices": m.moved_invoices,
                    "reason": m.reason, "created_at": _iso(m.created_at)}
                   for m in merges],
        "invoices": [{"id": i.id, "invoice_number": i.invoice_number,
                      "invoice_type": i.invoice_type, "status": i.status,
                      "currency": i.currency,
                      "total": str(i.total_amount) if i.total_amount is not None else None,
                      "disputed_cents": i.disputed_cents,
                      "counterparty_email": i.counterparty_email,
                      "counterparty_phone": i.counterparty_phone}
                     for i in invoices],
        "customer_messages": [{"id": m.id, "invoice_id": m.invoice_id,
                               "category": m.category, "body": m.body,
                               "created_at": _iso(m.created_at)} for m in customer_messages],
        "inbound_messages": [{"id": m.id, "invoice_id": m.invoice_id,
                              "provider": m.provider, "sender": m.sender,
                              "body": m.body, "status": m.status} for m in inbound],
        "outbound_messages": [{"id": m.id, "invoice_id": m.invoice_id,
                               "provider": m.provider, "recipient": m.recipient,
                               "body": m.body, "status": m.status} for m in outbound],
        "evidence": [{"id": e.id, "invoice_id": e.invoice_id,
                      "claim_type": e.claim_type, "title": e.title,
                      "description": e.description,
                      "source_type": e.source_type,
                      "source_reference": e.source_reference,
                      "source_snippet": e.source_snippet,
                      "trust_state": e.trust_state} for e in evidence],
        "promises": [{"id": p.id, "invoice_id": p.invoice_id,
                      "promised_cents": p.promised_cents, "status": p.status,
                      "source_text": p.source_text} for p in promises],
        "comms_preferences": [{"invoice_id": p.invoice_id, "channel": p.channel,
                               "opted_in": p.opted_in, "basis": p.basis,
                               "language": p.language} for p in prefs],
        "documents": [{"id": d.id, "invoice_id": d.invoice_id,
                       "original_filename": d.original_filename,
                       "mime_type": d.mime_type, "size_bytes": d.size_bytes,
                       "sha256": d.sha256, "scan_status": d.scan_status,
                       "hold": d.hold, "deleted_at": _iso(d.deleted_at),
                       "note": "file bytes stay in private storage; refetch via the documents API"}
                      for d in docs],
        "portal_tokens": [{"prefix": t.prefix, "invoice_id": t.invoice_id,
                           "expires_at": _iso(t.expires_at),
                           "revoked": t.revoked_at is not None,
                           "use_count": t.use_count} for t in tokens],
    }


def apply_correction(db, req, actor):
    """Write allowlisted contact fields. Money, parties and identity stay fixed."""
    payload = json.loads(req.details or "{}")
    _validate_correction_payload(payload, req.subject_type)
    entity = payload["entity"]
    fields = payload["fields"]
    if entity == "counterparty_branch":
        entity_id = payload.get("entity_id")
        target = db.query(models.CounterpartyBranch).filter(
            models.CounterpartyBranch.tenant_id == req.tenant_id,
            models.CounterpartyBranch.id == entity_id,
            models.CounterpartyBranch.counterparty_id == req.subject_ref).first()
        if target is None:
            raise PrivacyError("Branch does not belong to this subject")
    elif entity == "counterparty":
        target = _subject(db, req.tenant_id, "counterparty", req.subject_ref)
    else:
        target = _subject(db, req.tenant_id, "staff_user", req.subject_ref)
    for key, value in fields.items():
        setattr(target, key, value)
    req.status = "fulfilled"
    req.resolution = f"Corrected {entity} fields: {', '.join(sorted(fields))}"
    req.decided_by = actor
    req.decided_at = _now()
    _audit(db, req.tenant_id, actor, "privacy_request_fulfilled", req.id, req.resolution)
    db.flush()
    return sorted(fields)


def check_deletion(db, tenant_id, subject_type, subject_ref, actor=""):
    """Return human-readable blocks. Empty means deletion may proceed."""
    subject = _subject(db, tenant_id, subject_type, subject_ref)
    if subject_type == "staff_user":
        blocks = []
        if subject.email == actor:
            blocks.append("Staff cannot erase their own login; ask another admin")
        others = db.query(models.User).filter(
            models.User.tenant_id == tenant_id, models.User.role == "admin",
            models.User.is_active.is_(True),
            models.User.id != subject.id).count()
        if subject.role == "admin" and subject.is_active and others == 0:
            blocks.append("Refusing to erase the last active admin")
        return blocks
    invoices = _counterparty_invoices(db, tenant_id, subject)
    open_ids = [i.id for i in invoices if (i.status or "") not in TERMINAL_INVOICE_STATUS]
    blocks = []
    if open_ids:
        blocks.append(f"{len(open_ids)} non-terminal invoice(s): "
                      + ", ".join(str(i) for i in sorted(open_ids)))
    invoice_ids = [i.id for i in invoices]
    if invoice_ids:
        held = db.query(models.StoredDocument).filter(
            models.StoredDocument.tenant_id == tenant_id,
            models.StoredDocument.invoice_id.in_(invoice_ids),
            models.StoredDocument.hold.is_(True),
            models.StoredDocument.deleted_at.is_(None)).all()
        if held:
            blocks.append(f"{len(held)} linked document(s) on retention hold: "
                          + ", ".join(d.id for d in held))
    return blocks


def execute_deletion(db, req, actor):
    """Erase contact + communication data. Ledger rows stay under books-of-account
    retention; the resolution records exactly what was kept and why."""
    blocks = check_deletion(db, req.tenant_id, req.subject_type, req.subject_ref, actor)
    if blocks:
        raise PrivacyError("Deletion blocked: " + "; ".join(blocks))
    marker = f"[redacted - privacy request #{req.id}]"
    if req.subject_type == "staff_user":
        user = _subject(db, req.tenant_id, "staff_user", req.subject_ref)
        user.is_active = False
        revoked_sessions = db.query(models.UserSession).filter(
            models.UserSession.tenant_id == req.tenant_id,
            models.UserSession.user_id == user.id,
            models.UserSession.is_revoked.is_(False)).update(
                {"is_revoked": True}, synchronize_session=False)
        revoked_keys = db.query(models.UserApiKey).filter(
            models.UserApiKey.tenant_id == req.tenant_id,
            models.UserApiKey.user_id == user.id,
            models.UserApiKey.is_active.is_(True)).update(
                {"is_active": False}, synchronize_session=False)
        now = _now()
        voided_recovery = db.query(models.UserRecoveryToken).filter(
            models.UserRecoveryToken.tenant_id == req.tenant_id,
            models.UserRecoveryToken.user_id == user.id,
            models.UserRecoveryToken.used_at.is_(None)).update(
                {"used_at": now}, synchronize_session=False)
        req.status = "fulfilled"
        req.resolution = (f"Deactivated login {user.email}; revoked {revoked_sessions} session(s), "
                          f"{revoked_keys} API key(s), {voided_recovery} recovery token(s). "
                          "Audit history kept as a business record.")
    else:
        cp = _subject(db, req.tenant_id, "counterparty", req.subject_ref)
        for field in ("email", "phone", "address", "display_name",
                      "billing_address", "shipping_address"):
            setattr(cp, field, None)
        branches = db.query(models.CounterpartyBranch).filter(
            models.CounterpartyBranch.tenant_id == req.tenant_id,
            models.CounterpartyBranch.counterparty_id == cp.id).all()
        for branch in branches:
            branch.billing_address = None
            branch.shipping_address = None
        invoices = _counterparty_invoices(db, req.tenant_id, cp)
        invoice_ids = [i.id for i in invoices]
        for invoice in invoices:
            invoice.counterparty_email = None
            invoice.counterparty_phone = None
        counts = {}
        if invoice_ids:
            for model, columns in (
                    (models.CustomerMessage, {"body": marker}),
                    (models.InboundMessage, {"sender": marker, "body": marker}),
                    (models.OutboundMessage, {"recipient": marker, "body": marker}),
                    (models.CaseEvidence, {"source_snippet": None}),
                    (models.PromiseToPay, {"source_text": marker})):
                counts[model.__tablename__] = db.query(model).filter(
                    model.tenant_id == req.tenant_id,
                    model.invoice_id.in_(invoice_ids)).update(
                        columns, synchronize_session=False)
            docs = db.query(models.StoredDocument).filter(
                models.StoredDocument.tenant_id == req.tenant_id,
                models.StoredDocument.invoice_id.in_(invoice_ids),
                models.StoredDocument.deleted_at.is_(None)).all()
            deleted_docs = 0
            for doc in docs:
                # Holds were checked above; re-check per row against races.
                if doc.hold:
                    raise PrivacyError(f"Deletion blocked: document {doc.id} was put on hold")
                document_store.delete_document(db, doc, actor)
                deleted_docs += 1
            tokens = db.query(models.PortalToken).filter(
                models.PortalToken.tenant_id == req.tenant_id,
                models.PortalToken.invoice_id.in_(invoice_ids),
                models.PortalToken.revoked_at.is_(None)).all()
            revoked_tokens = 0
            for token in tokens:
                revoke_token(db, token, actor, f"privacy request #{req.id}")
                revoked_tokens += 1
        else:
            deleted_docs = 0
            revoked_tokens = 0
        req.status = "fulfilled"
        req.resolution = (
            f"Erased contact fields on counterparty {cp.id} (+{len(branches)} branches, "
            f"{len(invoices)} invoice snapshots); redacted {counts.get('customer_messages', 0)} "
            f"customer message(s), {counts.get('inbound_messages', 0)} inbound, "
            f"{counts.get('outbound_messages', 0)} outbound, "
            f"{counts.get('case_evidence', 0)} evidence snippet(s), "
            f"{counts.get('promises_to_pay', 0)} promise text(s); removed {deleted_docs} "
            f"document file(s); revoked {revoked_tokens} portal token(s). Invoices, ledger "
            "entries, names on the books, GSTINs and the audit trail are retained as "
            "books-of-account records.")
    req.decided_by = actor
    req.decided_at = _now()
    _audit(db, req.tenant_id, actor, "privacy_request_fulfilled", req.id, req.resolution)
    db.flush()
    return req.resolution


def fulfill_request(db, req, actor):
    """Fulfill access/export (returns the bundle) or correction/deletion."""
    if req.status not in ("open", "in_review"):
        raise PrivacyError(f"Request #{req.id} is already {req.status}")
    if req.kind in ("access", "export"):
        bundle = collect_subject_data(db, req.tenant_id, req.subject_type, req.subject_ref)
        req.status = "fulfilled"
        req.resolution = f"{req.kind} bundle assembled ({len(bundle)} sections)"
        req.decided_by = actor
        req.decided_at = _now()
        _audit(db, req.tenant_id, actor, "privacy_request_fulfilled", req.id, req.resolution)
        db.flush()
        return bundle
    if req.kind == "correction":
        return {"applied_fields": apply_correction(db, req, actor)}
    return {"resolution": execute_deletion(db, req, actor)}


def reject_request(db, req, actor, reason):
    """Refuse a request with a recorded reason (e.g. unverified requester)."""
    if req.status not in ("open", "in_review"):
        raise PrivacyError(f"Request #{req.id} is already {req.status}")
    if not reason or not reason.strip():
        raise PrivacyError("A rejection needs a reason")
    req.status = "rejected"
    req.resolution = reason.strip()[:2000]
    req.decided_by = actor
    req.decided_at = _now()
    _audit(db, req.tenant_id, actor, "privacy_request_rejected", req.id, req.resolution)
    db.flush()
    return req


def mark_in_review(db, req, actor):
    if req.status != "open":
        raise PrivacyError(f"Request #{req.id} is already {req.status}")
    req.status = "in_review"
    _audit(db, req.tenant_id, actor, "privacy_request_review", req.id, "")
    db.flush()
    return req


def request_view(req):
    return {"id": req.id, "tenant_id": req.tenant_id, "kind": req.kind,
            "subject_type": req.subject_type, "subject_ref": req.subject_ref,
            "details": json.loads(req.details or "{}"), "status": req.status,
            "resolution": req.resolution, "created_by": req.created_by,
            "created_at": _iso(req.created_at), "decided_by": req.decided_by,
            "decided_at": _iso(req.decided_at)}
