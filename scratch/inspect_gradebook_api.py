import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()

def inspect_api():
    print("=" * 70)
    print("      MENTARI LMS - GRADE BOOK NETWORK API SNIFFER")
    print("=" * 70)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        
        captured_responses = []

        def handle_response(res):
            url = res.url
            if any(k in url.lower() for k in ["grade", "nilai", "score", "rekap", "progress", "u-courses", "course"]):
                try:
                    ctype = res.headers.get("content-type", "")
                    if "json" in ctype:
                        data = res.json()
                        captured_responses.append({"url": url, "data": data})
                        print(f"[API HIT] {res.status} {url[:100]}")
                except Exception:
                    pass

        ctx.on("response", handle_response)
        page = ctx.new_page()

        print("[*] Membuka Dashboard Mentari...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        
        # Buka langsung URL grade-book
        gb_url = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0422/grade-book"
        print(f"[*] Menuju langsung ke {gb_url} ...")
        page.goto(gb_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        
        # Klik pada kartu/score jika bisa diklik untuk melihat detail pertemuan
        chip = page.locator('text="Score: 5", text="Score: 4.64", [class*="MuiChip"]').first
        if chip.count() > 0:
            print("[*] Mencoba klik chip score...")
            try:
                chip.click()
                page.wait_for_timeout(2000)
                page.screenshot(path="scratch/gradebook_detail.png")
            except Exception as e:
                print(f"[!] Chip click failed: {e}")

        browser.close()

    print(f"\n[*] Total JSON API Responses tertangkap: {len(captured_responses)}")
    for idx, item in enumerate(captured_responses):
        print(f"\n--- API RESPONSE #{idx+1}: {item['url']} ---")
        raw_str = json.dumps(item['data'], indent=2, ensure_ascii=False)
        print(raw_str[:1200] + ("..." if len(raw_str) > 1200 else ""))
        
    with open("data/mentari_gradebook_api_sample.json", "w", encoding="utf-8") as f:
        json.dump(captured_responses, f, indent=2, ensure_ascii=False)
    print("\n[V] Seluruh respons API tersimpan di data/mentari_gradebook_api_sample.json")

if __name__ == "__main__":
    inspect_api()
