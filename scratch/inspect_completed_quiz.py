import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
from pathlib import Path
import re
import time

AUTH_PATH = Path("data/auth.json").resolve()

def inspect_completed():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Pretest Pertemuan 2 Manajemen Proyek (sudah dikerjakan, nilai 100)
        url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312/quiz/711d7811-4445-4409-af80-b4ab92e19aa7"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        full_text = page.locator("body").inner_text()
        own = full_text.split("List Data Peserta")[0] if "List Data Peserta" in full_text else full_text

        print("=== OWN SECTION OF COMPLETED QUIZ ===")
        print(own.strip())
        print("=====================================")

        k_btn = page.locator('button:has-text("KERJAKAN QUIZ"), button:has-text("LANJUTKAN QUIZ"), button:has-text("Kerjakan Quiz"), button:has-text("Lanjutkan Quiz")').first
        has_k = k_btn.count() > 0 and k_btn.is_visible()
        print(f"has_kerjakan_btn: {has_k}")

        is_done = ("sudah mengerjakan quiz" in own.lower()) and not has_k
        print(f"is_done: {is_done}")

        score_match = re.search(r'(?:grade|nilai|skor)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', own, re.IGNORECASE)
        print(f"score_match: {score_match.groups() if score_match else None}")

        all_btns = [b.inner_text().strip() for b in page.locator("button, a").all() if b.is_visible() and b.inner_text().strip()]
        print(f"all_btns: {all_btns}")

        browser.close()

if __name__ == "__main__":
    inspect_completed()
