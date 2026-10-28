"""Conservative multi-document investigation. Claims reserve money, never credit it.

Line comparison lives in line_matching (pure). This module persists claims,
competing explanations, and clarification tasks, and pauses contact whenever
sources disagree or a fact is missing. Stages stay separate: customer text is
an allegation, parsed fields are extracted, staff confirmations are verified,
dispute decisions are accepted, and only post_entry creates ledger entries.
"""
from datetime import date, timedelta
from decimal import InvalidOperation
import hashlib
import json
import re
from app.database import models
from app.services.line_matching import (
    check_line_arithmetic,
    convert_quantity,
    fulfilment_hypotheses,
    identity_key,
    match_sku_in_text,
    normalize,
    price_hypotheses,
    tax_basis_plausible,
    to_cents,
    to_decimal,
)
from app.services.receivables import balance_cents

__all__ = ["normalize", "linked_documents", "document_digest", "investigate"]


def linked_documents(db, invoice):
    rows = db.query(models.IntakeUpload).filter_by(tenant_id=invoice.tenant_id).filter(
        models.IntakeUpload.extraction_json.isnot(None)).all()
    linked = []
    for row in rows:
        try:
            doc = json.loads(row.extraction_json)
        except (ValueError, TypeError):
            continue
        if (doc.get("invoice_reference") == invoice.invoice_number or
            (doc.get("invoice_number") == invoice.invoice_number and row.source_path == invoice.source_path)):
            linked.append((row, doc))
    return linked


def document_digest(db, invoice):
    return hashlib.sha256(json.dumps([(row.id, doc) for row, doc in linked_documents(db, invoice)],
        sort_keys=True).encode()).hexdigest()


def _source(row):
    return f"/api/v1/intake/uploads/{row.id}/file"


def _ensure_explanation(db, invoice, identity, category, hypotheses):
    row = db.query(models.CompetingExplanation).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, identity=identity,
        category=category, status="open").first()
    payload = json.dumps(hypotheses)
    if row:
        row.hypotheses_json = payload
        return row
    row = models.CompetingExplanation(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, identity=identity,
        category=category, hypotheses_json=payload, status="open")
    db.add(row)
    db.flush()
    return row


def _ensure_clarification(db, invoice, key, title, owner, source, affected_cents=0):
    row = db.query(models.ClarificationTask).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, key=key,
        status="open").first()
    draft = (f"Unsent draft - {title} (invoice {invoice.invoice_number}, "
             f"affects {affected_cents} cents). Source: {source}. Staff must "
             f"review and approve before any customer contact.")
    if row:
        row.title = title
        row.affected_cents = affected_cents
        row.draft_preview = draft
        return row
    row = models.ClarificationTask(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id, key=key, title=title,
        owner=owner, source=source, due_date=date.today() + timedelta(days=7),
        affected_cents=affected_cents, status="open", draft_preview=draft,
        created_by="investigator_agent")
    db.add(row)
    db.flush()
    return row


def investigate(db, invoice):
    linked = linked_documents(db, invoice)
    if invoice.investigation_decision_hash == document_digest(db, invoice):
        return int(invoice.disputed_cents or 0)
    original = next((doc for row, doc in linked if row.source_path == invoice.source_path
                     and doc.get("document_type") == "invoice"), {})
    lines = original.get("line_items", [])
    aliases = {a.alias: a.canonical_sku for a in db.query(models.ItemAlias).filter_by(
        tenant_id=invoice.tenant_id).all()}
    unit_rules = [(r.from_unit, r.to_unit, r.factor) for r in db.query(models.UnitRule).filter_by(
        tenant_id=invoice.tenant_id).all()]
    originals = {}
    issues, claims, hypotheses = [], {}, {}
    for line in lines:
        identity = identity_key(line, aliases)
        if not identity or identity in originals:
            issues.append("Invoice contains ambiguous or repeated item identities")
        originals[identity] = line

    def add(identity, category, amount, row, description):
        try:
            minor = to_cents(amount)
        except ValueError:
            issues.append("Claim requires an explicit rounding/tax decision")
            return
        if minor <= 0:
            return
        bucket = claims.setdefault((identity, category), [])
        bucket.append((minor, row, description))

    def note_hypotheses(identity, category, hyps):
        if hyps:
            hypotheses.setdefault((identity, category), []).extend(hyps)

    tax_present = bool(to_decimal(original.get("tax_amount") or "0") or
                       to_decimal(original.get("shipping_amount") or "0"))
    scheme_amounts = {}
    for _, doc in linked:
        if doc.get("document_type") != "discount_agreement":
            continue
        for line in doc.get("line_items", []):
            try:
                scheme_amounts.setdefault(identity_key(line, aliases),
                                          to_cents(to_decimal(line["amount"])))
            except (KeyError, ValueError, InvalidOperation):
                continue
    seen_documents = set()
    touched_explanations = set()
    for row, doc in linked:
        kind = doc.get("document_type")
        if kind in ("invoice", "receipt"):
            continue
        if doc.get("currency") and doc["currency"] != invoice.currency:
            issues.append("Document currency differs from invoice")
            continue
        content_hash = hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()
        if content_hash in seen_documents:
            db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor="investigator_agent",
                action="investigation_duplicate_skipped", entity_type="invoice",
                entity_id=str(invoice.id), details=f"upload={row.id}; kind={kind}"))
            continue
        seen_documents.add(content_hash)
        if kind in ("purchase_order", "delivery_note", "return_note", "discount_agreement") \
                and not doc.get("line_items"):
            issues.append(f"Unreadable {kind}; obtain a readable copy")
            _ensure_clarification(db, invoice, f"readable:{kind}:{row.id}",
                f"Obtain a readable {kind.replace('_', ' ')} for invoice {invoice.invoice_number}",
                "staff", _source(row))
            continue
        try:
            if kind in ("purchase_order", "delivery_note", "return_note", "discount_agreement"):
                if not lines:
                    issues.append("Invoice lines are required to investigate supporting documents")
                    continue
                seen = set()
                for item in doc.get("line_items", []):
                    identity = identity_key(item, aliases)
                    base = originals.get(identity)
                    if not base or identity in seen:
                        issues.append("Unmatched or duplicate item; register a staff-approved SKU alias")
                        continue
                    seen.add(identity)
                    arithmetic = check_line_arithmetic(item)
                    if arithmetic:
                        issues.append(arithmetic)
                        continue
                    try:
                        if item.get("unit") or base.get("unit"):
                            convert_quantity(to_decimal("1"), item.get("unit") or "",
                                             base.get("unit") or "", unit_rules)
                    except ValueError as exc:
                        issues.append(str(exc))
                        _ensure_clarification(db, invoice, f"unit:{identity}",
                            f"Obtain a staff-approved unit conversion for {identity or 'item'}",
                            "staff", "staff-approved unit conversion rule")
                        continue
                    if kind == "purchase_order":
                        difference = to_decimal(base["amount"]) - to_decimal(item["amount"])
                        try:
                            difference_cents = to_cents(difference) if difference > 0 else 0
                        except ValueError:
                            issues.append("Claim requires an explicit rounding/tax decision")
                            continue
                        hyps = price_hypotheses(
                            identity, to_decimal(base["amount"]), to_decimal(item["amount"]),
                            _source(row),
                            tax_basis_plausible=tax_basis_plausible(original, doc, difference),
                            scheme_match=difference > 0 and
                            scheme_amounts.get(identity) == difference_cents)
                        if len(hyps) == 1 and not hyps[0]["needs_staff"]:
                            add(identity, "price", to_decimal(base["amount"]) - to_decimal(item["amount"]),
                                row, "Invoice/PO line variance")
                        elif hyps:
                            note_hypotheses(identity, "price", hyps)
                            issues.append("Competing explanations require a staff decision")
                    elif kind == "discount_agreement":
                        discount = to_decimal(item["amount"])
                        if discount > to_decimal(base["amount"]):
                            issues.append("Scheme discount exceeds the invoice line")
                        else:
                            add(identity, "discount", discount, row, "Documented scheme discount claim; approval required")
                    else:
                        quantity, base_quantity = to_decimal(item["quantity"]), to_decimal(base["quantity"])
                        if item.get("unit") or base.get("unit"):
                            quantity, _ = convert_quantity(
                                quantity, item.get("unit") or "", base.get("unit") or "", unit_rules)
                        price = to_decimal(base["unit_price"])
                        if quantity > base_quantity or not price:
                            issues.append("Delivery/return quantity or unit price is inconsistent")
                            continue
                        missing = base_quantity - quantity if kind == "delivery_note" else quantity
                        damage_hint = "damag" in normalize(
                            item.get("description", "") + " " + doc.get("text", ""))
                        if tax_present:
                            issues.append("Delivery/return claim needs staff tax and freight allocation")
                            try:
                                affected = to_cents(missing * price)
                            except ValueError:
                                affected = 0
                            _ensure_clarification(db, invoice, f"allocate:{identity}",
                                f"Obtain a staff tax and freight allocation for {identity or 'item'}",
                                "staff", "invoice tax and freight schedule", affected)
                        else:
                            hyps = fulfilment_hypotheses(identity, missing, price,
                                                         _source(row), kind, damage_hint)
                            if len(hyps) == 1:
                                add(identity, "fulfilment", missing * price, row, hyps[0]["label"])
                            else:
                                note_hypotheses(identity, "fulfilment", hyps)
                                issues.append("Competing explanations require a staff decision")
            elif kind == "message":
                text = doc.get("text", "")
                damage_hit = re.search(r"(\d+)\s+units?", text, re.I)
                damage = damage_hit if damage_hit and "damag" in text.casefold() else None
                short = re.search(r"(?:short\s+by\s+|missing\s+)(\d+)\s+units|(?:\b(\d+)\s+units\s+short)", text, re.I)
                if damage or short:
                    count = damage.group(1) if damage else (short.group(1) or short.group(2))
                    if len(lines) == 1 and lines[0].get("unit_price") and lines[0].get("quantity"):
                        target = identity_key(lines[0], aliases)
                        base_line, base_qty = lines[0], to_decimal(lines[0]["quantity"])
                    else:
                        hits = match_sku_in_text(text, list(originals))
                        if len(hits) != 1:
                            issues.append("Customer shortage claim does not identify a uniquely priced invoice item")
                            _ensure_clarification(db, invoice, f"attribute:{row.id}",
                                "Attribute the customer shortage claim to one invoice line",
                                "staff", _source(row))
                            continue
                        target = hits[0]
                        base_line, base_qty = originals[target], to_decimal(originals[target].get("quantity", 0))
                        if not originals[target].get("unit_price") or not base_qty:
                            issues.append("Customer shortage claim does not identify a uniquely priced invoice item")
                            continue
                    missing = to_decimal(count)
                    if missing > base_qty:
                        issues.append("Claimed missing quantity exceeds invoice quantity")
                    elif damage:
                        alleged = db.query(models.CaseEvidence).filter_by(
                            tenant_id=invoice.tenant_id, invoice_id=invoice.id,
                            claim_type="damage_claim",
                            source_reference=_source(row)).first()
                        if alleged is None:
                            db.add(models.CaseEvidence(tenant_id=invoice.tenant_id, invoice_id=invoice.id,
                                claim_type="damage_claim", title="Customer alleges damaged goods",
                                description="Customer alleges damaged goods; supporting damage evidence required, not an automatic credit",
                                source_type="customer_message", source_reference=_source(row),
                                source_snippet=text[:250],
                                amount_cents=to_cents(missing * to_decimal(base_line["unit_price"])),
                                verified=False, trust_state="alleged",
                                currency=invoice.currency or "INR"))
                        _ensure_clarification(db, invoice, f"damage:{target}",
                            f"Obtain damage evidence for {target} on invoice {invoice.invoice_number}",
                            "customer", "customer damage photo or inspection note",
                            to_cents(missing * to_decimal(base_line["unit_price"])))
                    else:
                        add(target, "fulfilment", missing * to_decimal(base_line["unit_price"]), row,
                            "Customer alleges short delivery; not a verified credit")
                elif re.search(r"damag|return|discount|scheme|short|wrong|disput", text, re.I):
                    issues.append("Customer claim needs item-level supporting evidence")
        except (KeyError, ValueError, InvalidOperation):
            issues.append("Supporting evidence has missing or invalid line arithmetic")
    for identity, category in claims:
        if len({v[0] for v in claims[(identity, category)]}) > 1:
            issues.append("Sources disagree on the same item and claim")
            bucket = claims[(identity, category)]
            refs = [_source(v[1]) for v in bucket]
            conflicting = [{"key": f"source_{i}", "label": v[2],
                            "amount_cents": v[0], "needs_staff": True,
                            "supporting": [ref],
                            "contradicting": [r for r in refs if r != ref]}
                           for i, (v, ref) in enumerate(zip(bucket, refs))]
            note_hypotheses(identity, category, conflicting)
        if sum(1 for k in claims if k[0] == identity) > 1:
            issues.append("Overlapping claim types on one item require staff allocation")
            overlapping = [{"key": key[1], "label": f"Allocate as {key[1]}",
                            "amount_cents": claims[key][0][0], "needs_staff": True,
                            "supporting": [_source(claims[key][0][1])],
                            "contradicting": []}
                           for key in claims if key[0] == identity]
            note_hypotheses(identity, category, overlapping)
    for (identity, category), hyps in hypotheses.items():
        if len({h["amount_cents"] for h in hyps}) > 1 or any(h.get("needs_staff") for h in hyps) \
                or len(hyps) > 1:
            touched_explanations.add(_ensure_explanation(
                db, invoice, identity, category, hyps).id)
    for row in db.query(models.CompetingExplanation).filter_by(
            tenant_id=invoice.tenant_id, invoice_id=invoice.id, status="open").all():
        if row.id not in touched_explanations:
            row.status = "superseded"
    total = sum(values[0][0] for values in claims.values())
    # Previously posted allocations remain authoritative on reinvestigation.
    allocated = sum(e.disputed_delta_cents or 0 for e in db.query(models.ReceivableEntry).filter_by(
        tenant_id=invoice.tenant_id, invoice_id=invoice.id).all())
    remaining_claim = total + allocated
    if claims and not 0 <= remaining_claim <= balance_cents(db, invoice):
        issues.append("Proposed claim conflicts with posted allocations or outstanding balance")
    if issues:
        invoice.investigation_hold = True
        invoice.investigation_reason = "; ".join(dict.fromkeys(issues))
        db.add(models.AuditEvent(tenant_id=invoice.tenant_id, actor="investigator_agent",
            action="investigation_needs_review", entity_type="invoice", entity_id=str(invoice.id),
            details=invoice.investigation_reason))
        db.flush()
        raise ValueError(invoice.investigation_reason)
    # Only an explicit staff review clears a prior conflict hold.
    if invoice.investigation_hold:
        raise ValueError(invoice.investigation_reason or "Investigation requires staff review")
    if claims:
        invoice.disputed_cents = remaining_claim
        invoice.dispute_open = remaining_claim > 0
        if remaining_claim:
            invoice.status = "disputed"
        for values in claims.values():
            for amount, row, description in values:
                source = _source(row)
                title = description + ": " + str(amount)
                existing = db.query(models.CaseEvidence).filter_by(tenant_id=invoice.tenant_id,
                    invoice_id=invoice.id, claim_type="dispute_item", source_reference=source,
                    title=title).first()
                if existing is None:
                    db.add(models.CaseEvidence(tenant_id=invoice.tenant_id, invoice_id=invoice.id,
                        claim_type="dispute_item", title=title, description=description,
                        source_type="uploaded_claim", source_reference=source, amount_cents=amount,
                        verified=False, trust_state="extracted", currency=invoice.currency or "INR"))
    db.flush()
    from app.services.case_lifecycle import checkpoint
    checkpoint(db, invoice, "investigated", "investigator_agent")
    return int(invoice.disputed_cents or 0)
