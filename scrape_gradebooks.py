import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path(__file__).resolve().parent / "data/auth.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "data/mentari_gradebook_master.json"

COURSES = [
    {"id": "22TIF0312", "name": "MANAJEMEN PROYEK INFORMATIKA", "code": "20261-07TPLP003-22TIF0312", "total_meetings": 14},
    {"id": "22TIF0373", "name": "ARSITEKTUR DAN ORGANISASI KOMPUTER", "code": "20261-07TPLP003-22TIF0373", "total_meetings": 16},
    {"id": "22TIF0382", "name": "KEAMANAN KOMPUTER", "code": "20261-07TPLP003-22TIF0382", "total_meetings": 14},
    {"id": "22TIF0392", "name": "JARINGAN NIRKABEL", "code": "20261-07TPLP003-22TIF0392", "total_meetings": 14},
    {"id": "22TIF0402", "name": "KECAKAPAN ANTAR PERSONAL", "code": "20261-07TPLP003-22TIF0402", "total_meetings": 14},
    {"id": "22TIF0412", "name": "TESTING DAN QA PERANGKAT LUNAK", "code": "20261-07TPLP003-22TIF0412", "total_meetings": 14},
    {"id": "22TIF0422", "name": "ETIKA PROFESI", "code": "20261-07TPLP003-22TIF0422", "total_meetings": 14},
    {"id": "22TIF0433", "name": "PEMROGRAMAN WEB II", "code": "20261-07TPLP003-22TIF0433", "total_meetings": 16}
]

def scrape_all_gradebooks():
    print("=" * 80)
    print("      MENTARI LMS - SCRAPING REKAP NILAI (GRADE BOOK) 8 MATA KULIAH")
    print("=" * 80)

    if not AUTH_PATH.exists():
        print("[!] File data/auth.json tidak ditemukan.")
        return

    all_gradebooks = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        
        # Intercept network API response for grade-book
        current_data = {}
        def on_response(res):
            url = res.url
            if "/api/user-course/" in url and "/grade-book" in url:
                try:
                    ctype = res.headers.get("content-type", "")
                    if "json" in ctype:
                        current_data["data"] = res.json()
                except Exception:
                    pass

        ctx.on("response", on_response)
        page = ctx.new_page()

        print("[*] Memverifikasi Dashboard Mentari...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        for _ in range(15):
            title = page.title()
            if "Just a moment" not in title and title:
                break
            time.sleep(1)

        print("[*] Dashboard terverifikasi!")

        for idx, c in enumerate(COURSES, 1):
            name = c["name"]
            code = c["code"]
            gb_url = f"https://mentari.unpam.ac.id/u-courses/{code}/grade-book"
            print(f"\n[{idx}/8] Mengakses Rekap Nilai: {name} ...")
            print(f"      URL: {gb_url}")
            
            current_data.clear()
            page.goto(gb_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3500)

            # Jika belum tertangkap via event, coba ambil dari page DOM / table
            gb_record = {
                "course_name": name,
                "course_code": code,
                "url": gb_url,
                "student_info": {},
                "components": []
            }

            api_result = current_data.get("data")
            if api_result and isinstance(api_result, list) and len(api_result) > 0:
                user_record = api_result[0]
                gb_record["student_info"] = {
                    "nim": user_record.get("nim"),
                    "nama_mahasiswa": user_record.get("nama_mahasiswa"),
                    "email": user_record.get("alamat_email")
                }
                for item in user_record.get("sub_course_template", []):
                    gb_record["components"].append({
                        "kode": item.get("kode_template"),
                        "judul": item.get("judul"),
                        "score": item.get("score"),
                        "completion": item.get("completion"),
                        "total": item.get("total")
                    })
                print(f"      [V] Sukses via API! Mahasiswa: {user_record.get('nama_mahasiswa')}")
                for cmp in gb_record["components"]:
                    if cmp["completion"] > 0 or cmp["score"] is not None:
                        skor_str = f"Skor: {cmp['score']}" if cmp['score'] is not None else "Sudah Dikerjakan"
                        print(f"          • {cmp['judul']}: {cmp['completion']}/{cmp['total']} ({skor_str})")
            else:
                # Fallback: Ambil data dari tabel HTML
                tables = page.locator("table").all()
                if tables:
                    tbl = tables[0]
                    headers = [th.inner_text().strip() for th in tbl.locator("th").all()]
                    cells = [td.inner_text().strip() for td in tbl.locator("td").all()]
                    for h, val in zip(headers, cells):
                        gb_record["components"].append({
                            "judul": h,
                            "raw_value": val
                        })
                    print(f"      [V] Sukses via HTML Table ({len(gb_record['components'])} kolom)")
                else:
                    print("      [!] Gagal menangkap data rekap nilai.")

            all_gradebooks[name] = gb_record

        browser.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_gradebooks, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"[V] SELURUH REKAP NILAI BERHASIL DIPINDAI & DISIMPAN!")
    print(f"    File: {OUTPUT_PATH}")
    print("=" * 80)

if __name__ == "__main__":
    scrape_all_gradebooks()
