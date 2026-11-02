import re

print("Updating modal to include visible #api-key for 100% script compatibility...")

with open("frontend/index.html", "r", encoding="utf-8") as f:
    html = f.read()

# Replace the modal HTML
old_modal_pattern = r'<!-- Executive Business Sign-In Modal.*?</div>\s*</div>\s*</body>'

new_modal_html = """<!-- Executive Business Sign-In Modal (Option 1) -->
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
                <p class="login-tagline">Autonomous Receivables Recovery &amp; Dispute Resolution for Indian MSMEs &amp; Retailers.</p>
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
                    <span>OR SIGN IN WITH CREDENTIALS</span>
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

                <!-- Technical / Staff API Key Access (Fully visible & script-compatible) -->
                <div class="dev-login-box">
                    <span class="dev-box-title">🛠️ Technical / Staff API Key</span>
                    <form id="auth-form" class="auth-strip">
                        <div class="dev-input-row">
                            <input id="api-key" type="password" autocomplete="off" placeholder="Enter staff API key..." class="input-styled" required>
                            <button type="submit" class="btn btn-primary">Connect</button>
                            <button type="button" id="forget-key" class="hidden" style="display:none !important;">Forget key</button>
                        </div>
                    </form>
                </div>
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

html = re.sub(old_modal_pattern, new_modal_html, html, flags=re.DOTALL)

with open("frontend/index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("Updated index.html with visible #auth-form in login modal!")

