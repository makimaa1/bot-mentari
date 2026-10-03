@echo off
cd /d "%~dp0"
set "MENTARI_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "MENTARI_PYTHON=.venv\Scripts\python.exe"
chcp 65001 >nul
title Mentari LMS - WhatsApp AI Agent
cls
echo ===============================================================================
echo                MENTARI LMS - WHATSAPP AI AGENT CONTROLLER
echo                  Didukung Model Google Gemini 3.8 / 3.6 Flash
echo ===============================================================================
echo.
echo Pilih mode yang ingin dijalankan:
echo [1] Jalankan Server WhatsApp Webhook (Menerima perintah chat dari HP)
echo [2] Uji Coba Chat Agent Langsung di Terminal (Tanpa WhatsApp)
echo [3] Jalankan Pipeline Belajar Mentari (Manual di Komputer)
echo [4] Keluar
echo.
set /p mode="Masukkan pilihan [1-4]: "

if "%mode%"=="1" (
    cls
    echo [*] Memulai Server WhatsApp Agent...
    "%MENTARI_PYTHON%" wa_command_server.py
    pause
) else if "%mode%"=="2" (
    cls
    echo [*] Memulai Mode Chat Interaktif AI Agent...
    "%MENTARI_PYTHON%" wa_command_server.py --cli
    pause
) else if "%mode%"=="3" (
    cls
    call jalankan_pipeline.bat
) else (
    echo [*] Keluar.
)
