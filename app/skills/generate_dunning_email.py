"""
RecoverFlow - Receivables and Collections
"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from app.llm_client import retry_llm_call
import logging

class DunningEmailOutput(BaseModel):
    subject: str = Field(description="The subject line of the email")
    body: str = Field(description="The main body text of the email")
    tone: str = Field(description="The tone of the email")

DUNNING_STAGES = {
    1: {
        "trigger_days": 7,     # Days after the due date
        "tone": "friendly",
        "offline_template": "Subject: Friendly Reminder — Invoice {invoice_number}\n\nHi {client_name},\n\nJust a quick note that Invoice {invoice_number} for {currency} {amount:.2f} was due on {due_date}.\nIf you've already sent payment, please disregard this message.\n\nIf you have any questions, please don't hesitate to reach out.\n\nBest regards,\n{company_name}"
    },
    2: {
        "trigger_days": 15,
        "tone": "formal",
        "offline_template": "Subject: Second Notice — Invoice {invoice_number} Past Due\n\nDear {client_name},\n\nThis is a reminder that Invoice {invoice_number} for {currency} {amount:.2f}, originally due {due_date}, remains outstanding.\nIf you have already paid or have questions about the balance, please reply.\n\nSincerely,\n{company_name}"
    },
    3: {
        "trigger_days": 30,
        "tone": "urgent",
        "offline_template": "Subject: Follow-up on Invoice {invoice_number}\n\nDear {client_name},\n\nOur records show a balance of {currency} {amount:.2f} on Invoice {invoice_number}, due {due_date}.\nIf you have paid, returned the order, or believe the balance is incorrect, please reply so we can review it.\nPlease contact us to discuss the outstanding balance.\n\n{company_name}"
    },
    4: {
        "trigger_days": 45,
        "tone": "formal",
        "offline_template": "Subject: Please Contact Us About Invoice {invoice_number}\n\nDear {client_name},\n\nOur records show a balance of {currency} {amount:.2f} on Invoice {invoice_number}, due {due_date}.\nWe would like to resolve this with you. Please reply if you need a copy of the invoice, have already paid, or want to discuss the balance.\n\n{company_name}"
    },
}

@retry_llm_call
def _call_llm_with_retries(llm_client: Any, prompt_value: Any) -> DunningEmailOutput:
    structured_llm = llm_client.with_structured_output(DunningEmailOutput)
    return structured_llm.invoke(prompt_value)

def generate_dunning_email(
    invoice: Dict[str, Any],
    client: Dict[str, Any],
    days_overdue: int,
    stage: int,
    company_name: str,
    llm_client: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Generate a collection email and return its subject, body, tone, and stage.
    """
    if stage < 1 or stage > 4:
        raise ValueError("Stage must be between 1 and 4")

    stage_info = DUNNING_STAGES[stage]
    tone = stage_info["tone"]
    template = stage_info["offline_template"]

    if llm_client:
        try:
            prompt = ChatPromptTemplate.from_messages([
                ("system", f"You are an accounts receivable agent for {company_name}. Generate a {tone} dunning email."),
                ("human", f"Client Name: {client.get('name', 'Client')}\nInvoice Number: {invoice.get('invoice_number', 'UNKNOWN')}\nAmount: {invoice.get('currency', 'USD')} {invoice.get('total_amount', 0.0):.2f}\nDue Date: {invoice.get('due_date', 'UNKNOWN')}\nDays Overdue: {days_overdue}\nStage: {stage}")
            ])
            prompt_value = prompt.invoke({})
            
            output = _call_llm_with_retries(llm_client, prompt_value)
            
            return {
                "subject": output.subject,
                "body": output.body,
                "tone": output.tone,
                "stage": stage
            }
        except Exception as e:
            logging.error(f"LLM dunning generation failed after retries: {e}. Falling back to offline template.")

    # Use a local template when the LLM is unavailable or fails.
    body = template.format(
        client_name=client.get("name", "Client"),
        invoice_number=invoice.get("invoice_number", "UNKNOWN"),
        amount=invoice.get("total_amount", 0.0),
        currency=invoice.get("currency", "USD"),
        due_date=invoice.get("due_date", "UNKNOWN"),
        days_overdue=days_overdue,
        company_name=company_name
    )
    
    subject_line = body.split("\n")[0].replace("Subject: ", "")
    actual_body = "\n".join(body.split("\n")[1:]).strip()

    return {
        "subject": subject_line,
        "body": actual_body,
        "tone": tone,
        "stage": stage
    }
