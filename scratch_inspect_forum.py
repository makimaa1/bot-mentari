import os
import sys
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
import pipeline_runner as pr

def inspect_forum():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome", args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
        context = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
        page = context.new_page()

        print("[*] Navigating to Arkom...")
        course_url = pr.COURSES["2"]["url"]
        page.goto(course_url, wait_until="domcontentloaded", timeout=60000)
        pr.ensure_turnstile_cleared(page)
        page.wait_for_timeout(3000)

        print("[*] Expanding meeting 7...")
        pr.ensure_meeting_expanded(page, 7)
        page.wait_for_timeout(2000)

        scope = pr.get_meeting_scope(page, 7)
        cards = scope.locator('.MuiCard-root, .MuiPaper-root').all()
        print(f"[*] Found {len(cards)} cards in meeting 7")
        fordis_btn = None
        for c in cards:
            cls = c.get_attribute("class") or ""
            if "MuiAccordion" in cls:
                continue
            txt = c.inner_text().strip()
            first_l = txt.splitlines()[0] if txt else ""
            if "forum" in first_l.lower():
                print(f"[V] Found forum card: '{first_l}'")
                btn = c.locator('button:has-text("FORUM"), a:has-text("FORUM")').first
                if btn.count() > 0:
                    fordis_btn = btn
                    break

        if not fordis_btn:
            print("[!] Forum button not found!")
            browser.close()
            return

        print("[*] Clicking Forum button...")
        fordis_btn.scroll_into_view_if_needed()
        fordis_btn.click(force=True)
        page.wait_for_timeout(4000)
        print(f"[*] Current URL: {page.url}")

        # If it's a thread list, click the thread
        if "REPLY" not in page.locator("body").inner_text():
            print("[*] Looking for thread link/cell...")
            cell = page.locator("table tbody tr td").first
            if cell.count() > 0:
                print(f"[*] Clicking thread cell: {cell.inner_text().strip()}")
                cell.click()
                page.wait_for_timeout(4000)

        print(f"[*] In thread URL: {page.url}")
        page.screenshot(path="data/inspect_thread_full.png")

        # Now let's inspect REPLY buttons
        reply_btns = page.locator("button:has-text('REPLY'), button:has-text('Reply'), a:has-text('REPLY')").all()
        print(f"[*] Found {len(reply_btns)} REPLY buttons on page!")

        for i, btn in enumerate(reply_btns[:10]):
            txt = btn.inner_text().strip()
            # Find parent card or container
            parent = btn.locator("xpath=ancestor::*[contains(@class, 'MuiCard-root') or contains(@class, 'MuiPaper-root') or contains(@class, 'card') or contains(@class, 'post')][1]")
            p_txt = parent.inner_text() if parent.count() > 0 else "NO_PARENT"
            p_first_few = [l.strip() for l in p_txt.splitlines() if l.strip()][:4]
            print(f"  Btn #{i+1}: text='{txt}' | Container: {' // '.join(p_first_few)}")

        # Let's see what happens when clicking the first REPLY button (Dosen)
        print("\n[*] Clicking button #1 (Dosen REPLY)...")
        reply_btns[0].scroll_into_view_if_needed()
        reply_btns[0].click()
        page.wait_for_timeout(2000)
        page.screenshot(path="data/inspect_after_click_reply_dosen.png")

        # Look for dialog, modal, editor, textarea
        dialog = page.locator(".MuiDialog-root, [role='dialog'], .modal")
        print(f"[*] Dialog count: {dialog.count()}")
        if dialog.count() > 0:
            print("  Dialog text:")
            print(dialog.inner_text()[:300])

        # Look for inputs/editors anywhere
        editors = page.locator(".ql-editor, textarea, div[contenteditable='true']").all()
        print(f"[*] Found {len(editors)} editor/textarea elements:")
        for idx, ed in enumerate(editors):
            tag = ed.evaluate("el => el.tagName")
            cls = ed.get_attribute("class") or ""
            vis = ed.is_visible()
            print(f"  Editor #{idx+1}: tag={tag}, visible={vis}, class={cls}")

        # Look for submit buttons
        submit_btns = page.locator("button:has-text('KIRIM'), button:has-text('SUBMIT'), button:has-text('SIMPAN'), button:has-text('Kirim'), button:has-text('Balas'), button:has-text('Send')").all()
        print(f"[*] Found {len(submit_btns)} potential submit buttons:")
        for idx, sb in enumerate(submit_btns):
            print(f"  SubmitBtn #{idx+1}: text='{sb.inner_text().strip()}', visible={sb.is_visible()}")

        # Close dialog or cancel if open
        cancel_btn = page.locator("button:has-text('BATAL'), button:has-text('CANCEL'), button:has-text('Batal')").first
        if cancel_btn.count() > 0 and cancel_btn.is_visible():
            print("[*] Clicking cancel...")
            cancel_btn.click()
            page.wait_for_timeout(1000)

        browser.close()

if __name__ == "__main__":
    inspect_forum()
