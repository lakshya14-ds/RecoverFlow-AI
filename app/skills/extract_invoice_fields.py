"""
RecoverFlow - Receivables and Collections
"""
from dataclasses import dataclass, field
from typing import Optional
import re
import logging
import dateutil.parser

@dataclass
class InvoiceFields:
    invoice_number: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_email: Optional[str] = None
    counterparty_tax_id: Optional[str] = None
    issue_date: Optional[str] = None        # YYYY-MM-DD
    due_date: Optional[str] = None          # YYYY-MM-DD
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    po_number: Optional[str] = None
    description: Optional[str] = None
    currency: str = "USD"
    bank_routing: Optional[str] = None      # For bank-detail validation
    bank_account: Optional[str] = None      # Last four digits only
    confidence_scores: dict = field(default_factory=dict)
    raw_text: str = ""

def clean_amount(val_str: str) -> Optional[float]:
    clean_str = re.sub(r'[^\d.]', '', val_str)
    try:
        return float(clean_str)
    except ValueError:
        return None

def extract_invoice_fields(pdf_path: str) -> InvoiceFields:
    """
    Extract structured fields from a PDF invoice using Tesseract and
    simple text parsing rules.
    """
    from app.config import settings

    try:
        import pdf2image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("PDF OCR requires pdf2image and pytesseract; install requirements.txt") from exc
    fields = InvoiceFields()

    try:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
        
        images = pdf2image.convert_from_path(pdf_path, dpi=settings.OCR_DPI)
        raw_text = ""
        for img in images:
            raw_text += pytesseract.image_to_string(img, lang=settings.OCR_LANG)
        
        fields.raw_text = raw_text

        # Basic field extraction rules.
        # Invoice number.
        inv_match = re.search(r'(?:Invoice|INV)[^A-Za-z0-9]*([A-Z0-9-]{3,10})', raw_text, re.IGNORECASE)
        if inv_match:
            fields.invoice_number = inv_match.group(1).strip()
            fields.confidence_scores["invoice_number"] = 0.85

        # Amounts
        amounts = re.findall(r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', raw_text)
        if amounts:
            numeric_amounts = sorted([clean_amount(a) for a in amounts if clean_amount(a)], reverse=True)
            if numeric_amounts:
                fields.total_amount = numeric_amounts[0]
                fields.confidence_scores["total_amount"] = 0.90
                # Missing totals receive low confidence and require review.
        
        # Due date and issue date.
        dates = re.findall(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}, \d{4})', raw_text, re.IGNORECASE)
        if dates:
            try:
                parsed_dates = sorted([dateutil.parser.parse(d).date() for d in dates])
                if len(parsed_dates) >= 2:
                    fields.issue_date = parsed_dates[0].isoformat()
                    fields.due_date = parsed_dates[-1].isoformat()
                else:
                    fields.due_date = parsed_dates[0].isoformat()
                fields.confidence_scores["issue_date"] = 0.8
                fields.confidence_scores["due_date"] = 0.8
            except Exception:
                pass

        # Assume the first non-empty line is the counterparty name.
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        if lines:
            fields.counterparty_name = lines[0]
            fields.confidence_scores["counterparty_name"] = 0.70

    except Exception as e:
        logging.error(f"OCR Extraction failed: {e}")
        raise RuntimeError(f"OCR extraction failed: {e}") from e

    return fields
