"""Business identity: parties, branches, external ids, duplicates, merges.

GSTIN checks are FORMAT-ONLY (pattern plus state-code range). A syntactically
valid GSTIN is not verified identity; registry verification is future work.
Merges move links only — invoice name fields are never rewritten.
"""
import json
import re
from difflib import SequenceMatcher

from app.database import models

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
SYSTEM_RE = re.compile(r"^[a-z0-9_]{1,40}$")


def validate_gstin(value):
    """Normalize a GSTIN or raise. Empty means 'not provided', never a guess."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    normalized = value.strip().upper()
    if not GSTIN_RE.match(normalized):
        raise ValueError("GSTIN must be 15 characters: 2-digit state code, "
                         "10-character PAN, entity code, Z, checksum")
    if not 1 <= int(normalized[:2]) <= 38:
        raise ValueError("GSTIN state code must be between 01 and 38")
    return normalized


def validate_system(value):
    normalized = (value or "").strip().lower()
    if not SYSTEM_RE.match(normalized):
        raise ValueError("System must be 1-40 lowercase letters, digits, or _")
    return normalized


def display_name_of(row):
    return row.display_name or row.name


def create_counterparty(db, tenant_id, actor, name, type, email=None,
                        phone=None, address=None, tax_id=None, gstin=None,
                        legal_name=None, display_name=None,
                        billing_address=None, shipping_address=None):
    row = models.Counterparty(
        tenant_id=tenant_id, name=name.strip(), type=type,
        email=(email or None), phone=(phone or None),
        address=(address or None), tax_id=(tax_id or None),
        gstin=validate_gstin(gstin),
        legal_name=(legal_name.strip() if legal_name else None),
        display_name=(display_name.strip() if display_name else None),
        billing_address=(billing_address or None),
        shipping_address=(shipping_address or None), status="active")
    db.add(row)
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="counterparty_created", entity_type="counterparty",
        entity_id=name.strip()))
    db.flush()
    return row


def update_counterparty(db, row, actor, **fields):
    allowed = {"name", "type", "email", "phone", "address", "tax_id",
               "legal_name", "display_name", "billing_address",
               "shipping_address"}
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        setattr(row, key, value.strip() if isinstance(value, str) else value)
    if "gstin" in fields:
        row.gstin = validate_gstin(fields["gstin"])
    db.add(models.AuditEvent(tenant_id=row.tenant_id, actor=actor,
        action="counterparty_updated", entity_type="counterparty",
        entity_id=str(row.id)))
    db.flush()
    return row


def _digits(value):
    return "".join(ch for ch in (value or "") if ch.isdigit())[-10:]


def suggest_duplicates(db, tenant_id, party, limit=5):
    """Explainable duplicate candidates: score plus human-readable reasons."""
    candidates = db.query(models.Counterparty).filter_by(
        tenant_id=tenant_id, status="active").filter(
        models.Counterparty.id != party.id).all()
    scored = []
    for other in candidates:
        score, reasons = 0.0, []
        if party.gstin and other.gstin and party.gstin == other.gstin:
            score += 1.0
            reasons.append("same GSTIN")
        if party.email and other.email and party.email.strip().lower() == other.email.strip().lower():
            score += 0.5
            reasons.append("same email")
        mine, theirs = _digits(party.phone), _digits(other.phone)
        if mine and mine == theirs:
            score += 0.5
            reasons.append("same phone")
        ratio = SequenceMatcher(None, (party.name or "").lower(),
                                (other.name or "").lower()).ratio()
        if ratio >= 0.8:
            score += round(ratio * 0.6, 3)
            reasons.append(f"name similarity {ratio:.0%}")
        if score > 0:
            scored.append({"counterparty_id": other.id,
                           "name": display_name_of(other),
                           "score": round(score, 3), "reasons": reasons})
    scored.sort(key=lambda item: (-item["score"], item["name"]))
    return scored[:limit]


def merge_preview(db, tenant_id, loser_id, winner_id):
    loser = db.get(models.Counterparty, loser_id)
    winner = db.get(models.Counterparty, winner_id)
    if not loser or loser.tenant_id != tenant_id:
        raise LookupError("Counterparty not found")
    if not winner or winner.tenant_id != tenant_id:
        raise LookupError("Merge target not found")
    invoices = db.query(models.Invoice).filter_by(
        tenant_id=tenant_id, counterparty_id=loser.id).order_by(
        models.Invoice.invoice_number).all()
    return {"loser": {"id": loser.id, "name": display_name_of(loser),
                      "status": loser.status},
            "winner": {"id": winner.id, "name": display_name_of(winner),
                       "status": winner.status},
            "invoices": [{"id": row.id, "invoice_number": row.invoice_number,
                          "total_amount": str(row.total_amount)}
                         for row in invoices],
            "branches": db.query(models.CounterpartyBranch).filter_by(
                tenant_id=tenant_id, counterparty_id=loser.id).count(),
            "external_ids": db.query(models.CounterpartyExternalId).filter_by(
                tenant_id=tenant_id, counterparty_id=loser.id).count()}


def merge_counterparties(db, tenant_id, loser_id, winner_id, reason, actor):
    """Staff-confirmed merge. Moves links; invoice names are never rewritten."""
    loser = db.get(models.Counterparty, loser_id)
    winner = db.get(models.Counterparty, winner_id)
    if not loser or loser.tenant_id != tenant_id:
        raise LookupError("Counterparty not found")
    if not winner or winner.tenant_id != tenant_id:
        raise LookupError("Merge target not found")
    if loser.id == winner.id:
        raise ValueError("Cannot merge a counterparty into itself")
    if loser.status == "merged" or winner.status == "merged":
        raise ValueError("Merged counterparties cannot take part in a merge")
    moved = db.query(models.Invoice).filter_by(
        tenant_id=tenant_id, counterparty_id=loser.id).all()
    for invoice in moved:
        invoice.counterparty_id = winner.id
    for branch in db.query(models.CounterpartyBranch).filter_by(
            tenant_id=tenant_id, counterparty_id=loser.id).all():
        branch.counterparty_id = winner.id
    for external in db.query(models.CounterpartyExternalId).filter_by(
            tenant_id=tenant_id, counterparty_id=loser.id).all():
        external.counterparty_id = winner.id
    loser.status = "merged"
    loser.merged_into_id = winner.id
    ids = [row.id for row in moved]
    db.add(models.CounterpartyMerge(
        tenant_id=tenant_id, loser_id=loser.id, winner_id=winner.id,
        moved_invoices=len(ids), invoice_ids=json.dumps(ids),
        reason=reason, created_by=actor))
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="counterparty_merged", entity_type="counterparty",
        entity_id=str(loser.id),
        details=f"into={winner.id}; invoices={len(ids)}; reason={reason}"[:500]))
    db.flush()
    return {"loser_id": loser.id, "winner_id": winner.id,
            "moved_invoices": len(ids), "invoice_ids": ids}


def bootstrap_from_invoices(db, tenant_id, actor, invoice_type="AR"):
    """Create parties from distinct unlinked invoice names, then link them."""
    rows = db.query(models.Invoice).filter_by(
        tenant_id=tenant_id, invoice_type=invoice_type,
        counterparty_id=None).all()
    created, linked = 0, 0
    for invoice in rows:
        party = db.query(models.Counterparty).filter_by(
            tenant_id=tenant_id, name=invoice.counterparty_name,
            status="active").first()
        if not party:
            party = models.Counterparty(
                tenant_id=tenant_id, name=invoice.counterparty_name,
                type="customer" if invoice_type == "AR" else "vendor",
                status="active")
            db.add(party)
            db.flush()
            created += 1
        invoice.counterparty_id = party.id
        linked += 1
    db.add(models.AuditEvent(tenant_id=tenant_id, actor=actor,
        action="counterparty_bootstrapped", entity_type="counterparty",
        entity_id=invoice_type,
        details=f"created={created}; linked={linked}"))
    db.flush()
    return {"created": created, "linked": linked}


def link_invoice_party(db, invoice):
    """Point one invoice at the same-tenant active party with the exact name."""
    if invoice.counterparty_id is not None:
        return invoice.counterparty_id
    party = db.query(models.Counterparty).filter_by(
        tenant_id=invoice.tenant_id, name=invoice.counterparty_name,
        status="active").first()
    if party:
        invoice.counterparty_id = party.id
        db.flush()
        return party.id
    return None
