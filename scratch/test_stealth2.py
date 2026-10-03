import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

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
    Stealth().apply_stealth_sync(page)
    
    print("[*] Mengakses https://mentari.unpam.ac.id ...")
    page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=45000)
    for i in range(10):
        page.wait_for_timeout(1500)
        title = page.title()
        print(f"[{i}] Title: {title}")
        if "Just a moment" not in title and title:
            break
            
    print("Final title:", page.title())
    print("Final URL  :", page.url)
    page.screenshot(path="scratch/stealth2_result.png")
    
    # Ambil teks jika berhasil masuk
    if "Just a moment" not in page.title():
        print("[V] BERHASIL MASUK DASHBOARD!")
        links = [a.inner_text().strip() for a in page.locator("a, button").all() if a.inner_text().strip()]
        print("Menu/Links:", links[:20])
    browser.close()
