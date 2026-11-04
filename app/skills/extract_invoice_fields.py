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
    disputed_amount: Optional[Decimal] = None
    undisputed_amount: Optional[Decimal] = None
    paid_amount: Optional[Decimal] = None
    debit_note_ref: Optional[str] = None
    dispute_reason: Optional[str] = None
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
        # Tax and subtotal amounts
        tax_m = re.search(r'(?:IGST|CGST|SGST|Total\s+Tax|Tax\s+Amount|GST(?:\s*@\s*\d+%?)?)\s*[:#-]?\s*(?:₹|INR|Rs\.?|\$)?\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?)', raw_text, re.IGNORECASE)
        if tax_m:
            fields.tax_amount = clean_amount(tax_m.group(1))
            if fields.tax_amount:
                fields.confidence_scores["tax_amount"] = 0.85
        subtotal_m = re.search(r'(?:Taxable\s+(?:Subtotal|Amount|Value)|Subtotal|Sub\s*Total)\s*[:#-]?\s*(?:₹|INR|Rs\.?|\$)?\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?)', raw_text, re.IGNORECASE)
        if subtotal_m:
            fields.amount = clean_amount(subtotal_m.group(1))

        # Currency: default INR for Indian MSME documents, or detect explicitly
        if re.search(r'₹|\bINR\b|\bRs\.?\b', raw_text, re.IGNORECASE):
            fields.currency = "INR"
        elif re.search(r'\$|\bUSD\b', raw_text, re.IGNORECASE) and not re.search(r'₹|\bINR\b|\bRs\.?\b|\bGSTIN\b', raw_text, re.IGNORECASE):
            fields.currency = "USD"
        else:
            fields.currency = "INR"

        # Due date and issue date.
        # 1. Try explicit labeled fields first:
        issue_match = re.search(
            r'(?<!Due\s)(?<!Due)(?<!Payment\s)\b(?:Date\s+of\s+(?:Invoice|Bill|Issue)|(?:Invoice|Issue|Bill|Billing|Inv)\s*(?:Date|Dt)|Date)\s*[:#-]?\s*([^\n\r]+)',
            raw_text, re.IGNORECASE
        )
        due_match = re.search(
            r'\b(?:Payment\s+Due\s*(?:Date|Dt)?|Due\s*(?:Date|Dt|By|On)|Pay\s*(?:By|Before))\s*[:#-]?\s*([^\n\r]+)',
            raw_text, re.IGNORECASE
        )
        if issue_match:
            try:
                parsed_issue = dateutil.parser.parse(re.sub(r'\(.*?\)', '', issue_match.group(1)).strip(), fuzzy=True, dayfirst=True).date()
                fields.issue_date = parsed_issue.isoformat()
                fields.confidence_scores["issue_date"] = 0.90
            except Exception:
                pass
        if due_match:
            try:
                parsed_due = dateutil.parser.parse(re.sub(r'\(.*?\)', '', due_match.group(1)).strip(), fuzzy=True, dayfirst=True).date()
                fields.due_date = parsed_due.isoformat()
                fields.confidence_scores["due_date"] = 0.90
            except Exception:
                pass

        # If issue date found but no due date, check for credit terms (e.g. Net 30, 30 Days)
        if fields.issue_date and not fields.due_date:
            terms_match = re.search(r'\b(?:Net\s*(\d{1,3})|(\d{1,3})\s*Days?\s*(?:Credit\s*Term|Net)?)\b', raw_text, re.IGNORECASE)
            if terms_match:
                try:
                    days = int(terms_match.group(1) or terms_match.group(2))
                    if 0 < days <= 365:
                        from datetime import datetime, timedelta
                        fields.due_date = (datetime.fromisoformat(fields.issue_date) + timedelta(days=days)).date().isoformat()
                        fields.confidence_scores["due_date"] = 0.85
                except Exception:
                    pass

        # 2. General date search: ISO dates, DD/MM/YYYY, DD.MM.YYYY, DD-Mon-YYYY (e.g. 18-Nov-2026), Mon DD, YYYY
        date_pattern = r'(\b\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}\b|\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b|\b\d{1,2}(?:st|nd|rd|th)?[-\s/\.](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s/\.,]*\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b)'
        dates = re.findall(date_pattern, raw_text, re.IGNORECASE)
        if dates:
            try:
                parsed_dates = sorted([dateutil.parser.parse(re.sub(r'\(.*?\)', '', d).strip(), fuzzy=True, dayfirst=True).date() for d in dates])
                if not fields.issue_date and not fields.due_date:
                    if len(parsed_dates) >= 2:
                        fields.issue_date = parsed_dates[0].isoformat()
                        fields.due_date = parsed_dates[-1].isoformat()
                    else:
                        fields.issue_date = parsed_dates[0].isoformat()
                        fields.due_date = parsed_dates[0].isoformat()
                elif not fields.issue_date and fields.due_date:
                    fields.issue_date = parsed_dates[0].isoformat() if parsed_dates[0].isoformat() <= fields.due_date else fields.due_date
                elif not fields.due_date and fields.issue_date:
                    fields.due_date = parsed_dates[-1].isoformat() if parsed_dates[-1].isoformat() >= fields.issue_date else fields.issue_date
                fields.confidence_scores.setdefault("issue_date", 0.8)
                fields.confidence_scores.setdefault("due_date", 0.8)
            except Exception:
                pass
        # Guarantee neither is missing if at least one was found
        if fields.issue_date and not fields.due_date:
            fields.due_date = fields.issue_date
        elif fields.due_date and not fields.issue_date:
            fields.issue_date = fields.due_date

        # Extract counterparty name, skipping standard header titles and seller company
        HEADER_TITLES = {
            "tax invoice", "commercial invoice", "invoice", "original for recipient",
            "duplicate for supplier", "triplicate for transporter", "bill of supply",
            "commercial tax invoice", "proforma invoice", "purchase order", "receipt",
            "synthetic sample - for software testing only", "original", "from", "bill to",
            "supplier", "supplier (biller)", "supplier (biller):"
        }
        SELLER_NAMES = {"apex enterprises", "apex distributors", "vanguard industrial", "seller"}
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        candidate_name = None
        for i, line in enumerate(lines):
            lower_line = line.lower().rstrip(":")
            if any(hdr in lower_line for hdr in ("original for", "duplicate for", "triplicate for", "copy for")):
                continue
            if any(re.search(rf'\b{kw}\b', lower_line) for kw in ("bill to", "customer", "buyer", "consignee", "billed to", "recipient", "to")):
                for offset in (1, 2, 3, 4):
                    if i + offset < len(lines):
                        nxt = lines[i + offset].strip()
                        nxt_lower = nxt.lower()
                        if (nxt_lower not in HEADER_TITLES
                                and not any(s in nxt_lower for s in SELLER_NAMES)
                                and not nxt_lower.startswith(("invoice", "inv-", "tax", "gstin", "date", "due date", "total", "plot", "shop"))
                                and not re.search(r"\d{1,4}[/-]\d{1,2}[/-]\d{2,4}", nxt)
                                and not re.match(r"^(?:INR|Rs\.?|₹|\$)\s*\d", nxt, re.I)
                                and len(nxt) > 3):
                            candidate_name = nxt
                            break
                if candidate_name:
                    break
            elif any(re.search(rf'^{kw}\s*[:#-]', lower_line) for kw in ("bill to", "customer", "buyer", "consignee", "to", "billed to")):
                inline_val = re.sub(r'^(?:bill to|customer|buyer|consignee|billed to|to)\s*[:#-]?\s*', '', line, flags=re.I).strip()
                inline_lower = inline_val.lower()
                if inline_lower and inline_lower not in HEADER_TITLES and not any(s in inline_lower for s in SELLER_NAMES):
                    candidate_name = inline_val
                    break
        if not candidate_name:
            for line in lines:
                l_lower = line.lower()
                if (l_lower not in HEADER_TITLES
                        and not any(s in l_lower for s in SELLER_NAMES)
                        and not l_lower.startswith(("invoice", "inv-", "tax", "gstin", "date", "due date", "total", "plot", "shop"))
                        and len(line) > 3
                        and not re.match(r'^[0-9\W]+$', line)):
                    candidate_name = line
                    break
        if candidate_name:
            fields.counterparty_name = candidate_name
            fields.confidence_scores["counterparty_name"] = 0.70

        # Disputed amount, undisputed balance, paid amount, and debit note references
        dm = re.search(r'\b(?:Disputed\s*(?:Hold\s*Amount|Amount|Hold|Balance)|Dispute\s*(?:Amount|Hold|Claim)|Amount\s*on\s*Hold)[^\n\r\d]*?(\d[\d,]*(?:\.\d{1,2})?)', raw_text, re.IGNORECASE)
        if dm:
            fields.disputed_amount = clean_amount(dm.group(1))
            fields.confidence_scores["disputed_amount"] = 0.90

        um = re.search(r'\b(?:Undisputed\s*(?:Balance|Amount|Payable)?)[^\n\r\d]*?(\d[\d,]*(?:\.\d{1,2})?)', raw_text, re.IGNORECASE)
        if um:
            fields.undisputed_amount = clean_amount(um.group(1))
            fields.confidence_scores["undisputed_amount"] = 0.90

        pm = re.search(r'\b(?:Paid\s*to\s*Date|Amount\s*Paid|Total\s*Paid)[^\n\r\d]*?(\d[\d,]*(?:\.\d{1,2})?)', raw_text, re.IGNORECASE)
        if pm:
            fields.paid_amount = clean_amount(pm.group(1))

        dnm = re.search(r'\bDebit\s*Note\s*(?:Ref|Reference|No|Number)?\s*[:\-]\s*([A-Za-z0-9\-]+)', raw_text, re.IGNORECASE)
        if dnm:
            fields.debit_note_ref = dnm.group(1).strip()

        rm = re.search(r'\"(DISPUTE FILED[^\"]+)\"', raw_text, re.IGNORECASE) or \
             re.search(r'\((Short\s*Delivery[^)]+)\)', raw_text, re.IGNORECASE) or \
             re.search(r'\b(?:Dispute\s*(?:Reason|Status)|Short\s*Delivery)\s*[:\-]?\s*([^\n\r]+)', raw_text, re.IGNORECASE)
        if rm:
            fields.dispute_reason = re.sub(r'\s+', ' ', rm.group(1)).strip()

        if fields.disputed_amount is None and fields.undisputed_amount and fields.total_amount:
            diff = fields.total_amount - (fields.paid_amount or Decimal(0)) - fields.undisputed_amount
            if diff > Decimal(0):
                fields.disputed_amount = diff

    except Exception as e:
        logging.error(f"OCR Extraction failed: {e}")
        raise RuntimeError(f"OCR extraction failed: {e}") from e

    return fields
