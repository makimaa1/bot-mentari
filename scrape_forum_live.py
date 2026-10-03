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
from services.json_store import edit_json

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

    result = {"lecturer_post": "", "lecturer_name": "", "posts": []}
    reply_index = next((i for i, line in enumerate(lines) if line.strip().upper() == 'REPLY'), None)
    if reply_index is None:
        return result

    # Segmen 0 = soal dosen (judul, nama dosen, tanggal, isi)
    first = [l for l in lines[:reply_index] if l.strip() and l.strip() not in NOISE]
    if first:
        result["lecturer_name"] = first[1].strip() if len(first) > 1 else ""
        result["lecturer_post"] = "\n".join(first[3:] if len(first) > 3 else first).strip()
        if first:
            result["title"] = first[0].strip()

    # Nested replies may omit their own REPLY button; author/role headers still exist.
    reply_lines = lines[reply_index + 1:]
    headers = [i for i, line in enumerate(reply_lines) if i > 0 and line.strip() in ROLES
               and i + 1 < len(reply_lines)
               and re.match(r'\s*(?:Senin|Selasa|Rabu|Kamis|Jumat|Sabtu|Minggu|\d)', reply_lines[i + 1], re.I)]
    for number, idx in enumerate(headers):
        end = headers[number + 1] - 1 if number + 1 < len(headers) else len(reply_lines)
        if number + 1 < len(headers) and end > idx + 1 and re.fullmatch(r'[A-Z]{1,3}', reply_lines[end - 1].strip()):
            end -= 1
        author = reply_lines[idx - 1].strip()
        role = reply_lines[idx].strip()
        rest = [line for line in reply_lines[idx + 1:end] if line.strip().upper() not in NOISE]
        date = rest[0].strip() if rest else ""
        text = "\n".join(rest[1:]).strip()
        if not text:
            continue
        is_me = bool(student_name.strip()) and student_name.strip().casefold() == author.casefold()
        result["posts"].append({
            "author": author, "role": role, "date": date, "text": text, "is_me": is_me,
        })
    return result


def _open_forum(page, course: dict, meeting: int, navigate: bool = True) -> str:
    """Navigasi ke halaman forum pertemuan tertentu dan kembalikan teks body-nya."""
    import pipeline_runner as pr
    if navigate:
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
            if btn.count() == 0 or not btn.is_enabled():
                return "__LOCKED__"
            btn.scroll_into_view_if_needed()
            btn.click(force=True)
            page.wait_for_timeout(3500)
            body = page.locator("body").inner_text()
            requirement = re.search(r'min(?:imum)?\s*repl(?:ay|y|ies)(?:\s+forum)?\s*[:=]?\s*(\d+)', body, re.I)
            if 'soal forum diskusi belum tersedia' in body.lower():
                return '__NOT_AVAILABLE__'
            # Jika halaman berupa daftar thread, buka thread pertama
            if "REPLY" not in body:
                cell = page.locator("table tbody tr td").first
                if cell.count() > 0:
                    cell.click()
                    page.wait_for_timeout(3500)
                    body = page.locator("body").inner_text()
            if not re.search(r'^\s*REPLY\s*$', body, re.M | re.I):
                raise RuntimeError('Thread fordis belum terbuka atau sesi LMS sudah kedaluwarsa.')
            return (f'Min Replay: {requirement.group(1)}\n' if requirement else '') + body
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
                out["status"] = {"__NOT_AVAILABLE__": "belum_tersedia", "__NO_FORUM__": "tidak_ada", '__LOCKED__': 'terkunci',
                                 "__NO_MEETING__": "pertemuan_tidak_ditemukan"}[body]
            else:
                from services.auth import extract_stored_credentials
                parsed = parse_forum_text(body, extract_stored_credentials().get('fullname') or STUDENT_NAME)
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
    if entry.get('status') == 'error':
        return
    with edit_json(LIVE_PATH, []) as data:
        data[:] = [d for d in data if not (d.get("course") == entry["course"] and d.get("pertemuan") == entry["pertemuan"])]
        data.append(entry)
    if entry.get('status') == 'aktif':
        mine = [p for p in entry.get('posts', []) if p.get('is_me')]
        detail = {'course': entry['course'], 'pertemuan': entry['pertemuan'],
                  'topic': entry.get('title', ''), 'dosen': entry.get('lecturer_name', ''),
                  'lecturer_instruction': entry.get('lecturer_post', ''), 'has_answered': bool(mine),
                  'total_replies': len(mine), 'required_replies': entry.get('required_replies', 3),
                  'scraped_at': entry.get('scraped_at'),
                  'my_submissions': [{'reply_index': i + 1, 'timestamp': p.get('date', ''), 'content': p['text']}
                                     for i, p in enumerate(mine)]}
        with edit_json(LIVE_PATH.parent / 'mentari_forum_details.json', []) as details:
            details[:] = [d for d in details if (d.get('course'), d.get('pertemuan')) != (entry['course'], entry['pertemuan'])]
            details.append(detail)


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
