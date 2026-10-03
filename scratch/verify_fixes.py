import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.agent_bot import resolve_course_key, find_course_in_audit, COURSES_MAP
from pipeline_runner import extract_own_quiz_section, check_quiz_completion_status

print("=== 1. TEST COURSE RESOLUTION ===")
test_cases = {
    "keamanan jaringaan": ("3", "KEAMANAN KOMPUTER"),
    "keamanan jaringan": ("3", "KEAMANAN KOMPUTER"),
    "keamanan komputer": ("3", "KEAMANAN KOMPUTER"),
    "keamanan": ("3", "KEAMANAN KOMPUTER"),
    "kamjar": ("3", "KEAMANAN KOMPUTER"),
    "arsitektur dan organisasi komputer": ("2", "ARSITEKTUR DAN ORGANISASI KOMPUTER"),
    "arkom": ("2", "ARSITEKTUR DAN ORGANISASI KOMPUTER"),
    "aok": ("2", "ARSITEKTUR DAN ORGANISASI KOMPUTER"),
    "arsitektur": ("2", "ARSITEKTUR DAN ORGANISASI KOMPUTER"),
    "organisasi komputer": ("2", "ARSITEKTUR DAN ORGANISASI KOMPUTER"),
    "jaringan nirkabel": ("4", "JARINGAN NIRKABEL"),
    "jaringan": ("4", "JARINGAN NIRKABEL"),
    "nirkabel": ("4", "JARINGAN NIRKABEL"),
    "jarkom": ("4", "JARINGAN NIRKABEL"),
    "etika profesi": ("7", "ETIKA PROFESI"),
    "etika": ("7", "ETIKA PROFESI"),
    "profesi": ("7", "ETIKA PROFESI"),
    "manajemen proyek informatika": ("1", "MANAJEMEN PROYEK INFORMATIKA"),
    "manpro": ("1", "MANAJEMEN PROYEK INFORMATIKA"),
    "mpi": ("1", "MANAJEMEN PROYEK INFORMATIKA"),
    "kecakapan antar personal": ("5", "KECAKAPAN ANTAR PERSONAL"),
    "kap": ("5", "KECAKAPAN ANTAR PERSONAL"),
    "antar personal": ("5", "KECAKAPAN ANTAR PERSONAL"),
    "testing dan qa perangkat lunak": ("6", "TESTING DAN QA PERANGKAT LUNAK"),
    "qa": ("6", "TESTING DAN QA PERANGKAT LUNAK"),
    "testing": ("6", "TESTING DAN QA PERANGKAT LUNAK"),
    "tqa": ("6", "TESTING DAN QA PERANGKAT LUNAK"),
    "pemrograman web ii": ("8", "PEMROGRAMAN WEB II"),
    "web 2": ("8", "PEMROGRAMAN WEB II"),
    "pemweb": ("8", "PEMROGRAMAN WEB II")
}

all_passed = True
for query, (expected_k, expected_name) in test_cases.items():
    k, name = resolve_course_key(query)
    status = "OK" if (k == expected_k and name == expected_name) else "FAIL"
    if status == "FAIL":
        all_passed = False
    print(f"[{status}] '{query}' -> [{k}] {name}")

assert all_passed, "Some course resolution tests failed!"
print(">> ALL COURSE RESOLUTION TESTS PASSED!")

print("\n=== 2. TEST QUIZ SECTION EXTRACTION (ANTI-LEAK) ===")
mock_body = """
[2] ETIKA PROFESI # 07TPLP003 (Jumat) [P-1]
Posttest - Pertemuan 1
PERTEMUAN 1
Detail Pengerjaan Quiz
Quiz
KERJAKAN QUIZ

List Data Peserta
Cari Peserta (Nama / NIM)
Nama: ABID FADLI JUNAEDI
NIM: 231011400168
Status: Sudah Mengerjakan Quiz
Grade: 80
Waktu Penyelesaian: 1 Menit 17 Detik
"""

own_sec = extract_own_quiz_section(mock_body)
print("Own Section Content:\n", own_sec.strip())
assert "80" not in own_sec, "LEAK DETECTED: Classmate score leaked!"
assert "ABID FADLI" not in own_sec, "LEAK DETECTED: Classmate name leaked!"
assert "Sudah Mengerjakan Quiz" not in own_sec, "LEAK DETECTED: Classmate status leaked!"

is_done, score = check_quiz_completion_status(own_sec)
print(f"Sofyan is_done: {is_done}, score: {score}")
assert is_done is False, "Should be NOT done!"
assert score is None, "Score should be None!"
print(">> ANTI-LEAK TEST PASSED!")

print("\n=== 3. TEST COMPLETED QUIZ DETECTION ===")
mock_completed = """
[2] MANAJEMEN PROYEK INFORMATIKA # 07TPLP003 (Selasa) [P-1]
Posttest - Pertemuan 2
PERTEMUAN 2
Detail Pengerjaan Quiz
Quiz Sudah Mengerjakan Quiz
Grade
60
Selesai
Selasa, 8 September 2026 pukul 6.07 PM
Waktu Penyelesaian
46 Detik
KERJAKAN QUIZ

List Data Peserta
"""
own_completed = extract_own_quiz_section(mock_completed)
is_done_c, score_c = check_quiz_completion_status(own_completed)
print(f"Sofyan is_done: {is_done_c}, score: {score_c}")
assert is_done_c is True, "Should be done!"
assert score_c == "60", f"Score should be 60, got {score_c}"
print(">> COMPLETED QUIZ TEST PASSED!")

print("\n=== 4. TEST AUDIT MATCHER ===")
course_audit = find_course_in_audit("keamanan jaringaan")
assert course_audit is not None, "Course audit should be found"
print("Found in audit:", course_audit.get("course_name"))
assert "KEAMANAN KOMPUTER" in course_audit.get("course_name"), "Should find Keamanan Komputer"
print(">> ALL TESTS PASSED SUCCESSFULLY!")
