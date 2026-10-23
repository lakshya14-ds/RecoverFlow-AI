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
            container.innerHTML = `<p class="mobile-hint">Swipe the table to see each case action →</p><table><tr><th>Invoice</th><th>Customer</th><th>Due</th><th>Balance</th><th>Status</th><th>Action</th></tr>${cases.map(item => `
                <tr><td>${escapeHtml(item.invoice_number)}</td><td>${escapeHtml(item.customer)}</td>
                <td>${escapeHtml(item.due_date)}</td><td>${escapeHtml(item.currency)} ${(item.balance_cents / 100).toFixed(2)}</td>
                <td>${escapeHtml(item.contact_suppressed ? 'Contact paused' : displayStatus(item.status))}</td>
                <td><button type="button" class="btn case-open" data-id="${Number(item.invoice_id)}">Open</button></td></tr>`).join('')}</table>`;
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
            document.getElementById('resume-form').classList.toggle('hidden', !data.contact_suppressed);
            document.getElementById('case-history').innerHTML = `<h4>Activity</h4><div class="stack">${[
                ...data.entries.map(item => `<div class="subcard">${escapeHtml(item.kind)}: ${escapeHtml(item.currency)} ${(Math.abs(item.amount_cents) / 100).toFixed(2)} • ${escapeHtml(item.reference)}${item.amount_cents < 0 ? ` <button type="button" class="btn reverse-entry" data-id="${Number(item.id)}">Reverse (admin)</button>` : ''}</div>`),
                ...data.messages.map(item => `<div class="subcard">${escapeHtml(item.category)}: ${escapeHtml(item.body)}</div>`),
                ...data.campaigns.map(item => `<div class="subcard">Collection draft ${escapeHtml(item.campaign_stage)}: ${escapeHtml(displayStatus(item.status))}</div>`)
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

            let html = `<table><tr><th>Invoice ID</th><th>AFIS ID</th><th>Confidence</th><th>Amount</th><th>Action</th></tr>`;
            data.forEach(item => {
                html += `<tr>
                    <td>${escapeHtml(item.invoice_id)}</td>
                    <td>${escapeHtml(item.afis_transaction_id)}</td>
                    <td>${(item.confidence_score * 100).toFixed(1)}%</td>
                    <td>$${item.matched_amount.toFixed(2)}</td>
                    <td><button class="btn btn-primary" onclick="approveRecon(${Number(item.id)})">Approve</button></td>
                </tr>`;
            });
            html += `</table>`;
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

            let html = `<table><tr><th>Invoice ID</th><th>Severity</th><th>Score</th><th>Description</th><th>Action</th></tr>`;
            data.forEach(item => {
                html += `<tr>
                    <td>${escapeHtml(item.invoice_id)}</td>
                    <td><span style="color:var(--color-error);font-weight:bold;">${escapeHtml(item.severity.toUpperCase())}</span></td>
                    <td>${(item.fraud_score * 100).toFixed(1)}%</td>
                    <td>${escapeHtml(item.description)}</td>
                    <td><button class="btn btn-primary" onclick="resolveFraud(${Number(item.id)})">Mark False Positive</button></td>
                </tr>`;
            });
            html += `</table>`;
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

            let html = `<table><tr><th>Invoice</th><th>Stage</th><th>Days Overdue</th><th>Status</th><th>Draft</th></tr>`;
            data.forEach(item => {
                html += `<tr>
                    <td>${escapeHtml(item.invoice_id)}</td>
                    <td>${escapeHtml(item.campaign_stage)}</td>
                    <td>${escapeHtml(item.days_overdue)}</td>
                    <td>${escapeHtml(displayStatus(item.status))}</td>
                    <td><details><summary>Review text</summary><strong>${escapeHtml(item.email_subject)}</strong><p class="prewrap">${escapeHtml(item.email_body)}</p>${item.status === 'draft' ? `<button type="button" class="btn btn-primary approve-campaign" data-id="${Number(item.id)}">Approve draft</button>` : ''} ${item.status === 'draft' || item.status === 'approved' ? `<button type="button" class="btn refresh-campaign" data-id="${Number(item.id)}">Refresh balance</button><form class="campaign-edit" data-id="${Number(item.id)}"><input name="subject" value="${escapeHtml(item.email_subject)}" aria-label="Email subject" required><textarea name="body" aria-label="Email body" required>${escapeHtml(item.email_body)}</textarea><button type="submit" class="btn">Save edits</button></form>` : ''}${item.status === 'approved' ? `<form class="manual-contact" data-id="${Number(item.id)}"><select name="channel"><option value="email">Email</option><option value="phone">Phone</option><option value="other">Other</option></select><input name="reference" placeholder="Contact reference" required minlength="3"><button type="submit" class="btn btn-primary">Record manual contact</button></form>` : ''}</details></td>
                </tr>`;
            });
            html += `</table>`;
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

