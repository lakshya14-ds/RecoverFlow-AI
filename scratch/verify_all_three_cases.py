import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path("scratch/screenshots_sam_update")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

async def verify_all():
    errors = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1050})
        page = await context.new_page()

        page.on("pageerror", lambda err: errors.append(f"PAGEERROR: {err}"))
        page.on("console", lambda msg: errors.append(f"CONSOLE {msg.type}: {msg.text}") if msg.type == "error" else None)

        print("1. Opening https://recoverflaw.duckdns.org/...")
        await page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle", timeout=30000)
        await page.fill("#api-key", "recoverflow-local-final-qa-2026")
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(1500)

        print("2. Navigating to Review and Negotiate...")
        await page.click("a[data-view='review']")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "1_bills_list.png"))

        # Check RF-SAMPLE-2026-001
        print("3. Checking RF-SAMPLE-2026-001...")
        await page.click("tr:has-text('RF-SAMPLE-2026-001') button.case-open")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollBy(0, 480)")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "2_rf_sample_segments.png"))

        # Click modal
        chip = page.locator(".sam-segment-chip:has-text('Warehouse Receiving Notes')").first
        if await chip.is_visible():
            await chip.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "3_rf_sample_modal.png"))
            await page.click(".sam-close-btn")
            await page.wait_for_timeout(500)

        # Back to bills
        await page.click("#case-back-btn")
        await page.wait_for_timeout(1000)

        # Check INV-2026-HERO
        print("4. Checking INV-2026-HERO...")
        await page.click("tr:has-text('INV-2026-HERO') button.case-open")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "4_hero_segments_and_voice.png"))

        # Click Hero Delivery Challan stamp modal
        chip_hero = page.locator(".sam-segment-chip:has-text('Receiver Stamp')").first
        if await chip_hero.is_visible():
            await chip_hero.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "5_hero_stamp_modal.png"))
            await page.click(".sam-close-btn")
            await page.wait_for_timeout(500)

        await browser.close()
        print("Verification completed successfully!")
        if errors:
            print("Errors logged:")
            for e in errors:
                print("  ", e)
        else:
            print("Zero console errors or page exceptions!")

if __name__ == "__main__":
    asyncio.run(verify_all())
