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

from services.ai_solver import draft_forum_discussion

AUTH_PATH = Path("data/auth.json").resolve()
OUTPUT_DATA_PATH = Path("data/courses_summary.json").resolve()
DEEP_REPORT_PATH = Path("data/mentari_deep_data.json").resolve()

# Daftar kata kunci label sistem yang bukan nama mata kuliah
EXCLUDED_LABELS = {
    "dashboard", "kode kelas", "sks", "dosen", "hari", "keluar", 
    "notifikasi", "ruang", "semester", "mentari", "unpam", "jadwal"
}


def clean_text(text: str) -> str:
    """Membersihkan whitespace ganda dan newline."""
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " | ".join(lines)


def run_intelligent_explorer():
    print("=" * 80)
    print("      MENTARI LMS - SMART AUTONOMOUS AGENT (DEEP EXPLORER & TASK ACTION)")
    print("=" * 80)

    if not AUTH_PATH.exists():
        print("[!] File data/auth.json tidak ditemukan. Jalankan save_auth.py terlebih dahulu.")
        return

    print("[*] Meluncurkan Google Chrome dalam mode visual...")
    print("[*] Bot akan membuka setiap dari 8 mata kuliah, membuka akordion, dan mengklik Forum/Tugas.")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                slow_mo=600,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )
        except Exception:
            browser = p.chromium.launch(
                headless=False,
                slow_mo=600,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )

        context = browser.new_context(
            storage_state=str(AUTH_PATH),
            no_viewport=True
        )
        page = context.new_page()

        # 1. Buka Halaman Utama Mentari (Dashboard)
        dashboard_url = "https://mentari.unpam.ac.id"
        print(f"\n[*] Mengakses Dashboard Mentari: {dashboard_url} ...")
        page.goto(dashboard_url, wait_until="domcontentloaded", timeout=60000)

        # Tunggu verifikasi Cloudflare jika ada
        for i in range(15):
            title = page.title()
            if "Just a moment" not in title and title != "":
                print(f"[V] Berhasil masuk! Judul: '{title}'")
                break
            time.sleep(1)

        page.wait_for_timeout(4000)

        # 2. Buka Menu Perkuliahan jika ada
        menu_selectors = [
            'a:has-text("Perkuliahan")',
            'a:has-text("Mata Kuliah")',
            'a:has-text("Kelas Saya")',
            'a:has-text("Kelas Kuliah")',
            'button:has-text("Perkuliahan")',
            'button:has-text("Kelas")',
        ]

        for sel in menu_selectors:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                try:
                    txt = loc.first.inner_text().strip()
                    print(f"[*] Mengklik menu navigasi: '{txt}'")
                    loc.first.click()
                    page.wait_for_timeout(3000)
                    break
                except Exception:
                    pass

        # 3. Kumpulkan 8 Mata Kuliah Asli Kelas 07TPLP003
        print("\n[*] Mendeteksi kartu mata kuliah Anda (Kelas 07TPLP003)...")
        page.wait_for_timeout(2000)

        raw_course_names = []
        card_locs = page.locator('div:has-text("07TPLP003"):has-text("SKS")').all()

        for c in card_locs:
            try:
                lines = [l.strip() for l in c.inner_text().splitlines() if l.strip()]
                if lines:
                    c_name = lines[0]
                    # Pastikan nama matkul bukan label seperti 'Kode Kelas', 'SKS', dll.
                    if (
                        c_name.lower() not in EXCLUDED_LABELS
                        and len(c_name) > 3
                        and c_name not in raw_course_names
                    ):
                        raw_course_names.append(c_name)
            except Exception:
                pass

        # Validasi daftar 8 mata kuliah Anda
        print(f"\n[V] BERHASIL MENGIDENTIFIKASI {len(raw_course_names)} MATA KULIAH AKTIF:")
        for idx, name in enumerate(raw_course_names, 1):
            print(f"    {idx}. {name}")

        if not raw_course_names:
            print("[!] Tidak ada mata kuliah yang terdeteksi di dashboard.")
            browser.close()
            return

        full_curriculum_data = []

        # 4. Kunjungi Setiap Mata Kuliah Satu per Satu Secara Tepat
        for c_idx, course_name in enumerate(raw_course_names, 1):
            print("\n" + "=" * 80)
            print(f" [{c_idx}/{len(raw_course_names)}] MEMPROSES MATA KULIAH: {course_name}")
            print("=" * 80)

            # Selalu pastikan kita berada di dashboard sebelum mengklik kartu matkul
            if page.url != dashboard_url and not page.url.endswith("/"):
                print(f"[*] Kembali ke dashboard...")
                page.goto(dashboard_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(2500)

            # Klik kartu mata kuliah yang spesifik berdasarkan nama judulnya
            print(f"[*] Mengklik kartu: {course_name} ...")
            try:
                # Cari elemen kartu yang memuat nama matkul ini
                course_click_el = page.get_by_text(course_name, exact=False).first
                course_click_el.scroll_into_view_if_needed()
                course_click_el.click()
                page.wait_for_timeout(3500)
            except Exception as e:
                print(f"[!] Gagal klik kartu {course_name}: {e}")
                continue

            current_course_url = page.url
            print(f"[V] Berada di halaman kelas: {current_course_url}")

            # 5. Buka Akordion Pertemuan 1 s/d 16
            print("[*] Memindai dan membuka seluruh sesi pertemuan...")
            
            # Coba klik tombol 'Buka Semua' / 'Expand All' jika ada
            expand_btn = page.locator('button:has-text("Buka Semua"), button:has-text("Expand All"), a:has-text("Buka Semua")').first
            if expand_btn.count() > 0 and expand_btn.is_visible():
                try:
                    expand_btn.click()
                    page.wait_for_timeout(1500)
                except Exception:
                    pass

            course_meetings = []
            consecutive_misses = 0

            # Loop pertemuan dinamis hingga 25 (mendukung mata kuliah dengan 14, 16, 18, atau 21 pertemuan)
            for p_num in range(1, 26):
                p_header = page.locator(f'text=/^\\s*Pertemuan\\s+{p_num}\\b/i').first
                if p_header.count() > 0:
                    consecutive_misses = 0
                    try:
                        p_header.scroll_into_view_if_needed()
                        p_header.click()
                        page.wait_for_timeout(700)
                    except Exception:
                        pass

                    # Deteksi tombol spesifik Forum, Tugas, dan Kuis
                    meeting_info = {
                        "pertemuan": p_num,
                        "forum": [],
                        "kuis": [],
                        "tugas": [],
                        "ai_drafts": []
                    }

                    # Cari tombol/link Forum Diskusi
                    try:
                        forum_loc = page.locator(f'div:has-text("Pertemuan {p_num}") a:has-text("FORUM"), div:has-text("Pertemuan {p_num}") button:has-text("FORUM"), div:has-text("Pertemuan {p_num}") a:has-text("Forum"), div:has-text("Pertemuan {p_num}") button:has-text("Forum")')
                        if forum_loc.count() > 0:
                            for i in range(forum_loc.count()):
                                el = forum_loc.nth(i)
                                t = clean_text(el.inner_text())
                                if "forum" in t.lower() and len(t) < 50:
                                    meeting_info["forum"].append({"title": t, "element": el})
                                    break
                    except Exception:
                        pass

                    # Cari tombol/link Tugas
                    try:
                        tugas_loc = page.locator(f'div:has-text("Pertemuan {p_num}") a:has-text("TUGAS"), div:has-text("Pertemuan {p_num}") button:has-text("TUGAS"), div:has-text("Pertemuan {p_num}") a:has-text("Tugas"), div:has-text("Pertemuan {p_num}") button:has-text("Tugas")')
                        if tugas_loc.count() > 0:
                            for i in range(tugas_loc.count()):
                                el = tugas_loc.nth(i)
                                t = clean_text(el.inner_text())
                                if "tugas" in t.lower() and len(t) < 50:
                                    meeting_info["tugas"].append({"title": t, "element": el})
                                    break
                    except Exception:
                        pass

                    # Cari tombol/link Kuis
                    try:
                        kuis_loc = page.locator(f'div:has-text("Pertemuan {p_num}") a:has-text("KUIS"), div:has-text("Pertemuan {p_num}") button:has-text("KUIS"), div:has-text("Pertemuan {p_num}") a:has-text("Quiz"), div:has-text("Pertemuan {p_num}") button:has-text("Quiz")')
                        if kuis_loc.count() > 0:
                            for i in range(kuis_loc.count()):
                                el = kuis_loc.nth(i)
                                t = clean_text(el.inner_text())
                                if any(k in t.lower() for k in ["kuis", "quiz"]) and len(t) < 50:
                                    meeting_info["kuis"].append({"title": t, "element": el})
                                    break
                    except Exception:
                        pass

                    has_act = meeting_info["forum"] or meeting_info["kuis"] or meeting_info["tugas"]
                    if has_act:
                        print(f"    -> [Pertemuan {p_num:02d}]: Terbuka!")
                        if meeting_info["forum"]:
                            print(f"       💬 Forum Diskusi Terdeteksi!")
                        if meeting_info["kuis"]:
                            print(f"       📝 Kuis Terdeteksi!")
                        if meeting_info["tugas"]:
                            print(f"       📌 Tugas Terdeteksi!")
                    else:
                        print(f"    -> [Pertemuan {p_num:02d}]: Terbuka (Materi pembelajaran)")

                    serializable_meeting = {
                        "pertemuan": p_num,
                        "forum": [x["title"] for x in meeting_info["forum"]],
                        "kuis": [x["title"] for x in meeting_info["kuis"]],
                        "tugas": [x["title"] for x in meeting_info["tugas"]],
                        "ai_drafts": []
                    }

                    # 6. ACTION: BUKA FORUM & SUSUN DRAF AI
                    if meeting_info["forum"]:
                        target_forum_btn = meeting_info["forum"][0]["element"]
                        try:
                            print(f"       [ACTION] Mengklik masuk ke Forum Pertemuan {p_num}...")
                            target_forum_btn.scroll_into_view_if_needed()
                            target_forum_btn.click()
                            page.wait_for_timeout(3000)

                            print(f"       [FORUM URL] {page.url}")

                            # Baca konten teks pemantik diskusi dari dosen
                            prompt_text = ""
                            # Coba beberapa selector umum teks soal forum
                            content_candidates = [
                                page.locator('.forum-content'),
                                page.locator('.discussion-content'),
                                page.locator('article'),
                                page.locator('.card:has-text("Dosen")'),
                                page.locator('main p'),
                            ]
                            for cand in content_candidates:
                                if cand.count() > 0:
                                    t = cand.first.inner_text().strip()
                                    if len(t) > 20:
                                        prompt_text = t
                                        break

                            if not prompt_text:
                                prompt_text = f"Topik diskusi mata kuliah {course_name} (Pertemuan {p_num})"

                            print(f"       [TOPIK FORUM] {prompt_text[:120]}...")

                            # Susun draf dengan AI Gemini
                            print("       [AI ENGINE] Menyusun draf tanggapan formal dengan Gemini...")
                            ai_draft = draft_forum_discussion(
                                topic=prompt_text,
                                context=f"Mata Kuliah: {course_name} (Pertemuan {p_num})"
                            )
                            serializable_meeting["ai_drafts"].append({
                                "prompt": prompt_text[:200],
                                "draft": ai_draft
                            })
                            print("       [V] Draf tanggapan AI berhasil dibuat dan disimpan!")

                            # Kembali ke halaman kelas
                            page.goto(current_course_url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_timeout(2000)
                        except Exception as e:
                            print(f"       [!] Gagal memproses forum: {e}")
                            page.goto(current_course_url, wait_until="domcontentloaded", timeout=30000)

                    # 7. ACTION: BUKA TUGAS JIKA ADA
                    if meeting_info["tugas"]:
                        target_tugas_btn = meeting_info["tugas"][0]["element"]
                        try:
                            print(f"       [ACTION] Mengklik masuk ke Tugas Pertemuan {p_num}...")
                            target_tugas_btn.scroll_into_view_if_needed()
                            target_tugas_btn.click()
                            page.wait_for_timeout(3000)
                            print(f"       [TUGAS URL] {page.url}")
                            # Kembali ke halaman kelas
                            page.goto(current_course_url, wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_timeout(2000)
                        except Exception as e:
                            print(f"       [!] Gagal memproses tugas: {e}")
                            page.goto(current_course_url, wait_until="domcontentloaded", timeout=30000)

                    course_meetings.append(serializable_meeting)
                else:
                    consecutive_misses += 1
                    if p_num >= 14 and consecutive_misses >= 3:
                        break

            course_record = {
                "course_name": course_name,
                "url": current_course_url,
                "total_meetings": len(course_meetings),
                "meetings": course_meetings
            }
            full_curriculum_data.append(course_record)
            print(f"[V] Selesai menganalisis mata kuliah: {course_name}.")

        # 8. Simpan Database Lengkap
        DEEP_REPORT_PATH.parent.mkdir(exist_ok=True)
        with open(DEEP_REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(full_curriculum_data, f, indent=2, ensure_ascii=False)

        with open(OUTPUT_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump([{
                "name": c["course_name"],
                "meetings_count": c["total_meetings"],
                "url": c["url"]
            } for c in full_curriculum_data], f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 80)
        print(" [V] PENELUSURAN LENGKAP SELURUH 8 MATA KULIAH TELAH TUNTAS!")
        print(f" [*] Database tersimpan di: {DEEP_REPORT_PATH.resolve()}")
        print("=" * 80)
        print("\n[!] BROWSER DIBIARKAN TETAP TERBUKA AGAR ANDA DAPAT MENINJAU HASILNYA.")
        
        try:
            input("\n>> Tekan ENTER di sini jika Anda sudah selesai dan ingin menutup browser: ")
        except (EOFError, KeyboardInterrupt):
            page.wait_for_timeout(10000)

        browser.close()
        print("[*] Browser ditutup. Selesai.")


if __name__ == "__main__":
    run_intelligent_explorer()
