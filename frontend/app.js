document.addEventListener('DOMContentLoaded', () => {
    let apiKey = sessionStorage.getItem('recoverflowApiKey') || sessionStorage.getItem('apexApiKey') || '';
    let selectedCaseId = null;
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
        contacted_manually: 'Contact recorded', disputed: 'Disputed'
    }[value] || String(value || 'Unknown'));
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
        } catch (error) {
            status.textContent = error.message;
            document.getElementById('status-indicator').classList.remove('online');
        }
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
    });
    if (apiKey) loadSummary();
    // Navigational Logic
    const navItems = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.view');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetView = item.getAttribute('data-view');
            
            navItems.forEach(n => n.classList.remove('active'));
            views.forEach(v => v.classList.remove('active'));
            
            item.classList.add('active');
            document.getElementById(`view-${targetView}`).classList.add('active');
            document.querySelector('main header h2').textContent = targetView === 'dashboard' ? 'Overview' : item.textContent;

            // Load data when view is opened
            if(targetView === 'reconciliation') loadReconciliations();
            if(targetView === 'dunning') loadDunning();
            if(targetView === 'fraud') loadFraud();
            if(targetView === 'upload') loadReviewQueue();
            if(targetView === 'cases') loadCases();
            if(targetView === 'dashboard') loadSummary();
            if(targetView === 'connected') loadConnected();
            if(targetView === 'agent') loadAgent();
        });
    });

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
        try {
            const cases = await (await apiFetch('/api/v1/cases')).json();
            if (!cases.length) { container.textContent = 'No receivable cases yet.'; return; }
            container.innerHTML = `<p class="mobile-hint">Swipe the table to see each case action →</p><div class="table-container"><table><tr><th>Invoice</th><th>Customer</th><th>Due</th><th>Balance</th><th>Status</th><th>Action</th></tr>${cases.map(item => `
                <tr><td>${escapeHtml(item.invoice_number)}</td><td>${escapeHtml(item.customer)}</td>
                <td>${escapeHtml(item.due_date)}</td><td>${escapeHtml(item.currency)} ${(item.balance_cents / 100).toFixed(2)}</td>
                <td>${escapeHtml(item.contact_suppressed ? 'Contact paused' : displayStatus(item.status))}</td>
                <td><button type="button" class="btn case-open" data-id="${Number(item.invoice_id)}">Open</button></td></tr>`).join('')}</table></div>`;
            container.querySelectorAll('.case-open').forEach(button => button.addEventListener('click', () => openCase(button.dataset.id)));
        } catch (error) { container.textContent = error.message; }
    }

    async function openCase(id) {
        const detail = document.getElementById('case-detail');
        try {
            const data = await (await apiFetch(`/api/v1/cases/${id}`)).json();
            selectedCaseId = id;
            detail.classList.remove('hidden');
            document.getElementById('case-summary').textContent = `${data.customer} • ${data.invoice_number} • ${data.currency} ${(data.balance_cents / 100).toFixed(2)} outstanding${data.contact_suppressed ? ' • Contact paused' : ''}`;
            document.getElementById('create-payment-link').disabled = data.currency !== 'INR' || data.balance_cents <= 0 || data.requires_human_review || data.dispute_open;
            document.getElementById('payment-link-result').textContent = '';
            document.getElementById('resume-form').classList.toggle('hidden', !data.contact_suppressed);
            document.getElementById('shopify-confirm-form').classList.toggle('hidden', !(data.source_system === 'shopify' && data.requires_human_review));
            document.getElementById('case-history').innerHTML = `<h4>Activity</h4><div class="stack">${[
                ...data.entries.map(item => `<div class="subcard">${escapeHtml(item.kind)}: ${escapeHtml(item.currency)} ${(Math.abs(item.amount_cents) / 100).toFixed(2)} • ${escapeHtml(item.reference)}${item.amount_cents < 0 ? ` <button type="button" class="btn reverse-entry" data-id="${Number(item.id)}">Reverse (admin)</button>` : ''}</div>`),
                ...data.messages.map(item => `<div class="subcard">${escapeHtml(item.category)}: ${escapeHtml(item.body)}</div>`),
                ...data.campaigns.map(item => `<div class="subcard">Collection draft ${escapeHtml(item.campaign_stage)}: ${escapeHtml(displayStatus(item.status))}</div>`),
                ...(data.agent_notes || []).map(item => `<div class="subcard">Agent note: ${escapeHtml(item.body)}</div>`)
            ].join('') || '<p>No activity yet.</p>'}</div>`;
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

    document.getElementById('agent-policy-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const values = Object.fromEntries(new FormData(form));
        const payload = {
            enabled: form.elements.enabled.checked,
            auto_assess: form.elements.auto_assess.checked,
            auto_execute_internal: form.elements.auto_execute_internal.checked,
            max_assessments_per_day: Number(values.max_assessments_per_day),
            max_internal_actions_per_day: Number(values.max_internal_actions_per_day),
            max_balance_cents: Math.round(Number(values.max_balance_cents) * 100)
        };
        const result = document.getElementById('agent-policy-result');
        try {
            await apiFetch('/api/v1/agent/policy', {method: 'PUT',
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
            result.textContent = 'Agent limits saved.';
            loadAgent();
        } catch (error) { result.textContent = error.message; }
    });

    document.getElementById('agent-assess-form').addEventListener('submit', async event => {
        event.preventDefault();
        const id = Number(new FormData(event.currentTarget).get('invoice_id'));
        const result = document.getElementById('agent-assess-result');
        result.textContent = 'Assessing case...';
        try {
            const proposal = await (await apiFetch(`/api/v1/agent/cases/${id}/assess`,
                {method: 'POST'})).json();
            result.textContent = `Proposal ${proposal.id}: ${proposal.action}. Review it below.`;
            loadAgentProposals();
        } catch (error) { result.textContent = error.message; }
    });

    async function loadAgent() {
        const status = document.getElementById('agent-status');
        try {
            const data = await (await apiFetch('/api/v1/agent/status')).json();
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
        await loadAgentProposals();
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

