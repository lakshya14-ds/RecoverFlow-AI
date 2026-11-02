from playwright.sync_api import sync_playwright
import os

os.makedirs('scratch/screenshots_sidebar', exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    # open local file or test directly
    page = browser.new_page(viewport={'width': 1280, 'height': 800})
    file_url = 'file:///' + os.path.abspath('frontend/index.html').replace('\\', '/')
    page.goto(file_url)
    page.wait_for_timeout(1000)

    # Take screenshot of the sidebar
    sidebar = page.locator('.sidebar')
    sidebar.screenshot(path='scratch/screenshots_sidebar/sidebar_rendered.png')
    print('Sidebar screenshot captured at scratch/screenshots_sidebar/sidebar_rendered.png')
    browser.close()

