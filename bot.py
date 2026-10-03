import argparse
import sys
import json
from pathlib import Path

# Pastikan konsol Windows mendukung encoding UTF-8 tanpa error karakter/emoji
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

from services.auth import is_auth_saved, get_auth_file_path, check_session_validity, extract_stored_credentials
from services.scraper import extract_user_profile, extract_courses, extract_pending_activities, load_forum_ai_drafts

DEEP_DATA_FILE = Path(__file__).resolve().parent / "data" / "mentari_deep_data.json"


def print_banner():
    print("=" * 75)
    print("         MENTARI LMS AUTOMATION BOT - COMMAND & MONITOR CENTER")
    print("=" * 75)


def display_forums():
    print_banner()
    if not DEEP_DATA_FILE.exists():
        print("[!] Data penelusuran belum ada. Silakan jalankan: python explore_courses.py terlebih dahulu.\n")
        return

    with open(DEEP_DATA_FILE, "r", encoding="utf-8") as f:
        courses = json.load(f)

    print("\n[ DAFTAR FORUM DISKUSI TERDETEKSI DI SEMUA MATA KULIAH ]\n")
    total_forums = 0

    for c in courses:
        c_name = c.get("course_name")
        c_forums = []
        for m in c.get("meetings", []):
            if m.get("forum"):
                c_forums.append((m.get("pertemuan"), m.get("forum"), m.get("ai_drafts", [])))

        if c_forums:
            print(f"📘 {c_name}:")
            for p_num, f_list, drafts in c_forums:
                total_forums += len(f_list)
                print(f"   └── [Pertemuan {p_num:02d}]: {', '.join(f_list)}")
                if drafts:
                    for d in drafts:
                        print(f"       💬 Draf AI: {d.get('draft', '')[:100]}...\n")
            print()

    print(f"[*] Total Forum Diskusi Terdeteksi: {total_forums} item.")


def display_quizzes():
    print_banner()
    if not DEEP_DATA_FILE.exists():
        print("[!] Data penelusuran belum ada. Silakan jalankan: python explore_courses.py terlebih dahulu.\n")
        return

    with open(DEEP_DATA_FILE, "r", encoding="utf-8") as f:
        courses = json.load(f)

    print("\n[ DAFTAR KUIS / QUIZ TERDETEKSI DI SEMUA MATA KULIAH ]\n")
    total_quizzes = 0

    for c in courses:
        c_name = c.get("course_name")
        quiz_meetings = [m.get("pertemuan") for m in c.get("meetings", []) if m.get("kuis")]
        total_quizzes += len(quiz_meetings)
        print(f"📝 {c_name}:")
        print(f"   └── Kuis Terdeteksi di Pertemuan: {', '.join(str(p) for p in quiz_meetings)}\n")

    print(f"[*] Total Kuis Terdeteksi: {total_quizzes} sesi kuis.")


def run_bot(watch_mode: bool = False):
    print_banner()

    # 1. Validasi file sesi
    if not is_auth_saved():
        print("\n[!] File sesi 'data/auth.json' belum ditemukan!")
        print("    Silakan jalankan script berikut terlebih dahulu untuk login satu kali:")
        print("    -> python save_auth.py\n")
        sys.exit(1)

    auth_path = get_auth_file_path()
    cred_summary = extract_stored_credentials()
    print(f"[*] Memuat sesi autentikasi dari: {auth_path}")
    print(f"    - Mahasiswa            : {cred_summary.get('fullname', 'SOFYAN AGUNG')} ({cred_summary.get('username', '231011400159')})")
    print(f"    - Role                 : {cred_summary.get('role', 'MAHASISWA')}")

    # Mode visual atau headless
    headless = not watch_mode
    slow_mo = 500 if watch_mode else 0
    mode_text = "VISUAL (--watch, slow_mo=500ms)" if watch_mode else "HEADLESS (Latar Belakang)"
    print(f"[*] Mode Browser           : {mode_text}")

    launch_args = ["--disable-blink-features=AutomationControlled"]
    if watch_mode:
        launch_args.append("--start-maximized")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=headless,
                slow_mo=slow_mo,
                channel="chrome",
                args=launch_args
            )
        except Exception:
            browser = p.chromium.launch(
                headless=headless,
                slow_mo=slow_mo,
                args=launch_args
            )

        context = browser.new_context(
            storage_state=auth_path,
            viewport={"width": 1366, "height": 768} if not watch_mode else None,
            no_viewport=True if watch_mode else False
        )

        page = context.new_page()
        target_url = "https://mentari.unpam.ac.id"
        print(f"[*] Menghubungi {target_url}...")

        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[X] Gagal memuat halaman: {e}")
            browser.close()
            return

        # 2. Verifikasi status sesi
        print("[*] Memeriksa validitas sesi aktif...")
        if not check_session_validity(page):
            print("\n[!] Sesi telah kedaluwarsa atau diarahkan ke halaman login!")
            print("    Silakan perbarui sesi login Anda dengan menjalankan:")
            print("    -> python save_auth.py\n")
            browser.close()
            return

        print("[V] Sesi valid! Berhasil terhubung ke Mentari UNPAM.\n")

        # 3. Ekstraksi Data Dashboard & Database
        user_info = extract_user_profile(page)
        courses = extract_courses(page)
        activities = extract_pending_activities(page)

        # 4. Tampilkan Ringkasan Rapi
        print("-" * 75)
        print(f"  MAHASISWA   : {cred_summary.get('fullname', user_info.get('name'))}")
        print(f"  NIM         : {cred_summary.get('username', user_info.get('nim'))}")
        print(f"  KELAS       : 07TPLP003 (Teknik Informatika)")
        print(f"  PORTAL URL  : {page.url}")
        print("-" * 75)

        # Tabel Mata Kuliah
        print("\n[ 8 MATA KULIAH AKTIF KELAS 07TPLP003 ]")
        if courses:
            for idx, c in enumerate(courses, 1):
                print(f"  {idx:02d}. {c['title']}")
                if c.get("details"):
                    print(f"      Ket: {c['details']}")
        else:
            print("  (Memuat mata kuliah dari database...")

        # Ringkasan Aktivitas Terdata
        forums = [a for a in activities if a["type"] == "FORUM"]
        quizzes = [a for a in activities if a["type"] == "KUIS"]
        tasks = [a for a in activities if a["type"] == "TUGAS"]

        print("\n[ RINGKASAN AKTIVITAS AKADEMIK TERDETEKSI ]")
        print(f"  💬 Total Forum Diskusi : {len(forums)} forum")
        print(f"  📝 Total Sesi Kuis     : {len(quizzes)} kuis")
        print(f"  📌 Total Tugas         : {len(tasks)} tugas")

        print("\n" + "=" * 75)
        print("[*] Pemantauan selesai. Menutup browser...")
        browser.close()


def main():
    parser = argparse.ArgumentParser(
        description="Bot Otomasi dan Pemantau Mentari LMS UNPAM berbasis Playwright & Gemini."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Jalankan browser dalam mode visual (headless=False dengan slow_mo 500ms)."
    )
    parser.add_argument(
        "--list-forums",
        action="store_true",
        help="Tampilkan daftar seluruh forum diskusi beserta draf tanggapan AI Gemini."
    )
    parser.add_argument(
        "--list-quizzes",
        action="store_true",
        help="Tampilkan daftar seluruh sesi kuis yang terdeteksi di setiap pertemuan."
    )
    args = parser.parse_args()

    if args.list_forums:
        display_forums()
    elif args.list_quizzes:
        display_quizzes()
    else:
        run_bot(watch_mode=args.watch)


if __name__ == "__main__":
    main()
