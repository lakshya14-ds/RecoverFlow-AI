from playwright.sync_api import sync_playwright
import os

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    page.goto('https://recoverflaw.duckdns.org/')
    page.wait_for_timeout(2000)

    # Click demo access if modal is up
    demo_btn = page.locator('#demo-login-btn')
    if demo_btn.is_visible():
        demo_btn.click()
        page.wait_for_timeout(1000)

    sidebar = page.locator('.sidebar')
    sidebar.screenshot(path='scratch/screenshots_sidebar/live_sidebar_verified.png')
    print('Live sidebar screenshot captured!')
    browser.close()

