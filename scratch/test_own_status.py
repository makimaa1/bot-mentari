import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright
from pathlib import Path
import re
import time

AUTH_PATH = Path("data/auth.json").resolve()

def test_own_status():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Open Manajemen Proyek
        url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312"
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Open Pertemuan 3
        p3 = page.locator('text=/^\\s*Pertemuan\\s+3\\b/i').first
        p3.scroll_into_view_if_needed()
        p3.click()
        page.wait_for_timeout(2000)

        # Find Pretest card and click QUIZ
        cards = page.locator('.MuiPaper-root').all()
        for c in cards:
            txt = c.inner_text().strip()
            first_l = txt.splitlines()[0] if txt else ""
            if "pretest" in first_l.lower():
                c.locator('button:has-text("QUIZ")').first.click()
                page.wait_for_timeout(3500)
                break

        print(f"[*] Quiz URL: {page.url}")

        # Check Kerjakan button
        k_btn = page.locator('button:has-text("KERJAKAN QUIZ"), button:has-text("LANJUTKAN QUIZ")').first
        has_k_btn = k_btn.count() > 0 and k_btn.is_visible()
        print(f"[*] Has KERJAKAN/LANJUTKAN button: {has_k_btn}")

        # Check Detail Pengerjaan Quiz text only (split before 'List Data Peserta')
        full_text = page.locator("body").inner_text()
        student_section = full_text.split("List Data Peserta")[0] if "List Data Peserta" in full_text else full_text
        print("\n--- STUDENT'S OWN DETAIL SECTION ---")
        print(student_section.strip())
        print("-----------------------------------")

        is_student_done = ("sudah mengerjakan quiz" in student_section.lower()) and not has_k_btn
        print(f"\n[*] Is Sofyan Done? {is_student_done}")

        if is_student_done:
            score_match = re.search(r'(?:grade|nilai|skor)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', student_section, re.IGNORECASE)
            print(f"[*] Own Grade: {score_match.group(1) if score_match else 'None'}")
        else:
            print("[*] Sofyan has NOT done the quiz yet! Ready to click KERJAKAN QUIZ.")

        browser.close()

if __name__ == "__main__":
    test_own_status()
