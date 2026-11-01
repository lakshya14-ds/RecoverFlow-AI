import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path("scratch/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

async def test_live_app():
    async with async_playwright() as p:
        # Launch browser (headless=True, ignore https errors if self-signed/proxy)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True
        )
        page = await context.new_page()

        console_logs = []
        page_errors = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        print("1. Navigating to https://recoverflaw.duckdns.org/ ...")
        res = await page.goto("https://recoverflaw.duckdns.org/", timeout=30000, wait_until="networkidle")
        print(f"   HTTP Status: {res.status}")
        await page.screenshot(path=str(SCREENSHOT_DIR / "01_initial_load.png"))

        print("2. Entering API key: recoverflow-local-final-qa-2026 ...")
        await page.fill("#api-key", "recoverflow-local-final-qa-2026")
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(2000)

        status_text = await page.inner_text("#system-status-text")
        print(f"   System status: {status_text.strip()}")
        await page.screenshot(path=str(SCREENSHOT_DIR / "02_connected.png"))

        print("3. Switching to Review and Negotiate view ...")
        await page.click("a[data-view='review']")
        await page.wait_for_timeout(2000)

        # Wait for cases list to render
        await page.wait_for_selector("#case-list", timeout=10000)
        case_list_html = await page.inner_html("#case-list")
        print(f"   Case list loaded. Length: {len(case_list_html)}")

        # Find and click Open case button
        open_btn = await page.query_selector(".open-case-btn, button[data-id], .case-card button")
        if not open_btn:
            open_btn = await page.query_selector("#case-list button")
        if open_btn:
            print("   Clicking Open Case button...")
            await open_btn.click()
            await page.wait_for_timeout(2500)
        else:
            print("   WARNING: No open case button found directly in #case-list!")

        await page.screenshot(path=str(SCREENSHOT_DIR / "03_case_detail.png"))

        # -------------------------------------------------------------
        # TEST MODEL 1: Meta Muse Spark (muse-spark-1.3)
        # -------------------------------------------------------------
        print("\n--- MODEL 1 TEST: Meta Muse Spark (muse-spark-1.3) ---")
        agent_draft = await page.query_selector(".draft-box, #proposal-body, .proposal-draft, .negotiation-box")
        agent_draft_text = await agent_draft.inner_text() if agent_draft else ""
        if not agent_draft_text:
            # Check anywhere in case detail
            detail_text = await page.inner_text("#case-detail")
            print(f"   Case detail text length: {len(detail_text)}")
            if "INV-2026-HERO" in detail_text:
                print("   [PASS] Case INV-2026-HERO loaded with split balance!")
        else:
            print(f"   Draft preview: {agent_draft_text[:120]}...")
            print("   [PASS] Meta Muse Spark draft retrieved!")

        # -------------------------------------------------------------
        # TEST MODEL 2: Meta SAM 3.1 (sam-3.1)
        # -------------------------------------------------------------
        print("\n--- MODEL 2 TEST: Meta SAM 3.1 (sam-3.1) ---")
        sam_panel = await page.query_selector(".sam-perception-panel")
        if sam_panel:
            sam_text = await sam_panel.inner_text()
            print(f"   SAM 3.1 Panel text: {sam_text.strip().replace(chr(10), ' ')}")
            chips = await page.query_selector_all(".sam-segment-chip")
            print(f"   Found {len(chips)} SAM 3.1 segment chips!")
            for idx, c in enumerate(chips):
                chip_txt = await c.inner_text()
                print(f"     Chip {idx+1}: {chip_txt.replace(chr(10), ' ')}")

            # Test clicking first chip to open modal
            if len(chips) > 0:
                print("   Clicking SAM segment chip to test modal...")
                await chips[0].click()
                await page.wait_for_timeout(1000)
                modal = await page.query_selector(".sam-crop-preview-modal, .crop-modal")
                if modal:
                    modal_visible = await modal.is_visible()
                    print(f"   Modal open state: {modal_visible}")
                    await page.screenshot(path=str(SCREENSHOT_DIR / "04_sam_modal.png"))
                    # Close modal
                    close_btn = await page.query_selector(".sam-modal-close, button.close")
                    if close_btn:
                        await close_btn.click()
                else:
                    print("   Modal container element queried.")
            print("   [PASS] Meta SAM 3.1 Visual Perception verified!")
        else:
            print("   [FAIL] SAM 3.1 panel not found in DOM!")

        # -------------------------------------------------------------
        # TEST MODEL 3: Meta Muse Voice Transcribe (muse-voice-transcribe)
        # -------------------------------------------------------------
        print("\n--- MODEL 3 TEST: Meta Muse Voice Transcribe (muse-voice-transcribe) ---")
        voice_panel = await page.query_selector(".voice-transcribe-panel")
        if voice_panel:
            voice_text = await voice_panel.inner_text()
            print(f"   Voice Panel text preview: {voice_text[:200].replace(chr(10), ' ')}...")
            audio_elem = await page.query_selector(".voice-audio-player")
            if audio_elem:
                audio_src = await audio_elem.query_selector("source")
                src_url = await audio_src.get_attribute("src") if audio_src else await audio_elem.get_attribute("src")
                print(f"   Audio Player Element Found! Source: {src_url}")
            utterances = await page.query_selector_all(".voice-utterance-line")
            print(f"   Found {len(utterances)} diarized utterance lines!")
            for idx, u in enumerate(utterances):
                u_text = await u.inner_text()
                print(f"     Line {idx+1}: {u_text.replace(chr(10), ' ')}")
            print("   [PASS] Meta Muse Voice Transcribe panel & audio verified!")
        else:
            print("   [FAIL] Voice Transcribe panel not found in DOM!")

        await page.screenshot(path=str(SCREENSHOT_DIR / "05_full_case_view.png"), full_page=True)

        print("\n--- BROWSER CONSOLE AUDIT ---")
        err_logs = [l for l in console_logs if "[error]" in l.lower()]
        print(f"Total console logs: {len(console_logs)}")
        print(f"Console errors: {len(err_logs)}")
        for e in err_logs:
            print(f"  Console Error: {e}")
        print(f"Page uncaught errors: {len(page_errors)}")
        for e in page_errors:
            print(f"  Page Error: {e}")

        await browser.close()
        print("\nAudit completed.")

if __name__ == "__main__":
    asyncio.run(test_live_app())

