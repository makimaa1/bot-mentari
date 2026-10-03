import json
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        channel="chrome",
        args=[
            "--disable-blink-features=AutomationControlled",
            "--headless=new"
        ]
    )
    context = browser.new_context(
        storage_state=str(AUTH_PATH),
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)
    print("PAGE TITLE:", page.title())
    print("PAGE URL  :", page.url)
    
    # Ambil teks tombol atau link
    links = [a.inner_text().strip() for a in page.locator("a, button").all() if a.inner_text().strip()]
    print("LINKS/BUTTONS (sample):", links[:15])
    
    # Simpan screenshot
    page.screenshot(path="scratch/real_page.png")
    print("Screenshot saved to scratch/real_page.png")
    browser.close()
