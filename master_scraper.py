import os
import sys
import json
import time
import re
from pathlib import Path

# Pastikan konsol Windows mendukung encoding UTF-8 tanpa error karakter/emoji
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

AUTH_PATH = Path("data/auth.json").resolve()
OUTPUT_PATH = Path("data/mentari_master_audit.json").resolve()

# Daftar 8 Mata Kuliah Aktif Mahasiswa (Kelas 07TPLP003)
COURSES = [
    {
        "id": "22TIF0312",
        "name": "MANAJEMEN PROYEK INFORMATIKA",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312",
        "total_meetings": 14
    },
    {
        "id": "22TIF0373",
        "name": "ARSITEKTUR DAN ORGANISASI KOMPUTER",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0373",
        "total_meetings": 16
    },
    {
        "id": "22TIF0382",
        "name": "KEAMANAN KOMPUTER",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0382",
        "total_meetings": 14
    },
    {
        "id": "22TIF0392",
        "name": "JARINGAN NIRKABEL",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0392",
        "total_meetings": 14
    },
    {
        "id": "22TIF0402",
        "name": "KECAKAPAN ANTAR PERSONAL",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0402",
        "total_meetings": 14
    },
    {
        "id": "22TIF0412",
        "name": "TESTING DAN QA PERANGKAT LUNAK",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0412",
        "total_meetings": 14
    },
    {
        "id": "22TIF0422",
        "name": "ETIKA PROFESI",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0422",
        "total_meetings": 14
    },
    {
        "id": "22TIF0433",
        "name": "PEMROGRAMAN WEB II",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0433",
        "total_meetings": 16
    }
]


def clean_text(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " | ".join(lines)


def classify_card(title: str, text: str, buttons: list[str]) -> str:
    title_lower = title.lower().strip()
    full_lower = (title + " " + text).lower()

    # Prioritas 1: Jika judul secara eksplisit menyatakan jenis modul
    if any(k in title_lower for k in ["posttest", "post test", "post-test"]):
        return "POSTTEST"
    if any(k in title_lower for k in ["pretest", "pre test", "pre-test"]):
        return "PRETEST"
    if "kuesioner" in title_lower:
        return "KUESIONER"
    if "forum" in title_lower:
        return "FORUM"
    if any(k in title_lower for k in ["tugas", "penugasan"]):
        return "TUGAS"

    # Prioritas 2: Pengecekan kondisi KUNCI PRASYARAT (Restriction note)
    # Jika kartu bukan pretest dan bertuliskan 'Silakan selesaikan "Pretest" terlebih dahulu' -> POST-TEST
    if "selesaikan" in full_lower and "pretest" in full_lower and not any(k in title_lower for k in ["pretest", "pre-test", "pre test"]):
        return "POSTTEST"
    # Jika kartu bertuliskan 'Silakan selesaikan "Posttest" terlebih dahulu' -> KUESIONER
    if "selesaikan" in full_lower and any(k in full_lower for k in ["posttest", "post test", "post-test"]):
        return "KUESIONER"

    # Prioritas 3: Deteksi dari body dan tombol
    if any(k in full_lower for k in ["posttest", "post test", "post-test"]):
        return "POSTTEST"
    elif any(k in full_lower for k in ["pretest", "pre test", "pre-test"]):
        return "PRETEST"
    elif "kuesioner" in full_lower or "KUESIONER" in buttons:
        return "KUESIONER"
    elif "forum" in full_lower or "FORUM" in buttons:
        return "FORUM"
    elif any(k in full_lower for k in ["tugas", "penugasan"]) or "ASSIGNMENT" in buttons:
        return "TUGAS"
    elif any(k in full_lower for k in ["buku isbn", "power point", "video ajar", "artikel riset", "materi lainnya", "modul", "ppt"]) or "FILE" in buttons:
        return "MATERI"
    elif "vcon" in full_lower:
        return "VCON"
    elif "QUIZ" in buttons:
        return "QUIZ"
    return "LAINNYA"


def scan_single_meeting(page, p_num: int) -> dict:
    """Memindai seluruh kartu dan komponen pembelajaran pada 1 pertemuan."""
    p_header = page.locator(f'text=/^\\s*Pertemuan\\s+{p_num}\\b/i').first
    if p_header.count() == 0:
        return None

    try:
        p_header.scroll_into_view_if_needed()
        p_header.click()
        page.wait_for_timeout(1800)
    except Exception:
        return None

    # Ambil semua kartu konten yang aktif (bukan di sidebar Course Index)
    raw_cards = page.locator('.MuiPaper-root:not(:has-text("Course Index"))').all()

    meeting_data = {
        "pertemuan": p_num,
        "materi": [],
        "pretest": None,
        "forum": None,
        "posttest": None,
        "kuesioner": None,
        "tugas": [],
        "vcon": None,
        "total_komponen": 0
    }

    for c in raw_cards:
        txt = c.inner_text().strip()
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        if not lines:
            continue

        title = lines[0]
        # Lewati header global jika ada
        if any(skip in title.upper() for skip in ["DASHBOARD", "COURSE", "PARTICIPANT"]):
            continue

        # Ambil tombol di kartu ini
        btns = [b.inner_text().strip() for b in c.locator("button, a").all() if b.is_visible() and b.inner_text().strip()]
        card_type = classify_card(title, txt, btns)
        desc = " | ".join(lines[1:]) if len(lines) > 1 else ""

        card_info = {
            "title": title,
            "description": desc,
            "buttons": btns,
            "type": card_type
        }

        meeting_data["total_komponen"] += 1

        if card_type == "PRETEST":
            meeting_data["pretest"] = card_info
        elif card_type == "POSTTEST":
            meeting_data["posttest"] = card_info
        elif card_type == "KUESIONER":
            meeting_data["kuesioner"] = card_info
        elif card_type == "FORUM":
            meeting_data["forum"] = card_info
        elif card_type == "TUGAS":
            meeting_data["tugas"].append(card_info)
        elif card_type == "MATERI":
            meeting_data["materi"].append(card_info)
        elif card_type == "VCON":
            meeting_data["vcon"] = card_info

    return meeting_data


def run_master_scraper():
    print("=" * 80)
    print("      MENTARI LMS - MASTER DEEP SCRAPER & ACADEMIC AUDITOR")
    print("=" * 80)
    print("[*] Melakukan inspeksi total terhadap 8 Mata Kuliah & seluruh pertemuan.")
    print("[*] Mengidentifikasi 6 pilar pembelajaran: Materi -> Pretest -> Fordis -> Posttest -> Kuesioner -> Tugas.")
    print("=" * 80)

    if not AUTH_PATH.exists():
        print("[!] File data/auth.json tidak ditemukan. Jalankan save_auth.py terlebih dahulu.")
        return

    all_courses_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            slow_mo=300,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = context.new_page()

        # 1. Buka dashboard untuk memastikan Cloudflare Turnstile beres
        print("\n[*] Menghubungkan ke Mentari LMS Dashboard...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        for i in range(15):
            title = page.title()
            if "Just a moment" not in title and title != "":
                print(f"[V] Dashboard Terverifikasi! Judul: '{title}'")
                break
            time.sleep(1)

        page.wait_for_timeout(2500)

        # 2. Iterasi Setiap Mata Kuliah
        for c_idx, course in enumerate(COURSES, 1):
            print("\n" + "=" * 80)
            print(f" [{c_idx}/{len(COURSES)}] MEMINDAI MATA KULIAH: {course['name']}")
            print(f"       URL: {course['url']}")
            print("=" * 80)

            page.goto(course["url"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)

            course_record = {
                "course_id": course["id"],
                "course_name": course["name"],
                "url": course["url"],
                "meetings": []
            }

            consecutive_misses = 0
            # Pindai setiap pertemuan hingga batas total atau sampai tidak ada header lagi
            max_limit = course["total_meetings"] + 4
            for p_num in range(1, max_limit):
                res = scan_single_meeting(page, p_num)
                if res and res["total_komponen"] > 0:
                    consecutive_misses = 0
                    course_record["meetings"].append(res)

                    # Ringkasan status komponen pertemuan
                    m_count = len(res["materi"])
                    has_pre = "V" if res["pretest"] else "-"
                    has_for = "V" if res["forum"] else "-"
                    has_post = "V" if res["posttest"] else "-"
                    has_kues = "V" if res["kuesioner"] else "-"
                    t_count = len(res["tugas"])

                    print(f"    -> [Pertemuan {p_num:02d}]: Materi={m_count} | Pre-test={has_pre} | Fordis={has_for} | Post-test={has_post} | Kuesioner={has_kues} | Tugas={t_count}")
                    if res["forum"] and res["forum"]["description"]:
                        desc_brief = res["forum"]["description"].replace("\n", " ")[:65]
                        print(f"       💬 Fordis Topic: {desc_brief}...")
                else:
                    consecutive_misses += 1
                    if consecutive_misses >= 3:
                        break

            all_courses_data.append(course_record)
            print(f"[V] Selesai memindai {course['name']}: {len(course_record['meetings'])} pertemuan tercatat.")

        browser.close()

    # Simpan hasil scraping total ke JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_courses_data, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"[V] SCRAPING TOTAL SELESAI!")
    print(f"[*] Database Audit Lengkap tersimpan ke: {OUTPUT_PATH}")
    print("=" * 80)

    # Sinkronisasi Rekap Nilai Resmi (Grade Book)
    try:
        from scrape_gradebooks import scrape_all_gradebooks
        print("\n[*] Melanjutkan pemindaian Rekap Nilai (Grade Book) 8 Mata Kuliah...")
        scrape_all_gradebooks()
    except Exception as e:
        print(f"[!] Pemindaian Grade Book dilewati: {e}")

    # Sinkronisasi Nilai Kuis Per Pertemuan (Pre-Test & Post-Test)
    try:
        from scrape_meeting_grades import scrape_all_meeting_grades
        print("\n[*] Melanjutkan pemindaian Nilai Kuis Per Pertemuan (Pre & Post Test)...")
        scrape_all_meeting_grades()
    except Exception as e:
        print(f"[!] Pemindaian Nilai Kuis Per Pertemuan dilewati: {e}")


if __name__ == "__main__":
    run_master_scraper()
