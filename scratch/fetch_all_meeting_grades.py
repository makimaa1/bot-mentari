from playwright.sync_api import sync_playwright
from pathlib import Path
import json
import time

AUTH_PATH = Path("data/auth.json").resolve()

def run():
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

        print("[*] Mengambil data kursus Etika Profesi...")
        course_data = page.evaluate("""async () => {
            const access = JSON.parse(localStorage.getItem('access'));
            const token = access[0].token;
            const res = await fetch('/api/user-course/20261-07TPLP003-22TIF0422', {
                headers: { 'authorization': 'Bearer ' + token }
            });
            return await res.json();
        }""")

        quizzes = []
        for sec in course_data.get("data", []):
            sec_name = sec.get("nama_section")
            for sub in sec.get("sub_section", []):
                if sub.get("tipe") == "QUIZ" and sub.get("id"):
                    quizzes.append({
                        "section": sec_name,
                        "judul": sub.get("judul"),
                        "quiz_id": sub.get("id")
                    })
        print(f"[*] Ditemukan {len(quizzes)} kuis di Etika Profesi.")

        # Ambil nilai semua kuis
        quiz_results = page.evaluate("""async (items) => {
            const access = JSON.parse(localStorage.getItem('access'));
            const token = access[0].token;
            const out = [];
            for (const item of items) {
                try {
                    const res = await fetch('/api/quiz/peserta/' + item.quiz_id, {
                        headers: { 'authorization': 'Bearer ' + token }
                    });
                    const d = await res.json();
                    out.push({
                        section: item.section,
                        judul: item.judul,
                        quiz_id: item.quiz_id,
                        quiz: d.quiz || null
                    });
                } catch(e) {
                    out.push({
                        section: item.section,
                        judul: item.judul,
                        quiz_id: item.quiz_id,
                        error: String(e)
                    });
                }
            }
            return out;
        }""", quizzes)

        print("\n=== REKAP NILAI KUIS PER PERTEMUAN (ETIKA PROFESI) ===")
        for r in quiz_results:
            q = r.get("quiz")
            if q and q.get("grade") is not None:
                grade_str = f"Grade: {q.get('grade')}"
                end_at = q.get("end_at")
            else:
                grade_str = "Belum Mengerjakan"
                end_at = None
            print(f"[{r['section']}] {r['judul']}: {grade_str} (Selesai: {end_at})")

        browser.close()

if __name__ == "__main__":
    run()
