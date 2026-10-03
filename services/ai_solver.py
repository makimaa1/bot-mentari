import os
import re
from pathlib import Path
from dotenv import load_dotenv

# Muat environment variable dari .env di root proyek
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

_client = None

import time

# Model prioritas dan cadangan yang valid dan aktif di Google GenAI
FALLBACK_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
]

_model_cooldowns = {}


def get_available_models(preferred_model: str = "gemini-3.5-flash-lite") -> list:
    """Mengembalikan daftar model yang siap pakai tanpa yang sedang terkena limit kuota (429)."""
    now = time.time()
    ordered = [preferred_model] + [m for m in FALLBACK_MODELS if m != preferred_model]
    ready = [m for m in ordered if _model_cooldowns.get(m, 0) < now]
    return ready if ready else ordered


def get_gemini_client():
    """Menginisialisasi dan mengembalikan instance client Google GenAI jika API key tersedia."""
    global _client
    if _client is not None:
        return _client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        _client = genai.Client(api_key=api_key)
        return _client
    except ImportError:
        return None


def generate_content_with_fallback(client, prompt: str, preferred_model: str = "gemini-3.5-flash-lite") -> str:
    """Mengirim prompt ke Gemini dengan mekanisme failover ke model cadangan jika server 503/429/sibuk."""
    models_to_try = get_available_models(preferred_model)
    last_error = None

    for m in models_to_try:
        try:
            response = client.models.generate_content(
                model=m,
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str:
                _model_cooldowns[m] = time.time() + 300  # Cooldown 5 menit untuk model yang habis kuota
            elif "404" in err_str or "not found" in err_str:
                _model_cooldowns[m] = time.time() + 86400  # Nonaktifkan model 404
            continue

    if last_error:
        raise last_error
    return "Tidak ada respons dari model AI."


def solve_multiple_choice(question: str, options: list[str], model: str = "gemini-3.5-flash-lite") -> dict:
    """
    Menganalisis soal kuis pilihan ganda menggunakan model penalaran
    dan mengembalikan opsi yang paling tepat beserta indeksnya untuk diklik secara otomatis di browser.
    
    Args:
        question: Teks soal kuis.
        options: Daftar opsi jawaban (contoh: ['A. Opsi 1', 'B. Opsi 2', ...]).
        model: Model Gemini yang digunakan (default: gemini-3.5-flash-lite).
        
    Returns:
        Dict: {"index": int, "answer": str, "reason": str, "raw": str}
    """
    client = get_gemini_client()
    
    if not client:
        return {
            "index": 0,
            "answer": options[0] if options else "A",
            "reason": "Mode simulasi otomatis (Setel GEMINI_API_KEY di file .env untuk analisis AI real-time).",
            "raw": f"Jawaban: {options[0] if options else 'A'}\nAlasan: Mode simulasi"
        }
    
    formatted_options = "\n".join(f"[{i}] {opt}" for i, opt in enumerate(options))
    prompt = f"""Kamu adalah Profesor dan Pakar Utama dalam bidang Teknik Informatika, Sistem Informasi, Rekayasa Perangkat Lunak, dan Manajemen Proyek TI.
Berikut adalah soal kuis pilihan ganda akademik:

[PERTANYAAN]
{question}

[DAFTAR PILIHAN JAWABAN]
{formatted_options}

Tugasmu:
1. Pikirkan secara mendalam (*step-by-step reasoning*) konsep ilmiah dan definisi baku yang ditanyakan.
2. Evaluasi setiap pilihan jawaban satu per satu untuk menemukan mana yang paling akurat sesuai kurikulum akademik teknik informatika.
3. Tentukan SATU indeks jawaban yang paling tepat (0, 1, 2, 3, atau 4).

WAJIB mengembalikan jawaban dalam format persis seperti ini tanpa kata pembuka lain:
INDEX: <angka indeks 0/1/2/3/4>
JAWABAN: <teks lengkap dari opsi yang dipilih>
ALASAN: <penjelasan ilmiah 1-2 kalimat mengapa opsi ini adalah jawaban yang benar>
"""

    try:
        raw_text = generate_content_with_fallback(client, prompt, preferred_model=model)
        
        idx_match = re.search(r'INDEX:\s*(\d+)', raw_text, re.IGNORECASE)
        ans_match = re.search(r'JAWABAN:\s*(.+)', raw_text, re.IGNORECASE)
        reas_match = re.search(r'ALASAN:\s*(.+)', raw_text, re.IGNORECASE)
        
        chosen_idx = int(idx_match.group(1)) if idx_match else 0
        chosen_ans = ans_match.group(1).strip() if ans_match else (options[chosen_idx] if options else "")
        reason = reas_match.group(1).strip() if reas_match else "Dipilih berdasarkan analisis konsep teknologi dan best practice."

        # Verifikasi silang akurat:
        if options:
            matched_by_letter = False
            # 1. Cek kecocokan huruf awalan (A, B, C, D, E) antara chosen_ans dan opsi
            ans_letter_match = re.match(r'^([A-Ea-e])[\.\)\s]', chosen_ans)
            if ans_letter_match:
                target_letter = ans_letter_match.group(1).upper()
                for o_i, opt in enumerate(options):
                    opt_letter_match = re.match(r'^([A-Ea-e])[\.\)\s]', opt)
                    if opt_letter_match and opt_letter_match.group(1).upper() == target_letter:
                        chosen_idx = o_i
                        chosen_ans = opt
                        matched_by_letter = True
                        break

            # 2. Jika tidak cocok huruf, cek exact text match (tanpa awalan A/B/C/D)
            if not matched_by_letter:
                cleaned_ans = re.sub(r'^[A-Ea-e][\.\)\s]+', '', chosen_ans).strip().lower()
                for o_i, opt in enumerate(options):
                    cleaned_opt = re.sub(r'^[A-Ea-e][\.\)\s]+', '', opt).strip().lower()
                    if cleaned_ans == cleaned_opt:
                        chosen_idx = o_i
                        chosen_ans = opt
                        matched_by_letter = True
                        break

            # 3. Validasi batas indeks
            if chosen_idx >= len(options):
                chosen_idx = 0
            if not chosen_ans:
                chosen_ans = options[chosen_idx]
            
        return {
            "index": chosen_idx,
            "answer": chosen_ans,
            "reason": reason,
            "raw": raw_text
        }
    except Exception as e:
        return {
            "index": 0,
            "answer": options[0] if options else "A",
            "reason": f"Gagal memanggil API Gemini: {e}",
            "raw": str(e)
        }


FEMALE_LECTURER_KEYWORDS = ["fifi julfiati"]  # Satu-satunya dosen perempuan (Kecakapan Antar Personal). Dosen lain laki-laki.


def get_lecturer_honorific(course_name: str = "", dosen_name: str = "") -> str:
    """Menentukan sapaan Pak/Bu. Default 'Pak'; hanya dosen yang terdaftar perempuan yang disapa 'Bu'."""
    name_check = f"{course_name} {dosen_name}".lower()
    if any(k in name_check for k in FEMALE_LECTURER_KEYWORDS):
        return "Bu"
    return "Pak"


def draft_forum_discussion(
    topic: str,
    context: str = "",
    course_name: str = "",
    dosen_name: str = "",
    class_questions: list = None,
    model: str = "gemini-3.5-flash-lite"
) -> str:
    """
    Menghasilkan rangkaian 3 tanggapan forum diskusi (Fordis) Mentari LMS UNPAM
    yang sangat natural, mengalir, tidak kaku seperti AI, sesuai kebiasaan asli mahasiswa (Sofyan Agung):

    1. Respon 1: Menjawab pertanyaan dosen ('Izin menjawab Pak/Bu,' + enter + narasi 1-2 paragraf)
    2. Respon 2: Mengajukan pertanyaan materi ('Izin bertanya Pak/Bu,' + enter + pertanyaan kritis)
    3. Respon 3: Menjawab pertanyaan ASLI salah satu teman sekelas (diambil dari postingan forum)
    """
    client = get_gemini_client()
    honorific = get_lecturer_honorific(course_name, dosen_name)
    dosen_info = f"Dosen Pengampu: {dosen_name} (Sapaan: {honorific})" if dosen_name else f"Sapaan Dosen: {honorific}"
    class_questions = class_questions or []

    if not client:
        return (
            f"--- RESPON 1 (Menjawab Pertanyaan Dosen) ---\n"
            f"Izin menjawab {honorific},\n\n"
            f"Mengenai topik {topic[:60]}, pemahaman mendalam tentang konsep dasar dan implementasi arsitektur sistem "
            f"sangat penting untuk mengoptimalkan kinerja komputasi dan meminimalisir bottleneck transfer data.\n\n"
            f"--- RESPON 2 (Bertanya ke Dosen) ---\n"
            f"Izin bertanya {honorific},\n\n"
            f"Terkait penerapan konsep ini pada skala industri saat ini, kendala teknis apa yang paling sering "
            f"dihadapi dan bagaimana strategi arsitektur yang paling efektif untuk mengatasinya?\n\n"
            f"--- RESPON 3 (Menjawab Teman) ---\n"
            f"Izin menjawab,\n\n"
            f"Menanggapi diskusi rekan sekalian, saya sepakat bahwa pemilihan komponen dan pemahaman alur data "
            f"sangat menentukan kestabilan sistem secara keseluruhan."
        )

    context_str = f"\nKonteks Tambahan: {context}\n" if context else ""
    if class_questions:
        cq = "\n".join(f"[{i+1}] {q}" for i, q in enumerate(class_questions))
        friend_block = (f"Postingan TEMAN SEKELAS yang berisi pertanyaan (diambil asli dari forum):\n{cq}\n\n"
                        f"Untuk RESPON 3: pilih SATU pertanyaan teman yang paling bisa dijawab dengan baik, lalu jawab "
                        f"pertanyaan ITU SECARA SPESIFIK. Sebut nama teman tersebut secara natural di kalimat awal isi jawaban "
                        f"(contoh: 'Untuk pertanyaan Naufal tadi, ...').")
    else:
        friend_block = ("Belum ada pertanyaan teman yang terbaca di forum. Untuk RESPON 3 buat tanggapan umum yang "
                        "membantu teman sekelas terkait soal dosen.")
    prompt = f"""Kamu adalah SOFYAN AGUNG, mahasiswa semester 7 Program Studi Teknik Informatika UNPAM (Universitas Pamulang, Kelas 07TPLP003) yang sedang berpartisipasi aktif dalam forum diskusi e-learning Mentari LMS.

Topik / Soal Diskusi ASLI dari Dosen:
\"\"\"{topic}\"\"\"{context_str}
Mata Kuliah: {course_name if course_name else 'Teknik Informatika UNPAM'}
{dosen_info}

{friend_block}

TUGASMU:
Susunlah 3 RESPON DISKUSI LENGKAP dengan gaya bahasa yang SANGAT NATURAL, luwes, santun, cerdas, mengalir layaknya ketikan mahasiswa asli, dan SAMA SEKALI TIDAK KELIHATAN SEPERTI JAWABAN AI (hindari salam bertele-tele seperti "Selamat pagi/siang rekan mahasiswa sekalian", hindari format kaku poin-poin robotik, hindari kata-kata klise AI).

ATURAN ISI:
- RESPON 1 harus benar-benar menjawab SOAL ASLI di atas. Jika soal memiliki beberapa nomor pertanyaan, jawab seluruhnya secara runtut dalam narasi paragraf (boleh menyebut "untuk pertanyaan pertama..., kedua..."), bukan poin-poin kaku. Panjang boleh lebih dari 2 paragraf bila soal memuat banyak nomor.
- RESPON 2 berupa 1 pertanyaan kritis terkait materi yang relevan dengan soal (bukan pertanyaan yang sudah dijawab di materi).
- RESPON 3 menjawab pertanyaan teman sesuai aturan di atas.

ATURAN STRUKTUR & AWALAN KALIMAT (WAJIB DIIKUTI DENGAN PERSIS):
DILARANG KERAS menambahkan kalimat pengantar atau basa-basi apapun di awal (seperti 'Berikut adalah...', 'Tentu,...'). Langsung mulai tepat dari '--- RESPON 1 (Menjawab Pertanyaan Dosen) ---'.

--- RESPON 1 (Menjawab Pertanyaan Dosen) ---
Izin menjawab {honorific},

[Isi jawaban naratif terhadap soal dosen.]

--- RESPON 2 (Bertanya Mengenai Materi yang Kurang Dipahami) ---
Izin bertanya {honorific},

[Isi 1 pertanyaan cerdas, kritis, dan realistis dengan gaya bertanya mahasiswa yang tulus.]

--- RESPON 3 (Menjawab Pertanyaan Rekan Mahasiswa) ---
Izin menjawab,

[Isi jawaban untuk pertanyaan teman yang dipilih, 1 paragraf, nada bersahabat dan kolaboratif.]"""

    try:
        raw_res = generate_content_with_fallback(client, prompt, preferred_model=model)
        if "--- RESPON 1" in raw_res:
            raw_res = raw_res[raw_res.index("--- RESPON 1"):]
        return raw_res.strip()
    except Exception as e:
        return (
            f"--- RESPON 1 (Menjawab Pertanyaan Dosen) ---\n"
            f"Izin menjawab {honorific},\n\n"
            f"Mengenai materi {topic[:60]}, pemahaman alur kerja dan integrasi komponen merupakan fondasi utama "
            f"dalam rekayasa sistem komputer modern. (Catatan AI: {e})\n\n"
            f"--- RESPON 2 (Bertanya ke Dosen) ---\n"
            f"Izin bertanya {honorific},\n\n"
            f"Bagaimana perbandingan efisiensi pendekatan ini jika diterapkan pada infrastruktur modern saat ini?\n\n"
            f"--- RESPON 3 (Menjawab Teman) ---\n"
            f"Izin menjawab,\n\n"
            f"Sepakat dengan pendapat rekan sekalian, optimalisasi arsitektur selalu membutuhkan keseimbangan antara performa dan sumber daya."
        )


def parse_forum_draft_responses(raw_draft: str) -> dict:
    """Memecah teks draft fordis menjadi 3 respon terpisah yang siap diposting ke web LMS Mentari."""
    res1, res2, res3 = "", "", ""
    parts = re.split(r'---\s*RESPON\s*\d+[^\n]*---', raw_draft)
    cleaned_parts = [p.strip() for p in parts if p.strip()]

    if len(cleaned_parts) >= 3:
        res1 = cleaned_parts[0]
        res2 = cleaned_parts[1]
        res3 = cleaned_parts[2]
    elif len(cleaned_parts) == 2:
        res1 = cleaned_parts[0]
        res2 = cleaned_parts[1]
    elif len(cleaned_parts) == 1:
        res1 = cleaned_parts[0]

    # Deteksi nama teman yang ditargetkan dari respon 3 (contoh: 'Untuk pertanyaan Naufal tadi...')
    target_friend = "teman"
    m = re.search(r'(?:pertanyaan|tanggapan|rekan)\s+([A-Z][a-z]+|[A-Z]{3,})', res3)
    if m:
        target_friend = m.group(1)

    return {
        "respon_1": res1,
        "respon_2": res2,
        "respon_3": res3,
        "target_friend": target_friend
    }

