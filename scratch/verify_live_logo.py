from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    page.goto('https://recoverflaw.duckdns.org/')
    page.wait_for_timeout(1500)

    # 1. Screenshot live login modal
    modal = page.locator('.login-card-modal')
    if modal.is_visible():
        modal.screenshot(path='scratch/screenshots_sidebar/live_modal_logo.png')
        print('Captured live modal logo screenshot!')

    # 2. Click instant access
    demo_btn = page.locator('#demo-login-btn')
    if demo_btn.is_visible():
        demo_btn.click()
        page.wait_for_timeout(1000)

    # 3. Screenshot live sidebar
    sidebar = page.locator('.sidebar')
    sidebar.screenshot(path='scratch/screenshots_sidebar/live_sidebar_new_logo.png')
    print('Captured live sidebar logo screenshot!')

    browser.close()

