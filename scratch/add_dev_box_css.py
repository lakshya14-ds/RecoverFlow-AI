with open("frontend/styles.css", "r", encoding="utf-8") as f:
    css = f.read()

dev_box_css = """
.dev-login-box {
    margin-top: 18px;
    background: var(--nb-surface-subtle);
    border: 1.5px dashed var(--nb-ink-faint);
    border-radius: var(--nb-radius);
    padding: 12px 14px;
    text-align: left;
}
.dev-box-title {
    display: block;
    font-size: 11.5px;
    font-weight: 800;
    color: var(--nb-ink-muted);
    margin-bottom: 8px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
"""

if ".dev-login-box" not in css:
    css += "\n" + dev_box_css
    with open("frontend/styles.css", "w", encoding="utf-8") as f:
        f.write(css)
    print("Added dev box styles to styles.css")
else:
    print("dev box styles already present")

