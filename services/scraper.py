from playwright.sync_api import Page
import re
import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "mentari_deep_data.json"


def extract_user_profile(page: Page) -> dict:
    """Mengekstrak informasi ringkas pengguna dari header dashboard Mentari."""
    user_info = {"name": "SOFYAN AGUNG", "nim": "231011400159", "prodi": "Teknik Informatika", "raw": ""}
    try:
        selectors = [
            ".user-name",
            ".profile-name",
            "header .font-semibold",
            "header span",
            ".avatar + div",
        ]
        for sel in selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                text = loc.first.inner_text().strip()
                if text and len(text) > 2:
                    user_info["raw"] = text
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    if lines:
                        user_info["name"] = lines[0]
                    if len(lines) > 1:
                        user_info["nim"] = lines[1]
                    break
    except Exception:
        pass
    return user_info


def extract_courses(page: Page) -> list[dict]:
    """
    Mengekstrak 8 mata kuliah aktif semester berjalan kelas 07TPLP003
    dari dashboard Mentari.
    """
    courses = []
    seen = set()

    try:
        # Cari kartu mata kuliah kelas 07TPLP003
        card_locs = page.locator('div:has-text("07TPLP003"):has-text("SKS")').all()
        for c in card_locs:
            try:
                lines = [l.strip() for l in c.inner_text().splitlines() if l.strip()]
                if lines:
                    title = lines[0]
                    if title.lower() not in {"dashboard", "kode kelas", "sks", "dosen", "hari"} and title not in seen:
                        seen.add(title)
                        
                        # Cek link detail jika ada
                        inner_a = c.locator('a[href*="/u-courses/"]').first
                        href = inner_a.get_attribute("href") if inner_a.count() > 0 else ""
                        
                        courses.append({
                            "title": title,
                            "details": " | ".join(lines[1:3]) if len(lines) > 1 else "",
                            "url": f"https://mentari.unpam.ac.id{href}" if href.startswith("/") else href
                        })
            except Exception:
                pass
    except Exception:
        pass

    # Jika tidak ada kartu di DOM saat ini, muat dari database hasil penelusuran jika ada
    if not courses and DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                courses.append({
                    "title": item.get("course_name"),
                    "details": f"{item.get('total_meetings', 0)} Pertemuan",
                    "url": item.get("url")
                })
        except Exception:
            pass

    return courses


def extract_pending_activities(page: Page) -> list[dict]:
    """
    Mengekstrak daftar tugas, kuis, dan forum aktif dari database penelusuran
    dan widget timeline Mentari.
    """
    activities = []

    # 1. Coba baca dari data detail penelusuran mata kuliah
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for course in data:
                c_name = course.get("course_name", "Matkul")
                for m in course.get("meetings", []):
                    p_num = m.get("pertemuan")
                    # Forum
                    for fo in m.get("forum", []):
                        activities.append({
                            "type": "FORUM",
                            "course": c_name,
                            "meeting": p_num,
                            "title": f"Forum Diskusi Pertemuan {p_num}",
                            "details": f"Matkul: {c_name}"
                        })
                    # Kuis
                    for ku in m.get("kuis", []):
                        activities.append({
                            "type": "KUIS",
                            "course": c_name,
                            "meeting": p_num,
                            "title": f"Kuis Pertemuan {p_num}",
                            "details": f"Matkul: {c_name}"
                        })
                    # Tugas
                    for tu in m.get("tugas", []):
                        activities.append({
                            "type": "TUGAS",
                            "course": c_name,
                            "meeting": p_num,
                            "title": f"Tugas Pertemuan {p_num}",
                            "details": f"Matkul: {c_name}"
                        })
        except Exception:
            pass

    return activities


def load_forum_ai_drafts() -> list[dict]:
    """Memuat seluruh draf tanggapan AI untuk forum-forum yang telah ditelusuri."""
    drafts = []
    if not DATA_FILE.exists():
        return drafts

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for course in data:
            c_name = course.get("course_name")
            for m in course.get("meetings", []):
                p_num = m.get("pertemuan")
                for ad in m.get("ai_drafts", []):
                    drafts.append({
                        "course": c_name,
                        "meeting": p_num,
                        "prompt": ad.get("prompt"),
                        "draft": ad.get("draft")
                    })
    except Exception:
        pass
    return drafts
