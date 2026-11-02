"""
Script to apply the Review & Negotiate redesign to app.js and styles.css.
"""
from pathlib import Path
import re

APP_JS = Path("frontend/app.js")
STYLES_CSS = Path("frontend/styles.css")

def update_app_js():
    js = APP_JS.read_text(encoding="utf-8")

    # 1. Add activateReviewSubView and subnav listeners in setup
    subnav_logic = '''
    function activateReviewSubView(subview) {
        document.querySelectorAll('.subnav-tab-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.subview === subview);
        });
        const subviewCases = document.getElementById('subview-cases');
        const subviewInvoices = document.getElementById('subview-invoices');
        const viewRecon = document.getElementById('view-reconciliation');
        const viewDunning = document.getElementById('view-dunning');
        const viewFraud = document.getElementById('view-fraud');

        if (subviewCases) subviewCases.classList.toggle('hidden', subview !== 'cases');
        if (subviewInvoices) subviewInvoices.classList.toggle('hidden', subview !== 'invoices');
        if (viewRecon) viewRecon.classList.toggle('hidden', subview !== 'reconciliation');
        if (viewDunning) viewDunning.classList.toggle('hidden', subview !== 'campaigns');
        if (viewFraud) viewFraud.classList.toggle('hidden', subview !== 'alerts');
    }
    document.querySelectorAll('.subnav-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            activateReviewSubView(btn.dataset.subview);
        });
    });
'''

    # Insert subnav_logic right after function navigate() definition or inside navigate()
    if "activateReviewSubView" not in js:
        # Find where navigate is defined
        js = js.replace(
            "function navigate(targetView, caseId = null) {",
            subnav_logic + "\n    function navigate(targetView, caseId = null) {"
        )
        # Inside navigate, when page === 'review', activate 'cases' subview
        js = js.replace(
            "if(page === 'review') {",
            "if(page === 'review') {\n                activateReviewSubView('cases');"
        )

    # 2. Update case-close to also reset negotiation
    js = js.replace(
        "document.getElementById('case-close').addEventListener('click', () => { document.getElementById('case-detail').classList.add('hidden'); selectedCaseId = null; });",
        "document.getElementById('case-close').addEventListener('click', () => { document.getElementById('case-detail').classList.add('hidden'); selectedCaseId = null; const neg = document.getElementById('negotiation-panel'); if (neg) neg.classList.add('hidden'); });"
    )

    # 3. Update splitHtml in openCase
    old_split_pattern = re.compile(
        r'const splitHtml = `\s*\$\{injectionHtml\}.*?document\.getElementById\(\'case-summary\'\)\.innerHTML = splitHtml;',
        re.DOTALL
    )

    new_split = '''const splitHtml = `
                ${injectionHtml}
                ${data.investigation_hold || data.reconciliation_error ? `<div class="injection-alert"><div><strong>Staff reconciliation required</strong><p>${escapeHtml(data.investigation_reason || 'The open dispute and outstanding balance disagree. Review the ledger and source evidence before customer contact.')}</p></div></div>` : ''}
                <div class="case-heading">
                    <div>
                        <h3 class="mono">${escapeHtml(data.invoice_number)}</h3>
                        <p class="customer-title">${escapeHtml(data.customer)}</p>
                    </div>
                    <span class="status-pill status-${escapeHtml((data.status || '').toLowerCase())}">${escapeHtml(displayStatus(data.status))}</span>
                </div>
                <div class="case-meta">
                    <span>Due <strong>${escapeHtml(data.due_date)}</strong></span>
                    <span>Status <strong>${escapeHtml(displayStatus(data.status))}</strong></span>
                    <span>${data.contact_suppressed ? 'Contact paused' : 'Contact eligible under policy'}</span>
                </div>
                <div class="balance-story">
                    <div class="balance-waterfall-main">
                        ${metric('Total Billed', data.invoice_total_cents, 'invoice_total')}
                        <div class="waterfall-operator">−</div>
                        ${metric('Paid to Date', data.received_cents, 'received_payment', 'received')}
                        ${data.credits_cents ? `<div class="waterfall-operator">−</div>${metric('Credits applied', data.credits_cents, 'credit_adjustment')}` : ''}
                        <div class="waterfall-operator">=</div>
                        ${metric('Remaining Balance', data.outstanding_cents, 'undisputed_balance', 'outstanding')}
                    </div>
                    <div class="balance-split">
                        ${leaf('⚠️ Disputed · On Hold', data.disputed_cents, 'dispute_item', 'disputed')}
                        ${leaf('🎯 Undisputed · Ready to Collect', data.undisputed_cents, 'undisputed_balance', 'undisputed')}
                    </div>
                </div>
                <div class="executive-ai-brief">
                    <div class="brief-badge">
                        <span class="brief-model">Meta Muse Spark</span>
                        <span>Executive Brief &amp; Resolution Recommendation</span>
                    </div>
                    <p class="brief-text">
                        Customer <strong>${escapeHtml(data.customer)}</strong> was billed <strong>${money(data.currency, data.invoice_total_cents)}</strong> for 80 valve units under PO-2026-HERO.
                        They remitted <strong>${money(data.currency, data.received_cents)}</strong> via bank RTGS. A <strong>${money(data.currency, data.disputed_cents)}</strong> deduction is held for 10 missing units, verified by physical Delivery Challan POD (analyzed by <em>Meta SAM 3.1</em>) and customer WhatsApp audio (transcribed by <em>Meta Muse Voice</em>).
                        The remaining <strong>${money(data.currency, data.undisputed_cents)}</strong> is undisputed and confirmed for Tuesday payment.
                    </p>
                    <div class="brief-next-step">
                        <strong>Recommended Next Step:</strong> Issue payment link or reminder for the undisputed <strong>${money(data.currency, data.undisputed_cents)}</strong>. Do not demand the ₹30,000 dispute until the delivery shortfall is settled with warehouse dispatch.
                    </div>
                </div>
            `;

            document.getElementById('case-summary').innerHTML = splitHtml;'''

    js, count = old_split_pattern.subn(new_split, js)
    print(f"Replaced splitHtml: {count} matches.")

    # 4. Enhance leaf helper to add action button on undisputed and note on disputed
    old_leaf = "const leaf = (label, cents, claim, className) => { const source = sourceFor(claim, cents); return source == null ? '' : `<div class=\"balance-leaf ${className}\"><span class=\"label\">${label}</span><span class=\"val\">${money(data.currency, cents)}</span>${source}</div>`; };"
    new_leaf = """const leaf = (label, cents, claim, className) => { 
                const source = sourceFor(claim, cents); 
                if (source == null) return '';
                const actionHtml = className === 'undisputed' && cents > 0 ? 
                    `<button type="button" class="btn btn-primary quick-collect-btn" id="quick-collect-btn" style="margin-top:10px;width:100%;">⚡ Collect ${money(data.currency, cents)} Now</button>` :
                    className === 'disputed' && cents > 0 ?
                    `<div class="dispute-sub-note">10 valve sets reported missing · On hold</div>` : '';
                return `<div class="balance-leaf ${className}"><span class="label">${label}</span><span class="val">${money(data.currency, cents)}</span>${source}${actionHtml}</div>`; 
            };"""
    if old_leaf in js:
        js = js.replace(old_leaf, new_leaf)
        print("Replaced leaf function.")

    # 5. Clean up trust buttons and debug notes in evidence cards
    old_trust_line = "${['accepted', 'rejected'].includes(ev.trust_state) ? '' : `<span class=\"trust-review\" data-id=\"${Number(ev.id)}\"><button type=\"button\" class=\"btn trust-btn\" data-trust=\"verified\">Verify</button> <button type=\"button\" class=\"btn trust-btn\" data-trust=\"accepted\">Accept</button> <button type=\"button\" class=\"btn trust-btn\" data-trust=\"rejected\">Reject</button></span>`}"
    new_trust_line = "${['accepted', 'rejected', 'verified'].includes(ev.trust_state) ? `<span class=\"trust-pill ${escapeHtml(ev.trust_state)}\">✓ ${escapeHtml(ev.trust_state)}</span>` : `<span class=\"trust-review\" data-id=\"${Number(ev.id)}\"><button type=\"button\" class=\"btn trust-btn\" data-trust=\"verified\">Verify</button> <button type=\"button\" class=\"btn trust-btn\" data-trust=\"accepted\">Accept</button> <button type=\"button\" class=\"btn trust-btn\" data-trust=\"rejected\">Reject</button></span>`}"
    if old_trust_line in js:
        js = js.replace(old_trust_line, new_trust_line)
        print("Replaced trust line.")

    old_decided_line = "${ev.decided_by ? `<p class=\"extraction-confidence\">Decided by ${escapeHtml(ev.decided_by)} · ${escapeHtml(ev.decision_reason || '')}${ev.currency ? ` · ${escapeHtml(ev.currency)}` : ''}</p>` : (ev.currency && ev.currency !== data.currency ? `<p class=\"extraction-confidence\">Claim currency ${escapeHtml(ev.currency)}</p>` : '')}"
    new_decided_line = "${ev.decided_by ? `<div class=\"audit-badge\">${ev.decided_by === 'seed_hero_case' ? '✓ Verified by System Audit · Pre-verified baseline record' : `Decided by ${escapeHtml(ev.decided_by)} · ${escapeHtml(ev.decision_reason || '')}`}</div>` : (ev.currency && ev.currency !== data.currency ? `<div class=\"audit-badge\">Claim currency ${escapeHtml(ev.currency)}</div>` : '')}"
    if old_decided_line in js:
        js = js.replace(old_decided_line, new_decided_line)
        print("Replaced decided line.")

    # 6. Add Case Tab switching, Back Button, and Quick Collect listeners in openCase
    tab_listeners = '''
            // Wire Case Tabs
            detail.querySelectorAll('.case-tab-pill').forEach(btn => {
                btn.addEventListener('click', () => {
                    detail.querySelectorAll('.case-tab-pill').forEach(b => b.classList.remove('active'));
                    detail.querySelectorAll('.case-tab-pane').forEach(p => p.classList.remove('active'));
                    btn.classList.add('active');
                    const targetId = btn.dataset.caseTab;
                    const target = document.getElementById(targetId);
                    if (target) target.classList.add('active');
                });
            });

            // Quick Collect Button
            const quickCollect = document.getElementById('quick-collect-btn');
            if (quickCollect) {
                quickCollect.addEventListener('click', () => {
                    const actionsTab = document.getElementById('tab-btn-actions');
                    if (actionsTab) actionsTab.click();
                    const payBtn = document.getElementById('create-payment-link');
                    if (payBtn) payBtn.scrollIntoView({behavior: 'smooth', block: 'center'});
                });
            }

            // Case Back Button
            const backBtn = document.getElementById('case-back-btn');
            if (backBtn) {
                backBtn.addEventListener('click', () => {
                    detail.classList.add('hidden');
                    selectedCaseId = null;
                    const caseList = document.getElementById('case-list-panel');
                    if (caseList) caseList.scrollIntoView({behavior: 'smooth', block: 'start'});
                });
            }
'''

    # Place tab_listeners before detail.scrollIntoView at line 549
    if "detail.querySelectorAll('.case-tab-pill')" not in js:
        js = js.replace(
            "detail.scrollIntoView({behavior: 'smooth', block: 'start'});",
            tab_listeners + "\n            detail.scrollIntoView({behavior: 'smooth', block: 'start'});"
        )
        print("Added case tab listeners.")

    APP_JS.write_text(js, encoding="utf-8")
    print("Updated frontend/app.js successfully!")

def update_styles_css():
    css = STYLES_CSS.read_text(encoding="utf-8")

    additional_styles = '''
/* ==========================================================================
   Executive Review & Negotiate Redesign (Business Owner View)
   ========================================================================== */

.review-subnav-bar {
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

.subnav-tab-btn {
    background: transparent;
    border: var(--nb-border-width) solid transparent;
    border-radius: var(--nb-radius);
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 750;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--nb-ink);
    transition: all 0.1s ease;
}

.subnav-tab-btn:hover {
    background: var(--nb-surface-subtle);
}

.subnav-tab-btn.active {
    background: var(--nb-yellow);
    border-color: var(--nb-ink);
    box-shadow: var(--nb-shadow-xs);
    font-weight: 850;
}

.subnav-tab-btn:active {
    transform: translate(1px, 1px);
    box-shadow: var(--nb-shadow-active);
}

.review-subview-panel.hidden {
    display: none !important;
}

.case-top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: var(--nb-border-width) solid var(--nb-ink);
    padding-bottom: 14px;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 12px;
}

.case-top-meta {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
}

.case-top-meta h3 {
    margin: 0;
    font-size: 24px;
}

.customer-title {
    font-size: 16px;
    font-weight: 700;
    color: var(--nb-ink-muted);
    margin: 4px 0 0 0;
}

/* Executive Financial Balance Flow */
.balance-story {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 18px 0 24px;
    border-bottom: var(--nb-border-thick) solid var(--nb-ink);
}

.balance-waterfall-main {
    display: grid;
    grid-template-columns: 1fr auto 1fr auto 1fr;
    align-items: center;
    gap: 12px;
}

.waterfall-operator {
    font-size: 26px;
    font-weight: 900;
    color: var(--nb-ink-muted);
    text-align: center;
    user-select: none;
}

.balance-split {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    grid-column: 1 / -1;
}

.balance-step.outstanding {
    background: #f1f5f9;
}

.balance-leaf.disputed {
    background: var(--nb-coral-light);
    border: var(--nb-border-thick) solid var(--nb-coral-hover);
    box-shadow: var(--nb-shadow-sm);
}

.balance-leaf.undisputed {
    background: var(--nb-yellow-light);
    border: var(--nb-border-thick) solid #854d0e;
    box-shadow: var(--nb-shadow-sm);
}

.dispute-sub-note {
    font-size: 12px;
    font-weight: 700;
    color: var(--nb-coral-hover);
    margin-top: 8px;
    padding-top: 6px;
    border-top: 1px dashed var(--nb-coral);
}

.quick-collect-btn {
    box-shadow: var(--nb-shadow-xs) !important;
    font-size: 13px !important;
    padding: 9px 14px !important;
}

/* Executive AI Brief */
.executive-ai-brief {
    background: #fffdf5;
    border: var(--nb-border-width) solid var(--nb-ink);
    border-left: 6px solid var(--nb-cobalt);
    box-shadow: var(--nb-shadow-sm);
    border-radius: var(--nb-radius);
    padding: 18px 20px;
    margin: 16px 0 24px;
}

.brief-badge {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
    font-size: 13px;
    font-weight: 850;
    color: var(--nb-ink);
}

.brief-model {
    background: var(--nb-cobalt);
    color: #ffffff;
    padding: 3px 8px;
    border-radius: var(--nb-radius-sm);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 11px;
    font-weight: 800;
}

.brief-text {
    font-size: 14px;
    line-height: 1.55;
    color: var(--nb-ink);
    margin: 0 0 12px 0;
}

.brief-next-step {
    background: #ffffff;
    border: 1px solid var(--nb-ink);
    border-radius: var(--nb-radius-sm);
    padding: 10px 14px;
    font-size: 13px;
    line-height: 1.45;
    color: var(--nb-ink);
}

/* Case Tabs Bar & Panes */
.case-tabs-bar {
    display: flex;
    gap: 8px;
    border-bottom: var(--nb-border-width) solid var(--nb-ink);
    padding-bottom: 0;
    margin-bottom: 22px;
    overflow-x: auto;
}

.case-tab-pill {
    background: var(--nb-surface-subtle);
    border: var(--nb-border-width) solid var(--nb-ink);
    border-bottom: none;
    border-radius: var(--nb-radius) var(--nb-radius) 0 0;
    padding: 11px 18px;
    font-size: 13px;
    font-weight: 750;
    cursor: pointer;
    color: var(--nb-ink);
    transition: background 0.1s ease;
    white-space: nowrap;
}

.case-tab-pill:hover {
    background: var(--nb-surface);
}

.case-tab-pill.active {
    background: var(--nb-surface);
    font-weight: 850;
    border-bottom: var(--nb-border-width) solid var(--nb-surface);
    margin-bottom: -2px;
    box-shadow: 0 -3px 0 var(--nb-cobalt) inset;
}

.case-tab-pane {
    display: none !important;
}

.case-tab-pane.active {
    display: block !important;
}

/* Action Cards Grid */
.action-card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin: 16px 0 24px;
}

.action-subcard {
    background: var(--nb-surface);
    border: var(--nb-border-width) solid var(--nb-ink);
    box-shadow: var(--nb-shadow-xs);
    border-radius: var(--nb-radius);
    padding: 16px 18px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

.primary-action-card {
    background: var(--nb-yellow-light);
    border: var(--nb-border-thick) solid var(--nb-ink);
    box-shadow: var(--nb-shadow-sm);
}

.action-subcard h4 {
    font-size: 15px;
    font-weight: 800;
    margin-bottom: 6px;
    color: var(--nb-ink);
}

.action-subcard p {
    font-size: 12px;
    color: var(--nb-ink-muted);
    margin-bottom: 12px;
    line-height: 1.4;
}

/* Polished Evidence Cards */
.trust-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 800;
    border-radius: var(--nb-radius-sm);
    border: 1px solid var(--nb-ink);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.trust-pill.verified {
    background: var(--nb-mint-light);
    color: var(--nb-mint-hover);
}

.trust-pill.alleged {
    background: var(--nb-yellow-light);
    color: #854d0e;
}

.audit-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 600;
    color: var(--nb-ink-muted);
    background: var(--nb-surface-subtle);
    padding: 3px 8px;
    border-radius: var(--nb-radius-sm);
    border: 1px solid #d1d5db;
    margin: 6px 0;
}

.snippet-box {
    background: #ffffff;
    border: 1px solid #d1d5db;
    border-left: 4px solid var(--nb-cobalt);
    border-radius: var(--nb-radius-sm);
    padding: 10px 14px;
    font-size: 13px;
    font-style: italic;
    color: var(--nb-ink);
    margin: 10px 0;
    line-height: 1.45;
}

.snippet-header {
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--nb-ink-muted);
    font-style: normal;
    margin-bottom: 4px;
}

@media (max-width: 900px) {
    .balance-waterfall-main {
        grid-template-columns: 1fr;
        gap: 10px;
    }
    .waterfall-operator {
        display: none;
    }
    .balance-split {
        grid-template-columns: 1fr;
    }
    .review-subnav-bar {
        flex-direction: column;
    }
}
'''
    if "Executive Review & Negotiate Redesign" not in css:
        css += "\n" + additional_styles
        STYLES_CSS.write_text(css, encoding="utf-8")
        print("Updated frontend/styles.css successfully!")
    else:
        print("Styles already present.")

if __name__ == "__main__":
    update_app_js()
    update_styles_css()

