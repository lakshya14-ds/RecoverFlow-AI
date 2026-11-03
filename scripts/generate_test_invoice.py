"""Generate a realistic, professional Indian GST Tax Invoice PDF for testing RecoverFlow AI."""
import sys
from pathlib import Path
from decimal import Decimal

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import pypdf

sys.stdout.reconfigure(encoding="utf-8")

def build_realistic_invoice(output_path: Path, invoice_no: str = "INV-2026-9042") -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=A4, pageCompression=0)
    width, height = A4 # 595.27 x 841.89

    # Corporate Color Palette
    c_navy = HexColor("#0F2942")        # Primary Deep Navy
    c_teal = HexColor("#1A5F7A")        # Slate Accent Teal
    c_light = HexColor("#F8FAFC")       # Clean Card Background
    c_border = HexColor("#CBD5E1")      # Border Slate
    c_dark = HexColor("#1E293B")        # Charcoal Text
    c_muted = HexColor("#64748B")       # Secondary Muted Text
    c_white = HexColor("#FFFFFF")
    c_gold = HexColor("#B45309")

    # =============================================================
    # LAYER 1: BACKGROUND GRAPHICS & SHAPES (No text)
    # =============================================================
    # Top Corporate Banner
    c.setFillColor(c_navy)
    c.rect(0, height - 110, width, 110, fill=1, stroke=0)

    # Accent stripe under banner
    c.setFillColor(c_teal)
    c.rect(0, height - 113, width, 3, fill=1, stroke=0)

    # Address Box (From / Bill To)
    box_y = height - 225
    box_h = 100
    c.setFillColor(c_light)
    c.setStrokeColor(c_border)
    c.setLineWidth(1)
    c.roundRect(40, box_y, width - 80, box_h, 6, fill=1, stroke=1)
    c.line(width / 2, box_y + 8, width / 2, box_y + box_h - 8)

    # Metadata Box
    meta_y = height - 275
    c.setFillColor(c_white)
    c.setStrokeColor(c_border)
    c.roundRect(40, meta_y, width - 80, 40, 4, fill=1, stroke=1)

    # Table Header Bar
    table_top = height - 310
    table_w = width - 80
    c.setFillColor(c_navy)
    c.rect(40, table_top, table_w, 24, fill=1, stroke=0)

    # Table Row Backgrounds (3 rows)
    row_h = 24
    for r in range(3):
        ry = table_top - 24 - (r * row_h)
        bg = c_light if r % 2 == 1 else c_white
        c.setFillColor(bg)
        c.rect(40, ry, table_w, row_h, fill=1, stroke=0)
        c.setStrokeColor(c_border)
        c.setLineWidth(0.5)
        c.line(40, ry, 40 + table_w, ry)

    # Total Amount Due Highlight Card
    tot_box_y = table_top - 165
    c.setFillColor(c_navy)
    c.roundRect(320, tot_box_y, width - 40 - 320, 28, 4, fill=1, stroke=0)

    # Bank Details Card
    bank_y = tot_box_y - 90
    c.setFillColor(c_light)
    c.setStrokeColor(c_border)
    c.roundRect(40, bank_y, 260, 80, 4, fill=1, stroke=1)

    # Signature & Stamp Card
    sig_x = 320
    sig_w = width - 40 - sig_x
    c.setFillColor(c_white)
    c.setStrokeColor(c_border)
    c.roundRect(sig_x, bank_y, sig_w, 80, 4, fill=1, stroke=1)

    # Digital Seal Stamp Box
    c.setStrokeColor(HexColor("#1E40AF"))
    c.setFillColor(HexColor("#EFF6FF"))
    c.roundRect(sig_x + 35, bank_y + 20, 140, 32, 4, fill=1, stroke=1)

    # Footer dividing line
    c.setStrokeColor(c_border)
    c.line(40, 68, width - 40, 68)

    # =============================================================
    # LAYER 2: PRIMARY TEXT CONTENT IN PRECISE ORDER
    # (Engineered to match RecoverFlow offline deterministic parser)
    # =============================================================
    # Line 0: Header Title
    c.setFillColor(c_white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(45, height - 48, "TAX INVOICE")

    # Line 1: Subtitle
    c.setFont("Helvetica", 9)
    c.drawString(45, height - 66, "Original For Recipient | Commercial GST Invoicing")

    # Line 2: Document Number top-right
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 45, height - 48, invoice_no)

    # Lines 3 & 4: Section Headers
    c.setFillColor(c_teal)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(55, box_y + box_h - 20, "FROM")
    c.drawString(width / 2 + 15, box_y + box_h - 20, "BILL TO")

    # Lines 5 & 6: Supplier Info
    c.setFillColor(c_navy)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(55, box_y + box_h - 36, "Apex Enterprises Private Limited")
    c.setFillColor(c_dark)
    c.setFont("Helvetica", 8)
    c.drawString(55, box_y + box_h - 50, "Plot 42, Okhla Industrial Area Phase-III, New Delhi - 110020")

    # Lines 7 & 8: Buyer Info (Lines 7 must be Customer Name: lines.index("BILL TO") + 3)
    c.setFillColor(c_navy)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(width / 2 + 15, box_y + box_h - 36, "Bharat Retail Ventures Pvt Ltd")
    c.setFillColor(c_dark)
    c.setFont("Helvetica", 8)
    c.drawString(width / 2 + 15, box_y + box_h - 50, "Shop 12-14, Commercial Sector 18, Noida, UP - 201301")

    # Line 9 & 10: Testing Disclosures (placed in lower footer)
    c.setFillColor(c_teal)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(45, 26, "SYNTHETIC SAMPLE - FOR SOFTWARE TESTING ONLY")
    c.setFillColor(c_muted)
    c.setFont("Helvetica", 7.5)
    c.drawString(45, 15, "No goods were shipped and no real payment was made.")

    # Lines 11-15: Metadata Inline Fields
    c.setFillColor(c_dark)
    c.setFont("Helvetica", 9)
    c.drawString(50, meta_y + 22, f"Invoice Number: {invoice_no}")
    c.drawString(50, meta_y + 8, "Issue Date: 2026-10-18")
    c.drawString(220, meta_y + 8, "Due Date: 2026-11-17")
    c.drawString(220, meta_y + 22, "Invoice Reference: PO-2026-1088")
    c.drawString(440, meta_y + 22, "Currency: INR")

    # Lines 16-19: Table Headers
    c.setFillColor(c_white)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(48, table_top + 8, "ITEM")
    c.drawRightString(355, table_top + 8, "QTY")
    c.drawRightString(445, table_top + 8, "UNIT PRICE INR")
    c.drawRightString(545, table_top + 8, "AMOUNT INR")

    # Lines 20-31: Line Items (description, qty, unit_price, line_total)
    items = [
        ("Precision Hydraulic Valves Series 4B", 10, "3,500.00", "35,000.00"),
        ("High-Pressure Reinforced Couplings", 15, "1,500.00", "22,500.00"),
        ("Industrial Fluid Gaskets & O-Rings", 25, "700.00", "17,500.00"),
    ]
    curr_y = table_top - 24
    for desc, qty, rate_str, amt_str in items:
        c.setFillColor(c_dark)
        c.setFont("Helvetica", 8.5)
        c.drawString(48, curr_y + 8, desc)
        c.drawRightString(355, curr_y + 8, str(qty))
        c.drawRightString(445, curr_y + 8, rate_str)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawRightString(545, curr_y + 8, amt_str)
        curr_y -= row_h

    # Lines 32-37: Financial Waterfall (Subtotal, GST, Total Amount Due)
    subtot_y = curr_y - 12
    c.setFillColor(c_dark)
    c.setFont("Helvetica", 9.5)
    c.drawRightString(445, subtot_y, "Subtotal")
    c.drawRightString(545, subtot_y, "INR 75,000.00")

    gst_y = subtot_y - 20
    c.setFont("Helvetica", 9.5)
    c.drawRightString(445, gst_y, "GST 18% (Tax Amount)")
    c.drawRightString(545, gst_y, "INR 13,500.00")

    c.setFillColor(c_white)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(330, tot_box_y + 9, "Total Amount Due")
    c.drawRightString(545, tot_box_y + 9, "INR 88,500.00")

    # =============================================================
    # LAYER 3: SUPPLEMENTARY REALISTIC COMMERCIAL DETAILS
    # (Drawn after totals so parser has cleanly matched its fields)
    # =============================================================
    # Amount in words
    c.setFillColor(c_muted)
    c.setFont("Helvetica-Oblique", 8.5)
    c.drawString(40, tot_box_y + 9, "Amount in Words: INR Eighty-Eight Thousand Five Hundred Only")

    # Extra GSTIN & Tax Details in address blocks
    c.setFillColor(c_muted)
    c.setFont("Helvetica", 7.5)
    c.drawString(55, box_y + box_h - 64, "GSTIN: 07AAACA1234F1Z9 | PAN: AAACA1234F")
    c.drawString(55, box_y + box_h - 76, "State: Delhi (07) | Email: billing@apexenterprises.in")

    c.drawString(width / 2 + 15, box_y + box_h - 64, "GSTIN: 27AABCS8899P1Z2 | PAN: AABCS8899P")
    c.drawString(width / 2 + 15, box_y + box_h - 76, "State: Maharashtra (27) | Terms: Net 30 Days")

    # Bank Details
    c.setFillColor(c_teal)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(50, bank_y + 62, "BANK REMITTANCE DETAILS (RTGS / NEFT / IMPS)")
    c.setFillColor(c_dark)
    c.setFont("Helvetica", 7.5)
    c.drawString(50, bank_y + 48, "Bank Name: HDFC Bank Ltd | A/C Type: Current Account")
    c.drawString(50, bank_y + 36, "A/C Name: Apex Enterprises Private Limited")
    c.drawString(50, bank_y + 24, "Account Number: 50200084729103")
    c.drawString(50, bank_y + 12, "IFSC: HDFC0000128 | Branch: Okhla Industrial Area, New Delhi")

    # Signatory Box
    c.setFillColor(c_muted)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(width - 50, bank_y + 64, "For Apex Enterprises Pvt Ltd")
    c.setFillColor(HexColor("#1D4ED8"))
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(sig_x + 105, bank_y + 38, "[ DIGITALLY SIGNED ]")
    c.setFont("Helvetica", 7)
    c.drawCentredString(sig_x + 105, bank_y + 26, "Verified GST e-Sign · Accounts Dept")
    c.setFillColor(c_dark)
    c.setFont("Helvetica", 7.5)
    c.drawRightString(width - 50, bank_y + 10, "Authorized Signatory")

    # Commercial Terms
    c.setFillColor(c_muted)
    c.setFont("Helvetica", 7)
    c.drawString(40, 52, "Terms & Conditions: 1. Payment is due strictly within 30 days of invoice date. 2. Interest @ 18% p.a. charged on overdue payments.")
    c.drawString(40, 42, "3. Disputes regarding quantity or damage must be reported within 7 business days of delivery. 4. Subject to Delhi jurisdiction.")

    c.save()
    return output_path

if __name__ == "__main__":
    out_file = Path("output/pdf/INV-2026-9042-sample-invoice.pdf")
    build_realistic_invoice(out_file)
    print(f"Generated realistic invoice: {out_file}")
