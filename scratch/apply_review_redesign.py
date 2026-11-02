"""
Apply Review & Negotiate redesign for business owners.
"""
from pathlib import Path
import re

INDEX_HTML = Path("frontend/index.html")
STYLES_CSS = Path("frontend/styles.css")
APP_JS = Path("frontend/app.js")

def update_index_html():
    content = INDEX_HTML.read_text(encoding="utf-8")

    # Replace view-cases content
    old_cases_pattern = re.compile(
        r'<div id="view-cases" class="view hidden">.*?</div>\s*<div id="view-reconciliation"',
        re.DOTALL
    )

    new_cases_html = '''<div id="view-cases" class="view hidden">
                <!-- Review & Negotiate Executive Sub-Navigation -->
                <div class="review-subnav-bar">
                    <button type="button" class="subnav-tab-btn active" data-subview="cases">
                        <span class="tab-icon">📋</span> Active Bills &amp; Receivables
                    </button>
                    <button type="button" class="subnav-tab-btn" data-subview="invoices">
                        <span class="tab-icon">📥</span> Invoices Awaiting Review
                    </button>
                    <button type="button" class="subnav-tab-btn" data-subview="reconciliation">
                        <span class="tab-icon">🔄</span> Reconciliations
                    </button>
                    <button type="button" class="subnav-tab-btn" data-subview="campaigns">
                        <span class="tab-icon">📢</span> Collection Campaigns
                    </button>
                    <button type="button" class="subnav-tab-btn" data-subview="alerts">
                        <span class="tab-icon">🛡️</span> Security &amp; Risk Alerts
                    </button>
                </div>

                <!-- Sub-view 1: Primary Receivables Bills Workspace -->
                <div id="subview-cases" class="review-subview-panel">
                    <div class="paper-panel" id="case-list-panel">
                        <div class="section-heading">
                            <div>
                                <h3>Receivable cases</h3>
                                <p>Search by invoice or customer. Open a file for the balance and evidence.</p>
                            </div>
                            <label class="search-field">Search cases<input id="case-search" type="search" placeholder="Invoice or customer" autocomplete="off"></label>
                        </div>
                        <div id="case-list">Open this tab to load cases.</div>
                    </div>

                    <!-- Focused Case Workspace -->
                    <div id="case-detail" class="case-workspace hidden">
                        <div class="section-heading case-top-bar">
                            <div class="case-top-meta">
                                <button type="button" id="case-back-btn" class="btn btn-secondary">← Back to bill list</button>
                                <p class="eyebrow">Case File Workspace</p>
                                <h3>Balance &amp; Evidence</h3>
                            </div>
                            <button type="button" id="case-close" class="btn">Close file</button>
                        </div>
                        <div id="case-summary"></div>

                        <!-- Case Workspace Navigation Tabs -->
                        <div class="case-tabs-bar">
                            <button type="button" class="case-tab-pill active" id="tab-btn-evidence" data-case-tab="tab-evidence">
                                📂 Verified Evidence &amp; AI Proof (7)
                            </button>
                            <button type="button" class="case-tab-pill" id="tab-btn-negotiation" data-case-tab="tab-negotiation">
                                💬 Negotiation &amp; AI Co-pilot
                            </button>
                            <button type="button" class="case-tab-pill" id="tab-btn-actions" data-case-tab="tab-actions">
                                ⚡ Ledger Actions &amp; Audit Trail
                            </button>
                        </div>

                        <div class="case-columns">
                            <!-- Case Tab 1: Evidence & AI Proof -->
                            <section class="case-evidence case-tab-pane active" id="tab-evidence">
                                <div id="case-history"></div>
                            </section>

                            <!-- Case Tab 2: Negotiation Panel -->
                            <section class="case-tab-pane" id="tab-negotiation">
                                <div id="negotiation-panel" class="paper-panel">
                                    <div class="section-heading">
                                        <div>
                                            <h3>AI Co-Pilot &amp; Customer Negotiation</h3>
                                            <p>Supervise autonomous Meta AI drafts or take over directly. SIMULATED customer and sandbox outbox only.</p>
                                        </div>
                                    </div>
                                    <div id="negotiation-status"></div>
                                    <div class="negotiation-controls">
                                        <button type="button" class="btn" id="negotiation-manual">Manual with co-pilot</button>
                                        <button type="button" class="btn" id="negotiation-delegate">Delegate to AI</button>
                                        <button type="button" class="btn" id="negotiation-pause">Pause AI</button>
                                        <button type="button" class="btn" id="negotiation-take-over">Take over</button>
                                        <button type="button" class="btn" id="negotiation-stop">Stop</button>
                                    </div>
                                    <div id="negotiation-suggestions"></div>
                                    <form id="negotiation-send-form" class="data-form">
                                        <label>Staff message<textarea name="body" required placeholder="Edit split-balance draft or type custom message..."></textarea></label>
                                        <button type="submit" class="btn btn-primary">Send to sandbox</button>
                                    </form>
                                    <button type="button" class="btn btn-primary" id="negotiation-next-offer">Prepare AI offer</button>
                                    <form id="negotiation-customer-form" class="data-form">
                                        <label>SIMULATED customer reply<input name="body" required placeholder="Type simulated customer response..."></label>
                                        <button type="submit" class="btn">Add simulated reply</button>
                                    </form>
                                    <div id="negotiation-transcript"></div>
                                </div>
                            </section>

                            <!-- Case Tab 3: Staff Actions & Ledger Entries -->
                            <section class="case-actions case-tab-pane" id="tab-actions">
                                <h4>Business Actions &amp; Controls</h4>
                                <p class="muted">Record only verified ledger activity. Customer-facing messages require staff approval.</p>

                                <div class="action-card-grid">
                                    <div class="action-subcard primary-action-card">
                                        <h4>Razorpay SIMULATED payment link</h4>
                                        <p>Creates a simulated payment link for the eligible INR balance. Staff decide whether to share it.</p>
                                        <button type="button" id="create-payment-link" class="btn btn-primary">Create payment link</button>
                                        <p id="payment-link-result"></p>
                                    </div>

                                    <div class="action-subcard">
                                        <h4>Record a payment or credit</h4>
                                        <form id="entry-form" class="data-form">
                                            <select name="kind"><option value="payment">Payment</option><option value="credit">Credit</option></select>
                                            <input name="amount" type="number" min="0.01" step="0.01" placeholder="Amount (e.g. 60000.00)" required>
                                            <input name="reference" placeholder="Unique receipt or reference (e.g. RTGS-99214)" required>
                                            <label>Apply to balance
                                                <select name="allocation">
                                                    <option value="undisputed_first">Undisputed first</option>
                                                    <option value="disputed_first">Disputed first</option>
                                                    <option value="undisputed">Undisputed only</option>
                                                    <option value="disputed">Disputed only</option>
                                                </select>
                                            </label>
                                            <button type="submit" class="btn btn-primary">Record entry</button>
                                        </form>
                                        <p id="entry-result"></p>
                                    </div>

                                    <div class="action-subcard">
                                        <h4>Investigate discrepancy</h4>
                                        <p>Compare linked invoice, order, delivery, return, and scheme records. Conflicts pause contact for staff review.</p>
                                        <button type="button" id="case-investigate" class="btn">Run investigation</button>
                                        <p id="investigation-result"></p>

                                        <form id="case-evidence-form" class="data-form" style="margin-top:10px;">
                                            <label>Source record or upload reference<input name="source_reference" required placeholder="Document or upload reference"></label>
                                            <label>Evidence title<input name="title" required placeholder="e.g. Warehouse POD"></label>
                                            <label>What the source shows<input name="description" required placeholder="e.g. Signed bilty remark"></label>
                                            <button type="submit" class="btn">Attach source</button>
                                        </form>
                                        <p id="case-evidence-result"></p>
                                    </div>

                                    <div class="action-subcard">
                                        <h4>Record a customer reply</h4>
                                        <form id="reply-form" class="data-form">
                                            <select name="category">
                                                <option value="question">Question</option>
                                                <option value="needs_time">Needs time</option>
                                                <option value="paid_claim">Already paid</option>
                                                <option value="dispute">Dispute</option>
                                                <option value="opt_out">Opt out</option>
                                                <option value="other">Other</option>
                                            </select>
                                            <input name="body" placeholder="Customer's message" required>
                                            <button type="submit" class="btn btn-primary">Record reply</button>
                                        </form>
                                        <p id="reply-result"></p>
                                    </div>
                                </div>

                                <form id="dispute-review-form" class="data-form hidden">
                                    <label>Reviewed disputed amount<input name="disputed_amount" type="number" min="0" step="0.01" required></label>
                                    <label>Evidence reviewed<select name="evidence_id" required></select></label>
                                    <label>Reason for decision<input name="reason" minlength="5" required></label>
                                    <button type="submit" class="btn">Save staff dispute decision</button>
                                </form>
                                <p id="dispute-review-result"></p>

                                <form id="resume-form" class="data-form hidden">
                                    <input name="reason" placeholder="Reason contact may resume" required minlength="3">
                                    <label><input name="consent_restored" type="checkbox"> Contact permission restored if the customer opted out</label>
                                    <button type="submit" class="btn">Resume contact (admin)</button>
                                </form>
                                <p id="resume-result"></p>

                                <form id="shopify-confirm-form" class="data-form hidden">
                                    <input name="reason" placeholder="Why the Shopify balance is confirmed" required minlength="3">
                                    <label><input name="accept_due_date_change" type="checkbox"> Accept a changed due date</label>
                                    <button type="submit" class="btn">Confirm Shopify case (admin)</button>
                                </form>
                                <p id="shopify-confirm-result"></p>
                            </section>
                        </div>
                    </div>
                </div>

                <!-- Sub-view 2: Invoices Awaiting Review -->
                <div id="subview-invoices" class="review-subview-panel hidden">
                    <div class="card" id="invoices-review-card">
                        <h3>Invoices Awaiting Review</h3>
                        <p class="muted">Uploaded intake bills requiring staff verification before case activation.</p>
                        <div id="review-list">Open this tab to load invoices.</div>
                    </div>
                </div>
            </div>

            <div id="view-reconciliation"'''

    new_content, count = old_cases_pattern.subn(new_cases_html, content)
    if count == 1:
        INDEX_HTML.write_text(new_content, encoding="utf-8")
        print("Updated frontend/index.html successfully!")
    else:
        print(f"Error updating frontend/index.html: pattern matched {count} times.")

if __name__ == "__main__":
    update_index_html()

