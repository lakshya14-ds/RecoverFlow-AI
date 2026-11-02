# Update frontend/index.html and frontend/styles.css
with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# Replace favicon
html = html.replace('<link rel="icon" href="data:,">', '<link rel="icon" type="image/png" href="favicon.png">')

# Replace brand-mark with img
old_mark = '<span class="brand-mark" aria-hidden="true">R</span>'
new_mark = '<span class="brand-mark" aria-hidden="true"><img src="logo.png" alt="RecoverFlow AI" class="brand-mark-img"></span>'

assert old_mark in html, 'old_mark not found'
html = html.replace(old_mark, new_mark)

# Bump cache buster
html = html.replace('styles.css?v=20261102f', 'styles.css?v=20261102g')

with open('frontend/index.html', 'w', encoding='utf-8', newline='') as f:
    f.write(html)

print('Updated frontend/index.html')

# Update frontend/styles.css
with open('frontend/styles.css', 'r', encoding='utf-8') as f:
    css = f.read()

old_css_mark = """.brand-mark {
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    background: var(--nb-yellow);
    color: var(--nb-ink);
    border: var(--nb-border-width) solid var(--nb-ink);
    box-shadow: var(--nb-shadow-xs);
    border-radius: var(--nb-radius);
    font-weight: 900;
    font-size: 22px;
    font-family: ui-monospace, monospace;
    flex-shrink: 0;
}"""

new_css_mark = """.brand-mark {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    background: var(--nb-yellow);
    color: var(--nb-ink);
    border: var(--nb-border-width) solid var(--nb-ink);
    box-shadow: var(--nb-shadow-xs);
    border-radius: var(--nb-radius);
    overflow: hidden;
    flex-shrink: 0;
    padding: 0;
}

.brand-mark-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}"""

if old_css_mark not in css:
    old_css_mark = old_css_mark.replace('\n', '\r\n')
    new_css_mark = new_css_mark.replace('\n', '\r\n')

assert old_css_mark in css, 'old_css_mark not found in styles.css'
css = css.replace(old_css_mark, new_css_mark, 1)

with open('frontend/styles.css', 'w', encoding='utf-8', newline='') as f:
    f.write(css)

print('Updated frontend/styles.css')

