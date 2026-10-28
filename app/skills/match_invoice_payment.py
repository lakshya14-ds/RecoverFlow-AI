from decimal import Decimal
"""
RecoverFlow - Receivables and Collections
"""
import dateutil.parser

def match_invoice_to_payment(
    invoice: dict,
    afis_transactions: list[dict],
    fuzzy_amount_tolerance: float = 0.05,
    fuzzy_date_tolerance_days: int = 30,
) -> list[dict]:
    """
    Match an invoice against AFIS transactions and return candidates
    sorted by descending confidence.
    """
    matches = []
    inv_amount = Decimal(str(invoice.get("total_amount", 0)))
    inv_date_str = invoice.get("due_date")
    inv_date = None
    if inv_date_str:
        try:
            inv_date = dateutil.parser.parse(inv_date_str).date()
        except:
            pass

    for tx in afis_transactions:
        tx_amount = abs(Decimal(str(tx.get("amount", 0))))
        tx_date_str = tx.get("date")
        tx_date = None
        if tx_date_str:
            try:
                tx_date = dateutil.parser.parse(tx_date_str).date()
            except:
                pass
        
        amount_diff = abs(inv_amount - tx_amount)
        amount_exact = amount_diff < Decimal("0.01")
        amount_fuzzy = inv_amount > 0 and (amount_diff / inv_amount) <= Decimal(str(fuzzy_amount_tolerance))

        date_diff_days = None
        if inv_date and tx_date:
            date_diff_days = abs((inv_date - tx_date).days)
        
        date_exact = date_diff_days is not None and date_diff_days <= 5
        date_fuzzy = date_diff_days is not None and date_diff_days <= fuzzy_date_tolerance_days

        score = 0.0
        match_type = "none"

        # Apply amount and date matching strategies.
        if amount_exact and date_exact:
            score = 0.97
            match_type = "exact_amount_date"
        elif amount_exact and date_fuzzy:
            score = 0.88
            match_type = "exact_amount_fuzzy_date"
        elif amount_fuzzy and date_exact:
            score = 0.82
            match_type = "fuzzy_amount_exact_date"
        elif amount_fuzzy and date_fuzzy:
            score = 0.70
            match_type = "fuzzy_amount_fuzzy_date"
        
        if score > 0.0:
            matches.append({
                "afis_transaction_id": tx.get("id"),
                "confidence_score": score,
                "match_type": match_type,
                "variance_amount": amount_diff,
                "matched_amount": tx_amount,
                "explanation": f"Matched by {match_type} (Variance: {amount_diff:.2f})"
            })
            
    matches.sort(key=lambda x: x["confidence_score"], reverse=True)
    if not matches:
        return [{"confidence_score": 0.0, "match_type": "none"}]
    
    return matches[:3]
