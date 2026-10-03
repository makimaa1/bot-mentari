import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()

def sniff_course():
    print("=" * 70)
    print("      MENTARI LMS - COURSE & QUIZ NETWORK SNIFFER")
    print("=" * 70)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        
        all_api_calls = []

        def handle_response(res):
            url = res.url
            if "/api/" in url:
                try:
                    ctype = res.headers.get("content-type", "")
                    if "json" in ctype:
                        data = res.json()
                        all_api_calls.append({"method": res.request.method, "url": url, "data": data})
                        print(f"[API] {res.status} {res.request.method} {url}")
                except Exception:
                    pass

        ctx.on("response", handle_response)
        page = ctx.new_page()

        print("[*] Membuka Dashboard Mentari...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        # Buka kelas Etika Profesi
        course_url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0422"
        print(f"[*] Membuka kelas: {course_url} ...")
        page.goto(course_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)

        # Buka Pertemuan 2 (yang sudah selesai kuis)
        p2_header = page.locator('text=/^\\s*Pertemuan\\s+2\\b/i').first
        if p2_header.count() > 0:
            print("[*] Mengklik Pertemuan 2...")
            p2_header.click()
            page.wait_for_timeout(3000)

        # Cek tombol kuis pada Pertemuan 2
        cards = page.locator('.MuiPaper-root:not(:has-text("Course Index"))').all()
        print(f"[*] Kartu pertemuan 2 ditemukan: {len(cards)}")
        for idx, c in enumerate(cards):
            txt = c.inner_text().strip().replace('\n', ' | ')
            btns = [b.inner_text().strip() for b in c.locator("button, a").all() if b.is_visible()]
            print(f"   Card {idx}: {txt[:80]} ... Buttons: {btns}")

        # Coba klik tombol QUIZ pada Pre-Test Pertemuan 2
        quiz_btns = page.locator('button:has-text("QUIZ"), a:has-text("QUIZ")').all()
        print(f"[*] Tombol QUIZ terdeteksi: {len(quiz_btns)}")
        if quiz_btns:
            print("[*] Mengklik tombol QUIZ pertama...")
            quiz_btns[0].click()
            page.wait_for_timeout(4000)
            print(f"[*] URL Sekarang: {page.url}")
            page.screenshot(path="scratch/quiz_page_opened.png")
            print("[V] Screenshot quiz page: scratch/quiz_page_opened.png")

            # Ambil semua teks di halaman kuis yang terbuka
            q_text = page.locator("body").inner_text()
            print("\n--- ISI TEKS HALAMAN KUIS (First 1000 chars) ---")
            print(q_text[:1000])

        browser.close()

    print(f"\n[*] Total API Calls terekam: {len(all_api_calls)}")
    with open("scratch/course_api_calls.json", "w", encoding="utf-8") as f:
        json.dump(all_api_calls, f, indent=2, ensure_ascii=False)
    print("[V] Tersimpan ke scratch/course_api_calls.json")

if __name__ == "__main__":
    sniff_course()
