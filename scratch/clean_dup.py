from pathlib import Path
import re

p = Path("frontend/index.html")
text = p.read_text(encoding="utf-8")

# remove lines 87-90
dup_pattern = re.compile(r'\s*<div class="card">\s*<h3>Invoices Awaiting Review</h3>\s*<div id="review-list">.*?</div>\s*</div>', re.DOTALL)
# Only remove the one inside view-upload
view_upload_pattern = re.compile(r'(<div id="view-upload"[^>]*>.*?)<div class="card">\s*<h3>Invoices Awaiting Review</h3>\s*<div id="review-list">.*?</div>\s*</div>', re.DOTALL)

text, n = view_upload_pattern.subn(r'\1', text, count=1)
if n == 1:
    p.write_text(text, encoding="utf-8")
    print("Cleaned duplicate review-list in view-upload successfully")
else:
    print(f"Pattern matched {n} times")

