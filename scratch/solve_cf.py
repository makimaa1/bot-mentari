import json
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"]
    )
    context = browser.new_context(
        storage_state=str(AUTH_PATH),
        viewport={"width": 1440, "height": 900}
    )

    page = context.new_page()

    # Log requests
    context.on("request", lambda req: print(f"REQ: {req.method} {req.url[:80]} | Cookie header present: {'Cookie' in req.headers}"))

    print("[*] Mengakses https://mentari.unpam.ac.id ...")
    page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=45000)

    for i in range(12):
        page.wait_for_timeout(2000)
        title = page.title()
        print(f"Sec {i*2}: Title='{title}' | URL='{page.url}'")
        
        # Cek apakah ada iframe Cloudflare Turnstile
        iframes = page.frames
        for frame in iframes:
            if "challenges.cloudflare" in frame.url or "turnstile" in frame.url:
                print(f"    Found Cloudflare frame: {frame.url[:70]}")
                # Coba cari checkbox di dalam frame jika ada
                try:
                    cb = frame.locator('input[type="checkbox"], #challenge-stage, .ctp-checkbox-label')
                    if cb.count() > 0:
                        print("    Found checkbox inside frame! Clicking...")
                        cb.first.click()
                except Exception as e:
                    print(f"    Frame click error: {e}")

        if "Just a moment" not in title and title != "":
            print("[V] KELUAR DARI CLOUDFLARE!")
            break

    page.screenshot(path="scratch/cf_check.png")
    print("Final title:", page.title())
    print("Final URL  :", page.url)
    browser.close()
