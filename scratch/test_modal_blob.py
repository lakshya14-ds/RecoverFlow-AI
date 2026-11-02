import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path("scratch/screenshots_sam_update")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

async def test_modal():
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

        print("3. Opening RF-SAMPLE-2026-001...")
        await page.click("tr:has-text('RF-SAMPLE-2026-001') button.case-open")
        await page.wait_for_timeout(2000)

        # Scroll to evidence card
        await page.evaluate("window.scrollBy(0, 480)")
        await page.wait_for_timeout(1000)

        # Check for perception chips
        print("4. Inspecting SAM perception panel...")
        await page.screenshot(path=str(SCREENSHOTS_DIR / "panel_with_chips.png"))

        # Click on Receiver Stamp & Signature
        chip = page.locator(".sam-segment-chip:has-text('Receiver Stamp')").first
        if await chip.is_visible():
            print("5. Clicking Receiver Stamp & Signature chip...")
            await chip.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "modal_receiver_stamp_blob.png"))
            print("Captured modal_receiver_stamp_blob.png")
            await page.click(".sam-close-btn")
            await page.wait_for_timeout(500)

        # Click on Warehouse Receiving Notes
        chip2 = page.locator(".sam-segment-chip:has-text('Warehouse Receiving Notes')").first
        if await chip2.is_visible():
            print("6. Clicking Warehouse Receiving Notes chip...")
            await chip2.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "modal_receiving_notes_blob.png"))
            print("Captured modal_receiving_notes_blob.png")
            await page.click(".sam-close-btn")
            await page.wait_for_timeout(500)

        await browser.close()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(test_modal())

