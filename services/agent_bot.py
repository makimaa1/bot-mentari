import os
import sys
import json
import re
import subprocess
import functools
from pathlib import Path
from dotenv import load_dotenv

# Reconfigure console output for Windows UTF-8 safety
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

AUDIT_PATH = BASE_DIR / "data" / "mentari_master_audit.json"
DRAFTS_PATH = BASE_DIR / "data" / "forum_drafts.json"
FORUM_DETAILS_PATH = BASE_DIR / "data" / "mentari_forum_details.json"
GRADEBOOK_PATH = BASE_DIR / "data" / "mentari_gradebook_master.json"
MEETING_GRADES_PATH = BASE_DIR / "data" / "mentari_meeting_grades.json"
COURSES_METADATA_PATH = BASE_DIR / "data" / "mentari_courses_metadata.json"

def format_date_str(iso_str: str) -> str:
    """Format ISO timestamp ke format ramah bahasa Indonesia (e.g. 08 Sep 2026)."""
    if not iso_str:
        return ""
    try:
        parts = iso_str.split("T")[0].split("-")
        months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
        m_idx = int(parts[1]) - 1
        return f"{parts[2]} {months[m_idx]} {parts[0]}"
    except Exception:
        return iso_str[:10]

COURSES_MAP = {
    "1": "MANAJEMEN PROYEK INFORMATIKA",
    "2": "ARSITEKTUR DAN ORGANISASI KOMPUTER",
    "3": "KEAMANAN KOMPUTER",
    "4": "JARINGAN NIRKABEL",
    "5": "KECAKAPAN ANTAR PERSONAL",
    "6": "TESTING DAN QA PERANGKAT LUNAK",
    "7": "ETIKA PROFESI",
    "8": "PEMROGRAMAN WEB II"
}

COURSE_WEIGHTS = {
    "1": [("manajemen proyek informatika", 20), ("manajemen proyek", 15), ("manpro", 12), ("mpi", 12), ("manajemen", 6), ("proyek", 6)],
    "2": [("arsitektur dan organisasi komputer", 20), ("arsitektur dan organisasi", 15), ("organisasi komputer", 12), ("arkom", 12), ("aok", 12), ("arsitektur", 10), ("organisasi", 8)],
    "3": [("keamanan jaringan", 18), ("keamanan jaringaan", 18), ("keamanan komputer", 18), ("kamjar", 15), ("cyber security", 15), ("infosec", 15), ("keamanan", 10), ("security", 8)],
    "4": [("jaringan nirkabel", 18), ("nirkabel", 15), ("wireless", 15), ("jarkom", 12), ("jaringan", 6)],
    "5": [("kecakapan antar personal", 18), ("antar personal", 15), ("antarpersonal", 15), ("interpersonal", 12), ("kap", 10), ("kecakapan", 8), ("personal", 4)],
    "6": [("testing dan qa perangkat lunak", 20), ("testing dan qa", 18), ("qa perangkat lunak", 18), ("testing qa", 15), ("quality assurance", 15), ("tqa", 12), ("testing", 10), ("qa", 10), ("pengujian", 8)],
    "7": [("etika profesi", 18), ("etprof", 12), ("etika", 10), ("profesi", 8)],
    "8": [("pemrograman web ii", 18), ("pemrograman web 2", 18), ("pemrograman web", 15), ("pemweb ii", 15), ("pemweb 2", 15), ("web ii", 15), ("web 2", 15), ("pemweb", 10), ("web", 5)]
}

def resolve_course_key(query: str, strict: bool = False) -> tuple[str, str]:
    """
    Menyelesaikan nama mata kuliah / alias / singkatan / nomor ke kunci resmi ('1'-'8')
    dan nama mata kuliah kanonikal secara deterministik dan anti-salah.
    Mencegah salah target (misal: 'keamanan jaringan' salah ke 'arsitektur komputer').
    """
    if not query:
        if strict:
            raise ValueError("Mata kuliah belum disebutkan.")
        return "1", COURSES_MAP["1"]
    q = str(query).strip().lower()

    # 1. Kunci nomor langsung
    if q in COURSES_MAP:
        return q, COURSES_MAP[q]

    # 2. Nama persis
    for k, name in COURSES_MAP.items():
        if q == name.lower():
            return k, name

    # 3. Pembobotan skor kata kunci & alias khusus (anti tumpang-tindih)
    scores = {k: 0 for k in COURSES_MAP}
    for k, patterns in COURSE_WEIGHTS.items():
        for pat, weight in patterns:
            # Pola pendek (<= 5 huruf) harus match batas kata \b agar tidak salah match (misal 'arkom' di 'jarkom')
            if len(pat) <= 5:
                if re.search(r'\b' + re.escape(pat) + r'\b', q):
                    scores[k] += weight
            else:
                if re.search(r'\b' + re.escape(pat) + r'\b', q) or pat in q:
                    scores[k] += weight

    best_key = max(scores, key=lambda k: scores[k])
    if scores[best_key] > 0:
        if strict and sum(value == scores[best_key] for value in scores.values()) > 1:
            raise ValueError("Nama mata kuliah ambigu; sebutkan satu mata kuliah.")
        return best_key, COURSES_MAP[best_key]

    if strict:
        raise ValueError("Mata kuliah tidak dikenal; gunakan nama atau nomor 1-8.")
    return "1", COURSES_MAP["1"]


# =====================================================================
# DATA AUDIT PARSING HELPERS
# =====================================================================

def find_forum_detail(course_name: str, meeting_num: int = None):
    """Mencari detail soal dosen dan riwayat jawaban mahasiswa pada fordis."""
    if not FORUM_DETAILS_PATH.exists():
        return None
    try:
        with open(FORUM_DETAILS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    target_key, canonical_name = resolve_course_key(course_name) if course_name else (None, None)
    for item in data:
        c_n = item.get("course", "").lower()
        m_n = item.get("pertemuan")
        c_match = (not course_name) or (canonical_name.lower() in c_n) or (c_n in canonical_name.lower())
        m_match = (meeting_num is None) or (meeting_num == m_n)
        if c_match and m_match:
            return item
    return None

def find_course_in_audit(query: str):
    """Mencocokkan nama mata kuliah dari database audit secara presisi menggunakan resolver kanonikal."""
    if not AUDIT_PATH.exists():
        return None
    try:
        with open(AUDIT_PATH, encoding="utf-8") as f:
            audit = json.load(f)
    except Exception:
        return None

    if not query:
        return None

    target_key, canonical_name = resolve_course_key(query)

    for c in audit:
        c_name = c.get("course_name", "")
        if c_name.upper() == canonical_name.upper():
            return c

    for c in audit:
        c_name = c.get("course_name", "").lower()
        if canonical_name.lower() in c_name:
            return c

    return None


# =====================================================================
# AGENT TOOL FUNCTIONS (READ-ONLY & ACTION SEPARATED)
# =====================================================================

def tool_check_course_forums(course_name: str) -> str:
    """
    MEMERIKSA status dan ketersediaan Forum Diskusi (Fordis) untuk suatu mata kuliah.
    Tool ini menganalisis secara detail pertemuan mana yang memiliki forum aktif (ada soal dari dosen),
    pertemuan mana yang soalnya belum tersedia, dan pertemuan mana yang tidak ada forum.
    
    Gunakan tool ini ketika pengguna bertanya tentang:
    - 'cek matkul X yang ada fordisnya pertemuan berapa aja'
    - 'ada fordis apa di matkul X'
    - 'apakah ada fordis di pertemuan Y'
    """
    c = find_course_in_audit(course_name)
    if not c:
        return f"Mata kuliah '{course_name}' tidak ditemukan di database LMS Mentari. Pilihan yang ada: {', '.join(COURSES_MAP.values())}."

    c_name = c.get("course_name", "")
    meetings = c.get("meetings", [])

    active_forums = []
    pending_forums = []
    no_forums = []

    for m in meetings:
        p_num = m.get("pertemuan")
        f = m.get("forum")
        if not f:
            no_forums.append(p_num)
        else:
            title = f.get("title", "")
            desc = f.get("description", "")
            buttons = f.get("buttons", [])

            if "belum tersedia" in title.lower() or len(buttons) == 0:
                pending_forums.append(p_num)
            else:
                topic_info = desc if desc else title
                active_forums.append({
                    "pertemuan": p_num,
                    "info": topic_info.replace(" | FORUM", "").replace(" | FILE", "")
                })

    res_lines = [f"📊 *STATUS FORUM DISKUSI: {c_name}* (Total {len(meetings)} Pertemuan)\n"]

    if active_forums:
        res_lines.append("🟢 *FORUM AKTIF (Ada Soal & Dapat Diisi):*")
        for af in active_forums:
            res_lines.append(f"  • *Pertemuan {af['pertemuan']}*: {af['info']}")
        res_lines.append("")
    else:
        res_lines.append("🔴 *FORUM AKTIF*: Belum ada forum yang aktif/dibuka pada mata kuliah ini.\n")

    if pending_forums:
        res_lines.append(f"🟡 *SOAL BELUM DIBUKA DOSEN*: Pertemuan {pending_forums}")
        res_lines.append("  _(Keterangan di LMS: 'Soal forum diskusi belum tersedia, silahkan menghubungi dosen pengampu mata kuliah')_\n")

    if no_forums:
        res_lines.append(f"⚪ *TIDAK ADA FORUM DISKUSI*: Pertemuan {no_forums}")

    return "\n".join(res_lines)


def extract_question_section(lecturer_post: str) -> str:
    """Mengambil bagian soal/studi kasus dari postingan dosen (bukan seluruh materi panjang)."""
    for marker in ("Studi Kasus", "Permasalahan Diskusi", "Pertanyaan Diskusi", "Soal"):
        idx = lecturer_post.find(marker)
        if idx != -1:
            return lecturer_post[idx:].strip()
    return lecturer_post[-2500:].strip()


def get_live_forum(course_name: str, meeting_num: int, allow_live: bool = True) -> dict | None:
    """
    Mengambil data forum ASLI dari web Mentari (scrape live). Jika browser bot sedang dipakai antrean
    pengerjaan atau scrape gagal, fallback ke cache live terakhir. Hasil disinkronkan ke mentari_forum_details.json.
    """
    from scrape_forum_live import scrape_forum_live, load_cache
    from services.task_queue import is_worker_active

    key, canon = resolve_course_key(course_name)
    data = None
    if allow_live and not is_worker_active():
        try:
            data = scrape_forum_live(key, int(meeting_num), headless=False)
            if data.get("status") == "error":
                data = None
        except Exception:
            data = None
    if data is None:
        data = load_cache(canon, int(meeting_num))
        if data:
            data["source"] = "cache"
    if not data:
        return None

    if data.get("status") == "aktif":
        from scrape_forum_live import save_cache
        save_cache(data)
    return data


def tool_get_my_fordis_answers(course_name: str, meeting_num: int = 2) -> str:
    """
    MENGAMBIL dan MENAMPILKAN riwayat jawaban, tanggapan, atau postingan yang SUDAH PERNAH DIKIRIM (di-post/disubmit)
    oleh mahasiswa (SOFYAN AGUNG) di Forum Diskusi (Fordis) LMS Mentari UNPAM pada mata kuliah dan pertemuan tertentu.
    
    Gunakan tool ini KETIKA PENGGUNA BERTANYA/MEMINTA:
    - 'cek jawaban mentari aku pertemuan 2 fordis manajemen proyek informatika'
    - 'lihat jawaban aku apa di fordis pertemuan 2'
    - 'aku sudah jawab apa aja di fordis'
    - 'cek postingan fordis saya'
    - 'apakah aku sudah menjawab fordis matkul X pertemuan Y'
    
    PERINGATAN SANGAT PENTING:
    Tool ini HANYA untuk melihat riwayat jawaban ASLI yang sudah dikirim oleh mahasiswa ke LMS Mentari!
    DILARANG membuat draf baru atau menjawab soal dosen.
    """
    try:
        get_live_forum(course_name, meeting_num)  # sinkronkan balasan asli dari web terlebih dahulu
    except Exception:
        pass
    detail = find_forum_detail(course_name, meeting_num)
    c_name = course_name.upper()

    if not detail:
        c = find_course_in_audit(course_name)
        actual_name = c.get("course_name", c_name) if c else c_name
        return (
            f"ℹ️ Belum ditemukan riwayat postingan untuk *{actual_name}* Pertemuan {meeting_num}.\n"
            f"Di LMS Mentari, pertemuan ini belum mencatat adanya tanggapan yang kamu kirimkan, atau fordis belum dibuka dosen."
        )

    actual_course = detail.get("course", c_name)
    actual_m = detail.get("pertemuan", meeting_num)
    submissions = detail.get("my_submissions", [])
    has_answered = detail.get("has_answered", False)

    if not submissions or not has_answered:
        return (
            f"📋 *STATUS JAWABAN FORDIS KAMU:*\n"
            f"📚 *Mata Kuliah*: {actual_course}\n"
            f"📍 *Pertemuan*: Pertemuan {actual_m}\n"
            f"📌 *Topik*: {detail.get('topic', '-')}\n"
            f"👨‍🏫 *Dosen*: {detail.get('dosen', '-')}\n\n"
            f"❌ *Status*: Kamu *belum mengirimkan jawaban* pada forum diskusi pertemuan ini.\n"
            f"💡 Jika kamu ingin dibikinkan ide/draf jawaban untuk diposting, kamu bisa bilang *'buatkan draf fordis'*, nanti aku siapkan!"
        )

    out_lines = [
        f"📋 *RIWAYAT JAWABAN FORUM DISKUSI KAMU DI LMS MENTARI*",
        f"👤 *Mahasiswa*: SOFYAN AGUNG (231011400159 / 07TPLP003)",
        f"📚 *Mata Kuliah*: {actual_course}",
        f"📍 *Pertemuan*: Pertemuan {actual_m}",
        f"📌 *Topik*: {detail.get('topic', '-')}",
        f"👨‍🏫 *Dosen Pengampu*: {detail.get('dosen', '-')}",
        f"✅ *Status*: *SUDAH MENJAWAB* ({len(submissions)}x Reply di LMS)",
        ""
    ]

    for s in submissions:
        idx = s.get("reply_index", 1)
        ts = s.get("timestamp", "-")
        content = s.get("content", "")
        out_lines.append(f"💬 *Jawaban / Postingan #{idx}* (📅 {ts}):")
        out_lines.append(f"\"{content}\"\n")

    if detail.get("note"):
        out_lines.append(f"ℹ️ *Catatan*: {detail.get('note')}")

    return "\n".join(out_lines)


def tool_get_fordis_question(course_name: str, meeting_num: int = 2) -> str:
    """
    MENAMPILKAN SOAL, PERTANYAAN, TOPIK, ATAU INSTRUKSI RESMI DARI DOSEN PENGAMPU pada Forum Diskusi (Fordis)
    LMS Mentari untuk mata kuliah dan pertemuan tertentu.
    
    Gunakan tool ini KETIKA PENGGUNA BERTANYA:
    - 'apa soal yang diberikan dosen di fordis manajemen proyek pertemuan 2'
    - 'dosen nanya apa di fordis p2'
    - 'cek soal fordis'
    - 'apa instruksi dosen di forum diskusi pertemuan X'
    - 'topik diskusi dosen apa'
    
    ATURAN SANGAT KRUSIAL:
    Tool ini HANYA menampilkan pertanyaan, materi pemantik, dan instruksi dari dosen!
    DILARANG KERAS MENJAWAB SOALNYA jika pengguna hanya menanyakan apa soalnya.
    """
    live = get_live_forum(course_name, meeting_num)
    if live:
        st = live.get("status")
        nm = live.get("course", course_name.upper())
        if st == "belum_tersedia":
            return (f"📌 *Mata Kuliah*: {nm} (Pertemuan {meeting_num})\n"
                    f"🟡 Di web Mentari tertulis: soal forum diskusi *belum tersedia* / belum dibuka dosen.")
        if st == "tidak_ada":
            return f"Pada {nm} Pertemuan {meeting_num}, tidak ada Forum Diskusi di web Mentari."
        if st == "aktif":
            soal = extract_question_section(live.get("lecturer_post", ""))
            src = "langsung dari web Mentari (live)" if live.get("source") == "live" else "cache terakhir dari web (browser sedang dipakai)"
            return (f"📖 *SOAL FORUM DISKUSI ASLI DARI DOSEN*\n"
                    f"📚 *Mata Kuliah*: {nm}\n📍 *Pertemuan*: {meeting_num}\n"
                    f"👨‍🏫 *Dosen*: {live.get('lecturer_name', '-')}\n"
                    f"📌 *Judul*: {live.get('title', '-')}\n"
                    f"🔄 *Sumber*: {src}\n\n📝 *Soal*:\n{soal}")
    detail = find_forum_detail(course_name, meeting_num)
    c_name = course_name.upper()

    if not detail:
        c = find_course_in_audit(course_name)
        if not c:
            return f"Mata kuliah '{course_name}' tidak ditemukan di database LMS Mentari."
        actual_name = c.get("course_name", c_name)
        target_m = None
        for m in c.get("meetings", []):
            if m.get("pertemuan") == meeting_num:
                target_m = m
                break
        if not target_m or not target_m.get("forum"):
            return f"Pada mata kuliah {actual_name} Pertemuan {meeting_num}, tidak ada Forum Diskusi (Fordis)."

        f_info = target_m.get("forum", {})
        title = f_info.get("title", "")
        desc = f_info.get("description", "")
        if "belum tersedia" in title.lower() or not f_info.get("buttons"):
            return (
                f"📌 *Mata Kuliah*: {actual_name} (Pertemuan {meeting_num})\n"
                f"🟡 *Status Soal*: Soal forum diskusi *belum tersedia* / belum dibuka oleh dosen pengampu di LMS Mentari."
            )

        soal_text = desc.replace(" | FORUM", "").replace(" | FILE", "")
        return (
            f"📖 *SOAL & INSTRUKSI DOSEN DI FORUM DISKUSI:*\n"
            f"📚 *Mata Kuliah*: {actual_name}\n"
            f"📍 *Pertemuan*: Pertemuan {meeting_num}\n\n"
            f"📝 *Materi / Pertanyaan Pemantik dari Dosen*:\n"
            f"\"{soal_text}\"\n"
        )

    actual_course = detail.get("course", c_name)
    actual_m = detail.get("pertemuan", meeting_num)
    dosen = detail.get("dosen", "Dosen Pengampu")
    topic = detail.get("topic", "-")
    instruction = detail.get("lecturer_instruction", "")

    return (
        f"📖 *SOAL & INSTRUKSI FORUM DISKUSI DARI DOSEN*\n"
        f"📚 *Mata Kuliah*: {actual_course}\n"
        f"📍 *Pertemuan*: Pertemuan {actual_m}\n"
        f"👨‍🏫 *Dosen Pengampu*: {dosen}\n"
        f"📌 *Topik Forum*: {topic}\n\n"
        f"📝 *Soal & Instruksi Resmi Dosen*:\n"
        f"{instruction}\n"
    )


def tool_get_meeting_summary(course_name: str, meeting_num: int = 2) -> str:
    """
    MEMERIKSA dan MENAMPILKAN RINGKASAN STATUS DETAIL seluruh komponen pada satu pertemuan tertentu
    (Pre-Test, Modul Materi, Forum Diskusi & Status Jawaban Mahasiswa, Post-Test, Kuesioner).
    
    Gunakan tool ini ketika pengguna bertanya:
    - 'cek pertemuan 2 manajemen proyek ada apa aja'
    - 'status pertemuan 2'
    - 'isi pertemuan X matkul Y apa aja'
    - 'apakah pertemuan 2 sudah lengkap'
    """
    c = find_course_in_audit(course_name)
    if not c:
        return f"Mata kuliah '{course_name}' tidak ditemukan di database LMS Mentari."

    c_name = c.get("course_name", "")
    target_m = None
    for m in c.get("meetings", []):
        if m.get("pertemuan") == meeting_num:
            target_m = m
            break

    if not target_m:
        return f"Pertemuan {meeting_num} tidak ditemukan pada mata kuliah {c_name}."

    # Muat data nilai riil mahasiswa untuk status pengerjaan yang 100% akurat
    meeting_grades = {}
    if MEETING_GRADES_PATH.exists():
        try:
            with open(MEETING_GRADES_PATH, encoding="utf-8") as f:
                mg_data = json.load(f)
                for k, v in mg_data.items():
                    if c_name.casefold() == k.casefold():
                        meeting_grades = v.get("meetings", {}).get(f"Pertemuan {meeting_num}", {})
                        break
        except Exception:
            pass

    pre_grade_info = meeting_grades.get("pretest", {}) if meeting_grades else None
    post_grade_info = meeting_grades.get("posttest", {}) if meeting_grades else None

    pre_is_done = bool(pre_grade_info and (pre_grade_info.get("grade") is not None or pre_grade_info.get("status") == "Selesai"))
    post_is_done = bool(post_grade_info and (post_grade_info.get("grade") is not None or post_grade_info.get("status") == "Selesai"))

    pretest = target_m.get("pretest")
    forum = target_m.get("forum")
    posttest = target_m.get("posttest")
    kuesioner = target_m.get("kuesioner")

    forum_detail = find_forum_detail(c_name, meeting_num)
    has_my_post = False
    reply_count = 0
    if forum_detail:
        reply_count = forum_detail.get("total_replies", len(forum_detail.get("my_submissions", [])))
        has_my_post = reply_count >= forum_detail.get('required_replies', 3)

    lines = [
        f"📊 *RINGKASAN STATUS PERTEMUAN {meeting_num}*",
        f"📚 *Mata Kuliah*: {c_name}",
        f"👤 *Mahasiswa*: SOFYAN AGUNG (231011400159 / 07TPLP003)\n",
        "📋 *Rincian Komponen Pembelajaran*:"
    ]

    # 1. Pretest
    if pre_is_done:
        g_txt = f" (Nilai: {pre_grade_info.get('grade')})" if pre_grade_info.get('grade') is not None else ""
        lines.append(f"  1. 📝 *Pre-Test*: ✅ *SUDAH SELESAI DIKERJAKAN*{g_txt}")
    elif pretest:
        lines.append("  1. 📝 *Pre-Test*: 🟡 *Aktif (Belum Dikerjakan)* - Perlu dikerjakan terlebih dahulu")
    else:
        lines.append("  1. 📝 *Pre-Test*: ⚪ Tidak ada kuis pre-test di pertemuan ini")

    # 2. Materi
    materi_count = len(target_m.get("materi", []))
    lines.append(f"  2. 📚 *Materi Pembelajaran*: 🟢 {materi_count} Modul & Bahan Ajar tersedia" if materi_count else "  2. 📚 *Materi Pembelajaran*: 🟢 Modul & Bahan Ajar tersedia")

    # 3. Fordis
    if forum and "belum tersedia" not in forum.get("title", "").lower() and forum.get("buttons"):
        if has_my_post:
            lines.append(f"  3. 💬 *Forum Diskusi (Fordis)*: ✅ *Sudah Dijawab* ({reply_count}x Reply)")
        elif reply_count:
            lines.append(f"  3. 💬 *Forum Diskusi (Fordis)*: 🟡 Belum lengkap ({reply_count} balasan)")
        else:
            lines.append("  3. 💬 *Forum Diskusi (Fordis)*: 🟡 *Aktif (Ada Soal Dosen)* - Belum kamu jawab")
    elif forum and "belum tersedia" in forum.get("title", "").lower():
        lines.append("  3. 💬 *Forum Diskusi (Fordis)*: ⚪ Soal belum dibuka oleh dosen")
    else:
        lines.append("  3. 💬 *Forum Diskusi (Fordis)*: ⚪ Tidak ada forum diskusi")

    # 4. Post-Test
    if post_is_done:
        g_txt = f" (Nilai: {post_grade_info.get('grade')})" if post_grade_info.get('grade') is not None else ""
        lines.append(f"  4. 🎯 *Post-Test*: ✅ *SUDAH SELESAI DIKERJAKAN*{g_txt}")
    elif posttest:
        if pre_is_done:
            lines.append("  4. 🎯 *Post-Test*: 🟡 *Aktif (Belum Dikerjakan)* - Siap untuk dikerjakan")
        else:
            lines.append("  4. 🎯 *Post-Test*: 🔒 *Tersedia (Terkunci)* - Menunggu penyelesaian Pre-Test")
    else:
        lines.append("  4. 🎯 *Post-Test*: ⚪ Tidak ada modul post-test")

    # 5. Kuesioner
    if kuesioner:
        if post_is_done:
            lines.append("  5. 📋 *Kuesioner*: 🟡 *Aktif / Siap Diisi*")
        else:
            lines.append("  5. 📋 *Kuesioner*: 🔒 *Tersedia (Terkunci)* - Menunggu penyelesaian Post-Test")
    else:
        lines.append("  5. 📋 *Kuesioner*: ⚪ Tidak ada kuesioner evaluasi")

    if pre_is_done and (post_is_done or not posttest):
        lines.append(f"\n🎉 *Kesimpulan*: Seluruh kuis evaluasi pada Pertemuan {meeting_num} telah LENGKAP kamu selesaikan!")

    return "\n".join(lines)


def tool_get_fordis_draft(course_name: str, meeting_num: int = None) -> str:
    """
    MENGHASILKAN ATAU MELIHAT REKOMENDASI DRAF JAWABAN ILMIAH BARU DARI AI jika pengguna MEMINTA DIBUATKAN JAWABAN / CONTEKAN / IDE JAWABAN untuk fordis yang belum dijawab.
    
    Gunakan tool ini HANYA KETIKA PENGGUNA MEMINTA:
    - 'buatkan draf jawaban fordis X'
    - 'rekomendasi jawaban fordis pertemuan Y'
    - 'bantu jawab fordis Z'
    - 'ide jawaban fordis'
    
    DILARANG memanggil tool ini jika pengguna ingin melihat jawaban asli yang sudah disubmit (gunakan tool_get_my_fordis_answers) atau hanya ingin tahu apa soal dosen (gunakan tool_get_fordis_question)!
    """
    from services.ai_solver import draft_forum_discussion

    # 0. JALUR UTAMA: baca soal ASLI & postingan teman langsung dari web Mentari
    if meeting_num:
        live = get_live_forum(course_name, meeting_num)
        if live and live.get("status") == "belum_tersedia":
            return f"Forum diskusi {live.get('course')} Pertemuan {meeting_num} di web Mentari masih 'belum tersedia' (dosen belum membuka soal)."
        if live and live.get("status") == "aktif":
            c_name = live["course"]
            dosen_name = ""
            if COURSES_METADATA_PATH.exists():
                try:
                    dosen_name = json.load(open(COURSES_METADATA_PATH, encoding="utf-8")).get(c_name, {}).get("dosen", "")
                except Exception:
                    pass
            soal = extract_question_section(live.get("lecturer_post", ""))
            # Pertanyaan teman: postingan Mahasiswa lain yang memuat "izin bertanya" / tanda tanya
            class_questions = []
            for p in live.get("posts", []):
                if p.get("is_me") or p.get("role") != "Mahasiswa":
                    continue
                t = p.get("text", "")
                if "bertanya" in t.lower() or "?" in t:
                    class_questions.append(f"{p['author'].title()}: {t.strip()[:700]}")
            draft = draft_forum_discussion(
                topic=live.get("title", "") + "\n" + soal,
                context=f"Mata Kuliah {c_name} Pertemuan {meeting_num}",
                course_name=c_name, dosen_name=dosen_name,
                class_questions=class_questions[-6:],
            )
            src = "live dari web" if live.get("source") == "live" else "cache web terakhir"
            already = "\n⚠️ _Catatan: kamu sudah pernah membalas di forum ini._" if live.get("has_answered") else ""
            return (f"📚 *Mata Kuliah*: {c_name}\n📍 *Pertemuan*: {meeting_num}\n"
                    f"👨‍🏫 *Dosen*: {dosen_name}\n📌 *Judul Soal*: {live.get('title', '')}\n"
                    f"🔄 *Sumber soal*: {src} ({len(class_questions)} pertanyaan teman terbaca){already}\n\n"
                    f"💡 *3 Respon Siap Salin*:\n\n{draft}\n")

    # 1. Cek dari file draf tersimpan
    drafts = []
    if DRAFTS_PATH.exists():
        try:
            with open(DRAFTS_PATH, encoding="utf-8") as f:
                drafts = json.load(f)
        except Exception:
            pass

    q_clean = course_name.strip().lower() if course_name else ""
    matched_drafts = []

    for d in drafts:
        c_n = d.get("course", "").lower()
        m_n = d.get("pertemuan")
        c_match = (not q_clean) or (q_clean in c_n) or any(w in c_n for w in q_clean.split() if len(w) > 3)
        m_match = (meeting_num is None) or (meeting_num == m_n)
        # Jika draf masih format lama (tanpa RESPON 1 / mengandung salam robotik), regenerasi otomatis
        is_new_format = "RESPON 1" in d.get("draft", "") and "Selamat pagi/siang" not in d.get("draft", "")
        if c_match and m_match and is_new_format:
            matched_drafts.append(d)

    if matched_drafts:
        out = []
        for item in matched_drafts:
            dosen_txt = f"\n👨‍🏫 *Dosen*: {item.get('dosen')}" if item.get('dosen') else ""
            res = (
                f"📚 *Mata Kuliah*: {item.get('course')}\n"
                f"📍 *Pertemuan*: Pertemuan {item.get('pertemuan')}{dosen_txt}\n"
                f"📌 *Topik*: {item.get('topic')}\n\n"
                f"💡 *Rekomendasi 3 Respon Alami Forum Diskusi (Gaya Mahasiswa Asli)*:\n\n"
                f"{item.get('draft')}\n"
            )
            out.append(res)
        return "\n---\n".join(out)

    # 2. Jika belum ada draf tersimpan, periksa apakah forum di matkul & pertemuan tersebut ada di master audit
    c = find_course_in_audit(course_name)
    if not c:
        return f"Mata kuliah '{course_name}' tidak ditemukan di database LMS."

    c_name = c.get("course_name", "")
    target_m = None
    if meeting_num:
        for m in c.get("meetings", []):
            if m.get("pertemuan") == meeting_num:
                target_m = m
                break
    else:
        # Cari pertemuan pertama yang forumnya aktif
        for m in c.get("meetings", []):
            f = m.get("forum")
            if f and "belum tersedia" not in f.get("title", "").lower() and f.get("buttons"):
                target_m = m
                break

    if not target_m:
        return (f"Belum ada draf jawaban tersimpan untuk {c_name}."
                f" Silakan cek status fordis terlebih dahulu dengan tool_check_course_forums.")

    f_info = target_m.get("forum", {})
    if not f_info or "belum tersedia" in f_info.get("title", "").lower() or not f_info.get("buttons"):
        return f"Pada mata kuliah {c_name} Pertemuan {target_m.get('pertemuan')}, forum diskusi belum memiliki soal dari dosen pengampu (status: soal belum tersedia)."

    # Ambil data dosen dari metadata untuk penentuan Pak/Bu
    dosen_name = ""
    if COURSES_METADATA_PATH.exists():
        try:
            with open(COURSES_METADATA_PATH, encoding="utf-8") as f:
                c_meta = json.load(f)
            for mk, mv in c_meta.items():
                if mk.lower() in c_name.lower() or c_name.lower() in mk.lower():
                    dosen_name = mv.get("dosen", "")
                    break
        except Exception:
            pass

    # Buat draf otomatis jika forum aktif
    topic_text = f_info.get("description", f_info.get("title", f"Diskusi Pertemuan {target_m.get('pertemuan')}"))
    draft = draft_forum_discussion(
        topic=topic_text,
        context=f"Mata Kuliah {c_name} Pertemuan {target_m.get('pertemuan')}",
        course_name=c_name,
        dosen_name=dosen_name
    )

    new_entry = {
        "course": c_name,
        "pertemuan": target_m.get("pertemuan"),
        "dosen": dosen_name,
        "topic": topic_text,
        "draft": draft,
        "url": c.get("url", "")
    }

    # Perbarui atau tambahkan ke list draf
    drafts = [d for d in drafts if not (d.get("course") == c_name and d.get("pertemuan") == target_m.get("pertemuan"))]
    drafts.append(new_entry)
    try:
        with open(DRAFTS_PATH, "w", encoding="utf-8") as f:
            json.dump(drafts, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    dosen_display = f"\n👨‍🏫 *Dosen*: {dosen_name}" if dosen_name else ""
    return (
        f"📚 *Mata Kuliah*: {c_name}\n"
        f"📍 *Pertemuan*: Pertemuan {target_m.get('pertemuan')}{dosen_display}\n"
        f"📌 *Topik Terdeteksi*: {topic_text}\n\n"
        f"💡 *Rekomendasi 3 Respon Alami Forum Diskusi (Gaya Mahasiswa Asli)*:\n\n"
        f"{draft}\n"
    )


def tool_check_pending_tasks(course_name: str = "") -> str:
    """
    MEMERIKSA ringkasan tugas dan pertemuan yang BENAR-BENAR BELUM SELESAI / PENDING (memerlukan tindakan mahasiswa)
    pada seluruh mata kuliah atau mata kuliah tertentu.
    
    Gunakan tool ini KETIKA PENGGUNA BERTANYA:
    - 'cek tugas pending'
    - 'tugas apa yang belum dikerjakan'
    - 'ada tugas apa aja yang harus diselesaikan'
    - 'pertemuan berapa yang belum selesai'
    
    ATURAN KRUSIAL: Pertemuan yang sudah dikerjakan (Pre-Test, Post-Test, Kuesioner sudah lengkap)
    DILARANG dilaporkan sebagai pending!
    """
    if not AUDIT_PATH.exists():
        return "Data audit Mentari LMS belum ditemukan di sistem."

    try:
        with open(AUDIT_PATH, encoding="utf-8") as f:
            audit = json.load(f)
    except Exception as e:
        return f"Gagal membaca data audit: {e}"

    forum_details = []
    if FORUM_DETAILS_PATH.exists():
        try:
            with open(FORUM_DETAILS_PATH, encoding="utf-8") as f:
                forum_details = json.load(f)
        except Exception:
            pass

    meeting_grades = {}
    if MEETING_GRADES_PATH.exists():
        try:
            with open(MEETING_GRADES_PATH, encoding="utf-8") as f:
                meeting_grades = json.load(f)
        except Exception:
            pass

    gradebook_data = {}
    if GRADEBOOK_PATH.exists():
        try:
            with open(GRADEBOOK_PATH, encoding="utf-8") as f:
                gradebook_data = json.load(f)
        except Exception:
            pass

    target_canon = resolve_course_key(course_name)[1] if course_name else ""
    summary_lines = []

    for c in audit:
        c_name = c.get("course_name", "")
        if target_canon and target_canon.lower() not in c_name.lower():
            continue

        pending_items = []
        next_meeting_marked = False

        for m in c.get("meetings", []):
            p = m.get("pertemuan")
            res = build_meeting_recap_data(c_name, m, meeting_grades, forum_details, gradebook_data)

            if res["state"] == "DALAM PROSES ⏳":
                comps = []
                if res["pre_txt"] == "Belum Dikerjakan ⏳":
                    comps.append("Pre-Test ⏳")
                if res["fordis_txt"].startswith(("Belum Dijawab", "Belum Lengkap")):
                    comps.append("Fordis 💬")
                if res["post_txt"] == "Belum Dikerjakan ⏳":
                    comps.append("Post-Test 🎯")
                if res["kue_txt"] == "Belum Dikerjakan ⏳":
                    comps.append("Kuesioner 📋")

                if comps:
                    pending_items.append(f"• *Pertemuan {p}*: {', '.join(comps)}")

            elif res["state"] == "BELUM DIMULAI ⭕" and not next_meeting_marked:
                # Cek apakah ada fordis aktif yang belum dijawab
                if res["fordis_txt"].startswith(("Belum Dijawab", "Belum Lengkap")):
                    pending_items.append(f"• *Pertemuan {p}*: Fordis 💬 (Ada Soal Dosen)")
                elif m.get("pretest"):
                    pending_items.append(f"• *Pertemuan {p}* [Pertemuan Terbuka Selanjutnya]: Pre-Test ⏳")
                    next_meeting_marked = True

        if pending_items:
            summary_lines.append(f"📚 *{c_name}*:\n" + "\n".join(pending_items))

    if not summary_lines:
        return "🎉 *Luar biasa!* Tidak ada tugas atau kuis aktif yang berstatus pending pada mata kuliah ini. Seluruh pertemuan yang terbuka telah kamu selesaikan!"

    header = "📋 *DAFTAR TUGAS / PERTEMUAN YANG MEMERLUKAN TINDAKAN (PENDING):*\n\n"
    return header + "\n\n".join(summary_lines)


def build_meeting_recap_data(c_name: str, m: dict, meeting_grades: dict, forum_details: list, gradebook_data: dict = None) -> dict:
    """
    Menganalisis status 5 komponen pembelajaran untuk sebuah pertemuan di LMS Mentari:
    [1] Pre-Test, [2] Materi, [3] Forum Diskusi, [4] Post-Test, [5] Kuesioner.
    Menghasilkan status pertemuan:
    - 'SELESAI TUNTAS ✅' jika seluruh komponen yang wajib/tersedia telah selesai.
    - 'DALAM PROSES ⏳' jika sudah ada aktivitas (misal Pre-Test sudah dikerjakan dengan nilai tertentu) namun komponen lain masih pending.
    - 'BELUM DIMULAI ⭕' jika sama sekali belum ada pengerjaan.
    """
    if gradebook_data is None and GRADEBOOK_PATH.exists():
        try:
            with open(GRADEBOOK_PATH, "r", encoding="utf-8") as f:
                gradebook_data = json.load(f)
        except Exception:
            gradebook_data = {}

    p = m.get("pertemuan")
    pre_audit = m.get("pretest")
    post_audit = m.get("posttest")
    fordis_audit = m.get("forum")
    materi_audit = m.get("materi", [])
    kue_audit = m.get("kuesioner")

    c_mg = meeting_grades.get(c_name, {}).get("meetings", {}).get(f"Pertemuan {p}", {}) or {}
    pre_obj = c_mg.get("pretest") or {}
    post_obj = c_mg.get("posttest") or {}
    pre_g = pre_obj.get("grade")
    post_g = post_obj.get("grade")
    pre_done = pre_g is not None or (pre_obj.get("status") == "Selesai")
    post_done = post_g is not None or (post_obj.get("status") == "Selesai")

    # Aggregate counts do not identify which individual meetings were completed.
    kue_done = (c_mg.get("kuesioner") or {}).get("status") == "Selesai"
    fordis_answered = False
    fordis_complete = False
    reply_count = 0
    required_replies = 3
    for fd in forum_details:
        if fd.get("course") == c_name and fd.get("pertemuan") == p:
            reply_count = fd.get("total_replies", len(fd.get("my_submissions", [])))
            required_replies = fd.get("required_replies", 3)
            fordis_answered = reply_count > 0
            fordis_complete = reply_count >= required_replies
            break

    # 1. Evaluasi Status Kelengkapan Pertemuan
    is_complete = False
    # Kasus A: Pertemuan tanpa modul tes (Pre-Test & Post-Test ditiadakan dosen, menyisakan Kuesioner/Materi seperti Keamanan Komputer P2-P4)
    # Di Mentari LMS, selagi kuesioner sudah dikerjakan, status pertemuan tersebut telah selesai tuntas.
    if not pre_audit and not post_audit:
        if kue_audit and kue_done:
            is_complete = True
        elif materi_audit and not kue_audit:
            is_complete = True
    elif post_audit:
        if post_done and (pre_done or not pre_audit):
            is_complete = True
    elif pre_audit:
        if pre_done:
            is_complete = True

    # PENTING: Jika dosen membuka soal fordis aktif pada pertemuan ini dan mahasiswa belum menjawabnya,
    # pertemuan TIDAK BOLEH dianggap 'SELESAI TUNTAS'! Pertemuan berstatus 'DALAM PROSES ⏳'
    # agar mahasiswa tahu bahwa masih ada kewajiban menjawab fordis!
    has_active_unanswered_fordis = (
        bool(fordis_audit)
        and "belum tersedia" not in fordis_audit.get("title", "").lower()
        and not fordis_complete
    )
    if has_active_unanswered_fordis or (kue_audit and not kue_done):
        is_complete = False

    has_activity = is_complete or pre_done or post_done or fordis_answered or (kue_done and bool(kue_audit))

    if is_complete:
        state = "SELESAI TUNTAS ✅"
    elif has_activity:
        state = "DALAM PROSES ⏳"
    else:
        state = "BELUM DIMULAI ⭕"

    # 2. Format 5 Komponen Pembelajaran
    # 2.1 Pretest
    if not pre_audit:
        pre_txt = "(Ditiadakan Dosen) ℹ️" if is_complete else "(Tidak Ada) ℹ️"
    elif pre_done:
        pre_txt = f"*{pre_g}* ✅" if pre_g is not None else "Selesai ✅"
    else:
        pre_txt = "Belum Dikerjakan ⏳"

    # 2.2 Materi
    if materi_audit:
        materi_txt = f"{len(materi_audit)} Modul 📖"
    else:
        materi_txt = "(Tidak Ada) ℹ️"

    # 2.3 Fordis
    if not fordis_audit:
        fordis_txt = "(Ditiadakan Dosen) ℹ️" if is_complete else "(Tidak Ada) ℹ️"
    elif fordis_complete:
        fordis_txt = "Sudah Dijawab ✅"
    elif "belum tersedia" in fordis_audit.get("title", "").lower():
        fordis_txt = "Belum Ada Soal Dosen ℹ️"
    else:
        # Fordis ada soal resmi dari dosen dan belum dijawab mahasiswa
        fordis_txt = f"Belum Lengkap ({reply_count}/{required_replies}) 💬" if reply_count else "Belum Dijawab 💬"

    # 2.4 Posttest
    if not post_audit:
        post_txt = "(Ditiadakan Dosen) ℹ️" if is_complete else "(Tidak Ada) ℹ️"
    elif post_done:
        post_txt = f"*{post_g}* 🎯" if post_g is not None else "Selesai ✅"
    elif not pre_done:
        post_txt = "Terkunci (Syarat Pre-Test) 🔒"
    else:
        post_txt = "Belum Dikerjakan ⏳"

    # 2.5 Kuesioner
    if not kue_audit:
        kue_txt = "(Tidak Ada) ℹ️"
    elif kue_done:
        kue_txt = "Selesai ✅"
    else:
        kue_txt = "Belum Terverifikasi ⏳"

    return {
        "pertemuan": p,
        "state": state,
        "pre_txt": pre_txt,
        "materi_txt": materi_txt,
        "fordis_txt": fordis_txt,
        "post_txt": post_txt,
        "kue_txt": kue_txt,
        "has_activity": has_activity,
        "is_complete": is_complete,
        "pre_grade": pre_g,
        "post_grade": post_g,
        "pre_done": pre_done,
        "post_done": post_done,
        "fordis_answered": fordis_answered
    }


def tool_check_completed_tasks(course_name: str = "") -> str:
    """
    MEMERIKSA dan MENAMPILKAN seluruh pertemuan dan modul pembelajaran yang SUDAH SELESAI maupun SEDANG DALAM PROSES
    (Pre-Test selesai dengan nilai, Materi, Fordis, Post-Test, Kuesioner) pada seluruh 8 mata kuliah atau mata kuliah tertentu.
    
    Gunakan tool ini KETIKA PENGGUNA BERTANYA:
    - 'cek mata kuliah etika profesi yang udah pretest pertemuan berapa aja'
    - 'pertemuan berapa aja yang sudah dikerjakan'
    - 'yang udah selesai apa aja'
    - 'sudah pretest pertemuan berapa'
    - 'status kuis yang sudah beres'
    - 'apakah p6 dan p7 sudah dikerjakan'
    """
    if not AUDIT_PATH.exists():
        return "Data audit Mentari LMS belum ditemukan di sistem."

    try:
        with open(AUDIT_PATH, encoding="utf-8") as f:
            audit = json.load(f)
    except Exception as e:
        return f"Gagal membaca data audit: {e}"

    forum_details = []
    if FORUM_DETAILS_PATH.exists():
        try:
            with open(FORUM_DETAILS_PATH, encoding="utf-8") as f:
                forum_details = json.load(f)
        except Exception:
            pass

    meeting_grades = {}
    if MEETING_GRADES_PATH.exists():
        try:
            with open(MEETING_GRADES_PATH, encoding="utf-8") as f:
                meeting_grades = json.load(f)
        except Exception:
            pass

    q = course_name.strip().lower() if course_name else ""
    target_canon = resolve_course_key(q)[1] if q else ""
    summary_lines = []

    for c in audit:
        c_name = c.get("course_name", "")
        if target_canon and target_canon.lower() not in c_name.lower():
            continue

        active_items = []
        for m in c.get("meetings", []):
            item = build_meeting_recap_data(c_name, m, meeting_grades, forum_details)
            if item["has_activity"]:
                p = item["pertemuan"]
                active_items.append(
                    f"   • *Pertemuan {p}* [{item['state']}]: Pre-Test: {item['pre_txt']} | Materi: {item['materi_txt']} | Fordis: {item['fordis_txt']} | Post-Test: {item['post_txt']} | Kuesioner: {item['kue_txt']}"
                )

        if active_items:
            summary_lines.append(f"📚 *{c_name}* ({len(active_items)} Pertemuan Berjalan):\n" + "\n".join(active_items))
        elif target_canon:
            summary_lines.append(f"📚 *{c_name}*:\n   • _Belum ada modul atau pertemuan yang mulai dikerjakan._")

    if not summary_lines:
        return f"Belum ada data pengerjaan yang tercatat untuk mata kuliah '{course_name}'."

    header = "🎓 *DAFTAR PERTEMUAN & MODUL PEMBELAJARAN (SELESAI & DALAM PROSES)*\n"
    header += "👤 *Mahasiswa*: SOFYAN AGUNG (231011400159 / Kelas 07TPLP003)\n\n"
    return header + "\n\n".join(summary_lines)


def tool_get_grade_summary(course_name: str = "", meeting_num: int = None) -> str:
    """
    MEMERIKSA dan MENAMPILKAN REKAPITULASI TOTAL NILAI & 5 KOMPONEN PEMBELAJARAN PER PERTEMUAN
    (Pre-Test ➡️ Materi ➡️ Fordis ➡️ Post-Test ➡️ Kuesioner) secara rinci, transparan, dan lengkap
    untuk setiap pertemuan dari seluruh 8 mata kuliah atau mata kuliah tertentu di Mentari LMS UNPAM.

    ATURAN SANGAT PENTING:
    - Menampilkan seluruh 5 komponen (Pre-Test, Materi, Fordis, Post-Test, Kuesioner) untuk setiap pertemuan aktif.
    - Pertemuan yang baru dikerjakan sebagian (seperti P6 dan P7 yang baru Pre-Test) WAJIB tetap ditampilkan dengan status [DALAM PROSES ⏳] dan nilai Pre-Test riilnya! DILARANG DIHILANGKAN!
    - Menampilkan nilai riil masing-masing pertemuan (bukan sekadar rata-rata total).

    Gunakan tool ini KETIKA PENGGUNA BERTANYA:
    - 'cek rekap nilai aku di semua pertemuannya'
    - 'rekap etika profesi p6 dan p7'
    - 'kirim ulang rekap p6 dan p7'
    - 'rekap matkul etika profesi'
    - 'rekap nilai semua matkul'
    - 'rekap dari pretest sampai kuisioner'
    - 'nilai aku berapa aja'
    - 'lihat grade book'
    - 'skor kuis mata kuliah X'
    """
    if not AUDIT_PATH.exists():
        return "Data audit Mentari LMS belum ditemukan di sistem."

    try:
        with open(AUDIT_PATH, encoding="utf-8") as f:
            audit = json.load(f)
    except Exception as e:
        return f"Gagal membaca data audit: {e}"

    forum_details = []
    if FORUM_DETAILS_PATH.exists():
        try:
            with open(FORUM_DETAILS_PATH, encoding="utf-8") as f:
                forum_details = json.load(f)
        except Exception:
            pass

    meeting_grades = {}
    if MEETING_GRADES_PATH.exists():
        try:
            with open(MEETING_GRADES_PATH, encoding="utf-8") as f:
                meeting_grades = json.load(f)
        except Exception:
            pass

    q = course_name.strip().lower() if course_name else ""
    is_all = not q or any(w in q for w in ["all", "semua", "seluruh", "total", "rekap", "pertemuannya"])

    student_name = "SOFYAN AGUNG"
    student_nim = "231011400159"

    target_course_data = None
    if not is_all and q:
        _, canon_name = resolve_course_key(q)
        for c in audit:
            c_name = c.get("course_name", "")
            if canon_name.lower() in c_name.lower():
                target_course_data = c
                break

    # 1. KASUS: 1 MATA KULIAH SPESIFIK DENGAN NOMOR PERTEMUAN SPESIFIK
    if target_course_data and meeting_num:
        c_name = target_course_data.get("course_name", "")
        meetings = target_course_data.get("meetings", [])
        m_item = next((m for m in meetings if m.get("pertemuan") == meeting_num), None)

        if not m_item:
            return f"Data Pertemuan {meeting_num} untuk mata kuliah *{c_name}* belum tercatat di sistem."

        res = build_meeting_recap_data(c_name, m_item, meeting_grades, forum_details)

        lines = [
            f"📊 *REKAP KOMPONEN PEMBELAJARAN PERTEMUAN {meeting_num}*",
            f"👤 *Mahasiswa*: {student_name} ({student_nim})",
            f"📚 *Mata Kuliah*: {c_name}",
            f"📌 *Status Pertemuan*: [{res['state']}]\n",
            "📋 *Rincian 5 Komponen Pembelajaran*:",
            f"1. 📝 *Pre-Test*: {res['pre_txt']}",
            f"2. 📖 *Materi*: {res['materi_txt']}",
            f"3. 💬 *Forum Diskusi (Fordis)*: {res['fordis_txt']}",
            f"4. 🎯 *Post-Test*: {res['post_txt']}",
            f"5. 📋 *Kuesioner*: {res['kue_txt']}"
        ]
        return "\n".join(lines)

    # 2. KASUS: 1 MATA KULIAH SPESIFIK (SELURUH PERTEMUAN)
    if target_course_data:
        c_name = target_course_data.get("course_name", "")
        meetings = target_course_data.get("meetings", [])

        active_meetings = []
        inactive_meetings = []

        for m in meetings:
            res = build_meeting_recap_data(c_name, m, meeting_grades, forum_details)
            p = res["pertemuan"]
            if res["has_activity"]:
                active_meetings.append(
                    f"• *Pertemuan {p}* [{res['state']}]: Pre: {res['pre_txt']} | Materi: {res['materi_txt']} | Fordis: {res['fordis_txt']} | Post: {res['post_txt']} | Kuesioner: {res['kue_txt']}"
                )
            else:
                inactive_meetings.append(f"P-{p}")

        lines = [
            f"📊 *REKAPITULASI TOTAL KOMPONEN & NILAI PEMBELAJARAN*",
            f"👤 *Mahasiswa*: {student_name} ({student_nim})",
            f"📚 *Mata Kuliah*: {c_name}",
            f"🏆 *Total Pertemuan Berjalan*: {len(active_meetings)} Pertemuan\n",
            "📋 *Status Tiap Pertemuan (Pre-Test ➡️ Materi ➡️ Fordis ➡️ Post-Test ➡️ Kuesioner)*:"
        ]

        if active_meetings:
            lines.extend(active_meetings)
        else:
            lines.append("• _Belum ada aktivitas pembelajaran yang dimulai pada mata kuliah ini._")

        if inactive_meetings:
            lines.append(f"\nℹ️ *Pertemuan Belum Dimulai ({len(inactive_meetings)} pertemuan)*: {', '.join(inactive_meetings)} [BELUM DIMULAI ⭕]")

        lines.append("\n💡 *Catatan*: Nilai dan status di atas tersinkronisasi langsung dengan sistem Mentari LMS UNPAM.")
        return "\n".join(lines)

    # 3. KASUS: REKAPITULASI SELURUH 8 MATA KULIAH (TOTAL 5 KOMPONEN)
    summary_blocks = [
        f"📊 *REKAPITULASI TOTAL PEMBELAJARAN SELURUH 8 MATA KULIAH*",
        f"👤 *Mahasiswa*: {student_name} ({student_nim})",
        f"🏫 *Kelas*: 07TPLP003 | Teknik Informatika UNPAM",
        f"📌 *Alur Lengkap*: Pre-Test ➡️ Materi ➡️ Fordis ➡️ Post-Test ➡️ Kuesioner\n"
    ]

    active_courses_blocks = []
    empty_courses = []

    for idx, c in enumerate(audit, 1):
        c_name = c.get("course_name", "")
        meetings = c.get("meetings", [])

        meeting_lines = []
        for m in meetings:
            res = build_meeting_recap_data(c_name, m, meeting_grades, forum_details)
            if res["has_activity"]:
                p = res["pertemuan"]
                meeting_lines.append(
                    f"   • *Pertemuan {p}* [{res['state']}]: Pre: {res['pre_txt']} | Materi: {res['materi_txt']} | Fordis: {res['fordis_txt']} | Post: {res['post_txt']} | Kuesioner: {res['kue_txt']}"
                )

        if meeting_lines:
            c_block = [f"📚 *{len(active_courses_blocks)+1}. {c_name}* ({len(meeting_lines)} Pertemuan Berjalan):"]
            c_block.extend(meeting_lines)
            active_courses_blocks.append("\n".join(c_block))
        else:
            empty_courses.append(c_name)

    if active_courses_blocks:
        summary_blocks.append("\n\n".join(active_courses_blocks))

    if empty_courses:
        empty_lines = [f"\n🔒 *Mata Kuliah Belum Dimulai (0 Pertemuan Berjalan):*"]
        for ec in empty_courses:
            empty_lines.append(f"   • {ec}")
        summary_blocks.append("\n".join(empty_lines))

    summary_blocks.append("\n💡 *Catatan*: Rekap ini mencakup seluruh 5 komponen pembelajaran dan diperbarui secara otomatis setiap kali kuis selesai.")
    return "\n".join(summary_blocks)


def tool_execute_learning_pipeline(course_name: str, meeting_target: str = "1", target_step: str = "all") -> str:
    """
    PERINGATAN KRUSIAL: Tool ini HANYA boleh dipanggil jika pengguna memberikan PERINTAH TEGAS dan EKSPLISIT
    untuk MENJALANKAN/MENGEKSEKUSI bot pengerjaan di laptop (contoh: 'kerjakan pertemuan 2', 'jalankan pretest pertemuan 1 dan 2', 'kerjakan pretest p1 dan p2 testing dan qa', 'kerjakan semua pertemuan yang ada di matkul X', 'kerjakan semua matkul yang belum beres').

    Argumen:
    - course_name: Nama mata kuliah (misal: 'Testing dan QA', 'Etika Profesi', 'Manajemen Proyek', atau 'all'/'semua' untuk seluruh 8 mata kuliah).
    - meeting_target: Target pertemuan fleksibel. Dapat berupa:
                      • Nomor pertemuan tunggal: '1', '2', dst.
                      • Beberapa pertemuan sekaligus: '1,2', 'p1 dan p2', '1, 2, 3'.
                      • Rentang pertemuan: '1-3', 'p1-p4'.
                      • Pengerjaan otomatis seluruh pertemuan: 'all' atau 'auto'.
    - target_step: Tahap/modul pembelajaran spesifik yang ingin dikerjakan ('all', 'pretest', 'posttest', 'fordis', 'materi', 'kuesioner').
                   Default 'all' jika pengguna ingin seluruh alur pertemuan diproses.
                   Jika pengguna minta spesifik seperti 'kerjakan post test', WAJIB isi 'posttest'!
                   Jika pengguna minta 'kerjakan pretest', WAJIB isi 'pretest'!
    """
    c_clean = (course_name or "1").strip().lower()
    if c_clean in ["all", "semua", "seluruh"]:
        target_c_key = "all"
        actual_course_name = "Seluruh 8 Mata Kuliah Mentari LMS"
    else:
        try:
            target_c_key, actual_course_name = resolve_course_key(course_name, strict=True)
        except ValueError as exc:
            return str(exc)

    step_clean = (target_step or "all").lower().strip()
    m_clean = str(meeting_target).strip()

    try:
        from pipeline_runner import normalize_step, parse_meeting_targets
        step_clean = normalize_step(step_clean)
        if m_clean.lower() not in {"auto", "all", "semua", "seluruh"}:
            m_clean = ','.join(map(str, parse_meeting_targets(m_clean)))
        from services.task_queue import enqueue_task
        q_res = enqueue_task(
            course_key=target_c_key,
            course_name=actual_course_name,
            meeting_target=m_clean,
            target_step=step_clean
        )
        pos = q_res.get("position", 1)
        total = q_res.get("total_in_queue", 1)
        if q_res.get('status') == 'running':
            return f"Tugas {actual_course_name} pertemuan {m_clean} ({step_clean}) sedang berjalan; perintah tidak diduplikasi."
        target_label = f"modul *{step_clean.upper()}*" if step_clean != "all" else "seluruh alur pembelajaran (Pre-Test ➡️ Materi ➡️ Fordis ➡️ Post-Test ➡️ Kuesioner)"
        meeting_label = f"Pertemuan {m_clean}" if m_clean not in ["all", "auto", "semua"] else "seluruh pertemuan yang tersedia"

        if pos == 1 and q_res.get("status") == "started":
            return (f"🚀 *Perintah Diterima & Langsung Dieksekusi!*\n"
                    f"Bot di laptop telah mulai memproses {target_label} untuk:\n"
                    f"📚 *{actual_course_name}*\n"
                    f"📍 *Target*: *{meeting_label}*\n\n"
                    f"Browser Chrome telah diluncurkan secara tertib (1 jendela aktif). "
                    f"Setiap kali satu pertemuan selesai, nilai langsung dicatat ke database dan ringkasannya otomatis dikirimkan ke WhatsApp! ☕✨")
        else:
            return (f"📋 *Perintah Diterima & Masuk Antrean Sekuensial (Urutan ke-{pos} dari {total})!*\n"
                    f"📚 *{actual_course_name}*\n"
                    f"📍 *Target*: *{meeting_label}* ({target_label})\n\n"
                    f"🔒 *Keamanan Sesi*: Karena ada tugas lain yang sedang berjalan di browser, tugas ini akan dieksekusi secara otomatis dan berurutan setelah tugas sebelumnya selesai dalam 1 browser (mencegah bentrok login & blokir Cloudflare). ☕✨")
    except Exception as e:
        return f"Gagal mendaftarkan tugas ke antrean pengerjaan: {e}"


def tool_scrape_mentari() -> str:
    """
    PERINGATAN: HANYA dipanggil jika pengguna secara eksplisit meminta 'scrape', 'pindai ulang', atau 'sinkronkan LMS'.
    DILARANG dipanggil jika pengguna hanya mengecek atau bertanya biasa.
    """
    cmd = [sys.executable, str(BASE_DIR / "master_scraper.py")]
    try:
        subprocess.Popen(cmd, cwd=str(BASE_DIR))
        return "🔄 *Master Scraping Dimulai!*\nBot sedang memindai ulang seluruh 8 mata kuliah di Mentari LMS UNPAM di laptop. Data terbaru akan segera diperbarui."
    except Exception as e:
        return f"Gagal menjalankan master scraper: {e}"


def tool_sync_grades(course_name: str = "") -> str:
    """
    MENYINKRONKAN / MENGAMBIL NILAI KUIS TERBARU SECARA LANGSUNG DARI MENTARI LMS (LIVE SYNC).
    
    Gunakan tool ini KETIKA:
    - Mahasiswa baru saja mengerjakan pertemuan/kuis baru di Mentari LMS (lewat HP/laptop sendiri) dan ingin bot membaca nilai terbarunya
    - Mahasiswa meminta: 'sinkronkan nilai', 'update nilai', 'refresh nilai', 'cek nilai terbaru'
    - Mahasiswa bertanya apakah bot bisa membaca kuis pertemuan baru yang baru saja dia selesaikan.
    """
    try:
        from scrape_meeting_grades import scrape_all_meeting_grades
        scrape_all_meeting_grades(target_course_name=course_name if course_name else None)
        return (
            "🔄 *Sinkronisasi Nilai Berhasil!*\n"
            "Bot baru saja menarik data nilai terbaru langsung dari server Mentari LMS UNPAM:\n\n"
            + tool_get_grade_summary(course_name=course_name)
        )
    except Exception as e:
        return f"Gagal menyinkronkan data nilai dari Mentari LMS: {e}"


def tool_get_course_schedule(course_name: str = "", day_name: str = "") -> str:
    """
    MEMERIKSA JADWAL KULIAH RESMI, NAMA DOSEN PENGAMPU LENGKAP BESERTA GELAR, JUMLAH SKS,
    DAN HARI PERKULIAHAN MAHASISWA (SOFYAN AGUNG - KELAS 07TPLP003) DARI DATA RESMI MENTARI LMS UNPAM.

    Gunakan tool ini KETIKA PENGGUNA BERTANYA:
    - 'hari ini ada kuliah apa aja' / 'jadwal hari ini'
    - 'besok ada kuliah apa' / 'jadwal hari senin/selasa/rabu/jumat'
    - 'siapa dosen mata kuliah X' (misal: 'dosen etika profesi siapa', 'siapa pengajar manajemen proyek')
    - 'jadwal kuliah seminggu' / 'jadwal perkuliahan'
    - 'berapa sks matkul X' / 'total sks semester ini'
    - 'matkul etika profesi hari apa'
    """
    if not COURSES_METADATA_PATH.exists():
        return "Data jadwal dan metadata mata kuliah belum ditemukan di sistem."

    try:
        with open(COURSES_METADATA_PATH, encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as e:
        return f"Gagal membaca data jadwal kuliah: {e}"

    days_indo = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
    import datetime
    today_idx = datetime.datetime.now().weekday()
    today_name = days_indo[today_idx]

    c_query = course_name.strip().lower() if course_name else ""
    d_query = day_name.strip().lower() if day_name else ""

    target_day = None
    if "hari ini" in d_query or "hari ini" in c_query:
        target_day = today_name
    elif "besok" in d_query or "besok" in c_query:
        tomorrow_idx = (today_idx + 1) % 7
        target_day = days_indo[tomorrow_idx]
    else:
        for d in days_indo:
            if d.lower() in d_query or d.lower() in c_query:
                target_day = d
                break

    # 1. KASUS: Tanya Dosen / Detail Mata Kuliah Tertentu
    target_c = None
    if c_query and "hari ini" not in c_query and "besok" not in c_query and "jadwal" not in c_query and "seminggu" not in c_query:
        _, canon_name = resolve_course_key(c_query)
        for cname, cinfo in metadata.items():
            if canon_name.lower() in cname.lower() or cname.lower() in canon_name.lower():
                target_c = cinfo
                break

    if target_c:
        return (
            f"📚 *DETAIL MATA KULIAH: {target_c['course_name']}*\n"
            f"👨‍🏫 *Dosen Pengampu*: {target_c['dosen']}\n"
            f"📅 *Jadwal Kuliah*: Hari *{target_c['hari']}*\n"
            f"🎓 *Bobot*: *{target_c['sks']} SKS*\n"
            f"🏫 *Kelas / Kode*: {target_c['kelas']} | Kode MK: {target_c['course_id']}\n"
            f"🆔 *Kode LMS*: {target_c['course_code']}"
        )

    # 2. KASUS: Tanya Jadwal Hari Tertentu
    if target_day:
        matched = [c for c in metadata.values() if c.get("hari", "").lower() == target_day.lower()]
        if not matched:
            return (
                f"🌴 Hari *{target_day}* tidak ada jadwal perkuliahan di LMS Mentari "
                f"untuk kelas 07TPLP003 (Hari libur / tidak ada perkuliahan terjadwal)."
            )

        lines = [
            f"📅 *JADWAL KULIAH HARI {target_day.upper()}*",
            f"🏫 *Kelas*: 07TPLP003 | Teknik Informatika UNPAM\n"
        ]
        for c in matched:
            lines.append(f"• 📚 *{c['course_name']}* ({c['sks']} SKS)\n   👨‍🏫 Dosen: *{c['dosen']}*")
        total_sks_day = sum(c['sks'] for c in matched)
        lines.append(f"\n⚡ *Total*: {len(matched)} mata kuliah ({total_sks_day} SKS).")
        return "\n".join(lines)

    # 3. KASUS: Tanya Jadwal Kuliah Seluruhnya / Seminggu / Total SKS
    schedule_by_day = {}
    for c in metadata.values():
        h = c.get("hari", "Lainnya")
        if h not in schedule_by_day:
            schedule_by_day[h] = []
        schedule_by_day[h].append(c)

    lines = [
        f"📅 *JADWAL PERKULIAHAN RESMI KELAS 07TPLP003*",
        f"👤 *Mahasiswa*: SOFYAN AGUNG (231011400159)",
        f"🎓 *Semester*: Ganjil 2026/2027 | Total 8 Mata Kuliah (18 SKS)\n"
    ]

    for d in ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]:
        if d in schedule_by_day:
            courses = schedule_by_day[d]
            lines.append(f"📌 *HARI {d.upper()}:*")
            for c in courses:
                lines.append(f"  • 📚 *{c['course_name']}* ({c['sks']} SKS)\n     👨‍🏫 Dosen: *{c['dosen']}*")
            lines.append("")

    return "\n".join(lines)


# =====================================================================
# AGENT RUNNER & REASONING ENGINE (MENTARI AI AGENT)
# =====================================================================

import time

# Daftar model aktif dengan prioritas model berkuota tinggi dan cepat
from services.ai_solver import DEFAULT_MODEL, FALLBACK_MODELS
ACTIVE_MODELS = list(dict.fromkeys([DEFAULT_MODEL, *FALLBACK_MODELS]))

_model_cooldowns = {}
_last_working_model = DEFAULT_MODEL
_session_histories = {}  # session_id -> list of {"role": str, "text": str}

# System Instruction untuk Mode Ngobrol Santai (Tanpa Tools, Alami & Asyik)
CHAT_SYSTEM_INSTRUCTION = """Kamu adalah "Mentari", asisten AI pribadi sekaligus sahabat diskusi yang cerdas, hangat, luwes, dan suportif untuk SOFYAN AGUNG (mahasiswa Teknik Informatika Universitas Pamulang / UNPAM, Semester 7, Kelas 07TPLP003, NIM: 231011400159).

GAYA BICARA & KEPRIBADIAN (ALAMI, CERDAS & SEPERTI TEMAN SEJAWAT):
1. Mengalir Alami & Bersahabat: Berbicaralah seperti teman sejawat kuliah atau asisten pintar yang akrab (gunakan sapaan 'kamu' dan sebut dirimu 'aku' atau 'Mentari'). Hindari gaya robotik, template kaku formulir, atau customer service.
2. Cerdas & Solutif: Jika diajak berdiskusi konsep koding (Python, Web, Database/SQL, Algoritma, Jaringan, QA), perkuliahan, atau strategi belajar, berikan penjelasan yang bernas, mudah dipahami, dan praktis.
3. Konteks Perkuliahan Sofyan:
   - Sofyan adalah mahasiswa Teknik Informatika UNPAM semester 7 (07TPLP003, Reguler P).
   - Memiliki 8 mata kuliah aktif: Manajemen Proyek Informatika, Arsitektur dan Organisasi Komputer, Keamanan Komputer, Jaringan Nirkabel, Kecakapan Antar Personal, Testing & QA Perangkat Lunak, Etika Profesi, dan Pemrograman Web II.
4. Kamu memiliki kemampuan mengotomasi Mentari LMS UNPAM di laptop Sofyan. Jika Sofyan meminta bantuan mengecek data kuliah (nilai kuis, fordis, tugas, jadwal) atau menyuruh mengeksekusi pengerjaan di laptop, kamu siap melayani kapan pun diperintahkan.
5. ATURAN KRUSIAL FORDIS: DILARANG KERAS mengatakan "fordis tidak penting" atau menyepelekan Forum Diskusi! Di Mentari LMS UNPAM, Fordis adalah komponen wajib yang dinilai dan menentukan kehadiran. Jika ada fordis aktif yang belum dikerjakan (seperti Arkom P7), ingatkan Sofyan untuk mengerjakannya."""

# System Instruction untuk Mode Cek Data LMS Mentari (Read-Only)
LMS_INFO_SYSTEM_INSTRUCTION = """Kamu adalah "Mentari", asisten akademik pribadi sekaligus sahabat cerdas untuk SOFYAN AGUNG (Teknik Informatika UNPAM, Semester 7, Kelas 07TPLP003, NIM: 231011400159).

GAYA KOMUNIKASI (NATURAL, JELAS & BERSAHABAT):
- Sapalah Sofyan secara ramah dan luwes (misal: "Halo Sofyan!", "Siap Sofyan!", "Oke Sofyan!").
- Sajikan informasi resmi dari tools dengan gaya bahasa yang mengalir alami, komunikatif, dan tertata rapi (*tebal* untuk poin penting, bullet points, dan emoji yang relevan).
- DILARANG KERAS bersikap kaku seperti mesin formulir customer service. Jawablah layaknya rekan kuliah senior yang pintar, teliti, dan bisa diandalkan.

ATURAN SANGAT KRUSIAL MENGENAI FORUM DISKUSI (FORDIS):
1. DILARANG KERAS MENGATAKAN ATAU MENGANGGAP FORDIS "TIDAK PENTING" ATAU "TIDAK WAJIB"!
   Di LMS Mentari UNPAM, Forum Diskusi (Fordis) adalah komponen resmi penilaian partisipasi dan kehadiran mahasiswa.
2. JANGAN PERNAH MENGKLAIM FORDIS "DITIADAKAN" JIKA DOSEN SEBENARNYA MEMBUKA SOAL TOPIK DI LMS!
   Contohnya pada Arsitektur dan Organisasi Komputer (AOK) Pertemuan 3, 6, dan 7, dosen (Nanang S.Kom., M.Kom.) telah membuka soal resmi. Jika belum dijawab mahasiswa, statusnya WAJIB dilaporkan sebagai [Belum Dijawab 💬], BUKAN ditiadakan!
3. JIKA DOSEN TIBA-TIBA MEMBUKA ATAU MENAMBAHKAN FORDIS BARU DI WEB LMS:
   Bot dapat langsung mendeteksi dan memperbarui status fordis terbaru dari web menggunakan tool `tool_sync_grades` saat Sofyan meminta sinkronisasi nilai/data web.

PANDUAN PEMILIHAN TOOLS (PASTIKAN TEPAT SASARAN):
1. **MELIHAT JAWABAN / POSTINGAN YANG SUDAH DIKIRIM (SUBMIT) DI FORDIS**:
   (contoh: "cek jawaban mentari aku pertemuan 2 fordis manajemen proyek", "lihat jawaban aku apa", "aku udah jawab apa aja di fordis"):
   👉 WAJIB gunakan `tool_get_my_fordis_answers`!
   ❌ DILARANG KERAS membuat draf jawaban baru atau menjawab soal dosen jika pengguna hanya ingin melihat riwayat jawabannya sendiri.

2. **MENANYAKAN SOAL / INSTRUKSI RESMI DOSEN DI FORDIS**:
   (contoh: "apa soal yang diberikan dosen di fordis p2", "dosen nanya apa di fordis", "cek soal fordis", "soal fordis arkom p7"):
   👉 WAJIB gunakan `tool_get_fordis_question`!
   ❌ DILARANG KERAS MENJAWAB SOALNYA! Tampilkan pertanyaan dan instruksi dosen apa adanya.

3. **MEMINTA REKOMENDASI / DRAF JAWABAN ILMIAH BARU UNTUK FORDIS**:
   (contoh: "buatkan draf jawaban fordis", "bantu susun jawaban fordis X", "bikinin ide jawaban"):
   👉 Gunakan `tool_get_fordis_draft`.

4. **STATUS KETERSEDIAAN FORUM DISKUSI**:
   (contoh: "fordis etika profesi pertemuan berapa aja", "cek fordis yang aktif", "fordis arkom ada apa aja"):
   👉 Gunakan `tool_check_course_forums`.

5. **RINGKASAN STATUS 1 PERTEMUAN LENGKAP**:
   (contoh: "cek pertemuan 2 manajemen proyek ada apa aja", "status pertemuan 2"):
   👉 Gunakan `tool_get_meeting_summary`.

6. **DAFTAR TUGAS / PERTEMUAN YANG SUDAH SELESAI DIKERJAKAN**:
   (contoh: "cek mata kuliah etika profesi yang udah pretest pertemuan berapa aja", "pertemuan berapa yang sudah beres", "yang udah dikerjakan apa aja"):
   👉 WAJIB gunakan `tool_check_completed_tasks`!

7. **DAFTAR SELURUH TUGAS PENDING (YANG BELUM SELESAI / MEMBUTUHKAN TINDAKAN)**:
   (contoh: "cek tugas pending", "ada tugas apa aja yang belum", "sisa tugas apa aja"):
   👉 Gunakan `tool_check_pending_tasks`.

8. **REKAP NILAI KUIS / SKOR PER PERTEMUAN / REKAP LENGKAP SEMUA MATA KULIAH (TOTAL 5 KOMPONEN)**:
   (contoh: "cek rekap nilai aku di semua pertemuannya", "rekap etika profesi p6 dan p7", "kirim ulang rekap p6 dan p7", "rekap matkul etika profesi", "rekap semua matkul", "rekap nilai per pertemuan", "skor kuis"):
   👉 WAJIB gunakan `tool_get_grade_summary`!
   Tool ini memberikan rekap 5 komponen pembelajaran lengkap (Pre-Test ➡️ Materi ➡️ Fordis ➡️ Post-Test ➡️ Kuesioner) beserta status pertemuan ([SELESAI TUNTAS ✅] atau [DALAM PROSES ⏳]).
   DILARANG menghilangkan pertemuan yang baru dikerjakan sebagian (misal Pre-Test saja seperti P6/P7), laporkan apa adanya sesuai status [DALAM PROSES ⏳] dan nilai riilnya!

9. **SINKRONISASI / UPDATE NILAI TERBARU (LIVE SYNC DARI SERVER MENTARI)**:
   (contoh: "aku baru aja ngerjain pertemuan baru coba cek", "sinkronkan nilai", "update nilai", "bisa baca pertemuan baru ga"):
   👉 WAJIB gunakan `tool_sync_grades`! Tool ini akan melakukan penarikan data live real-time dari server Mentari LMS UNPAM.

10. **JADWAL KULIAH, DOSEN PENGAMPU, HARI PERKULIAHAN & SKS**:
    (contoh: "hari ini ada kuliah apa", "besok ada kuliah apa", "jadwal hari rabu", "siapa dosen manajemen proyek", "jadwal kuliah seminggu", "berapa sks matkul web 2"):
    👉 WAJIB gunakan `tool_get_course_schedule`!

PENTING: Pengguna HANYA meminta informasi/cek status. JANGAN mengeksekusi browser otomatis atau pipeline pengerjaan!"""

# System Instruction untuk Mode Eksekusi Perintah LMS ("Suruh Mentari")
EXECUTE_SYSTEM_INSTRUCTION = """Kamu adalah "Mentari AI Agent", asisten akademik cerdas untuk SOFYAN AGUNG (Teknik Informatika UNPAM).

PERINGATAN PENTING: Pengguna secara EKSPLISIT memberikan PERINTAH untuk MENJALANKAN / MENGEKSEKUSI tugas Mentari LMS di laptopnya!

DAFTAR 8 MATA KULIAH RESMI & PEMETAAN ALIAS (WAJIB TEPAT SASARAN):
1. MANAJEMEN PROYEK INFORMATIKA (Alias: 'manpro', 'mpi', 'manajemen proyek')
2. ARSITEKTUR DAN ORGANISASI KOMPUTER (Alias: 'arkom', 'aok', 'arsitektur', 'organisasi komputer')
3. KEAMANAN KOMPUTER (Alias: 'keamanan', 'kamjar', 'keamanan jaringan', 'keamanan jaringaan', 'cyber security', 'infosec')
   ⚠️ PERHATIAN KRUSIAL: Jika pengguna menyebut 'keamanan jaringan', 'keamanan jaringaan', atau 'keamanan', maksudnya adalah KEAMANAN KOMPUTER (Nomor 3), BUKAN Arsitektur Komputer! DILARANG KERAS tertukar ke mata kuliah lain!
4. JARINGAN NIRKABEL (Alias: 'jaringan', 'nirkabel', 'wireless', 'jarkom')
5. KECAKAPAN ANTAR PERSONAL (Alias: 'kecakapan', 'kap', 'antar personal', 'interpersonal')
6. TESTING DAN QA PERANGKAT LUNAK (Alias: 'testing', 'qa', 'tqa', 'quality assurance', 'pengujian software')
7. ETIKA PROFESI (Alias: 'etika', 'profesi', 'etprof')
8. PEMROGRAMAN WEB II (Alias: 'web', 'pemweb', 'web 2', 'web ii', 'pemrograman web')

TUGASMU:
1. Jika pengguna menyuruh mengerjakan tugas/kuis/pertemuan di laptop:
   - Target pertemuan (meeting_target) sangat fleksibel:
     • Satu pertemuan: meeting_target="1", "2", dst.
     • Beberapa pertemuan sekaligus: meeting_target="1,2" atau "p1 dan p2"
     • Rentang pertemuan: meeting_target="1-3" atau "p1-p3"
     • Seluruh pertemuan yang tersedia / butuh dikerjakan: meeting_target="all" atau "auto"
   - Target mata kuliah (course_name):
     • Satu matkul spesifik: course_name="Testing dan QA", "Etika Profesi", dsb.
     • Seluruh mata kuliah: course_name="all" (jika pengguna menyuruh "kerjakan semua matkul yang belum selesai", "kerjakan semua yang tersedia")
   - Target modul (target_step):
     • 'kerjakan post test', 'jalankan posttest', 'posttest p3' 👉 `target_step="posttest"`
     • 'kerjakan pretest', 'jalankan pretest', 'pretest p1 dan p2' 👉 `target_step="pretest"`
     • 'kerjakan fordis', 'jawab fordis', 'isi fordis' 👉 `target_step="fordis"`
     • 'isi kuesioner' 👉 `target_step="kuesioner"`
     • 'kerjakan pertemuan X' (tanpa sebut modul spesifik) 👉 `target_step="all"`
   Panggil `tool_execute_learning_pipeline(course_name=..., meeting_target=..., target_step=...)` dengan argumen yang tepat!
2. Jika pengguna menyuruh memindai ulang / scrape LMS (contoh: "mentari scrape", "sinkronkan lms"):
   Panggil `tool_scrape_mentari`.
3. Setelah tool dipanggil, berikan jawaban konfirmasi yang mantap, ramah, dan meyakinkan kepada Sofyan bahwa proses otomatisasi di laptop telah dimulai di latar belakang dan laporan akan otomatis dikirimkan ke WhatsApp begitu selesai."""


def detect_intent(query: str) -> str:
    """
    Mengklasifikasikan pesan pengguna ke dalam 3 kategori:
    1. 'EXECUTE'   : Perintah tegas untuk mengeksekusi otomasi di laptop (pipeline/kuis/scrape).
    2. 'LMS_INFO'  : Permintaan data/informasi/cek status/jadwal LMS Mentari (read-only).
    3. 'CHAT'      : Obrolan santai, tanya-jawab umum, sapaan, curhat, diskusi koding/materi.
    """
    q = query.lower().strip()
    if re.search(r'\b(jangan|batal|batalkan|stop|hentikan)\b', q):
        return "LMS_INFO"
    if re.search(r'\b(draf|draft|ide jawaban|sudah|udah|apakah|kenapa|mengapa|belum bisa)\b', q):
        return "LMS_INFO"

    # 1. Perintah Eksekusi Otomasi di Laptop
    exec_verbs = [
        "kerjakan", "ngerjain", "mengerjakan", "jalankan", "eksekusi", "proses sekarang", "buka browser",
        "mulai kerjakan", "selesaikan pertemuan", "pindai ulang", "master scrape", "suruh ngerjain", "suruh kerjakan",
        "bantu kerjakan", "tolong kerjakan", "garap", "jawab fordis", "isi fordis", "isi forum diskusi", "jawab forum diskusi"
    ]
    has_exec_verb = any(v in q for v in exec_verbs)
    has_target = any(w in q for w in [
        "pertemuan", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9", "p10",
        "p11", "p12", "p13", "p14", "kuis", "pipeline", "lms", "mentari", "posttest", "pretest", "fordis", "forum diskusi"
    ])

    if has_exec_verb and (has_target or "mentari" in q):
        return "EXECUTE"

    # 2. Cek Data & Informasi LMS Mentari (Read-Only)
    lms_terms = [
        "fordis", "forum diskusi", "status tugas", "draf fordis",
        "draft fordis", "pretest", "posttest", "kuesioner", "jawaban mentari",
        "jawaban aku", "jawaban saya", "postingan aku", "postingan saya", "soal dosen",
        "soal yang diberikan", "soal fordis", "instruksi dosen", "dosen nanya", "isi pertemuan", "ada apa aja",
        "udah pretest", "sudah pretest", "udah dikerjakan", "sudah dikerjakan", "udah selesai", "sudah selesai",
        "udah beres", "sudah beres", "yang udah", "yang sudah",
        "rekap nilai", "nilai aku", "nilai saya", "rekap", "nilai", "skor", "score", "grade book", "gradebook", "grade",
        "hasil kuis", "hasil tes", "evaluasi nilai"
    ]
    has_lms_term = any(t in q for t in lms_terms)

    # Deteksi pengecekan nilai / grade
    has_grade_check = any(w in q for w in ["nilai", "skor", "score", "grade", "rekap", "hasil kuis", "hasil tes"])

    # Deteksi jadwal kuliah, dosen, hari, sks (memerlukan kata konteks akademik DAN penanda waktu/pertanyaan)
    has_academic_ctx = any(w in q for w in ["kuliah", "jadwal", "matkul", "mata kuliah", "kelas", "dosen", "pengampu", "sks"])
    has_time_or_q = any(w in q for w in [
        "hari ini", "besok", "lusa", "senin", "selasa", "rabu", "kamis", "jumat", "sabtu",
        "kapan", "jam berapa", "ada", "apa", "siapa", "berapa", "cek", "lihat"
    ])
    has_schedule_check = has_academic_ctx and has_time_or_q

    # Deteksi sinkronisasi data / baru mengerjakan
    sync_terms = [
        "sinkronkan", "update nilai", "refresh nilai", "baru ngerjain", "baru kelar",
        "baru beres", "cek nilai terbaru", "bisa baca", "pertemuan baru", "live sync", "update data"
    ]
    has_sync_check = any(s in q for s in sync_terms)

    # Deteksi pengecekan tugas / pending / kuis yang butuh dikerjakan
    has_task_check = ("tugas" in q or "pending" in q) and any(w in q for w in [
        "cek", "lihat", "pending", "belum", "apa aja", "status", "daftar", "ada", "masih", "sisa"
    ])

    # Deteksi nama mata kuliah dengan kata tanya/cek
    course_keywords = [
        "manajemen proyek", "manpro", "mpi",
        "arsitektur", "arkom", "aok",
        "keamanan komputer", "keamanan jaringan", "keamanan jaringaan", "kamjar", "cyber security",
        "jaringan nirkabel", "jarkom", "nirkabel", "wireless",
        "kecakapan", "kap", "antar personal", "interpersonal",
        "testing", "qa", "tqa", "quality assurance",
        "etika profesi", "etika", "profesi", "etprof",
        "pemrograman web", "pemweb", "web ii", "web 2"
    ]
    has_course = any(c in q for c in course_keywords)
    has_check_word = any(w in q for w in [
        "cek", "lihat", "ada apa", "status", "apa aja", "pertemuan berapa", "kapan", "daftar", "soal", "jawaban", "tanya", "udah", "sudah", "selesai", "beres"
    ])

    # Disuruh Mentari untuk cek
    is_asking_mentari = "mentari" in q and has_check_word

    if has_lms_term or has_grade_check or has_schedule_check or has_sync_check or has_task_check or (has_course and has_check_word) or is_asking_mentari:
        return "LMS_INFO"

    # 3. Default: Obrolan Biasa / Ngobrol Santai
    return "CHAT"


def get_available_agent_models() -> list:
    """Mengembalikan daftar model yang siap digunakan tanpa model yang sedang limit 429."""
    global _last_working_model
    now = time.time()
    ready = [m for m in ACTIVE_MODELS if _model_cooldowns.get(m, 0) < now]
    if _last_working_model in ready:
        ready.remove(_last_working_model)
        ready.insert(0, _last_working_model)
    return ready if ready else ACTIVE_MODELS


def get_agent_response(user_query: str, session_id: str = "default") -> str:
    """
    Memproses pesan masuk dari WhatsApp / CLI dengan sistem dua mode yang cerdas:
    - Mode Obrolan Santai: Bisa diajak ngobrol biasa, curhat, sapaan, tanya materi secara natural.
    - Mode Mentari LMS   : Menjalankan eksekusi atau pengecekan LMS hanya jika disuruh Mentari.
    Menjaga konteks percakapan multi-turn berdasarkan session_id.
    """
    global _last_working_model
    from services.ai_solver import get_gemini_client
    client = get_gemini_client()
    if not client:
        return "Gemini belum tersedia. Periksa GEMINI_API_KEY di .env dan instalasi google-genai."
    from google.genai import types

    intent = detect_intent(user_query)

    # Tentukan System Instruction dan Tools berdasarkan Intent
    if intent == "CHAT":
        sys_inst = CHAT_SYSTEM_INSTRUCTION
        tools = None  # Mode ngobrol biasa TIDAK dibekali tools agar tidak salah eksekusi
        temp = 0.7   # Lebih luwes dan ekspresif untuk obrolan santai
    elif intent == "LMS_INFO":
        sys_inst = LMS_INFO_SYSTEM_INSTRUCTION
        tools = [
            tool_get_my_fordis_answers,
            tool_get_fordis_question,
            tool_get_meeting_summary,
            tool_check_course_forums,
            tool_get_fordis_draft,
            tool_check_completed_tasks,
            tool_check_pending_tasks,
            tool_get_grade_summary,
            tool_sync_grades,
            tool_get_course_schedule
        ]
        temp = 0.3
    else:  # EXECUTE
        sys_inst = EXECUTE_SYSTEM_INSTRUCTION
        tools = [
            tool_execute_learning_pipeline,
            tool_scrape_mentari,
            tool_sync_grades,
            tool_get_my_fordis_answers,
            tool_get_fordis_question,
            tool_get_meeting_summary,
            tool_check_course_forums,
            tool_get_fordis_draft,
            tool_check_completed_tasks,
            tool_check_pending_tasks,
            tool_get_grade_summary,
            tool_get_course_schedule
        ]
        temp = 0.2

    executed_actions = {}
    if tools:
        def once_per_request(fn):
            @functools.wraps(fn)
            def call(*args, **kwargs):
                key = (fn.__name__, json.dumps([args, kwargs], sort_keys=True))
                if key not in executed_actions:
                    executed_actions[key] = fn(*args, **kwargs)
                return executed_actions[key]
            return call
        tools = [once_per_request(fn) if fn in (tool_execute_learning_pipeline, tool_scrape_mentari) else fn
                 for fn in tools]

    # Siapkan riwayat percakapan untuk session_id ini
    if session_id not in _session_histories:
        _session_histories[session_id] = []

    history_records = _session_histories[session_id][-10:]  # Simpan 10 pesan terakhir
    gemini_history = []
    for h in history_records:
        role = "user" if h["role"] == "user" else "model"
        gemini_history.append(
            types.Content(role=role, parts=[types.Part.from_text(text=h["text"])])
        )

    available_models = get_available_agent_models()
    last_error = None

    for model_name in available_models:
        try:
            config_kwargs = {
                "system_instruction": sys_inst,
                "temperature": temp
            }
            if tools:
                config_kwargs["tools"] = tools

            chat = client.chats.create(
                model=model_name,
                history=gemini_history if gemini_history else None,
                config=types.GenerateContentConfig(**config_kwargs)
            )

            response = chat.send_message(user_query)
            if response and response.text:
                reply_text = response.text.strip()
                _last_working_model = model_name

                # Catat ke memori sesi percakapan
                _session_histories[session_id].append({"role": "user", "text": user_query})
                _session_histories[session_id].append({"role": "model", "text": reply_text})
                if len(_session_histories[session_id]) > 20:
                    _session_histories[session_id] = _session_histories[session_id][-20:]

                return reply_text
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str:
                _model_cooldowns[model_name] = time.time() + 300  # Cooldown 5 menit
            elif "404" in err_str or "not found" in err_str:
                _model_cooldowns[model_name] = time.time() + 86400
            if executed_actions:
                return '\n\n'.join(executed_actions.values())
            continue
        if executed_actions:
            return '\n\n'.join(executed_actions.values())

    # Fallback darurat cerdas jika seluruh koneksi AI sedang sibuk
    return emergency_fallback_handler(user_query, str(last_error), intent=intent)


def emergency_fallback_handler(user_query: str, error_msg: str, intent: str = "CHAT") -> str:
    """Fallback deterministik yang ramah dan aman jika API Gemini sedang mengalami gangguan."""
    q = user_query.lower()

    # Ekstraksi nomor pertemuan jika ada
    m_match = re.search(r'pertemuan\s*(\d+)|p-(\d+)|p\s*(\d+)', q)
    p_num = 2
    if m_match:
        p_num = int(m_match.group(1) or m_match.group(2) or m_match.group(3))

    # Cari mata kuliah yang spesifik menggunakan resolver kanonikal
    c_key, c_name = resolve_course_key(q)

    # 1. Jika pengguna bertanya tentang jawaban miliknya
    if any(w in q for w in ["jawaban aku", "jawaban saya", "jawaban mentari", "postingan aku", "sudah jawab"]):
        return tool_get_my_fordis_answers(c_name or "MANAJEMEN PROYEK INFORMATIKA", p_num)

    # 2. Jika pengguna menanyakan soal dosen
    if any(w in q for w in ["soal dosen", "soal yang diberikan", "soal fordis", "dosen nanya apa", "instruksi dosen"]):
        return tool_get_fordis_question(c_name or "MANAJEMEN PROYEK INFORMATIKA", p_num)

    # 3. Jika pengguna menanyakan rekap nilai / skor / grade
    if any(w in q for w in ["nilai", "skor", "grade", "rekap", "hasil kuis", "hasil tes"]):
        return tool_get_grade_summary(c_name)

    # 4. Jika pengguna menanyakan apa yang sudah selesai / sudah dikerjakan / udah pretest
    if any(w in q for w in ["udah pretest", "sudah pretest", "udah dikerjakan", "sudah dikerjakan", "udah selesai", "sudah selesai", "yang udah", "yang sudah", "sudah beres", "udah beres"]):
        return tool_check_completed_tasks(c_name)

    # 5. Jika pengguna meminta ringkasan satu pertemuan
    if any(w in q for w in ["ada apa aja", "isi pertemuan", "status pertemuan", "ringkasan pertemuan"]):
        return tool_get_meeting_summary(c_name or "MANAJEMEN PROYEK INFORMATIKA", p_num)

    # 5. Jika intent eksekusi
    if intent == "EXECUTE":
        return "Respons AI terputus. Periksa antrean sebelum mengulang perintah; status eksekusi belum dapat dipastikan."

    # 6. Jika intent LMS Info umum
    if intent == "LMS_INFO":
        if "fordis" in q and any(w in q for w in ["pertemuan berapa", "kapan", "aktif"]):
            return tool_check_course_forums(c_name or "MANAJEMEN PROYEK INFORMATIKA")
        elif "draf" in q or "draft" in q or "contekan" in q:
            return tool_get_fordis_draft(c_name or "MANAJEMEN PROYEK INFORMATIKA", p_num)
        else:
            return tool_check_pending_tasks(c_name)

    # 7. Mode Chat
    return (
        "Halo Sofyan! 😊\n"
        "Aku dengar pesanmu, tapi koneksi ke server AI lagi agak padat sebentar nih. "
        "Aku tetap standby kok! Kalau mau tanya soal LMS atau minta cek jawaban/soal fordis, "
        "langsung bilang aja ya!"
    )

