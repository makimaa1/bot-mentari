import json

with open("data/mentari_master_audit.json", encoding="utf-8") as f:
    audit = json.load(f)

for c in audit:
    print("=" * 65)
    print("COURSE:", c["course_name"])
    for m in c["meetings"]:
        p = m["pertemuan"]
        pre = m.get("pretest")
        post = m.get("posttest")
        kue = m.get("kuesioner")
        f = m.get("forum")
        
        has_pre = bool(pre and pre.get("buttons"))
        has_post = bool(post and post.get("buttons"))
        has_kue = bool(kue and kue.get("buttons"))
        has_for = bool(f and f.get("buttons") and "belum tersedia" not in f.get("title","").lower())
        
        pre_title = pre.get("title", "") if pre else ""
        is_locked = "selesaikan" in pre_title.lower() or not (has_pre or has_post or has_kue or has_for)
        
        if not is_locked:
            print(f"  P-{p:02d} [UNLOCKED / AKTIF]: Pre={has_pre} | Post={has_post} | Kuesioner={has_kue} | Fordis={has_for}")
        elif has_pre or has_post or has_kue or has_for:
            print(f"  P-{p:02d} [LOCKED]: Pre={has_pre} | Post={has_post} | Kuesioner={has_kue} | Fordis={has_for}")
