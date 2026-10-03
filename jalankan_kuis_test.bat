@echo off
title Mentari LMS - Quiz Tester (Pretest & Post-Test)
cd /d "%~dp0"
set "MENTARI_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "MENTARI_PYTHON=.venv\Scripts\python.exe"
echo ========================================================
echo   MENJALANKAN PENGUJIAN KUIS (PRETEST & POST-TEST)
echo   Mata Kuliah: MANAJEMEN PROYEK INFORMATIKA (Pertemuan 1)
echo ========================================================
"%MENTARI_PYTHON%" quiz_runner.py
pause
