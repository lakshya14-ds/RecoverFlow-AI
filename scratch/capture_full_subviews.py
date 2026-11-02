import asyncio
import os
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})

        await page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle")
        await page.fill("#api-key", "recoverflow-local-final-qa-2026")
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(2000)

        await page.click("a.nav-item[data-view='control']")
        await page.wait_for_timeout(2000)

        # Tab 1: Action Queue
        await page.screenshot(path="scratch/screenshots_control_verified/full_01_queue.png", full_page=True)

        # Tab 2: Autonomy & Guardrails
        await page.click("button.control-subnav-btn[data-control-subview='autonomy']")
        await page.wait_for_timeout(1000)
        await page.screenshot(path="scratch/screenshots_control_verified/full_02_autonomy.png", full_page=True)

        # Tab 3: Channels & Payments
        await page.click("button.control-subnav-btn[data-control-subview='channels']")
        await page.wait_for_timeout(1000)
        await page.screenshot(path="scratch/screenshots_control_verified/full_03_channels.png", full_page=True)

        # Tab 4: Diagnostics
        await page.click("button.control-subnav-btn[data-control-subview='diagnostics']")
        await page.wait_for_timeout(1000)
        await page.screenshot(path="scratch/screenshots_control_verified/full_04_diagnostics.png", full_page=True)

        # Also test clicking "Open bill" on the first queue item to verify seamless navigation to Review
        await page.click("button.control-subnav-btn[data-control-subview='queue']")
        await page.wait_for_timeout(500)
        print("Clicking 'Open bill' on first queue item...")
        await page.click("#owner-queue .queue-open >> nth=0")
        await page.wait_for_timeout(2500)
        
        # Verify we navigated to Review and case details opened
        review_active = await page.locator("a.nav-item[data-view='review']").evaluate("el => el.classList.contains('active')")
        case_visible = await page.locator("#case-detail").is_visible()
        print(f"Navigated to Review: {review_active}, Case detail opened: {case_visible}")
        await page.screenshot(path="scratch/screenshots_control_verified/full_05_navigated_to_bill.png", full_page=True)

        await browser.close()
        print("Full page captures and navigation test completed!")

asyncio.run(run())

