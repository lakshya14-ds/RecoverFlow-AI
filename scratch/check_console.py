import asyncio
from playwright.async_api import async_playwright

async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True)
        page = await browser.new_page()
        page.on('console', lambda msg: print('CONSOLE:', msg.type, msg.text))
        page.on('pageerror', lambda err: print('PAGEERROR:', err))
        await page.goto('https://recoverflaw.duckdns.org/', wait_until='networkidle')
        await page.fill('#api-key', 'recoverflow-local-final-qa-2026')
        await page.click("#auth-form button[type='submit']")
        await page.wait_for_timeout(1000)
        print('Clicking review...')
        await page.click(".nav-item[data-view='review']")
        await page.wait_for_timeout(2000)
        active_nav = await page.eval_on_selector('.nav-item.active', 'el => el.textContent')
        print('Current active nav:', active_nav)
        
        # Check subview-cases visibility
        subview_cases = await page.query_selector('#subview-cases')
        if subview_cases:
            cls = await subview_cases.get_attribute('class')
            print('#subview-cases class:', cls)
        else:
            print('#subview-cases NOT FOUND in DOM!')

        # Check view-cases
        view_cases = await page.query_selector('#view-cases')
        if view_cases:
            cls = await view_cases.get_attribute('class')
            print('#view-cases class:', cls)
        
        # Check #case-search
        cs = await page.query_selector('#case-search')
        if cs:
            is_vis = await cs.is_visible()
            print('#case-search is_visible:', is_vis)
        else:
            print('#case-search NOT FOUND in DOM!')

        await browser.close()

if __name__ == '__main__':
    asyncio.run(check())

