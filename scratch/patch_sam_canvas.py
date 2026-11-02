from pathlib import Path

content = Path('app/services/sam_agent.py').read_text(encoding='utf-8')

old_load = '''def _load_image(file_bytes: bytes, mime_type: str) -> Optional[Image.Image]:
    """Load image from raw bytes, converting PDF if necessary."""
    if mime_type == "application/pdf" or file_bytes.startswith(b"%PDF"):
        return _render_first_page_of_pdf(file_bytes)
    try:
        return Image.open(io.BytesIO(file_bytes)).convert("RGB")
    except Exception as exc:
        logger.warning(f"Could not load image bytes: {exc}")
        return None'''

new_load = '''def _render_text_as_canvas(text_bytes: bytes, filename: str = "") -> Image.Image:
    """Render raw CSV/text content onto an invoice/document canvas for perception models."""
    from PIL import ImageDraw
    canvas = Image.new("RGB", (800, 1100), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([10, 10, 790, 1090], outline=(30, 30, 30), width=2)
    # Header bar
    draw.rectangle([10, 10, 790, 60], fill=(240, 243, 246), outline=(30, 30, 30), width=2)
    draw.text((30, 25), f"DOCUMENT ATTACHMENT: {filename[:50]}", fill=(10, 10, 10))
    try:
        text = text_bytes.decode("utf-8", errors="replace")
    except Exception:
        text = str(text_bytes[:1000])
    lines = [l.strip() for l in text.splitlines() if l.strip()][:35]
    y = 80
    for line in lines:
        draw.text((30, y), line[:85], fill=(30, 30, 30))
        y += 26
    return canvas


def _load_image(file_bytes: bytes, mime_type: str, filename_hint: str = "") -> Optional[Image.Image]:
    """Load image from raw bytes, converting PDF or text canvas if necessary."""
    if mime_type == "application/pdf" or file_bytes.startswith(b"%PDF"):
        return _render_first_page_of_pdf(file_bytes)
    try:
        return Image.open(io.BytesIO(file_bytes)).convert("RGB")
    except Exception as exc:
        logger.info(f"Could not load image bytes directly ({exc}), rendering document canvas fallback")
        return _render_text_as_canvas(file_bytes, filename_hint)'''

assert old_load in content, 'old_load not found'
content = content.replace(old_load, new_load)

# Also update call in segment_image_bytes
old_call = 'img = _load_image(image_bytes, mime_type)'
new_call = 'img = _load_image(image_bytes, mime_type, filename_hint=filename_hint)'
assert old_call in content, 'old_call not found'
content = content.replace(old_call, new_call)

Path('app/services/sam_agent.py').write_text(content, encoding='utf-8')
print("Successfully patched _load_image in sam_agent.py")

