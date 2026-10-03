import json
from pathlib import Path
from playwright.sync_api import Page

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
AUTH_FILE = DATA_DIR / "auth.json"


def is_auth_saved() -> bool:
    """Memeriksa apakah file auth.json sesi tersimpan ada dan valid."""
    return AUTH_FILE.exists() and AUTH_FILE.stat().st_size > 10


def get_auth_file_path() -> str:
    """Mengembalikan path absolut ke auth.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(AUTH_FILE)


def extract_stored_credentials() -> dict:
    """
    Mengekstrak informasi kredensial yang tersimpan di auth.json
    (seperti token JWT di Local Storage dan cookies Cloudflare).
    """
    if not is_auth_saved():
        return {}

    try:
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        summary = {
            "cookies": [c.get("name") for c in data.get("cookies", [])],
            "has_cf_clearance": any(c.get("name") == "cf_clearance" for c in data.get("cookies", [])),
            "has_stoken": any(c.get("name") == "stoken" for c in data.get("cookies", [])),
            "has_sl_session": any(c.get("name") == "sl-session" for c in data.get("cookies", [])),
            "has_jwt_access": False,
            "role": None,
            "fullname": None,
            "username": None,
            "token": None,
        }

        # Cek local storage untuk access token
        for origin in data.get("origins", []):
            for item in origin.get("localStorage", []):
                if item.get("name") == "access":
                    summary["has_jwt_access"] = True
                    try:
                        val = json.loads(item.get("value", "{}"))
                        user_obj = val[0] if isinstance(val, list) and val else val
                        summary["role"] = user_obj.get("role")
                        token_str = user_obj.get("token")
                        summary["token"] = token_str
                        
                        # Decode payload JWT untuk mendapatkan nama lengkap & NIM
                        if token_str and "." in token_str:
                            import base64
                            payload_part = token_str.split(".")[1]
                            padded = payload_part + "=" * ((4 - len(payload_part) % 4) % 4)
                            payload_data = json.loads(base64.urlsafe_b64decode(padded.decode() if isinstance(padded, bytes) else padded).decode("utf-8"))
                            summary["fullname"] = payload_data.get("fullname")
                            summary["username"] = payload_data.get("username")
                            if not summary["role"]:
                                summary["role"] = payload_data.get("role")
                    except Exception:
                        pass
        return summary
    except Exception as e:
        return {"error": str(e)}


def check_session_validity(page: Page) -> bool:
    """
    Memeriksa apakah sesi saat ini masih aktif dan valid di halaman Mentari.
    Mendeteksi tanda login form vs dashboard aktif.
    """
    current_url = page.url.lower()

    # Jika diarahkan ke URL login
    if "login" in current_url:
        return False

    # Periksa keberadaan form password
    try:
        password_input = page.locator('input[type="password"]')
        if password_input.count() > 0 and password_input.first.is_visible():
            return False
    except Exception:
        pass

    # Periksa token di local storage melalui konteks browser
    try:
        access_token = page.evaluate("() => localStorage.getItem('access')")
        if access_token:
            return True
    except Exception:
        pass

    # Periksa elemen khas dashboard Mentari (navbar, sidebar, avatar, atau menu)
    try:
        dashboard_indicators = [
            page.locator('button:has-text("Keluar")'),
            page.locator('a:has-text("Dashboard")'),
            page.locator('header'),
            page.locator('nav'),
            page.locator('.sidebar'),
        ]
        for indicator in dashboard_indicators:
            if indicator.count() > 0:
                return True
    except Exception:
        pass

    return True
