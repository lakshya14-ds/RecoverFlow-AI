"""
RecoverFlow - Receivables and Collections
"""
from typing import Dict, Any
from app.skills.match_invoice_payment import match_invoice_to_payment
from app.config import settings

def run_matching_agent(state: Dict[str, Any], afis_transactions: list[dict] = None) -> Dict[str, Any]:
    """Try to match an invoice with AFIS transactions."""
    if afis_transactions is None:
        afis_transactions = []
        
    invoice_data = state.get("invoice_data", {})
    
    matches = match_invoice_to_payment(invoice_data, afis_transactions)
    best_match = matches[0]
    
    matched_id = best_match.get("afis_transaction_id")
    confidence = best_match.get("confidence_score", 0.0)
    
    requires_human_review = state.get("requires_human_review", False)
    
    if confidence < settings.HUMAN_REVIEW_THRESHOLD:
        requires_human_review = True
        matched_id = None  # Do not approve a low-confidence match.
        
    return {
        "matched_afis_id": matched_id,
        "reconciliation_confidence": confidence,
        "matched_amount": best_match.get("matched_amount"),
        "match_type": best_match.get("match_type"),
        "variance_amount": best_match.get("variance_amount"),
        "requires_human_review": requires_human_review
    }
