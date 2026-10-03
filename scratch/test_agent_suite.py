import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from services.agent_bot import get_agent_response, detect_intent

queries = [
    ("cek mata kuliah etika profesi yang udah pretest pertemuan berapa aja", "test_ep_completed"),
    ("cek tugas yang masih pending", "test_pending"),
    ("halo bro, apa kabar?", "test_chat"),
    ("cek jawaban mentari aku pertemuan 2 fordis manajemen proyek", "test_fordis_ans"),
    ("apa soal yang diberikan dosen di fordis p2 manajemen proyek", "test_fordis_q")
]

for q, sess in queries:
    print("=" * 70)
    intent = detect_intent(q)
    print(f"QUERY  : {q}")
    print(f"INTENT : {intent}")
    print("-" * 70)
    try:
        resp = get_agent_response(q, session_id=sess)
        print("RESPONSE:\n" + resp)
    except Exception as e:
        print(f"ERROR: {e}")
    print("\n")
