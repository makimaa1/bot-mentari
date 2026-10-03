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
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-browser-side-navigation",
            "--disable-gpu",
        ]
    )
    context = browser.new_context(
        storage_state=str(AUTH_PATH),
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 768},
    )
    # Stealth bypass scripts
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.navigator.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', { get: () => ['id-ID', 'id', 'en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    """)
    page = context.new_page()
    page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=45000)
    
    # Tunggu beberapa detik untuk melihat apakah Turnstile lewat
    for i in range(8):
        page.wait_for_timeout(1500)
        title = page.title()
        print(f"[{i}] Title: {title}")
        if "Just a moment" not in title and title:
            break
            
    page.screenshot(path="scratch/stealth_result.png")
    print(f"Final Title: {page.title()}")
    print(f"Final URL  : {page.url}")
    browser.close()
