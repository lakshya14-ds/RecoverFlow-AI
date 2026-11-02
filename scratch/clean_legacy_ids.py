import re

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Update view-dashboard IDs
dashboard_match = re.search(r'(<div id="view-dashboard".*?)(<div id="view-upload")', html, re.DOTALL)
if dashboard_match:
    dash_block = dashboard_match.group(1)
    dash_block = dash_block.replace('id="dso-value"', 'id="legacy-dso-value"')
    dash_block = dash_block.replace('id="pending-value"', 'id="legacy-pending-value"')
    dash_block = dash_block.replace('id="fraud-value"', 'id="legacy-fraud-value"')
    html = html[:dashboard_match.start(1)] + dash_block + html[dashboard_match.start(2):]
    print("Renamed legacy IDs in view-dashboard")

# 2. Update view-connected IDs
conn_match = re.search(r'(<div id="view-connected".*?)(<div id="view-agent")', html, re.DOTALL)
if conn_match:
    conn_block = conn_match.group(1)
    conn_block = conn_block.replace('id="provider-status"', 'id="legacy-provider-status"')
    conn_block = conn_block.replace('id="shopify-sync"', 'id="legacy-shopify-sync"')
    conn_block = conn_block.replace('id="shopify-sync-result"', 'id="legacy-shopify-sync-result"')
    conn_block = conn_block.replace('id="payment-link-list"', 'id="legacy-payment-link-list"')
    conn_block = conn_block.replace('id="message-inbox"', 'id="legacy-message-inbox"')
    conn_block = conn_block.replace('id="provider-events"', 'id="legacy-provider-events"')
    html = html[:conn_match.start(1)] + conn_block + html[conn_match.start(2):]
    print("Renamed legacy IDs in view-connected")

# 3. Update view-agent IDs
agent_match = re.search(r'(<div id="view-agent".*?)(<div id="view-control")', html, re.DOTALL)
if agent_match:
    agent_block = agent_match.group(1)
    agent_block = agent_block.replace('id="agent-status"', 'id="legacy-agent-status"')
    agent_block = agent_block.replace('id="agent-policy-form"', 'id="legacy-agent-policy-form"')
    agent_block = agent_block.replace('id="agent-policy-result"', 'id="legacy-agent-policy-result"')
    html = html[:agent_match.start(1)] + agent_block + html[agent_match.start(2):]
    print("Renamed legacy IDs in view-agent")

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Saved updated index.html")

