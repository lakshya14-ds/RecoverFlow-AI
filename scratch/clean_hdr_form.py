with open("frontend/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Remove the hidden auth-form in header
old_hdr_form = """                    <!-- Programmatic compatibility form for tests -->
                    <form id="auth-form" class="auth-strip hidden" style="display:none !important;">
                        <input id="api-key" type="password" autocomplete="off">
                        <button type="submit" class="btn btn-primary">Connect</button>
                        <button type="button" id="forget-key" class="btn">Forget key</button>
                    </form>"""

html = html.replace(old_hdr_form, "")

with open("frontend/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("Removed duplicate header form.")

