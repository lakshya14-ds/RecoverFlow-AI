import os
import sys
from playwright.sync_api import sync_playwright

os.makedirs("scratch/screenshots_control", exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    
    print("Navigating to https://recoverflaw.duckdns.org/ ...", flush=True)
    page.goto("https://recoverflaw.duckdns.org/", wait_until="networkidle")
    
    # Enter API key
    api_key_input = page.locator("#api-key")
    if api_key_input.is_visible():
        print("Entering API key...", flush=True)
        page.fill("#api-key", "recoverflow-local-final-qa-2026")
        page.click("#auth-form button[type='submit']")
        page.wait_for_timeout(2000)
    
    # Click Control tab
    print("Clicking Control nav item...", flush=True)
    page.click("a.nav-item[data-view='control']")
    page.wait_for_timeout(2500)
    
    # Screenshot full page
    page.screenshot(path="scratch/screenshots_control/03_control_full.png", full_page=True)
    
    # Get HTML content of view-control
    control_html = page.locator("#view-control").inner_html()
    with open("scratch/control_rendered.html", "w", encoding="utf-8") as f:
        f.write(control_html)
        
    print("Captured control page. Length of rendered HTML:", len(control_html), flush=True)
    
    # Check all panels/cards inside #view-control
    cards = page.locator("#view-control > div, #view-control > .paper-panel, #view-control .card").all()
    print(f"Found {len(cards)} cards/panels in #view-control:", flush=True)
    for i, c in enumerate(cards):
        header = c.locator("h3, h4").first.text_content() if c.locator("h3, h4").count() > 0 else "No header"
        print(f" Card {i+1}: {header.strip()}", flush=True)
        
    browser.close()
    print("Done!", flush=True)
