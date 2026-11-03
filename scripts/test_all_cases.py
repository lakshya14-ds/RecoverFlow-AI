import sys
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")

def test_all_cases():
    print("Testing 'Open file' on all cases at https://recoverflaw.duckdns.org/ ...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        page = context.new_page()

        errors = []
        page.on("pageerror", lambda err: errors.append(f"PAGE_ERROR: {err}"))
        page.on("console", lambda msg: errors.append(f"CONSOLE_{msg.type.upper()}: {msg.text}") if msg.type == "error" else None)

        page.goto("https://recoverflaw.duckdns.org/")
        page.wait_for_selector("#login-modal", state="visible")
        page.click("#demo-login-btn")
        page.wait_for_selector("#login-modal", state="hidden")
        time.sleep(1)

        # Go to review
        page.click(".nav-item[data-view='review']")
        page.wait_for_selector("#case-list table", state="visible")
        time.sleep(1)

        # Count cases
        rows = page.query_selector_all("#case-list table tbody tr")
        print(f"Total rows in cases table: {len(rows)}")

        for i in range(len(rows)):
            # Re-query rows to avoid stale element references
            current_rows = page.query_selector_all("#case-list table tbody tr")
            if i >= len(current_rows):
                break
            row = current_rows[i]
            row_text = row.inner_text().replace('\n', ' | ')
            btn = row.query_selector(".case-open")
            if not btn:
                print(f"Row {i} has NO .case-open button! Text: {row_text}")
                continue

            case_id = btn.get_attribute("data-id")
            print(f"\n[Case {i+1}/{len(rows)}] Clicking 'Open file' for Case ID {case_id}:")
            print(f"  Row: {row_text[:70]}...")

            # Click open file
            btn.click()
            time.sleep(1)

            # Check if case-detail opened
            detail_visible = page.is_visible("#case-detail")
            summary_content = page.inner_text("#case-summary") if detail_visible else ""
            print(f"  -> case-detail visible: {detail_visible}")
            print(f"  -> Summary: {summary_content[:90].replace(chr(10), ' ')}...")

            if not detail_visible:
                print(f"  FAILED TO OPEN CASE {case_id}!")
                errors.append(f"Failed to open case {case_id}")

            # Test Close file
            close_btn = page.query_selector("#case-close")
            if close_btn:
                close_btn.click()
                time.sleep(0.5)

        print("\n==========================================")
        print(f"Completed testing all cases. Errors encountered: {len(errors)}")
        for err in errors:
            print(f"  {err}")
        print("==========================================")

        browser.close()

if __name__ == "__main__":
    test_all_cases()

