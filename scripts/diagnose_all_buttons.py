import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

def diagnose():
    print("Connecting to https://recoverflaw.duckdns.org/ ...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        page = context.new_page()

        page_errors = []
        console_msgs = []
        network_failures = []

        page.on("pageerror", lambda err: page_errors.append(str(err)))
        page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
        page.on("requestfailed", lambda req: network_failures.append(f"{req.method} {req.url} -> {req.failure}"))

        page.goto("https://recoverflaw.duckdns.org/")
        page.wait_for_selector("#login-modal", state="visible")

        # 1. Click Business Demo Login
        page.click("#demo-login-btn")
        page.wait_for_selector("#login-modal", state="hidden")
        time.sleep(1)
        print("Logged in as Business Owner.")

        # 2. Check Intake View
        print("\n--- Testing Intake Tab ---")
        intake_rows = page.query_selector_all("#intake-tracker .intake-row")
        print(f"Found {len(intake_rows)} intake items.")
        retry_btn = page.query_selector(".intake-retry")
        if retry_btn:
            btn_id = retry_btn.get_attribute("data-id")
            print(f"Clicking Retry extraction on upload {btn_id}...")
            retry_btn.click()
            time.sleep(2)
            print("Finished clicking Retry extraction.")

        # 3. Check Review and Negotiate View
        print("\n--- Testing Review and Negotiate Tab ---")
        page.click(".nav-item[data-view='review']")
        page.wait_for_selector("#case-list table", state="visible")
        time.sleep(1)

        # Get all Open file buttons
        open_btns = page.query_selector_all("#case-list .case-open")
        print(f"Found {len(open_btns)} 'Open file' buttons in cases table.")
        
        for idx, btn in enumerate(open_btns):
            case_id = btn.get_attribute("data-id")
            row_text = btn.evaluate("el => el.closest('tr').innerText").replace('\n', ' | ')
            print(f"\nClicking 'Open file' for case #{case_id} ({row_text[:60]}...):")
            
            # Click open file
            btn.click()
            time.sleep(1)

            # Check if case-detail is visible
            is_detail_visible = page.is_visible("#case-detail")
            print(f"  case-detail visible: {is_detail_visible}")
            if not is_detail_visible:
                print(f"  FAILED to open case {case_id}!")
            else:
                # Check case summary content
                summary_text = page.inner_text("#case-summary")
                print(f"  Summary loaded: {summary_text[:80].replace(chr(10), ' ')}...")
                
                # Test switching tabs inside case workspace
                for tab_name in ['tab-evidence', 'tab-negotiation', 'tab-history']:
                    tab_btn = page.query_selector(f"button[data-case-tab='{tab_name}']")
                    if tab_btn:
                        tab_btn.click()
                        time.sleep(0.3)
                        pane = page.query_selector(f"#{tab_name}")
                        is_active = pane.evaluate("el => el.classList.contains('active')") if pane else False
                        print(f"    Tab {tab_name} switched: {is_active}")

                # Test close file button
                close_btn = page.query_selector("#case-close")
                if close_btn:
                    close_btn.click()
                    time.sleep(0.5)
                    print(f"    Closed file #{case_id}. Case detail hidden: {not page.is_visible('#case-detail')}")

        # 4. Check Sub-views in Review and Negotiate
        print("\n--- Testing Sub-tabs in Review and Negotiate ---")
        subtabs = [
            ('review-subnav-queue', 'Invoices Awaiting Review', '#review-list'),
            ('review-subnav-reconciliations', 'Reconciliations', '#reconciliation-table'),
            ('review-subnav-campaigns', 'Collection Campaigns', '#dunning-campaigns'),
            ('review-subnav-fraud', 'Security & Risk Alerts', '#fraud-events'),
            ('review-subnav-cases', 'Active Bills & Receivables', '#case-list')
        ]
        for sub_id, sub_label, target_sel in subtabs:
            sub_btn = page.query_selector(f"#{sub_id}")
            if sub_btn:
                sub_btn.click()
                time.sleep(0.5)
                is_vis = page.is_visible(target_sel)
                print(f"  Subtab '{sub_label}' ({sub_id}) -> target {target_sel} visible: {is_vis}")

        # 5. Check Control Center Tabs and Buttons
        print("\n--- Testing Control Center ---")
        page.click(".nav-item[data-view='control']")
        page.wait_for_selector("#view-control", state="visible")
        time.sleep(1)

        control_subtabs = [
            ('queue', 'Urgent Action Queue', '#control-subview-queue'),
            ('autonomy', 'AI Autonomy & Guardrails', '#control-subview-autonomy'),
            ('channels', 'Payment Links & Channels', '#control-subview-channels'),
            ('diagnostics', 'System Audit & Technical Logs', '#control-subview-diagnostics')
        ]
        for sub_key, sub_label, target_sel in control_subtabs:
            sub_btn = page.query_selector(f"button[data-control-subview='{sub_key}']")
            if sub_btn:
                sub_btn.click()
                time.sleep(0.5)
                is_vis = page.is_visible(target_sel)
                print(f"  Control subtab '{sub_label}' ({sub_key}) -> target {target_sel} visible: {is_vis}")

        print("\n--- Errors Summary ---")
        print(f"Page uncaught errors ({len(page_errors)}):")
        for err in page_errors:
            print(f"  ERROR: {err}")
        print(f"Network failures ({len(network_failures)}):")
        for fail in network_failures:
            print(f"  NET_FAIL: {fail}")
        console_errs = [c for c in console_msgs if "[error]" in c]
        print(f"Console errors ({len(console_errs)}):")
        for cerr in console_errs:
            print(f"  CONSOLE: {cerr}")

        browser.close()

if __name__ == "__main__":
    diagnose()
