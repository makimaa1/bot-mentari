import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
from pathlib import Path

BASE_DIR = Path(".").resolve()
MEETING_GRADES_PATH = BASE_DIR / "data" / "mentari_meeting_grades.json"
GRADEBOOK_PATH = BASE_DIR / "data" / "mentari_gradebook_master.json"

def format_date_str(iso_str):
    if not iso_str:
        return ""
    try:
        # e.g. 2026-09-08T12:35:13.193Z -> 08 Sep 2026
        parts = iso_str.split("T")[0].split("-")
        months = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
        m_idx = int(parts[1]) - 1
        return f"{parts[2]} {months[m_idx]} {parts[0]}"
    except Exception:
        return iso_str[:10]

def tool_get_grade_summary(course_name: str = "", meeting_num: int = None) -> str:
    """
    MEMERIKSA dan MENAMPILKAN REKAP NILAI KUIS PER PERTEMUAN (Nilai Pre-Test & Nilai Post-Test)
    secara rinci dan transparan untuk setiap pertemuan dari seluruh 8 mata kuliah atau mata kuliah tertentu di Mentari LMS UNPAM.
    """
    if not MEETING_GRADES_PATH.exists() and not GRADEBOOK_PATH.exists():
        return "Data rekap nilai belum ditemukan di sistem. Silakan sinkronkan terlebih dahulu."

    meeting_data = {}
    if MEETING_GRADES_PATH.exists():
        try:
            with open(MEETING_GRADES_PATH, encoding="utf-8") as f:
                meeting_data = json.load(f)
        except Exception:
            pass

    q = course_name.strip().lower() if course_name else ""
    is_all = not q or any(w in q for w in ["semua", "seluruh", "total", "rekap", "pertemuannya"])

    student_name = "SOFYAN AGUNG"
    student_nim = "231011400159"

    # Cari target mata kuliah spesifik
    target_course = None
    if not is_all and meeting_data:
        for c_key in meeting_data.keys():
            if q in c_key.lower() or any(w in c_key.lower() for w in q.split() if len(w) > 3):
                target_course = c_key
                break

    # 1. KASUS: 1 MATA KULIAH SPESIFIK DENGAN NOMOR PERTEMUAN SPESIFIK
    if target_course and meeting_num:
        c_info = meeting_data[target_course]
        meetings = c_info.get("meetings", {})
        m_key = f"Pertemuan {meeting_num}"
        m_info = meetings.get(m_key)

        if not m_info:
            return f"Data {m_key} untuk mata kuliah *{target_course}* belum tercatat di sistem."

        pre = m_info.get("pretest")
        post = m_info.get("posttest")
        pre_g = f"*{pre.get('grade')}*" if (pre and pre.get("grade") is not None) else "_Belum dikerjakan_"
        post_g = f"*{post.get('grade')}*" if (post and post.get("grade") is not None) else "_Belum dikerjakan_"

        pre_date = f" (Selesai: {format_date_str(pre.get('finished_at'))})" if (pre and pre.get("finished_at")) else ""
        post_date = f" (Selesai: {format_date_str(post.get('finished_at'))})" if (post and post.get("finished_at")) else ""

        lines = [
            f"📊 *NILAI KUIS PERTEMUAN {meeting_num}*",
            f"👤 *Mahasiswa*: {student_name} ({student_nim})",
            f"📚 *Mata Kuliah*: {target_course}\n",
            f"• 📝 *Pre-Test*: {pre_g}{pre_date}",
            f"• 🎯 *Post-Test*: {post_g}{post_date}"
        ]
        return "\n".join(lines)

    # 2. KASUS: 1 MATA KULIAH SPESIFIK (SELURUH PERTEMUAN)
    if target_course:
        c_info = meeting_data[target_course]
        meetings = c_info.get("meetings", {})
        done_count = c_info.get("completed_quizzes_count", 0)

        lines = [
            f"📊 *DETAIL NILAI KUIS PER PERTEMUAN*",
            f"👤 *Mahasiswa*: {student_name} ({student_nim})",
            f"📚 *Mata Kuliah*: {target_course}",
            f"🏆 *Total Kuis Diselesaikan*: {done_count} kuis\n",
            "📋 *Rincian Nilai Tiap Pertemuan*:"
        ]

        active_meetings = []
        inactive_meetings = []

        for m_name, m_val in meetings.items():
            pre = m_val.get("pretest")
            post = m_val.get("posttest")
            pre_has = pre and pre.get("grade") is not None
            post_has = post and post.get("grade") is not None

            if pre_has or post_has:
                pre_txt = f"Pre-Test: *{pre.get('grade')}* 📝" if pre_has else "Pre-Test: _Belum dikerjakan_"
                post_txt = f"Post-Test: *{post.get('grade')}* 🎯" if post_has else "Post-Test: _Belum dikerjakan_"
                active_meetings.append(f"• *{m_name}*: {pre_txt} | {post_txt}")
            else:
                inactive_meetings.append(m_name.replace("Pertemuan ", "P-"))

        if active_meetings:
            lines.extend(active_meetings)
        else:
            lines.append("• _Belum ada kuis yang dikerjakan pada mata kuliah ini._")

        if inactive_meetings:
            lines.append(f"\nℹ️ *Pertemuan lainnya ({', '.join(inactive_meetings)})*: Belum dikerjakan / Belum dibuka.")

        return "\n".join(lines)

    # 3. KASUS: REKAPITULASI SELURUH 8 MATA KULIAH (PER PERTEMUAN)
    summary_blocks = [
        f"📊 *REKAPITULASI NILAI KUIS PER PERTEMUAN (MENTARI LMS)*",
        f"👤 *Mahasiswa*: {student_name} ({student_nim})",
        f"🏫 *Kelas*: 07TPLP003 | Teknik Informatika UNPAM\n"
    ]

    active_courses_blocks = []
    empty_courses = []

    for idx, (c_name, c_info) in enumerate(meeting_data.items(), 1):
        done_count = c_info.get("completed_quizzes_count", 0)
        meetings = c_info.get("meetings", {})

        meeting_lines = []
        for m_name, m_val in meetings.items():
            pre = m_val.get("pretest")
            post = m_val.get("posttest")
            pre_has = pre and pre.get("grade") is not None
            post_has = post and post.get("grade") is not None

            if pre_has or post_has:
                pre_txt = f"Pre-Test: *{pre.get('grade')}* 📝" if pre_has else "Pre-Test: _Belum dikerjakan_"
                post_txt = f"Post-Test: *{post.get('grade')}* 🎯" if post_has else "Post-Test: _Belum dikerjakan_"
                meeting_lines.append(f"   • *{m_name}*: {pre_txt} | {post_txt}")

        if done_count > 0 and meeting_lines:
            c_block = [f"📚 *{len(active_courses_blocks)+1}. {c_name}* ({done_count} Kuis Selesai):"]
            c_block.extend(meeting_lines)
            active_courses_blocks.append("\n".join(c_block))
        else:
            empty_courses.append(c_name)

    if active_courses_blocks:
        summary_blocks.append("\n\n".join(active_courses_blocks))

    if empty_courses:
        empty_lines = [f"\n🔒 *Mata Kuliah Lainnya (Belum Ada Kuis Dikerjakan):*"]
        for ec in empty_courses:
            empty_lines.append(f"   • {ec}")
        summary_blocks.append("\n".join(empty_lines))

    summary_blocks.append("\n💡 *Catatan*: Nilai di atas adalah nilai murni per kuis yang tercatat langsung di server Mentari LMS UNPAM.")
    return "\n".join(summary_blocks)

if __name__ == "__main__":
    print("=== TEST ALL COURSES ===")
    print(tool_get_grade_summary("semua"))
    print("\n=== TEST SINGLE COURSE (ETIKA PROFESI) ===")
    print(tool_get_grade_summary("etika profesi"))
    print("\n=== TEST SINGLE MEETING (ETIKA PROFESI P2) ===")
    print(tool_get_grade_summary("etika profesi", 2))
