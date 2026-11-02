import asyncio
import os
from playwright.async_api import async_playwright

os.makedirs("scratch/screenshots_login_verified", exist_ok=True)

async def run():
    print("Starting automated test of Option 1 Business Sign-In on https://recoverflaw.duckdns.org/ ...", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Create fresh context with empty session storage
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page_errors = []
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # [STEP 1] Fresh visit without session
        print("\n[STEP 1] Visiting https://recoverflaw.duckdns.org/ with clean session...", flush=True)
        await page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle")
        await page.wait_for_timeout(1500)

        modal_visible = await page.locator("#login-modal").is_visible()
        unauth_pill_visible = await page.locator("#unauth-header-pill").is_visible()
        print(f"  * Is login modal visible? {modal_visible} (expected True)")
        print(f"  * Is unauth header pill visible? {unauth_pill_visible} (expected True)")
        assert modal_visible, "Login modal should be visible on clean visit"

        await page.screenshot(path="scratch/screenshots_login_verified/01_unauthenticated_modal_shown.png")

        # [STEP 2] Test 1-Click Business Owner Demo Sign-In
        print("\n[STEP 2] Clicking 'Enter as Business Owner (Apex Enterprises)'...", flush=True)
        await page.click("#demo-login-btn")
        await page.wait_for_timeout(2500)

        modal_after = await page.locator("#login-modal").is_visible()
        auth_pill_visible = await page.locator("#auth-header-pill").is_visible()
        user_text = await page.locator("#auth-header-pill").inner_text()
        print(f"  * Is login modal hidden now? {not modal_after} (expected True)")
        print(f"  * Is auth profile pill visible? {auth_pill_visible} (expected True)")
        print(f"  * Header user profile text: '{user_text.encode('ascii', 'ignore').decode('ascii').replace(chr(10), ' | ')}'")
        assert not modal_after, "Login modal should be hidden after 1-click login"
        assert auth_pill_visible, "Auth header pill should be visible"

        await page.screenshot(path="scratch/screenshots_login_verified/02_signed_in_dashboard.png")

        # [STEP 3] Check workbench data access
        print("\n[STEP 3] Checking case data in Review and Negotiate...", flush=True)
        await page.click("a.nav-item[data-view='review']")
        await page.wait_for_timeout(2000)
        cases_count = await page.locator("#case-list .case-open").count()
        print(f"  * Number of active case rows loaded: {cases_count}")
        assert cases_count > 0, "Cases should be loaded in Review and Negotiate"

        # [STEP 4] Test Sign Out
        print("\n[STEP 4] Clicking 'Sign Out' in header...", flush=True)
        await page.click("#header-logout-btn")
        await page.wait_for_timeout(2000)

        modal_reopened = await page.locator("#login-modal").is_visible()
        print(f"  * Did login modal reappear after sign out? {modal_reopened} (expected True)")
        assert modal_reopened, "Login modal should reopen after logout"

        await page.screenshot(path="scratch/screenshots_login_verified/03_logged_out_modal_reopened.png")

        # [STEP 5] Test Credentials Form Sign-In
        print("\n[STEP 5] Testing credentials sign in form (owner@apexdistributors.in)...", flush=True)
        await page.click("#credentials-submit-btn")
        await page.wait_for_timeout(2500)

        modal_after_cred = await page.locator("#login-modal").is_visible()
        auth_pill_cred = await page.locator("#auth-header-pill").is_visible()
        print(f"  * Is modal hidden after credentials login? {not modal_after_cred} (expected True)")
        print(f"  * Is auth profile pill visible? {auth_pill_cred} (expected True)")
        assert not modal_after_cred, "Modal should close after credentials login"
        assert auth_pill_cred, "Auth pill should be visible"

        await page.screenshot(path="scratch/screenshots_login_verified/04_credentials_login_success.png")

        # [STEP 6] Check console errors
        print(f"\n[SUMMARY] Total console errors: {len(console_errors)}, Page errors: {len(page_errors)}")
        if console_errors:
            print("Console errors:", console_errors)
        if page_errors:
            print("Page errors:", page_errors)
        assert len(console_errors) == 0, f"Expected 0 console errors, got {len(console_errors)}"
        assert len(page_errors) == 0, f"Expected 0 page errors, got {len(page_errors)}"

        await browser.close()
        print("\nALL OPTION 1 AUTOMATED TESTS PASSED WITH 100% SUCCESS!", flush=True)

if __name__ == "__main__":
    asyncio.run(run())
