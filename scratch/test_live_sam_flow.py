import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOTS_DIR = Path("scratch/screenshots_sam_update")
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

async def run_flow():
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

        # Verify button exists with new business label
        btn = page.locator(".run-sam-btn[data-evidence-id='54']")
        btn_text = await btn.text_content()
        safe_text = btn_text.encode('ascii', 'ignore').decode('ascii').strip()
        print(f"Button found with label: '{safe_text}'")

        # Capture screenshot showing the new button
        await page.screenshot(path=str(SCREENSHOTS_DIR / "1_new_business_button.png"))
        print("Captured 1_new_business_button.png")

        # Click the button
        print("4. Clicking 'Extract Visual Proof & Stamps (Powered by Meta SAM 3.1)'...")
        await btn.click()

        # Wait for segmentation and case re-render
        print("5. Waiting for visual perception extraction...")
        await page.wait_for_selector(".sam-perception-panel", timeout=25000)
        await page.wait_for_timeout(2000)

        # Capture screenshot showing the extracted visual chips
        await page.screenshot(path=str(SCREENSHOTS_DIR / "2_visual_proof_chips.png"))
        print("Captured 2_visual_proof_chips.png")

        # Click on the first segment chip: Receiver Stamp & Signature
        print("6. Clicking on 'Receiver Stamp & Signature' chip...")
        chip = page.locator(".sam-segment-chip:has-text('Receiver Stamp')").first
        await chip.click()
        await page.wait_for_timeout(1500)

        # Capture screenshot of the modal
        await page.screenshot(path=str(SCREENSHOTS_DIR / "3_stamp_crop_modal.png"))
        print("Captured 3_stamp_crop_modal.png")

        # Close the modal
        await page.click(".sam-close-btn")
        await page.wait_for_timeout(500)

        # Click on the second chip: Warehouse Receiving Notes
        print("7. Clicking on 'Warehouse Receiving Notes' chip...")
        chip2 = page.locator(".sam-segment-chip:has-text('Warehouse Receiving Notes')").first
        await chip2.click()
        await page.wait_for_timeout(1500)

        # Capture screenshot of the notes modal
        await page.screenshot(path=str(SCREENSHOTS_DIR / "4_receiving_notes_modal.png"))
        print("Captured 4_receiving_notes_modal.png")

        await browser.close()
        print("All steps completed and verified successfully!")

if __name__ == "__main__":
    asyncio.run(run_flow())
