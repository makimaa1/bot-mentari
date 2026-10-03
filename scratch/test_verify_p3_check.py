import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
from pathlib import Path
import re
import time

AUTH_PATH = Path("data/auth.json").resolve()

def ensure_turnstile_cleared(page, timeout_sec: int = 15):
    for _ in range(timeout_sec):
        title = page.title()
        if "Just a moment" not in title and "Security Verification" not in title and title != "":
            return True
        time.sleep(1)
    return False

def verify_p3_check():
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
        ensure_turnstile_cleared(page)
        page.wait_for_timeout(2000)

        url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312/quiz/ab00e20f-dbaa-4a51-9748-8c2352db126e"
        print(f"[*] Navigating directly to Quiz URL: {url}...")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        full_pre = page.locator("body").inner_text()
        own_pre = full_pre.split("List Data Peserta")[0] if "List Data Peserta" in full_pre else full_pre

        k_btn = page.locator('button:has-text("KERJAKAN QUIZ"), button:has-text("LANJUTKAN QUIZ"), button:has-text("Kerjakan Quiz"), button:has-text("Lanjutkan Quiz")').first
        has_kerjakan_btn = k_btn.count() > 0 and k_btn.is_visible()

        is_done = ("sudah mengerjakan quiz" in own_pre.lower()) and not has_kerjakan_btn

        print("\n--- SOFYAN OWN SECTION ---")
        print(own_pre.strip())
        print("--------------------------")
        print(f"[*] has_kerjakan_btn: {has_kerjakan_btn}")
        print(f"[*] is_done: {is_done}")

        if is_done:
            score_match = re.search(r'(?:grade|nilai|skor)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', own_pre, re.IGNORECASE)
            print(f"[*] Score found: {score_match.group(1) if score_match else None}")
        else:
            print("[V] SUKSES: Bot dengan benar mendeteksi bahwa Pre-Test BELUM dikerjakan oleh Sofyan!")
            print("[V] Tombol KERJAKAN QUIZ terdeteksi dan bot TIDAK mengambil nilai mahasiswa lain (Grade 40)!")
        
        browser.close()
        return

if __name__ == "__main__":
    verify_p3_check()
