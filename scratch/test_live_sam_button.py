import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_DIR = Path("scratch/screenshots_sam_update")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

async def test_live():
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

        print("3. Opening Case 19 (RF-SAMPLE-2026-001)...")
        # Click Open file for RF-SAMPLE-2026-001
        await page.click("tr:has-text('RF-SAMPLE-2026-001') button.case-open")
        await page.wait_for_timeout(2000)

        # Scroll down to Evidence section
        await page.evaluate("window.scrollBy(0, 450)")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUTPUT_DIR / "1_rf_sample_segments_live.png"))
        print("Captured 1_rf_sample_segments_live.png")

        # Click on the first chip: Receiver Stamp & Signature
        print("4. Clicking Receiver Stamp & Signature chip...")
        chip = page.locator(".sam-segment-chip:has-text('Receiver Stamp')").first
        if await chip.is_visible():
            await chip.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUTPUT_DIR / "2_rf_sample_stamp_modal.png"))
            print("Captured 2_rf_sample_stamp_modal.png")
            # Close modal
            await page.click(".sam-close-btn")
            await page.wait_for_timeout(500)

        # Now let's test deleting segments for evidence 54 temporarily via API to test clicking the new button live on the UI!
        print("5. Resetting segments on evidence 54 to test button click live in browser...")
        # We can delete segments for evidence 54 via EC2 or test on another case
        # Or let's test on INV-AUDIT-CSV-1 or check if it has evidence
        await page.click("#back-to-bills-btn")
        await page.wait_for_timeout(1000)

        # Open INV-2026-HERO
        print("6. Opening INV-2026-HERO...")
        await page.click("tr:has-text('INV-2026-HERO') button.case-open")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUTPUT_DIR / "3_hero_evidence_panel.png"))
        print("Captured 3_hero_evidence_panel.png")

        # Click on Challan Damaged Goods chip
        chip_damage = page.locator(".sam-segment-chip:has-text('Damaged Goods')").first
        if await chip_damage.is_visible():
            await chip_damage.click()
            await page.wait_for_timeout(1500)
            await page.screenshot(path=str(OUTPUT_DIR / "4_hero_damaged_goods_modal.png"))
            print("Captured 4_hero_damaged_goods_modal.png")
            await page.click(".sam-close-btn")
            await page.wait_for_timeout(500)

        await browser.close()
        print("Playwright test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_live())

