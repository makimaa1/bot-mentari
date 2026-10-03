import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
from pathlib import Path
import re
import time

AUTH_PATH = Path("data/auth.json").resolve()

def inspect_p3():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        print("[*] Opening Mentari Dashboard...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
        for _ in range(15):
            title = page.title()
            if "Just a moment" not in title and title:
                break
            time.sleep(1)

        url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312"
        print(f"[*] Navigating to {url}...")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Click Pertemuan 3
        p3 = page.locator('text=/^\\s*Pertemuan\\s+3\\b/i').first
        print(f"[*] Pertemuan 3 header count: {p3.count()}")
        if p3.count() > 0:
            p3.scroll_into_view_if_needed()
            p3.click()
            page.wait_for_timeout(2500)

        cards = page.locator('.MuiPaper-root').all()
        print(f"[*] Total cards: {len(cards)}")
        for idx, c in enumerate(cards):
            txt = c.inner_text().strip()
            first_l = txt.splitlines()[0] if txt else ""
            if "pretest" in first_l.lower():
                print(f"[V] Card {idx}: {first_l}")
                q_btn = c.locator('button:has-text("QUIZ")').first
                if q_btn.count() > 0:
                    print("[*] Clicking QUIZ button...")
                    q_btn.click()
                    page.wait_for_timeout(4000)
                    print(f"[*] Current URL: {page.url}")

                    body = page.locator("body").inner_text()
                    print("\n=== FULL BODY TEXT OF QUIZ PAGE ===")
                    print(body)
                    print("=" * 60)

                    score_match = re.search(r'(?:nilai|skor|grade|score)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', body, re.IGNORECASE)
                    print(f"[*] Regex score_match: {score_match.groups() if score_match else None}")
                    if score_match:
                        print(f"[*] Full match: '{score_match.group(0)}'")
                    print(f"[*] 'sudah mengerjakan quiz' in body: {'sudah mengerjakan quiz' in body.lower()}")

                    # Check for buttons on this quiz page
                    all_btns = [b.inner_text().strip() for b in page.locator("button, a").all() if b.is_visible()]
                    print(f"[*] Visible buttons on quiz page: {all_btns}")
                    break

        browser.close()

if __name__ == "__main__":
    inspect_p3()
