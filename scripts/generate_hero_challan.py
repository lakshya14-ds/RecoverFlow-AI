"""Generate synthetic Indian Delivery Challan & Lorry Receipt (POD) for INV-2026-HERO."""
import os
from pathlib import Path
from PIL import Image, ImageDraw

def generate_hero_challan(output_dir: str = "docs/challan") -> tuple[str, str]:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    png_path = out_path / "CHALLAN-2026-HERO.png"
    pdf_path = out_path / "CHALLAN-2026-HERO.pdf"

    # Standard A4 canvas: 800 x 1100 px
    img = Image.new("RGB", (800, 1100), color=(253, 252, 248))
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle([20, 20, 780, 1080], outline=(40, 40, 40), width=3)
    draw.rectangle([26, 26, 774, 1074], outline=(180, 180, 180), width=1)

    # Header
    draw.rectangle([30, 30, 770, 110], fill=(240, 243, 246), outline=(60, 60, 60), width=2)
    draw.text((45, 40), "APEX INDUSTRIAL LOGISTICS & CARRIERS", fill=(20, 35, 60))
    draw.text((45, 65), "DELIVERY CHALLAN & PROOF OF DELIVERY (POD)", fill=(10, 10, 10))
    draw.text((45, 88), "Consignment Note / Bilty: LR-MUM-88421  |  Date: 10-Oct-2026", fill=(70, 70, 70))

    # Consignor & Consignee Boxes
    draw.rectangle([30, 120, 395, 230], outline=(150, 150, 150), width=1)
    draw.text((40, 128), "CONSIGNOR (Shipper):", fill=(20, 20, 20))
    draw.text((40, 148), "Apex Industrial Equipments Ltd.", fill=(40, 40, 40))
    draw.text((40, 168), "Plot 42, Andheri East, Mumbai 400093", fill=(70, 70, 70))
    draw.text((40, 188), "GSTIN: 27AABCA1234D1Z8", fill=(70, 70, 70))
    draw.text((40, 208), "Invoice Ref: INV-2026-HERO", fill=(10, 10, 10))

    draw.rectangle([405, 120, 770, 230], outline=(150, 150, 150), width=1)
    draw.text((415, 128), "CONSIGNEE (Receiver):", fill=(20, 20, 20))
    draw.text((415, 148), "Metro Retail Distributors Pvt Ltd", fill=(40, 40, 40))
    draw.text((415, 168), "Warehouse Bay 4, Bhiwandi Complex", fill=(70, 70, 70))
    draw.text((415, 188), "Thane, Maharashtra - 421302", fill=(70, 70, 70))
    draw.text((415, 208), "Contact: +91 98200 12345", fill=(70, 70, 70))

    # Dispatched Items Table
    draw.rectangle([30, 245, 770, 420], outline=(100, 100, 100), width=2)
    draw.rectangle([30, 245, 770, 280], fill=(225, 230, 238))
    draw.text((40, 255), "Item #", fill=(10, 10, 10))
    draw.text((100, 255), "Description of Goods", fill=(10, 10, 10))
    draw.text((420, 255), "HSN Code", fill=(10, 10, 10))
    draw.text((540, 255), "Dispatched Qty", fill=(10, 10, 10))
    draw.text((680, 255), "Accepted Qty", fill=(10, 10, 10))

    draw.line([(30, 280), (770, 280)], fill=(100, 100, 100), width=1)
    draw.text((40, 300), "1", fill=(30, 30, 30))
    draw.text((100, 300), "Precision Industrial Valve Sets (Series V-80)", fill=(30, 30, 30))
    draw.text((420, 300), "8481.80", fill=(30, 30, 30))
    draw.text((540, 300), "80 Sets", fill=(30, 30, 30))
    draw.text((680, 300), "70 Sets [!]", fill=(180, 20, 20))

    # Bounding box 1: Warehouse Receiving Remarks Box (Center / Notes)
    # ymin: 440, xmin: 30, ymax: 600, xmax: 770
    draw.rectangle([30, 440, 770, 600], outline=(200, 70, 70), width=2, fill=(255, 250, 248))
    draw.text((45, 450), "GATE RECEIVING REMARKS & DISCREPANCY RECORD:", fill=(180, 20, 20))
    draw.text((45, 480), "Shortage Noted at Unloading Bay 4: Received 70 valve sets in sound condition.", fill=(160, 10, 10))
    draw.text((45, 510), "Shortfall of 10 Sets (Carton #7 & #8 missing/transit loss). Seal broken upon arrival.", fill=(160, 10, 10))
    draw.text((45, 540), "DISPUTE CLAIM: INR 30,000 (10 units x INR 3,000/unit) HELD PENDING CREDIT NOTE.", fill=(200, 0, 0))
    draw.text((45, 570), "Inspected by: M. Jadhav (Receiving Warehouse Supervisor) - 12-Oct-2026", fill=(80, 80, 80))

    # Bounding box 2: Damaged Carton / Condition Photographic Inspection Crop
    # ymin: 620, xmin: 30, ymax: 840, xmax: 420
    draw.rectangle([30, 620, 420, 840], outline=(120, 120, 120), width=2, fill=(245, 245, 245))
    draw.text((40, 630), "PHYSICAL CARGO INSPECTION (BAY 4 CAMERA)", fill=(40, 40, 40))
    draw.rectangle([45, 660, 405, 825], fill=(210, 195, 175), outline=(100, 90, 80), width=2)
    draw.polygon([(60, 700), (220, 680), (380, 710), (360, 800), (200, 820), (50, 790)], fill=(185, 160, 130), outline=(80, 60, 40), width=2)
    draw.line([(60, 700), (200, 740), (380, 710)], fill=(80, 60, 40), width=2)
    draw.line([(200, 740), (200, 820)], fill=(80, 60, 40), width=2)
    draw.polygon([(180, 720), (230, 715), (220, 750), (170, 745)], fill=(120, 40, 30), outline=(180, 20, 20), width=2)
    draw.text((70, 760), "[!] CARTON SEAL BROKEN - 10 UNITS SHORT", fill=(220, 20, 20))

    # Bounding box 3: Receiver Stamp & Authorized Signature Box (Bottom Right)
    # ymin: 860, xmin: 430, ymax: 1060, xmax: 770
    draw.rectangle([430, 860, 770, 1060], outline=(30, 60, 120), width=2, fill=(248, 250, 255))
    draw.text((440, 870), "AUTHORIZED RECEIVER STAMP & SIGNATURE:", fill=(20, 40, 90))

    # Draw oval rubber stamp in official violet/indigo color
    draw.ellipse([450, 900, 650, 980], outline=(65, 50, 170), width=3)
    draw.ellipse([456, 906, 644, 974], outline=(65, 50, 170), width=1)
    draw.text((468, 918), "METRO RETAIL DISTRIBUTORS", fill=(65, 50, 170))
    draw.text((485, 935), "GOODS RECEIVED BAY", fill=(65, 50, 170))
    draw.text((505, 952), "12 OCT 2026", fill=(65, 50, 170))

    # Draw signature
    signature_points = [(620, 1010), (635, 995), (650, 1015), (665, 990), (680, 1005), (710, 985), (730, 1020), (750, 1010)]
    draw.line(signature_points, fill=(15, 30, 150), width=3)
    draw.text((610, 1025), "R. K. Sharma (Store Incharge)", fill=(30, 30, 80))

    img.save(png_path)
    img.convert("RGB").save(pdf_path, "PDF")
    return str(png_path), str(pdf_path)


if __name__ == "__main__":
    png, pdf = generate_hero_challan()
    print(f"Generated hero challan: {png} and {pdf}")

