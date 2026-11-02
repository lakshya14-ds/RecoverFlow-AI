import asyncio
import os
import sys
from playwright.async_api import async_playwright

os.makedirs("scratch/screenshots_control_verified", exist_ok=True)

async def run():
    print("Starting automated verification of Control section on https://recoverflaw.duckdns.org/ ...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # 1. Navigate to live site
        print("[1] Opening https://recoverflaw.duckdns.org/ ...", flush=True)
        res = await page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle", timeout=30000)
        print(f"    Page loaded with status: {res.status}", flush=True)

        # 2. Enter API key
        print("[2] Submitting API key recoverflow-local-final-qa-2026...", flush=True)
        await page.fill("#api-key", "recoverflow-local-final-qa-2026")
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(2000)

        # 3. Click Control tab
        print("[3] Clicking Control navigation item...", flush=True)
        await page.click("a.nav-item[data-view='control']")
        await page.wait_for_timeout(2500)

        # 4. Check page height
        box = await page.locator("main.content").bounding_box()
        print(f"    Control main content height: {box['height']:.1f}px (previously was 4,869px!)", flush=True)

        # 5. Verify Executive Header Metrics
        dso = await page.locator("#dso-value").inner_text()
        pending = await page.locator("#pending-value").inner_text()
        fraud = await page.locator("#fraud-value").inner_text()
        print(f"    Executive Metrics: DSO='{dso.strip()}', Pending Reconciliations='{pending.strip()}', Alerts='{fraud.strip()}'", flush=True)

        # 6. Verify Subview 1: Action Queue
        print("[4] Verifying Subview 1: Urgent Action Queue...", flush=True)
        queue_count = await page.locator("#queue-count-badge").inner_text()
        queue_items = await page.locator("#owner-queue .queue-row").count()
        print(f"    Action queue count badge: {queue_count.strip()}, rendered queue rows: {queue_items}", flush=True)
        assert queue_items > 0, "Expected action queue items to be rendered"
        
        # Check first item text
        first_item_text = await page.locator("#owner-queue .queue-row").first.inner_text()
        print(f"    First queue action item: {first_item_text.splitlines()[0]}", flush=True)

        await page.screenshot(path="scratch/screenshots_control_verified/01_control_action_queue.png")

        # 7. Verify Subview 2: AI Autonomy & Guardrails
        print("[5] Verifying Subview 2: AI Autonomy & Guardrails...", flush=True)
        await page.click("button.control-subnav-btn[data-control-subview='autonomy']")
        await page.wait_for_timeout(1000)

        autonomy_val = await page.locator("#autonomy-mode").input_value()
        policy_enabled = await page.locator("#agent-policy-form input[name='enabled']").is_checked()
        max_bal = await page.locator("#agent-policy-form input[name='max_balance_cents']").input_value()
        print(f"    Autonomy mode: '{autonomy_val}', Agent enabled: {policy_enabled}, Max auto-draft balance: INR {max_bal}", flush=True)

        await page.screenshot(path="scratch/screenshots_control_verified/02_control_autonomy_guardrails.png")

        # 8. Verify Subview 3: Payment Links & Channels
        print("[6] Verifying Subview 3: Payment Links & Channels...", flush=True)
        await page.click("button.control-subnav-btn[data-control-subview='channels']")
        await page.wait_for_timeout(1000)

        provider_status = await page.locator("#provider-status").inner_text()
        print(f"    Provider status: {provider_status[:60]}...", flush=True)

        await page.screenshot(path="scratch/screenshots_control_verified/03_control_payment_channels.png")

        # 9. Verify Subview 4: System Audit & Technical Logs
        print("[7] Verifying Subview 4: System Audit & Technical Logs...", flush=True)
        await page.click("button.control-subnav-btn[data-control-subview='diagnostics']")
        await page.wait_for_timeout(1000)

        tasks_count = await page.locator("#agent-activity .activity-row").count()
        eval_summary = await page.locator("#evaluation-summary").inner_text()
        print(f"    Agent activity tasks rendered: {tasks_count}", flush=True)
        print(f"    Evaluation summary text: {eval_summary[:60]}...", flush=True)

        await page.screenshot(path="scratch/screenshots_control_verified/04_control_diagnostics.png")

        # 10. Verify absence of cluttered duplicate forms in main view
        print("[8] Verifying absence of cluttered legacy intake forms on Control...", flush=True)
        legacy_visible = await page.locator("#legacy-tools").is_visible()
        print(f"    Is #legacy-tools visible? {legacy_visible} (should be False)", flush=True)
        assert not legacy_visible, "Legacy tools duplicate upload forms should be hidden"

        # Check console errors
        print(f"\n[SUMMARY] Total console errors: {len(console_errors)}, Page errors: {len(page_errors)}")
        if console_errors:
            print("Console errors:", console_errors)
        if page_errors:
            print("Page errors:", page_errors)

        await browser.close()
        print("ALL LIVE CHECKS COMPLETED SUCCESSFULLY!", flush=True)

if __name__ == "__main__":
    asyncio.run(run())
