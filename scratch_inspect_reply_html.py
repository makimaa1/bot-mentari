from playwright.sync_api import sync_playwright
import pipeline_runner as pr

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel='chrome', args=['--start-maximized', '--disable-blink-features=AutomationControlled'])
    ctx = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
    page = ctx.new_page()
    page.goto('https://mentari.unpam.ac.id', wait_until='domcontentloaded')
    pr.ensure_turnstile_cleared(page)

    thread_url = 'https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0373/forum/6f22ac70-2e1d-4095-8b94-2aeec67b8f25/topics/79998260-49bf-468d-b85e-c11e6f04beac'
    page.goto(thread_url, wait_until='domcontentloaded')
    pr.ensure_turnstile_cleared(page)
    page.wait_for_timeout(3000)

    # First check what the original button on the lecturer post is
    print('Lecturer section reply button before clicking:')
    reply_btn_0 = page.locator("button:has-text('REPLY')").first
    print('Outer HTML:', reply_btn_0.evaluate('el => el.outerHTML'))

    # Click it
    reply_btn_0.click()
    page.wait_for_timeout(1500)

    # Now inspect parent of textarea:visible
    ta = page.locator('textarea:visible').first
    parent = ta.locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root') or contains(@class, 'MuiBox-root')][1]")
    print('Parent outer HTML:')
    print(parent.evaluate('el => el.outerHTML'))

    browser.close()
