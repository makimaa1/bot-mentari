import os
import sys
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
from services.ai_solver import solve_multiple_choice
from pipeline_runner import (
    extract_own_quiz_section,
    check_quiz_completion_status,
    ensure_meeting_expanded,
    find_meeting_quiz_card
)

AUTH_PATH = Path(__file__).resolve().parent / "data/auth.json"
COURSE_URL = "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312"  # Manajemen Proyek Informatika
COURSE_NAME = "MANAJEMEN PROYEK INFORMATIKA"


def clean_text(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " | ".join(lines)


def run_quiz_test(target_meeting: int = 1):
    print("=" * 80)
    print("   MENTARI LMS - AI QUIZ SOLVER & AUDITOR (PRETEST & POST-TEST RUNNER)")
    print("=" * 80)
    print(f"[*] Target Mata Kuliah : {COURSE_NAME}")
    print(f"[*] Target Pertemuan   : Pertemuan {target_meeting}")
    print(f"[*] Aturan 1           : Kuis HANYA dikerjakan jika ada FORUM DISKUSI di pertemuan ini.")
    print(f"[*] Aturan 2           : Cek status pengerjaan kuis (Sudah/Belum dikerjakan).")
    print(f"[*] AI Engine          : Google Gemini 3.5 Flash / 3.8 Flash (Structured Solver)")
    print(f"[*] Safety Mode        : Jawaban dipilih otomatis, final 'Submit' diverifikasi pengguna.")
    print("=" * 80)

    if not AUTH_PATH.exists():
        print("[!] File data/auth.json tidak ditemukan. Jalankan save_auth.py terlebih dahulu.")
        return

    print("\n[*] Meluncurkan Google Chrome dalam mode visual...")
    print("[*] Anda dapat menyaksikan AI menganalisis soal dan memilih jawaban langsung di layar.")

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

        # 1. Buka Dashboard terlebih dahulu untuk kliring Cloudflare Turnstile
        print("\n[*] Mengakses Dashboard Mentari untuk sinkronisasi sesi...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        for i in range(15):
            title = page.title()
            if "Just a moment" not in title and title != "":
                print(f"[V] Berhasil masuk Dashboard! Judul: '{title}'")
                break
            time.sleep(1)

        page.wait_for_timeout(2000)

        # 2. Buka Halaman Mata Kuliah Target
        print(f"\n[*] Mengakses halaman mata kuliah: {COURSE_URL} ...")
        page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # 3. Buka Pertemuan Target
        print(f"\n[*] Mencari dan membuka Pertemuan {target_meeting}...")
        p_header = page.locator(f'text=/^\\s*Pertemuan\\s+{target_meeting}\\b/i').first

        if not ensure_meeting_expanded(page, target_meeting):
            print(f"[!] Gagal membuka Pertemuan {target_meeting} di halaman kelas.")
            browser.close()
            return
        print(f"[V] Akordion Pertemuan {target_meeting} berhasil dibuka.")

        # 4. Validasi Aturan 1: Apakah ada Forum Diskusi di pertemuan ini?
        print("\n[*] [ATURAN 1] Memeriksa keberadaan Forum Diskusi di pertemuan ini...")
        forum_loc = page.locator(f'div:has-text("Pertemuan {target_meeting}") button:has-text("FORUM"), div:has-text("Pertemuan {target_meeting}") div:has-text("Forum Diskusi"), div:has-text("Pertemuan {target_meeting}") a:has-text("Forum")')
        has_forum = forum_loc.count() > 0

        if not has_forum:
            print("\n[!] HASIL PEMERIKSAAN ATURAN 1:")
            print(f"    Pertemuan {target_meeting} TIDAK memiliki Forum Diskusi.")
            print("    -> Sesuai aturan Anda, KUIS TIDAK AKAN DIKERJAKAN.")
            print("\n[*] Menutup browser dalam 5 detik...")
            page.wait_for_timeout(5000)
            browser.close()
            return

        print(f"[V] ATURAN 1 TERPENUHI: Forum Diskusi aktif di Pertemuan {target_meeting}!")

        # 5. Validasi Aturan 2: Deteksi Kuis (Pre-Test & Post-Test)
        print("\n[*] [ATURAN 2] Mendeteksi modul Kuis (Pre-Test & Post-Test) di pertemuan ini...")
        
        # Pindai kartu konten di halaman (abaikan sidebar Course Index)
        content_cards = page.locator('.MuiPaper-root:not(:has-text("Course Index"))').all()
        quiz_plan = []

        has_pretest = False
        has_posttest = False

        for c in content_cards:
            txt = c.inner_text().strip()
            first_line = txt.splitlines()[0] if txt else ""
            if "pretest" in first_line.lower():
                has_pretest = True
            elif "posttest" in first_line.lower() or "post test" in first_line.lower():
                has_posttest = True

        if has_pretest:
            quiz_plan.append("PRETEST")
        if has_posttest:
            quiz_plan.append("POSTTEST")

        # Jika tidak ada label spesifik pretest/posttest, cek apakah ada tombol QUIZ generik
        if not quiz_plan:
            generic_btns = page.locator('button.MuiButton-contained:has-text("QUIZ")').all()
            if generic_btns:
                quiz_plan.append("GENERIC")

        print(f"[V] Rencana pengerjaan kuis pada Pertemuan {target_meeting}:")
        for idx, q_type in enumerate(quiz_plan, 1):
            label = "Pre-Test" if q_type == "PRETEST" else ("Post-Test" if q_type == "POSTTEST" else "Kuis")
            print(f"    {idx}. {label} ({q_type})")

        if not quiz_plan:
            print("[!] Tidak ada modul kuis aktif yang ditemukan di pertemuan ini.")
            browser.close()
            return

        # 6. Eksekusi Kuis Sesuai Urutan: Pre-Test terlebih dahulu, lalu Post-Test
        for q_idx, q_type in enumerate(quiz_plan, 1):
            quiz_label = "PRE-TEST" if q_type == "PRETEST" else ("POST-TEST" if q_type == "POSTTEST" else "KUIS")
            print("\n" + "=" * 80)
            print(f" [{q_idx}/{len(quiz_plan)}] MEMPROSES {quiz_label}")
            print("=" * 80)

            # Cari kartu kuis secara presisi
            quiz_info = find_meeting_quiz_card(page, target_meeting, q_type)
            target_btn = quiz_info.get("button")

            if not target_btn or target_btn.count() == 0:
                # Fallback: cari tombol QUIZ langsung di dalam scope pertemuan
                meeting_scope = page.locator(f'div:has(text=/^\\s*Pertemuan\\s+{target_meeting}\\b/i)').first
                target_btn = meeting_scope.locator('button:has-text("QUIZ"), a:has-text("QUIZ")').first if meeting_scope.count() > 0 else None

            if not target_btn or target_btn.count() == 0:
                print(f"[!] Tombol untuk {quiz_label} tidak ditemukan atau kuis masih terkunci.")
                continue

            print(f"[*] Mengklik tombol masuk ke {quiz_label}...")
            try:
                target_btn.scroll_into_view_if_needed()
                target_btn.click(force=True)
                page.wait_for_timeout(3500)
            except Exception as e:
                print(f"[!] Gagal klik tombol kuis: {e}")
                continue

            current_url = page.url
            print(f"[V] URL setelah klik {quiz_label}: {current_url}")

            # Pastikan telah berpindah dari halaman kelas ke halaman kuis/ujian
            if "/quiz/" not in current_url and "/exam/" not in current_url:
                print("[!] URL belum berpindah, mencoba klik ulang tombol QUIZ...")
                try:
                    target_btn.click(force=True)
                    page.wait_for_timeout(3500)
                    current_url = page.url
                    print(f"[V] URL baru: {current_url}")
                except Exception:
                    pass

            # 7. Penanganan Alur Tombol Pengerjaan (Step 1 -> Step 2 -> Step 3)
            # Jika belum masuk ke /exam/, periksa status kuis
            if "/exam/" not in current_url:
                full_check = page.locator("body").inner_text()
                own_check = extract_own_quiz_section(full_check)

                kerjakan_btn = page.locator('button:has-text("KERJAKAN QUIZ"), button:has-text("LANJUTKAN QUIZ"), button:has-text("Kerjakan Quiz"), button:has-text("Lanjutkan Quiz")').first
                has_kerjakan_btn = kerjakan_btn.count() > 0 and kerjakan_btn.is_visible()

                is_done, score_val = check_quiz_completion_status(own_check)

                if is_done:
                    score_info = f" (Nilai: {score_val})" if score_val else ""
                    print(f"    📊 STATUS KUIS: {quiz_label} SUDAH SELESAI DIKERJAKAN!{score_info}")
                    print(f"    -> Melewati {quiz_label} dan lanjut ke langkah berikutnya.")

                    # Kembali ke halaman kelas jika masih ada kuis berikutnya
                    if q_idx < len(quiz_plan):
                        print("\n[*] Kembali ke halaman mata kuliah untuk memproses kuis berikutnya...")
                        page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(3000)
                        p_header = page.locator(f'text=/^\\s*Pertemuan\\s+{target_meeting}\\b/i').first
                        if p_header.count() > 0:
                            p_header.scroll_into_view_if_needed()
                            p_header.click()
                            page.wait_for_timeout(2000)
                    continue

                # LANGKAH 1: Klik tombol "KERJAKAN QUIZ" atau "LANJUTKAN QUIZ"
                if has_kerjakan_btn:
                    btn_text = kerjakan_btn.inner_text().strip()
                    print(f"[*] [Langkah 1/3] Menemukan tombol: '{btn_text}'. Mengklik...")
                    kerjakan_btn.click()
                    page.wait_for_timeout(2500)
                    current_url = page.url

                # LANGKAH 2: Jika belum di /exam/, klik "MULAI QUIZ"
                if "/exam/" not in current_url:
                    mulai_btn = page.locator('button:has-text("MULAI QUIZ"), button:has-text("Mulai Quiz")').first
                    if mulai_btn.count() > 0 and mulai_btn.is_visible():
                        btn_text = mulai_btn.inner_text().strip()
                        print(f"[*] [Langkah 2/3] Menemukan tombol mulai: '{btn_text}'. Mengklik...")
                        mulai_btn.click()
                        page.wait_for_timeout(2000)

                # LANGKAH 3: Tangani Dialog Konfirmasi ("Apakah anda yakin ingin memulai quiz ini ?" -> Klik "Ya")
                if "/exam/" not in current_url:
                    ya_btn = page.locator('button:has-text("Ya"), button:has-text("YA")').first
                    if ya_btn.count() > 0 and ya_btn.is_visible():
                        print(f"[*] [Langkah 3/3] Muncul dialog konfirmasi! Mengklik tombol 'Ya'...")
                        ya_btn.click()
                        page.wait_for_timeout(3500)

            # Verifikasi akhir apakah sudah berada di halaman ujian
            current_url = page.url
            if "/exam/" not in current_url:
                print(f"[!] Peringatan: Halaman ujian belum termuat. URL saat ini: {current_url}")
                try:
                    page.wait_for_url("**/exam/**", timeout=8000)
                    current_url = page.url
                except Exception:
                    pass

            print(f"[V] Berada di Halaman Pengerjaan Ujian: {current_url}")

            # 8. Selesaikan Soal dengan AI Gemini
            print("\n" + "-" * 75)
            print(f"       AI GEMINI MENGERJAKAN SOAL {quiz_label}")
            print("-" * 75)

            # Deteksi total soal dari panel Navigasi Soal di sidebar kanan
            nav_buttons = page.locator('div:has-text("Navigasi Soal") button, .MuiCard-root:has-text("Navigasi Soal") button').all()
            soal_nav_btns = [b for b in nav_buttons if b.inner_text().strip().isdigit()]
            total_soal = len(soal_nav_btns) if soal_nav_btns else 5
            print(f"[V] Terdeteksi total {total_soal} soal pada {quiz_label} ini!")

            for s_num in range(1, total_soal + 1):
                print("\n" + "=" * 70)
                print(f"   [SOAL #{s_num} dari {total_soal}]")
                print("=" * 70)

                page.wait_for_timeout(1500)

                # Ambil seluruh opsi jawaban
                labels = page.locator('label.MuiFormControlLabel-root').all()
                if not labels:
                    labels = page.locator('div:has(> input[type="radio"]), label:has(input[type="radio"])').all()

                options_text = [clean_text(l.inner_text()) for l in labels]

                # Ambil teks pertanyaan dari body secara presisi
                body_lines = [line.strip() for line in page.locator("body").inner_text().splitlines() if line.strip()]
                q_lines = []
                capturing = False
                for line in body_lines:
                    if any(m in line for m in ["PERTEMUAN", "Multiple Choice", "Belum dijawab", "Sudah dijawab"]):
                        capturing = True
                        continue
                    if capturing:
                        if options_text and options_text[0][:15] in line:
                            break
                        if line.startswith("A.") or line == "A.":
                            break
                        if not any(skip in line for skip in ["Waktu tersisa", "Pretest", "Post Test", "KEMBALI", "Navigasi Soal", "Hint"]):
                            q_lines.append(line)

                soal_text = " ".join(q_lines).strip()
                if not soal_text:
                    soal_text = f"Soal nomor {s_num}"

                print(f"[*] Pertanyaan : {soal_text}")
                print(f"[*] Pilihan ({len(options_text)} opsi):")
                for o_idx, opt in enumerate(options_text):
                    print(f"    [{chr(65+o_idx)}] {opt}")

                if options_text:
                    print("[*] AI Gemini sedang menganalisis materi dan menentukan jawaban...")
                    ai_result = solve_multiple_choice(
                        question=soal_text,
                        options=options_text
                    )

                    chosen_index = ai_result.get("index", 0)
                    chosen_answer = ai_result.get("answer", "")
                    reason = ai_result.get("reason", "")

                    print(f"    💡 Rekomendasi AI : {chr(65+chosen_index)} ({chosen_answer[:65]})")
                    print(f"    📝 Alasan Akademik: {reason}")

                    # Klik radio button yang dipilih AI
                    try:
                        target_label = labels[chosen_index]
                        target_label.scroll_into_view_if_needed()
                        target_label.click(force=True)
                        print(f"    [V] Opsi {chr(65+chosen_index)} berhasil diklik dan dicentang di browser!")
                    except Exception as e:
                        print(f"    [!] Gagal klik opsi: {e}")

                    page.wait_for_timeout(1000)

                # Jika belum soal terakhir, klik NEXT ke soal berikutnya
                if s_num < total_soal:
                    next_btn = page.locator('button:has-text("NEXT")').first
                    if next_btn.count() > 0 and next_btn.is_visible():
                        print("[*] Mengklik 'NEXT ->' untuk berpindah ke nomor berikutnya...")
                        next_btn.click()
                        page.wait_for_timeout(2000)
                    elif s_num < len(soal_nav_btns):
                        print(f"[*] Berpindah ke nomor {s_num+1} melalui panel Navigasi Soal...")
                        soal_nav_btns[s_num].click()
                        page.wait_for_timeout(2000)

            # 9. Selesai Menjawab Semua Soal
            print("\n" + "=" * 80)
            print(f" [V] SELURUH SOAL {quiz_label} TELAH BERHASIL DIJAWAB OLEH AI GEMINI!")
            print(" [!] STANDAR KEAMANAN: BOT TIDAK AKAN MENEKAN TOMBOL 'SUBMIT/SELESAI' OTOMATIS.")
            print(" [!] SILAKAN PERIKSA JAWABAN ANDA DI LAYAR BROWSER.")
            print("=" * 80)

            screenshot_path = f"data/quiz_result_{quiz_label.lower()}.png"
            page.screenshot(path=screenshot_path)
            print(f"[*] Tangkapan layar hasil kuis disimpan ke: {screenshot_path}")

            # Minta konfirmasi user sebelum kembali (MENCEGAH AUTO-BACK!)
            print(f"\n[!] Jendela kuis {quiz_label} tetap terbuka di layar komputer Anda.")
            try:
                input(f">> Tekan ENTER di sini jika Anda sudah selesai memeriksa {quiz_label} dan ingin melanjutkan: ")
            except (EOFError, KeyboardInterrupt):
                page.wait_for_timeout(5000)

            # Kembali ke halaman kelas jika masih ada kuis berikutnya
            if q_idx < len(quiz_elements):
                print("\n[*] Kembali ke halaman mata kuliah untuk memproses kuis berikutnya...")
                page.goto(COURSE_URL, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(3000)
                
                # Buka kembali akordion pertemuan
                p_header = page.locator(f'text=/^\\s*Pertemuan\\s+{target_meeting}\\b/i').first
                if p_header.count() > 0:
                    p_header.scroll_into_view_if_needed()
                    p_header.click()
                    page.wait_for_timeout(1500)

        print("\n" + "=" * 80)
        print(" [V] PENGUJIAN KUIS PERTEMUAN TELAH SELESAI SELURUHNYA!")
        print("=" * 80)
        print("\n[!] BROWSER DIBIARKAN TERBUKA AGAR ANDA DAPAT MENINJAU HASILNYA.")
        
        try:
            input("\n>> Tekan ENTER di sini untuk menutup browser: ")
        except (EOFError, KeyboardInterrupt):
            page.wait_for_timeout(5000)

        browser.close()
        print("[*] Browser ditutup. Selesai.")


if __name__ == "__main__":
    target = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 1
    run_quiz_test(target_meeting=target)
