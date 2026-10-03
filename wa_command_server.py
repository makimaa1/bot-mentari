import os
import sys
import json
import re
import time
import threading
import subprocess
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from dotenv import load_dotenv

# Reconfigure console output for Windows UTF-8 safety
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

from services.agent_bot import get_agent_response
from services.wa_notifier import send_wa_message

PORT = int(os.getenv("WEBHOOK_PORT", 5000))
MY_WA_NUMBER = os.getenv("MY_WA_NUMBER", "").strip()
CLOUDFLARED_PATH = BASE_DIR / "cloudflared.exe"

tunnel_proc = None
public_tunnel_url = ""


def normalize_phone(phone: str) -> str:
    """Mengambil angka inti nomor HP tanpa kode negara 62/0 atau suffix WhatsApp."""
    clean = str(phone).split("@")[0] if "@" in str(phone) else str(phone)
    p = "".join(filter(str.isdigit, clean))
    if p.startswith("62"):
        p = p[2:]
    elif p.startswith("0"):
        p = p[1:]
    return p


class FonnteWebhookHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Format logging bersih di konsol
        sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] {format % args}\n")

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        res = {
            "status": "online",
            "bot": "Mentari LMS WhatsApp AI Agent",
            "model": "Google Gemini 3.8 Flash (Fallback: 3.6 / 3.7 / 3.5)",
            "webhook_path": "/webhook"
        }
        self.wfile.write(json.dumps(res, indent=2).encode("utf-8"))

    def do_POST(self):
        """Menerima pesan masuk dari Webhook WhatsApp Fonnte."""
        # Muat ulang .env secara dinamis agar perubahan nomor HP langsung aktif tanpa restart server
        load_dotenv(dotenv_path=env_path, override=True)

        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8", errors="ignore")
        content_type = self.headers.get("Content-Type", "")

        sender = ""
        user_message = ""
        member = ""

        # Parsing payload (JSON atau form urlencoded)
        if "application/json" in content_type:
            try:
                body = json.loads(post_data)
                sender = body.get("sender", "")
                user_message = body.get("message", "")
                member = body.get("member", "")
            except Exception as e:
                print(f"[!] Error parse JSON: {e}")
        else:
            try:
                parsed = urllib.parse.parse_qs(post_data)
                sender = parsed.get("sender", [""])[0]
                user_message = parsed.get("message", [""])[0]
                member = parsed.get("member", [""])[0]
            except Exception as e:
                print(f"[!] Error parse urlencoded: {e}")

        # Balas HTTP 200 OK ke server Fonnte agar webhook tidak timeout
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"status": True}).encode("utf-8"))

        if not user_message:
            return

        # Ambil daftar nomor yang diizinkan dari .env
        allowed_raw = os.getenv("MY_WA_NUMBER", "").strip()
        allowed_numbers = [normalize_phone(num) for num in re.split(r'[,;\s]+', allowed_raw) if num.strip()]

        # Deteksi apakah pesan berasal dari Grup WhatsApp
        is_group = "@g.us" in sender
        actual_sender = member if member else sender
        clean_actual = normalize_phone(actual_sender)
        is_owner = any(allowed in clean_actual or clean_actual in allowed for allowed in allowed_numbers if allowed) if allowed_numbers else True

        # Jika pesan dari grup:
        if is_group:
            # Periksa apakah pesan memang ditujukan ke bot:
            # 1. Mengandung tag mention (@...), ATAU
            # 2. Mengandung kata pemicu (bot, !bot, /bot, mentari), ATAU
            # 3. Dikirim oleh pemilik bot (owner)
            has_mention = "@" in user_message
            has_bot_keyword = any(kw in user_message.lower() for kw in ["bot", "!bot", "/bot", "mentari", "tanya"])

            if not (has_mention or has_bot_keyword or is_owner):
                # Obrolan biasa antar anggota grup, abaikan agar tidak spam & tidak boros kuota
                return

            print(f"\n👥 [CHAT GRUP DITERIMA: {sender}]")
            print(f"   Dari Member: {actual_sender}")
            print(f"   Pesan Asli : {user_message}")

            # Bersihkan tag mention (misal @166873052217409) dari teks pertanyaan
            clean_query = re.sub(r'@\d+', '', user_message).strip()
            clean_query = re.sub(r'^(?:!bot|/bot|bot)\s*[:,\-]?\s*', '', clean_query, flags=re.IGNORECASE).strip()
            if not clean_query:
                clean_query = "halo"
        else:
            # Pesan Personal (Japri):
            # Validasi keamanan jika MY_WA_NUMBER diatur
            if allowed_numbers and not is_owner:
                print(f"[!] Pesan Japri dari nomor tidak dikenal ({clean_actual}). Diabaikan untuk keamanan.")
                print(f"    (Nomor terdaftar di .env: {allowed_raw})")
                return

            print("\n" + "=" * 70)
            print(f"📩 [PESAN PRIBADI MASUK DARI WHATSAPP]")
            print(f"   Pengirim : {sender}")
            print(f"   Isi Pesan: {user_message}")
            print("=" * 70)
            clean_query = user_message

        # Target pengiriman balasan:
        # Jika grup kirim ke ID grup (sender), jika personal kirim ke sender (tanpa @c.us)
        if is_group:
            reply_target = sender
        else:
            reply_target = sender.split("@")[0]

        # Jalankan pemrosesan pesan via thread terpisah agar webhook tidak terblokir
        threading.Thread(
            target=self.process_and_reply,
            args=(clean_query, reply_target, is_group, actual_sender),
            daemon=True
        ).start()

    def process_and_reply(self, user_message: str, reply_target: str, is_group: bool = False, member: str = ""):
        """Memproses query via Gemini Agent dan mengirimkan jawaban ke WA."""
        print("[*] Agen AI sedang menganalisis pesan dan memeriksa data Mentari...")
        try:
            # Muat ulang services.agent_bot secara dinamis agar pembaruan data/kode langsung aktif
            import importlib
            import services.agent_bot
            importlib.reload(services.agent_bot)

            # Gunakan reply_target sebagai session_id agar riwayat obrolan bersambung per kontak/grup
            session_key = reply_target if reply_target else "default_wa"
            agent_reply = services.agent_bot.get_agent_response(user_message, session_id=session_key)

            # Jika di grup, tambahkan tag atau salam singkat ke pengirim
            if is_group and member:
                member_clean = member.split("@")[0]
                agent_reply = f"Halo @{member_clean} 👋\n\n{agent_reply}"

            print(f"[V] Respons AI Agent siap ({len(agent_reply)} karakter).")
            print(f"[*] Mengirim balasan ke WhatsApp {reply_target}...")
            send_wa_message(agent_reply, target=reply_target)
        except Exception as e:
            print(f"[!] Gagal menghasilkan balasan: {e}")
            err_msg = f"Maaf, ada kendala saat memproses permintaanmu: {e}"
            send_wa_message(err_msg, target=reply_target)


def start_cloudflared_tunnel(port: int):
    """Menjalankan Cloudflare Tunnel otomatis dan mengambil URL HTTPS publiknya."""
    global tunnel_proc, public_tunnel_url
    if not CLOUDFLARED_PATH.exists():
        return None

    cmd = [str(CLOUDFLARED_PATH), "tunnel", "--url", f"http://127.0.0.1:{port}"]
    tunnel_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    start_time = time.time()
    while time.time() - start_time < 15:
        line = tunnel_proc.stderr.readline()
        if not line:
            time.sleep(0.1)
            continue
        m = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
        if m:
            public_tunnel_url = m.group(0)
            return public_tunnel_url
    return None


def run_cli_test_mode():
    """Mode interaktif pengujian di terminal tanpa perlu koneksi webhook."""
    print("=" * 75)
    print("      MENTARI LMS - AI AGENT CLI TESTING ENVIRONMENT")
    print("=" * 75)
    print("[*] Engine AI: Google Gemini 3.8 Flash (Fallback: 3.6 / 3.7 / 3.5)")
    print("[*] Ketik pertanyaan atau perintahmu (contoh: 'cek fordis manajemen proyek')")
    print("[*] Ketik 'exit' atau 'keluar' untuk mengakhiri sesi.")
    print("=" * 75)

    while True:
        try:
            user_input = input("\nKamu (WhatsApp) >> ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "keluar", "quit", "q"]:
                print("[*] Selesai.")
                break

            print("[*] Mentari Agent sedang berpikir dan memeriksa data...")
            reply = get_agent_response(user_input, session_id="cli_user")
            print("\n" + "-" * 70)
            print(f"Bot Mentari (WhatsApp):\n{reply}")
            print("-" * 70)
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Selesai.")
            break


def run_server():
    print("=" * 80)
    print("🚀 MENGAKTIFKAN SERVER MENTARI LMS WHATSAPP AI AGENT")
    print("=" * 80)
    print(f"[*] Port Lokal         : {PORT}")
    print(f"[*] Nomor Mahasiswa    : {MY_WA_NUMBER if MY_WA_NUMBER else '(Semua nomor diizinkan)'}")
    print(f"[*] Model AI Utama     : Google Gemini 3.8 Flash")

    # Sinkronisasi grup WhatsApp dengan Fonnte agar bot dapat langsung membalas di grup
    try:
        from services.wa_notifier import sync_whatsapp_groups
        print("[*] Menyinkronkan daftar grup WhatsApp ke server Fonnte...")
        sync_res = sync_whatsapp_groups()
        print(f"[V] Status sinkronisasi grup: {sync_res.get('detail', 'OK')}")
    except Exception as e:
        print(f"[!] Sinkronisasi grup dilewati: {e}")

    tunnel_url = None
    if CLOUDFLARED_PATH.exists():
        print("[*] Membuka Cloudflare Tunnel HTTPS publik otomatis...")
        tunnel_url = start_cloudflared_tunnel(PORT)

    if tunnel_url:
        webhook_public = f"{tunnel_url}/webhook"
        print("\n" + "=" * 80)
        print("🔗 URL WEBHOOK PUBLIK TERBENTUK:")
        print(f"   👉  {webhook_public}")
        print("=" * 80)

        # Sinkronisasi otomatis ke dashboard Fonnte via API
        print("[*] Menyinkronkan Webhook ke server Fonnte secara otomatis...")
        try:
            from services.wa_notifier import update_fonnte_webhook
            res_up = update_fonnte_webhook(webhook_public)
            if res_up.get("status"):
                print("🎉 [SUKSES OTOMATIS] Webhook Fonnte telah diatur otomatis oleh bot!")
                print("✨ Kamu TIDAK PERLU lagi buka web Fonnte atau menyalin link manual!")
            else:
                print(f"[!] Info sinkronisasi Fonnte: {res_up.get('reason', res_up)}")
                print(f"    Jika diperlukan, URL manual: {webhook_public}")
        except Exception as e:
            print(f"[!] Sinkronisasi otomatis Fonnte dilewati: {e}")
        print("=" * 80 + "\n")
    else:
        print(f"\n[*] Server aktif secara lokal di: http://localhost:{PORT}/webhook")
        print("[!] Untuk menghubungkan ke Fonnte, gunakan tunneling seperti ngrok atau cloudflared.\n")

    server_address = ("0.0.0.0", PORT)
    httpd = HTTPServer(server_address, FonnteWebhookHandler)
    print("[*] Server siap mendengarkan pesan masuk dari WhatsApp...")
    print("[*] Tekan CTRL+C untuk menghentikan server.\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Menutup server dan koneksi tunnel...")
        if tunnel_proc:
            tunnel_proc.terminate()
        httpd.server_close()
        print("[*] Server berhasil dihentikan.")


if __name__ == "__main__":
    if "--cli" in sys.argv or "-c" in sys.argv:
        run_cli_test_mode()
    else:
        run_server()
