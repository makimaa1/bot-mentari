import json

with open("data/mentari_master_audit.json", encoding="utf-8") as f:
    audit = json.load(f)

for c in audit:
    print("=" * 60)
    print("COURSE:", c["course_name"])
    for m in c["meetings"]:
        p = m["pertemuan"]
        pre = m.get("pretest")
        post = m.get("posttest")
        kue = m.get("kuesioner")
        
        pre_btns = pre.get("buttons") if pre else None
        post_btns = post.get("buttons") if post else None
        kue_btns = kue.get("buttons") if kue else None
        
        pre_desc = pre.get("description", "") if pre else ""
        pre_title = pre.get("title", "") if pre else ""

        print(f"P-{p:02d}: pre={pre_title[:20]} | btns={pre_btns} | post={post_btns} | kue={kue_btns} | desc={pre_desc[:30]}")
