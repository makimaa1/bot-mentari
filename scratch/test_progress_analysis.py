import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json

with open("data/mentari_master_audit.json", encoding="utf-8") as f:
    audit = json.load(f)

with open("data/mentari_forum_details.json", encoding="utf-8") as f:
    forum_details = json.load(f)

def analyze_course_progress(audit_data):
    results = {}
    for c in audit_data:
        c_name = c["course_name"]
        results[c_name] = {
            "completed": [],
            "pending": [],
            "locked": []
        }
        for m in c["meetings"]:
            p = m["pertemuan"]
            pre = m.get("pretest")
            post = m.get("posttest")
            kue = m.get("kuesioner")
            f = m.get("forum")

            has_pre_btn = bool(pre and pre.get("buttons"))
            has_post_btn = bool(post and post.get("buttons"))
            has_kue_btn = bool(kue and kue.get("buttons"))
            has_forum = bool(f and f.get("buttons") and "belum tersedia" not in f.get("title", "").lower())
            is_locked = bool(pre and "selesaikan" in pre.get("title", "").lower()) or (not has_pre_btn and not has_post_btn and not has_kue_btn and not has_forum)

            # Cek apakah fordis sudah dijawab mahasiswa
            fordis_answered = False
            for fd in forum_details:
                if fd["course"] == c_name and fd["pertemuan"] == p:
                    fordis_answered = fd.get("has_answered", False)
                    break

            if is_locked:
                results[c_name]["locked"].append(p)
            elif has_post_btn and has_kue_btn:
                # Pre-test, post-test, dan kuesioner terbuka dan telah dilalui
                status_desc = ["Pre-Test ✅", "Post-Test ✅", "Kuesioner ✅"]
                if has_forum:
                    if fordis_answered:
                        status_desc.append("Fordis ✅")
                    else:
                        status_desc.append("Fordis 💬 (Belum Dijawab)")
                results[c_name]["completed"].append((p, status_desc))
            elif has_pre_btn and not has_post_btn:
                # Baru Pre-test yang aktif, belum dikerjakan
                results[c_name]["pending"].append((p, ["Pre-Test ⏳ (Perlu Dikerjakan)"]))
            elif has_forum and not fordis_answered:
                results[c_name]["pending"].append((p, ["Fordis 💬 (Perlu Dijawab)"]))

    return results

res = analyze_course_progress(audit)
for c_name, data in res.items():
    print("=" * 65)
    print("MATA KULIAH:", c_name)
    print("  SUDAH SELESAI:")
    for p, items in data["completed"]:
        print(f"    - Pertemuan {p}: {', '.join(items)}")
    print("  PENDING / PERLU TINDAKAN:")
    for p, items in data["pending"]:
        print(f"    - Pertemuan {p}: {', '.join(items)}")
    print(f"  TERKUNCI / MENUNGGU JADWAL: Pertemuan {data['locked'][:5]}... (Total {len(data['locked'])} pertemuan)")
