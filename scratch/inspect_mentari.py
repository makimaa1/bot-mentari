import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()
SCRATCH_DIR = Path("scratch")
SCRATCH_DIR.mkdir(exist_ok=True)


def inspect():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"]
            )
        except Exception:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"]
            )
        context = browser.new_context(
            storage_state=str(AUTH_PATH),
            viewport={"width": 1440, "height": 900}
        )

        api_calls = []

        def handle_request(req):
            if any(k in req.url for k in ["api", "graphql", "mahasiswa", "kelas", "jadwal", "tugas", "forum"]):
                api_calls.append({"method": req.method, "url": req.url})

        context.on("request", handle_request)

        page = context.new_page()
        print("[*] Mengakses https://mentari.unpam.ac.id ...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=45000)
        
        # Tunggu hingga Cloudflare selesai verifikasi (judul bukan 'Just a moment...')
        print("[*] Menunggu Cloudflare Turnstile verification...")
        for _ in range(15):
            page.wait_for_timeout(2000)
            title = page.title()
            print(f"    Status judul: {title}")
            if "Just a moment" not in title and title:
                break

        # Simpan screenshot
        screenshot_path = SCRATCH_DIR / "dashboard.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"[V] Screenshot tersimpan: {screenshot_path}")

        print(f"[*] Judul Halaman: {page.title()}")
        print(f"[*] URL Sekarang : {page.url}")

        # Ambil semua link navigasi
        links = []
        for a in page.locator("a").all():
            href = a.get_attribute("href")
            text = a.inner_text().strip()
            if href and text:
                links.append({"text": text.replace("\n", " "), "href": href})

        # Ambil tombol-tombol utama
        buttons = []
        for b in page.locator("button").all():
            bt = b.inner_text().strip()
            if bt:
                buttons.append(bt.replace("\n", " "))

        # Ambil semua heading
        headings = []
        for h in page.locator("h1, h2, h3, h4, h5").all():
            ht = h.inner_text().strip()
            if ht:
                headings.append(ht.replace("\n", " "))

        print("\n--- LINK / MENU DITEMUKAN ---")
        for l in links[:20]:
            print(f"  - [{l['text']}] -> {l['href']}")

        print("\n--- TOMBOL DITEMUKAN ---")
        for b in buttons[:15]:
            print(f"  - {b}")

        print("\n--- HEADING / JUDUL BAGIAN ---")
        for h in headings[:15]:
            print(f"  - {h}")

        print("\n--- API ENDPOINT YANG DIPANGGIL ---")
        for api in api_calls[:20]:
            print(f"  - [{api['method']}] {api['url']}")

        # Ambil cuplikan teks utama halaman
        body_text = page.locator("body").inner_text()
        lines = [line.strip() for line in body_text.split("\n") if line.strip()]
        print("\n--- CUPLIKAN KONTEN HALAMAN (25 Baris Pertama) ---")
        for line in lines[:25]:
            print(f"  {line}")

        browser.close()


if __name__ == "__main__":
    inspect()
