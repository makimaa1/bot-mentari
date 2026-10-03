@echo off
title Mentari LMS - Full Learning Pipeline
cd /d "%~dp0"
echo =====================================================================
echo    MENTARI LMS - PIPELINE PEMBELAJARAN LENGKAP & OTOMATIS
echo    Alur: [1] Pre-Test -^> [2] Materi -^> [3] Fordis -^> [4] Post-Test -^> [5] Kuesioner
echo =====================================================================
echo  PILIH MATA KULIAH:
echo   1. MANAJEMEN PROYEK INFORMATIKA
echo   2. ARSITEKTUR DAN ORGANISASI KOMPUTER
echo   3. KEAMANAN KOMPUTER
echo   4. JARINGAN NIRKABEL
echo   5. KECAKAPAN ANTAR PERSONAL
echo   6. TESTING DAN QA PERANGKAT LUNAK
echo   7. ETIKA PROFESI
echo   8. PEMROGRAMAN WEB II
echo =====================================================================
set /p matkul_id="Masukkan nomor mata kuliah [1-8] (Default: 1): "
if "%matkul_id%"=="" set matkul_id=1

set /p pertemuan_num="Masukkan nomor pertemuan [1-19] (Default: 2): "
if "%pertemuan_num%"=="" set pertemuan_num=2

echo.
echo [*] Memulai Pipeline Pembelajaran untuk Matkul #%matkul_id% Pertemuan %pertemuan_num%...
python pipeline_runner.py %matkul_id% %pertemuan_num%
pause
