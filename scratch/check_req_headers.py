from playwright.sync_api import sync_playwright
from pathlib import Path
import json
import time

AUTH_PATH = Path("data/auth.json").resolve()

def check_headers():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH))
        page = ctx.new_page()

        headers_captured = []
        def on_req(req):
            if "/api/quiz/peserta" in req.url:
                headers_captured.append({
                    "url": req.url,
                    "method": req.method,
                    "headers": req.headers
                })
                print("[REQ HEADERS]", json.dumps(req.headers, indent=2))

        page.on("request", on_req)
        
        print("[*] Opening Mentari...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
        for _ in range(15):
            title = page.title()
            if "Just a moment" not in title and title:
                break
            time.sleep(1)
        print("[*] Dashboard Title:", page.title())
        
        course_url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0422"
        page.goto(course_url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        # Click Pertemuan 2
        p2 = page.locator('text=/^\\s*Pertemuan\\s+2\\b/i').first
        print(f"[*] Pertemuan 2 count: {p2.count()}")
        if p2.count() > 0:
            p2.click()
            page.wait_for_timeout(2000)

        # Click first quiz button
        q_btns = page.locator('button:has-text("QUIZ"), a:has-text("QUIZ")').all()
        print(f"[*] Quiz buttons count: {len(q_btns)}")
        if q_btns:
            print("[*] Clicking first quiz button...")
            q_btns[0].click()
            page.wait_for_timeout(4000)
            print("[*] URL after click:", page.url)

        browser.close()

if __name__ == "__main__":
    check_headers()
