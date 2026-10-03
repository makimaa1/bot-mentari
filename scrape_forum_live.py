"""
Scraper LIVE Forum Diskusi (Fordis) Mentari LMS UNPAM.
Membaca langsung dari web: soal asli dosen, balasan/pertanyaan teman sekelas, dan balasan milik Sofyan.
Hasil disimpan ke data/forum_live.json (cache) sebagai fallback ketika browser tidak bisa dibuka.
"""
import sys
import json
import time
import re
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
LIVE_PATH = BASE_DIR / "data" / "forum_live.json"
STUDENT_NAME = "SOFYAN AGUNG"
ROLES = ("Mahasiswa", "Dosen")
NOISE = {"DASHBOARD", "BACK", "REFRESH", "FILE ATTACHMENT", "REPLY"}


def parse_forum_text(body: str, student_name: str = STUDENT_NAME) -> dict:
    """Mengurai teks halaman forum menjadi soal dosen + daftar balasan."""
    lines = [l.rstrip() for l in body.splitlines()]
    # Potong footer Cloudflare / noise di akhir
    cut = None
    for i, l in enumerate(lines):
        if l.strip().lower().startswith(("mentari.unpam.ac.id", "performing security verification")):
            cut = i
            break
    if cut is not None:
        lines = lines[:cut]

    # Mulai setelah REFRESH (header halaman)
    start = 0
    for i, l in enumerate(lines):
        if l.strip() == "REFRESH":
            start = i + 1
            break
    lines = lines[start:]

    # Pecah berdasarkan tombol REPLY
    segments, cur = [], []
    for l in lines:
        if l.strip() == "REPLY":
            segments.append(cur)
            cur = []
        else:
            cur.append(l)
    if any(x.strip() for x in cur):
        segments.append(cur)

    result = {"lecturer_post": "", "lecturer_name": "", "posts": []}
    if not segments:
        return result

    # Segmen 0 = soal dosen (judul, nama dosen, tanggal, isi)
    first = [l for l in segments[0] if l.strip() and l.strip() not in NOISE]
    if first:
        result["lecturer_name"] = first[1].strip() if len(first) > 1 else ""
        result["lecturer_post"] = "\n".join(first[3:] if len(first) > 3 else first).strip()
        if first:
            result["title"] = first[0].strip()

    # Segmen berikutnya = balasan (inisial, nama, role, tanggal, isi)
    for seg in segments[1:]:
        seg = [l for l in seg if l.strip() != "FILE ATTACHMENT"]
        idx = next((i for i, l in enumerate(seg) if l.strip() in ROLES), None)
        if idx is None or idx < 1:
            continue
        author = seg[idx - 1].strip()
        role = seg[idx].strip()
        rest = seg[idx + 1:]
        date = rest[0].strip() if rest else ""
        text = "\n".join(rest[1:]).strip()
        if not text:
            continue
        is_me = student_name.lower() in author.lower()
        result["posts"].append({
            "author": author, "role": role, "date": date, "text": text, "is_me": is_me,
        })
    return result


def _open_forum(page, course: dict, meeting: int) -> str:
    """Navigasi ke halaman forum pertemuan tertentu dan kembalikan teks body-nya."""
    import pipeline_runner as pr
    page.goto(course["url"], wait_until="domcontentloaded", timeout=60000)
    pr.ensure_turnstile_cleared(page)
    page.wait_for_timeout(2500)
    if not pr.ensure_meeting_expanded(page, meeting):
        return "__NO_MEETING__"
    scope = pr.get_meeting_scope(page, meeting)
    for c in scope.locator('.MuiCard-root, .MuiPaper-root').all():
        cls = c.get_attribute("class") or ""
        if "MuiAccordion" in cls:
            continue
        txt = c.inner_text().strip()
        first_l = txt.splitlines()[0] if txt else ""
        if "forum" in first_l.lower():
            if "belum tersedia" in txt.lower():
                return "__NOT_AVAILABLE__"
            btn = c.locator('button:has-text("FORUM")').first
            if btn.count() == 0:
                return "__NOT_AVAILABLE__"
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            page.wait_for_timeout(3500)
            body = page.locator("body").inner_text()
            # Jika halaman berupa daftar thread, buka thread pertama
            if "REPLY" not in body:
                cell = page.locator("table tbody tr td").first
                if cell.count() > 0:
                    cell.click()
                    page.wait_for_timeout(3500)
                    body = page.locator("body").inner_text()
            return body
    return "__NO_FORUM__"


def scrape_forum_live(course_key: str, meeting: int, headless: bool = False) -> dict:
    """Scrape live 1 forum. Mengembalikan dict hasil & menyimpannya ke cache."""
    import pipeline_runner as pr
    from playwright.sync_api import sync_playwright

    course = pr.COURSES[course_key]
    out = {"course": course["name"], "pertemuan": int(meeting), "scraped_at": time.time(),
           "status": "error", "source": "live"}
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=headless, channel="chrome",
                                        args=["--start-maximized", "--disable-blink-features=AutomationControlled"])
        except Exception:
            browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(storage_state=str(pr.AUTH_PATH), no_viewport=True)
        page = ctx.new_page()
        try:
            body = _open_forum(page, course, int(meeting))
            if body.startswith("__"):
                out["status"] = {"__NOT_AVAILABLE__": "belum_tersedia", "__NO_FORUM__": "tidak_ada",
                                 "__NO_MEETING__": "pertemuan_tidak_ditemukan"}[body]
            else:
                parsed = parse_forum_text(body)
                out.update(parsed)
                out["status"] = "aktif"
                mine = [x for x in parsed["posts"] if x["is_me"]]
                out["my_reply_count"] = len(mine)
                out["has_answered"] = len(mine) > 0
                out["url"] = page.url
        except Exception as e:
            out["error"] = str(e)
        finally:
            browser.close()

    save_cache(out)
    return out


def save_cache(entry: dict):
    data = []
    if LIVE_PATH.exists():
        try:
            data = json.loads(LIVE_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = []
    data = [d for d in data if not (d.get("course") == entry["course"] and d.get("pertemuan") == entry["pertemuan"])]
    data.append(entry)
    LIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIVE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_cache(course_name: str, meeting: int):
    if not LIVE_PATH.exists():
        return None
    try:
        for d in json.loads(LIVE_PATH.read_text(encoding="utf-8")):
            if d.get("course") == course_name and d.get("pertemuan") == int(meeting):
                return d
    except Exception:
        pass
    return None


if __name__ == "__main__":
    ck = sys.argv[1] if len(sys.argv) > 1 else "2"
    mt = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    r = scrape_forum_live(ck, mt)
    print(json.dumps(r, indent=2, ensure_ascii=False)[:4000])
