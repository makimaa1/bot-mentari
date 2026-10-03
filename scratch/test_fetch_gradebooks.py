import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()

# 8 Mata Kuliah
COURSES = [
    {"id": "22TIF0312", "name": "MANAJEMEN PROYEK INFORMATIKA", "code": "20261-07TPLP003-22TIF0312"},
    {"id": "22TIF0373", "name": "ARSITEKTUR DAN ORGANISASI KOMPUTER", "code": "20261-07TPLP003-22TIF0373"},
    {"id": "22TIF0382", "name": "KEAMANAN KOMPUTER", "code": "20261-07TPLP003-22TIF0382"},
    {"id": "22TIF0392", "name": "JARINGAN NIRKABEL", "code": "20261-07TPLP003-22TIF0392"},
    {"id": "22TIF0402", "name": "KECAKAPAN ANTAR PERSONAL", "code": "20261-07TPLP003-22TIF0402"},
    {"id": "22TIF0412", "name": "TESTING DAN QA PERANGKAT LUNAK", "code": "20261-07TPLP003-22TIF0412"},
    {"id": "22TIF0422", "name": "ETIKA PROFESI", "code": "20261-07TPLP003-22TIF0422"},
    {"id": "22TIF0433", "name": "PEMROGRAMAN WEB II", "code": "20261-07TPLP003-22TIF0433"}
]

def fetch_all():
    print("=" * 70)
    print("      MENTARI LMS - FETCHING ALL GRADE BOOKS VIA BROWSER CONTEXT")
    print("=" * 70)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        print("[*] Masuk ke Mentari LMS...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        results = {}
        for c in COURSES:
            code = c["code"]
            name = c["name"]
            print(f"[*] Mengambil Rekap Nilai: {name} ({code})...")
            js_code = f"""
            async () => {{
                try {{
                    const accessRaw = localStorage.getItem('access');
                    let token = '';
                    if (accessRaw) {{
                        const parsed = JSON.parse(accessRaw);
                        token = Array.isArray(parsed) ? parsed[0].token : parsed.token;
                    }}
                    const res = await fetch('/api/user-course/{code}/grade-book', {{
                        headers: {{
                            'Authorization': token ? ('Bearer ' + token) : '',
                            'Accept': 'application/json'
                        }}
                    }});
                    if (res.ok) {{
                        return await res.json();
                    }} else {{
                        return {{ error: res.status, text: await res.text() }};
                    }}
                }} catch (e) {{
                    return {{ error: e.message }};
                }}
            }}
            """
            data = page.evaluate(js_code)
            results[name] = data
            if isinstance(data, list) and len(data) > 0:
                print(f"    [V] Berhasil! Data mahasiswa: {data[0].get('nama_mahasiswa')}")
                for sub in data[0].get("sub_course_template", []):
                    j = sub.get("judul")
                    s = sub.get("score")
                    comp = sub.get("completion")
                    tot = sub.get("total")
                    if comp > 0 or s is not None:
                        print(f"        • {j}: {comp}/{tot} (Skor: {s})")
            else:
                print(f"    [!] Hasil: {data}")

        browser.close()

        out_path = Path("data/mentari_gradebook_summary.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[V] Sukses! Seluruh rekap nilai tersimpan di {out_path}")

if __name__ == "__main__":
    fetch_all()
