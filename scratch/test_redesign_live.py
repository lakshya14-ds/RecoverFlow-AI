import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path("scratch/screenshots_redesign")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

async def test_and_capture_redesign():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1050})

        print("1. Loading https://recoverflaw.duckdns.org/...")
        await page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle", timeout=30000)
        await page.fill("#api-key", "recoverflow-local-final-qa-2026")
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(1500)

        print("2. Navigating to Review and Negotiate...")
        await page.click("a[data-view='review']")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(SCREENSHOT_DIR / "1_review_bills_list.png"))

        print("3. Filtering for INV-2026-HERO and opening file...")
        await page.fill("#case-search", "INV-2026-HERO")
        await page.wait_for_timeout(1000)
        await page.click("tr:has-text('INV-2026-HERO') button.case-open")
        await page.wait_for_timeout(2000)

        print("4. Capturing Executive Financial Waterfall & Brief...")
        await page.screenshot(path=str(SCREENSHOT_DIR / "2_executive_case_view.png"))

        # Scroll to Evidence cards
        print("5. Capturing Polished Evidence Cards (Tab 1)...")
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(SCREENSHOT_DIR / "3_evidence_tab.png"))

        # Click Tab 2: Negotiation
        print("6. Clicking Tab 2 (Negotiation & AI Co-pilot)...")
        await page.click("#tab-btn-negotiation")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(SCREENSHOT_DIR / "4_negotiation_tab.png"))

        # Click Tab 3: Actions
        print("7. Clicking Tab 3 (Ledger Actions & Audit Trail)...")
        await page.click("#tab-btn-actions")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(SCREENSHOT_DIR / "5_actions_tab.png"))

        # Test sub-nav: Invoices Awaiting Review
        print("8. Testing sub-nav tabs: Invoices Awaiting Review...")
        await page.click(".subnav-tab-btn[data-subview='invoices']")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(SCREENSHOT_DIR / "6_subnav_invoices.png"))

        await browser.close()
        print("All screenshots captured successfully!")

if __name__ == "__main__":
    asyncio.run(test_and_capture_redesign())

