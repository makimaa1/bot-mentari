@echo off
title Mentari LMS - Course Explorer
cd /d "%~dp0"
set "MENTARI_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "MENTARI_PYTHON=.venv\Scripts\python.exe"
echo ========================================================
echo   MENJALANKAN PENELUSURAN MATA KULIAH MENTARI LMS
echo ========================================================
"%MENTARI_PYTHON%" explore_courses.py
pause
