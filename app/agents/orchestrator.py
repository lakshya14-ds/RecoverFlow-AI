from decimal import Decimal
"""
RecoverFlow - Receivables and Collections
"""
from typing import TypedDict, Dict, Any, List
import logging
from langgraph.graph import StateGraph, END
from app.agents.ocr_extraction import run_ocr_agent
from app.agents.fraud_detection import run_fraud_agent
from app.agents.matching_reconcile import run_matching_agent
from app.agents.semantic_approval import evaluate_invoice
from app.database.db_manager import SessionLocal
from app.database.models import Invoice
from app.database import models
from app.plugins.afis_reader import AFISReader
from datetime import date, timedelta

# Shared workflow state.
class RecoverFlowAgentState(TypedDict, total=False):
    tenant_id: str
    invoice_type: str
    invoice_path: str
    invoice_data: Dict[str, Any]
    extracted_confidence: float
    fraud_score: float
    is_duplicate: bool
    duplicate_of_id: int
    matched_afis_id: int
    reconciliation_confidence: float
    matched_amount: Decimal
    match_type: str
    variance_amount: Decimal
    requires_human_review: bool
    dunning_stage: int
    dunning_email_sent: bool
    semantic_approval_status: str
    semantic_reason: str
    cfo_insights: List[str]
    dso_forecast: list
    errors: List[str]

# Workflow nodes.
def ocr_node(state: RecoverFlowAgentState) -> Dict[str, Any]:
    try:
        res = run_ocr_agent(state)
        return {
            "invoice_data": res.get("invoice_data", {}),
            "extracted_confidence": res.get("extracted_confidence", 0.0),
            "errors": state.get("errors", []) + res.get("errors", [])
        }
    except Exception as e:
        logging.error(f"OCR Node Error: {e}")
        return {"errors": state.get("errors", []) + [f"OCR Error: {str(e)}"], "requires_human_review": True}

def fraud_node(state: RecoverFlowAgentState) -> Dict[str, Any]:
    try:
        with SessionLocal() as db:
            existing = db.query(Invoice).filter(
                Invoice.tenant_id == state.get("tenant_id", "local"),
                Invoice.counterparty_name == state.get("invoice_data", {}).get("counterparty_name")
            ).all()
            existing_data = [
                {"id": row.id, "invoice_number": row.invoice_number,
                 "counterparty_name": row.counterparty_name, "total_amount": row.total_amount}
                for row in existing
            ]
        res = run_fraud_agent(state, existing_data)
        return {
            "fraud_score": res.get("fraud_score", 0.0),
            "is_duplicate": res.get("is_duplicate", False),
            "duplicate_of_id": res.get("duplicate_of_id"),
            "requires_human_review": res.get("requires_human_review", False)
        }
    except Exception as e:
        logging.error(f"Fraud Node Error: {e}")
        return {"errors": state.get("errors", []) + [f"Fraud Check Error: {str(e)}"], "requires_human_review": True}

def match_node(state: RecoverFlowAgentState) -> Dict[str, Any]:
    try:
        invoice = state.get("invoice_data", {})
        due = date.fromisoformat(invoice["due_date"])
        start = date.fromisoformat(invoice.get("issue_date") or invoice["due_date"]) - timedelta(days=30)
        transactions = (AFISReader().get_transactions(
            start.isoformat(), (due + timedelta(days=60)).isoformat(),
            tx_type="income" if state.get("invoice_type") == "AR" else "expense")
                        if state.get("tenant_id", "local") == "local" else [])
        with SessionLocal() as db:
            used_ids = {row[0] for row in db.query(models.Reconciliation.afis_transaction_id).filter(
                models.Reconciliation.tenant_id == state.get("tenant_id", "local"),
                models.Reconciliation.status == "approved").all()}
        transactions = [tx for tx in transactions if tx.get("id") not in used_ids]
        res = run_matching_agent(state, transactions)
        return {
            "matched_afis_id": res.get("matched_afis_id"),
            "reconciliation_confidence": res.get("reconciliation_confidence", 0.0),
            "matched_amount": res.get("matched_amount"),
            "match_type": res.get("match_type"),
            "variance_amount": res.get("variance_amount"),
            "requires_human_review": state.get("requires_human_review") or res.get("requires_human_review", False)
        }
    except Exception as e:
        logging.error(f"Match Node Error: {e}")
        return {"errors": state.get("errors", []) + [f"Match Error: {str(e)}"], "requires_human_review": True}

def semantic_approval_node(state: RecoverFlowAgentState) -> Dict[str, Any]:
    try:
        res = evaluate_invoice(state, state.get("invoice_data", {}))
        return {
            "semantic_approval_status": res.get("semantic_approval_status"),
            "semantic_reason": res.get("semantic_reason"),
            "requires_human_review": bool(state.get("requires_human_review")) or res.get("semantic_approval_status") == "MANUAL_REVIEW"
        }
    except Exception as e:
        return {"errors": state.get("errors", []) + [f"Semantic Error: {str(e)}"], "requires_human_review": True}

def human_review_node(state: RecoverFlowAgentState) -> Dict[str, Any]:
    return {"requires_human_review": True}

# Routing rules.
def route_after_ocr(state: RecoverFlowAgentState) -> str:
    if state.get("extracted_confidence", 0.0) < 0.6 or "OCR Error" in "".join(state.get("errors", [])):
        return "human_review"
    return "fraud_check"

def route_after_fraud(state: RecoverFlowAgentState) -> str:
    if state.get("is_duplicate") or state.get("fraud_score", 0.0) > 0.65 or "Fraud Check Error" in "".join(state.get("errors", [])):
        return "human_review"
    return "reconcile"

# Workflow graph.
workflow = StateGraph(RecoverFlowAgentState)

workflow.add_node("ocr", ocr_node)
workflow.add_node("fraud", fraud_node)
workflow.add_node("match", match_node)
workflow.add_node("semantic_approval", semantic_approval_node)
workflow.add_node("human_review", human_review_node)

workflow.set_entry_point("ocr")

# Conditional transitions.
workflow.add_conditional_edges("ocr", route_after_ocr, {"human_review": "human_review", "fraud_check": "fraud"})
workflow.add_conditional_edges("fraud", route_after_fraud, {"human_review": "human_review", "reconcile": "match"})
workflow.add_edge("match", "semantic_approval")

def route_after_semantic(state: RecoverFlowAgentState) -> str:
    if state.get("requires_human_review") or not state.get("matched_afis_id") or state.get("errors"):
        return "human_review"
    return "complete"

workflow.add_conditional_edges("semantic_approval", route_after_semantic, {"human_review": "human_review", "complete": END})
workflow.add_edge("human_review", END)

recoverflow_orchestrator = workflow.compile()
