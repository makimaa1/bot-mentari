import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from master_scraper import classify_card
from pipeline_runner import (
    extract_own_quiz_section,
    check_quiz_completion_status,
    resolve_course_key,
    COURSES
)

def run_all_tests():
    print("=" * 70)
    print("  UNIT TEST: PRETEST VS POSTTEST DETECTION & TARGETING INTEGRITY")
    print("=" * 70)

    total = 0
    passed = 0

    def assert_eq(test_name, actual, expected):
        nonlocal total, passed
        total += 1
        if actual == expected:
            print(f"[PASS] {test_name}")
            passed += 1
        else:
            print(f"[FAIL] {test_name}: Expected {repr(expected)}, got {repr(actual)}")

    # 1. Test classify_card on edge cases
    assert_eq(
        "classify_card: Pretest title with restriction mention",
        classify_card("Pretest", "Silakan selesaikan Pretest ini sebelum besok", ["QUIZ"]),
        "PRETEST"
    )
    assert_eq(
        "classify_card: Posttest title with Pretest prerequisite mention",
        classify_card("Posttest", 'Silakan selesaikan "Pretest" terlebih dahulu', ["QUIZ"]),
        "POSTTEST"
    )
    assert_eq(
        "classify_card: Standard Posttest",
        classify_card("Posttest", "PERTEMUAN 1 | QUIZ", ["QUIZ"]),
        "POSTTEST"
    )
    assert_eq(
        "classify_card: Standard Pretest",
        classify_card("Pretest", "PERTEMUAN 1 | QUIZ", ["QUIZ"]),
        "PRETEST"
    )

    # 2. Test resolve_course_key
    assert_eq(
        "resolve_course_key: Etika Profesi",
        resolve_course_key("etika profesi")[0],
        "7"
    )
    assert_eq(
        "resolve_course_key: Keamanan Jaringaan (typo)",
        resolve_course_key("keamanan jaringaan")[0],
        "3"
    )
    assert_eq(
        "resolve_course_key: Arsitektur",
        resolve_course_key("arsitektur dan organisasi komputer")[0],
        "2"
    )
    assert_eq(
        "resolve_course_key: Manajemen Proyek Informatika",
        resolve_course_key("manajemen proyek informatika")[0],
        "1"
    )

    # 3. Test check_quiz_completion_status
    pretest_sample_done = """
    Detail Quiz
    Mahasiswa: Sofyan
    Status Quiz: Sudah Mengerjakan Quiz
    Grade: 80
    Waktu Penyelesaian: 10 menit
    List Data Peserta:
    1. Budi Grade: 100
    """
    is_done, score = check_quiz_completion_status(extract_own_quiz_section(pretest_sample_done))
    assert_eq("Completion status: Pretest done", is_done, True)
    assert_eq("Score extraction: Pretest score is 80", score, "80")

    posttest_sample_not_done = """
    Detail Quiz
    Mahasiswa: Sofyan
    Status Quiz: Belum Mengerjakan Quiz
    List Data Peserta:
    1. Ani Grade: 90
    """
    is_done_post, score_post = check_quiz_completion_status(extract_own_quiz_section(posttest_sample_not_done))
    assert_eq("Completion status: Posttest not done", is_done_post, False)
    assert_eq("Score extraction: Posttest score is None", score_post, None)

    # 4. Simulation of card targeting logic
    # Simulate cards found inside meeting 1 of Etika Profesi
    cards = [
        {"title": "Pretest", "text": "Pretest\nPERTEMUAN 1 | QUIZ", "btn": "QUIZ", "is_pre": True},
        {"title": "Materi Slide", "text": "Power Point\nSlide Pertemuan 1", "btn": "FILE", "is_pre": False},
        {"title": "Forum Diskusi", "text": "Forum Diskusi\nTopik Pertemuan 1", "btn": "FORUM", "is_pre": False},
        {"title": "Posttest", "text": 'Posttest\nSilakan selesaikan "Pretest" terlebih dahulu', "btn": "QUIZ", "is_pre": False},
    ]

    def simulate_find_quiz(target_type):
        for c in cards:
            lines = c["text"].splitlines()
            first_l = lines[0].lower()
            top_txt = " ".join(lines[:3]).lower()
            full_lower = c["text"].lower()

            if target_type == "PRETEST":
                if any(k in top_txt for k in ["pretest", "pre-test"]) and not any(k in first_l for k in ["posttest", "post-test"]):
                    return c["title"]
            elif target_type == "POSTTEST":
                is_post_title = any(k in top_txt for k in ["posttest", "post-test"])
                is_locked_post = "selesaikan" in full_lower and "pretest" in full_lower
                is_not_pre = not any(first_l == k for k in ["pretest", "pre-test"])
                if (is_post_title or is_locked_post) and is_not_pre:
                    return c["title"]
        return None

    assert_eq("Simulated Targeting: PRETEST targets Pretest", simulate_find_quiz("PRETEST"), "Pretest")
    assert_eq("Simulated Targeting: POSTTEST targets Posttest directly", simulate_find_quiz("POSTTEST"), "Posttest")

    print("\n" + "=" * 70)
    print(f"  TOTAL TESTS: {total} | PASSED: {passed} | FAILED: {total - passed}")
    print("=" * 70)
    if passed == total:
        print(">>> ALL TARGETING INTEGRITY TESTS PASSED! <<<")
    else:
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
