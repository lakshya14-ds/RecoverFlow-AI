"""Create three clearly synthetic PDFs for a full Release 4 intake rehearsal."""
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output" / "pdf"
INVOICE_NUMBER = "RF-SAMPLE-2026-001"
PO_NUMBER = "RF-PO-2026-001"


def _base(path: Path, title: str, document_number: str, subtitle: str):
    page = canvas.Canvas(str(path), pagesize=A4, pageCompression=0)
    width, height = A4
    navy = HexColor("#173A43")
    teal = HexColor("#147D83")
    light = HexColor("#E9F3F1")
    page.setFillColor(navy)
    page.rect(0, height - 135, width, 135, fill=1, stroke=0)
    page.setFillColor(HexColor("#FFFFFF"))
    page.setFont("Helvetica-Bold", 23)
    page.drawString(45, height - 58, title)
    page.setFont("Helvetica", 10)
    page.drawString(45, height - 82, subtitle)
    page.drawRightString(width - 45, height - 58, document_number)
    page.setFillColor(light)
    page.roundRect(40, height - 255, width - 80, 88, 10, fill=1, stroke=0)
    page.setFillColor(navy)
    page.setFont("Helvetica-Bold", 10)
    page.drawString(55, height - 189, "FROM")
    page.drawString(315, height - 189, "BILL TO")
    page.setFont("Helvetica", 10)
    page.drawString(55, height - 208, "RecoverFlow Demo Supplies")
    page.drawString(55, height - 225, "Synthetic business, Pune, India")
    page.drawString(315, height - 208, "Synthetic Test Retailer")
    page.drawString(315, height - 225, "Synthetic customer, Mumbai, India")
    page.setFillColor(teal)
    page.setFont("Helvetica-Bold", 9)
    page.drawString(45, 55, "SYNTHETIC SAMPLE - FOR SOFTWARE TESTING ONLY")
    page.setFillColor(HexColor("#5E7072"))
    page.setFont("Helvetica", 8)
    page.drawString(45, 40, "No goods were shipped and no real payment was made.")
    return page, width, height


def _line(page, y, description, quantity, unit_price, amount):
    page.setFont("Helvetica", 10)
    page.drawString(48, y, description)
    page.drawRightString(355, y, str(quantity))
    page.drawRightString(447, y, f"{unit_price:,.2f}")
    page.drawRightString(548, y, f"{amount:,.2f}")
    page.setStrokeColor(HexColor("#DEE8E6"))
    page.line(45, y - 12, 550, y - 12)


def _items_header(page, y):
    page.setFillColor(HexColor("#E9F3F1"))
    page.rect(45, y - 8, 505, 29, fill=1, stroke=0)
    page.setFillColor(HexColor("#173A43"))
    page.setFont("Helvetica-Bold", 9)
    page.drawString(48, y + 1, "ITEM")
    page.drawRightString(355, y + 1, "QTY")
    page.drawRightString(447, y + 1, "UNIT PRICE INR")
    page.drawRightString(548, y + 1, "AMOUNT INR")


def _total(page, y, label, amount, emphasize=False):
    page.setFillColor(HexColor("#173A43"))
    page.setFont("Helvetica-Bold" if emphasize else "Helvetica", 12 if emphasize else 10)
    page.drawRightString(445, y, label)
    page.drawRightString(548, y, f"INR {amount:,.2f}")


def create_invoice(path: Path):
    page, _, h = _base(path, "TAX INVOICE", INVOICE_NUMBER, "Overdue receivable - sample only")
    page.setFillColor(HexColor("#173A43"))
    page.setFont("Helvetica", 10)
    page.drawString(45, h - 291, f"Invoice Number: {INVOICE_NUMBER}")
    page.drawString(45, h - 309, "Issue Date: 2026-09-01")
    page.drawString(315, h - 309, "Due Date: 2026-09-30")
    page.drawString(45, h - 327, f"Purchase Order Reference: {PO_NUMBER}")
    page.drawString(315, h - 327, "Currency: INR")
    _items_header(page, h - 374)
    _line(page, h - 404, "Precision Valve Sets", 10, 1000, 10000)
    _line(page, h - 438, "Safety Couplings", 5, 2000, 10000)
    _total(page, h - 492, "Subtotal", 20000)
    _total(page, h - 516, "GST 18% (Tax Amount)", 3600)
    _total(page, h - 548, "Total Amount Due", 23600, True)
    page.save()


def create_po(path: Path):
    page, _, h = _base(path, "PURCHASE ORDER", PO_NUMBER,
                       "Synthetic comparison document for line-item review")
    page.setFillColor(HexColor("#173A43"))
    page.setFont("Helvetica", 10)
    page.drawString(45, h - 291, f"PO Number: {PO_NUMBER}")
    page.drawString(45, h - 309, f"Invoice Reference: {INVOICE_NUMBER}")
    page.drawString(315, h - 309, "Issue Date: 2026-08-25")
    page.drawString(315, h - 327, "Currency: INR")
    _items_header(page, h - 374)
    _line(page, h - 404, "Precision Valve Sets", 10, 1000, 10000)
    _line(page, h - 438, "Safety Couplings", 4, 2000, 8000)
    _total(page, h - 492, "Subtotal", 18000)
    _total(page, h - 516, "GST 18% (Tax Amount)", 3240)
    _total(page, h - 548, "Total Purchase Order", 21240, True)
    page.save()


def create_receipt(path: Path):
    page, _, h = _base(path, "SIMULATED RECEIPT", "RF-RCPT-2026-001",
                       "For staff-confirmation workflow testing only")
    page.setFillColor(HexColor("#173A43"))
    page.setFont("Helvetica", 11)
    page.drawString(45, h - 300, f"Invoice Reference: {INVOICE_NUMBER}")
    page.drawString(45, h - 324, "Receipt Date: 2026-10-01")
    page.drawString(45, h - 348, "Payment Reference: SIM-RF-2026-001")
    page.drawString(45, h - 372, "Currency: INR")
    page.setFont("Helvetica-Bold", 17)
    page.drawString(45, h - 425, "Total Amount Received: INR 15,000.00")
    page.setFont("Helvetica", 10)
    page.drawString(45, h - 465, "This is a simulated receipt. Staff confirmation is required in RecoverFlow.")
    page.save()


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    files = (OUTPUT / "recoverflow-example-invoice.pdf",
             OUTPUT / "recoverflow-example-purchase-order.pdf",
             OUTPUT / "recoverflow-example-simulated-receipt.pdf")
    if any(path.exists() for path in files):
        raise FileExistsError("Example PDF already exists; refusing to overwrite")
    create_invoice(files[0])
    create_po(files[1])
    create_receipt(files[2])
    for path in files:
        print(path)


if __name__ == "__main__":
    main()
