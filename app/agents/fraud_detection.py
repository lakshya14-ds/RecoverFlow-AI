"""
RecoverFlow - Receivables and Collections
"""
from typing import Dict, Any
from app.skills.detect_duplicate_invoice import detect_duplicate_invoice
from app.ml.isolation_forest import FraudDetector
import pandas as pd
from app.config import settings

def run_fraud_agent(state: Dict[str, Any], existing_invoices: list[dict] = None) -> Dict[str, Any]:
    """Check for duplicate invoices and amount anomalies."""
    if existing_invoices is None:
        existing_invoices = []
        
    invoice_data = state.get("invoice_data", {})
    
    # 1. Duplicates
    dup_result = detect_duplicate_invoice(invoice_data, existing_invoices)
    
    # 2. Isolation Forest Anomaly
    detector = FraudDetector()
    if len(existing_invoices) >= 10:
        detector.fit(pd.DataFrame(existing_invoices))
    fraud_res = detector.predict_score(invoice_data)
    
    is_duplicate = dup_result.get("is_duplicate", False)
    fraud_score = fraud_res.get("fraud_score", 0.0)
    
    requires_human_review = state.get("requires_human_review", False)
    if is_duplicate or fraud_score > settings.FRAUD_ALERT_THRESHOLD:
        requires_human_review = True
        
    return {
        "is_duplicate": is_duplicate,
        "duplicate_of_id": dup_result.get("duplicate_of_id"),
        "fraud_score": fraud_score,
        "requires_human_review": requires_human_review
    }
