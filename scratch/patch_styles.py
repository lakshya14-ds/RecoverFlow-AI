from pathlib import Path

content = Path('frontend/styles.css').read_text(encoding='utf-8')

target = '''.sam-tag {
    background: #0066ff;
    color: #fff;
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid var(--nb-ink);
    font-size: 10px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}'''

replacement = '''.sam-tag {
    background: #0066ff;
    color: #fff;
    padding: 2px 6px;
    border-radius: 3px;
    border: 1px solid var(--nb-ink);
    font-size: 10px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}

.sam-model-badge {
    font-size: 10px;
    font-weight: 700;
    color: #1f2937;
    background: #e5e7eb;
    border: 1px solid var(--nb-ink);
    border-radius: 3px;
    padding: 1px 6px;
    letter-spacing: 0.02em;
}

.model-tag-bracket {
    font-size: 0.78rem;
    font-weight: 600;
    opacity: 0.85;
    margin-left: 5px;
    letter-spacing: 0.01em;
}'''

assert target in content, 'target not found'
content = content.replace(target, replacement)
Path('frontend/styles.css').write_text(content, encoding='utf-8')
print("Successfully updated frontend/styles.css")

