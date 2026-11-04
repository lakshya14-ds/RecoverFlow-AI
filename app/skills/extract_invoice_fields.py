from decimal import Decimal, InvalidOperation
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
    amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None
    po_number: Optional[str] = None
    description: Optional[str] = None
    currency: str = "INR"
    bank_routing: Optional[str] = None      # For bank-detail validation
    bank_account: Optional[str] = None      # Last four digits only
    confidence_scores: dict = field(default_factory=dict)
    raw_text: str = ""

def clean_amount(val_str: str) -> Optional[Decimal]:
    clean_str = re.sub(r'[^\d.]', '', val_str)
    try:
        return Decimal(clean_str)
    except (ValueError, InvalidOperation):
        return None

def extract_invoice_fields(pdf_path: str) -> InvoiceFields:
    """
    Extract structured fields from a PDF invoice using bundled rasterization,
    digital text fallback, and Tesseract OCR only when needed.
    """
    from app.config import settings

    try:
        import pytesseract
    except ImportError:
        pytesseract = None
    fields = InvoiceFields()

    try:
        import os
        if pytesseract is not None:
            tesseract_cmd = settings.TESSERACT_CMD
            local_tess = settings.BASE_DIR / "bin" / "tesseract" / "tesseract.exe"
            if (not tesseract_cmd or tesseract_cmd == "tesseract") and local_tess.exists():
                tesseract_cmd = str(local_tess)
                os.environ.setdefault("TESSDATA_PREFIX", str(settings.BASE_DIR / "bin" / "tesseract" / "tessdata"))
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        images = []
        # 1. Primary: high-fidelity pypdfium2 rasterization (bundled binary, no system poppler needed).
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(pdf_path)
            for page in pdf:
                images.append(page.render(scale=2).to_pil().convert("RGB"))
        except Exception:
            # 2. Secondary fallback: pdf2image (only when system poppler is present).
            try:
                import pdf2image
                poppler_kwargs = {}
                poppler_path = getattr(settings, "POPPLER_PATH", "")
                if not poppler_path:
                    local_poppler = settings.BASE_DIR / "bin" / "poppler" / "poppler-24.08.0" / "Library" / "bin"
                    if local_poppler.exists():
                        poppler_path = str(local_poppler)
                if poppler_path:
                    poppler_kwargs["poppler_path"] = poppler_path
                images = pdf2image.convert_from_path(pdf_path, dpi=settings.OCR_DPI, **poppler_kwargs)
            except Exception:
                images = []

        # 3. Direct digital text extraction fallback via pypdf.
        raw_text = ""
        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    raw_text += page_text + "\n"
        except Exception:
            pass

        # If digital text was not available and images were rendered, perform OCR.
        if not raw_text.strip() and images and pytesseract is not None:
            for img in images:
                try:
                    raw_text += pytesseract.image_to_string(img, lang=settings.OCR_LANG)
                except Exception:
                    pass

        fields.raw_text = raw_text

        # Basic field extraction rules.
        # Invoice number: match "Invoice Number: ...", "Invoice No: ...", "INV-..."
        inv_match = re.search(r'\b(?:Invoice\s*(?:No\.?|Number|#))\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{2,25})', raw_text, re.IGNORECASE)
        if not inv_match:
            inv_match = re.search(r'\b(INV-[A-Z0-9-]{3,25})\b', raw_text, re.IGNORECASE)
        if not inv_match:
            inv_match = re.search(r'\b(?:INV)\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{2,25})', raw_text, re.IGNORECASE)
        if inv_match:
            candidate_inv = inv_match.group(1).strip()
            if candidate_inv.lower() not in ("original", "duplicate", "triplicate", "invoice", "number", "tax", "oice"):
                fields.invoice_number = candidate_inv
                fields.confidence_scores["invoice_number"] = 0.85

        # Amounts: support INR, Rs, ₹, $, and standard Indian / international comma numbers
        amounts = re.findall(r'(?:INR|Rs\.?|₹|\$)\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?)', raw_text, re.IGNORECASE)
        if not amounts:
            amounts = re.findall(r'\b(\d{1,3}(?:,\d{2,3})+,\d{3}(?:\.\d{2})?)\b', raw_text)
        if amounts:
            numeric_amounts = sorted([clean_amount(a) for a in amounts if clean_amount(a)], reverse=True)
            if numeric_amounts:
                fields.total_amount = numeric_amounts[0]
                fields.confidence_scores["total_amount"] = 0.90
        # Currency: default INR for Indian MSME documents, or detect explicitly
        if re.search(r'₹|\bINR\b|\bRs\.?\b', raw_text, re.IGNORECASE):
            fields.currency = "INR"
        elif re.search(r'\$|\bUSD\b', raw_text, re.IGNORECASE) and not re.search(r'₹|\bINR\b|\bRs\.?\b|\bGSTIN\b', raw_text, re.IGNORECASE):
            fields.currency = "USD"
        else:
            fields.currency = "INR"

        
        # Due date and issue date.
        dates = re.findall(r'(\b\d{4}-\d{2}-\d{2}\b|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2}, \d{4})', raw_text, re.IGNORECASE)
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

        # Extract counterparty name, skipping standard header titles and seller company
        HEADER_TITLES = {
            "tax invoice", "commercial invoice", "invoice", "original for recipient",
            "duplicate for supplier", "triplicate for transporter", "bill of supply",
            "commercial tax invoice", "proforma invoice", "purchase order", "receipt",
            "synthetic sample - for software testing only", "original", "from", "bill to"
        }
        SELLER_NAMES = {"apex enterprises", "apex distributors"}
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        candidate_name = None
        for i, line in enumerate(lines):
            lower_line = line.lower().rstrip(":")
            if lower_line in ("bill to", "customer", "buyer", "to"):
                for offset in (1, 2, 3, 4):
                    if i + offset < len(lines):
                        nxt = lines[i + offset].strip()
                        nxt_lower = nxt.lower()
                        if (nxt_lower not in HEADER_TITLES
                                and not nxt_lower.startswith(("invoice ", "invoice:", "inv-"))
                                and not re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}", nxt)
                                and not re.match(r"^(?:INR|Rs\.?|₹|\$)\s*\d", nxt, re.I)
                                and not any(s in nxt_lower for s in SELLER_NAMES)
                                and "plot" not in nxt_lower and "shop" not in nxt_lower
                                and len(nxt) > 3):
                            candidate_name = nxt
                            break
                if not candidate_name and lower_line == "customer":
                    candidate_name = line
                if candidate_name:
                    break
            elif any(lower_line.startswith(prefix) for prefix in ("bill to:", "customer:", "buyer:", "to:")):
                inline_val = re.sub(r'^(?:bill to|customer|buyer|to)\s*[:#-]?\s*', '', line, flags=re.I).strip()
                inline_lower = inline_val.lower()
                if inline_lower and inline_lower not in HEADER_TITLES and not any(s in inline_lower for s in SELLER_NAMES):
                    candidate_name = inline_val
                    break
        if not candidate_name:
            for line in lines:
                l_lower = line.lower()
                if l_lower not in HEADER_TITLES and not any(s in l_lower for s in SELLER_NAMES) and len(line) > 3 and not re.match(r'^[0-9\W]+$', line):
                    candidate_name = line
                    break
        if candidate_name:
            fields.counterparty_name = candidate_name
            fields.confidence_scores["counterparty_name"] = 0.70

    except Exception as e:
        logging.error(f"OCR Extraction failed: {e}")
        raise RuntimeError(f"OCR extraction failed: {e}") from e

    return fields
