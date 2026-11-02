with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Remove emojis in login modal
assert '<span>⚡ INSTANT ACCESS</span>' in html, 'INSTANT ACCESS with emoji not found'
html = html.replace('<span>⚡ INSTANT ACCESS</span>', '<span>INSTANT ACCESS</span>')

assert '🚀 Enter as Business Owner (Apex Enterprises)' in html, 'rocket button not found'
html = html.replace('🚀 Enter as Business Owner (Apex Enterprises)', 'Enter as Business Owner (Apex Enterprises)')

# 2. Remove demo-features-hint
features_hint_snippet = '''                    <div class="demo-features-hint">
                        <span>✓ Seeded Hero Case Loaded</span>
                        <span>✓ Full Meta AI Suite Active</span>
                        <span>✓ Zero Setup Required</span>
                    </div>'''

if features_hint_snippet not in html:
    features_hint_snippet = features_hint_snippet.replace('\n', '\r\n')

assert features_hint_snippet in html, 'demo-features-hint not found'
html = html.replace(features_hint_snippet + ('\r\n' if '\r\n' in html else '\n'), '')

# 3. Remove emoji in technical title
assert '🛠️ Technical / Staff API Key' in html, 'tech key with emoji not found'
html = html.replace('🛠️ Technical / Staff API Key', 'Technical / Staff API Key')

# 4. Remove emojis in modal footer
assert '<span>🛡️ Disputed Balances Frozen</span>' in html, 'disputed balances emoji not found'
html = html.replace('<span>🛡️ Disputed Balances Frozen</span>', '<span>Disputed Balances Frozen</span>')
html = html.replace('<span>🤖 Meta AI Guarded</span>', '<span>Meta AI Guarded</span>')
html = html.replace('<span>🇮🇳 Indian MSME Credit Compliant</span>', '<span>Indian MSME Credit Compliant</span>')

# 5. Header button & avatar
assert '🔑 Business Sign In' in html, 'header login button emoji not found'
html = html.replace('🔑 Business Sign In', 'Business Sign In')

assert '<div class="user-avatar-badge">🏢</div>' in html, 'avatar badge emoji not found'
html = html.replace('<div class="user-avatar-badge">🏢</div>', '<div class="user-avatar-badge">AE</div>')

# 6. Bump cache buster
html = html.replace('styles.css?v=20261102g', 'styles.css?v=20261102h')

with open('frontend/index.html', 'w', encoding='utf-8', newline='') as f:
    f.write(html)

print('Updated frontend/index.html successfully.')

# Update styles.css for user-avatar-badge
with open('frontend/styles.css', 'r', encoding='utf-8') as f:
    css = f.read()

old_badge_css = """.user-avatar-badge {
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: var(--nb-yellow);
    border: 2px solid var(--nb-ink);
    border-radius: var(--nb-radius-pill);
    box-shadow: var(--nb-shadow-xs);
}"""

new_badge_css = """.user-avatar-badge {
    font-size: 12px;
    font-weight: 900;
    letter-spacing: -0.02em;
    color: var(--nb-ink);
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: var(--nb-yellow);
    border: 2px solid var(--nb-ink);
    border-radius: var(--nb-radius-pill);
    box-shadow: var(--nb-shadow-xs);
}"""

if old_badge_css not in css:
    old_badge_css = old_badge_css.replace('\n', '\r\n')
    new_badge_css = new_badge_css.replace('\n', '\r\n')

assert old_badge_css in css, 'old_badge_css not found'
css = css.replace(old_badge_css, new_badge_css)

with open('frontend/styles.css', 'w', encoding='utf-8', newline='') as f:
    f.write(css)

print('Updated frontend/styles.css successfully.')

