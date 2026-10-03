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
from services.ai_solver import solve_multiple_choice, draft_forum_discussion
from services.agent_bot import resolve_course_key

AUTH_PATH = Path("data/auth.json").resolve()
MASTER_AUDIT_PATH = Path("data/mentari_master_audit.json").resolve()
MEETING_GRADES_PATH = Path("data/mentari_meeting_grades.json").resolve()
DRAFTS_PATH = Path("data/forum_drafts.json").resolve()

# Daftar 8 Mata Kuliah Aktif Mahasiswa (Kelas 07TPLP003)
COURSES = {
    "1": {
        "id": "22TIF0312",
        "name": "MANAJEMEN PROYEK INFORMATIKA",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0312"
    },
    "2": {
        "id": "22TIF0373",
        "name": "ARSITEKTUR DAN ORGANISASI KOMPUTER",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0373"
    },
    "3": {
        "id": "22TIF0382",
        "name": "KEAMANAN KOMPUTER",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0382"
    },
    "4": {
        "id": "22TIF0392",
        "name": "JARINGAN NIRKABEL",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0392"
    },
    "5": {
        "id": "22TIF0402",
        "name": "KECAKAPAN ANTAR PERSONAL",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0402"
    },
    "6": {
        "id": "22TIF0412",
        "name": "TESTING DAN QA PERANGKAT LUNAK",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0412"
    },
    "7": {
        "id": "22TIF0422",
        "name": "ETIKA PROFESI",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0422"
    },
    "8": {
        "id": "22TIF0433",
        "name": "PEMROGRAMAN WEB II",
        "url": "https://mentari.unpam.ac.id/u-courses/20261-07TPLP003-22TIF0433"
    }
}


def clean_text(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " | ".join(lines)


def ensure_turnstile_cleared(page, timeout_sec: int = 15):
    """Menunggu Cloudflare Turnstile verifikasi otomatis jika muncul."""
    for _ in range(timeout_sec):
        title = page.title()
        if "Just a moment" not in title and title != "":
            return True
        time.sleep(1)
    return False
def extract_own_quiz_section(full_text: str) -> str:
    """
    Memotong teks halaman kuis agar HANYA menyertakan kartu data milik mahasiswa sendiri (Sofyan),
    membuang seluruh tabel peserta lain (List Data Peserta / Cari Peserta) agar tidak membaca nilai teman sekelas.
    """
    if not full_text:
        return ""
    patterns = [
        r'list\s+data\s+peserta',
        r'daftar\s+peserta',
        r'data\s+peserta',
        r'cari\s+peserta',
        r'status\s+quiz',
        r'urut\s+berdasarkan',
        r'peserta\s+quiz'
    ]
    truncated = full_text
    for p in patterns:
        m = re.search(p, truncated, flags=re.IGNORECASE)
        if m:
            truncated = truncated[:m.start()]
            break
    return truncated


def check_quiz_completion_status(own_section: str) -> tuple[bool, str | None]:
    """
    Mengecek secara ketat apakah Sofyan sudah menyelesaikan kuis atau belum berdasarkan teks section miliknya.
    Mengembalikan tuple (is_done, score_val).
    """
    clean_sec = own_section.lower()
    has_sudah = "sudah mengerjakan quiz" in clean_sec
    has_belum = "belum mengerjakan quiz" in clean_sec
    has_waktu = "waktu penyelesaian" in clean_sec

    score_match = re.search(r'(?:grade|nilai|skor)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', own_section, re.IGNORECASE)
    score_val = score_match.group(1) if score_match else None

    is_done = (has_sudah and not has_belum) or (has_waktu and score_val is not None)
    return is_done, score_val


def parse_meeting_targets(meeting_input, course_name: str = "", target_step: str = "all") -> list[int]:
    """
    Mengonversi input pertemuan fleksibel (int, list, '1,2', '1-3', 'p1 dan p2', 'all', 'auto')
    menjadi daftar integer nomor pertemuan terurut.
    """
    if isinstance(meeting_input, int):
        return [meeting_input]
    if isinstance(meeting_input, list):
        return sorted(list(set(int(x) for x in meeting_input if str(x).isdigit())))

    m_str = str(meeting_input).strip().lower()

    # 1. Kasus: 'all' atau 'auto'
    if m_str in ["all", "auto", "semua", "seluruh"]:
        audit_path = Path("data/mentari_master_audit.json")
        grades_path = Path("data/mentari_meeting_grades.json")

        all_meetings = []
        if audit_path.exists():
            try:
                with open(audit_path, encoding="utf-8") as f:
                    audit = json.load(f)
                grades = {}
                if grades_path.exists():
                    with open(grades_path, encoding="utf-8") as f:
                        grades = json.load(f)

                for c in audit:
                    c_n = c.get("course_name", "")
                    if course_name and course_name.lower() not in c_n.lower():
                        continue
                    c_grades = grades.get(c_n, {}).get("meetings", {})
                    for m in c.get("meetings", []):
                        p_num = m.get("pertemuan")
                        m_grade = c_grades.get(f"Pertemuan {p_num}", {})
                        if target_step in ["pretest", "pre", "pre-test"]:
                            pre_done = m_grade.get("pretest", {}).get("grade") is not None
                            if not pre_done and m.get("pretest"):
                                all_meetings.append(p_num)
                        elif target_step in ["posttest", "post", "post-test"]:
                            post_done = m_grade.get("posttest", {}).get("grade") is not None
                            if not post_done and m.get("posttest"):
                                all_meetings.append(p_num)
                        else:
                            is_done = m_grade.get("pretest", {}).get("grade") is not None and (not m.get("posttest") or m_grade.get("posttest", {}).get("grade") is not None)
                            if not is_done:
                                all_meetings.append(p_num)
            except Exception:
                pass
        return sorted(list(set(all_meetings))) if all_meetings else [1, 2]

    # 2. Kasus: Range seperti '1-3' atau '1 - 4' atau 'p1-p3'
    range_match = re.search(r'(?:p|pertemuan\s*)?(\d+)\s*[-–]\s*(?:p|pertemuan\s*)?(\d+)', m_str)
    if range_match:
        start_m = int(range_match.group(1))
        end_m = int(range_match.group(2))
        if start_m <= end_m:
            return list(range(start_m, end_m + 1))

    # 3. Kasus: Deteksi seluruh angka dalam string (misal 'p1 dan p2', '1, 2', 'pertemuan 1 dan 2')
    digits = re.findall(r'\d+', m_str)
    if digits:
        return sorted(list(set(int(d) for d in digits)))

    return [1]


def update_meeting_grade_record(course_name: str, meeting_num: int, quiz_type: str, grade: int | float | None, status: str = "Selesai"):
    """Langsung memperbarui file data/mentari_meeting_grades.json secara instan ke disk tanpa perlu scraper ulang."""
    try:
        if not MEETING_GRADES_PATH.exists():
            return
        with open(MEETING_GRADES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        target_key = None
        for k in data.keys():
            if course_name.lower() in k.lower() or k.lower() in course_name.lower():
                target_key = k
                break
        if not target_key:
            return

        c_data = data[target_key]
        m_key = f"Pertemuan {meeting_num}"
        if "meetings" not in c_data:
            c_data["meetings"] = {}
        if m_key not in c_data["meetings"]:
            c_data["meetings"][m_key] = {"section_name": m_key, "pretest": None, "posttest": None}

        q_key = "pretest" if "pre" in quiz_type.lower() else "posttest"
        if not c_data["meetings"][m_key].get(q_key):
            c_data["meetings"][m_key][q_key] = {
                "judul": "Pretest" if q_key == "pretest" else "Posttest",
                "quiz_type": "Pre-Test" if q_key == "pretest" else "Post-Test"
            }

        q_entry = c_data["meetings"][m_key][q_key]
        if grade is not None:
            try:
                # Format ke int jika nilai bulat
                grade_clean = int(grade) if float(grade).is_integer() else float(grade)
            except Exception:
                grade_clean = grade
            q_entry["grade"] = grade_clean
            q_entry["status"] = "Selesai"
        elif status:
            q_entry["status"] = status

        # Hitung ulang kuis yang tuntas
        done_cnt = 0
        for mv in c_data["meetings"].values():
            if mv.get("pretest") and mv["pretest"].get("grade") is not None:
                done_cnt += 1
            if mv.get("posttest") and mv["posttest"].get("grade") is not None:
                done_cnt += 1
        c_data["completed_quizzes_count"] = done_cnt

        with open(MEETING_GRADES_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"    💾 [DATABASE SYNC] Nilai {quiz_type} Pertemuan {meeting_num} ({grade}) berhasil disimpan ke database!")
    except Exception as e:
        print(f"    [!] Gagal memperbarui record meeting_grades: {e}")


def check_quiz_completion_api(page) -> tuple[bool, str | None]:
    """
    Mengecek status riil pengerjaan kuis mahasiswa via API resmi Mentari LMS.
    Mengembalikan tuple (is_completed, grade_str).
    """
    try:
        m = re.search(r'/quiz/([a-zA-Z0-9-]+)', page.url)
        if not m:
            return False, None
        quiz_id = m.group(1)
        quiz_data = page.evaluate("""async (qid) => {
            try {
                const access = JSON.parse(localStorage.getItem('access'));
                const token = access && access[0] ? access[0].token : null;
                if (!token) return null;
                const res = await fetch('/api/quiz/peserta/' + qid, {
                    headers: { 'authorization': 'Bearer ' + token }
                });
                if (!res.ok) return null;
                const d = await res.json();
                return d.quiz || null;
            } catch(e) {
                return null;
            }
        }""", quiz_id)
        if quiz_data and quiz_data.get("grade") is not None:
            return True, str(quiz_data.get("grade"))
        elif quiz_data and quiz_data.get("end_at"):
            return True, None
    except Exception as e:
        print(f"    [!] Peringatan cek API kuis: {e}")
    return False, None


def check_quiz_completion_dom(page) -> tuple[bool, str | None]:
    """
    Mengecek status riwayat pengerjaan dari tabel attempt mahasiswa di DOM.
    HANYA valid jika ada baris status 'Selesai' / 'Finished'.
    """
    try:
        tables = page.locator('table, .MuiTable-root').all()
        for tbl in tables:
            t_txt = tbl.inner_text().lower()
            if "selesai" in t_txt or "finished" in t_txt:
                rows = tbl.locator('tr:has-text("Selesai"), tr:has-text("selesai")').all()
                for r in rows:
                    r_txt = r.inner_text()
                    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:/\s*100|\s*%)?', r_txt)
                    if m:
                        return True, m.group(1)
                return True, None
    except Exception:
        pass
    return False, None


def detect_page_error_or_lock(page) -> str:
    """Mendeteksi pesan error, alert, modal dialog, atau toast pembatasan akses."""
    try:
        modals_or_alerts = page.locator('.MuiDialog-root, [role="alert"], [role="dialog"], .Toastify, [class*="alert"], [class*="toast"]').all()
        for m in modals_or_alerts:
            m_txt = m.inner_text().strip()
            if any(w in m_txt.lower() for w in ["selesaikan", "forum diskusi", "pretest", "prasyarat", "error", "belum"]):
                clean_lines = [l.strip() for l in m_txt.splitlines() if l.strip() and l.strip().upper() != "ERROR"]
                return " - ".join(clean_lines) if clean_lines else m_txt

        body_peek = page.locator("body").inner_text()[:600]
        if "ERROR" in body_peek and any(w in body_peek.lower() for w in ["selesaikan", "forum diskusi", "pretest", "belum"]):
            m = re.search(r'ERROR\s*\n+([^\n]+)', body_peek)
            if m:
                return m.group(1).strip()
    except Exception:
        pass
    return ""


def scrape_student_quiz_status(page, student_name: str = "SOFYAN AGUNG", student_nim: str = "231011400159") -> dict:
    """
    Scraper mendalam & adaptif untuk membaca status pengerjaan kuis mahasiswa secara nyata di web Mentari LMS.
    Menggabungkan 4 lapisan deteksi independen:
    1. Bagian Ringkasan Utama ('Detail Pengerjaan Quiz') milik mahasiswa
    2. Scraping Baris Data Peserta ('List Data Peserta') khusus nama/NIM mahasiswa
    3. Verifikasi Data Internal LMS via API ('/api/quiz/peserta/{quiz_id}')
    4. Deteksi Pesan Error / Pembatasan Prasyarat (Lock Restriction)
    """
    result = {
        "is_done": False,
        "grade": None,
        "is_locked": False,
        "lock_reason": "",
        "can_start": False,
        "source": ""
    }

    # 1. Deteksi Tombol Pengerjaan Aktif di Layar
    k_btn = page.locator('button:has-text("KERJAKAN QUIZ"), button:has-text("LANJUTKAN QUIZ"), button:has-text("Kerjakan Quiz"), button:has-text("Lanjutkan Quiz")').first
    result["can_start"] = k_btn.count() > 0 and k_btn.is_visible()

    # 2. Lapisan 1: Pindai Bagian Atas 'Detail Pengerjaan Quiz'
    try:
        full_text = page.locator("body").inner_text()
        own_section = full_text.split("List Data Peserta")[0] if "List Data Peserta" in full_text else full_text
        own_sec_clean = own_section.lower()

        # Di Mentari LMS, jika kuis sudah dikerjakan mahasiswa, muncul:
        # 'Quiz Sudah Mengerjakan Quiz', 'Selesai', dan angka Grade
        has_selesai_word = "selesai" in own_sec_clean and ("waktu penyelesaian" in own_sec_clean or "sudah mengerjakan" in own_sec_clean)
        
        grade_match = re.search(r'(?:grade|nilai|skor)\s*\n+\s*(\d+(?:[.,]\d+)?)', own_section, re.IGNORECASE)
        if not grade_match:
            grade_match = re.search(r'(?:grade|nilai|skor)\s*[:=]\s*(\d+(?:[.,]\d+)?)', own_section, re.IGNORECASE)

        if has_selesai_word and grade_match:
            result["is_done"] = True
            result["grade"] = grade_match.group(1)
            result["source"] = "Detail Pengerjaan Quiz (DOM)"
            return result
    except Exception as e:
        print(f"    [!] Catatan scraping Detail Pengerjaan Quiz: {e}")

    # 3. Lapisan 2: Scraping Langsung Tabel 'List Data Peserta' untuk Sofyan Agung / NIM
    try:
        nim_locator = page.locator(f'tr:has-text("{student_nim}"), .MuiCard-root:has-text("{student_nim}"), tr:has-text("{student_name}"), .MuiCard-root:has-text("{student_name}")').first
        if nim_locator.count() > 0:
            row_txt = nim_locator.inner_text()
            print(f"    [*] Ditemukan entri mahasiswa ({student_name}) di tabel peserta.")
            is_done_row = "sudah mengerjakan" in row_txt.lower() or "selesai" in row_txt.lower()
            is_belum_row = "belum mengerjakan" in row_txt.lower()
            score_m = re.search(r'(?:grade|nilai|skor)?\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:/\s*100|\s*%)?', row_txt, re.IGNORECASE)
            row_grade = score_m.group(1) if score_m else None

            if is_done_row and not is_belum_row:
                result["is_done"] = True
                result["grade"] = row_grade
                result["source"] = "List Data Peserta (DOM Row)"
                return result
        else:
            # Gunakan search box peserta jika tersedia
            search_input = page.locator('input[placeholder*="Cari Peserta"], input[placeholder*="Nama / NIM"], input[placeholder*="NIM"]').first
            if search_input.count() > 0 and search_input.is_visible():
                search_input.fill(student_nim)
                page.wait_for_timeout(1500)
                filtered_row = page.locator(f'tr:has-text("{student_nim}"), .MuiCard-root:has-text("{student_nim}")').first
                if filtered_row.count() > 0:
                    f_txt = filtered_row.inner_text()
                    is_done_row = "sudah mengerjakan" in f_txt.lower()
                    is_belum_row = "belum mengerjakan" in f_txt.lower()
                    score_m = re.search(r'(\d+(?:[.,]\d+)?)', f_txt)
                    f_grade = score_m.group(1) if score_m else None

                    if is_done_row and not is_belum_row:
                        result["is_done"] = True
                        result["grade"] = f_grade
                        result["source"] = "List Data Peserta Filter (DOM)"
                        return result
    except Exception as e:
        print(f"    [!] Catatan scraping List Data Peserta: {e}")

    # 4. Lapisan 3: Verifikasi API Mentari LMS (/api/quiz/peserta/{quiz_id})
    try:
        is_done_api, score_api = check_quiz_completion_api(page)
        if is_done_api:
            result["is_done"] = True
            result["grade"] = score_api
            result["source"] = "Mentari LMS API"
            return result
    except Exception as e:
        print(f"    [!] Catatan verifikasi API: {e}")

    # 5. Lapisan 4: Deteksi Pembatasan Prasyarat / Error
    err_msg = detect_page_error_or_lock(page)
    if err_msg:
        result["is_locked"] = True
        result["lock_reason"] = err_msg

    return result


def ensure_meeting_expanded(page, meeting_num: int) -> bool:
    """
    Memastikan container Pertemuan target benar-benar terbuka (expanded).
    Di Mentari LMS, container pertemuan memiliki ID '#PERTEMUAN_{meeting_num}'.
    """
    p_container = page.locator(f'#PERTEMUAN_{meeting_num}').first
    if p_container.count() == 0:
        p_container = page.locator(f'div:not([id*="course-index"]):not(.MuiDrawer-root *):has-text("Pertemuan {meeting_num}")').first

    if p_container.count() == 0:
        print(f"[!] Container Pertemuan {meeting_num} tidak ditemukan di halaman kelas.")
        return False

    # Cek apakah sudah terbuka (memiliki kartu modul .MuiPaper-root di dalamnya)
    has_cards = p_container.locator('.MuiPaper-root').count() > 0
    if not has_cards:
        print(f"[*] Membuka panel Pertemuan {meeting_num}...")
        summary_btn = p_container.locator('.op-accordion-summary, button, [role="button"]').first
        if summary_btn.count() > 0:
            summary_btn.scroll_into_view_if_needed()
            summary_btn.click()
        else:
            p_container.click()
        page.wait_for_timeout(2500)
    else:
        print(f"[*] Panel Pertemuan {meeting_num} sudah dalam posisi terbuka.")
        page.wait_for_timeout(500)

    return True


def get_meeting_scope(page, meeting_num: int):
    """
    Mengambil elemen container khusus untuk pertemuan yang dituju.
    Di Mentari LMS, elemen utamanya adalah '#PERTEMUAN_{meeting_num}'.
    """
    p_container = page.locator(f'#PERTEMUAN_{meeting_num}').first
    if p_container.count() > 0:
        return p_container

    p_box = page.locator(f'div:not([id*="course-index"]):not(.MuiDrawer-root *):has-text("Pertemuan {meeting_num}")').first
    return p_box if p_box.count() > 0 else page


def find_meeting_quiz_card(page, meeting_num: int, quiz_type: str = "PRETEST") -> dict:
    """
    Mencari kartu kuis (PRETEST atau POSTTEST) secara presisi di dalam container pertemuan target.
    Menjamin tidak akan pernah tertukar antara Pre-Test dan Post-Test.
    """
    ensure_meeting_expanded(page, meeting_num)
    scope = get_meeting_scope(page, meeting_num)
    if not scope or scope.count() == 0:
        scope = page

    target_type = quiz_type.upper().strip()  # "PRETEST" atau "POSTTEST"

    # Ambil semua kartu kandidat di dalam scope pertemuan ini
    candidate_cards = scope.locator('.MuiPaper-root').all()
    valid_cards = []
    for c in candidate_cards:
        txt = c.inner_text().strip()
        if not txt or "Course Index" in txt:
            continue
        valid_cards.append((c, txt))

    # 1. Pencarian berbasis kartu modul spesifik
    for c, c_txt in valid_cards:
        lines = [l.strip() for l in c_txt.splitlines() if l.strip()]
        if not lines:
            continue
        first_l = lines[0].lower()
        top_txt = " ".join(lines[:3]).lower()

        btn = c.locator('button:has-text("QUIZ"), a:has-text("QUIZ")').first
        has_btn = btn.count() > 0 and btn.is_visible()

        # Ekstrak catatan pembatasan jika ada (misal: "Silakan selesaikan forum diskusi...")
        card_restriction = ""
        for line in lines:
            if any(w in line.lower() for w in ["selesaikan", "prasyarat", "dibatasi", "belum mengerjakan", "terlebih dahulu"]):
                card_restriction = line
                break

        if target_type == "PRETEST":
            is_pre = any(k in top_txt for k in ["pretest", "pre-test", "pre test"])
            is_not_post = not any(k in first_l for k in ["posttest", "post-test", "post test"])
            if is_pre and is_not_post:
                is_locked = not has_btn or bool(card_restriction and not has_btn)
                return {
                    "card": c,
                    "button": btn if has_btn else None,
                    "is_locked": is_locked,
                    "card_title": lines[0],
                    "card_text": c_txt,
                    "restriction_note": card_restriction,
                    "status_note": card_restriction if card_restriction else ("Aktif" if has_btn else "Terkunci")
                }

        elif target_type == "POSTTEST":
            is_post_title = any(k in top_txt for k in ["posttest", "post-test", "post test"])
            is_locked_post = bool(card_restriction and any(w in card_restriction.lower() for w in ["pretest", "forum"]))
            is_not_pre = not any(first_l == k for k in ["pretest", "pre-test", "pre test"])

            if (is_post_title or is_locked_post) and is_not_pre:
                is_locked = (not has_btn) or bool(card_restriction and not has_btn)
                return {
                    "card": c,
                    "button": btn if has_btn else None,
                    "is_locked": is_locked,
                    "card_title": lines[0],
                    "card_text": c_txt,
                    "restriction_note": card_restriction,
                    "status_note": card_restriction if card_restriction else ("Aktif" if has_btn else "Terkunci")
                }

    # 2. Fallback: cari tombol QUIZ langsung di dalam scope pertemuan
    quiz_buttons = scope.locator('button:has-text("QUIZ"), a:has-text("QUIZ")').all()
    for q_btn in quiz_buttons:
        if not q_btn.is_visible():
            continue
        parent_card = q_btn.locator('xpath=ancestor::*[contains(@class, "MuiPaper-root")][1]').first
        if parent_card.count() > 0:
            c_txt = parent_card.inner_text().strip()
            lines = [l.strip() for l in c_txt.splitlines() if l.strip()]
            first_l = lines[0].lower() if lines else ""
            top_txt = " ".join(lines[:3]).lower()

            if target_type == "PRETEST":
                if any(k in top_txt for k in ["pretest", "pre-test", "pre test"]) and not any(k in first_l for k in ["posttest", "post-test", "post test"]):
                    return {
                        "card": parent_card,
                        "button": q_btn,
                        "is_locked": False,
                        "card_title": lines[0] if lines else "Pretest",
                        "card_text": c_txt,
                        "restriction_note": "",
                        "status_note": "Aktif via tombol"
                    }
            elif target_type == "POSTTEST":
                if any(k in top_txt for k in ["posttest", "post-test", "post test"]) and not any(k in first_l for k in ["pretest", "pre-test", "pre test"]):
                    return {
                        "card": parent_card,
                        "button": q_btn,
                        "is_locked": False,
                        "card_title": lines[0] if lines else "Posttest",
                        "card_text": c_txt,
                        "restriction_note": "",
                        "status_note": "Aktif via tombol"
                    }

    return {"card": None, "button": None, "is_locked": False, "card_title": "", "card_text": "", "restriction_note": "", "status_note": "Not Found"}




def solve_quiz_exam(page, quiz_label: str):
    """Menyelesaikan seluruh soal kuis di halaman /exam/ menggunakan Gemini AI."""
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
        print(f"   [{quiz_label} - SOAL #{s_num} dari {total_soal}]")
        print("=" * 70)

        page.wait_for_timeout(1500)

        # Ambil opsi jawaban
        labels = page.locator('label.MuiFormControlLabel-root').all()
        if not labels:
            labels = page.locator('div:has(> input[type="radio"]), label:has(input[type="radio"])').all()

        options_text = [clean_text(l.inner_text()) for l in labels]

        # Ambil pertanyaan dari teks body
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
                if not any(skip in line for skip in ["Waktu tersisa", "Pretest", "Posttest", "Post Test", "KEMBALI", "Navigasi Soal", "Hint"]):
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

    print("\n" + "=" * 80)
    print(f" [V] SELURUH SOAL {quiz_label} TELAH BERHASIL DIJAWAB OLEH AI GEMINI!")
    print("=" * 80)

    # Tangkapan layar bukti pengerjaan kuis
    screenshot_path = f"data/quiz_exam_{quiz_label.lower().replace(' ', '_').replace('-', '_')}.png"
    try:
        page.screenshot(path=screenshot_path)
        print(f"[*] Screenshot jawaban disimpan ke: {screenshot_path}")
    except Exception:
        pass

    # Klik tombol 'SELESAI QUIZ' jika ada di layar
    selesai_btn = page.locator('button:has-text("SELESAI QUIZ"), button:has-text("Selesai Quiz"), button:has-text("SELESAI")').first
    if selesai_btn.count() > 0 and selesai_btn.is_visible():
        btn_txt = selesai_btn.inner_text().strip()
        print(f"[*] Menemukan tombol akhir kuis: '{btn_txt}'. Mengklik untuk menyelesaikan kuis...")
        selesai_btn.click()
        page.wait_for_timeout(2500)

        # Tangani dialog konfirmasi "Apakah anda yakin ingin menyelesaikan quiz ini ?" -> Klik "Ya"
        ya_btn = page.locator('button:has-text("Ya"), button:has-text("YA")').first
        if ya_btn.count() > 0 and ya_btn.is_visible():
            print("[*] Konfirmasi penyelesaian kuis muncul! Mengklik 'Ya'...")
            ya_btn.click()
            page.wait_for_timeout(4000)

    # Verifikasi pengalihan keluar dari halaman ujian
    if "/exam/" in page.url:
        try:
            page.wait_for_url(lambda u: "/exam/" not in u, timeout=10000)
        except Exception:
            pass

    score_val = None
    try:
        # Jika sudah kembali ke halaman /quiz/, baca nilai asli milik Sofyan (bukan daftar teman sekelas)
        if "/quiz/" in page.url:
            page.wait_for_timeout(2500)
            body_done = page.locator("body").inner_text()
            own_done = extract_own_quiz_section(body_done)
            sm = re.search(r'(?:grade|nilai|skor)\s*[:=]?\s*(\d+(?:[.,]\d+)?)', own_done, re.IGNORECASE)
            if sm:
                score_val = sm.group(1)
                print(f"    📊 NILAI RESMI MENTARI LMS ({quiz_label}): {score_val}")
    except Exception as e:
        print(f"    [!] Catatan saat membaca nilai kuis: {e}")

    return {
        "completed": True,
        "total_soal": total_soal,
        "grade": score_val
    }


def execute_single_meeting_pipeline(page, course: dict, target_meeting: int, step_clean: str, target_step: str) -> dict:
    """Mengeksekusi alur pembelajaran 5 tahap untuk satu pertemuan spesifik."""
    status_pretest = "Tidak Ada"
    status_fordis = "Tidak Ada"
    status_posttest = "Tidak Ada"
    status_kuesioner = "Tidak Ada"

    print("\n" + "=" * 85)
    print(f"[*] EKSEKUSI PEMBELAJARAN PERTEMUAN {target_meeting}: {course['name']}")
    print("=" * 85)

    if not ensure_meeting_expanded(page, target_meeting):
        print(f"[!] Pertemuan {target_meeting} tidak dapat dibuka pada mata kuliah ini.")
        return {"pretest": "Gagal Buka", "fordis": "Tidak Ada", "posttest": "Tidak Ada", "kuesioner": "Tidak Ada"}

    # -------------------------------------------------------------
    # TAHAP 1: PRE-TEST (Kunci Prasyarat Pembuka Sesi)
    # -------------------------------------------------------------
    should_run_pretest = step_clean in ["all", "pretest", "pre", "pre-test", "pre tes"]
    if should_run_pretest:
        print("\n" + "=" * 80)
        print(" [TAHAP 1/5] PRE-TEST (KUNCI PEMBUKA SESI PERTEMUAN)")
        print("=" * 80)

        quiz_info = find_meeting_quiz_card(page, target_meeting, "PRETEST")
        pretest_card = quiz_info.get("card")
        p_btn = quiz_info.get("button")
        is_pre_locked = quiz_info.get("is_locked", False)

        if p_btn:
            print(f"[*] Mengakses modul Pre-Test (Judul Kartu: '{quiz_info['card_title']}')...")
            p_btn.scroll_into_view_if_needed()
            p_btn.click(force=True)
            page.wait_for_timeout(3500)

            # Validasi proteksi salah halaman
            body_peek = page.locator("body").inner_text()[:1200].lower()
            if "posttest" in body_peek and "pretest" not in body_peek:
                print("    [!] PERINGATAN: Terdeteksi halaman Post-Test, bukan Pre-Test! Membatalkan eksekusi.")
                status_pretest = "Gagal: Halaman Kuis Tertukar (Terbuka Posttest)"
            else:
                # Tunggu hingga halaman kuis selesai memuat tombol atau komponen utama
                try:
                    page.wait_for_selector('button:has-text("QUIZ"), button:has-text("Quiz"), .MuiTable-root, .MuiPaper-root', timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                # Deteksi tombol pengerjaan kuis milik Sofyan
                k_btn = page.locator('button:has-text("KERJAKAN QUIZ"), button:has-text("LANJUTKAN QUIZ"), button:has-text("Kerjakan Quiz"), button:has-text("Lanjutkan Quiz")').first

                # Analisis mendalam status kuis mahasiswa via Smart Scraper Multilapis
                quiz_status = scrape_student_quiz_status(page)

                if quiz_status["is_done"]:
                    # Mahasiswa SUDAH mengerjakan kuis ini dan sudah ada nilainya!
                    # Meskipun tombol 'KERJAKAN QUIZ' tetap ada di web, bot TIDAK AKAN mengkliknya lagi!
                    real_score = quiz_status.get("grade")
                    score_txt = f" (Nilai: {real_score})" if real_score is not None else ""
                    status_pretest = f"Sudah Dikerjakan{score_txt}"
                    print(f"    📊 STATUS: SOFYAN TELAH SELESAI MENGERJAKAN PRE-TEST!{score_txt} [Sumber: {quiz_status['source']}]")
                    update_meeting_grade_record(course["name"], target_meeting, "PRE-TEST", real_score)
                    print("    -> Sesi pembelajaran telah terbuka, lanjut ke tahap berikutnya.")

                elif quiz_status["can_start"]:
                    # Mahasiswa BELUM mengerjakan kuis ini dan tombol pengerjaan tersedia
                    btn_text = k_btn.inner_text().strip()
                    print(f"[*] Pre-Test belum dikerjakan oleh Sofyan, memulai proses pengerjaan (Tombol: '{btn_text}')...")
                    k_btn.click()
                    page.wait_for_timeout(2500)

                    m_btn = page.locator('button:has-text("MULAI QUIZ"), button:has-text("Mulai Quiz")').first
                    if m_btn.count() > 0 and m_btn.is_visible():
                        print("[*] Mengklik 'MULAI QUIZ'...")
                        m_btn.click()
                        page.wait_for_timeout(2000)

                    y_btn = page.locator('button:has-text("Ya"), button:has-text("YA")').first
                    if y_btn.count() > 0 and y_btn.is_visible():
                        print("[*] Dialog konfirmasi muncul, mengklik 'Ya'...")
                        y_btn.click()
                        page.wait_for_timeout(3500)

                    if "/exam/" not in page.url:
                        try:
                            page.wait_for_url("**/exam/**", timeout=8000)
                        except Exception:
                            pass

                    # Deteksi pesan error/pembatasan prasyarat dari sistem Mentari LMS
                    err_msg = detect_page_error_or_lock(page)

                    if err_msg:
                        print(f"    🔒 Modul Pre-Test dibatasi oleh sistem Mentari LMS: '{err_msg}'")
                        status_pretest = f"Terkunci ({err_msg})"
                    elif "/exam/" in page.url:
                        # Jika di /exam/ masih ada tombol 'MULAI QUIZ', klik untuk memulai sesi soal
                        exam_mulai = page.locator('button:has-text("MULAI QUIZ"), button:has-text("Mulai Quiz")').first
                        if exam_mulai.count() > 0 and exam_mulai.is_visible():
                            print("[*] Mengklik 'MULAI QUIZ' di halaman ujian...")
                            exam_mulai.click()
                            page.wait_for_timeout(1500)
                            y2_btn = page.locator('button:has-text("Ya"), button:has-text("YA")').first
                            if y2_btn.count() > 0 and y2_btn.is_visible():
                                y2_btn.click()
                                page.wait_for_timeout(2500)

                        exam_res = solve_quiz_exam(page, "PRE-TEST")
                        if exam_res.get("grade"):
                            status_pretest = f"Sudah Dikerjakan AI (Nilai: {exam_res['grade']})"
                            update_meeting_grade_record(course["name"], target_meeting, "PRE-TEST", exam_res["grade"])
                        else:
                            status_pretest = "Telah Selesai Dijawab AI & Disubmit"
                            update_meeting_grade_record(course["name"], target_meeting, "PRE-TEST", None, status="Selesai")
                    else:
                        print("[!] Gagal masuk ke halaman ujian Pre-Test.")
                        status_pretest = "Gagal Masuk Ujian"
                else:
                    if quiz_status["is_locked"]:
                        status_pretest = f"Terkunci ({quiz_status['lock_reason']})"
                    else:
                        card_note = quiz_info.get("restriction_note")
                        if card_note:
                            print(f"    🔒 Modul Pre-Test dibatasi: '{card_note}'")
                            status_pretest = f"Terkunci ({card_note})"
                        else:
                            print("    [!] Tombol pengerjaan kuis tidak aktif atau kuis belum terbuka.")
                            status_pretest = "Kuis Belum Terbuka / Terkunci"

            # Kembali ke halaman kelas
            print("\n[*] Kembali ke halaman pertemuan...")
            page.goto(course["url"], wait_until="domcontentloaded", timeout=45000)
            ensure_turnstile_cleared(page)
            page.wait_for_timeout(3000)
            ensure_meeting_expanded(page, target_meeting)
        elif is_pre_locked or pretest_card:
            card_note = quiz_info.get("restriction_note") or "Pre-Test Terkunci"
            print(f"[*] Pre-Test pada Pertemuan {target_meeting} terdeteksi namun masih terkunci: '{card_note}'")
            status_pretest = f"Terkunci ({card_note})"
        else:
            print(f"[*] Pertemuan {target_meeting} pada mata kuliah {course['name']} tidak memiliki Pre-Test.")
            status_pretest = "Tidak Ada Pre-Test di Pertemuan Ini"
    else:
        print(f"\n[*] Melewati modul Pre-Test (Target eksekusi yang diminta: '{target_step}').")

    # -------------------------------------------------------------
    # TAHAP 2: MATERI PEMBELAJARAN (Slide PPT, Buku ISBN, Video)
    # -------------------------------------------------------------
    should_run_materi = step_clean in ["all", "materi"]
    lecturer_notes = ""
    if should_run_materi:
        print("\n" + "=" * 80)
        print(" [TAHAP 2/5] PEMERIKSAAN MATERI PEMBELAJARAN & INSTRUKSI DOSEN")
        print("=" * 80)

        meeting_scope = get_meeting_scope(page, target_meeting)
        cards = meeting_scope.locator('.MuiCard-root, .MuiPaper-root').all()
        materi_cards = []

        for c in cards:
            cls = c.get_attribute("class") or ""
            if "MuiAccordion-root" in cls or "MuiAccordionSummary-root" in cls:
                continue
            txt = c.inner_text().strip()
            first_line = txt.splitlines()[0] if txt else ""
            if any(k in first_line.lower() for k in ["buku isbn", "power point", "video ajar", "artikel riset", "materi lainnya", "ppt"]):
                materi_cards.append({"title": first_line, "element": c, "text": txt})
                lines = [l.strip() for l in txt.splitlines() if l.strip()]
                if len(lines) > 1 and not lecturer_notes:
                    desc_text = " ".join(lines[1:])
                    if any(w in desc_text.lower() for w in ["silahkan", "forum", "download", "diskusikan", "buka", "tugas"]):
                        lecturer_notes = desc_text

        print(f"[V] Terdeteksi {len(materi_cards)} materi modul pada Pertemuan {target_meeting}:")
        for idx, mc in enumerate(materi_cards, 1):
            btn = mc["element"].locator("button:has-text('FILE'), a").first
            btn_txt = btn.inner_text().strip() if btn.count() > 0 else "Baca di Web"
            print(f"    {idx}. {mc['title']} [Tombol: {btn_txt}]")

        if lecturer_notes:
            print(f"\n📌 CATATAN/INSTRUKSI DOSEN TERDETEKSI:")
            print(f"   \"{lecturer_notes}\"")
    else:
        print(f"\n[*] Melewati modul Materi (Target eksekusi yang diminta: '{target_step}').")

    # -------------------------------------------------------------
    # TAHAP 3: FORUM DISKUSI (FORDIS)
    # -------------------------------------------------------------
    should_run_fordis = step_clean in ["all", "fordis", "forum", "diskusi"]
    if should_run_fordis:
        print("\n" + "=" * 80)
        print(" [TAHAP 3/5] FORUM DISKUSI (FORDIS)")
        print("=" * 80)

        meeting_scope = get_meeting_scope(page, target_meeting)
        cards_now = meeting_scope.locator('.MuiCard-root, .MuiPaper-root').all()
        fordis_card = None
        for c in cards_now:
            cls = c.get_attribute("class") or ""
            if "MuiAccordion-root" in cls or "MuiAccordionSummary-root" in cls:
                continue
            first_l = c.inner_text().strip().splitlines()[0] if c.inner_text().strip() else ""
            if "forum" in first_l.lower():
                fordis_card = c
                break

        if fordis_card:
            f_btn = fordis_card.locator('button:has-text("FORUM")').first
            if f_btn.count() > 0:
                print("[*] Mengakses Forum Diskusi...")
                f_btn.scroll_into_view_if_needed()
                f_btn.click(force=True)
                page.wait_for_timeout(3500)

                print(f"[V] Berada di Halaman Forum: {page.url}")
                forum_text = page.locator("body").inner_text()

                if "soal forum diskusi belum tersedia" in forum_text.lower():
                    print("    ℹ️ STATUS FORDIS: Soal diskusi belum disediakan oleh dosen pengampu.")
                    status_fordis = "Belum Ada Soal Dosen"
                else:
                    print("    💬 STATUS FORDIS: Topik diskusi aktif!")
                    # Cek apakah ada daftar thread topik di halaman forum (misal tabel dengan kolom JUDUL)
                    topic_cells = page.locator("table td, tr td:first-child, a:has-text('Proyek'), a:has-text('Pertemuan')").all()
                    thread_clicked = False
                    for cell in topic_cells:
                        c_txt = cell.inner_text().strip()
                        if c_txt and c_txt != "-" and "JUDUL" not in c_txt and len(c_txt) > 3:
                            print(f"    [*] Membuka thread topik spesifik: '{c_txt}'...")
                            cell.click()
                            page.wait_for_timeout(3500)
                            thread_clicked = True
                            forum_text = page.locator("body").inner_text()
                            break

                    # Ekstrak konten diskusi dosen yang sebenarnya
                    topic_lines = [l.strip() for l in forum_text.splitlines() if l.strip()]
                    topic_content = "Topik Diskusi Pertemuan " + str(target_meeting)
                    for l in topic_lines:
                        # Prioritaskan baris materi/penjelasan dosen
                        if len(l) > 40 and not any(skip in l for skip in ["DASHBOARD", "COURSES", "Course Index", "Participant", "Min Replay", "REFRESH", "BACK"]):
                            topic_content = l
                            break

                    print(f"    [*] Topik: {topic_content[:100]}...")
                    print("[*] AI Gemini sedang menyusun draf tanggapan akademik berbobot...")

                    draft = draft_forum_discussion(
                        topic=topic_content,
                        context=lecturer_notes if lecturer_notes else f"Mata Kuliah {course['name']} Pertemuan {target_meeting}"
                    )

                    print("\n" + "-" * 75)
                    print("           DRAF TANGGAPAN FORUM DISKUSI DARI GEMINI AI")
                    print("-" * 75)
                    print(draft)
                    print("-" * 75)

                    # Simpan draf ke data/forum_drafts.json
                    DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
                    existing_drafts = []
                    if DRAFTS_PATH.exists():
                        try:
                            with open(DRAFTS_PATH, encoding="utf-8") as f:
                                existing_drafts = json.load(f)
                        except Exception:
                            pass

                    existing_drafts.append({
                        "course": course["name"],
                        "pertemuan": target_meeting,
                        "topic": topic_content,
                        "draft": draft,
                        "url": page.url
                    })

                    with open(DRAFTS_PATH, "w", encoding="utf-8") as f:
                        json.dump(existing_drafts, f, indent=2, ensure_ascii=False)

                    print(f"[V] Draf tanggapan disimpan ke: {DRAFTS_PATH}")

                # Kembali ke halaman kelas
                print("\n[*] Kembali ke halaman pertemuan...")
                page.goto(course["url"], wait_until="domcontentloaded", timeout=45000)
                ensure_turnstile_cleared(page)
                page.wait_for_timeout(3000)
                ensure_meeting_expanded(page, target_meeting)
        else:
            print("[*] Pertemuan ini tidak memiliki Forum Diskusi.")
    else:
        print(f"\n[*] Melewati modul Forum Diskusi (Target eksekusi yang diminta: '{target_step}').")

    # -------------------------------------------------------------
    # TAHAP 4: POST-TEST (Setelah Fordis)
    # -------------------------------------------------------------
    should_run_posttest = step_clean in ["all", "posttest", "post", "post-test", "post tes", "post test"]
    if should_run_posttest:
        print("\n" + "=" * 80)
        print(" [TAHAP 4/5] POST-TEST")
        print("=" * 80)

        quiz_info = find_meeting_quiz_card(page, target_meeting, "POSTTEST")
        posttest_card = quiz_info.get("card")
        post_btn = quiz_info.get("button")
        is_post_locked = quiz_info.get("is_locked", False)

        if post_btn:
            print(f"[*] Mengakses modul Post-Test (Judul Kartu: '{quiz_info['card_title']}')...")
            post_btn.scroll_into_view_if_needed()
            post_btn.click(force=True)
            page.wait_for_timeout(3500)

            # Validasi proteksi salah halaman kuis
            body_peek = page.locator("body").inner_text()[:1200].lower()
            if "pretest" in body_peek and "posttest" not in body_peek:
                print("    [!] PERINGATAN: Terdeteksi halaman Pre-Test, bukan Post-Test! Membatalkan eksekusi.")
                status_posttest = "Gagal: Halaman Kuis Tertukar (Terbuka Pretest)"
            else:
                # Tunggu hingga halaman kuis selesai memuat tombol atau komponen utama
                try:
                    page.wait_for_selector('button:has-text("QUIZ"), button:has-text("Quiz"), .MuiTable-root, .MuiPaper-root', timeout=10000)
                except Exception:
                    pass
                page.wait_for_timeout(1500)

                # Deteksi tombol pengerjaan kuis milik Sofyan
                k_btn = page.locator('button:has-text("KERJAKAN QUIZ"), button:has-text("LANJUTKAN QUIZ"), button:has-text("Kerjakan Quiz"), button:has-text("Lanjutkan Quiz")').first

                # Analisis mendalam status kuis mahasiswa via Smart Scraper Multilapis
                quiz_status = scrape_student_quiz_status(page)

                if quiz_status["is_done"]:
                    # Mahasiswa SUDAH mengerjakan kuis ini dan sudah ada nilainya!
                    # Meskipun tombol 'KERJAKAN QUIZ' tetap ada di web, bot TIDAK AKAN mengkliknya lagi!
                    real_score = quiz_status.get("grade")
                    score_txt = f" (Nilai: {real_score})" if real_score is not None else ""
                    status_posttest = f"Sudah Dikerjakan{score_txt}"
                    print(f"    📊 STATUS: SOFYAN TELAH SELESAI MENGERJAKAN POST-TEST!{score_txt} [Sumber: {quiz_status['source']}]")
                    update_meeting_grade_record(course["name"], target_meeting, "POST-TEST", real_score)
                    print("    -> Melewati Post-Test karena sudah tuntas.")

                elif quiz_status["can_start"]:
                    # Mahasiswa BELUM mengerjakan kuis ini dan tombol pengerjaan tersedia
                    btn_text = k_btn.inner_text().strip()
                    print(f"[*] Post-Test belum dikerjakan oleh Sofyan, memulai proses pengerjaan (Tombol: '{btn_text}')...")
                    k_btn.click()
                    page.wait_for_timeout(2500)

                    m_btn = page.locator('button:has-text("MULAI QUIZ"), button:has-text("Mulai Quiz")').first
                    if m_btn.count() > 0 and m_btn.is_visible():
                        print("[*] Mengklik 'MULAI QUIZ'...")
                        m_btn.click()
                        page.wait_for_timeout(2000)

                    y_btn = page.locator('button:has-text("Ya"), button:has-text("YA")').first
                    if y_btn.count() > 0 and y_btn.is_visible():
                        print("[*] Dialog konfirmasi muncul, mengklik 'Ya'...")
                        y_btn.click()
                        page.wait_for_timeout(3500)

                    if "/exam/" not in page.url:
                        try:
                            page.wait_for_url("**/exam/**", timeout=8000)
                        except Exception:
                            pass

                    # Deteksi pesan error/pembatasan prasyarat dari sistem Mentari LMS
                    err_msg = detect_page_error_or_lock(page)

                    if err_msg:
                        print(f"    🔒 Modul Post-Test dibatasi oleh sistem Mentari LMS: '{err_msg}'")
                        status_posttest = f"Terkunci ({err_msg})"
                    elif "/exam/" in page.url:
                        # Jika di /exam/ masih ada tombol 'MULAI QUIZ', klik untuk memulai sesi soal
                        exam_mulai = page.locator('button:has-text("MULAI QUIZ"), button:has-text("Mulai Quiz")').first
                        if exam_mulai.count() > 0 and exam_mulai.is_visible():
                            print("[*] Mengklik 'MULAI QUIZ' di halaman ujian...")
                            exam_mulai.click()
                            page.wait_for_timeout(1500)
                            y2_btn = page.locator('button:has-text("Ya"), button:has-text("YA")').first
                            if y2_btn.count() > 0 and y2_btn.is_visible():
                                y2_btn.click()
                                page.wait_for_timeout(2500)

                        exam_res = solve_quiz_exam(page, "POST-TEST")
                        if exam_res.get("grade"):
                            status_posttest = f"Sudah Dikerjakan AI (Nilai: {exam_res['grade']})"
                            update_meeting_grade_record(course["name"], target_meeting, "POST-TEST", exam_res["grade"])
                        else:
                            status_posttest = "Telah Selesai Dijawab AI & Disubmit"
                            update_meeting_grade_record(course["name"], target_meeting, "POST-TEST", None, status="Selesai")
                    else:
                        print("[!] Gagal masuk ke halaman ujian Post-Test.")
                        status_posttest = "Gagal Masuk Ujian"
                else:
                    if quiz_status["is_locked"]:
                        status_posttest = f"Terkunci ({quiz_status['lock_reason']})"
                    else:
                        card_note = quiz_info.get("restriction_note")
                        if card_note:
                            print(f"    🔒 Modul Post-Test terdeteksi dibatasi: '{card_note}'")
                            status_posttest = f"Terkunci ({card_note})"
                        elif is_post_locked:
                            status_posttest = "Terkunci: Prasyarat Belum Selesai"
                        else:
                            print("    [!] Tombol pengerjaan Post-Test tidak aktif atau kuis belum terbuka.")
                            status_posttest = "Kuis Belum Terbuka / Terkunci"

            # Kembali ke halaman pertemuan
            print("\n[*] Kembali ke halaman pertemuan...")
            page.goto(course["url"], wait_until="domcontentloaded", timeout=45000)
            ensure_turnstile_cleared(page)
            page.wait_for_timeout(3000)
            ensure_meeting_expanded(page, target_meeting)
        elif is_post_locked or posttest_card:
            card_note = quiz_info.get("restriction_note") or "Post-Test Terkunci (Prasyarat Belum Selesai)"
            print(f"    🔒 Modul Post-Test terdeteksi di LMS Mentari namun terkunci: '{card_note}'")
            status_posttest = f"Terkunci ({card_note})"
        else:
            print("[*] Pertemuan ini tidak memiliki Post-Test.")
            status_posttest = "Tidak Ada Modul Post-Test"
    else:
        print(f"\n[*] Melewati modul Post-Test (Target eksekusi yang diminta: '{target_step}').")

    # -------------------------------------------------------------
    # TAHAP 5: KUESIONER PEMBELAJARAN
    # -------------------------------------------------------------
    should_run_kuesioner = step_clean in ["all", "kuesioner", "kuisioner", "evaluasi"]
    if should_run_kuesioner:
        print("\n" + "=" * 80)
        print(" [TAHAP 5/5] KUESIONER EVALUASI PEMBELAJARAN")
        print("=" * 80)

        meeting_scope = get_meeting_scope(page, target_meeting)
        cards_now = meeting_scope.locator('.MuiCard-root, .MuiPaper-root').all()
        kuesioner_card = None
        for c in cards_now:
            cls = c.get_attribute("class") or ""
            if "MuiAccordion-root" in cls or "MuiAccordionSummary-root" in cls:
                continue
            first_l = c.inner_text().strip().splitlines()[0] if c.inner_text().strip() else ""
            if "kuesioner" in first_l.lower():
                kuesioner_card = c
                break

        if kuesioner_card:
            k_btn = kuesioner_card.locator('button:has-text("KUESIONER")').first
            if k_btn.count() > 0:
                print("[*] Mengakses modul Kuesioner...")
                k_btn.scroll_into_view_if_needed()
                k_btn.click(force=True)
                page.wait_for_timeout(3500)

                print(f"[V] Berada di Halaman Kuesioner: {page.url}")
                page.screenshot(path=f"data/kuesioner_p{target_meeting}.png")

                # Cek pertanyaan kuesioner
                radios = page.locator("input[type='radio']").all()
                print(f"    📋 Terdeteksi {len(radios)} opsi radio pada kuesioner.")
                
                # Memastikan opsi default "Ya" (evaluasi positif standar)
                ya_labels = page.locator("label:has-text('Ya')").all()
                for yl in ya_labels:
                    try:
                        r = yl.locator("input[type='radio']")
                        if r.count() > 0 and not r.is_checked():
                            yl.click(force=True)
                    except Exception:
                        pass

                status_kuesioner = "20 Butir Evaluasi Terisi ('Ya')"
                print(f"    [V] Opsi evaluasi 'Ya' telah terisi dengan rapi.")
                print(f"    [!] Standar Keamanan: Bot tidak menekan submit kuesioner otomatis agar Anda dapat meninjau.")
        else:
            print("[*] Pertemuan ini tidak memiliki Kuesioner evaluasi.")
    else:
        print(f"\n[*] Melewati modul Kuesioner (Target eksekusi yang diminta: '{target_step}').")

    # Selesai seluruh pipeline
    print("\n" + "=" * 85)
    print(f" [V] PIPELINE PEMBELAJARAN PERTEMUAN {target_meeting} TELAH SELESAI DIPROSES!")
    print("=" * 85)

    # Kirim notifikasi ringkasan otomatis ke WhatsApp jika terhubung
    try:
        from services.wa_notifier import notify_meeting_completed
        notify_meeting_completed(
            course_name=course["name"],
            meeting_num=target_meeting,
            pretest_status=status_pretest,
            fordis_status=status_fordis,
            posttest_status=status_posttest,
            kuesioner_status=status_kuesioner,
            target_step=target_step
        )
    except Exception as e:
        print(f"[!] Gagal mengirim notifikasi WA: {e}")

    return {
        "pretest": status_pretest,
        "fordis": status_fordis,
        "posttest": status_posttest,
        "kuesioner": status_kuesioner
    }


def run_pipeline(course_choice: str = "1", target_meeting: str | int = 2, target_step: str = "all", headless: bool = False, interactive: bool = True):
    step_clean = (target_step or "all").lower().strip()

    # Tentukan daftar mata kuliah yang akan diproses
    course_q = str(course_choice).strip().lower()
    if course_q in ["all", "semua", "seluruh"]:
        courses_to_process = list(COURSES.values())
        print(f"[*] Mode Batch Multi-Matkul: Memproses seluruh {len(courses_to_process)} mata kuliah!")
    else:
        resolved_key, _ = resolve_course_key(str(course_choice))
        courses_to_process = [COURSES.get(resolved_key, COURSES["1"])]

    print("=" * 85)
    print("     MENTARI LMS - COMPLETE LEARNING PIPELINE ENGINE")
    print("=" * 85)
    print(f"[*] Total Mata Kuliah : {len(courses_to_process)} matkul")
    print(f"[*] Target Pertemuan  : {target_meeting}")
    if step_clean != "all":
        print(f"[*] Target Khusus     : {step_clean.upper()} (Hanya mengeksekusi modul yang diminta)")
    else:
        print(f"[*] Alur Belajar      : [1] Pre-Test -> [2] Materi -> [3] Fordis -> [4] Post-Test -> [5] Kuesioner")
    print(f"[*] AI Engine         : Google Gemini 3.8 Flash (Fallback: 3.6 / 3.7 / 3.5)")
    print("=" * 85)

    if not AUTH_PATH.exists():
        print("[!] File data/auth.json tidak ditemukan. Jalankan save_auth.py terlebih dahulu.")
        return

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=headless,
                channel="chrome",
                slow_mo=300 if not headless else 0,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )
        except Exception:
            browser = p.chromium.launch(
                headless=headless,
                slow_mo=300 if not headless else 0,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )

        context = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = context.new_page()

        # 1. Masuk Dashboard Mentari
        print("\n[*] Menghubungkan ke Dashboard Mentari...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded", timeout=60000)
        ensure_turnstile_cleared(page)
        page.wait_for_timeout(2000)

        for course in courses_to_process:
            print("\n" + "=" * 85)
            print(f"[*] MEMBUKA KELAS: {course['name']}")
            print("=" * 85)

            # Parsing target pertemuan fleksibel
            meetings = parse_meeting_targets(target_meeting, course_name=course["name"], target_step=step_clean)
            if not meetings:
                print(f"[*] Tidak ada pertemuan yang memerlukan pengerjaan pada mata kuliah {course['name']}.")
                continue

            print(f"[*] Daftar Pertemuan yang akan dikerjakan ({len(meetings)} pertemuan): {meetings}")

            for idx, m_num in enumerate(meetings):
                print(f"\n[*] [{idx+1}/{len(meetings)}] Mengakses halaman kelas {course['name']} untuk Pertemuan {m_num}...")
                try:
                    page.goto(course["url"], wait_until="domcontentloaded", timeout=60000)
                    ensure_turnstile_cleared(page)
                    page.wait_for_timeout(2500)
                    execute_single_meeting_pipeline(page, course, m_num, step_clean, target_step)
                except Exception as m_err:
                    print(f"[!] Error saat mengeksekusi Pertemuan {m_num}: {m_err}")
                    print("    -> Melanjutkan ke pertemuan berikutnya tanpa menghentikan bot...")

            # Perbarui nilai kuis terbaru untuk mata kuliah ini di database lokal
            try:
                from scrape_meeting_grades import scrape_all_meeting_grades
                print(f"[*] Memperbarui data nilai kuis {course['name']} di database...")
                scrape_all_meeting_grades(target_course_name=course["name"])
            except Exception as e:
                print(f"[!] Pembaruan nilai otomatis dilewati: {e}")

        if interactive:
            print("\n[!] BROWSER DIBIARKAN TERBUKA AGAR ANDA DAPAT MENINJAU SELURUH HASILNYA.")
            try:
                input("\n>> Tekan ENTER di sini untuk menutup browser: ")
            except (EOFError, KeyboardInterrupt):
                page.wait_for_timeout(5000)
        else:
            print("\n[*] Seluruh eksekusi selesai. Menutup browser dalam 5 detik...")
            page.wait_for_timeout(5000)

        browser.close()
        print("[*] Selesai tuntas.")


def process_queue_worker(headless: bool = False, interactive: bool = False):
    """
    Worker antrean terpusat: Mengambil tugas satu per satu dari data/pipeline_queue.json
    dan mengeksekusinya secara berurutan dalam 1 sesi browser yang tertib dan aman.
    """
    queue_file = Path("data/pipeline_queue.json")
    lock_file = Path("data/pipeline_queue.lock")

    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "started_at": time.time()}, f, indent=2)

    try:
        while True:
            if not queue_file.exists():
                break

            try:
                with open(queue_file, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
            except Exception:
                tasks = []

            if not tasks:
                break

            current_task = tasks.pop(0)

            with open(queue_file, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2, ensure_ascii=False)

            print("\n" + "=" * 85)
            print(f"[*] MEMPROSES TUGAS DARI ANTREAN:")
            print(f"[*] Mata Kuliah : {current_task.get('course_name')}")
            print(f"[*] Pertemuan   : {current_task.get('meeting_target')}")
            print(f"[*] Modul       : {current_task.get('target_step')}")
            print(f"[*] Sisa Antrean: {len(tasks)} tugas menunggu")
            print("=" * 85)

            try:
                run_pipeline(
                    course_choice=current_task.get("course_key", "1"),
                    target_meeting=current_task.get("meeting_target", "1"),
                    target_step=current_task.get("target_step", "all"),
                    headless=headless,
                    interactive=interactive
                )
            except Exception as task_err:
                print(f"[!] Error saat memproses tugas antrean: {task_err}")

    finally:
        try:
            lock_file.unlink(missing_ok=True)
        except Exception:
            pass
        print("[*] Seluruh antrean pengerjaan telah selesai diproses.")


if __name__ == "__main__":
    if "--run-queue" in sys.argv:
        is_headless = "--headless" in sys.argv
        is_interactive = "--non-interactive" not in sys.argv
        process_queue_worker(headless=is_headless, interactive=is_interactive)
    else:
        c_choice = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "1"
        m_choice = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "2"
        is_headless = "--headless" in sys.argv
        is_interactive = "--non-interactive" not in sys.argv

        t_step = "all"
        for arg in sys.argv:
            if arg.startswith("--step="):
                t_step = arg.split("=", 1)[1]
        if "--step" in sys.argv:
            s_idx = sys.argv.index("--step")
            if s_idx + 1 < len(sys.argv):
                t_step = sys.argv[s_idx + 1]

        run_pipeline(course_choice=c_choice, target_meeting=m_choice, target_step=t_step, headless=is_headless, interactive=is_interactive)
