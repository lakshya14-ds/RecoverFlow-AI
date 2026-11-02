import os
import re

print("Starting Control tab redesign patch...")

# 1. Patch frontend/index.html
with open("frontend/index.html", "r", encoding="utf-8") as f:
    html_content = f.read()

# Update version to 20261102d
html_content = html_content.replace('styles.css?v=20261102c', 'styles.css?v=20261102d')
html_content = html_content.replace('app.js?v=20261102c', 'app.js?v=20261102d')

# Replace #view-control
old_control_pattern = r'<div id="view-control" class="view hidden">.*?</div>\s*</main>'

new_control_html = """<div id="view-control" class="view hidden">
                <!-- Executive Overview Banner & High-Level Metrics -->
                <div class="control-header-panel">
                    <div class="control-title-area">
                        <div class="control-badge-pill">⚙️ Business Control &amp; Automation Center</div>
                        <h3>Manage Receivables, Agent Autonomy &amp; Guardrails</h3>
                        <p class="muted">Monitor urgent bill decisions, set how autonomously the AI follows up on unpaid invoices, and configure financial protection limits for your business.</p>
                    </div>
                    <div class="control-metric-grid">
                        <div class="control-metric-card">
                            <span class="control-metric-label">AI Status</span>
                            <div class="control-metric-val status-val"><span class="pulse-dot"></span> Active &amp; Guarded</div>
                            <span class="control-metric-sub">Human-supervised recovery</span>
                        </div>
                        <div class="control-metric-card">
                            <span class="control-metric-label">Avg Collection (DSO)</span>
                            <div class="control-metric-val" id="dso-value">—</div>
                            <span class="control-metric-sub">Days sales outstanding</span>
                        </div>
                        <div class="control-metric-card">
                            <span class="control-metric-label">Pending Reconciliations</span>
                            <div class="control-metric-val" id="pending-value">—</div>
                            <span class="control-metric-sub">Bank &amp; invoice matches</span>
                        </div>
                        <div class="control-metric-card">
                            <span class="control-metric-label">Security &amp; Risk Alerts</span>
                            <div class="control-metric-val" id="fraud-value">—</div>
                            <span class="control-metric-sub">Meta AI prompt shield active</span>
                        </div>
                    </div>
                </div>

                <!-- Executive Sub-Navigation -->
                <div class="control-subnav-bar">
                    <button type="button" class="control-subnav-btn active" data-control-subview="queue">
                        ⚡ Urgent Action Queue <span id="queue-count-badge" class="subnav-counter">3</span>
                    </button>
                    <button type="button" class="control-subnav-btn" data-control-subview="autonomy">
                        🤖 AI Autonomy &amp; Guardrails
                    </button>
                    <button type="button" class="control-subnav-btn" data-control-subview="channels">
                        💳 Payment Links &amp; Channels
                    </button>
                    <button type="button" class="control-subnav-btn" data-control-subview="diagnostics">
                        🛠️ System Audit &amp; Technical Logs
                    </button>
                </div>

                <!-- Subview 1: Urgent Action Queue (Priority for Business Owners) -->
                <div id="control-subview-queue" class="control-subview-panel">
                    <div class="card control-main-card">
                        <div class="card-header-flex">
                            <div>
                                <h3>Bills &amp; Tasks Requiring Your Approval</h3>
                                <p class="muted">The AI has analyzed these overdue accounts and prepared actions. Your approval is required before any customer contact or ledger change.</p>
                            </div>
                            <button type="button" class="btn" id="refresh-queue-btn">🔄 Refresh Queue</button>
                        </div>
                        <div class="stack" id="owner-queue">
                            <p class="muted">Loading urgent actions…</p>
                        </div>
                    </div>
                </div>

                <!-- Subview 2: AI Autonomy & Guardrails -->
                <div id="control-subview-autonomy" class="control-subview-panel hidden">
                    <div class="control-grid-2col">
                        <!-- Autonomy Level Selection -->
                        <div class="card">
                            <div class="card-header-flex">
                                <div>
                                    <h3>AI Recovery Autonomy Level</h3>
                                    <p class="muted">Choose how independently the AI handles customer reminders.</p>
                                </div>
                            </div>
                            <div class="autonomy-selector-box">
                                <label for="autonomy-mode" class="bold-label">Operating Mode</label>
                                <select id="autonomy-mode" class="input-styled">
                                    <option value="review_all">Review All (Recommended) — AI drafts reminders; you approve before sending</option>
                                    <option value="auto_prepare">Auto-Prepare — AI calculates splits, verifies proofs, and stages payment links</option>
                                    <option value="auto_send_sandbox">Autonomous Pilot — AI auto-sends polite reminders for undisputed balances</option>
                                </select>
                                <button type="button" class="btn btn-primary" id="autonomy-save" style="margin-top:10px;">Save Autonomy Mode</button>
                                <p id="autonomy-result" class="control-feedback-msg"></p>
                            </div>

                            <div class="autonomy-info-box">
                                <h4>💡 How Autonomy Works For You</h4>
                                <ul class="business-feature-list">
                                    <li><strong>Review All:</strong> Zero customer messages are sent without your explicit sign-off. Best for maintaining personal buyer relationships.</li>
                                    <li><strong>Auto-Prepare:</strong> The AI extracts deductions, cross-references receiving notes, and prepares 1-click reminders so you don't do data entry.</li>
                                    <li><strong>Autonomous Pilot:</strong> For high-volume retailers. Sends polite reminders only for undisputed balances below your safety threshold.</li>
                                </ul>
                            </div>
                        </div>

                        <!-- Financial Guardrails & Limits Form -->
                        <div class="card">
                            <h3>Business Safety Limits &amp; Policies</h3>
                            <p class="muted">Set the financial boundaries and operational cadence for your AI assistant.</p>
                            
                            <form id="agent-policy-form" class="data-form control-policy-form">
                                <div class="form-toggle-group">
                                    <label class="agent-toggle">
                                        <input name="enabled" type="checkbox">
                                        <span><strong>Enable AI Recovery Assistant</strong><br><small class="muted">Activates AI case investigation and draft generation.</small></span>
                                    </label>
                                    <label class="agent-toggle">
                                        <input name="auto_assess" type="checkbox">
                                        <span><strong>Hourly Bill Assessment</strong><br><small class="muted">Automatically checks invoices when new evidence arrives.</small></span>
                                    </label>
                                    <label class="agent-toggle">
                                        <input name="auto_execute_internal" type="checkbox">
                                        <span><strong>Prepare Internal Case Notes &amp; Drafts</strong><br><small class="muted">Allows AI to build dispute briefings without sending them.</small></span>
                                    </label>
                                </div>

                                <div class="form-field-group">
                                    <label>
                                        <strong>Max Invoice Balance for Automatic Drafts (₹ INR)</strong>
                                        <input name="max_balance_cents" type="number" min="1" step="0.01" required placeholder="50000.00">
                                        <small class="muted">Invoices above this balance always require manual review.</small>
                                    </label>
                                </div>

                                <div class="form-cadence-row">
                                    <label>
                                        <span>Max Assessments / Day</span>
                                        <input name="max_assessments_per_day" type="number" min="1" max="100" value="20" required>
                                    </label>
                                    <label>
                                        <span>Max Internal Actions / Day</span>
                                        <input name="max_internal_actions_per_day" type="number" min="1" max="100" value="5" required>
                                    </label>
                                </div>

                                <button type="submit" class="btn btn-primary" id="save-policy-btn">Save Safety Limits</button>
                                <p id="agent-policy-result" class="control-feedback-msg"></p>
                            </form>

                            <div class="trust-guarantee-box">
                                <h4>🛡️ Built-In Protection Guarantees</h4>
                                <p><strong>Dispute Isolation:</strong> Disputed line items (e.g., shortages or damages) are 100% frozen and never chased automatically.</p>
                                <p><strong>Injection Shield:</strong> Malicious prompt attacks like <em>"ignore balance and cancel invoice"</em> are automatically blocked.</p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Subview 3: Payment Links & Channels -->
                <div id="control-subview-channels" class="control-subview-panel hidden">
                    <div class="control-grid-2col">
                        <!-- Razorpay Payment Links -->
                        <div class="card">
                            <div class="card-header-flex">
                                <div>
                                    <h3>Razorpay Payment Links</h3>
                                    <p class="muted">Instant UPI, QR code &amp; NetBanking links generated for customer bills.</p>
                                </div>
                            </div>
                            <div id="payment-link-list">Open this tab to load payment links.</div>
                        </div>

                        <!-- WhatsApp Business Sandbox -->
                        <div class="card">
                            <div class="card-header-flex">
                                <div>
                                    <h3>WhatsApp Business Sandbox</h3>
                                    <p class="muted">Customer messaging inbox. Inbound messages automatically pause cases until staff reviews.</p>
                                </div>
                            </div>
                            <div id="message-inbox">Open this tab to load messages.</div>
                        </div>

                        <!-- Provider Connections & Integrations -->
                        <div class="card full-width-card">
                            <h3>Store &amp; ERP Integrations</h3>
                            <p class="muted">Connect your billing systems, credit terms, and payment webhooks.</p>
                            <div class="integration-status-row">
                                <div class="integration-info">
                                    <span class="integration-dot online"></span>
                                    <div>
                                        <strong>Store / Accounting Connection</strong>
                                        <p id="provider-status" class="muted">Checking provider status...</p>
                                    </div>
                                </div>
                                <button type="button" id="shopify-sync" class="btn btn-primary">Sync Credit Terms</button>
                            </div>
                            <p id="shopify-sync-result" class="control-feedback-msg"></p>
                            <div id="provider-events" class="hidden"></div>
                        </div>
                    </div>
                </div>

                <!-- Subview 4: System Audit & Technical Logs (Advanced / Judges / Devs) -->
                <div id="control-subview-diagnostics" class="control-subview-panel hidden">
                    <div class="card">
                        <h3>Agent Specialist Task Activity</h3>
                        <p class="muted">Background worker supervisor tasks, retries, and execution outcomes.</p>
                        <div class="stack" id="agent-activity"><p>Loading activity…</p></div>
                    </div>

                    <div class="card">
                        <h3>Sandbox Outbox</h3>
                        <p class="muted">Simulated outbound messages awaiting dispatch or testing.</p>
                        <div id="sandbox-outbox">No messages queued.</div>
                    </div>

                    <div class="card">
                        <h3>Meta AI Model Engine &amp; Slot Rates</h3>
                        <p id="agent-status" class="agent-model-summary">Loading model status...</p>
                        <div id="key-assignment">Connect to load slot status.</div>
                    </div>

                    <div class="card">
                        <h3>Synthetic Evaluation &amp; Accuracy</h3>
                        <p id="evaluation-summary">Loading measured synthetic results…</p>
                        <p><a href="/evaluation.html" target="_blank" rel="noopener" class="btn">Open methods and file-level results</a></p>
                    </div>

                    <!-- Hidden legacy tools container to preserve DOM references without cluttering UI -->
                    <div id="legacy-tools" class="hidden" style="display:none !important;"></div>
                </div>
            </div>
        </main>"""

html_content = re.sub(old_control_pattern, new_control_html, html_content, flags=re.DOTALL)

with open("frontend/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)
print("Updated frontend/index.html successfully!")


# 2. Patch frontend/app.js
with open("frontend/app.js", "r", encoding="utf-8") as f:
    app_js = f.read()

# Update pageForView and remove the chaotic DOM mutations
old_dom_mutations = """    const pageForView = {dashboard: 'control', upload: 'intake', cases: 'review',
        reconciliation: 'review', dunning: 'review', fraud: 'review',
        connected: 'control', agent: 'review', control: 'control'};
    const legacyTools = document.getElementById('legacy-tools');
    [...document.querySelectorAll('#view-upload > .card')].forEach(card => {
        if (card.contains(document.getElementById('review-list'))) {
            const target = document.getElementById('subview-invoices') || document.getElementById('view-cases');
            target.appendChild(card);
        } else legacyTools.appendChild(card);
    });
    document.getElementById('view-connected').before(document.getElementById('view-control'));
    document.getElementById('view-control').after(document.getElementById('view-dashboard'));
    document.getElementById('view-control').appendChild(
        document.querySelector('#view-agent > .card'));"""

new_dom_setup = """    const pageForView = {
        upload: 'intake',
        cases: 'review',
        reconciliation: 'review',
        dunning: 'review',
        fraud: 'review',
        agent: 'review',
        control: 'control',
        dashboard: 'dashboard',
        connected: 'connected'
    };

    function activateControlSubView(subview) {
        document.querySelectorAll('.control-subnav-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.controlSubview === subview);
        });
        const subQueue = document.getElementById('control-subview-queue');
        const subAutonomy = document.getElementById('control-subview-autonomy');
        const subChannels = document.getElementById('control-subview-channels');
        const subDiagnostics = document.getElementById('control-subview-diagnostics');

        if (subQueue) subQueue.classList.toggle('hidden', subview !== 'queue');
        if (subAutonomy) subAutonomy.classList.toggle('hidden', subview !== 'autonomy');
        if (subChannels) subChannels.classList.toggle('hidden', subview !== 'channels');
        if (subDiagnostics) subDiagnostics.classList.toggle('hidden', subview !== 'diagnostics');
    }

    document.querySelectorAll('.control-subnav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            activateControlSubView(btn.dataset.controlSubview);
        });
    });

    const refreshQueueBtn = document.getElementById('refresh-queue-btn');
    if (refreshQueueBtn) {
        refreshQueueBtn.addEventListener('click', () => {
            loadOwnerQueue();
        });
    }"""

if old_dom_mutations in app_js:
    app_js = app_js.replace(old_dom_mutations, new_dom_setup)
    print("Replaced old DOM mutations in app.js!")
else:
    print("Warning: old_dom_mutations not found exactly, checking regex...")
    app_js = re.sub(r"const pageForView = \{dashboard: 'control'.*?document\.querySelector\('#view-agent > \.card'\)\);",
                    new_dom_setup, app_js, flags=re.DOTALL)
    print("Replaced via regex!")

# Update navigate control descriptions and activation
old_control_desc = "control:'Inspect the ledger, sandbox payments, audit, policies, and keys.'"
new_control_desc = "control:'Manage overdue bills, agent autonomy, financial safety limits, and connected channels.'"
app_js = app_js.replace(old_control_desc, new_control_desc)

old_control_load = "if(page === 'control') { loadSummary(); loadConnected(); loadAgent(); loadControl(); loadOwnerQueue(); loadAgentActivity(); }"
new_control_load = """if(page === 'control') {
                activateControlSubView('queue');
                loadSummary();
                loadConnected();
                loadAgent();
                loadControl();
                loadOwnerQueue();
                loadAgentActivity();
            }"""
app_js = app_js.replace(old_control_load, new_control_load)

# Update loadOwnerQueue to update the count badge and empty state
old_queue_render = """            container.innerHTML = items.length ? items.map(item => `
                <div class="queue-row"><div><strong class="mono">${escapeHtml(item.invoice_number)}</strong>
                <small>${escapeHtml(item.customer)}</small><p>${escapeHtml(item.action)} — ${escapeHtml(item.reason)}</p>
                <small>Owner: ${escapeHtml(item.owner)} · Due: ${escapeHtml(item.deadline || '—')} · Affects: ${formatCents(item.affected_cents)}${item.approval_required ? ' · Approval required' : ''}</small>
                ${item.uncertainty.length ? `<small>Uncertain: ${item.uncertainty.map(escapeHtml).join('; ')}</small>` : ''}</div>
                <div><button type="button" class="btn queue-open" data-id="${Number(item.invoice_id)}">Open case</button></div></div>`).join('')
                : '<p>No pending actions. All cases are steady or resolved.</p>';"""

new_queue_render = """            const badge = document.getElementById('queue-count-badge');
            if (badge) {
                badge.textContent = items.length;
            }
            container.innerHTML = items.length ? items.map(item => `
                <div class="queue-row"><div><strong class="mono">${escapeHtml(item.invoice_number)}</strong>
                <small>${escapeHtml(item.customer || '')}</small><p>${escapeHtml(item.action)} — ${escapeHtml(item.reason || '')}</p>
                <small>Owner: ${escapeHtml(item.owner || 'staff')} · Due: ${escapeHtml(item.deadline || '—')} · Affects: ${formatCents(item.affected_cents)}${item.approval_required ? ' · Approval required' : ''}</small>
                ${(item.uncertainty || []).length ? `<small>Uncertain: ${item.uncertainty.map(escapeHtml).join('; ')}</small>` : ''}</div>
                <div><button type="button" class="btn btn-primary queue-open" data-id="${Number(item.invoice_id)}">Open bill</button></div></div>`).join('')
                : '<div class="empty-queue-box"><h4>🎉 All Caught Up!</h4><p>No urgent bill decisions or approvals pending. All accounts are running on schedule.</p></div>';"""

app_js = app_js.replace(old_queue_render, new_queue_render)

with open("frontend/app.js", "w", encoding="utf-8") as f:
    f.write(app_js)
print("Updated frontend/app.js successfully!")


# 3. Append new styles to frontend/styles.css
control_styles = """
/* ==========================================================================
   Executive Business Control & Automation Center Styles
   ========================================================================== */

.control-header-panel {
    background: var(--nb-surface);
    border: var(--nb-border-width) solid var(--nb-ink);
    box-shadow: var(--nb-shadow-md);
    border-radius: var(--nb-radius);
    padding: 24px;
    margin-bottom: 20px;
}

.control-title-area h3 {
    margin: 6px 0 8px 0;
    font-size: 22px;
    font-weight: 850;
    letter-spacing: -0.02em;
}

.control-badge-pill {
    display: inline-block;
    padding: 4px 10px;
    background: var(--nb-yellow);
    border: var(--nb-border-width) solid var(--nb-ink);
    border-radius: var(--nb-radius-pill);
    font-size: 11px;
    font-weight: 850;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 6px;
    box-shadow: var(--nb-shadow-xs);
}

.control-metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
    margin-top: 20px;
}

.control-metric-card {
    background: var(--nb-surface-sun);
    border: var(--nb-border-width) solid var(--nb-ink);
    box-shadow: var(--nb-shadow-xs);
    border-radius: var(--nb-radius);
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.control-metric-label {
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--nb-ink-muted);
}

.control-metric-val {
    font-size: 24px;
    font-weight: 900;
    color: var(--nb-ink);
    margin: 6px 0 2px 0;
    display: flex;
    align-items: center;
    gap: 8px;
}

.control-metric-val.status-val {
    font-size: 14px;
    font-weight: 850;
    color: var(--nb-mint-hover);
}

.pulse-dot {
    width: 10px;
    height: 10px;
    background: var(--nb-mint);
    border-radius: 50%;
    border: 2px solid var(--nb-ink);
    display: inline-block;
    animation: pulse-glow 2s infinite ease-in-out;
}

@keyframes pulse-glow {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.2); opacity: 0.8; }
}

.control-metric-sub {
    font-size: 11px;
    color: var(--nb-ink-faint);
}

/* Control Sub-navigation */
.control-subnav-bar {
    display: flex;
    gap: 10px;
    margin-bottom: 22px;
    flex-wrap: wrap;
    background: var(--nb-surface);
    border: var(--nb-border-width) solid var(--nb-ink);
    box-shadow: var(--nb-shadow-sm);
    border-radius: var(--nb-radius);
    padding: 8px 12px;
}

.control-subnav-btn {
    background: transparent;
    border: var(--nb-border-width) solid transparent;
    border-radius: var(--nb-radius);
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 750;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--nb-ink);
    transition: all 0.1s ease;
}

.control-subnav-btn:hover {
    background: var(--nb-surface-subtle);
}

.control-subnav-btn.active {
    background: var(--nb-yellow);
    border-color: var(--nb-ink);
    box-shadow: var(--nb-shadow-xs);
    font-weight: 850;
}

.subnav-counter {
    background: var(--nb-coral);
    color: #ffffff;
    border: 1.5px solid var(--nb-ink);
    border-radius: var(--nb-radius-pill);
    font-size: 11px;
    font-weight: 800;
    padding: 1px 7px;
    line-height: 1.2;
}

/* Control Subview Panels */
.control-subview-panel {
    display: block;
}

.control-subview-panel.hidden {
    display: none !important;
}

.control-grid-2col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
}

.full-width-card {
    grid-column: 1 / -1;
}

.autonomy-selector-box {
    background: var(--nb-surface-sun);
    border: var(--nb-border-width) solid var(--nb-ink);
    border-radius: var(--nb-radius);
    padding: 16px;
    margin: 14px 0;
}

.autonomy-info-box {
    margin-top: 16px;
    padding: 14px 16px;
    background: var(--nb-surface-subtle);
    border-left: 4px solid var(--nb-cobalt);
    border-radius: var(--nb-radius-sm);
}

.business-feature-list {
    margin: 8px 0 0 16px;
    padding: 0;
    font-size: 13px;
    line-height: 1.6;
    color: var(--nb-ink);
}

.trust-guarantee-box {
    margin-top: 16px;
    padding: 14px 16px;
    background: var(--nb-mint-light);
    border: var(--nb-border-width) solid var(--nb-ink);
    border-radius: var(--nb-radius);
    font-size: 12.5px;
    line-height: 1.5;
}

.trust-guarantee-box h4 {
    margin-top: 0;
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 850;
    color: var(--nb-ink);
}

.empty-queue-box {
    padding: 36px 20px;
    text-align: center;
    background: var(--nb-surface-sun);
    border: 2px dashed var(--nb-ink-faint);
    border-radius: var(--nb-radius);
}

.empty-queue-box h4 {
    margin: 0 0 6px 0;
    font-size: 16px;
    font-weight: 850;
}

.empty-queue-box p {
    margin: 0;
    color: var(--nb-ink-muted);
    font-size: 13px;
}

.integration-status-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    background: var(--nb-surface-subtle);
    border: var(--nb-border-width) solid var(--nb-ink);
    border-radius: var(--nb-radius);
    padding: 14px 18px;
    margin: 14px 0 8px 0;
}

.integration-info {
    display: flex;
    align-items: center;
    gap: 12px;
}

.integration-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    border: 2px solid var(--nb-ink);
    background: var(--nb-mint);
}

.control-feedback-msg {
    font-size: 12px;
    font-weight: 750;
    margin-top: 8px;
    color: var(--nb-cobalt);
}

.form-toggle-group {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 16px;
}

.form-field-group {
    margin-bottom: 14px;
}

.form-field-group label {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.form-cadence-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 16px;
}

.form-cadence-row label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    font-weight: 700;
}

.card-header-flex {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 14px;
    margin-bottom: 14px;
}

.agent-model-summary {
    background: var(--nb-surface-subtle);
    padding: 8px 12px;
    border-radius: var(--nb-radius-sm);
    border: 1px solid var(--nb-ink-faint);
    font-size: 12.5px;
    margin-bottom: 12px;
}

@media (max-width: 900px) {
    .control-grid-2col {
        grid-template-columns: 1fr;
    }
    .control-subnav-bar {
        flex-direction: column;
    }
    .integration-status-row {
        flex-direction: column;
        align-items: flex-start;
    }
}
"""

with open("frontend/styles.css", "r", encoding="utf-8") as f:
    css_content = f.read()

if "Executive Business Control & Automation Center Styles" not in css_content:
    css_content += "\n" + control_styles
    with open("frontend/styles.css", "w", encoding="utf-8") as f:
        f.write(css_content)
    print("Appended control styles to frontend/styles.css!")
else:
    print("Control styles already present in styles.css!")

print("All patches applied successfully!")

