import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
from pathlib import Path
import re

AUTH_PATH = Path("data/auth.json").resolve()

def test_locators():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        ctx = browser.new_context(storage_state=str(AUTH_PATH))
        page = ctx.new_page()

        print("[*] Opening dashboard...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Quiz P3 Manajemen Proyek
        url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312/quiz/ab00e20f-dbaa-4a51-9748-8c2352db126e"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        # 1. Cari tombol KERJAKAN QUIZ / LANJUTKAN QUIZ
        k_btn = page.locator('button:has-text("KERJAKAN QUIZ"), button:has-text("LANJUTKAN QUIZ")')
        is_btn_visible = k_btn.count() > 0 and k_btn.first.is_visible()
        print(f"[*] Tombol KERJAKAN/LANJUTKAN QUIZ terlihat: {is_btn_visible}")
        if is_btn_visible:
            print(f"    Text tombol: '{k_btn.first.inner_text()}'")

        # 2. Cek card Detail Pengerjaan Quiz
        cards = page.locator('.MuiPaper-root').all()
        for idx, c in enumerate(cards):
            txt = c.inner_text().strip()
            if "Detail Pengerjaan Quiz" in txt:
                print(f"\n[V] Card {idx} (Detail Pengerjaan Quiz):\n{txt}")
                has_sudah = "sudah mengerjakan quiz" in txt.lower()
                has_belum = "belum mengerjakan quiz" in txt.lower()
                print(f"    Sudah: {has_sudah}, Belum: {has_belum}")
                score_match = re.search(r'(?:grade|nilai|skor)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', txt, re.IGNORECASE)
                print(f"    Own Score match: {score_match.groups() if score_match else None}")
                break

        browser.close()

if __name__ == "__main__":
    test_locators()
