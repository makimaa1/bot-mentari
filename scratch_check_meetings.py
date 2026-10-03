import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
import pipeline_runner as pr

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome", args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
    page = ctx.new_page()

    course_url = pr.COURSES["2"]["url"]
    print(f"Navigating to {course_url}...")
    page.goto(course_url, wait_until="networkidle", timeout=60000)
    pr.ensure_turnstile_cleared(page)
    page.wait_for_timeout(3000)

    print(f"Title: {page.title()}")
    print(f"URL: {page.url}")

    # Find all elements with 'PERTEMUAN' or 'pertemuan' in id or text
    accordions = page.locator(".MuiAccordion-root, [id*='pertemuan'], [id*='PERTEMUAN']").all()
    print(f"Found {len(accordions)} accordion/pertemuan elements:")
    for i, a in enumerate(accordions[:25]):
        aid = a.get_attribute("id") or ""
        txt = a.inner_text().strip().splitlines()[0] if a.inner_text().strip() else ""
        print(f"  #{i+1}: id='{aid}', text='{txt[:50]}'")

    # Also search for 'Pertemuan 7'
    p7 = page.locator("text='Pertemuan 7', text='PERTEMUAN 7', text='Pertemuan 07'").all()
    print(f"Found {len(p7)} elements with 'Pertemuan 7' text:")
    for i, el in enumerate(p7):
        print(f"  P7 #{i+1}: tag={el.evaluate('e => e.tagName')}, parent_id={el.evaluate('e => e.parentElement.id')}, id={el.get_attribute('id')}")

    browser.close()
