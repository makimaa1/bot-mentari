import time
from playwright.sync_api import sync_playwright
import pipeline_runner as pr

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome", args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
    page = ctx.new_page()

    page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
    pr.ensure_turnstile_cleared(page)
    page.wait_for_timeout(2000)

    course_url = pr.COURSES["2"]["url"]
    print(f"Navigating to {course_url}...")
    page.goto(course_url, wait_until="domcontentloaded", timeout=60000)
    pr.ensure_turnstile_cleared(page)

    # Wait for accordions to appear
    print("Waiting for accordions...")
    try:
        page.wait_for_selector(".MuiAccordion-root, [id*='PERTEMUAN'], [id*='pertemuan']", timeout=15000)
    except Exception as e:
        print(f"Timeout waiting for selector: {e}")

    page.wait_for_timeout(2000)

    # Print all IDs matching PERTEMUAN
    ids = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('*[id]'))
            .map(el => el.id)
            .filter(id => id.toLowerCase().includes('pertemuan'));
    }""")
    print("Pertemuan IDs found:", ids)

    # Print texts of accordions
    accs = page.locator(".MuiAccordionSummary-root").all()
    print(f"Found {len(accs)} accordion summaries:")
    for i, a in enumerate(accs):
        print(f"  #{i+1}: '{a.inner_text().strip().splitlines()[0]}'")

    browser.close()
