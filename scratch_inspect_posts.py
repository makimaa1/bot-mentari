from playwright.sync_api import sync_playwright
import pipeline_runner as pr

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel="chrome", args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
    page = ctx.new_page()
    page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
    pr.ensure_turnstile_cleared(page)

    thread_url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0373/forum/6f22ac70-2e1d-4095-8b94-2aeec67b8f25/topics/79998260-49bf-468d-b85e-c11e6f04beac"
    page.goto(thread_url, wait_until="domcontentloaded")
    pr.ensure_turnstile_cleared(page)
    page.wait_for_timeout(3000)

    # Let's inspect the cards/containers on the page
    cards = page.locator(".MuiCard-root, .MuiPaper-root").all()
    print(f"Total cards/papers: {len(cards)}")

    # Let's find all posts
    reply_icons = page.locator("button:has(svg[data-testid='ReplyIcon'])").all()
    print(f"Total Reply buttons with ReplyIcon: {len(reply_icons)}")

    # Check the first 5 reply buttons and their container headers/authors
    for idx, r_btn in enumerate(reply_icons[:6]):
        # Find the post card containing this button
        post_card = r_btn.locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root')][1]")
        txt = post_card.inner_text().strip() if post_card.count() > 0 else "NO_CARD"
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        header = " | ".join(lines[:4])
        print(f"Post #{idx}: {header}")

    browser.close()
