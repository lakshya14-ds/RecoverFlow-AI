import os
from playwright.sync_api import sync_playwright

os.makedirs('docs/images', exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    
    # 1. Capture clean unauthenticated login modal
    print("Capturing 01_business_signin_modal.png...")
    page.goto('https://recoverflaw.duckdns.org/')
    page.wait_for_timeout(1500)
    # Screenshot the modal card cleanly
    modal = page.locator('.login-card-modal')
    if modal.is_visible():
        modal.screenshot(path='docs/images/01_business_signin_modal.png')
    
    # Click 1-click business login
    demo_btn = page.locator('#demo-login-btn')
    if demo_btn.is_visible():
        demo_btn.click()
        page.wait_for_timeout(1500)
    
    # 2. Navigate to Review and Negotiate and open hero case
    print("Capturing 02_financial_waterfall_and_briefing.png...")
    page.click('a[data-view="review"]')
    page.wait_for_timeout(1000)
    # Open hero case if closed
    hero_btn = page.locator('button.open-case-btn[data-case-id="28"]')
    if hero_btn.is_visible():
        hero_btn.click()
        page.wait_for_timeout(1000)
    
    page.screenshot(path='docs/images/02_financial_waterfall_and_briefing.png')
    
    # 3. Switch to Verified Evidence tab (Meta SAM 3.1 & Muse Voice)
    print("Capturing 03_multimodal_evidence_perception.png...")
    ev_tab = page.locator('button.case-subtab-btn[data-case-tab="evidence"]')
    if ev_tab.is_visible():
        ev_tab.click()
        page.wait_for_timeout(1000)
    page.screenshot(path='docs/images/03_multimodal_evidence_perception.png')
    
    # 4. Switch to Negotiation & AI Co-pilot tab
    print("Capturing 04_negotiation_copilot_and_approval.png...")
    neg_tab = page.locator('button.case-subtab-btn[data-case-tab="negotiation"]')
    if neg_tab.is_visible():
        neg_tab.click()
        page.wait_for_timeout(1000)
    page.screenshot(path='docs/images/04_negotiation_copilot_and_approval.png')
    
    # 5. Switch to Control Center
    print("Capturing 05_business_owner_control_center.png...")
    page.click('a[data-view="control"]')
    page.wait_for_timeout(1000)
    page.screenshot(path='docs/images/05_business_owner_control_center.png')
    
    browser.close()
    print("All live screenshots captured into docs/images/ successfully!")

