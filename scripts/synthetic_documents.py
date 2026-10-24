"""Synthetic source files for the offline demo and extraction evaluation."""
from io import BytesIO

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas


def synthetic_pdf(*, kind="invoice", number="INV-SYN-1", reference="",
                  total="240000.00", line_amount=None, text="") -> bytes:
    lines = ["RECOVERFLOW SYNTHETIC DOCUMENT", f"DOCUMENT TYPE: {kind}",
             f"INVOICE NUMBER: {number if kind == 'invoice' else ''}",
             f"INVOICE REFERENCE: {reference}",
             "CUSTOMER NAME: Synthetic Retailer",
             "ISSUE DATE: 2026-01-01", "DUE DATE: 2026-02-01",
             f"TOTAL AMOUNT: {total}", "CURRENCY: INR", f"TEXT: {text}"]
    if kind in ("invoice", "purchase_order"):
        lines.append(f"LINE: Precision Valve Sets | {80 if kind == 'invoice' else 70} | 3000.00 | {line_amount or total}")
    stream = BytesIO()
    page = canvas.Canvas(stream, pagesize=(612, 792), pageCompression=0)
    page.setFont("Helvetica", 10)
    for index, value in enumerate(lines):
        page.drawString(35, 750 - index * 24, value)
    page.save()
    return stream.getvalue()


def synthetic_image(fmt="PNG") -> bytes:
    image = Image.new("RGB", (640, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 30), "SIMULATED RECEIPT", fill="black")
    draw.text((30, 80), "Invoice INV-SYN-1", fill="black")
    draw.text((30, 130), "INR 150000.00", fill="black")
    stream = BytesIO()
    image.save(stream, format=fmt)
    return stream.getvalue()
