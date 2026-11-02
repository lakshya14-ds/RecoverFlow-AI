import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("scratch/screenshots_sam_update")

async def test_case_10():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1050})
        page = await context.new_page()

        print("1. Opening https://recoverflaw.duckdns.org/...")
        await page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle", timeout=30000)
        await page.fill("#api-key", "recoverflow-local-final-qa-2026")
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(1500)

        print("2. Navigating to Review and Negotiate...")
        await page.click("a[data-view='review']")
        await page.wait_for_timeout(1500)

        print("3. Opening INV-AUDIT-CSV-1...")
        await page.click("tr:has-text('INV-AUDIT-CSV-1') button.case-open")
        await page.wait_for_timeout(2000)

        # Scroll to evidence card
        await page.evaluate("window.scrollBy(0, 520)")
        await page.wait_for_timeout(1000)

        # Capture button view
        await page.screenshot(path=str(OUTPUT_DIR / "case10_extract_button.png"))
        print("Captured case10_extract_button.png")

        # Now click the button on Case 10!
        print("4. Clicking 'Extract Visual Proof & Stamps' on Case 10...")
        btn = page.locator(".run-sam-btn[data-evidence-id='46']")
        await btn.click()

        # Wait for segmentation to complete
        await page.wait_for_selector(".sam-perception-panel", timeout=25000)
        await page.wait_for_timeout(2000)

        # Capture segmented view
        await page.screenshot(path=str(OUTPUT_DIR / "case10_segments_extracted.png"))
        print("Captured case10_segments_extracted.png")

        await browser.close()
        print("Case 10 test complete!")

if __name__ == "__main__":
    asyncio.run(test_case_10())

