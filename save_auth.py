"""Save a browser session after the user logs in to Mentari."""
from playwright.sync_api import sync_playwright
from services.auth import check_session_validity, get_auth_file_path


def main():
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome', headless=False)
        except Exception:
            browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto('https://mentari.unpam.ac.id', wait_until='domcontentloaded')
            input('Login di browser sampai dashboard terbuka, lalu tekan ENTER di terminal: ')
            if not check_session_validity(page):
                raise RuntimeError('Login belum terverifikasi. Sesi lama tidak diganti.')
            context.storage_state(path=get_auth_file_path())
            print('Sesi login disimpan ke data/auth.json.')
        finally:
            browser.close()


if __name__ == '__main__':
    main()
