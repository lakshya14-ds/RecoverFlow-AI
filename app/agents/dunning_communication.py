"""
RecoverFlow - Receivables and Collections
"""
from typing import Dict, Any
from app.skills.generate_dunning_email import generate_dunning_email

def run_dunning_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Draft a collection email for the current stage."""
    invoice_data = state.get("invoice_data", {})
    days_overdue = invoice_data.get("days_overdue", 0)
    stage = state.get("dunning_stage", 1)
    
    company_name = "Accounts Receivable"
    
    email_data = generate_dunning_email(
        invoice=invoice_data,
        client={"name": invoice_data.get("counterparty_name", "Client")},
        days_overdue=days_overdue,
        stage=stage,
        company_name=company_name
    )
    
    # Sending is a separate, explicit API action.
    
    return {
        "dunning_email_sent": False,
        "dunning_stage": stage,
        "email_data": email_data
    }
