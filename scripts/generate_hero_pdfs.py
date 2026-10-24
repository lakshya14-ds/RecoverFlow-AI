"""Generate clean synthetic PDF files for hero case evidence."""
import os

def create_simple_pdf(filepath: str, title: str, lines: list[str]):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    text_commands = ["BT", "/F1 16 Tf", "50 750 Td", f"({title}) Tj", "ET"]
    y = 710
    text_commands.append("BT")
    text_commands.append("/F1 12 Tf")
    text_commands.append(f"50 {y} Td")
    for line in lines:
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        text_commands.append(f"({escaped}) Tj")
        text_commands.append("T*")
    text_commands.append("ET")
    
    stream_content = "\n".join(text_commands).encode("latin-1")
    stream_len = len(stream_content)
    
    header_str = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n"
    )
    footer_obj5 = (
        "\nendstream\nendobj\n"
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )
    
    pdf_content = header_str.encode("latin-1") + stream_content + footer_obj5.encode("latin-1")
    xref_offset = len(pdf_content)
    
    trailer_str = (
        "xref\n0 6\n"
        "0000000000 65535 f \n"
        "0000000009 00000 n \n"
        "0000000058 00000 n \n"
        "0000000115 00000 n \n"
        f"{210:010d} 00000 n \n"
        f"{210 + stream_len + 40:010d} 00000 n \n"
        "trailer\n<< /Size 6 /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )
    pdf_content += trailer_str.encode("latin-1")
    
    with open(filepath, "wb") as f:
        f.write(pdf_content)
    print(f"Generated valid PDF: {filepath} ({len(pdf_content)} bytes)")

if __name__ == "__main__":
    create_simple_pdf(
        "docs/invoices/INV-2026-HERO.pdf",
        "COMMERCIAL TAX INVOICE - INV-2026-HERO",
        [
            "Invoice Number: INV-2026-HERO",
            "Date: 2026-09-09 | Due Date: 2026-10-09",
            "Customer: Apex Enterprises Pvt Ltd",
            "GSTIN: 27AABCA1234D1Z8",
            "----------------------------------------------------------------------",
            "Item: Precision Valve Sets (SKU: PVS-100)",
            "Quantity: 80 Units",
            "Unit Price: INR 3,000.00",
            "----------------------------------------------------------------------",
            "Subtotal: INR 2,40,000.00",
            "Total Invoiced Amount: INR 2,40,000.00",
            "Payment Terms: Net 30 Days via RTGS / Bank Transfer"
        ]
    )

    create_simple_pdf(
        "docs/po/PO-2026-HERO.pdf",
        "PURCHASE ORDER - PO-2026-HERO",
        [
            "PO Reference: PO-2026-HERO",
            "PO Date: 2026-09-01",
            "Buyer: Apex Enterprises Pvt Ltd (Procurement Dept)",
            "Delivery Location: Warehouse Unit 4, Industrial Area Phase II",
            "----------------------------------------------------------------------",
            "Authorized Items:",
            "- 80 Units x Precision Valve Sets @ INR 3,000.00 = INR 2,40,000.00",
            "Payment Terms: Net 30 Days from invoice date",
            "Authorized Signature: Procurement Manager, Apex Enterprises Pvt Ltd"
        ]
    )
