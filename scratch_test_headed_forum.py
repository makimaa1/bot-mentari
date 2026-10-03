import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import pipeline_runner as pr

def test_headed_forum():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        print("[*] Navigating to Mentari home...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        pr.ensure_turnstile_cleared(page)
        page.wait_for_timeout(2000)

        course_url = pr.COURSES["2"]["url"]
        print(f"[*] Navigating to Arkom: {course_url}...")
        page.goto(course_url, wait_until="domcontentloaded", timeout=60000)
        pr.ensure_turnstile_cleared(page)
        page.wait_for_timeout(3000)

        print("[*] Ensuring Meeting 7 expanded...")
        pr.ensure_meeting_expanded(page, 7)
        page.wait_for_timeout(2000)

        scope = pr.get_meeting_scope(page, 7)
        cards = scope.locator('.MuiCard-root, .MuiPaper-root').all()
        print(f"[*] Found {len(cards)} cards in meeting 7")
        fordis_card = None
        for c in cards:
            cls = c.get_attribute("class") or ""
            if "MuiAccordion" in cls:
                continue
            txt = c.inner_text().strip()
            first_l = txt.splitlines()[0] if txt else ""
            if "forum" in first_l.lower():
                fordis_card = c
                print(f"[V] Found fordis card: {first_l}")
                break

        if not fordis_card:
            print("[!] Fordis card not found!")
            browser.close()
            return

        f_btn = fordis_card.locator('button:has-text("FORUM"), a:has-text("FORUM")').first
        f_btn.scroll_into_view_if_needed()
        f_btn.click(force=True)
        page.wait_for_timeout(4000)
        print(f"[*] URL: {page.url}")

        if "REPLY" not in page.locator("body").inner_text():
            cell = page.locator("table tbody tr td").first
            if cell.count() > 0:
                print(f"[*] Clicking thread cell: {cell.inner_text().strip()}...")
                cell.click()
                page.wait_for_timeout(4000)

        print(f"[*] Thread URL: {page.url}")
        page.screenshot(path="data/arkom_p7_thread.png")

        # Find all reply buttons
        reply_btns = page.locator("button:has-text('REPLY'), button:has-text('Reply')").all()
        print(f"[*] Found {len(reply_btns)} REPLY buttons!")

        # Click the first REPLY button (belonging to lecturer)
        print("[*] Clicking lecturer REPLY button (index 0)...")
        reply_btns[0].scroll_into_view_if_needed()
        reply_btns[0].click()
        page.wait_for_timeout(2500)
        page.screenshot(path="data/arkom_p7_after_reply_click.png")

        # Inspect dialog or active input elements
        dialog = page.locator(".MuiDialog-root, [role='dialog'], form")
        print(f"[*] Dialog/Form count: {dialog.count()}")
        for i in range(dialog.count()):
            d = dialog.nth(i)
            print(f"  Dialog #{i+1} visible={d.is_visible()}:")
            print(d.inner_text()[:300])

        # Find input or contenteditable elements
        editors = page.locator(".ql-editor, textarea, div[contenteditable='true']").all()
        print(f"[*] Found {len(editors)} editor elements:")
        for i, ed in enumerate(editors):
            tag = ed.evaluate("el => el.tagName")
            vis = ed.is_visible()
            name = ed.get_attribute("name") or ""
            cls = ed.get_attribute("class") or ""
            print(f"  Editor #{i+1}: tag={tag}, visible={vis}, name='{name}', class='{cls}'")

        # Find submit / send buttons
        action_btns = page.locator("button").all()
        for b in action_btns:
            txt = b.inner_text().strip()
            if any(w in txt.upper() for w in ["KIRIM", "SUBMIT", "SIMPAN", "BALAS", "BATAL", "CANCEL"]):
                vis = b.is_visible()
                print(f"  Action button: '{txt}', visible={vis}")

        browser.close()

if __name__ == "__main__":
    test_headed_forum()
