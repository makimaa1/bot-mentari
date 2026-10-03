import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()

def test_gradebook():
    print("=" * 70)
    print("      MENTARI LMS - GRADE BOOK INSPECTOR")
    print("=" * 70)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        print("[*] Membuka Dashboard Mentari...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        
        # Tunggu Cloudflare
        for _ in range(15):
            title = page.title()
            if "Just a moment" not in title and title:
                break
            time.sleep(1)
            
        print(f"[*] Dashboard OK: {page.title()}")
        
        # Buka Etika Profesi yang sudah selesai P2-P5
        course_url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0422"
        print(f"[*] Membuka kelas Etika Profesi: {course_url} ...")
        page.goto(course_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        
        # Cari tab Grade Book yang tepat
        print("[*] Mencari tombol Grade Book di navigation bar...")
        gb_target = page.locator('button, a, [role="button"], [role="tab"]').filter(has_text="Grade Book")
        print(f"[*] Tombol Grade Book terfilter: {gb_target.count()}")
        
        target_clicked = False
        for idx in range(gb_target.count()):
            btn = gb_target.nth(idx)
            txt = btn.inner_text().strip()
            print(f"  Item {idx}: '{txt}'")
            if "Grade Book" in txt and not target_clicked:
                btn.scroll_into_view_if_needed()
                btn.click()
                target_clicked = True
                print(f"  -> Diklik item {idx}!")
                break
                
        if not target_clicked:
            # Fallback exact text
            page.get_by_text("Grade Book", exact=True).first.click()
            
        page.wait_for_timeout(4000)
        print(f"[*] URL Sekarang: {page.url}")
        page.screenshot(path="scratch/gradebook.png")
        print("[V] Screenshot Grade Book tersimpan: scratch/gradebook.png")
            
        # Ekstraksi tabel jika ada
        tables = page.locator("table").all()
        print(f"[*] Ditemukan {len(tables)} tabel.")
        for idx, tbl in enumerate(tables):
            print(f"\n--- TABEL {idx+1} ---")
            rows = tbl.locator("tr").all()
            for r in rows:
                cells = [c.inner_text().strip().replace('\n', ' | ') for c in r.locator("th, td").all()]
                if cells:
                    print("  " + " ; ".join(cells))

        # Ambil seluruh teks badan halaman jika tabel tidak ada
        body_text = page.locator(".MuiContainer-root, main, [role='main'], body").first.inner_text()
        print("\n--- CUPLIKAN ISI GRADE BOOK (First 1500 chars) ---")
        print(body_text[:1500])

        browser.close()

if __name__ == "__main__":
    test_gradebook()
