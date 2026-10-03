# Audit dan perbaikan Bot Mentari

Tanggal: 3 Oktober 2026. Dasar pemeriksaan: kode dari commit `8cc2f23`, konfigurasi lokal, serta data dan tangkapan layar yang diberikan pengguna. Nilai rahasia tidak dimasukkan ke laporan.

## Struktur proyek

Alur utama adalah WhatsApp/Fonnte → `wa_command_server.py` → `services/agent_bot.py` → `services/task_queue.py` → `pipeline_runner.py` → browser Mentari. `services/ai_solver.py` memanggil Gemini. Data hasil baca disimpan sebagai JSON di `data/`; proyek tidak memakai server database.

`master_scraper.py` memetakan modul per pertemuan. `scrape_gradebooks.py` membaca rekap per mata kuliah, `scrape_meeting_grades.py` membaca nilai per kuis, dan `scrape_forum_live.py` membaca diskusi. `bot.py` menampilkan ringkasan. `explore_courses.py` dan `quiz_runner.py` adalah jalur lama yang masih tersedia. Skrip `scratch` berisi pemeriksaan manual, termasuk beberapa yang dapat menulis ke LMS.

## Bug yang diperbaiki

| Prioritas | Temuan dan bukti | Perubahan |
| --- | --- | --- |
| Tinggi | Tahap fordis hanya membuat draf, menulis JSON, lalu kembali ke kelas. Tidak ada klik Reply atau Kirim di pipeline utama. | `services/forum.py` mengirim bagian draf yang diperlukan, memilih postingan dosen/teman, memverifikasi balasan setelah muat ulang, dan memperbarui cache. |
| Tinggi | Parser memecah postingan menurut tombol REPLY. Balasan bertingkat tanpa tombol sendiri hilang. Snapshot asli berisi tiga balasan pengguna tetapi sebelumnya hanya dua terbaca. | Parser memakai batas nama/role/tanggal. Ketiga balasan pada snapshot asli sekarang terbaca. |
| Tinggi | Cache live Arkom P7 berisi tiga balasan, sementara rekap detail mencatat nol. | Penulisan cache live dan detail memakai jalur yang sama. Data lokal diselaraskan; versi sebelumnya disimpan di `data/audit_backup_2026_10_03/`. |
| Tinggi | Draf simulasi tetap dihasilkan saat API tidak tersedia; solver kuis memilih opsi pertama ketika API atau parsing gagal. | Kegagalan AI menghentikan aksi. Indeks kuis diperiksa, dan draf fordis harus memiliki tiga bagian lengkap. |
| Tinggi | `auto` kembali ke P1–P2 ketika hasil kosong; nilai `null` membuat pencarian terhenti. Forum juga dilewati karena kuis sudah selesai. | Pemilihan pertemuan menangani `null`, menghormati modul yang diminta, mengembalikan daftar kosong untuk kuis selesai, dan menolak target tidak valid. |
| Tinggi | Antrean dibaca/ditulis tanpa penguncian. Reproduksi 16 enqueue bersamaan kehilangan sebagian tugas. | Penguncian lintas thread/proses dan penulisan atomik; tugas identik yang masih menunggu/berjalan tidak ditambahkan lagi. Kegagalan worker dicatat. |
| Tinggi | Sender WhatsApp dicocokkan sebagai substring, grup melewati pemeriksaan pemilik, dan endpoint tidak memiliki autentikasi. | Token webhook wajib, pencocokan nomor persis, pembatasan pengirim di grup, validasi endpoint/ukuran payload, dan penyamaran token pada log URL. |
| Sedang | Modul agent di-reload pada setiap pesan sehingga memori percakapan dan cooldown model terhapus. | Reload dihapus dan pemrosesan respons diserialkan. Jika model gagal setelah memanggil aksi, hasil aksi dikembalikan tanpa menjalankannya lagi lewat fallback. |
| Sedang | Total komponen selesai pada gradebook dianggap sebagai nomor pertemuan: misalnya completion=5 membuat P1–P5 dianggap selesai. Satu reply dianggap memenuhi fordis. | Rekap memakai bukti per pertemuan dan jumlah balasan yang diperlukan. Penyelesaian kuesioner tidak lagi disimpulkan dari nilai posttest. |
| Sedang | Scope scraper bisa mencakup pertemuan lain; fallback locator dapat mengarah ke seluruh halaman. | Pembacaan kartu dibatasi pada container pertemuan yang tepat. Pertemuan yang tidak ditemukan tidak memakai seluruh halaman sebagai cadangan. |
| Sedang | Solver selalu mengembalikan `completed=True` meskipun masih berada pada halaman ujian. | Keberhasilan memerlukan verifikasi status kuis. Kegagalan memilih jawaban atau navigasi menghentikan proses sebelum submit. |
| Sedang | `requests` dan `psutil` belum tercantum di requirements; `save_auth.py` dirujuk tetapi dikecualikan dari repo; path data bergantung direktori kerja. | Dependensi dilengkapi, utilitas login ditambahkan, path data utama dibuat relatif ke lokasi kode, dan launcher memakai `.venv` bila tersedia. |

## Verifikasi

- Seluruh 32 tes pada `python -m unittest discover -s tests -v` lulus. Cakupannya meliputi pengiriman fordis dengan layanan tiruan, pengulangan setelah putus, draf tidak lengkap, verifikasi setelah reload, parser nested reply, validasi target, antrean bersamaan, dan autentikasi webhook.
- Skrip regresi lama `scratch/test_quiz_targeting.py` dan `scratch/verify_fixes.py` lulus memakai data lokal.
- Seluruh sumber Python aplikasi dan tes lolos pemeriksaan sintaks.
- Selector Reply, textarea, dan SendIcon diuji di Chrome pada halaman tiruan dengan target dosen dan teman yang berbeda. Ini menguji selector, bukan penerimaan server Mentari.
- API key Gemini berhasil membaca daftar model dan menghasilkan respons pendek. SDK `google-genai` 2.28.0 terpasang di `.venv`.
- Data `.env`, sesi autentikasi, dan cache tetap diabaikan Git. `WEBHOOK_SECRET` baru dibuat lokal tanpa mencetak nilainya.

## Batas yang masih perlu diperhatikan

Pengujian live dengan sesi pengguna mendapat HTTP 403 pada halaman pemeriksaan Cloudflare. Pengiriman ke Mentari dan WhatsApp tidak dilakukan dalam audit ini. Penerimaan balasan pada server LMS masih perlu diverifikasi setelah pengguna memperbarui sesi lewat `save_auth.py` dan menjalankan satu target fordis.

Browser Python dan pembuatan direktori sementara oleh interpreter `.venv` mengalami penolakan izin Windows di lingkungan audit. Suite dijalankan dengan interpreter Python utama; pengujian selector menggunakan Playwright CLI. Kendala ini tidak boleh disamakan dengan kelulusan pengujian browser Python.

Kelas, identitas pada sebagian prompt, daftar mata kuliah, dan URL semester masih ditulis di kode. Dukungan akun/kelas/semester lain memerlukan perubahan konfigurasi. Fordis membaca thread pertama yang tersedia pada pertemuan; beberapa thread dalam satu pertemuan belum diproses sebagai batch.

Materi saat ini didaftar, dan kuesioner diisi tanpa submit otomatis. Statusnya kini membedakan aktivitas tersebut dari penyelesaian yang terverifikasi. Rekap kuesioner bisa tampil belum terverifikasi sampai tersedia bukti khusus per pertemuan.

Tugas yang terputus ketika sedang mengirim memiliki status yang belum pasti. Draf dan balasan yang sudah tampak dipakai untuk menghindari duplikasi, tetapi penyimpanan lokal dan server LMS bukan satu transaksi. Periksa LMS sebelum mengulang jika laporan pengiriman belum terverifikasi.

Dokumentasi yang digunakan: [Playwright Python locators](https://playwright.dev/python/docs/locators) dan [Google Gen AI Python SDK](https://github.com/googleapis/python-genai). Panduan menjalankan tersedia di [README.md](README.md).
