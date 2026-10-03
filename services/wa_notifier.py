import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Reconfigure console output for Windows UTF-8 safety
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Muat environment variable dari .env
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

import requests

FONNTE_TOKEN = os.getenv("FONNTE_TOKEN", "")
MY_WA_NUMBER = os.getenv("MY_WA_NUMBER", "")


def sync_whatsapp_groups() -> dict:
    """Memperbarui daftar grup WhatsApp di server Fonnte agar ID grup dikenali."""
    token = os.getenv("FONNTE_TOKEN", FONNTE_TOKEN)
    if not token:
        return {"status": False, "reason": "FONNTE_TOKEN not set"}
    try:
        res = requests.post("https://api.fonnte.com/fetch-group", headers={"Authorization": token}, timeout=15)
        return res.json()
    except Exception as e:
        return {"status": False, "reason": str(e)}


def update_fonnte_webhook(webhook_url: str) -> dict:
    """
    Memperbarui URL Webhook di dashboard Fonnte secara otomatis via API.
    Pengguna tidak perlu lagi membuka web Fonnte atau menyalin link manual!
    """
    token = os.getenv("FONNTE_TOKEN", FONNTE_TOKEN)
    if not token:
        return {"status": False, "reason": "FONNTE_TOKEN belum diatur di .env"}

    try:
        # Ambil identitas device saat ini dari Fonnte
        dev_res = requests.post("https://api.fonnte.com/device", headers={"Authorization": token}, timeout=10)
        dev_data = dev_res.json()
        if not dev_data.get("status"):
            return {"status": False, "reason": dev_data.get("reason", "Gagal membaca device")}

        device_num = dev_data.get("device", "")
        device_name = dev_data.get("name", "Mentari")

        # Update webhook di Fonnte secara otomatis serta pastikan Auto Read aktif
        payload = {
            "device": device_num,
            "name": device_name,
            "webhook": webhook_url,
            "autoread": "true",
            "personal": "true",
            "group": "true"
        }
        up_res = requests.post("https://api.fonnte.com/update-device", headers={"Authorization": token}, data=payload, timeout=10)
        return up_res.json()
    except Exception as e:
        return {"status": False, "reason": str(e)}


def send_wa_message(message: str, target: str = "") -> dict:
    """
    Mengirim pesan WhatsApp menggunakan gateway Fonnte.
    
    Args:
        message: Teks pesan yang akan dikirim.
        target: Nomor WhatsApp tujuan (format: 08xxx atau 628xxx atau id_grup@g.us).
                Jika kosong, menggunakan MY_WA_NUMBER dari .env.
    """
    token = os.getenv("FONNTE_TOKEN", FONNTE_TOKEN)
    to_number = target if target else os.getenv("MY_WA_NUMBER", MY_WA_NUMBER)

    if to_number and "@" in to_number and not to_number.endswith("@g.us"):
        to_number = to_number.split("@")[0]

    if not token:
        print("[!] FONNTE_TOKEN belum diatur di file .env. Notifikasi WA dilewati.")
        return {"status": False, "reason": "FONNTE_TOKEN not set"}

    if not to_number:
        print("[!] MY_WA_NUMBER belum diatur di file .env. Notifikasi WA dilewati.")
        return {"status": False, "reason": "MY_WA_NUMBER not set"}

    url = "https://api.fonnte.com/send"
    headers = {
        "Authorization": token
    }
    payload = {
        "target": to_number,
        "message": message,
        "countryCode": "62"
    }

    try:
        response = requests.post(url, headers=headers, data=payload, timeout=15)
        res_json = response.json()
        if res_json.get("status"):
            print(f"[V] Notifikasi WhatsApp berhasil terkirim ke {to_number}!")
        else:
            reason = str(res_json.get("reason", res_json))
            # Jika grup belum terdaftar di Fonnte, sinkronisasi otomatis dan kirim ulang
            if "invalid group id" in reason.lower() and to_number.endswith("@g.us"):
                print("[*] ID Grup belum tersinkronisasi di Fonnte. Melakukan sinkronisasi grup otomatis...")
                sync_whatsapp_groups()
                retry_res = requests.post(url, headers=headers, data=payload, timeout=15)
                retry_json = retry_res.json()
                if retry_json.get("status"):
                    print(f"[V] Pesan WhatsApp berhasil terkirim ke grup {to_number} setelah sinkronisasi!")
                    return retry_json
            print(f"[!] Gagal kirim WA: {reason}")
        return res_json
    except Exception as e:
        print(f"[!] Error kirim WA: {e}")
        return {"status": False, "reason": str(e)}


def notify_meeting_completed(course_name: str, meeting_num: int, pretest_status: str, fordis_status: str, posttest_status: str, kuesioner_status: str, target_step: str = "all"):
    """Mengirim ringkasan penyelesaian tahapan pertemuan ke WhatsApp pengguna."""
    clean_step = target_step.lower().strip()
    # Tentukan catatan penutup yang kontekstual dan natural
    def get_footer_note(status_str: str, module_name: str) -> str:
        s_lower = status_str.lower()
        if "terkunci" in s_lower or "prasyarat" in s_lower or "selesaikan" in s_lower:
            return f"⚠️ _Modul {module_name} belum dapat dikerjakan karena masih terkunci oleh prasyarat LMS Mentari._"
        if "sebelumnya" in s_lower:
            return f"ℹ️ _Modul {module_name} telah selesai dikerjakan pada sesi sebelumnya._"
        if "tidak ada" in s_lower:
            return f"ℹ️ _Modul {module_name} tidak ditemukan / tidak tersedia pada pertemuan ini._"
        if "gagal" in s_lower:
            return f"⚠️ _Pengerjaan {module_name} mengalami kendala saat mengakses sistem._"
        return f"✅ _Eksekusi {module_name} telah sukses diproses oleh Bot Mentari LMS._"

    if clean_step in ["posttest", "post", "post-test", "post tes"]:
        footer = get_footer_note(posttest_status, "Post-Test")
        msg = f"""🎓 *[MENTARI LMS NOTIFIKASI OTOMATIS]*

📚 *Mata Kuliah*: {course_name}
📍 *Pertemuan*: Pertemuan {meeting_num}
🎯 *Modul Target*: POST-TEST

📋 *Hasil Pengerjaan*:
• Status/Nilai : {posttest_status}

{footer}
"""
    elif clean_step in ["pretest", "pre", "pre-test", "pre tes"]:
        footer = get_footer_note(pretest_status, "Pre-Test")
        msg = f"""🎓 *[MENTARI LMS NOTIFIKASI OTOMATIS]*

📚 *Mata Kuliah*: {course_name}
📍 *Pertemuan*: Pertemuan {meeting_num}
📝 *Modul Target*: PRE-TEST

📋 *Hasil Pengerjaan*:
• Status/Nilai : {pretest_status}

{footer}
"""
    elif clean_step in ["fordis", "forum", "diskusi"]:
        footer = get_footer_note(fordis_status, "Forum Diskusi")
        msg = f"""🎓 *[MENTARI LMS NOTIFIKASI OTOMATIS]*

📚 *Mata Kuliah*: {course_name}
📍 *Pertemuan*: Pertemuan {meeting_num}
💬 *Modul Target*: FORUM DISKUSI

📋 *Hasil*: {fordis_status}

{footer}
"""
    else:
        msg = f"""🎓 *[MENTARI LMS NOTIFIKASI OTOMATIS]*

📚 *Mata Kuliah*: {course_name}
📍 *Pertemuan*: Pertemuan {meeting_num}

📋 *Rincian Status Belajar*:
1. 📝 *Pre-Test*    : {pretest_status}
2. 📚 *Materi*      : Modul/PPT telah dipindai & diunduh
3. 💬 *Fordis*      : {fordis_status}
4. 🎯 *Post-Test*   : {posttest_status}
5. 📋 *Kuesioner*   : {kuesioner_status}

✅ _Seluruh alur belajar pertemuan ini telah sukses diproses oleh Bot Mentari LMS._
"""
    return send_wa_message(msg)


def format_pending_audit(audit_data: list) -> str:
    """Menyusun teks WhatsApp rapi untuk daftar pertemuan yang belum dikerjakan."""
    msg_lines = [
        "📊 *[DAFTAR MENTARI LMS YANG BELUM SELESAI]*\n",
        "Berikut ringkasan pertemuan yang memerlukan tindakan:\n"
    ]

    has_any_pending = False
    for idx, c in enumerate(audit_data, 1):
        c_name = c["course_name"]
        pending_items = []

        for m in c.get("meetings", []):
            p_num = m["pertemuan"]
            # Periksa jika pretest ada tapi belum nilai, atau fordis ada
            issues = []
            if m.get("pretest"):
                issues.append("Pre-Test")
            if m.get("forum"):
                issues.append("Fordis")
            if m.get("posttest"):
                issues.append("Post-Test")
            if m.get("kuesioner"):
                issues.append("Kuesioner")

            if issues:
                pending_items.append(f"P-{p_num} ({', '.join(issues)})")

        if pending_items:
            has_any_pending = True
            msg_lines.append(f"*{idx}. {c_name}*")
            msg_lines.append(f"   👉 {'; '.join(pending_items[:4])}\n")

    if not has_any_pending:
        return "🎉 *Luar biasa!* Seluruh pertemuan di 8 mata kuliah Anda telah selesai dikerjakan."

    msg_lines.append("💡 *Tips Perintah*: Balas chat ini dengan format:")
    msg_lines.append("`kerjakan <nomor_matkul> <nomor_pertemuan>`")
    msg_lines.append("Contoh: `kerjakan 1 3`")

    return "\n".join(msg_lines)


if __name__ == "__main__":
    test_msg = "Halo! Bot Mentari LMS berhasil tersambung ke WhatsApp Anda."
    print("[*] Menguji pengiriman notifikasi WA...")
    send_wa_message(test_msg)
