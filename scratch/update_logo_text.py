with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

assert '<h1>RecoverFlow</h1>' in html, 'h1 RecoverFlow not found'
html = html.replace('<title>RecoverFlow | Receivables and Collections</title>', '<title>RecoverFlow AI | Receivables and Collections</title>')
html = html.replace('<h1>RecoverFlow</h1>', '<h1>RecoverFlow AI</h1>')
html = html.replace('<p class="eyebrow">RecoverFlow / Receivables &amp; Dispute Ops</p>', '<p class="eyebrow">RecoverFlow AI / Receivables &amp; Dispute Ops</p>')
html = html.replace('<h2>RecoverFlow</h2>', '<h2>RecoverFlow AI</h2>')

with open('frontend/index.html', 'w', encoding='utf-8', newline='') as f:
    f.write(html)

print('Updated RecoverFlow to RecoverFlow AI in frontend/index.html')

