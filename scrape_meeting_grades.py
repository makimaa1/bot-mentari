"""
Scraper Komprehensif Nilai Kuis Per Pertemuan (Pre-Test & Post-Test) Mentari LMS UNPAM.
Mengambil nilai riil per pertemuan untuk semua mata kuliah aktif.
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

AUTH_PATH = Path(__file__).resolve().parent / "data/auth.json"
OUTPUT_FILE = Path(__file__).resolve().parent / "data/mentari_meeting_grades.json"
GRADEBOOK_MASTER_FILE = Path(__file__).resolve().parent / "data/mentari_gradebook_master.json"

def scrape_all_meeting_grades(target_course_name: str = None):
    print("=" * 70)
    print("    MENTARI LMS - SCRAPER NILAI KUIS PER PERTEMUAN (PRE & POST TEST)")
    print("=" * 70)

    if not GRADEBOOK_MASTER_FILE.exists():
        raise FileNotFoundError("Data gradebook belum ada; jalankan master_scraper.py terlebih dahulu.")

    with open(GRADEBOOK_MASTER_FILE, "r", encoding="utf-8") as f:
        master_data = json.load(f)

    # Muat cache yang sudah ada agar tidak menimpa matkul lain jika single-course sync
    all_course_grades = {}
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                all_course_grades = json.load(f)
        except Exception:
            all_course_grades = {}

    courses = []
    canonical_name = None
    if target_course_name:
        from services.agent_bot import resolve_course_key
        _, canonical_name = resolve_course_key(target_course_name, strict=True)
    for cname, cinfo in master_data.items():
        code = cinfo.get("course_code")
        if code:
            if target_course_name:
                if canonical_name.casefold() == cname.casefold():
                    courses.append({"course_name": cname, "course_code": code})
            else:
                courses.append({"course_name": cname, "course_code": code})

    print(f"[*] Total mata kuliah yang akan diproses: {len(courses)}")
    if not courses:
        raise ValueError('Tidak ada mata kuliah yang cocok untuk disinkronkan.')

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(storage_state=str(AUTH_PATH), no_viewport=True)
        page = ctx.new_page()

        print("[*] Membuka Mentari LMS...")
        page.goto("https://mentari.unpam.ac.id", wait_until="domcontentloaded")
        for _ in range(15):
            title = page.title()
            if "Just a moment" not in title and title:
                break
            time.sleep(1)

        print("[*] Mengambil Token Autentikasi...")
        token = page.evaluate("""() => {
            try {
                const access = JSON.parse(localStorage.getItem('access'));
                return access && access[0] ? access[0].token : null;
            } catch(e) {
                return null;
            }
        }""")

        if not token:
            browser.close()
            raise RuntimeError('Sesi Mentari tidak valid; login ulang dengan save_auth.py.')

        print(f"[V] Token berhasil didapatkan (panjang: {len(token)})")

        for c_idx, c in enumerate(courses, 1):
            cname = c["course_name"]
            code = c["course_code"]
            print(f"\n[{c_idx}/{len(courses)}] Memproses: {cname} ({code})...")

            # 1. Fetch user-course data
            course_struct = page.evaluate("""async (payload) => {
                try {
                    const res = await fetch('/api/user-course/' + payload.code, {
                        headers: { 'authorization': 'Bearer ' + payload.token }
                    });
                    if (!res.ok) return null;
                    return await res.json();
                } catch(e) {
                    return null;
                }
            }""", {"code": code, "token": token})

            if not course_struct or "data" not in course_struct:
                print(f"  [!] Gagal mengambil struktur kursus untuk {cname}")
                continue

            # 2. Collect quiz IDs
            quizzes_to_fetch = []
            sections_data = course_struct.get("data", [])
            for sec in sections_data:
                sec_code = sec.get("kode_section", "")
                sec_name = sec.get("nama_section", sec_code)
                for sub in sec.get("sub_section", []):
                    if sub.get("tipe") == "QUIZ" and sub.get("id"):
                        judul = sub.get("judul", "Quiz")
                        quizzes_to_fetch.append({
                            "section_code": sec_code,
                            "section_name": sec_name,
                            "quiz_type": "Pre-Test" if "pre" in judul.lower() else ("Post-Test" if "post" in judul.lower() else judul),
                            "judul": judul,
                            "quiz_id": sub.get("id")
                        })

            print(f"  [*] Ditemukan {len(quizzes_to_fetch)} kuis. Mengambil nilai peserta...")

            # 3. Batch fetch quiz participant grades
            results = page.evaluate("""async (payload) => {
                const out = [];
                for (const item of payload.items) {
                    try {
                        const res = await fetch('/api/quiz/peserta/' + item.quiz_id, {
                            headers: { 'authorization': 'Bearer ' + payload.token }
                        });
                        if (res.ok) {
                            const d = await res.json();
                            out.push({
                                ...item,
                                quiz_data: d.quiz || null
                            });
                        } else {
                            out.push({ ...item, quiz_data: null });
                        }
                    } catch(e) {
                        out.push({ ...item, quiz_data: null, error: String(e) });
                    }
                }
                return out;
            }""", {"items": quizzes_to_fetch, "token": token})

            # 4. Group by meeting / section
            meetings_map = {}
            for item in results:
                s_name = item["section_name"]
                if s_name not in meetings_map:
                    meetings_map[s_name] = {
                        "section_name": s_name,
                        "section_code": item["section_code"],
                        "pretest": None,
                        "posttest": None,
                        "other_quizzes": []
                    }

                qd = item.get("quiz_data")
                grade = qd.get("grade") if qd else None
                status = "Selesai" if grade is not None else "Belum Dikerjakan"
                finished_at = qd.get("end_at") if qd else None
                duration_sec = qd.get("end_in_second") if qd else None

                q_info = {
                    "quiz_id": item["quiz_id"],
                    "judul": item["judul"],
                    "quiz_type": item["quiz_type"],
                    "grade": grade,
                    "status": status,
                    "finished_at": finished_at,
                    "duration_seconds": duration_sec
                }

                if item["quiz_type"] == "Pre-Test":
                    meetings_map[s_name]["pretest"] = q_info
                elif item["quiz_type"] == "Post-Test":
                    meetings_map[s_name]["posttest"] = q_info
                else:
                    meetings_map[s_name]["other_quizzes"].append(q_info)

            # Hitung ringkasan per kursus
            completed_quizzes = [r for r in results if r.get("quiz_data") and r["quiz_data"].get("grade") is not None]
            all_course_grades[cname] = {
                "course_name": cname,
                "course_code": code,
                "total_quizzes": len(results),
                "completed_quizzes_count": len(completed_quizzes),
                "meetings": meetings_map
            }

            print(f"  [V] Selesai: {len(completed_quizzes)} kuis telah dikerjakan.")

        browser.close()

    # Simpan hasil akhir
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_course_grades, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print(f"🎉 SUKSES! Rekap nilai per pertemuan tersimpan di:\n👉 {OUTPUT_FILE}")
    print("=" * 70)

if __name__ == "__main__":
    scrape_all_meeting_grades()
