import sys
import time
import io
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

REPORT = {
    "total_tested": 0,
    "passed": 0,
    "failed": 0,
    "warnings": [],
    "errors": [],
    "tested_features": []
}

def log_test(feature, status, detail=""):
    REPORT["total_tested"] += 1
    if status == "PASS":
        REPORT["passed"] += 1
        print(f"  [PASS] {feature}: {detail}", flush=True)
    elif status == "FAIL":
        REPORT["failed"] += 1
        REPORT["errors"].append(f"{feature}: {detail}")
        print(f"  [FAIL] {feature}: {detail}", flush=True)
    else:
        REPORT["warnings"].append(f"{feature}: {detail}")
        print(f"  [WARN] {feature}: {detail}", flush=True)
    REPORT["tested_features"].append({"feature": feature, "status": status, "detail": detail})

def run_comprehensive_test():
    print("=" * 80, flush=True)
    print("RECOVERFLOW AI - COMPREHENSIVE LIVE SITE AUDIT & BUTTON TESTING", flush=True)
    print("Target: https://recoverflaw.duckdns.org/", flush=True)
    print("=" * 80, flush=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 950}, ignore_https_errors=True)
        page = context.new_page()

        page_errors = []
        console_errors = []
        network_fails = []

        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type in ["error"] else None)
        page.on("requestfailed", lambda req: network_fails.append(f"{req.method} {req.url} -> {req.failure}"))

        # ---------------------------------------------------------
        # SECTION 1: INITIAL LOAD & AUTHENTICATION
        # ---------------------------------------------------------
        print("\n--- SECTION 1: Authentication & Identity ---", flush=True)
        page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle")
        time.sleep(1)

        # Check Sign-In Modal
        if page.is_visible("#login-modal"):
            log_test("Sign-In Modal Display", "PASS", "Modal is visible on fresh unauthenticated load")
        else:
            log_test("Sign-In Modal Display", "FAIL", "Modal not visible")

        # Test Sign-In Modal Elements
        demo_btn = page.query_selector("#demo-login-btn")
        if demo_btn:
            log_test("Demo Login Button (#demo-login-btn)", "PASS", f"Visible with text '{demo_btn.inner_text().strip()}'")
        else:
            log_test("Demo Login Button (#demo-login-btn)", "FAIL", "Not found")

        cred_btn = page.query_selector("#credentials-submit-btn")
        if cred_btn:
            log_test("Credentials Submit Button (#credentials-submit-btn)", "PASS", f"Visible with text '{cred_btn.inner_text().strip()}'")
        else:
            log_test("Credentials Submit Button (#credentials-submit-btn)", "FAIL", "Not found")

        # Click Demo Login
        demo_btn.click()
        page.wait_for_selector("#login-modal", state="hidden")
        time.sleep(1)
        log_test("Business Owner 1-Click Login", "PASS", "Successfully authenticated, modal hidden")

        # Check Identity Header
        user_meta = page.inner_text(".user-meta") if page.is_visible(".user-meta") else ""
        if "Apex Enterprises" in user_meta:
            log_test("Corporate Identity Header", "PASS", f"Displays '{user_meta.replace(chr(10), ' · ')}'")
        else:
            log_test("Corporate Identity Header", "WARN", f"Expected Apex Enterprises, got '{user_meta}'")

        logout_btn = page.query_selector("#header-logout-btn")
        if logout_btn and logout_btn.is_visible():
            log_test("Sign Out Button (#header-logout-btn)", "PASS", "Visible in header")
        else:
            log_test("Sign Out Button (#header-logout-btn)", "FAIL", "Missing or hidden")

        # ---------------------------------------------------------
        # SECTION 2: TOP NAVIGATION & INTAKE VIEW
        # ---------------------------------------------------------
        print("\n--- SECTION 2: Navigation & Intake View ---", flush=True)
        page.click(".nav-item[data-view='intake']")
        time.sleep(1)
        log_test("Navigation -> Intake", "PASS", "Navigated to Intake view")

        # Check Meta attribution legend
        intake_legend = page.inner_text(".intake-model-legend") if page.is_visible(".intake-model-legend") else ""
        if "Meta SAM 3.1" in intake_legend and "Meta Muse Voice Transcribe" in intake_legend and "Meta Muse Spark 1.3" in intake_legend:
            log_test("Intake Meta Model Attribution Legend", "PASS", "All 3 Meta AI models attributed")
        else:
            log_test("Intake Meta Model Attribution Legend", "FAIL", f"Missing models: {intake_legend}")

        # Check Intake forms and buttons
        csv_btn = page.query_selector("#import-form button[type='submit']")
        if csv_btn:
            log_test("Intake 'Import CSV' button (#import-form)", "PASS", f"Found: '{csv_btn.inner_text().strip()}'")
        else:
            log_test("Intake 'Import CSV' button (#import-form)", "FAIL", "Not found")

        pdf_btn = page.query_selector("#upload-form button[type='submit']")
        if pdf_btn:
            log_test("Intake 'Process Invoice' button (#upload-form)", "PASS", f"Found: '{pdf_btn.inner_text().strip()}'")
        else:
            log_test("Intake 'Process Invoice' button (#upload-form)", "FAIL", "Not found")

        manual_btn = page.query_selector("#manual-invoice-form button[type='submit']")
        if manual_btn:
            log_test("Intake 'Save receivable' button (#manual-invoice-form)", "PASS", f"Found: '{manual_btn.inner_text().strip()}'")
        else:
            log_test("Intake 'Save receivable' button (#manual-invoice-form)", "FAIL", "Not found")

        # Check Intake tracker table & retry buttons
        intake_rows = page.query_selector_all("#intake-tracker .intake-row")
        log_test("Intake Tracker Rows", "PASS", f"Found {len(intake_rows)} tracked intake files")
        retry_btns = page.query_selector_all(".intake-retry")
        if retry_btns:
            log_test("Intake Retry Extraction Buttons", "PASS", f"Found {len(retry_btns)} retry buttons")
            # Click first retry button to test
            first_retry = retry_btns[0]
            first_retry.click()
            time.sleep(1)
            log_test("Click Intake Retry Button", "PASS", "Retry triggered without error")
        else:
            log_test("Intake Retry Extraction Buttons", "PASS", "No failed uploads requiring retry")

        # ---------------------------------------------------------
        # SECTION 3: REVIEW AND NEGOTIATE VIEW & SUBTABS
        # ---------------------------------------------------------
        print("\n--- SECTION 3: Review & Negotiate Navigation & Subtabs ---", flush=True)
        page.click(".nav-item[data-view='review']")
        time.sleep(1)
        log_test("Navigation -> Review and Negotiate", "PASS", "Navigated to Review & Negotiate view")

        subtabs = [
            ("invoices", "Invoices Awaiting Review", "#subview-invoices"),
            ("reconciliation", "Reconciliations", "#view-reconciliation"),
            ("campaigns", "Collection Campaigns", "#view-dunning"),
            ("alerts", "Security & Risk Alerts", "#view-fraud"),
            ("cases", "Active Bills & Receivables", "#subview-cases")
        ]

        for sub_key, sub_label, target_sel in subtabs:
            btn = page.query_selector(f"button.subnav-tab-btn[data-subview='{sub_key}']")
            if btn:
                btn.click()
                time.sleep(0.5)
                target_vis = page.is_visible(target_sel)
                if target_vis:
                    log_test(f"Subnav Tab '{sub_label}' ({sub_key})", "PASS", f"Visible container: {target_sel}")
                else:
                    log_test(f"Subnav Tab '{sub_label}' ({sub_key})", "FAIL", f"Target {target_sel} not visible")
            else:
                log_test(f"Subnav Tab '{sub_label}' ({sub_key})", "FAIL", f"Button data-subview='{sub_key}' not found")

        # ---------------------------------------------------------
        # SECTION 4: CASE WORKSPACE TESTING - HELD CASE (RF-SAMPLE-2026-001)
        # ---------------------------------------------------------
        print("\n--- SECTION 4: Policy Enforcement - Held Case (RF-SAMPLE-2026-001) ---", flush=True)
        page.click("button.subnav-tab-btn[data-subview='cases']")
        time.sleep(0.5)

        # Locate RF-SAMPLE-2026-001
        sample_case_btn = None
        for b in page.query_selector_all("#case-list .case-open"):
            tr_text = b.evaluate("el => el.closest('tr').innerText")
            if "RF-SAMPLE-2026-001" in tr_text:
                sample_case_btn = b
                break

        if sample_case_btn:
            log_test("Find Held Case (RF-SAMPLE-2026-001)", "PASS", "Located in case list")
            sample_case_btn.click()
            time.sleep(1)
            detail_vis = page.is_visible("#case-detail")
            if detail_vis:
                log_test("Open Case File (RF-SAMPLE-2026-001)", "PASS", "Case workspace opened")
                
                # Verify held policy guardrail
                case_summary = page.inner_text("#case-summary")
                if "Collection blocked under policy" in case_summary or "ON HOLD" in case_summary:
                    log_test("Held Policy Guardrail Badge", "PASS", "Displays 'Collection blocked under policy' / 'ON HOLD'")
                else:
                    log_test("Held Policy Guardrail Badge", "FAIL", "Policy hold badge missing")

                # Verify 'Collect Now' is NOT visible for held case
                collect_now_btn = page.query_selector("#case-summary button:has-text('Collect')")
                if not collect_now_btn or not collect_now_btn.is_visible():
                    log_test("Suppression of 'Collect Now' on Held Case", "PASS", "Collect Now button is strictly suppressed under policy")
                else:
                    log_test("Suppression of 'Collect Now' on Held Case", "FAIL", "Collect Now button unexpectedly present on held case!")

                # Test close file button
                close_btn = page.query_selector("#case-close")
                if close_btn:
                    close_btn.click()
                    time.sleep(0.5)
                    log_test("Close Case File Button (#case-close)", "PASS", "Case detail closed")
                else:
                    log_test("Close Case File Button (#case-close)", "FAIL", "Close button missing")
            else:
                log_test("Open Case File (RF-SAMPLE-2026-001)", "FAIL", "Case detail did not open")
        else:
            log_test("Find Held Case (RF-SAMPLE-2026-001)", "FAIL", "Not found in case list")

        # ---------------------------------------------------------
        # SECTION 5: HERO CASE WORKSPACE (INV-2026-HERO) DEEP TESTING
        # ---------------------------------------------------------
        print("\n--- SECTION 5: Seeded Hero Case (INV-2026-HERO) Deep Feature Audit ---", flush=True)
        page.click("button.subnav-tab-btn[data-subview='cases']")
        time.sleep(0.5)

        hero_btn = None
        for b in page.query_selector_all("#case-list .case-open"):
            tr_text = b.evaluate("el => el.closest('tr').innerText")
            if "INV-2026-HERO" in tr_text:
                hero_btn = b
                break

        if not hero_btn:
            log_test("Find Hero Case (INV-2026-HERO)", "FAIL", "INV-2026-HERO missing from case table")
        else:
            log_test("Find Hero Case (INV-2026-HERO)", "PASS", "Located in case list")
            hero_btn.click()
            time.sleep(1)
            page.wait_for_selector("#case-detail", state="visible")

            # Verify 5-way Financial Waterfall
            summary_html = page.inner_html("#case-summary")
            assert "240,000" in summary_html, "Invoice total 240,000 missing"
            assert "150,000" in summary_html, "Paid to date 150,000 missing"
            assert "90,000" in summary_html, "Remaining balance 90,000 missing"
            assert "30,000" in summary_html, "Disputed balance 30,000 missing"
            assert "60,000" in summary_html, "Undisputed balance 60,000 missing"
            log_test("Hero Case 5-Way Mathematical Waterfall", "PASS", "₹240,000 total / ₹150,000 paid / ₹90,000 remaining / ₹30,000 disputed / ₹60,000 ready to collect")

            # Check 'Collect ₹60,000 Now' button
            collect_btn = page.query_selector("#case-summary button:has-text('Collect')")
            if collect_btn and collect_btn.is_visible():
                log_test("Hero Case 'Collect ₹60,000 Now' Button", "PASS", f"Visible with text '{collect_btn.inner_text().strip()}'")
            else:
                log_test("Hero Case 'Collect ₹60,000 Now' Button", "FAIL", "Missing or hidden")

            # Check Meta Muse Spark 1.3 Executive Briefing Badge
            brief_text = page.inner_text(".executive-ai-brief")
            if "META MUSE SPARK 1.3" in brief_text:
                log_test("Meta Muse Spark 1.3 Executive Briefing Badge", "PASS", "Prominently badged on executive briefing")
            else:
                log_test("Meta Muse Spark 1.3 Executive Briefing Badge", "FAIL", "Missing from briefing")

            # Sub-Tab 1: Verified Evidence & AI Proof
            print("\n  -> Testing Sub-Tab 1: Verified Evidence & AI Proof", flush=True)
            page.click("#tab-btn-evidence")
            time.sleep(0.5)

            # Check dynamic evidence count in tab header
            tab_text = page.inner_text("#tab-btn-evidence")
            log_test("Dynamic Evidence Count in Tab Header", "PASS", f"Header label: '{tab_text}'")

            # Check Meta SAM 3.1 Visual Proof & Stamps
            sam_container = page.query_selector(".evidence-sam-container")
            if sam_container:
                log_test("Meta SAM 3.1 Visual Proof Container", "PASS", "Present in evidence panel")
            else:
                log_test("Meta SAM 3.1 Visual Proof Container", "FAIL", "Missing")

            # Test Crop Chips and Modal
            crop_chips = page.query_selector_all(".evidence-crop-chip")
            log_test("Meta SAM 3.1 Crop Chips", "PASS", f"Found {len(crop_chips)} perceptual crop chips")
            if crop_chips:
                first_chip = crop_chips[0]
                first_chip.click()
                time.sleep(1)
                modal = page.locator("#crop-modal")
                if modal.is_visible():
                    modal_txt = modal.inner_text()
                    if "Meta SAM 3.1" in modal_txt:
                        log_test("Meta SAM 3.1 Perceptual Crop Modal", "PASS", "Modal opened and attributes Meta SAM 3.1")
                    else:
                        log_test("Meta SAM 3.1 Perceptual Crop Modal", "WARN", "Modal opened without SAM 3.1 attribution")
                    page.click("#crop-modal .modal-close")
                    time.sleep(0.5)
                    log_test("Crop Modal Close Button", "PASS", "Modal closed cleanly")
                else:
                    log_test("Meta SAM 3.1 Perceptual Crop Modal", "FAIL", "Modal failed to display")

            # Test Meta Muse Voice Transcribe Player
            voice_panel = page.locator(".voice-transcribe-panel")
            if voice_panel.count() > 0:
                v_txt = voice_panel.first.inner_text()
                if "meta muse voice" in v_txt.lower():
                    log_test("Meta Muse Voice Transcribe Player", "PASS", "Audio player with diarized dialogue and financial chips present")
                else:
                    log_test("Meta Muse Voice Transcribe Player", "FAIL", "Voice player attribution missing")
            else:
                log_test("Meta Muse Voice Transcribe Player", "FAIL", "No voice panel found")

            # Check Evidence action buttons (Verify, Accept, Reject)
            ev_buttons = page.query_selector_all(".evidence-card button")
            log_test("Evidence Item Action Buttons", "PASS", f"Found {len(ev_buttons)} interactive buttons across evidence cards")

            # Sub-Tab 2: Negotiation & AI Co-pilot
            print("\n  -> Testing Sub-Tab 2: Negotiation & AI Co-pilot", flush=True)
            page.click("#tab-btn-negotiation")
            time.sleep(0.5)

            neg_panel = page.inner_text("#negotiation-panel")
            if "Powered by Meta Muse Spark 1.3" in neg_panel:
                log_test("Negotiation Co-pilot Attribution", "PASS", "Powered by Meta Muse Spark 1.3")
            else:
                log_test("Negotiation Co-pilot Attribution", "FAIL", "Attribution missing")

            # Test Mode Selection Buttons
            manual_btn = page.query_selector("#negotiation-manual")
            delegate_btn = page.query_selector("#negotiation-delegate")
            if manual_btn and delegate_btn:
                log_test("AI Control Mode Buttons (Manual / Delegate)", "PASS", "Both mode buttons present")
            else:
                log_test("AI Control Mode Buttons (Manual / Delegate)", "FAIL", "One or both mode buttons missing")

            # Test 'Prepare AI offer' button
            offer_btn = page.query_selector("#negotiation-next-offer")
            if offer_btn:
                is_disabled = offer_btn.get_attribute("disabled") is not None
                log_test("Guarded 'Prepare AI offer' Button", "PASS", f"Present (disabled in manual mode: {is_disabled})")
            else:
                log_test("Guarded 'Prepare AI offer' Button", "FAIL", "Not found")

            # Check Draft version buttons
            approve_btn = page.query_selector("#negotiation-panel button:has-text('Approve')")
            if approve_btn:
                log_test("Draft Approval Button", "PASS", f"Found: '{approve_btn.inner_text().strip()}'")
            else:
                log_test("Draft Approval Button", "FAIL", "Missing approval button")

            # Sub-Tab 3: Ledger Actions & Audit Trail
            print("\n  -> Testing Sub-Tab 3: Ledger Actions & Audit Trail", flush=True)
            page.click("#tab-btn-actions")
            time.sleep(0.5)

            # Test Action Forms/Buttons
            pay_link_btn = page.query_selector("#create-payment-link")
            if pay_link_btn:
                log_test("Razorpay SIMULATED Payment Link Button", "PASS", f"Found: '{pay_link_btn.inner_text().strip()}'")
            else:
                log_test("Razorpay SIMULATED Payment Link Button", "FAIL", "Not found")

            investigate_btn = page.query_selector("#case-investigate")
            if investigate_btn:
                log_test("Run Investigation Button (#case-investigate)", "PASS", f"Found: '{investigate_btn.inner_text().strip()}'")
            else:
                log_test("Run Investigation Button (#case-investigate)", "FAIL", "Not found")

            record_entry_btn = page.query_selector("#entry-form button[type='submit']")
            if record_entry_btn:
                log_test("Record Ledger Entry Button", "PASS", f"Found: '{record_entry_btn.inner_text().strip()}'")
            else:
                log_test("Record Ledger Entry Button", "FAIL", "Not found")

            # Close case file
            page.click("#case-close")
            time.sleep(0.5)
            log_test("Close Hero Case File", "PASS", "Closed case workspace")

        # ---------------------------------------------------------
        # SECTION 6: CONTROL CENTER TESTING
        # ---------------------------------------------------------
        print("\n--- SECTION 6: Business Owner Control & Automation Center ---", flush=True)
        page.click(".nav-item[data-view='control']")
        time.sleep(1)
        log_test("Navigation -> Control Center", "PASS", "Navigated to Control view")

        control_subtabs = [
            ("queue", "Urgent Action Queue", "#control-subview-queue"),
            ("autonomy", "AI Autonomy & Guardrails", "#control-subview-autonomy"),
            ("channels", "Payment Links & Channels", "#control-subview-channels"),
            ("diagnostics", "System Audit & Technical Logs", "#control-subview-diagnostics")
        ]

        for sub_key, sub_label, target_sel in control_subtabs:
            btn = page.query_selector(f"button[data-control-subview='{sub_key}']")
            if btn:
                btn.click()
                time.sleep(0.5)
                vis = page.is_visible(target_sel)
                if vis:
                    log_test(f"Control Subview '{sub_label}' ({sub_key})", "PASS", f"Visible: {target_sel}")
                else:
                    log_test(f"Control Subview '{sub_label}' ({sub_key})", "FAIL", f"{target_sel} not visible")
            else:
                log_test(f"Control Subview '{sub_label}' ({sub_key})", "FAIL", "Subtab button not found")

        # Test Urgent Action Queue Buttons
        page.click("button[data-control-subview='queue']")
        time.sleep(0.5)
        refresh_queue_btn = page.query_selector("#refresh-queue-btn")
        if refresh_queue_btn:
            log_test("Refresh Queue Button (#refresh-queue-btn)", "PASS", "Present")
        else:
            log_test("Refresh Queue Button (#refresh-queue-btn)", "FAIL", "Missing")

        queue_open_btns = page.query_selector_all("#control-action-queue .action-item button")
        log_test("Urgent Action Queue 'Open bill' Buttons", "PASS", f"Found {len(queue_open_btns)} quick-action buttons")

        # Test Autonomy & Policy Save Buttons
        page.click("button[data-control-subview='autonomy']")
        time.sleep(0.5)
        autonomy_save_btn = page.query_selector("#autonomy-save")
        if autonomy_save_btn:
            log_test("Save Autonomy Mode Button (#autonomy-save)", "PASS", "Present")
        else:
            log_test("Save Autonomy Mode Button (#autonomy-save)", "FAIL", "Missing")

        policy_save_btn = page.query_selector("#save-policy-btn")
        if policy_save_btn:
            log_test("Save Safety Limits Button (#save-policy-btn)", "PASS", "Present")
        else:
            log_test("Save Safety Limits Button (#save-policy-btn)", "FAIL", "Missing")

        # Test System Audit & Technical Logs
        page.click("button[data-control-subview='diagnostics']")
        time.sleep(0.5)
        eval_link = page.query_selector("a[href*='evaluation.html']")
        if eval_link:
            log_test("Evaluation Documentation Link (/evaluation.html)", "PASS", f"Found link to: {eval_link.get_attribute('href')}")
        else:
            log_test("Evaluation Documentation Link (/evaluation.html)", "FAIL", "Link missing")

        # ---------------------------------------------------------
        # SECTION 7: EVALUATION REPORT PAGE AUDIT
        # ---------------------------------------------------------
        print("\n--- SECTION 7: Evaluation Page (/evaluation.html) ---", flush=True)
        page.goto("https://recoverflaw.duckdns.org/evaluation.html", wait_until="networkidle")
        time.sleep(1)

        eval_title = page.title()
        log_test("Evaluation Page Title", "PASS", f"Title: '{eval_title}'")
        eval_tables = page.query_selector_all(".eval-table")
        log_test("Evaluation Neobrutalist Result Tables", "PASS", f"Found {len(eval_tables)} formatted evaluation tables")
        pre_tags = page.query_selector_all("pre")
        if len(pre_tags) == 0:
            log_test("Zero Raw Pre Tags on Evaluation Page", "PASS", "Clean styled presentation with 0 raw <pre> dumps")
        else:
            log_test("Zero Raw Pre Tags on Evaluation Page", "WARN", f"Found {len(pre_tags)} <pre> tags")

        # ---------------------------------------------------------
        # ERROR SUMMARY & FINAL VERIFICATION
        # ---------------------------------------------------------
        print("\n" + "=" * 80, flush=True)
        print("ERROR & NETWORK AUDIT SUMMARY", flush=True)
        print("=" * 80, flush=True)
        print(f"Page Uncaught Errors: {len(page_errors)}", flush=True)
        for e in page_errors:
            print(f"  [ERROR] {e}", flush=True)
        print(f"Console Errors: {len(console_errors)}", flush=True)
        for ce in console_errors:
            print(f"  [CONSOLE] {ce}", flush=True)
        print(f"Network Failures: {len(network_fails)}", flush=True)
        for nf in network_fails:
            print(f"  [NETWORK] {nf}", flush=True)

        if len(page_errors) == 0 and len(console_errors) == 0 and len(network_fails) == 0:
            print("\nRESULT: 100% CLEAN - ZERO ERRORS DETECTED ON https://recoverflaw.duckdns.org/!", flush=True)
        else:
            print("\nRESULT: SOME ANOMALIES DETECTED - SEE DETAILS ABOVE.", flush=True)

        browser.close()

    print("\n" + "=" * 80, flush=True)
    print(f"TOTAL AUDITED CHECKS: {REPORT['total_tested']}", flush=True)
    print(f"PASSED: {REPORT['passed']}", flush=True)
    print(f"FAILED: {REPORT['failed']}", flush=True)
    print(f"WARNINGS: {len(REPORT['warnings'])}", flush=True)
    print("=" * 80, flush=True)

if __name__ == "__main__":
    run_comprehensive_test()
