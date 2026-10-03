import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()

def test_download():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        ctx = browser.new_context(storage_state=str(AUTH_PATH))
        page = ctx.new_page()

        # Monitor requests
        page.on("request", lambda r: print(f"REQ: {r.method} {r.url}") if any(k in r.url for k in ["excel", "export", "download", "grade"]) else None)

        url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0422/grade-book"
        print(f"[*] Membuka {url}...")
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)

        dl_btn = page.locator('button:has-text("DOWNLOAD EXCEL"), a:has-text("DOWNLOAD EXCEL")')
        print(f"[*] Tombol Download ditemukan: {dl_btn.count()}")

        if dl_btn.count() > 0:
            try:
                with page.expect_download(timeout=10000) as dl_info:
                    dl_btn.first.click()
                dl = dl_info.value
                save_path = Path("scratch/gradebook_etika.xlsx")
                dl.save_as(save_path)
                print(f"[V] BERHASIL DOWNLOAD EXCEL: {save_path} (Ukuran: {save_path.stat().st_size} bytes)")
            except Exception as e:
                print(f"[!] Error download: {e}")

        browser.close()

if __name__ == "__main__":
    test_download()
