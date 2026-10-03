# Bot Mentari

Bot Python untuk membaca data Mentari LMS, membuat draf fordis, menjalankan pipeline pembelajaran, dan menerima perintah melalui WhatsApp/Fonnte. Proyek ini masih memakai daftar delapan mata kuliah kelas 07TPLP003 semester 20261 di kode.

## Menjalankan

Gunakan Python 3.10 atau lebih baru dan Google Chrome. Dari folder proyek:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Isi `.env` mengikuti nama variabel pada `.env.example`. Pertahankan `.env` dan folder `data` di komputer sendiri; keduanya diabaikan Git. `WEBHOOK_SECRET` wajib untuk server WhatsApp, dan `MY_WA_NUMBER` membatasi pengirim yang boleh mengakses bot, termasuk di grup.

Sesi LMS terpisah dari API key di `.env`. Jika `data/auth.json` belum ada atau Cloudflare/login menolak sesi lama:

```powershell
.\.venv\Scripts\python.exe save_auth.py
```

Login di jendela browser, selesaikan pemeriksaan yang ditampilkan situs, lalu tekan ENTER di terminal. Skrip menyimpan sesi setelah dashboard dikenali. Jangan membagikan `auth.json` karena berisi akses akun.

Untuk WhatsApp, buka `jalankan_wa_agent.bat`. Launcher memilih Python di `.venv` jika tersedia. Jika memasang webhook secara manual di Fonnte, gunakan `https://<alamat-tunnel>/webhook?token=<WEBHOOK_SECRET>`. Bila `cloudflared.exe` ada, server menyinkronkan URL bertoken secara otomatis.

Untuk memperbarui data lokal:

```powershell
.\.venv\Scripts\python.exe master_scraper.py
```

## Fordis

Contoh perintah WhatsApp: `kerjakan fordis arkom p7`. Contoh menjalankan langsung:

```powershell
.\.venv\Scripts\python.exe pipeline_runner.py 2 7 --step fordis
```

Perintah ini mengirim balasan ke LMS. Pipeline membaca soal lengkap dan balasan yang sudah ada, menyimpan tiga bagian draf, lalu mengirim bagian yang masih diperlukan. Balasan ke teman ditujukan ke postingan yang digunakan saat membuat draf. Jika tidak ada pertanyaan teman, bagian ketiga menjadi tanggapan umum pada topik dosen.

Keberhasilan diperiksa dari balasan milik mahasiswa setelah halaman dimuat ulang. Jika proses terputus, draf yang sama dipakai kembali dan teks yang sudah tercatat dilewati. Status yang belum dapat diverifikasi dilaporkan sebagai gagal. Periksa LMS sebelum mengulang kegagalan pengiriman yang statusnya belum pasti.

`--step pretest`, `posttest`, `materi`, `kuesioner`, dan `all` juga tersedia. Kuesioner masih diisi sebagai draf tanpa submit otomatis; ringkasannya menyebutkan hal tersebut. `auto` atau `all` untuk target pertemuan memerlukan data audit lokal, dan tidak lagi memilih pertemuan 1–2 sebagai cadangan.

## Pengujian

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Suite ini memakai data tiruan dan tidak mengirim WhatsApp, memakai kuota Gemini, atau mengubah LMS. Skrip lama dalam `scratch/` dan `scratch_*.py` berbeda: sebagian mengakses akun dan mengirim balasan, sehingga tidak dijalankan oleh suite ini.

Lihat [AUDIT.md](AUDIT.md) untuk temuan dan batas verifikasi.
