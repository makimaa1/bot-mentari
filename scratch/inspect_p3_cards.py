import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
from pathlib import Path
import json

AUTH_PATH = Path("data/auth.json").resolve()

def inspect_p3_cards():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Open Pertemuan 3
        p3 = page.locator('text=/^\\s*Pertemuan\\s+3\\b/i').first
        if p3.count() > 0:
            p3.scroll_into_view_if_needed()
            p3.click()
            page.wait_for_timeout(2500)

        cards = page.locator('.MuiPaper-root:not(:has-text("Course Index"))').all()
        print(f"Total cards in P3: {len(cards)}")
        for idx, c in enumerate(cards):
            txt = c.inner_text().strip()
            lines = [l.strip() for l in txt.splitlines() if l.strip()]
            first_l = lines[0] if lines else ""
            btns = [b.inner_text().strip() for b in c.locator("button, a").all() if b.is_visible() and b.inner_text().strip()]
            print(f"[{idx}] Title: '{first_l}' | Buttons: {btns}")
            if len(lines) > 1:
                print(f"    Snippet: {lines[1:3]}")

        browser.close()

if __name__ == "__main__":
    inspect_p3_cards()
