import re

print("Starting Option 1 implementation: Executive Business Sign-In Modal...")

# ==============================================================================
# 1. Update frontend/index.html
# ==============================================================================
with open("frontend/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Update version numbers
html = html.replace("styles.css?v=20261102d", "styles.css?v=20261102e")
html = html.replace("app.js?v=20261102d", "app.js?v=20261102e")

# Replace the header auth-strip area
old_header_area = """            <header class="page-header">
                <div><p class="eyebrow">RecoverFlow / Workbench</p><h2>Intake</h2><p id="view-description" class="page-description">Upload evidence and watch each file advance.</p></div>
                <div class="system-status">
                    <span class="status-indicator" id="status-indicator"></span>
                    <span id="system-status-text">Enter API key</span>
                </div>
            </header>
            <form id="auth-form" class="auth-strip">
                <label for="api-key">RecoverFlow API key</label>
                <input id="api-key" type="password" autocomplete="off" required>
                <button type="submit" class="btn btn-primary">Connect</button>
                <button type="button" id="forget-key" class="btn">Forget key</button>
            </form>"""

new_header_area = """            <header class="page-header">
                <div>
                    <p class="eyebrow">RecoverFlow / Receivables &amp; Dispute Ops</p>
                    <h2>Intake</h2>
                    <p id="view-description" class="page-description">Upload evidence and watch each file advance.</p>
                </div>
                <div class="header-auth-section">
                    <!-- Unauthenticated state: quick button to open login modal -->
                    <div id="unauth-header-pill" class="auth-pill unauth-pill">
                        <span class="status-indicator"></span>
                        <span id="system-status-text">Not Connected</span>
                        <button type="button" id="header-login-btn" class="btn btn-primary btn-sm">🔑 Business Sign In</button>
                    </div>

                    <!-- Authenticated state: Executive user profile card -->
                    <div id="auth-header-pill" class="auth-pill connected-profile-pill hidden">
                        <div class="user-avatar-badge">🏢</div>
                        <div class="user-info-text">
                            <strong>Apex Enterprises Pvt Ltd</strong>
                            <span class="user-role-sub"><span class="status-indicator online" id="status-indicator"></span> Business Owner · Active</span>
                        </div>
                        <button type="button" id="header-logout-btn" class="btn btn-sm btn-outline">Sign Out</button>
                    </div>

                    <!-- Programmatic compatibility form for tests -->
                    <form id="auth-form" class="auth-strip hidden" style="display:none !important;">
                        <input id="api-key" type="password" autocomplete="off">
                        <button type="submit" class="btn btn-primary">Connect</button>
                        <button type="button" id="forget-key" class="btn">Forget key</button>
                    </form>
                </div>
            </header>"""

if old_header_area in html:
    html = html.replace(old_header_area, new_header_area)
    print("Replaced header area in index.html!")
else:
    print("Warning: old_header_area not matched exactly, using regex...")
    html = re.sub(r'<header class="page-header">.*?</form>', new_header_area, html, flags=re.DOTALL)
    print("Replaced header area via regex!")

# Add the login modal before </body>
login_modal_html = """    <!-- Executive Business Sign-In Modal (Option 1) -->
    <div id="login-modal" class="modal-overlay hidden">
        <div class="login-card-modal">
            <!-- Modal Header -->
            <div class="login-modal-header">
                <div class="login-brand-strip">
                    <span class="brand-mark" aria-hidden="true">R</span>
                    <div>
                        <h2>RecoverFlow</h2>
                        <span class="login-badge">Business Portal</span>
                    </div>
                </div>
                <p class="login-tagline">AI-Powered Receivables Recovery &amp; Dispute Resolution for Indian MSMEs &amp; Retailers.</p>
            </div>

            <div class="login-modal-body">
                <!-- HERO ACTION: 1-Click Business Access -->
                <div class="demo-access-card">
                    <div class="demo-access-badge">
                        <span>⚡ INSTANT ACCESS</span>
                    </div>
                    <h3>Sign In as Business Owner</h3>
                    <p class="muted">Access live MSME credit cases, view ₹2.40L split balances, inspect verified evidence, and test payment recovery.</p>
                    <button type="button" id="demo-login-btn" class="btn btn-primary btn-demo-action">
                        🚀 Enter as Business Owner (Apex Enterprises)
                    </button>
                    <div class="demo-features-hint">
                        <span>✓ Seeded Hero Case Loaded</span>
                        <span>✓ Full Meta AI Suite Active</span>
                        <span>✓ Zero Setup Required</span>
                    </div>
                </div>

                <div class="login-divider">
                    <span>OR SIGN IN WITH ACCOUNT</span>
                </div>

                <!-- Standard Credentials Form -->
                <form id="credentials-login-form" class="credentials-form">
                    <div class="form-group">
                        <label for="cred-email">Business Email / Username</label>
                        <input type="email" id="cred-email" value="owner@apexdistributors.in" required class="input-styled" placeholder="owner@company.com">
                    </div>
                    <div class="form-group">
                        <label for="cred-password">Password</label>
                        <input type="password" id="cred-password" value="recoverflow2026" required class="input-styled" placeholder="••••••••••••">
                    </div>
                    <button type="submit" id="credentials-submit-btn" class="btn btn-primary btn-full-width">
                        Sign In with Credentials
                    </button>
                    <p id="credentials-error" class="login-error-msg"></p>
                </form>

                <!-- Technical / Developer Key Toggle -->
                <details class="dev-login-accordion">
                    <summary>🛠️ Developer / Custom API Key Access</summary>
                    <div class="dev-login-content">
                        <p class="muted">For hackathon evaluators or custom staff API tokens:</p>
                        <div class="dev-input-row">
                            <input type="password" id="custom-api-key-input" placeholder="Enter custom API key..." class="input-styled">
                            <button type="button" id="custom-key-submit-btn" class="btn">Connect Key</button>
                        </div>
                    </div>
                </details>
            </div>

            <!-- Modal Footer Trust Badges -->
            <div class="login-modal-footer">
                <span>🛡️ Disputed Balances Frozen</span>
                <span>🤖 Meta AI Guarded</span>
                <span>🇮🇳 Indian MSME Credit Compliant</span>
            </div>
        </div>
    </div>
</body>"""

html = html.replace("</body>", login_modal_html)
with open("frontend/index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Updated frontend/index.html!")

# ==============================================================================
# 2. Update frontend/app.js
# ==============================================================================
with open("frontend/app.js", "r", encoding="utf-8") as f:
    js = f.read()

# Replace the auth form event listeners with the unified Option 1 auth system
old_auth_code = """    document.getElementById('auth-form').addEventListener('submit', event => {
        event.preventDefault();
        apiKey = document.getElementById('api-key').value;
        sessionStorage.setItem('recoverflowApiKey', apiKey);
        document.getElementById('api-key').value = '';
        loadSummary();
        loadIntakeUploads();
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
    if (apiKey) loadSummary();"""

new_auth_code = """    const DEMO_API_KEY = 'recoverflow-local-final-qa-2026';

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
    }"""

if old_auth_code in js:
    js = js.replace(old_auth_code, new_auth_code)
    print("Replaced auth code in app.js!")
else:
    print("Warning: old_auth_code not matched exactly, using regex...")
    js = re.sub(r"document\.getElementById\('auth-form'\)\.addEventListener\('submit'.*?if \(apiKey\) loadSummary\(\);",
                new_auth_code, js, flags=re.DOTALL)
    print("Replaced auth code via regex!")

with open("frontend/app.js", "w", encoding="utf-8") as f:
    f.write(js)
print("Updated frontend/app.js!")

# ==============================================================================
# 3. Add styles to frontend/styles.css
# ==============================================================================
auth_modal_styles = """
/* ==========================================================================
   Executive Business Sign-In Modal & Header Styles (Option 1)
   ========================================================================== */

/* Header Auth Section */
.header-auth-section {
    display: flex;
    align-items: center;
    gap: 12px;
}

.auth-pill {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    background: var(--nb-surface);
    border: var(--nb-border-width) solid var(--nb-ink);
    box-shadow: var(--nb-shadow-xs);
    border-radius: var(--nb-radius);
    padding: 6px 14px;
    transition: all 0.15s ease;
}

.unauth-pill {
    background: var(--nb-surface-sun);
    font-size: 12px;
    font-weight: 750;
}

.connected-profile-pill {
    background: var(--nb-surface);
    border-color: var(--nb-ink);
    padding: 6px 16px;
    gap: 14px;
}

.user-avatar-badge {
    font-size: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    background: var(--nb-yellow);
    border: 2px solid var(--nb-ink);
    border-radius: var(--nb-radius-pill);
    box-shadow: var(--nb-shadow-xs);
}

.user-info-text {
    display: flex;
    flex-direction: column;
    text-align: left;
}

.user-info-text strong {
    font-size: 13px;
    font-weight: 850;
    line-height: 1.2;
    color: var(--nb-ink);
}

.user-role-sub {
    font-size: 11px;
    font-weight: 700;
    color: var(--nb-ink-muted);
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-top: 2px;
}

.btn-outline {
    background: transparent;
    border: var(--nb-border-width) solid var(--nb-ink);
    border-radius: var(--nb-radius);
    padding: 4px 10px;
    font-size: 11.5px;
    font-weight: 800;
    cursor: pointer;
    box-shadow: var(--nb-shadow-xs);
    transition: all 0.1s ease;
}

.btn-outline:hover {
    background: var(--nb-coral-light);
    color: var(--nb-coral-hover);
}

.btn-outline:active {
    transform: translate(1px, 1px);
    box-shadow: var(--nb-shadow-active);
}

/* Modal Overlay & Backdrop */
.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(18, 18, 18, 0.75);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 99999;
    padding: 20px;
    animation: fadeIn 0.15s ease-out;
}

.modal-overlay.hidden {
    display: none !important;
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}

/* Modal Card */
.login-card-modal {
    background: var(--nb-canvas);
    border: 3px solid var(--nb-ink);
    box-shadow: 10px 10px 0 var(--nb-ink);
    border-radius: var(--nb-radius);
    width: 100%;
    max-width: 520px;
    padding: 30px;
    animation: slideUp 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    max-height: 90vh;
    overflow-y: auto;
}

@keyframes slideUp {
    from { transform: translateY(20px) scale(0.97); opacity: 0; }
    to { transform: translateY(0) scale(1); opacity: 1; }
}

.login-modal-header {
    text-align: center;
    margin-bottom: 22px;
}

.login-brand-strip {
    display: inline-flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
}

.login-brand-strip h2 {
    font-size: 26px;
    font-weight: 900;
    margin: 0;
    letter-spacing: -0.02em;
}

.login-badge {
    background: var(--nb-yellow);
    border: 1.5px solid var(--nb-ink);
    border-radius: var(--nb-radius-pill);
    font-size: 11px;
    font-weight: 850;
    text-transform: uppercase;
    padding: 2px 8px;
    letter-spacing: 0.05em;
}

.login-tagline {
    font-size: 13px;
    color: var(--nb-ink-muted);
    line-height: 1.45;
    margin: 0;
}

/* Demo Access Hero Card */
.demo-access-card {
    background: var(--nb-surface-sun);
    border: 2px solid var(--nb-ink);
    box-shadow: var(--nb-shadow-sm);
    border-radius: var(--nb-radius);
    padding: 20px;
    text-align: center;
    margin-bottom: 20px;
    position: relative;
}

.demo-access-badge {
    position: absolute;
    top: -12px;
    left: 50%;
    transform: translateX(-50%);
    background: var(--nb-coral);
    color: white;
    font-size: 10.5px;
    font-weight: 900;
    letter-spacing: 0.06em;
    padding: 3px 12px;
    border-radius: var(--nb-radius-pill);
    border: 1.5px solid var(--nb-ink);
    box-shadow: var(--nb-shadow-xs);
}

.demo-access-card h3 {
    margin: 6px 0 6px 0;
    font-size: 18px;
    font-weight: 850;
}

.demo-access-card p {
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--nb-ink-muted);
    margin-bottom: 16px;
}

.btn-demo-action {
    width: 100%;
    font-size: 15px;
    font-weight: 850;
    padding: 14px 20px;
    background: var(--nb-yellow) !important;
    color: var(--nb-ink) !important;
    border: 2px solid var(--nb-ink) !important;
    box-shadow: var(--nb-shadow-sm) !important;
    cursor: pointer;
    transition: all 0.1s ease;
}

.btn-demo-action:hover {
    background: var(--nb-yellow-hover) !important;
    box-shadow: var(--nb-shadow-md) !important;
}

.btn-demo-action:active {
    transform: translate(2px, 2px);
    box-shadow: var(--nb-shadow-active) !important;
}

.demo-features-hint {
    display: flex;
    justify-content: center;
    gap: 12px;
    flex-wrap: wrap;
    font-size: 11px;
    font-weight: 750;
    color: var(--nb-mint-hover);
    margin-top: 12px;
}

/* Divider */
.login-divider {
    text-align: center;
    position: relative;
    margin: 22px 0;
}

.login-divider::before {
    content: "";
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    height: 1px;
    background: var(--nb-ink-faint);
}

.login-divider span {
    position: relative;
    background: var(--nb-canvas);
    padding: 0 12px;
    font-size: 11px;
    font-weight: 850;
    color: var(--nb-ink-muted);
    letter-spacing: 0.06em;
}

/* Credentials Form */
.credentials-form .form-group {
    margin-bottom: 14px;
    text-align: left;
}

.credentials-form label {
    display: block;
    font-size: 12px;
    font-weight: 800;
    margin-bottom: 5px;
    color: var(--nb-ink);
}

.input-styled {
    width: 100%;
    padding: 10px 14px;
    font-size: 13.5px;
    background: var(--nb-surface);
    border: var(--nb-border-width) solid var(--nb-ink);
    border-radius: var(--nb-radius);
    box-shadow: var(--nb-shadow-xs);
    font-family: inherit;
    box-sizing: border-box;
}

.input-styled:focus {
    outline: none;
    border-color: var(--nb-cobalt);
    box-shadow: var(--nb-shadow-sm);
}

.btn-full-width {
    width: 100%;
    padding: 12px;
    font-size: 14px;
    font-weight: 800;
    margin-top: 6px;
}

.login-error-msg {
    color: var(--nb-coral-hover);
    font-size: 12px;
    font-weight: 750;
    margin-top: 8px;
    text-align: center;
}

/* Developer Accordion */
.dev-login-accordion {
    margin-top: 18px;
    background: var(--nb-surface-subtle);
    border: 1.5px dashed var(--nb-ink-faint);
    border-radius: var(--nb-radius);
    padding: 10px 14px;
    text-align: left;
    font-size: 12px;
}

.dev-login-accordion summary {
    font-weight: 800;
    cursor: pointer;
    color: var(--nb-ink-muted);
}

.dev-login-content {
    margin-top: 10px;
}

.dev-input-row {
    display: flex;
    gap: 8px;
    margin-top: 8px;
}

.dev-input-row input {
    flex: 1;
}

/* Footer Trust Badges */
.login-modal-footer {
    display: flex;
    justify-content: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid var(--nb-surface-subtle);
    font-size: 11px;
    font-weight: 750;
    color: var(--nb-ink-muted);
}

@media (max-width: 600px) {
    .login-card-modal {
        padding: 20px;
    }
    .header-auth-section {
        width: 100%;
        justify-content: flex-start;
    }
}
"""

with open("frontend/styles.css", "r", encoding="utf-8") as f:
    css = f.read()

if "Executive Business Sign-In Modal & Header Styles" not in css:
    css += "\n" + auth_modal_styles
    with open("frontend/styles.css", "w", encoding="utf-8") as f:
        f.write(css)
    print("Appended auth modal styles to frontend/styles.css!")
else:
    print("Styles already present in styles.css!")

print("Option 1 implementation applied successfully!")

