document.addEventListener('DOMContentLoaded', () => {
    let apiKey = sessionStorage.getItem('recoverflowApiKey') || sessionStorage.getItem('apexApiKey') || '';
    let selectedCaseId = null;
    let caseRows = [];
    if (apiKey) {
        sessionStorage.setItem('recoverflowApiKey', apiKey);
        sessionStorage.removeItem('apexApiKey');
    }
    const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[char]));
    const displayStatus = value => ({
        pending: 'Open', partially_matched: 'Partially paid', paid: 'Paid',
        draft: 'Draft', approved: 'Approved', sent: 'Sent',
        contacted_manually: 'Contact recorded', disputed: 'Disputed',
        PARTIALLY_RESOLVED: 'Partially resolved', RESOLVED_PAID: 'Resolved · paid'
    }[value] || String(value || 'Unknown'));
    const formatCents = cents => {
        const value = BigInt(cents || 0);
        const whole = (value < 0n ? -value : value) / 100n;
        const fraction = ((value < 0n ? -value : value) % 100n).toString().padStart(2, '0');
        return `${value < 0n ? '-' : ''}${whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`;
    };
    const money = (currency, cents) => `${currency === 'INR' ? '₹' : escapeHtml(currency) + ' '}${formatCents(cents)}`;
    const localEvidence = new Map([
        ['docs/invoices/INV-2026-HERO.pdf', '/evidence/INV-2026-HERO.pdf'],
        ['docs/po/PO-2026-HERO.pdf', '/evidence/PO-2026-HERO.pdf']
    ]);
    async function apiFetch(url, options = {}) {
        if (!apiKey) throw new Error('Enter your API key first.');
        const headers = new Headers(options.headers || {});
        headers.set('X-RECOVERFLOW-API-KEY', apiKey);
        const response = await fetch(url, {...options, headers});
        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail || `Request failed (${response.status})`);
        }
        return response;
    }
    async function loadSummary() {
        const status = document.getElementById('system-status-text');
        try {
            const data = await (await apiFetch('/api/v1/reports/summary')).json();
            document.getElementById('dso-value').textContent =
                data.dso_days == null ? 'No DSO data' : `${data.dso_days.toFixed(1)} days`;
            document.getElementById('pending-value').textContent = data.pending_reconciliations;
            document.getElementById('fraud-value').textContent = data.open_fraud_alerts;
            status.textContent = 'Connected';
            document.getElementById('status-indicator').classList.add('online');
            document.getElementById('auth-form').classList.add('connected');
            loadOverview();
        } catch (error) {
            status.textContent = error.message;
            document.getElementById('status-indicator').classList.remove('online');
        }
    }
    async function loadOverview() {
        const queue = document.getElementById('overview-queue');
        const activity = document.getElementById('overview-activity');
        queue.textContent = 'Loading cases…';
        activity.textContent = 'Loading ledger activity…';
        try {
            const rows = await (await apiFetch('/api/v1/cases')).json();
            const open = rows.filter(row => row.outstanding_cents > 0).slice(0, 5);
            queue.innerHTML = open.length ? open.map(row => `<div class="queue-row"><div><strong class="mono">${escapeHtml(row.invoice_number)}</strong><small>${escapeHtml(row.customer)} · Due ${escapeHtml(row.due_date)}</small></div><div><strong>${money(row.currency, row.undisputed_cents)}</strong><small>${row.contact_suppressed ? 'Contact paused' : 'Undisputed'}</small><button type="button" class="btn overview-case" data-id="${Number(row.invoice_id)}">Open file</button></div></div>`).join('') : '<p class="empty-state">No open receivable cases.</p>';
            queue.querySelectorAll('.overview-case').forEach(button => button.addEventListener('click', () => navigate('cases', button.dataset.id)));
            const details = await Promise.all(rows.slice(0, 3).map(row => apiFetch(`/api/v1/cases/${row.invoice_id}`).then(res => res.json())));
            const events = details.flatMap(row => [
                ...(row.entries || []).map(item => ({label: `${displayStatus(item.kind)} · ${money(item.currency, item.amount_cents < 0 ? -item.amount_cents : item.amount_cents)}`, meta: `${row.invoice_number} · ${item.reference}`})),
                ...(row.messages || []).map(item => ({label: item.is_injection ? 'Blocked untrusted message' : `Customer message · ${displayStatus(item.category)}`, meta: row.invoice_number}))
            ]).slice(-5).reverse();
            activity.innerHTML = events.length ? events.map(item => `<div class="activity-row"><span>${escapeHtml(item.label)}<small>${escapeHtml(item.meta)}</small></span></div>`).join('') : '<p class="empty-state">No ledger activity in the first three cases.</p>';
        } catch (error) { queue.textContent = error.message; activity.textContent = 'Activity unavailable.'; }
    }
    document.getElementById('auth-form').addEventListener('submit', event => {
        event.preventDefault();
        apiKey = document.getElementById('api-key').value;
        sessionStorage.setItem('recoverflowApiKey', apiKey);
        document.getElementById('api-key').value = '';
        loadSummary();
    });
    document.getElementById('forget-key').addEventListener('click', () => {
        apiKey = '';
        sessionStorage.removeItem('recoverflowApiKey');
        sessionStorage.removeItem('apexApiKey');
        document.getElementById('system-status-text').textContent = 'Enter API key';
        document.getElementById('status-indicator').classList.remove('online');
        document.getElementById('auth-form').classList.remove('connected');
        window.location.reload();
    });
    if (apiKey) loadSummary();
    // Navigational Logic
    const navItems = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.view');

    function navigate(targetView, caseId = null) {
            const item = document.querySelector(`.nav-item[data-view="${targetView}"]`);
            
            navItems.forEach(n => n.classList.remove('active'));
            views.forEach(v => v.classList.remove('active'));
            
            item.classList.add('active');
            document.getElementById(`view-${targetView}`).classList.add('active');
            document.querySelector('main header h2').textContent = targetView === 'dashboard' ? 'Overview' : item.textContent;
            const descriptions = {dashboard:'The work that needs a decision today.',upload:'Bring receivables into review.',cases:'One balance, one evidence trail, one decision at a time.',reconciliation:'Check payment matches before posting.',dunning:'Review collection wording and contact records.',connected:'Provider status and controlled schedules.',agent:'Assess, edit, and approve exact draft versions.',fraud:'Resolve exceptions with a recorded reason.'};
            document.getElementById('view-description').textContent = descriptions[targetView];

            // Load data when view is opened
            if(targetView === 'reconciliation') loadReconciliations();
            if(targetView === 'dunning') loadDunning();
            if(targetView === 'fraud') loadFraud();
            if(targetView === 'upload') loadReviewQueue();
            if(targetView === 'cases') loadCases();
            if(targetView === 'dashboard') loadSummary();
            if(targetView === 'connected') loadConnected();
            if(targetView === 'agent') loadAgent();
            if (caseId) openCase(caseId);
    }
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navigate(item.dataset.view);
        });
    });
    document.getElementById('overview-open-cases').addEventListener('click', () => navigate('cases'));
    document.getElementById('case-close').addEventListener('click', () => { document.getElementById('case-detail').classList.add('hidden'); selectedCaseId = null; });
    document.getElementById('case-search').addEventListener('input', event => renderCases(event.target.value));

    // Upload Form
    const uploadForm = document.getElementById('upload-form');
    if(uploadForm) {
        uploadForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById('invoice-file');
            if (!fileInput.files.length) return;

            const resultDiv = document.getElementById('upload-result');
            resultDiv.textContent = 'Uploading invoice and starting processing...';

            try {
                const invoiceType = document.getElementById('invoice-type').value;
                const res = await apiFetch(`/api/v1/invoices/upload?invoice_type=${invoiceType}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/pdf'},
                    body: fileInput.files[0]
                });
                const data = await res.json();
                resultDiv.textContent = `Upload queued. Job: ${data.job_id}`;
                const poll = async () => {
                    try {
                        const job = await (await apiFetch(`/api/v1/invoices/jobs/${data.job_id}`)).json();
                        resultDiv.textContent = `Processing: ${job.status}${job.invoice_id ? ' — invoice ' + job.invoice_id : ''}${job.error ? ' — ' + job.error : ''}`;
                        if (job.status === 'queued' || job.status === 'processing') setTimeout(poll, 1500);
                        else {
                            loadSummary(); loadReviewQueue();
                            if (!job.invoice_id && (job.status === 'failed' || job.status === 'needs_review')) {
                                const retry = document.createElement('button');
                                retry.type = 'button'; retry.className = 'btn'; retry.textContent = 'Retry processing';
                                retry.addEventListener('click', async () => {
                                    try {
                                        await apiFetch(`/api/v1/invoices/jobs/${data.job_id}/retry`, {method: 'POST'});
                                        resultDiv.textContent = 'Retry queued.';
                                        setTimeout(poll, 1500);
                                    } catch (error) { resultDiv.textContent = error.message; }
                                });
                                resultDiv.append(' ', retry);
                            }
                        }
                    } catch (error) { resultDiv.textContent = error.message; }
                };
                setTimeout(poll, 1500);
                fileInput.value = '';
            } catch (error) {
                resultDiv.textContent = `Upload error: ${error.message}`;
            }
        });
    }
    document.getElementById('import-form').addEventListener('submit', async event => {
        event.preventDefault();
        const file = document.getElementById('import-file').files[0];
        const result = document.getElementById('import-result');
        if (!file) return;
        result.textContent = 'Importing receivables...';
        try {
            const response = await apiFetch('/api/v1/imports/receivables/csv', {
                method: 'POST', headers: {'Content-Type': 'text/csv'}, body: file
            });
            const data = await response.json();
            result.textContent = `Imported ${data.imported}; already present ${data.skipped}.`;
            loadCases();
        } catch (error) { result.textContent = error.message; }
    });
    document.getElementById('manual-invoice-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form));
        values.invoice_type = 'AR';
        values.total_amount = Number(values.total_amount);
        const result = document.getElementById('manual-invoice-result');
        try {
            const response = await apiFetch('/api/v1/invoices/manual', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(values)
            });
            const created = await response.json();
            result.textContent = `Receivable saved with ID ${created.id}.`;
            form.reset();
            loadCases();
        } catch (error) { result.textContent = error.message; }
    });

    async function loadReviewQueue() {
        const container = document.getElementById('review-list');
        try {
            const data = await (await apiFetch('/api/v1/invoices/?status=pending_review')).json();
            if (!data.length) { container.textContent = 'No invoices awaiting review.'; return; }
            container.innerHTML = `<div class="stack">${data.map(item => `
                <form class="subcard review-form" data-id="${Number(item.id)}">
                    <strong>Invoice ${escapeHtml(item.invoice_number)}</strong>
                    <div class="data-form">
                        <input name="invoice_number" value="${escapeHtml(item.invoice_number)}" aria-label="Invoice number" required>
                        <select name="invoice_type"><option value="AR" ${item.invoice_type === 'AR' ? 'selected' : ''}>AR</option><option value="AP" ${item.invoice_type === 'AP' ? 'selected' : ''}>AP</option></select>
                        <input name="counterparty_name" value="${escapeHtml(item.counterparty_name)}" aria-label="Customer or vendor" required>
                        <input name="counterparty_email" type="email" value="${escapeHtml(item.counterparty_email || '')}" placeholder="Email">
                        <input name="issue_date" type="date" value="${escapeHtml(item.issue_date)}" required>
                        <input name="due_date" type="date" value="${escapeHtml(item.due_date)}" required>
                        <input name="total_amount" type="number" step="0.01" min="0.01" value="${Number(item.total_amount).toFixed(2)}" required>
                        <input name="currency" value="${escapeHtml(item.currency || 'USD')}" maxlength="3" aria-label="Currency code" required>
                        <button type="submit" class="btn btn-primary">Confirm reviewed invoice</button>
                    </div>
                </form>`).join('')}</div>`;
            container.querySelectorAll('.review-form').forEach(form => form.addEventListener('submit', async event => {
                event.preventDefault();
                const values = Object.fromEntries(new FormData(form));
                values.total_amount = Number(values.total_amount);
                try {
                    await apiFetch(`/api/v1/invoices/${form.dataset.id}/review`, {
                        method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(values)
                    });
                    loadReviewQueue(); loadCases();
                } catch (error) { alert(error.message); }
            }));
        } catch (error) { container.textContent = error.message; }
    }

    async function loadCases() {
        const container = document.getElementById('case-list');
        container.textContent = 'Loading cases…';
        try {
            caseRows = await (await apiFetch('/api/v1/cases')).json();
            renderCases(document.getElementById('case-search').value);
        } catch (error) { container.textContent = error.message; }
    }
    function renderCases(query = '') {
        const container = document.getElementById('case-list');
        const search = query.trim().toLocaleLowerCase();
        const rows = caseRows.filter(item => `${item.invoice_number} ${item.customer}`.toLocaleLowerCase().includes(search));
        container.innerHTML = rows.length ? `<p class="mobile-hint">Swipe the table to see each case action →</p><div class="table-container"><table><thead><tr><th scope="col">Invoice</th><th scope="col">Customer</th><th scope="col">Due</th><th scope="col">Outstanding</th><th scope="col">Undisputed</th><th scope="col">Status</th><th scope="col">Action</th></tr></thead><tbody>${rows.map(item => `
            <tr><td class="mono">${escapeHtml(item.invoice_number)}</td><td>${escapeHtml(item.customer)}</td><td>${escapeHtml(item.due_date)}</td><td>${money(item.currency, item.outstanding_cents)}</td><td>${money(item.currency, item.undisputed_cents)}</td><td><span class="state-text">${escapeHtml(displayStatus(item.status))}</span>${item.contact_suppressed ? '<br><span class="state-text blocked">Contact paused</span>' : ''}</td><td><button type="button" class="btn case-open" data-id="${Number(item.invoice_id)}">Open file</button></td></tr>`).join('')}</tbody></table></div>` : `<p class="empty-state">${caseRows.length ? 'No cases match this search.' : 'No receivable cases yet.'}</p>`;
        container.querySelectorAll('.case-open').forEach(button => button.addEventListener('click', () => openCase(button.dataset.id)));
    }

    async function openCase(id) {
        const detail = document.getElementById('case-detail');
        try {
            const data = await (await apiFetch(`/api/v1/cases/${id}`)).json();
            selectedCaseId = id;
            detail.classList.remove('hidden');

            const injectionMsg = (data.messages || []).find(m => m.is_injection);
            const injectionHtml = injectionMsg ? `
                <div class="injection-alert">
                    <div>
                        <strong>Blocked policy event · Untrusted customer message</strong>
                        <p>The message was retained as evidence; its instruction was not followed. ${escapeHtml(injectionMsg.rejection_reason || '')}</p>
                    </div>
                </div>` : '';

            const sourceFor = (claim, cents) => {
                const evidence = (data.evidence || []).find(ev => ev.claim_type === claim && ev.amount_cents === cents);
                if (evidence) return `<button type="button" class="source-chip" data-claim="${escapeHtml(claim)}">Source · ${escapeHtml(evidence.title)}</button>`;
                if (cents === 0) return '<span class="source-unavailable">No amount currently due</span>';
                return '<button type="button" class="source-chip" data-claim="ledger">Source · Current ledger activity</button>';
            };
            const metric = (label, cents, claim, className = '') => `<div class="balance-step ${className}"><span class="label">${label}</span><span class="val">${money(data.currency, cents)}</span>${sourceFor(claim, cents)}</div>`;
            const leaf = (label, cents, claim, className) => `<div class="balance-leaf ${className}"><span class="label">${label}</span><span class="val">${money(data.currency, cents)}</span>${sourceFor(claim, cents)}</div>`;

            const splitHtml = `
                ${injectionHtml}
                <div class="case-heading"><h3 class="mono">${escapeHtml(data.invoice_number)}</h3><p>${escapeHtml(data.customer)}</p></div>
                <div class="case-meta"><span>Due <strong>${escapeHtml(data.due_date)}</strong></span><span>Status <strong>${escapeHtml(displayStatus(data.status))}</strong></span><span>${data.contact_suppressed ? 'Contact paused' : 'Contact eligible under policy'}</span></div>
                <div class="balance-story">
                    ${metric('Invoice total', data.invoice_total_cents, 'invoice_total')}
                    ${metric('Received', data.received_cents, 'received_payment', 'received')}
                    ${metric('Outstanding', data.outstanding_cents, 'undisputed_balance')}
                    <div class="balance-split">${leaf('Disputed · on hold', data.disputed_cents, 'dispute_item', 'disputed')}${leaf('Undisputed · eligible', data.undisputed_cents, 'undisputed_balance', 'undisputed')}</div>
                </div>
            `;

            document.getElementById('case-summary').innerHTML = splitHtml;

            // Source controls point to the exact evidence record rendered below.
            document.getElementById('case-summary').querySelectorAll('.source-chip').forEach(chip => {
                chip.addEventListener('click', (e) => {
                    e.preventDefault();
                    const claim = chip.getAttribute('data-claim');
                    document.querySelectorAll('.evidence-card').forEach(c => c.classList.remove('highlighted'));
                    const target = claim === 'ledger' ? document.getElementById('ledger-activity') : [...document.querySelectorAll('.evidence-card')].find(card => card.dataset.claim === claim);
                    if (target) {
                        target.classList.add('highlighted');
                        target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                    }
                });
            });

            document.getElementById('create-payment-link').disabled = data.currency !== 'INR' || data.undisputed_cents <= 0 || data.requires_human_review;
            document.getElementById('payment-link-result').textContent = '';
            document.getElementById('resume-form').classList.toggle('hidden', !data.contact_suppressed);
            document.getElementById('shopify-confirm-form').classList.toggle('hidden', !(data.source_system === 'shopify' && data.requires_human_review));

            // Evidence Investigation Cards
            const evidenceHtml = `
                <h4>Evidence &amp; activity</h4>
                <p>Linked records support the balance story. Unverified material is labeled.</p>
                <div class="evidence-list">
                    ${(data.evidence || []).map(ev => `
                        <div class="evidence-card" id="evidence-${Number(ev.id)}" data-claim="${escapeHtml(ev.claim_type)}">
                            <div class="evidence-header">
                                <strong>${localEvidence.has(ev.source_reference) ? `<a class="document-link" href="${localEvidence.get(ev.source_reference)}" target="_blank" rel="noopener noreferrer">${escapeHtml(ev.title)} · Open PDF</a>` : escapeHtml(ev.title)}</strong>
                                <span class="source-tag">${escapeHtml(ev.source_type)} · ${ev.verified ? 'Marked verified' : 'Not verified'}</span>
                            </div>
                            <p style="margin:4px 0;font-size:13px;">${escapeHtml(ev.description)}</p>
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px;">
                                <span class="evidence-ref">Source: ${escapeHtml(ev.source_reference)}</span>
                                ${ev.amount_cents != null ? `<strong>${money(data.currency, ev.amount_cents)}</strong>` : ''}
                            </div>
                            ${ev.source_snippet ? `<div class="snippet-box">"${escapeHtml(ev.source_snippet)}"</div>` : ''}
                        </div>
                    `).join('') || '<p>No linked evidence items yet.</p>'}
                </div>
            `;

            document.getElementById('case-history').innerHTML = `
                ${evidenceHtml}
                <h4 id="ledger-activity">Current ledger entries &amp; activity</h4>
                <div class="stack">${[
                    ...data.entries.map(item => `<div class="subcard">${escapeHtml(item.kind)}: ${money(item.currency, item.amount_cents < 0 ? -item.amount_cents : item.amount_cents)} · <span class="mono">${escapeHtml(item.reference)}</span>${item.amount_cents < 0 ? ` <button type="button" class="btn reverse-entry" data-id="${Number(item.id)}">Reverse (admin)</button>` : ''}</div>`),
                    ...data.messages.map(item => `<div class="subcard">${escapeHtml(item.category)}: ${escapeHtml(item.body)}${item.is_injection ? ' <span class="state-text blocked">Blocked instruction</span>' : ''}</div>`),
                    ...data.campaigns.map(item => `<div class="subcard">Collection draft stage ${escapeHtml(item.campaign_stage)}: ${escapeHtml(displayStatus(item.status))}</div>`),
                    ...(data.agent_notes || []).map(item => `<div class="subcard">Agent note: ${escapeHtml(item.body)}</div>`)
                ].join('') || '<p>No activity yet.</p>'}</div>
            `;

            detail.querySelectorAll('.reverse-entry').forEach(button => button.addEventListener('click', async () => {
                const reason = prompt('Why is this receipt or credit being reversed?');
                if (!reason) return;
                try {
                    await apiFetch(`/api/v1/cases/${id}/entries/${button.dataset.id}/reverse`, {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({reason})
                    });
                    openCase(id); loadCases();
                } catch (error) { alert(error.message); }
            }));
            loadCases();
            detail.scrollIntoView({behavior: 'smooth', block: 'start'});
        } catch (error) { detail.classList.remove('hidden'); document.getElementById('case-summary').textContent = error.message; }
    }

    document.getElementById('entry-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form));
        const result = document.getElementById('entry-result');
        try {
            await apiFetch(`/api/v1/cases/${selectedCaseId}/entries`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(values)
            });
            result.textContent = 'Balance entry recorded.';
            form.reset(); openCase(selectedCaseId); loadCases();
        } catch (error) { result.textContent = error.message; }
    });
    document.getElementById('reply-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form));
        const result = document.getElementById('reply-result');
        try {
            await apiFetch(`/api/v1/cases/${selectedCaseId}/replies`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(values)
            });
            result.textContent = 'Customer reply recorded.';
            form.reset(); openCase(selectedCaseId); loadCases();
        } catch (error) { result.textContent = error.message; }
    });
    document.getElementById('resume-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const result = document.getElementById('resume-result');
        const payload = {reason: form.elements.reason.value,
                         consent_restored: form.elements.consent_restored.checked};
        try {
            await apiFetch(`/api/v1/cases/${selectedCaseId}/resume`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(payload)
            });
            result.textContent = 'Contact resumed.';
            form.reset(); openCase(selectedCaseId); loadCases();
        } catch (error) { result.textContent = error.message; }
    });
    document.getElementById('shopify-confirm-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const result = document.getElementById('shopify-confirm-result');
        try {
            await apiFetch(`/api/v1/sync/shopify/cases/${selectedCaseId}/confirm`, {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({reason: form.elements.reason.value,
                    accept_due_date_change: form.elements.accept_due_date_change.checked})
            });
            result.textContent = 'Shopify balance confirmed. Contact remains paused until an admin resumes the case.';
            form.reset(); openCase(selectedCaseId); loadCases();
        } catch (error) { result.textContent = error.message; }
    });
    document.getElementById('draft-form').addEventListener('submit', async event => {
        event.preventDefault();
        const values = Object.fromEntries(new FormData(event.currentTarget));
        const result = document.getElementById('draft-result');
        try {
            await apiFetch(`/api/v1/dunning/trigger-stage?invoice_id=${encodeURIComponent(values.invoice_id)}&stage=${encodeURIComponent(values.stage)}`, {
                method: 'POST'
            });
            result.textContent = 'Collection draft created. No email was sent.';
            loadDunning();
        } catch (error) { result.textContent = error.message; }
    });

    document.getElementById('create-payment-link').addEventListener('click', async () => {
        const result = document.getElementById('payment-link-result');
        if (!selectedCaseId) return;
        result.textContent = 'Creating payment link...';
        try {
            const response = await apiFetch('/api/v1/payments/links', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({invoice_id: Number(selectedCaseId), idempotency_key: crypto.randomUUID()})
            });
            const link = await response.json();
            result.innerHTML = link.provider_link_id?.startsWith('plink_mock_')
                ? 'Demo payment link created. This is a local simulation and cannot collect a real payment.'
                : `Link created: <a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(link.url)}</a>. Share only after checking the case.`;
        } catch (error) { result.textContent = error.message; }
    });

    document.getElementById('shopify-sync').addEventListener('click', async () => {
        const result = document.getElementById('shopify-sync-result');
        result.textContent = 'Syncing credit terms...';
        try {
            const data = await (await apiFetch('/api/v1/sync/shopify', {method: 'POST'})).json();
            result.textContent = `Imported ${data.imported}; unchanged ${data.unchanged}; needs review ${data.review}; skipped ${data.skipped}.`;
            loadCases();
        } catch (error) { result.textContent = error.message; }
    });

    document.getElementById('policy-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form));
        const payload = {enabled: form.elements.enabled.checked, timezone: values.timezone,
            run_hour: Number(values.run_hour), stage1_days: Number(values.stage1_days),
            stage2_days: Number(values.stage2_days), stage3_days: Number(values.stage3_days),
            stage4_days: Number(values.stage4_days)};
        const result = document.getElementById('policy-result');
        try {
            await apiFetch('/api/v1/policies/collection', {
                method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            result.textContent = 'Schedule saved. Drafts still require staff approval.';
        } catch (error) { result.textContent = error.message; }
    });

    async function loadConnected() {
        const status = document.getElementById('provider-status');
        try {
            const data = await (await apiFetch('/api/v1/integrations/status')).json();
            status.textContent = `Shopify: ${data.shopify.configured ? 'configured' : 'not configured'} • Razorpay: ${data.razorpay.simulated ? 'mock simulation; no real payments' : data.razorpay.configured ? data.razorpay.mode : 'not configured'} • WhatsApp inbound: ${data.meta_whatsapp.inbound_configured ? 'configured' : 'not configured'} • WhatsApp replies: ${data.meta_whatsapp.outbound_configured ? 'configured' : 'not configured'}`;
            document.getElementById('shopify-sync').disabled = !data.shopify.configured;
            const policy = await (await apiFetch('/api/v1/policies/collection')).json();
            const form = document.getElementById('policy-form');
            for (const field of ['timezone', 'run_hour', 'stage1_days', 'stage2_days', 'stage3_days', 'stage4_days']) form.elements[field].value = policy[field];
            form.elements.enabled.checked = !!policy.enabled;
        } catch (error) { status.textContent = error.message; }
        await Promise.all([loadPaymentLinks(), loadMessageInbox(), loadProviderEvents()]);
    }

    async function loadAgent() {
        const status = document.getElementById('agent-status');
        let agentStatus = null;
        try {
            const data = await (await apiFetch('/api/v1/agent/status')).json();
            agentStatus = data;
            const rl = data.rate_limits;
            const modelText = data.model_configured
                ? (rl ? `${data.model} (RPM: ${rl.rpm_used}/${rl.rpm_limit}, RPD: ${rl.rpd_used}/${rl.rpd_limit})` : data.model)
                : 'rules-only; add Gemini API key to enable AI';
            status.textContent = `AI wording: ${modelText} • Agent: ${data.policy?.enabled ? 'enabled' : 'off'}`;
            const policy = data.policy || {enabled: false, auto_assess: false,
                auto_execute_internal: false, max_assessments_per_day: 20,
                max_internal_actions_per_day: 5, max_balance_cents: 100000};
            const form = document.getElementById('agent-policy-form');
            for (const key of ['enabled', 'auto_assess', 'auto_execute_internal'])
                form.elements[key].checked = !!policy[key];
            for (const key of ['max_assessments_per_day', 'max_internal_actions_per_day'])
                form.elements[key].value = policy[key];
            form.elements.max_balance_cents.value = (policy.max_balance_cents / 100).toFixed(2);
        } catch (error) { status.textContent = error.message; }
        const proposals = await loadAgentProposals();
        await loadAgentVersions(proposals, agentStatus);
    }

    async function loadAgentProposals() {
        const container = document.getElementById('agent-proposals');
        try {
            const rows = await (await apiFetch('/api/v1/agent/proposals')).json();
            container.innerHTML = rows.length ? `<div class="stack">${rows.map(item => {
                const open = item.status === 'proposed';
                const flags = JSON.parse(item.risk_flags || '[]');
                return `<div class="subcard"><strong>Case ${Number(item.invoice_id)} · ${escapeHtml(item.action)}</strong>
                    <small> · ${escapeHtml(item.status)} · ${escapeHtml(item.engine)}</small>
                    <p class="prewrap">${escapeHtml(item.summary)}</p>
                    <p>${escapeHtml(item.rationale)}</p>
                    ${flags.length ? `<p>Checks: ${escapeHtml(flags.join(', '))}</p>` : ''}
                    ${open ? `<button type="button" class="btn agent-note" data-id="${Number(item.id)}">Save internal note</button>
                        ${item.action === 'collection_draft' ? `<button type="button" class="btn agent-draft" data-id="${Number(item.id)}">Create draft for staff approval</button>` : ''}
                        ${item.action === 'reply_draft' ? `<form class="agent-reply-form data-form" data-id="${Number(item.id)}"><textarea name="body" maxlength="500" required aria-label="Review customer reply">${escapeHtml(item.draft_text || '')}</textarea><button type="submit" class="btn btn-primary">Review and send reply</button></form>` : ''}
                        <button type="button" class="btn agent-reject" data-id="${Number(item.id)}">Reject proposal</button>` : ''}
                    </div>`;
            }).join('')}</div>` : '<p>No assessments yet. Enable the agent and assess a case.</p>';
            const post = async (id, suffix, body) => {
                await apiFetch(`/api/v1/agent/proposals/${id}/${suffix}`, {method: 'POST',
                    ...(body ? {headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {})});
                loadAgentProposals();
            };
            container.querySelectorAll('.agent-note').forEach(button => button.addEventListener('click', async () => {
                try { await post(button.dataset.id, 'internal/case_note'); }
                catch (error) { alert(error.message); }
            }));
            container.querySelectorAll('.agent-draft').forEach(button => button.addEventListener('click', async () => {
                try { await post(button.dataset.id, 'internal/collection_draft'); loadDunning(); }
                catch (error) { alert(error.message); }
            }));
            container.querySelectorAll('.agent-reject').forEach(button => button.addEventListener('click', async () => {
                const reason = prompt('Why should this proposal be rejected?');
                if (!reason) return;
                try { await post(button.dataset.id, 'reject', {reason}); }
                catch (error) { alert(error.message); }
            }));
            container.querySelectorAll('.agent-reply-form').forEach(form => form.addEventListener('submit', async event => {
                event.preventDefault();
                if (!confirm('Send this reviewed reply to the customer now?')) return;
                try { await post(form.dataset.id, 'send-reply', {body: new FormData(form).get('body')}); }
                catch (error) { alert(error.message); }
            }));
            return rows;
        } catch (error) { container.textContent = error.message; }
    }

    async function loadPaymentLinks() {
        const container = document.getElementById('payment-link-list');
        try {
            const links = await (await apiFetch('/api/v1/payments/links')).json();
            container.innerHTML = links.length ? `<p class="mobile-hint">Swipe table to see links →</p><div class="table-container"><table><tr><th>Invoice</th><th>Amount</th><th>Status</th><th>Link</th><th>Action</th></tr>${links.map(link => `<tr><td>${Number(link.invoice_id)}</td><td>INR ${(link.amount_cents / 100).toFixed(2)}</td><td>${escapeHtml(link.status)}</td><td>${link.provider_link_id?.startsWith('plink_mock_') ? 'Demo only' : link.url ? `<a href="${escapeHtml(link.url)}" target="_blank" rel="noopener noreferrer">Open</a>` : 'Pending review'}</td><td>${link.provider_link_id && ['open', 'partially_paid', 'needs_review'].includes(link.status) ? `<button type="button" class="btn cancel-link" data-id="${Number(link.id)}">Cancel (admin)</button>` : !link.provider_link_id && ['creating', 'needs_review'].includes(link.status) ? `<button type="button" class="btn recover-link" data-id="${Number(link.id)}">Check Razorpay (admin)</button>` : ''}</td></tr>`).join('')}</table></div>` : '<p>No payment links yet.</p>';
            container.querySelectorAll('.cancel-link').forEach(button => button.addEventListener('click', async () => {
                try {
                    await apiFetch(`/api/v1/payments/links/${button.dataset.id}/cancel`, {method: 'POST'});
                    loadPaymentLinks();
                } catch (error) { alert(error.message); }
            }));
            container.querySelectorAll('.recover-link').forEach(button => button.addEventListener('click', async () => {
                try {
                    await apiFetch(`/api/v1/payments/links/${button.dataset.id}/recover`, {method: 'POST'});
                    loadPaymentLinks();
                } catch (error) { alert(error.message); }
            }));
        } catch (error) { container.textContent = error.message; }
    }

    async function loadMessageInbox() {
        const container = document.getElementById('message-inbox');
        try {
            const messages = await (await apiFetch('/api/v1/messages/inbox')).json();
            container.innerHTML = messages.length ? `<div class="stack">${messages.map(item => `<div class="subcard"><strong>${escapeHtml(item.sender)}</strong> • ${escapeHtml(item.status)}<p class="prewrap">${escapeHtml(item.body)}</p>${item.status !== 'triaged' ? `<form class="inbox-triage data-form" data-id="${Number(item.id)}"><input name="invoice_id" type="number" min="1" value="${item.invoice_id ? Number(item.invoice_id) : ''}" placeholder="Case ID" required><select name="category"><option value="question">Question</option><option value="needs_time">Needs time</option><option value="paid_claim">Already paid</option><option value="dispute">Dispute</option><option value="opt_out">Opt out</option><option value="other">Other</option></select><button class="btn btn-primary" type="submit">Triage</button></form>` : `<form class="inbox-reply data-form" data-id="${Number(item.id)}"><input name="body" placeholder="Staff reply within 24 hours" required><button class="btn" type="submit">Send reply</button></form>`}</div>`).join('')}</div>` : '<p>No WhatsApp messages yet.</p>';
            container.querySelectorAll('.inbox-triage').forEach(form => form.addEventListener('submit', async event => {
                event.preventDefault();
                const values = Object.fromEntries(new FormData(form));
                try {
                    await apiFetch(`/api/v1/messages/${form.dataset.id}/triage`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({invoice_id: Number(values.invoice_id), category: values.category})});
                    loadMessageInbox(); loadCases();
                } catch (error) { alert(error.message); }
            }));
            container.querySelectorAll('.inbox-reply').forEach(form => form.addEventListener('submit', async event => {
                event.preventDefault();
                const body = new FormData(form).get('body');
                try {
                    await apiFetch(`/api/v1/messages/${form.dataset.id}/reply`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({body, idempotency_key: crypto.randomUUID()})});
                    form.reset(); alert('Reply accepted by Meta.');
                } catch (error) { alert(error.message); }
            }));
        } catch (error) { container.textContent = error.message; }
    }

    async function loadProviderEvents() {
        const container = document.getElementById('provider-events');
        try {
            const events = await (await apiFetch('/api/v1/integrations/events')).json();
            const attention = events.filter(item => item.status === 'needs_review' || item.status === 'queued');
            container.innerHTML = attention.length ? `<div class="stack">${attention.map(item => `<div class="subcard"><strong>${escapeHtml(item.provider)}</strong> • ${escapeHtml(item.kind)} • ${escapeHtml(item.status)}<p>${escapeHtml(item.error || 'Review the related case or wait for the next sync.')}</p><small>Event ${escapeHtml(item.event_id)}</small>${item.status === 'needs_review' ? ` <button type="button" class="btn resolve-provider-event" data-id="${Number(item.id)}">Mark reviewed (admin)</button>` : ''}</div>`).join('')}</div>` : '<p>No provider events need attention.</p>';
            container.querySelectorAll('.resolve-provider-event').forEach(button => button.addEventListener('click', async () => {
                const reason = prompt('How was this provider event checked and resolved?');
                if (!reason) return;
                try {
                    await apiFetch(`/api/v1/integrations/events/${button.dataset.id}/resolve`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({reason})});
                    loadProviderEvents();
                } catch (error) { alert(error.message); }
            }));
        } catch (error) { container.textContent = error.message; }
    }

    // API calls to load data
    async function loadReconciliations() {
        const container = document.getElementById('reconciliation-list');
        try {
            const res = await apiFetch('/api/v1/reconciliation/pending');
            const data = await res.json();
            
            if(data.length === 0) {
                container.innerHTML = '<p>No reconciliations are awaiting review.</p>';
                return;
            }

            let html = `<p class="mobile-hint">Swipe table to review matches →</p><div class="table-container"><table><tr><th>Invoice ID</th><th>AFIS ID</th><th>Confidence</th><th>Amount</th><th>Action</th></tr>`;
            data.forEach(item => {
                html += `<tr>
                    <td>${escapeHtml(item.invoice_id)}</td>
                    <td>${escapeHtml(item.afis_transaction_id)}</td>
                    <td>${(item.confidence_score * 100).toFixed(1)}%</td>
                    <td>$${item.matched_amount.toFixed(2)}</td>
                    <td><button class="btn btn-primary" onclick="approveRecon(${Number(item.id)})">Approve</button></td>
                </tr>`;
            });
            html += `</table></div>`;
            container.innerHTML = html;
        } catch (e) {
            container.textContent = e.message;
        }
    }

    async function loadFraud() {
        const container = document.getElementById('fraud-list');
        try {
            const res = await apiFetch('/api/v1/fraud/alerts?status=open');
            const data = await res.json();
            
            if(data.length === 0) {
                container.innerHTML = '<p>No open fraud alerts.</p>';
                return;
            }

            let html = `<p class="mobile-hint">Swipe table to view alerts →</p><div class="table-container"><table><tr><th>Invoice ID</th><th>Severity</th><th>Score</th><th>Description</th><th>Action</th></tr>`;
            data.forEach(item => {
                html += `<tr>
                    <td>${escapeHtml(item.invoice_id)}</td>
                    <td><span style="color:var(--color-error);font-weight:bold;">${escapeHtml(item.severity.toUpperCase())}</span></td>
                    <td>${(item.fraud_score * 100).toFixed(1)}%</td>
                    <td>${escapeHtml(item.description)}</td>
                    <td><button class="btn btn-primary" onclick="resolveFraud(${Number(item.id)})">Mark False Positive</button></td>
                </tr>`;
            });
            html += `</table></div>`;
            container.innerHTML = html;
        } catch (e) {
            container.textContent = e.message;
        }
    }

    async function loadDunning() {
        const container = document.getElementById('dunning-list');
        try {
            const res = await apiFetch('/api/v1/dunning/campaigns');
            const data = await res.json();
            
            if(data.length === 0) {
                container.innerHTML = '<p>No collection campaigns yet.</p>';
                return;
            }

            let html = `<p class="mobile-hint">Swipe table to review draft & actions →</p><div class="table-container"><table><tr><th>Invoice</th><th>Stage</th><th>Days Overdue</th><th>Status</th><th>Draft</th></tr>`;
            data.forEach(item => {
                html += `<tr>
                    <td>${escapeHtml(item.invoice_id)}</td>
                    <td>${escapeHtml(item.campaign_stage)}</td>
                    <td>${escapeHtml(item.days_overdue)}</td>
                    <td>${escapeHtml(displayStatus(item.status))}</td>
                    <td><details><summary>Review text</summary><strong>${escapeHtml(item.email_subject)}</strong><p class="prewrap">${escapeHtml(item.email_body)}</p>${item.status === 'draft' ? `<button type="button" class="btn btn-primary approve-campaign" data-id="${Number(item.id)}">Approve draft</button>` : ''} ${item.status === 'draft' || item.status === 'approved' ? `<button type="button" class="btn refresh-campaign" data-id="${Number(item.id)}">Refresh balance</button><form class="campaign-edit" data-id="${Number(item.id)}"><input name="subject" value="${escapeHtml(item.email_subject)}" aria-label="Email subject" required><textarea name="body" aria-label="Email body" required>${escapeHtml(item.email_body)}</textarea><button type="submit" class="btn">Save edits</button></form>` : ''}${item.status === 'approved' ? `<form class="manual-contact" data-id="${Number(item.id)}"><select name="channel"><option value="email">Email</option><option value="phone">Phone</option><option value="other">Other</option></select><input name="reference" placeholder="Contact reference" required minlength="3"><button type="submit" class="btn btn-primary">Record manual contact</button></form>` : ''}</details></td>
                </tr>`;
            });
            html += `</table></div>`;
            container.innerHTML = html;
            container.querySelectorAll('.approve-campaign').forEach(button => button.addEventListener('click', async () => {
                try {
                    await apiFetch(`/api/v1/dunning/campaigns/${button.dataset.id}/approve`, {method: 'POST'});
                    loadDunning();
                } catch (error) { alert(error.message); }
            }));
            container.querySelectorAll('.refresh-campaign').forEach(button => button.addEventListener('click', async () => {
                try {
                    await apiFetch(`/api/v1/dunning/campaigns/${button.dataset.id}/refresh`, {method: 'POST'});
                    loadDunning();
                } catch (error) { alert(error.message); }
            }));
            container.querySelectorAll('.campaign-edit').forEach(form => form.addEventListener('submit', async event => {
                event.preventDefault();
                const values = Object.fromEntries(new FormData(form));
                try {
                    await apiFetch(`/api/v1/dunning/campaigns/${form.dataset.id}`, {
                        method: 'PUT', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(values)
                    });
                    loadDunning();
                } catch (error) { alert(error.message); }
            }));
            container.querySelectorAll('.manual-contact').forEach(form => form.addEventListener('submit', async event => {
                event.preventDefault();
                const values = Object.fromEntries(new FormData(form));
                try {
                    await apiFetch(`/api/v1/dunning/campaigns/${form.dataset.id}/record-contact`, {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(values)
                    });
                    loadDunning(); loadCases();
                } catch (error) { alert(error.message); }
            }));
        } catch (e) {
            container.textContent = e.message;
        }
    }

    async function loadAgentVersions(proposals = null, statusData = null) {
        const statusEl = document.getElementById('agent-status');
        const proposalsEl = document.getElementById('agent-versions');
        try {
            statusData = statusData || await (await apiFetch('/api/v1/agent/status')).json();
            const rl = statusData.rate_limits || {};
            statusEl.innerHTML = `
                <strong>Active Model:</strong> <code>${escapeHtml(statusData.model)}</code> • 
                <strong>Configured:</strong> ${statusData.model_configured ? '<span style="color:var(--color-success);font-weight:600;">Yes</span>' : '<span style="color:var(--color-text-muted);">Rules Fallback</span>'} • 
                <strong>Rate Limits:</strong> RPM: ${rl.rpm_remaining !== undefined ? rl.rpm_remaining : '—'}/${rl.rpm_limit || 15} remaining | RPD: ${rl.rpd_remaining !== undefined ? rl.rpd_remaining : '—'}/${rl.rpd_limit || 1500} remaining
            `;

            // Populate policy form
            const pol = statusData.policy || {
                enabled: false, auto_assess: false, auto_execute_internal: false,
                max_assessments_per_day: 20, max_internal_actions_per_day: 5,
                max_balance_cents: 100000
            };
            const form = document.getElementById('agent-policy-form');
            if (form) {
                form.elements['enabled'].checked = Boolean(pol.enabled);
                form.elements['auto_assess'].checked = Boolean(pol.auto_assess);
                form.elements['auto_execute_internal'].checked = Boolean(pol.auto_execute_internal);
                form.elements['max_assessments_per_day'].value = pol.max_assessments_per_day;
                form.elements['max_internal_actions_per_day'].value = pol.max_internal_actions_per_day;
                form.elements['max_balance_cents'].value = (pol.max_balance_cents / 100).toFixed(2);
            }

            // Load proposals
            proposals = proposals || await (await apiFetch('/api/v1/agent/proposals')).json();
            if (!proposals.length) {
                proposalsEl.innerHTML = '<p>No agent proposals generated yet. Use the form above to assess a case.</p>';
                return;
            }
            const currentCases = await (await apiFetch('/api/v1/cases')).json();
            const caseById = new Map(currentCases.map(row => [row.invoice_id, row]));

            proposalsEl.innerHTML = `<div class="stack">${(await Promise.all(proposals.map(async item => {
                let versions = [];
                try {
                    versions = await (await apiFetch(`/api/v1/agent/proposals/${item.id}/versions`)).json();
                } catch (_) {}
                const latestVersion = versions.length ? versions[versions.length - 1] : null;
                const isApproved = latestVersion && latestVersion.status === 'approved';
                const currentCase = caseById.get(item.invoice_id);
                const staleBalance = item.action === 'split_balance_draft' && currentCase && currentCase.undisputed_cents <= 0;

                return `
                    <div class="subcard">
                        <div class="proposal-heading">
                            <strong>Proposal #${item.id} · Case ${item.invoice_id}</strong>
                            <div class="proposal-meta">
                                <span class="state-text ${item.status === 'approved' ? 'received' : ''}">${escapeHtml(item.status)}</span>
                                <span>${escapeHtml(item.action)}</span>
                                <span class="mono">${escapeHtml(item.engine)}</span>
                            </div>
                        </div>
                        <button type="button" class="source-chip agent-case-source" data-invoice-id="${Number(item.invoice_id)}">Open case sources</button>
                        ${staleBalance ? '<p class="stale-warning">Balance changed: no undisputed amount remains. This draft is an audit record; reassess the case for a current action.</p>' : ''}
                        
                        ${item.draft_text ? `
                            <div class="proposal-draft">
                                <div class="proposal-heading">
                                    <strong>Message Draft</strong>
                                    ${latestVersion ? `
                                        <div>
                                            <span class="version-badge ${isApproved ? 'approved' : ''}">v${latestVersion.version_number} (${escapeHtml(latestVersion.status)})</span>
                                            <span class="hash-pill" title="Immutable SHA-256 Digest">#${latestVersion.version_hash.slice(0, 10)}</span>
                                        </div>` : ''}
                                </div>
                                <div class="snippet-box">${escapeHtml(item.draft_text)}</div>
                                
                                ${isApproved ? `
                                    <div class="state-text received" style="margin-bottom:8px;">
                                        Approved by ${escapeHtml(latestVersion.approved_by || 'staff')} on ${latestVersion.approved_at ? new Date(latestVersion.approved_at).toLocaleString() : 'record'}.
                                    </div>` : `
                                    <div class="proposal-actions">
                                        <button type="button" class="btn btn-primary approve-draft-btn" data-proposal-id="${item.id}" data-version-num="${latestVersion ? latestVersion.version_number : 1}" data-version-hash="${latestVersion ? latestVersion.version_hash : ''}" ${staleBalance ? 'disabled title="Case balance changed"' : ''}>Approve Version ${latestVersion ? latestVersion.version_number : 1}</button>
                                        <button type="button" class="btn reject-proposal-btn" data-proposal-id="${item.id}">Reject Proposal</button>
                                    </div>
                                    <details style="margin-top:8px;">
                                        <summary>Edit draft · creates a new version</summary>
                                        <form class="edit-draft-form" data-proposal-id="${item.id}" style="display:grid;gap:8px;margin-top:8px;">
                                            <textarea name="body" style="width:100%;min-height:90px;padding:8px;border:1px solid var(--color-border);border-radius:var(--radius-md);" required>${escapeHtml(item.draft_text)}</textarea>
                                            <input name="change_reason" placeholder="Reason for edit (e.g. adjusted wording for courtesy)" style="padding:8px;border:1px solid var(--color-border);border-radius:var(--radius-md);" required>
                                            <button type="submit" class="btn">Save as New Version</button>
                                        </form>
                                    </details>
                                `}

                                ${versions.length > 1 ? `
                                    <details style="margin-top:8px;">
                                        <summary>Version history (${versions.length} revisions)</summary>
                                        <div style="margin-top:6px;display:grid;gap:6px;">
                                            ${versions.map(v => `
                                                <div class="draft-version-item">
                                                    <div style="display:flex;justify-content:space-between;font-size:11px;">
                                                        <strong>v${v.version_number} by ${escapeHtml(v.edited_by)}</strong>
                                                        <span class="hash-pill">${v.version_hash.slice(0, 10)}</span>
                                                    </div>
                                                    <p style="margin:3px 0;font-size:11px;color:var(--color-text-muted);">${escapeHtml(v.change_reason || 'Initial draft')}</p>
                                                </div>
                                            `).join('')}
                                        </div>
                                    </details>
                                ` : ''}
                            </div>
                        ` : ''}
                    </div>
                `;
            }))).join('')}</div>`;

            // Attach Approve button listeners
            proposalsEl.querySelectorAll('.agent-case-source').forEach(button => button.addEventListener('click', () => navigate('cases', button.dataset.invoiceId)));
            proposalsEl.querySelectorAll('.approve-draft-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const proposalId = btn.dataset.proposalId;
                    const versionNum = Number(btn.dataset.versionNum);
                    const versionHash = btn.dataset.versionHash;
                    try {
                        await apiFetch(`/api/v1/agent/proposals/${proposalId}/approve`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({version_number: versionNum, version_hash: versionHash})
                        });
                        alert(`Draft Version ${versionNum} approved successfully! Approval recorded immutably.`);
                        loadAgent();
                    } catch (err) { alert(err.message); }
                });
            });

            // Attach Reject button listeners
            proposalsEl.querySelectorAll('.reject-proposal-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const proposalId = btn.dataset.proposalId;
                    const reason = prompt('Reason for rejecting proposal:');
                    if (!reason) return;
                    try {
                        await apiFetch(`/api/v1/agent/proposals/${proposalId}/reject`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({reason})
                        });
                        loadAgent();
                    } catch (err) { alert(err.message); }
                });
            });

            // Attach Edit draft form listeners
            proposalsEl.querySelectorAll('.edit-draft-form').forEach(form => {
                form.addEventListener('submit', async (e) => {
                    e.preventDefault();
                    const proposalId = form.dataset.proposalId;
                    const body = form.elements['body'].value;
                    const change_reason = form.elements['change_reason'].value;
                    try {
                        const res = await apiFetch(`/api/v1/agent/proposals/${proposalId}/edit-draft`, {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({body, change_reason})
                        });
                        const updatedVer = await res.json();
                        alert(`Created new draft revision v${updatedVer.version_number}! Review and approve when ready.`);
                        loadAgent();
                    } catch (err) { alert(err.message); }
                });
            });

        } catch (e) {
            proposalsEl.textContent = e.message;
        }
    }

    // Agent Policy Form Listener
    const agentPolicyForm = document.getElementById('agent-policy-form');
    if (agentPolicyForm) {
        agentPolicyForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const resEl = document.getElementById('agent-policy-result');
            resEl.textContent = 'Saving policy limits...';
            try {
                const payload = {
                    enabled: agentPolicyForm.elements['enabled'].checked,
                    auto_assess: agentPolicyForm.elements['auto_assess'].checked,
                    auto_execute_internal: agentPolicyForm.elements['auto_execute_internal'].checked,
                    max_assessments_per_day: Number(agentPolicyForm.elements['max_assessments_per_day'].value),
                    max_internal_actions_per_day: Number(agentPolicyForm.elements['max_internal_actions_per_day'].value),
                    max_balance_cents: Math.round(Number(agentPolicyForm.elements['max_balance_cents'].value) * 100),
                };
                await apiFetch('/api/v1/agent/policy', {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                resEl.textContent = 'Agent policy saved successfully.';
                loadAgent();
            } catch (err) { resEl.textContent = err.message; }
        });
    }

    // Assess Case Form Listener
    const agentAssessForm = document.getElementById('agent-assess-form');
    if (agentAssessForm) {
        agentAssessForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const invoiceId = agentAssessForm.elements['invoice_id'].value;
            const resEl = document.getElementById('agent-assess-result');
            resEl.textContent = 'Running assessment...';
            try {
                const res = await apiFetch(`/api/v1/agent/cases/${invoiceId}/assess`, {method: 'POST'});
                const prop = await res.json();
                resEl.textContent = `Assessment complete: Proposal #${prop.id} created with action "${prop.action}" via ${prop.engine}.`;
                agentAssessForm.reset();
                loadAgent();
            } catch (err) { resEl.textContent = err.message; }
        });
    }


    // Exported globals for inline onclick
    window.approveRecon = async (id) => {
        try {
            await apiFetch(`/api/v1/reconciliation/${id}/approve`, {method: 'POST'});
            loadReconciliations();
        } catch(e) {
            alert("Could not approve the reconciliation.");
        }
    };

    window.resolveFraud = async (id) => {
        try {
            await apiFetch(`/api/v1/fraud/${id}/resolve?resolution=false_positive`, {method: 'POST'});
            loadFraud();
        } catch(e) {
            alert("Could not resolve the fraud alert.");
        }
    };
});
// RecoverFlow dashboard module

