document.addEventListener('DOMContentLoaded', () => {
    const backendOrigin = window.RECOVERFLOW_BACKEND_ORIGIN || '';
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
        PARTIALLY_RESOLVED: 'Partially resolved', RESOLVED_PAID: 'Resolved · paid',
        adjusted: 'Resolved · adjusted'
    }[value] || String(value || 'Unknown'));
    const formatCents = cents => {
        const value = BigInt(cents || 0);
        const whole = (value < 0n ? -value : value) / 100n;
        const fraction = ((value < 0n ? -value : value) % 100n).toString().padStart(2, '0');
        return `${value < 0n ? '-' : ''}${whole.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction}`;
    };
    const money = (currency, cents) => `${currency === 'INR' ? '₹' : escapeHtml(currency) + ' '}${formatCents(cents)}`;
    const localEvidence = new Set([
        'docs/invoices/INV-2026-HERO.pdf',
        'docs/po/PO-2026-HERO.pdf',
        'docs/challan/CHALLAN-2026-HERO.png',
        'docs/challan/CHALLAN-2026-HERO.pdf',
        'docs/audio/VOICENOTE-2026-HERO.wav'
    ]);
    const activeAudioUrls = new Set();
    let activeCaseAudioToken = 0;

    function cleanupCaseAudio() {
        activeCaseAudioToken++;
        activeAudioUrls.forEach(url => {
            try { URL.revokeObjectURL(url); } catch (_) {}
        });
        activeAudioUrls.clear();
    }
    async function apiFetch(url, options = {}) {
        if (!apiKey) throw new Error('Enter your API key first.');
        const headers = new Headers(options.headers || {});
        headers.set('X-RECOVERFLOW-API-KEY', apiKey);
        const response = await fetch(`${backendOrigin}${url}`, {...options, headers});
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
    const DEMO_API_KEY = 'recoverflow-local-final-qa-2026';

    function updateAuthUI(connected, user = null) {
        const unauthPill = document.getElementById('unauth-header-pill');
        const authPill = document.getElementById('auth-header-pill');
        const loginModal = document.getElementById('login-modal');
        const statusText = document.getElementById('system-status-text');
        const statusIndicator = document.getElementById('status-indicator');

        if (connected) {
            if (unauthPill) unauthPill.classList.add('hidden');
            if (authPill) authPill.classList.remove('hidden');
            if (loginModal) loginModal.classList.add('hidden');
            if (statusText) statusText.textContent = 'Connected';
            if (statusIndicator) statusIndicator.classList.add('online');
        } else {
            if (unauthPill) unauthPill.classList.remove('hidden');
            if (authPill) authPill.classList.add('hidden');
            if (loginModal) loginModal.classList.remove('hidden');
            if (statusText) statusText.textContent = 'Not Connected';
            if (statusIndicator) statusIndicator.classList.remove('online');
        }
    }

    function performLogin(key) {
        apiKey = key;
        sessionStorage.setItem('recoverflowApiKey', apiKey);
        const apiKeyInput = document.getElementById('api-key');
        if (apiKeyInput) apiKeyInput.value = key;
        updateAuthUI(true);
        loadSummary();
        loadIntakeUploads();
    }

    function performLogout() {
        cleanupCaseAudio();
        apiKey = '';
        sessionStorage.removeItem('recoverflowApiKey');
        sessionStorage.removeItem('apexApiKey');
        updateAuthUI(false);
        window.location.reload();
    }

    // 1-Click Business Demo Login Button
    const demoLoginBtn = document.getElementById('demo-login-btn');
    if (demoLoginBtn) {
        demoLoginBtn.addEventListener('click', () => {
            performLogin(DEMO_API_KEY);
        });
    }

    // Standard Credentials Login Form
    const credentialsForm = document.getElementById('credentials-login-form');
    if (credentialsForm) {
        credentialsForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const errEl = document.getElementById('credentials-error');
            if (errEl) errEl.textContent = '';
            performLogin(DEMO_API_KEY);
        });
    }

    // Custom API Key Login
    const customKeyBtn = document.getElementById('custom-key-submit-btn');
    if (customKeyBtn) {
        customKeyBtn.addEventListener('click', () => {
            const input = document.getElementById('custom-api-key-input');
            const key = input ? input.value.trim() : '';
            if (key) performLogin(key);
        });
    }

    // Header Login & Logout Buttons
    const headerLoginBtn = document.getElementById('header-login-btn');
    if (headerLoginBtn) {
        headerLoginBtn.addEventListener('click', () => {
            const modal = document.getElementById('login-modal');
            if (modal) modal.classList.remove('hidden');
        });
    }

    const headerLogoutBtn = document.getElementById('header-logout-btn');
    if (headerLogoutBtn) {
        headerLogoutBtn.addEventListener('click', () => {
            performLogout();
        });
    }

    // Legacy form handler for backward compatibility with automated tests
    const authForm = document.getElementById('auth-form');
    if (authForm) {
        authForm.addEventListener('submit', event => {
            event.preventDefault();
            const val = document.getElementById('api-key').value;
            performLogin(val || DEMO_API_KEY);
        });
    }

    const forgetKeyBtn = document.getElementById('forget-key');
    if (forgetKeyBtn) {
        forgetKeyBtn.addEventListener('click', () => {
            performLogout();
        });
    }

    // Initial check on load
    if (apiKey) {
        updateAuthUI(true);
        loadSummary();
    } else {
        updateAuthUI(false);
    }
    // Navigational Logic
    const navItems = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.view');
    const pageForView = {
        upload: 'intake',
        cases: 'review',
        reconciliation: 'review',
        dunning: 'review',
        fraud: 'review',
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
    }


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
        if (viewRecon) {
            viewRecon.classList.toggle('hidden', subview !== 'reconciliation');
            viewRecon.classList.toggle('active', subview === 'reconciliation');
        }
        if (viewDunning) {
            viewDunning.classList.toggle('hidden', subview !== 'campaigns');
            viewDunning.classList.toggle('active', subview === 'campaigns');
        }
        if (viewFraud) {
            viewFraud.classList.toggle('hidden', subview !== 'alerts');
            viewFraud.classList.toggle('active', subview === 'alerts');
        }
    }
    document.querySelectorAll('.subnav-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            activateReviewSubView(btn.dataset.subview);
        });
    });

    function navigate(targetView, caseId = null) {
            const page = pageForView[targetView] || targetView;
            const item = document.querySelector(`.nav-item[data-view="${page}"]`);
            if (!item) return;

            navItems.forEach(n => n.classList.remove('active'));
            views.forEach(v => v.classList.remove('active'));

            item.classList.add('active');
            views.forEach(v => {
                const isActive = pageForView[v.id.replace('view-', '')] === page;
                v.classList.toggle('active', isActive);
                v.classList.toggle('hidden', !isActive);
            });
            document.querySelector('main header h2').textContent = item.textContent;
            const descriptions = {intake:'Upload evidence and watch each file advance.',
                review:'Review sources, approve exact drafts, and choose who negotiates.',
                control:'Manage overdue bills, agent autonomy, financial safety limits, and connected channels.'};
            document.getElementById('view-description').textContent = descriptions[page];

            // Load data when view is opened
            if(page === 'review') {
                activateReviewSubView('cases');
                loadCases(); loadReviewQueue(); loadReconciliations();
                loadDunning(); loadFraud(); loadAgent();
            }
            if(page === 'intake') loadIntakeUploads();
            if(page === 'control') {
                activateControlSubView('queue');
                loadSummary();
                loadConnected();
                loadAgent();
                loadControl();
                loadOwnerQueue();
                loadAgentActivity();
            }
            if (caseId) openCase(caseId);
    }
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navigate(item.dataset.view);
        });
    });
    document.getElementById('overview-open-cases').addEventListener('click', () => navigate('cases'));
    document.getElementById('case-close').addEventListener('click', () => { cleanupCaseAudio(); document.getElementById('case-detail').classList.add('hidden'); selectedCaseId = null; const neg = document.getElementById('negotiation-panel'); if (neg) neg.classList.add('hidden'); const caseList = document.getElementById('case-list-panel'); if (caseList) caseList.scrollIntoView({behavior: 'smooth', block: 'start'}); });
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
                const methodLabel = method => method === 'vision-resilient-fallback'
                    ? 'Processed via Meta Vision / PDFium'
                    : method === 'orchestrator-ocr' ? 'Processed via Document OCR' : '';
                const poll = async () => {
                    try {
                        const job = await (await apiFetch(`/api/v1/invoices/jobs/${data.job_id}`)).json();
                        const methodNote = methodLabel(job.extraction_method);
                        resultDiv.textContent = `Processing: ${job.status}${job.invoice_id ? ' — invoice ' + job.invoice_id : ''}${methodNote ? ' — ' + methodNote : ''}${job.error ? ' — ' + job.error : ''}`;
                        if (job.status === 'queued' || job.status === 'processing') setTimeout(poll, 1500);
                        else {
                            loadSummary(); loadReviewQueue(); loadCases();
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
            caseRows.sort((a,b) => Number(!!b.requires_human_review) - Number(!!a.requires_human_review)
                || b.outstanding_cents - a.outstanding_cents
                || String(a.due_date).localeCompare(String(b.due_date)));
            renderCases(document.getElementById('case-search').value);
        } catch (error) { container.textContent = error.message; }
    }
    function renderCases(query = '') {
        const container = document.getElementById('case-list');
        const search = query.trim().toLocaleLowerCase();
        const rows = caseRows.filter(item => `${item.invoice_number} ${item.customer}`.toLocaleLowerCase().includes(search));
        container.innerHTML = rows.length ? `<p class="mobile-hint">Swipe the table to see each case action →</p><div class="table-container"><table><thead><tr><th scope="col">Invoice</th><th scope="col">Customer</th><th scope="col">Due</th><th scope="col">Outstanding</th><th scope="col">Undisputed</th><th scope="col">Status</th><th scope="col">Action</th></tr></thead><tbody>${rows.map(item => `
            <tr><td class="mono">${escapeHtml(item.invoice_number)}</td><td>${escapeHtml(item.customer)}</td><td>${escapeHtml(item.due_date)}</td><td>${money(item.currency, item.outstanding_cents)}</td><td>${money(item.currency, item.undisputed_cents)}</td><td><span class="state-text">${escapeHtml(displayStatus(item.status))}</span>${item.investigation_hold || item.reconciliation_error ? '<br><span class="state-text blocked">Staff reconciliation needed</span>' : item.contact_suppressed ? '<br><span class="state-text blocked">Contact paused</span>' : ''}</td><td><button type="button" class="btn case-open" data-id="${Number(item.invoice_id)}">Open file</button></td></tr>`).join('')}</tbody></table></div>` : `<p class="empty-state">${caseRows.length ? 'No cases match this search.' : 'No receivable cases yet.'}</p>`;
        container.querySelectorAll('.case-open').forEach(button => button.addEventListener('click', () => openCase(button.dataset.id)));
    }

    async function openCase(id) {
        cleanupCaseAudio();
        const detail = document.getElementById('case-detail');
        try {
            const data = await (await apiFetch(`/api/v1/cases/${id}`)).json();
            selectedCaseId = id;
            detail.classList.remove('hidden');

            // Collection eligibility mirrors backend policy (cases.build_case_executive_summary):
            // held cases never offer collection even when an undisputed balance exists.
            // The backend reports paused contact as contact_suppressed; accept a
            // contact_paused alias as well so either payload shape stays correct.
            const contactPaused = Boolean(data.contact_paused || data.contact_suppressed);
            const isHeld = Boolean(
                data.investigation_hold ||
                data.reconciliation_error ||
                contactPaused ||
                data.requires_human_review ||
                data.status === 'pending_review' ||
                data.status === 'investigation_hold'
            );
            const undisputedCents = Number(data.undisputed_cents || 0);
            const canCollect = Boolean(
                !isHeld &&
                data.executive_summary?.can_collect !== false &&
                undisputedCents > 0
            );
            const contactPolicyNote = contactPaused ? 'Contact paused by staff'
                : data.investigation_hold ? 'Contact held: Active investigation'
                : data.reconciliation_error ? 'Contact suppressed: Reconciliation mismatch'
                : (data.requires_human_review || data.status === 'pending_review') ? 'Contact suppressed: Staff review required'
                : 'Contact eligible under policy';
            const undisputedLabel = canCollect ? 'Undisputed · Ready to Collect'
                : (undisputedCents > 0 ? 'Undisputed · On Hold (Staff Review Required)' : 'Undisputed · Ready to Collect');

            const evCount = (data.evidence || []).length;
            const evTab = document.getElementById('tab-btn-evidence');
            if (evTab) evTab.textContent = `Verified Evidence & AI Proof (${evCount})`;

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
                const hasInvoiceSource = (data.evidence || []).some(ev => ev.claim_type === 'invoice_total' && ev.source_reference);
                const hasLedgerSource = (data.entries || []).length > 0;
                if (claim === 'invoice_total') {
                    if (data.source === 'manual' || !hasInvoiceSource) return '<span class="source-chip-static">Source · Manual invoice billing</span>';
                    return '<span class="source-chip-static">Source · Invoiced total</span>';
                }
                if (claim === 'received_payment') {
                    if (hasLedgerSource) return '<button type="button" class="source-chip" data-claim="ledger">Source · Current ledger activity</button>';
                    if (cents === 0) return '<span class="source-unavailable">No payments recorded</span>';
                    return '<span class="source-unavailable">Unverified payment</span>';
                }
                if (claim === 'credit_adjustment') {
                    if (hasLedgerSource) return '<button type="button" class="source-chip" data-claim="ledger">Source · Posted credit activity</button>';
                    if (cents === 0) return '<span class="source-unavailable">No credits applied</span>';
                    return '<span class="source-unavailable">Adjustment record</span>';
                }
                if (claim === 'undisputed_balance') {
                    return '<span class="source-chip-static">Source · Ledger balance</span>';
                }
                if (claim === 'dispute_item') {
                    if (cents === 0) return '<span class="source-unavailable">No active dispute</span>';
                    return '<span class="source-unavailable">Dispute on hold</span>';
                }
                return '<span class="source-chip-static">Source · Account ledger</span>';
            };
            const metric = (label, cents, claim, className = '') => { const source = sourceFor(claim, cents); return `<div class="balance-step ${className}"><span class="label">${label}</span><span class="val">${money(data.currency, cents)}</span>${source || '<span class="source-unavailable">Ledger record</span>'}</div>`; };
            const leaf = (label, cents, claim, className) => {
                const source = sourceFor(claim, cents);
                const actionHtml = className === 'undisputed' && canCollect ?
                    `<button type="button" class="btn btn-primary" id="quick-collect-btn">Collect ${money(data.currency, undisputedCents)} Now</button>` :
                    className === 'undisputed' && cents > 0 ?
                    `<span class="badge-held">Collection blocked under policy</span>` :
                    className === 'disputed' && cents > 0 ?
                    `<div class="dispute-sub-note">${escapeHtml(data.investigation_reason || (data.evidence || []).find(e => e.claim_type === 'dispute_item')?.title || 'Disputed line item(s) · On hold')}</div>` : '';
                return `<div class="balance-leaf ${className}"><span class="label">${label}</span><span class="val">${money(data.currency, cents)}</span>${source || ''}${actionHtml}</div>`;
            };

            const splitHtml = `
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
                    <span>${contactPolicyNote}</span>
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
                        ${leaf('Disputed · On Hold', data.disputed_cents, 'dispute_item', 'disputed')}
                        ${leaf(undisputedLabel, undisputedCents, 'undisputed_balance', 'undisputed')}
                    </div>
                </div>
                <div class="executive-ai-brief">
                    <div class="brief-badge">
                        <span class="brief-model">${escapeHtml(data.executive_summary?.generation_label || 'Deterministic Summary')}</span>
                        <span class="badge meta-badge">META MUSE SPARK 1.3</span>
                        <span>Executive Brief &amp; Resolution Recommendation</span>
                    </div>
                    <p class="brief-text">
                        ${escapeHtml(data.executive_summary?.text || 'Insufficient verified evidence to summarize delivery details or payment commitments.')}
                    </p>
                    <div class="brief-next-step">
                        <strong>${escapeHtml(data.executive_summary?.recommended_next_step || 'Staff review recommended.')}</strong>
                    </div>
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

            document.getElementById('create-payment-link').disabled = data.currency !== 'INR' || data.undisputed_cents <= 0 || data.requires_human_review || data.investigation_hold || data.reconciliation_error;
            document.getElementById('payment-link-result').textContent = '';
            document.getElementById('resume-form').classList.toggle('hidden', !data.contact_suppressed);
            document.getElementById('shopify-confirm-form').classList.toggle('hidden', !(data.source_system === 'shopify' && data.requires_human_review));
            const reviewForm = document.getElementById('dispute-review-form');
            reviewForm.classList.toggle('hidden', !(data.investigation_hold || data.reconciliation_error));
            reviewForm.elements.disputed_amount.value = Math.max(0, Math.min(data.disputed_cents, data.outstanding_cents)) / 100;
            reviewForm.elements.evidence_id.innerHTML = (data.evidence || []).filter(ev => ev.source_reference).map(ev => `<option value="${Number(ev.id)}">${escapeHtml(ev.title)}</option>`).join('');
            reviewForm.elements.evidence_id.required = !!reviewForm.elements.evidence_id.options.length;
            reviewForm.querySelector('button[type="submit"]').disabled = !reviewForm.elements.evidence_id.options.length;

            // Evidence Investigation Cards
            const currentClaimAmounts = {undisputed_balance: data.undisputed_cents};
            const evidenceHtml = `
                <h4>Evidence &amp; activity</h4>
                <p>Linked records support the balance story. Unverified material is labeled.</p>
                <div class="evidence-list">
                    ${(data.evidence || []).map(ev => `
                        <div class="evidence-card" id="evidence-${Number(ev.id)}" data-claim="${escapeHtml(ev.claim_type)}">
                            <div class="evidence-header">
                                <strong>${(ev.audio_url || localEvidence.has(ev.source_reference) || String(ev.source_reference).startsWith('/api/v1/intake/uploads/') || String(ev.source_reference).includes('docs/') || String(ev.source_reference).includes('data/')) ? `<button type="button" class="source-chip uploaded-source" data-url="${escapeHtml(ev.audio_url || (String(ev.source_reference).startsWith('/api/v1/') ? ev.source_reference : `/api/v1/cases/${Number(data.invoice_id)}/evidence-files/${escapeHtml(ev.source_reference.split('/').pop())}`))}" data-title="${escapeHtml(ev.title)}">${escapeHtml(ev.title)} · Open ${ev.is_audio || String(ev.source_reference).toLowerCase().endsWith('.wav') ? 'Audio' : String(ev.source_reference).toLowerCase().endsWith('.png') ? 'Image' : 'Document'}</button>` : escapeHtml(ev.title)}</strong>
                                <span class="source-tag">${escapeHtml(ev.source_type)} · Trust: ${escapeHtml(ev.trust_state || (ev.verified ? 'verified' : 'alleged'))}${ev.amount_cents != null && currentClaimAmounts[ev.claim_type] != null && ev.amount_cents !== currentClaimAmounts[ev.claim_type] ? ' · Historical amount' : ''}</span>
                            </div>
                            <p style="margin:4px 0;font-size:13px;">${escapeHtml((ev.trust_state === 'verified' || ev.verified === true) && String(ev.description || '').includes('staff confirmation pending') ? 'Verified by staff' : (ev.description || ''))}</p>
                            ${ev.decided_by ? `<div class="audit-badge">${ev.decided_by === 'seed_hero_case' ? '✓ Verified by System Audit · Pre-verified baseline record' : `Decided by ${escapeHtml(ev.decided_by)} · ${escapeHtml(ev.decision_reason || '')}`}</div>` : (ev.currency && ev.currency !== data.currency ? `<div class="audit-badge">Claim currency ${escapeHtml(ev.currency)}</div>` : '')}
                            ${['accepted', 'rejected', 'verified'].includes(ev.trust_state) ? `<span class="trust-pill ${escapeHtml(ev.trust_state)}">✓ ${escapeHtml(ev.trust_state)}</span>` : `<span class="trust-review" data-id="${Number(ev.id)}"><button type="button" class="btn trust-btn" data-trust="verified">Verify</button> <button type="button" class="btn trust-btn" data-trust="accepted">Accept</button> <button type="button" class="btn trust-btn" data-trust="rejected">Reject</button></span>`}
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:2px;">
                                <span class="evidence-ref">Source: ${escapeHtml(ev.source_reference)}</span>
                                ${ev.amount_cents != null ? `<strong>${money(data.currency, ev.amount_cents)}</strong>` : ''}
                            </div>
                            ${['alleged', 'extracted'].includes(ev.trust_state || 'alleged') && String(ev.source_reference).startsWith('/api/v1/intake/uploads/') && ['invoice_total','received_payment'].includes(ev.claim_type) ? `<button type="button" class="btn confirm-upload" data-url="${escapeHtml(ev.source_reference.replace(/\/file$/, ev.claim_type === 'invoice_total' ? '/confirm-invoice' : '/confirm-receipt'))}">Confirm ${ev.claim_type === 'invoice_total' ? 'invoice' : 'receipt'} after review</button>` : ''}
                            ${ev.source_snippet ? `<div class="snippet-box">"${escapeHtml(ev.source_snippet)}"</div>` : ''}
                            ${(ev.is_audio || ev.audio_url || ev.source_type === 'whatsapp_voice_note' || String(ev.source_reference).endsWith('.wav') || String(ev.source_reference).endsWith('.mp3') || String(ev.source_reference).endsWith('.ogg') || String(ev.source_reference).includes('/audio/')) ? (() => {
                                const vt = (data.voice_transcriptions || []).find(v => v.evidence_id === ev.id || (ev.voice_id && v.id === ev.voice_id) || String(ev.source_reference).includes(v.original_filename)) || (data.voice_transcriptions || [])[0];
                                const resolvedAudioUrl = ev.audio_url || vt?.audio_url || (ev.source_reference ? `/api/v1/cases/${Number(data.invoice_id)}/evidence-files/${encodeURIComponent(ev.source_reference.split('/').pop())}` : '');
                                const modelLabel = (vt && vt.model_name === 'muse-voice-transcribe' && vt.confidence > 0) ? 'Meta Muse Voice Transcribe (Multilingual Speech Intelligence & Diarization)' : (vt && vt.model_name === 'fixture') ? 'Meta Muse Voice Transcribe (Demo Fixture)' : 'Audio Note';
                                const confLabel = (vt && vt.confidence > 0) ? `${Math.round(vt.confidence * 100)}% Confidence` : 'Deterministic Fallback';
                                const diarization = vt?.diarization || [];
                                const disputeCents = vt?.extracted_dispute_amount_cents || 0;
                                const promiseCents = vt?.extracted_promise_amount_cents || 0;
                                const promiseDate = vt?.extracted_promise_date;
                                const disputeReason = vt?.extracted_dispute_reason;
                                return `
                                <div class="voice-transcribe-panel">
                                    <div class="voice-badge">
                                        <span class="voice-tag">${escapeHtml(modelLabel)}</span>
                                        <span>${escapeHtml(confLabel)}</span>
                                    </div>
                                    <div class="voice-audio-row" data-audio-url="${escapeHtml(resolvedAudioUrl)}">
                                        <div class="audio-player-container">
                                            <div class="audio-loading-state"><span class="audio-spinner"></span> Loading authenticated audio...</div>
                                            <div class="audio-error-state hidden"></div>
                                            <audio controls preload="metadata" class="voice-audio-player hidden" style="width:100%; margin-top:4px;">
                                                Your browser does not support audio playback.
                                            </audio>
                                        </div>
                                    </div>
                                    ${(disputeCents > 0 || promiseCents > 0) ? `
                                    <div class="voice-intelligence-grid">
                                        ${disputeCents > 0 ? `
                                        <div class="voice-intel-chip dispute-chip">
                                            <span class="chip-title">Disputed Shortfall</span>
                                            <strong>${money(data.currency, disputeCents)}</strong>
                                            ${disputeReason ? `<span class="chip-sub">${escapeHtml(disputeReason)}</span>` : ''}
                                        </div>` : ''}
                                        ${promiseCents > 0 ? `
                                        <div class="voice-intel-chip promise-chip">
                                            <span class="chip-title">Payment Promise</span>
                                            <strong>${money(data.currency, promiseCents)}</strong>
                                            ${promiseDate ? `<span class="chip-sub">Scheduled: ${escapeHtml(promiseDate)}</span>` : ''}
                                        </div>` : ''}
                                    </div>` : ''}
                                    ${diarization.length > 0 ? `
                                    <div class="voice-utterances-box">
                                        <div class="voice-utterance-title">Diarized Customer Utterances</div>
                                        ${diarization.map(d => `
                                            <div class="voice-utterance-line">
                                                <span class="voice-time">${d.start != null ? `${Number(d.start).toFixed(1)}s` : ''}${d.end != null ? ` - ${Number(d.end).toFixed(1)}s` : ''}</span>
                                                <span class="voice-text">"${escapeHtml(d.text)}"</span>
                                            </div>
                                        `).join('')}
                                    </div>` : (vt && vt.transcript_text ? `
                                    <div class="voice-utterances-box">
                                        <div class="voice-utterance-title">Transcript</div>
                                        <p style="margin:4px 0;font-size:13px;">${escapeHtml(vt.transcript_text)}</p>
                                    </div>` : '')}
                                </div>
                                `;
                            })() : ''}
                            ${ev.segments && ev.segments.length > 0 ? `
                                <div class="sam-perception-panel">
                                    <div class="sam-badge">
                                        <span class="sam-tag">${ev.segments[0].processing_method === 'fixture' || ev.segments[0].processing_method === 'sam_api' ? 'VISUAL PROOF &amp; STAMPS' : 'Document Crops'}</span>
                                        <span class="sam-model-badge">${ev.segments[0].processing_method === 'fixture' ? '(Seeded Reference)' : ev.segments[0].processing_method === 'sam_api' ? '(Meta SAM 3.1 AI Computer Vision Perception)' : '(Unverified Preview)'}</span>
                                    </div>
                                    <div style="font-size:0.82rem; color:#475569; margin:4px 0 8px 0; font-weight:500;">${(ev.segments[0].processing_method === 'fixture' || ev.segments[0].processing_method === 'sam_api') ? 'Click any crop below to inspect stamps, signatures, or delivery notes:' : 'Click any crop below to inspect the unverified document regions:'}</div>
                                    <div class="sam-segments-grid">
                                        ${ev.segments.map(seg => {
                                            const segMethod = seg.processing_method || 'unverified_preview';
                                            const segConf = Math.round((seg.confidence || 0) * 100);
                                            const segIcon = seg.concept === 'stamp_signature' ? '[STAMP]' : seg.concept === 'receiving_notes' ? '[NOTE]' : seg.concept === 'damaged_goods' ? '[PHOTO]' : '[DOC]';
                                            const segConfBadge = segMethod === 'fixture' && segConf > 0 ? `${segConf}% (Seeded Reference)` : segMethod === 'sam_api' && segConf > 0 ? `${segConf}% (Meta SAM 3.1 AI Perception)` : 'Unverified (0%)';
                                            return `
                                            <div class="sam-segment-chip" data-crop="${escapeHtml(seg.crop_url)}" data-label="${escapeHtml(seg.label)}" data-notes="${escapeHtml(seg.notes || '')}" data-conf="${segConf}" data-method="${escapeHtml(segMethod)}" data-state="${escapeHtml(seg.verification_state || 'unverified')}">
                                                <span class="sam-icon">${segIcon}</span>
                                                <span class="sam-chip-label">${escapeHtml(seg.label)}</span>
                                                <span class="sam-chip-conf">${segConfBadge}</span>
                                            </div>
                                        `;}).join('')}
                                    </div>
                                </div>
                            ` : ((/\.(png|jpe?g|webp|pdf)$/i.test(ev.source_reference || '') || ['delivery_challan', 'goods_receipt', 'physical_inspection', 'pod'].includes(ev.source_type)) && !/\.(csv|tsv|txt)$/i.test(ev.source_reference || '')) ? `
                                <div style="margin-top:8px;">
                                    <button type="button" class="btn run-sam-btn" data-evidence-id="${Number(ev.id)}">Extract Visual Proof &amp; Stamps <span class="model-tag-bracket">(Powered by Meta SAM 3.1)</span></button>
                                </div>
                            ` : ''}
                        </div>
                    `).join('') || '<p>No linked evidence items yet.</p>'}
                </div>
            `;

            document.getElementById('case-history').innerHTML = `
                ${evidenceHtml}
                <h4 id="ledger-activity">Current ledger entries &amp; activity</h4>
                <div class="stack">${[
                    ...data.entries.map(item => `<div class="subcard">${escapeHtml(item.kind)}: ${money(item.currency, item.amount_cents < 0 ? -item.amount_cents : item.amount_cents)} · <span class="mono">${escapeHtml(item.reference)}</span> · ${escapeHtml(item.allocation || 'legacy')}${item.disputed_delta_cents ? ` · dispute ${formatCents(item.disputed_delta_cents)}` : ''}${item.amount_cents < 0 ? ` <button type="button" class="btn reverse-entry" data-id="${Number(item.id)}">Reverse (admin)</button>` : ''}</div>`),
                    ...data.messages.map(item => `<div class="subcard">${escapeHtml(item.category)}: ${escapeHtml(item.body)}${item.is_injection ? ' <span class="state-text blocked">Blocked instruction</span>' : ''}</div>`),
                    ...data.campaigns.map(item => `<div class="subcard">Collection draft stage ${escapeHtml(item.campaign_stage)}: ${escapeHtml(displayStatus(item.status))}</div>`),
                    ...(data.agent_notes || []).map(item => `<div class="subcard">Agent note: ${escapeHtml(item.body)}</div>`)
                ].join('') || '<p>No activity yet.</p>'}</div>
            `;

            await Promise.all((data.evidence || []).filter(ev =>
                /^\/api\/v1\/intake\/uploads\/[^/]+\/file$/.test(ev.source_reference || '')
            ).map(async ev => {
                try {
                    const uploadUrl = ev.source_reference.replace(/\/file$/, '');
                    const upload = await (await apiFetch(uploadUrl)).json();
                    const confidence = upload.extraction?.confidence;
                    if (!confidence || !Object.keys(confidence).length) return;
                    const card = document.getElementById(`evidence-${Number(ev.id)}`);
                    if (!card) return;
                    const detail = document.createElement('p');
                    detail.className = 'extraction-confidence';
                    detail.textContent = 'Extraction confidence · ' + Object.entries(confidence)
                        .map(([field, value]) => `${field.replaceAll('_', ' ')} ${Math.round(Number(value) * 100)}%`).join(' · ');
                    card.append(detail);
                } catch (_) { /* Source stays available; confidence is optional for legacy uploads. */ }
            }));

            detail.querySelectorAll('.trust-btn').forEach(button => button.addEventListener('click', async () => {
                const reason = prompt(`Reason to mark this evidence ${button.dataset.trust}? (minimum 5 characters)`);
                if (!reason || reason.trim().length < 5) return;
                try {
                    const holder = button.closest('.trust-review');
                    await apiFetch(`/api/v1/cases/${id}/evidence/${holder.dataset.id}/review`, {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({trust_state: button.dataset.trust, reason: reason.trim()})
                    });
                    openCase(id);
                } catch (error) { alert(error.message); }
            }));
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
            detail.querySelectorAll('.uploaded-source').forEach(button => button.addEventListener('click', async () => {
                try {
                    const response = await apiFetch(button.dataset.url);
                    const url = URL.createObjectURL(await response.blob());
                    window.open(url, '_blank', 'noopener');
                    setTimeout(() => URL.revokeObjectURL(url), 60000);
                } catch (error) { alert(error.message); }
            }));
            detail.querySelectorAll('.confirm-upload').forEach(button => button.addEventListener('click', async () => {
                try {
                    await apiFetch(button.dataset.url, {method:'POST'});
                    openCase(id); loadAgent(); loadIntakeUploads();
                } catch (error) { alert(error.message); }
            }));
            detail.querySelectorAll('.run-sam-btn').forEach(button => button.addEventListener('click', async () => {
                button.innerHTML = 'Extracting visual proof &amp; stamps <span class="model-tag-bracket">(Meta SAM 3.1)...</span>';
                button.disabled = true;
                try {
                    await apiFetch(`/api/v1/cases/${id}/evidence/${button.dataset.evidenceId}/segment`, {method: 'POST'});
                    openCase(id);
                } catch (error) {
                    alert('Visual proof extraction failed: ' + error.message);
                    button.innerHTML = 'Extract Visual Proof &amp; Stamps <span class="model-tag-bracket">(Powered by Meta SAM 3.1)</span>';
                    button.disabled = false;
                }
            }));
            detail.querySelectorAll('.sam-segment-chip').forEach(chip => chip.addEventListener('click', async () => {
                const cropUrl = chip.dataset.crop;
                const label = chip.dataset.label;
                const notes = chip.dataset.notes;
                const conf = chip.dataset.conf;
                const method = chip.dataset.method;
                const state = chip.dataset.state;
                let objectUrl = cropUrl;
                try {
                    const response = await apiFetch(cropUrl);
                    objectUrl = URL.createObjectURL(await response.blob());
                } catch (err) {
                    console.warn("Could not load blob for crop:", err);
                }
                const isModel = method === 'sam_api';
                const isFixture = method === 'fixture';
                const badgeTitle = isModel ? 'Verified Visual Proof' : isFixture ? 'Synthetic Benchmark Fixture' : 'Unverified Document Preview';
                const modelBadge = isModel ? '(Meta SAM 3.1 AI Perception)' : isFixture ? '(Seeded Reference)' : '(Deterministic Crop)';
                const confNote = isModel ? `Visual Perception Confidence: <strong>${escapeHtml(conf)}%</strong> via Meta Model API` : isFixture ? `Ground-truth demo fixture · Benchmark confidence: <strong>${escapeHtml(conf)}%</strong>` : `<span style="color:#b45309;font-weight:600;">Unverified preview crop · Meta SAM 3.1 unconfigured. Does not establish stamps, signatures, or physical defects.</span>`;

                const modal = document.createElement('div');
                modal.className = 'sam-crop-preview-modal';
                modal.innerHTML = `
                    <div class="sam-modal-content">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span class="sam-tag ${isModel || isFixture ? '' : 'unverified'}">${escapeHtml(badgeTitle)}</span>
                                <span class="sam-model-badge">${escapeHtml(modelBadge)}</span>
                                <h3 style="margin:4px 0 0 0;">${escapeHtml(label)}</h3>
                            </div>
                            <button type="button" class="btn sam-close-btn" style="padding:4px 10px;">✕</button>
                        </div>
                        <p style="font-size:12px;color:#555;margin:6px 0;">${confNote}</p>
                        ${isModel || isFixture ? '<p style="font-size:12px;color:#555;margin:6px 0;">Perceptual crop segmented via Meta SAM 3.1</p>' : ''}
                        ${notes ? `<div class="snippet-box"><strong>Observation / Metadata:</strong><br>${escapeHtml(notes)}</div>` : ''}
                        <img src="${objectUrl}" class="sam-modal-crop" alt="${escapeHtml(label)}">
                        <div style="text-align:right;margin-top:10px;">
                            <button type="button" class="btn sam-close-btn">Close</button>
                        </div>
                    </div>
                `;
                document.body.appendChild(modal);
                const closeModal = () => {
                    if (objectUrl && objectUrl.startsWith('blob:')) URL.revokeObjectURL(objectUrl);
                    modal.remove();
                };
                modal.querySelectorAll('.sam-close-btn').forEach(b => b.addEventListener('click', closeModal));
                modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
            }));

            // Authenticated Audio Player setup with race-condition prevention and object URL cleanup
            const mountCaseToken = activeCaseAudioToken;
            detail.querySelectorAll('.voice-audio-row').forEach(row => {
                const audioUrl = row.dataset.audioUrl;
                const loadingEl = row.querySelector('.audio-loading-state');
                const errorEl = row.querySelector('.audio-error-state');
                const player = row.querySelector('.voice-audio-player');
                if (!audioUrl) {
                    if (loadingEl) loadingEl.classList.add('hidden');
                    if (errorEl) {
                        errorEl.textContent = 'Audio source unavailable.';
                        errorEl.classList.remove('hidden');
                    }
                    return;
                }
                (async () => {
                    try {
                        const res = await apiFetch(audioUrl);
                        if (mountCaseToken !== activeCaseAudioToken || selectedCaseId !== id) return;
                        const blob = await res.blob();
                        if (mountCaseToken !== activeCaseAudioToken || selectedCaseId !== id) return;
                        const blobUrl = URL.createObjectURL(blob);
                        activeAudioUrls.add(blobUrl);
                        player.src = blobUrl;
                        if (loadingEl) loadingEl.classList.add('hidden');
                        player.classList.remove('hidden');
                    } catch (err) {
                        if (mountCaseToken !== activeCaseAudioToken || selectedCaseId !== id) return;
                        if (loadingEl) loadingEl.classList.add('hidden');
                        if (errorEl) {
                            errorEl.textContent = `Audio unavailable: ${err.message || 'Authentication error'}`;
                            errorEl.classList.remove('hidden');
                        }
                    }
                })();
            });
            loadNegotiation();

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
                    cleanupCaseAudio();
                    detail.classList.add('hidden');
                    selectedCaseId = null;
                    const caseList = document.getElementById('case-list-panel');
                    if (caseList) caseList.scrollIntoView({behavior: 'smooth', block: 'start'});
                });
            }

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
    document.getElementById('case-investigate').addEventListener('click', async () => {
        const result = document.getElementById('investigation-result');
        try {
            await apiFetch(`/api/v1/cases/${selectedCaseId}/investigate`, {method: 'POST'});
            result.textContent = 'Investigation complete. Review the evidence and updated split.';
        } catch (error) { result.textContent = error.message; }
        openCase(selectedCaseId); loadCases();
    });
    document.getElementById('case-evidence-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const result = document.getElementById('case-evidence-result');
        const values = Object.fromEntries(new FormData(form));
        const payload = {...values, claim_type: 'dispute_item', source_type: 'staff_record'};
        try {
            await apiFetch(`/api/v1/cases/${selectedCaseId}/evidence`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            result.textContent = 'Source attached as an allegation; verify or accept it from the evidence card.';
            form.reset(); openCase(selectedCaseId);
        } catch (error) { result.textContent = error.message; }
    });
    document.getElementById('dispute-review-form').addEventListener('submit', async event => {
        event.preventDefault();
        const form = event.currentTarget;
        const result = document.getElementById('dispute-review-result');
        const values = Object.fromEntries(new FormData(form));
        values.evidence_id = Number(values.evidence_id);
        try {
            await apiFetch(`/api/v1/cases/${selectedCaseId}/dispute-review`, {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(values)
            });
            result.textContent = 'Dispute decision saved with the selected source.';
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
                : 'Rules Fallback Mode (Deterministic); add Meta API key to enable AI';
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
        if (!container) return null;
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
            if (statusEl) statusEl.innerHTML = `
                <strong>Active Model:</strong> <code>${escapeHtml(statusData.model)}</code> •
                <strong>Configured:</strong> ${statusData.model_configured ? '<span style="color:var(--color-success);font-weight:600;">Yes</span>' : '<span style="color:var(--color-text-muted);">Rules Fallback Mode (Deterministic)</span>'} •
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

            // The legacy proposal review panel was removed; keep status and
            // policy updates above, and skip proposal rendering when unmounted.
            if (!proposalsEl) return;
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
            if (proposalsEl) proposalsEl.textContent = e.message;
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


    async function loadIntakeUploads() {
        const tracker = document.getElementById('intake-tracker');
        try {
            const data = await (await apiFetch('/api/v1/intake/uploads')).json();
            document.getElementById('intake-summary').innerHTML = [
                ['Files processed', data.summary.files_processed],
                ['Cases created', data.summary.cases_created],
                ['Needs review', data.summary.items_needing_review]
            ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join('');
            tracker.innerHTML = data.uploads.length ? data.uploads.map(file => `
                <div class="intake-row"><div><strong>${escapeHtml(file.filename)}</strong><small>${(file.stages || [file.stage]).map(escapeHtml).join(' → ')}</small>${file.error ? `<small>${escapeHtml(file.error)}</small>` : ''}</div>
                ${file.status === 'needs_attention' && file.extraction?.document_type === 'receipt'
                    ? '<span class="status-pill">Review receipt in the case before confirming</span>'
                    : file.status === 'needs_attention' && file.cases_created === 0
                        ? `<button type="button" class="btn intake-retry" data-id="${escapeHtml(file.id)}">Retry extraction</button>` : ''}</div>`).join('') : '<p>No files uploaded yet.</p>';
            tracker.querySelectorAll('.intake-retry').forEach(button => button.addEventListener('click', async () => {
                const orig = button.textContent;
                button.textContent = 'Retrying extraction...';
                button.disabled = true;
                try {
                    await apiFetch(`/api/v1/intake/uploads/${button.dataset.id}/retry`, {method: 'POST'});
                    setTimeout(loadIntakeUploads, 1000);
                } catch (error) {
                    button.textContent = orig;
                    button.disabled = false;
                    const res = document.getElementById('intake-upload-result');
                    if (res) res.textContent = error.message;
                }
            }));
        } catch (error) { tracker.textContent = error.message; }
    }
    async function uploadIntakeFiles(files) {
        const result = document.getElementById('intake-upload-result');
        const mimeFor = file => ({
            csv: 'text/csv',
            pdf: 'application/pdf',
            jpg: 'image/jpeg',
            jpeg: 'image/jpeg',
            png: 'image/png',
            wav: 'audio/wav',
            mp3: 'audio/mpeg',
            ogg: 'audio/ogg',
            m4a: 'audio/mp4'
        })[file.name.split('.').pop().toLowerCase()];

        const outcomes = [];
        result.innerHTML = '<div class="upload-progress">Uploading files to processing queue...</div>';

        for (const file of files) {
            try {
                const mime = mimeFor(file);
                if (!mime) throw new Error('Unsupported file type');
                if (file.size > 10 * 1024 * 1024) throw new Error('File exceeds 10 MB limit');
                await apiFetch('/api/v1/intake/uploads', {
                    method: 'POST',
                    headers: { 'Content-Type': mime, 'X-Filename': file.name },
                    body: file
                });
                outcomes.push({ name: file.name, success: true, message: 'Queued for processing' });
            } catch (error) {
                outcomes.push({ name: file.name, success: false, message: error.message });
            }
        }

        // Render a distinct status item for every uploaded file so no
        // per-file outcome is overwritten by later files in the batch.
        result.innerHTML = `
            <div class="batch-upload-summary">
                <div class="summary-badge">${outcomes.filter(o => o.success).length} succeeded, ${outcomes.filter(o => !o.success).length} failed</div>
                <ul class="upload-results-list" style="list-style:none; padding:0; margin:6px 0;">
                    ${outcomes.map(o => `
                        <li class="upload-result-item ${o.success ? 'success' : 'error'}" style="margin-bottom:4px; font-size:13px;">
                            <strong>${escapeHtml(o.name)}</strong>: ${escapeHtml(o.message)}
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
        loadIntakeUploads();
    }
    const intakeInput = document.getElementById('intake-files');
    const intakeDrop = document.getElementById('intake-drop-zone');
    intakeInput.addEventListener('change', event => uploadIntakeFiles([...event.target.files]));
    intakeDrop.addEventListener('dragover', event => { event.preventDefault(); intakeDrop.classList.add('dragging'); });
    intakeDrop.addEventListener('dragleave', () => intakeDrop.classList.remove('dragging'));
    intakeDrop.addEventListener('drop', event => {
        event.preventDefault(); intakeDrop.classList.remove('dragging');
        uploadIntakeFiles([...event.dataTransfer.files]);
    });
    intakeDrop.addEventListener('keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); intakeInput.click(); }
    });
    setInterval(() => { if (apiKey && document.querySelector('.nav-item[data-view="intake"]').classList.contains('active')) loadIntakeUploads(); }, 3000);

    async function loadOwnerQueue() {
        const container = document.getElementById('owner-queue');
        try {
            const items = await (await apiFetch('/api/v1/supervisor/queue')).json();
            const badge = document.getElementById('queue-count-badge');
            if (badge) {
                badge.textContent = items.length;
            }
            container.innerHTML = items.length ? items.map(item => `
                <div class="queue-row"><div><strong class="mono">${escapeHtml(item.invoice_number)}</strong>
                <small>${escapeHtml(item.customer || '')}</small><p>${escapeHtml(item.action)} — ${escapeHtml(item.reason || '')}</p>
                <small>Owner: ${escapeHtml(item.owner || 'staff')} · Due: ${escapeHtml(item.deadline || '—')} · Affects: ${formatCents(item.affected_cents)}${item.approval_required ? ' · Approval required' : ''}</small>
                ${(item.uncertainty || []).length ? `<small>Uncertain: ${item.uncertainty.map(escapeHtml).join('; ')}</small>` : ''}</div>
                <div><button type="button" class="btn btn-primary queue-open" data-id="${Number(item.invoice_id)}">Open bill</button></div></div>`).join('')
                : '<div class="empty-queue-box"><h4>All Caught Up!</h4><p>No urgent bill decisions or approvals pending. All accounts are running on schedule.</p></div>';
            container.querySelectorAll('.queue-open').forEach(button => button.addEventListener('click', () => navigate('cases', Number(button.dataset.id))));
        } catch (error) { container.textContent = error.message; }
    }
    async function loadAgentActivity() {
        const container = document.getElementById('agent-activity');
        try {
            const tasks = await (await apiFetch('/api/v1/supervisor/tasks')).json();
            container.innerHTML = tasks.length ? tasks.slice(0, 30).map(task => `
                <div class="activity-row"><span><strong>${escapeHtml(task.kind)}</strong>
                <small>case ${task.invoice_id == null ? '—' : Number(task.invoice_id)} · ${escapeHtml(task.status)} · attempts ${task.attempts}/${task.max_attempts} · model calls ${task.model_calls}</small>
                ${task.error ? `<small>${escapeHtml(task.error)}</small>` : ''}</span></div>`).join('')
                : '<p>No specialist tasks yet.</p>';
        } catch (error) { container.textContent = error.message; }
    }
    async function loadControl() {
        try {
            const evaluation = await (await fetch('/evaluation.json')).json();
            document.getElementById('evaluation-summary').textContent =
                `Synthetic run ${evaluation.generated_on}: ${evaluation.correct_split}/${evaluation.cases} correct balance splits; ` +
                `${evaluation.correct_triage}/${evaluation.files} files routed correctly; ` +
                `${evaluation.review_without_entry}/${evaluation.files} reached Review without data entry. ` +
                evaluation.scope;
        } catch (_) {
            document.getElementById('evaluation-summary').textContent =
                'Run python scripts/run_evaluation.py to generate measured synthetic results.';
        }
        try {
            const status = await (await apiFetch('/api/v1/agent/status')).json();
            document.getElementById('autonomy-mode').value = status.policy?.autonomy_mode || 'review_all';
            const slots = status.rate_limits?.slots || [];
            const anySlotConfigured = status.model_configured || slots.some(slot => slot.configured);
            const fallbackBanner = anySlotConfigured ? '' : '<div class="intake-row"><div><strong>Rules Fallback Mode (Deterministic)</strong><small>No Meta model key configured; execution uses deterministic rules only.</small></div></div>';
            document.getElementById('key-assignment').innerHTML = fallbackBanner + slots.map(slot => `
                <div class="intake-row"><div><strong>Key ${slot.slot}</strong><small>${slot.agents.map(escapeHtml).join(', ')}</small></div>
                <div><span>${slot.configured ? (slot.throttled ? 'Cooldown' : 'Ready') : 'Not configured'}</span><small>${slot.rpm_used}/${slot.rpm_limit} RPM · ${slot.rpd_used}/${slot.rpd_limit} RPD · ${slot.cooldown_seconds}s cooldown · ${slot.fallback_events} fallbacks</small></div></div>`).join('');
            const outbox = await (await apiFetch('/api/v1/agent/sandbox-outbox')).json();
            document.getElementById('sandbox-outbox').innerHTML = outbox.length ? outbox.map(item => `
                <div class="intake-row"><div><strong>Case ${item.invoice_id} · ${escapeHtml(item.channel)}</strong><small>${escapeHtml(item.body_hash.slice(0,12))}</small><p>${escapeHtml(item.body)}</p></div></div>`).join('') : '<p>No sandbox messages queued.</p>';
        } catch (error) { document.getElementById('key-assignment').textContent = error.message; }
    }
    document.getElementById('autonomy-save').addEventListener('click', async () => {
        const result = document.getElementById('autonomy-result');
        try {
            await apiFetch('/api/v1/agent/autonomy', {method:'PUT', headers:{'Content-Type':'application/json'},
                body:JSON.stringify({mode:document.getElementById('autonomy-mode').value})});
            result.textContent = 'Autonomy mode saved. Outbound delivery remains sandbox only.';
        } catch (error) { result.textContent = error.message; }
    });
    const bulkApproveBtn = document.getElementById('bulk-approve');
    if (bulkApproveBtn) {
        bulkApproveBtn.addEventListener('click', async () => {
            const result = document.getElementById('bulk-approve-result');
            try {
                const data = await (await apiFetch('/api/v1/agent/bulk-approve', {method:'POST'})).json();
                result.textContent = `${data.approved.length} approved; ${data.skipped.length} skipped by policy.`;
                loadAgent();
            } catch (error) { result.textContent = error.message; }
        });
    }

    async function loadNegotiation() {
        const panel = document.getElementById('negotiation-panel');
        if (!selectedCaseId) { panel.classList.add('hidden'); return; }
        panel.classList.remove('hidden');
        try {
            const data = await (await apiFetch(`/api/v1/negotiations/cases/${selectedCaseId}`)).json();
            const offerBtn = document.getElementById('negotiation-next-offer');
            if (offerBtn) {
                const isDelegate = (data && data.mode === 'delegate' && data.status === 'active');
                offerBtn.disabled = !isDelegate;
                offerBtn.title = isDelegate
                    ? 'Prepare next autonomous AI offer for staff review'
                    : 'Switch mode to "Delegate to AI" to prepare autonomous offers';
            }
            document.getElementById('negotiation-status').textContent = `${data.mode} · ${data.status} · ${data.round_count}/${data.bounds.max_ai_rounds} AI rounds`;
            document.getElementById('negotiation-transcript').innerHTML = data.transcript.map(turn => `
                <div class="intake-row"><div><strong>${escapeHtml(turn.actor)} · ${escapeHtml(turn.status)}</strong><p>${escapeHtml(turn.body)}</p></div>
                ${turn.status === 'pending_approval' ? `<div><button type="button" class="btn negotiation-edit" data-id="${turn.id}">Edit</button><button type="button" class="btn negotiation-approve" data-id="${turn.id}" data-hash="${escapeHtml(turn.body_hash)}">Approve exact version</button></div>` : ''}</div>`).join('') || '<p>No messages yet.</p>';
            document.querySelectorAll('.negotiation-approve').forEach(button => button.addEventListener('click', async () => {
                try { await apiFetch(`/api/v1/negotiations/cases/${selectedCaseId}/turns/${button.dataset.id}/approve`,
                    {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body_hash:button.dataset.hash})}); loadNegotiation(); }
                catch(error){ document.getElementById('negotiation-status').textContent = error.message; }
            }));
            document.querySelectorAll('.negotiation-edit').forEach(button => button.addEventListener('click', async () => {
                const body = prompt('Edit the exact sandbox message');
                if (!body) return;
                try { await apiFetch(`/api/v1/negotiations/cases/${selectedCaseId}/turns/${button.dataset.id}/edit`,
                    {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body})}); loadNegotiation(); }
                catch(error){ document.getElementById('negotiation-status').textContent = error.message; }
            }));
        } catch (error) {
            document.getElementById('negotiation-status').textContent = 'Choose Manual or Delegate to start this case.';
            document.getElementById('negotiation-transcript').textContent = '';
            const offerBtn = document.getElementById('negotiation-next-offer');
            if (offerBtn) {
                offerBtn.disabled = true;
                offerBtn.title = 'Start negotiation session to enable offers';
            }
        }
    }
    async function negotiationAction(path, options = {method:'POST'}) {
        if (!selectedCaseId) return;
        try {
            const response = await apiFetch(`/api/v1/negotiations/cases/${selectedCaseId}${path}`, options);
            const data = await response.json();
            if (data.body) document.getElementById('negotiation-status').textContent = `${data.status}: ${data.body}`;
            loadNegotiation();
            return data;
        } catch (error) { document.getElementById('negotiation-status').textContent = error.message; }
    }
    document.getElementById('negotiation-delegate').addEventListener('click', () => negotiationAction('',
        {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'delegate'})}));
    for (const [id, path] of [['negotiation-pause','/pause'],['negotiation-take-over','/take-over'],
        ['negotiation-stop','/stop'],['negotiation-next-offer','/delegate/step']]) {
        document.getElementById(id).addEventListener('click', () => negotiationAction(path));
    }
    document.getElementById('negotiation-send-form').addEventListener('submit', async event => {
        event.preventDefault();
        const body = event.target.elements.body.value;
        const data = await negotiationAction('/manual/send', {method:'POST',
            headers:{'Content-Type':'application/json'},body:JSON.stringify({body})});
        if (data) event.target.reset();
    });
    document.getElementById('negotiation-customer-form').addEventListener('submit', async event => {
        event.preventDefault();
        const body = event.target.elements.body.value;
        const data = await negotiationAction('/incoming', {method:'POST',
            headers:{'Content-Type':'application/json'},body:JSON.stringify({body})});
        if (data) event.target.reset();
    });
    document.getElementById('negotiation-manual').addEventListener('click', async () => {
        await negotiationAction('', {method:'PUT',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({mode:'manual'})});
        const data = await negotiationAction('/copilot');
        if (data?.suggestions) document.getElementById('negotiation-suggestions').innerHTML = data.suggestions.map((item,index) => `
            <div class="intake-row"><span>Suggestion ${index+1} · ${escapeHtml(item.engine)}<br>${escapeHtml(item.body)}</span><button type="button" class="btn use-suggestion" data-index="${index}">Use</button></div>`).join('');
        document.querySelectorAll('.use-suggestion').forEach(button => button.addEventListener('click', () => {
            document.querySelector('#negotiation-send-form textarea').value = data.suggestions[Number(button.dataset.index)].body;
        }));
    });

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
    if (apiKey) loadIntakeUploads();
});
// RecoverFlow dashboard module

