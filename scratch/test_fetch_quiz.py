from playwright.sync_api import sync_playwright
from pathlib import Path
import json

AUTH_PATH = Path("data/auth.json").resolve()

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="chrome")
        ctx = browser.new_context(storage_state=str(AUTH_PATH))
        page = ctx.new_page()
        page.goto("https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0422", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Let's inspect token in localStorage
        token = page.evaluate("() => localStorage.getItem('token') || localStorage.getItem('access_token') || sessionStorage.getItem('token')")
        print("Token found in storage:", token[:30] if token else "None")

        # Let's list all localStorage keys
        storage_keys = page.evaluate("() => Object.keys(localStorage)")
        print("LocalStorage keys:", storage_keys)

        for qid in ["689ea129-c82d-4800-844e-eaad92fb11a4", "71dc557c-02af-4280-87fa-923a4ed169aa"]:
            script = """
            async (id) => {
                const res = await fetch('/api/quiz/peserta/' + id);
                const text = await res.text();
                return { status: res.status, text: text.slice(0, 300) };
            }
            """
            out = page.evaluate(script, qid)
            print(f"Quiz {qid}: status={out['status']}, text={out['text'][:150]}")

        browser.close()

if __name__ == "__main__":
    main()
