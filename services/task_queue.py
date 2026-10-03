"""
Sistem Antrean Terpusat Pengerjaan Mentari LMS (Task Queue Manager).
Memastikan seluruh eksekusi kuis/pertemuan berjalan bergantian secara tertib
dalam 1 sesi browser Chrome tanpa membuka banyak browser secara bersamaan.
"""
import sys
import os
import time
import json
from pathlib import Path
import psutil
import subprocess

BASE_DIR = Path(__file__).resolve().parent.parent
QUEUE_FILE = BASE_DIR / "data" / "pipeline_queue.json"
LOCK_FILE = BASE_DIR / "data" / "pipeline_queue.lock"


def is_worker_active() -> bool:
    """Mengecek apakah proses queue worker sedang aktif berjalan di laptop."""
    if not LOCK_FILE.exists():
        return False
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        pid = data.get("pid")
        if pid and psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            if "python" in proc.name().lower():
                return True
    except Exception:
        pass
    # Jika file ada tapi PID mati, bersihkan lock file lama
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    return False


def enqueue_task(course_key: str, course_name: str, meeting_target: str, target_step: str) -> dict:
    """
    Menambahkan tugas eksekusi ke antrean dan memastikan satu worker browser berjalan.
    Menghindari terbukanya banyak jendela Chrome secara bersamaan.
    """
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 1. Baca antrean saat ini
    tasks = []
    if QUEUE_FILE.exists():
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                tasks = json.load(f)
        except Exception:
            tasks = []

    new_task = {
        "id": f"task_{int(time.time()*1000)}",
        "course_key": course_key,
        "course_name": course_name,
        "meeting_target": str(meeting_target),
        "target_step": target_step,
        "created_at": time.time()
    }
    tasks.append(new_task)

    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2, ensure_ascii=False)

    worker_running = is_worker_active()

    if not worker_running:
        # Jalankan worker di latar belakang
        cmd = [
            sys.executable,
            str(BASE_DIR / "pipeline_runner.py"),
            "--run-queue",
            "--non-interactive"
        ]
        p = subprocess.Popen(cmd, cwd=str(BASE_DIR))
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            json.dump({"pid": p.pid, "started_at": time.time()}, f, indent=2)
        return {
            "status": "started",
            "position": 1,
            "total_in_queue": len(tasks),
            "message": f"Browser Chrome diluncurkan untuk memproses {course_name} (Pertemuan {meeting_target})."
        }
    else:
        return {
            "status": "queued",
            "position": len(tasks),
            "total_in_queue": len(tasks),
            "message": f"Tugas dimasukkan ke dalam antrean (urutan ke-{len(tasks)}). Browser akan otomatis memproses tugas ini secara berurutan setelah tugas sebelumnya selesai."
        }
