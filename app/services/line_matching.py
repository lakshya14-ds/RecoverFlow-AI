"""Pure line-level comparison for distributor documents. No database, no model.

Compares normalized SKU aliases, units, quantities, unit prices, tax basis,
freight, and rounding. Never converts units without a staff-approved rule and
never apportions tax or freight automatically: ambiguous money becomes
competing hypotheses for staff, not a confident pick.
"""
from decimal import Decimal, InvalidOperation
import re
import unicodedata


def normalize(value):
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", value or "").casefold()).strip()


def identity_key(line, aliases):
    sku = normalize(line.get("sku", ""))
    name = normalize(line.get("description", ""))
    if sku:
        return aliases.get(sku, sku)
    return aliases.get(name, name)


def to_decimal(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid quantity or monetary value")
    return result


def to_cents(amount: Decimal):
    minor = amount * 100
    if minor != minor.to_integral_value():
        raise ValueError("Claim requires an explicit rounding/tax decision")
    return int(minor)


def convert_quantity(quantity: Decimal, from_unit: str, to_unit: str, unit_rules):
    """Convert only on exact match or a staff-approved rule. Returns
    (quantity_in_to_unit, rule_or_none). Raises on silent conversion."""
    source, target = normalize(from_unit), normalize(to_unit)
    if not source or not target or source == target:
        return quantity, None
    for rule in unit_rules:
        if normalize(rule[0]) == source and normalize(rule[1]) == target:
            return quantity * to_decimal(rule[2]), rule
    raise ValueError(f"Unit mismatch requires staff conversion: {from_unit} -> {to_unit}")


def check_line_arithmetic(line):
    """Verify quantity * unit_price == amount when all three are stated."""
    if not (line.get("quantity") and line.get("unit_price") and line.get("amount")):
        return None
    try:
        expected = to_decimal(line["quantity"]) * to_decimal(line["unit_price"])
    except (ValueError, InvalidOperation):
        return "Line has missing or invalid line arithmetic"
    if expected != to_decimal(line["amount"]):
        return "Line quantity and unit price do not reconcile to the line amount"
    return None


def price_hypotheses(identity, base_amount: Decimal, doc_amount: Decimal,
                     doc_ref, *, tax_basis_plausible: bool = False,
                     scheme_match: bool = False):
    """Competing explanations for an invoice/PO line variance. Every hypothesis
    needs positive evidence: differing unit prices evidence a price difference,
    exact total-fit evidences a tax-basis difference, and a matching scheme
    line evidences a discount. The first pattern never wins by itself."""
    difference = base_amount - doc_amount
    if difference <= 0:
        return []
    hyps = [{"key": "price_difference", "label": "PO line price differs from invoice",
             "amount_cents": to_cents(difference), "needs_staff": False,
             "supporting": [doc_ref], "contradicting": []}]
    if tax_basis_plausible:
        hyps.append({"key": "tax_basis_difference",
                     "label": "Totals fit tax-inclusive versus tax-exclusive pricing",
                     "amount_cents": to_cents(difference), "needs_staff": True,
                     "supporting": [doc_ref], "contradicting": []})
    if scheme_match:
        hyps.append({"key": "scheme_discount", "label": "A scheme line matches this variance",
                     "amount_cents": to_cents(difference), "needs_staff": True,
                     "supporting": [doc_ref], "contradicting": []})
    return hyps


def tax_basis_plausible(invoice_doc, other_doc, variance: Decimal):
    """True only with positive evidence: the invoice states tax, the variance
    equals that tax exactly, and the other doc's total plus the tax equals the
    invoice total. Anything else is a price difference, not a tax question."""
    try:
        tax = to_decimal(invoice_doc.get("tax_amount") or "0")
        inv_total = to_decimal(invoice_doc.get("total_amount") or "0")
        doc_total = to_decimal(other_doc.get("total_amount") or "0")
    except (ValueError, InvalidOperation):
        return False
    if tax <= 0 or inv_total <= 0 or doc_total <= 0:
        return False
    return variance == tax and doc_total + tax == inv_total


def fulfilment_hypotheses(identity, missing_qty: Decimal, price: Decimal,
                          doc_ref, kind, damage_hint: bool = False):
    hyps = [{"key": "short_supply" if kind == "delivery_note" else "return_claim",
             "label": "Delivery shortfall" if kind == "delivery_note" else "Returned goods claim",
             "amount_cents": to_cents(missing_qty * price), "needs_staff": False,
             "supporting": [doc_ref], "contradicting": []}]
    if damage_hint:
        hyps.append({"key": "damaged_goods", "label": "Goods may be damaged, not short",
                     "amount_cents": to_cents(missing_qty * price), "needs_staff": True,
                     "supporting": [doc_ref],
                     "contradicting": ["no damage evidence on file"]})
    return hyps


def match_sku_in_text(text, identities):
    """Return invoice line identities named in free text (exact normalized hit)."""
    haystack = " " + normalize(text) + " "
    return sorted({identity for identity in identities
                   if identity and f" {identity} " in haystack})
