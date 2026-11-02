import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

OUT = Path("scratch/screenshots_verified")
OUT.mkdir(parents=True, exist_ok=True)

async def verify_live():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        # Use a fresh context with cache disabled to simulate a completely new user
        context = await browser.new_context(
            viewport={"width": 1440, "height": 950},
            ignore_https_errors=True
        )
        page = await context.new_page()

        print("1. Loading live site...")
        await page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle")
        await page.fill("#api-key", "recoverflow-local-final-qa-2026")
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(1000)

        print("2. Clicking 'Review and Negotiate'...")
        await page.click(".nav-item[data-view='review']")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT / "live_1_review_subnav.png"))

        print("3. Opening hero case INV-2026-HERO...")
        await page.fill("#case-search", "INV-2026-HERO")
        await page.wait_for_timeout(1000)
        await page.click("tr:has-text('INV-2026-HERO') button.case-open")
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(OUT / "live_2_case_waterfall_and_brief.png"))

        print("4. Inspecting Tab 1 Evidence (scroll down)...")
        await page.evaluate("window.scrollBy(0, 500)")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT / "live_3_case_evidence_tab.png"))

        print("5. Clicking Tab 2 (Negotiation & AI Co-pilot)...")
        await page.click("#tab-btn-negotiation")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT / "live_4_case_negotiation_tab.png"))

        print("6. Clicking Tab 3 (Ledger Actions & Audit Trail)...")
        await page.click("#tab-btn-actions")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=str(OUT / "live_5_case_actions_tab.png"))

        await browser.close()
        print("Live verification complete! All screenshots saved in scratch/screenshots_verified/")

if __name__ == "__main__":
    asyncio.run(verify_live())

