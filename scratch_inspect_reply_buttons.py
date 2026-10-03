import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import pipeline_runner as pr

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        channel="chrome",
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
    )
    ctx = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
    page = ctx.new_page()

    page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
    pr.ensure_turnstile_cleared(page)

    thread_url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0373/forum/6f22ac70-2e1d-4095-8b94-2aeec67b8f25/topics/79998260-49bf-468d-b85e-c11e6f04beac"
    print("Navigating to thread...")
    page.goto(thread_url, wait_until="domcontentloaded")
    pr.ensure_turnstile_cleared(page)
    page.wait_for_timeout(3000)

    reply_btns = page.locator("button:has-text('REPLY')").all()
    print("Found reply buttons:", len(reply_btns))
    reply_btns[0].scroll_into_view_if_needed()
    reply_btns[0].click()
    page.wait_for_timeout(2000)

    # Find the visible textarea
    ta = page.locator("textarea:visible").first
    print("Visible textarea count:", page.locator("textarea:visible").count())

    # Find all visible buttons
    vis_btns = [b.inner_text().strip() for b in page.locator("button:visible").all()]
    print("Visible buttons on page:", vis_btns)

    # Inspect parent container of the visible textarea
    parent_box = ta.locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root') or contains(@class, 'MuiBox-root')][1]")
    if parent_box.count() > 0:
        near_btns = [b.inner_text().strip() for b in parent_box.locator("button:visible").all()]
        print("Buttons inside parent box:", near_btns)
        # Check all child elements of parent box
        btn_els = parent_box.locator("button").all()
        for idx, be in enumerate(btn_els):
            print(f"  btn {idx+1}: text='{be.inner_text().strip()}', type={be.get_attribute('type')}, class={be.get_attribute('class')}")

    browser.close()
