"""
RecoverFlow - Receivables and Collections
"""

def detect_duplicate_invoice(
    invoice: dict,
    existing_invoices: list[dict]
) -> dict:
    """
    Compare the invoice with existing invoices from the same counterparty,
    using exact and fuzzy invoice-number matches.
    """
    inv_num = str(invoice.get("invoice_number", "")).strip()
    inv_amount = float(invoice.get("total_amount", 0.0))
    inv_counterparty = str(invoice.get("counterparty_name", "")).strip().lower()

    if not inv_num or not inv_counterparty:
        return {"is_duplicate": False}

    for existing in existing_invoices:
        ext_num = str(existing.get("invoice_number", "")).strip()
        ext_amount = float(existing.get("total_amount", 0.0))
        ext_counterparty = str(existing.get("counterparty_name", "")).strip().lower()

        if inv_counterparty != ext_counterparty:
            continue

        # Exact match.
        if inv_num == ext_num and abs(inv_amount - ext_amount) < 0.01:
            return {
                "is_duplicate": True, 
                "duplicate_of_id": existing.get("id"),
                "similarity_score": 1.0, 
                "method": "exact_match"
            }

        # Fuzzy number match above 85% with nearly equal amounts.
        from difflib import SequenceMatcher
        ratio = SequenceMatcher(None, inv_num, ext_num).ratio() * 100
        amount_diff = abs(inv_amount - ext_amount) / (inv_amount if inv_amount > 0 else 1)
        
        if ratio > 85 and amount_diff < 0.01:
            return {
                "is_duplicate": True, 
                "duplicate_of_id": existing.get("id"),
                "similarity_score": ratio / 100.0, 
                "method": "fuzzy_match"
            }

    return {"is_duplicate": False}
