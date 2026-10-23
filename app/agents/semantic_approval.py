"""
RecoverFlow - Receivables and Collections
Semantic Approval Agent (Epic 5)
"""
from typing import Dict, Any

def evaluate_invoice(state: Dict[str, Any], invoice_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply a deterministic invoice review policy.
    """
    amount = invoice_data.get("total_amount")
    vendor = invoice_data.get("counterparty_name") or "unknown"
    
    # Deterministic review policy; no LLM approval is claimed.
    if amount is None or float(amount) <= 0 or float(amount) > 5000 or any(
        word in vendor.lower() for word in ("urgent", "urgente")
    ):
        approval_status = "MANUAL_REVIEW"
        reason = "Amount or vendor requires manual review."
    else:
        approval_status = "AUTO_APPROVE"
        reason = "Passed the configured review policy."
        
    return {
        "semantic_approval_status": approval_status,
        "semantic_reason": reason
    }
