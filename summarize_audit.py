import sys
import json
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

audit_path = Path("data/mentari_master_audit.json")
with open(audit_path, encoding="utf-8") as f:
    data = json.load(f)

print("=" * 80)
print("     MENTARI LMS - REKAPITULASI AUDIT PEMBELAJARAN 8 MATA KULIAH")
print("=" * 80)
total_meetings = sum(len(c["meetings"]) for c in data)
print(f"Total Mata Kuliah Terdaftar : {len(data)}")
print(f"Total Sesi Pertemuan        : {total_meetings}")
print("-" * 80)

for idx, c in enumerate(data, 1):
    m_list = c["meetings"]
    pre_cnt = sum(1 for m in m_list if m.get("pretest"))
    for_cnt = sum(1 for m in m_list if m.get("forum"))
    post_cnt = sum(1 for m in m_list if m.get("posttest"))
    kues_cnt = sum(1 for m in m_list if m.get("kuesioner"))
    tugas_cnt = sum(len(m.get("tugas", [])) for m in m_list)
    materi_cnt = sum(len(m.get("materi", [])) for m in m_list)
    
    print(f"{idx}. {c['course_name']} ({len(m_list)} Pertemuan)")
    print(f"   📚 Modul/PPT   : {materi_cnt} file materi")
    print(f"   📝 Pre-test    : {pre_cnt} pertemuan")
    print(f"   💬 Fordis      : {for_cnt} pertemuan")
    print(f"   🎯 Post-test   : {post_cnt} pertemuan")
    print(f"   📋 Kuesioner   : {kues_cnt} pertemuan")
    print(f"   📌 Tugas       : {tugas_cnt} penugasan")
    print("-" * 80)
