@echo off
title Mentari LMS - Quiz Tester (Pretest & Post-Test)
cd /d "%~dp0"
echo ========================================================
echo   MENJALANKAN PENGUJIAN KUIS (PRETEST & POST-TEST)
echo   Mata Kuliah: MANAJEMEN PROYEK INFORMATIKA (Pertemuan 1)
echo ========================================================
python quiz_runner.py
pause
