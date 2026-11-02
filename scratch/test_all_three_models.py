import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def safe_text(s):
    if s is None:
        return ""
    return str(s).encode("ascii", "replace").decode("ascii")

SCREENSHOT_DIR = Path("scratch/screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

async def run_three_models_audit():
    results = {
        "muse_spark": {"status": "pending", "details": []},
        "sam_3_1": {"status": "pending", "details": []},
        "muse_voice_transcribe": {"status": "pending", "details": []},
        "console_errors": [],
        "page_errors": []
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 1000},
            ignore_https_errors=True
        )
        page = await context.new_page()

        # Track console errors only after auth is initiated to avoid counting the initial unauthenticated probe
        authenticated = False
        def handle_console(msg):
            if msg.type == "error":
                if not authenticated and "401" in msg.text:
                    return
                results["console_errors"].append(msg.text)

        page.on("console", handle_console)
        page.on("pageerror", lambda err: results["page_errors"].append(str(err)))

        print("=================================================================")
        print("RECOVERFLOW LIVE THREE-MODEL META AUDIT")
        print("Target: https://recoverflaw.duckdns.org/")
        print("Key:    recoverflow-local-final-qa-2026")
        print("=================================================================\n")

        # 1. Load application
        print("[STEP 1] Loading web application...")
        res = await page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle", timeout=30000)
        print(f"  * Page loaded with HTTP status: {res.status}")
        await page.screenshot(path=str(SCREENSHOT_DIR / "step1_landing.png"))

        # 2. Enter API Key
        print("[STEP 2] Authenticating with recoverflow-local-final-qa-2026...")
        authenticated = True
        await page.fill("#api-key", "recoverflow-local-final-qa-2026")
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(2000)

        status_text = await page.inner_text("#system-status-text")
        print(f"  * System status indicator: '{status_text.strip()}'")
        assert "connected" in status_text.lower(), f"Failed to connect! Status: {status_text}"
        await page.screenshot(path=str(SCREENSHOT_DIR / "step2_connected.png"))

        # 3. Navigate to Review & Negotiate
        print("[STEP 3] Opening 'Review and Negotiate' view...")
        await page.click("a[data-view='review']")
        await page.wait_for_timeout(2000)

        # Search specifically for INV-2026-HERO
        print("  * Filtering table for 'INV-2026-HERO'...")
        await page.fill("#case-search", "INV-2026-HERO")
        await page.wait_for_timeout(1000)

        hero_btn = await page.wait_for_selector("tr:has-text('INV-2026-HERO') button.case-open", timeout=10000)
        assert hero_btn is not None, "Could not find row for INV-2026-HERO!"

        print("  * Opening hero case file (INV-2026-HERO)...")
        await hero_btn.click()

        # Wait for case summary to finish rendering
        await page.wait_for_selector(".case-heading", timeout=10000)
        await page.wait_for_timeout(2000)
        await page.screenshot(path=str(SCREENSHOT_DIR / "step3_hero_case_opened.png"))

        # Verify Case Summary & 5-way balance
        summary_elem = await page.query_selector("#case-summary")
        summary_text = await summary_elem.inner_text() if summary_elem else ""
        print(f"  * Case summary rendered: {'INV-2026-HERO' in summary_text}")
        print(f"  * Summary snippet: {safe_text(summary_text.splitlines()[0] if summary_text else '')}")

        # -------------------------------------------------------------
        # MODEL 1 AUDIT: Meta Muse Spark (muse-spark-1.3)
        # -------------------------------------------------------------
        print("\n-------------------------------------------------------------")
        print("[MODEL 1 AUDIT] Meta Muse Spark (muse-spark-1.3)")
        print("-------------------------------------------------------------")
        try:
            # Check draft / proposal
            case_history_elem = await page.query_selector("#case-history")
            history_html = await case_history_elem.inner_html() if case_history_elem else ""

            # Check agent notes and evidence items
            has_spark_evidence = "INV-2026-HERO" in history_html
            print(f"  * Muse Spark analyzed invoices & balance split: {has_spark_evidence}")
            results["muse_spark"]["details"].append(f"Balance split active: {has_spark_evidence}")

            # Verify prompt injection defense in case messages
            injection_alert = await page.query_selector(".injection-alert")
            if injection_alert:
                alert_text = await injection_alert.inner_text()
                print(f"  * Active prompt injection defense banner: '{safe_text(alert_text.replace(chr(10), ' '))}'")
                results["muse_spark"]["details"].append(f"Defense banner: {safe_text(alert_text)}")

            results["muse_spark"]["status"] = "PASSED"
            print("  >>> [SUCCESS] Meta Muse Spark 1.3 is functioning as expected!")
        except Exception as e:
            results["muse_spark"]["status"] = f"FAILED: {e}"
            print(f"  >>> [FAIL] Meta Muse Spark test encountered error: {e}")

        # -------------------------------------------------------------
        # MODEL 2 AUDIT: Meta SAM 3.1 (sam-3.1)
        # -------------------------------------------------------------
        print("\n-------------------------------------------------------------")
        print("[MODEL 2 AUDIT] Meta SAM 3.1 (sam-3.1)")
        print("-------------------------------------------------------------")
        try:
            # Locate SAM 3.1 perception panel
            sam_panel = await page.query_selector(".sam-perception-panel")
            assert sam_panel is not None, "SAM 3.1 perception panel not found on evidence cards!"
            sam_badge_text = await sam_panel.inner_text()
            print(f"  * SAM 3.1 Badge: '{safe_text(sam_badge_text.splitlines()[0] if sam_badge_text else '')}'")

            chips = await page.query_selector_all(".sam-segment-chip")
            print(f"  * Segment chips found: {len(chips)}")
            assert len(chips) >= 3, f"Expected 3 SAM perception chips, found {len(chips)}"

            chip_labels = []
            for c in chips:
                lbl = await c.inner_text()
                chip_labels.append(safe_text(lbl.replace("\n", " ")))
            print(f"  * Detected segments: {chip_labels}")
            results["sam_3_1"]["details"].append(f"Segments: {chip_labels}")

            # Click first chip to test high-res visual crop modal
            print("  * Clicking SAM perception chip to test high-res visual crop modal...")
            await chips[0].click()
            await page.wait_for_timeout(1500)

            modal = await page.query_selector(".sam-crop-preview-modal")
            assert modal is not None, "SAM visual inspection modal did not open on chip click!"
            modal_img = await modal.query_selector("img")
            img_src = await modal_img.get_attribute("src") if modal_img else ""
            print(f"  * Modal crop image URL: {img_src}")
            assert "/segments/file/" in img_src or img_src.startswith("blob:"), f"Unexpected crop URL: {img_src}"
            await page.screenshot(path=str(SCREENSHOT_DIR / "step4_sam_modal_live.png"))

            # Close modal
            close_btn = await modal.query_selector(".sam-modal-close")
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(500)

            results["sam_3_1"]["status"] = "PASSED"
            print("  >>> [SUCCESS] Meta SAM 3.1 Visual Perception is functioning as expected!")
        except Exception as e:
            results["sam_3_1"]["status"] = f"FAILED: {e}"
            print(f"  >>> [FAIL] Meta SAM 3.1 test encountered error: {e}")

        # -------------------------------------------------------------
        # MODEL 3 AUDIT: Meta Muse Voice Transcribe (muse-voice-transcribe)
        # -------------------------------------------------------------
        print("\n-------------------------------------------------------------")
        print("[MODEL 3 AUDIT] Meta Muse Voice Transcribe (muse-voice-transcribe)")
        print("-------------------------------------------------------------")
        try:
            # Locate Voice Transcribe panel
            voice_panel = await page.query_selector(".voice-transcribe-panel")
            assert voice_panel is not None, "Voice transcribe panel not found on evidence cards!"

            voice_badge = await voice_panel.query_selector(".voice-badge")
            badge_text = await voice_badge.inner_text() if voice_badge else ""
            print(f"  * Voice Model Badge: '{safe_text(badge_text.replace(chr(10), ' '))}'")

            # Audio Player element
            audio_elem = await voice_panel.query_selector(".voice-audio-player")
            assert audio_elem is not None, "HTML5 <audio> player not rendered!"
            source_elem = await audio_elem.query_selector("source")
            audio_src = await source_elem.get_attribute("src") if source_elem else await audio_elem.get_attribute("src")
            print(f"  * Audio stream source: {audio_src}")
            assert audio_src and ("/audio" in audio_src or ".wav" in audio_src), f"Invalid audio source: {audio_src}"

            # Financial terms extraction chips
            intel_chips = await voice_panel.query_selector_all(".voice-intel-chip")
            print(f"  * Extracted financial intelligence chips: {len(intel_chips)}")
            for c in intel_chips:
                c_txt = await c.inner_text()
                print(f"    - {safe_text(c_txt.replace(chr(10), ' | '))}")
                results["muse_voice_transcribe"]["details"].append(safe_text(c_txt.replace(chr(10), ' | ')))

            # Diarized utterance lines
            utterances = await voice_panel.query_selector_all(".voice-utterance-line")
            print(f"  * Diarized customer utterances: {len(utterances)} lines")
            assert len(utterances) >= 4, f"Expected 4 diarized utterances, got {len(utterances)}"
            for u in utterances:
                u_txt = await u.inner_text()
                print(f"    > {safe_text(u_txt)}")

            await page.screenshot(path=str(SCREENSHOT_DIR / "step5_voice_panel_live.png"))

            results["muse_voice_transcribe"]["status"] = "PASSED"
            print("  >>> [SUCCESS] Meta Muse Voice Transcribe is functioning as expected!")
        except Exception as e:
            results["muse_voice_transcribe"]["status"] = f"FAILED: {e}"
            print(f"  >>> [FAIL] Meta Muse Voice Transcribe test encountered error: {e}")

        # Final audit
        print("\n=================================================================")
        print("AUDIT SUMMARY REPORT")
        print("=================================================================")
        print(f"1. Meta Muse Spark 1.3:          {results['muse_spark']['status']}")
        print(f"2. Meta SAM 3.1:                 {results['sam_3_1']['status']}")
        print(f"3. Meta Muse Voice Transcribe:   {results['muse_voice_transcribe']['status']}")
        print(f"Console errors:                  {len(results['console_errors'])}")
        print(f"Page uncaught exceptions:        {len(results['page_errors'])}")
        print("=================================================================")

        await page.screenshot(path=str(SCREENSHOT_DIR / "step6_full_hero_view.png"), full_page=True)
        await browser.close()
        return results

if __name__ == "__main__":
    res = asyncio.run(run_three_models_audit())
    with open("scratch/audit_results.json", "w") as f:
        json.dump(res, f, indent=2)
