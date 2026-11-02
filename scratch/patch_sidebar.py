# Update frontend/index.html and frontend/styles.css
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace sidebar note
old_sidebar_note = '<p class="sidebar-note">Human-supervised recovery<br>Local pilot · India</p>'
new_sidebar_note = '''<div class="sidebar-note">
                <div class="sidebar-status-line">
                    <span class="sidebar-status-dot"></span>
                    <span>Systems Operational</span>
                </div>
                <div class="sidebar-brand-meta">
                    <strong>Bank-Grade 256-Bit SSL</strong>
                    <span>GST &amp; MSME SAMADHAAN Ready</span>
                </div>
            </div>'''

if old_sidebar_note not in html:
    # check for CRLF / LF variations
    old_sidebar_note = old_sidebar_note.replace('\n', '\r\n')
assert old_sidebar_note in html, 'old_sidebar_note not found'
html = html.replace(old_sidebar_note, new_sidebar_note, 1)

# Replace control metric sub
old_metric_sub = '<span class="control-metric-sub">Human-supervised recovery</span>'
new_metric_sub = '<span class="control-metric-sub">Dual-Control Policy Active</span>'
if old_metric_sub in html:
    html = html.replace(old_metric_sub, new_metric_sub, 1)

# Replace CSV pilot text
old_csv_text = 'Use INR for the India pilot.'
new_csv_text = 'Use INR for Indian operations.'
if old_csv_text in html:
    html = html.replace(old_csv_text, new_csv_text, 1)

# Bump CSS cache buster
html = html.replace('styles.css?v=20261102e', 'styles.css?v=20261102f')

with open('frontend/index.html', 'w', encoding='utf-8', newline='') as f:
    f.write(html)

print('Updated frontend/index.html')

# 2. Update frontend/styles.css
with open('frontend/styles.css', 'r', encoding='utf-8') as f:
    css = f.read()

old_css_rule = """.sidebar-note {
    margin: auto 4px 0;
    padding-top: 18px;
    border-top: var(--nb-border-width) solid var(--nb-border);
    color: var(--nb-ink-muted);
    font-size: 11px;
    font-weight: 600;
    line-height: 1.6;
}"""

new_css_rule = """.sidebar-note {
    margin: auto 4px 0;
    padding-top: 14px;
    border-top: var(--nb-border-width) solid var(--nb-border);
    color: var(--nb-ink-muted);
    font-size: 11px;
    line-height: 1.5;
}

.sidebar-status-line {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    font-weight: 700;
    color: #15803d;
    background: #ecfdf5;
    border: 1px solid #a7f3d0;
    padding: 2px 7px;
    border-radius: 999px;
    margin-bottom: 7px;
    letter-spacing: 0.01em;
}

.sidebar-status-dot {
    width: 6px;
    height: 6px;
    background: #16a34a;
    border-radius: 50%;
    display: inline-block;
    box-shadow: 0 0 0 2px rgba(22, 163, 74, 0.25);
    animation: statusPulse 2s infinite;
}

@keyframes statusPulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.4); }
    70% { transform: scale(1); box-shadow: 0 0 0 4px rgba(22, 163, 74, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(22, 163, 74, 0); }
}

.sidebar-brand-meta {
    display: flex;
    flex-direction: column;
    gap: 2px;
}

.sidebar-brand-meta strong {
    font-weight: 700;
    color: var(--nb-ink);
    font-size: 11px;
    letter-spacing: -0.01em;
}

.sidebar-brand-meta span {
    color: var(--nb-ink-muted);
    font-size: 10px;
    font-weight: 600;
}"""

if old_css_rule not in css:
    old_css_rule = old_css_rule.replace('\n', '\r\n')
    new_css_rule = new_css_rule.replace('\n', '\r\n')

assert old_css_rule in css, 'old_css_rule not found in styles.css'
css = css.replace(old_css_rule, new_css_rule, 1)

with open('frontend/styles.css', 'w', encoding='utf-8', newline='') as f:
    f.write(css)

print('Updated frontend/styles.css')

