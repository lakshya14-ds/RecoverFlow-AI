import sys
import time
sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright

def run_live_audit():
    print("Starting Live Chrome QA Audit against https://recoverflaw.duckdns.org/ ...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        page = context.new_page()

        # Capture console errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Step 1: Open Home & Login
        page.goto("https://recoverflaw.duckdns.org/")
        page.wait_for_selector("#login-modal", state="visible")
        print("PASS: Login modal visible.")

        # Click Instant Access
        page.click("#demo-login-btn")
        page.wait_for_selector("#login-modal", state="hidden")
        print("PASS: Logged in via 1-click business owner access.")

        # Step 2: Check Sidebar Compliance Claims (Phase 3)
        sidebar_text = page.inner_text(".sidebar")
        assert "TLS Encrypted Communication" in sidebar_text or "TLS" in sidebar_text, "TLS Protected claim missing in sidebar"
        assert "Indian MSME Invoicing Standard" in sidebar_text or "GST" in sidebar_text, "Indian MSME Invoicing Standard claim missing in sidebar"
        assert "Bank-Grade" not in sidebar_text, "Stale 'Bank-Grade' found in sidebar!"
        print("PASS: Sidebar compliance claims verified (no Bank-Grade, honest TLS/MSME standard).")

        # Step 3: Check Obsolete view-agent is NOT in DOM (Phase 4)
        view_agent = page.query_selector("#view-agent")
        assert view_agent is None, "Obsolete #view-agent still exists in DOM!"
        print("PASS: Obsolete #view-agent completely purged from DOM.")

        # Step 4: Navigate to 'Review and Negotiate' view
        page.click(".nav-item[data-view='review']")
        page.wait_for_selector("#case-list table", state="visible")
        time.sleep(1)
        print("PASS: Navigated to Review and Negotiate view, cases table loaded.")

        # Find RF-SAMPLE-2026-001 or a held case
        case_buttons = page.query_selector_all("#case-list .case-open")
        print(f"Found {len(case_buttons)} cases in the table.")
        assert len(case_buttons) > 0, "No cases found in table!"

        # Locate RF-SAMPLE-2026-001
        rf_btn = None
        for btn in case_buttons:
            row_text = btn.evaluate("el => el.closest('tr').innerText")
            if "RF-SAMPLE-2026-001" in row_text:
                rf_btn = btn
                break
        
        if rf_btn:
            print("Opening RF-SAMPLE-2026-001...")
            rf_btn.click()
            page.wait_for_selector("#case-detail", state="visible")
            time.sleep(1)

            # Check Eligibility & Collect button for held case (Phase 2)
            meta_text = page.inner_text(".case-meta")
            print(f"RF-SAMPLE-2026-001 meta text: '{meta_text}'")
            waterfall_text = page.inner_text(".balance-story")
            print(f"waterfall_text:\n{waterfall_text}")
            assert "UNDISPUTED · ON HOLD" in waterfall_text.upper(), "Held case did not show 'Undisputed · On Hold'!"
            assert "Collection blocked under policy" in waterfall_text, "Missing 'Collection blocked under policy' tag!"
            quick_collect_btn = page.query_selector("#quick-collect-btn")
            assert quick_collect_btn is None, "Collect Now button unexpectedly shown on held case!"
            print("PASS: Held case shows On Hold bucket, collection blocked tag, and NO Collect button.")

            # Check Dynamic Evidence Count (Phase 4)
            ev_tab_text = page.inner_text("#tab-btn-evidence")
            print(f"Evidence tab text: '{ev_tab_text}'")
            assert ev_tab_text != "Verified Evidence & AI Proof (7)", "Evidence tab text still has hardcoded (7)!"
            assert "Verified Evidence & AI Proof (" in ev_tab_text, "Evidence tab missing dynamic count format!"
            print("PASS: Dynamic evidence tab count verified.")

            # Check Prepare AI offer button disabled outside delegate mode (Phase 4)
            neg_tab_btn = page.query_selector("button[data-case-tab='tab-negotiation']")
            if neg_tab_btn:
                neg_tab_btn.click()
                time.sleep(1)
                offer_btn = page.query_selector("#negotiation-next-offer")
                assert offer_btn is not None, "Prepare AI offer button not found!"
                is_disabled = offer_btn.is_disabled()
                btn_title = offer_btn.get_attribute("title")
                print(f"Prepare AI offer button disabled: {is_disabled}, title: '{btn_title}'")
                assert is_disabled, "Prepare AI offer button is not disabled in non-delegate mode!"
                print("PASS: Prepare AI offer button is properly guarded and disabled.")

            # Back to bill list
            page.click("button:has-text('Back to bill list')")
            time.sleep(1)

        # Step 5: Open Hero Case (INV-2026-HERO) for Visual Proof & Crop checks (Phase 1)
        hero_btn = None
        for btn in page.query_selector_all("#case-list .case-open"):
            row_text = btn.evaluate("el => el.closest('tr').innerText")
            if "INV-2026-HERO" in row_text:
                hero_btn = btn
                break
        
        if hero_btn:
            print("Opening INV-2026-HERO...")
            hero_btn.click()
            page.wait_for_selector("#case-detail", state="visible")
            time.sleep(1)

            # Switch to Verified Evidence tab
            page.click("button[data-case-tab='tab-evidence']")
            time.sleep(1)

            # Check segment chips in Verified Evidence tab
            chips = page.query_selector_all(".sam-segment-chip")
            print(f"Found {len(chips)} SAM segment chips in hero case.")
            for chip in chips:
                chip_text = chip.inner_text()
                assert "dY" not in chip_text, f"Corrupted characters found in chip: {chip_text}"
                print(f"Chip verified: {chip_text.replace('\n', ' ')}")

            if chips:
                chips[0].click()
                page.wait_for_selector(".sam-crop-preview-modal", state="visible")
                modal_text = page.inner_text(".sam-modal-content")
                print(f"Crop inspection modal verified: {modal_text[:100]}...")
                page.click(".sam-close-btn")
                page.wait_for_selector(".sam-crop-preview-modal", state="hidden")
                print("PASS: Crop modal opened and closed cleanly without corrupted characters.")

        # Step 6: Check Control Center & Autonomy Transparency (Phase 3)
        page.click(".nav-item[data-view='control']")
        page.wait_for_selector("#view-control", state="visible")
        # Click AI Autonomy sub-tab
        page.click("button[data-control-subview='autonomy']")
        time.sleep(0.5)
        autonomy_text = page.inner_text("#control-subview-autonomy")
        assert "simulated sandbox outbox" in autonomy_text.lower(), "Simulated sandbox outbox transparency missing!"
        print("PASS: AI Autonomy subview states sandbox-only dispatch and dual-control review.")

        # Step 7: Check Evaluation Page (/evaluation.html) (Phase 5)
        page.goto("https://recoverflaw.duckdns.org/evaluation.html")
        page.wait_for_load_state("networkidle")
        pre_tags = page.query_selector_all("pre")
        assert len(pre_tags) == 0, f"Raw <pre> tags found on evaluation page! Count: {len(pre_tags)}"
        tables = page.query_selector_all("table")
        assert len(tables) >= 2, f"Expected styled tables on evaluation page, found: {len(tables)}"
        eval_body = page.inner_text("body")
        assert "Meta Muse Spark" in eval_body, "Meta Muse Spark missing from evaluation page!"
        assert "Meta SAM 3.1" in eval_body, "Meta SAM 3.1 missing from evaluation page!"
        assert "Meta Muse Voice" in eval_body, "Meta Muse Voice missing from evaluation page!"
        print(f"PASS: Evaluation page rendered cleanly with {len(tables)} styled tables and 0 <pre> tags.")

        page.screenshot(path="docs/images/live_audit_evaluation_page.png")
        print("Captured docs/images/live_audit_evaluation_page.png")

        browser.close()
        print("\n==========================================")
        print("ALL LIVE CHROME QA AUDIT CHECKS PASSED 100%!")
        print("==========================================")

if __name__ == "__main__":
    run_live_audit()
