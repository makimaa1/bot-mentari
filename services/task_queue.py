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
import uuid
from services.json_store import file_lock, read_json, write_json

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
            if "python" in proc.name().lower() and abs(proc.create_time() - data.get("process_created", proc.create_time())) < 0.1:
                return True
    except Exception:
        pass
    return False


def enqueue_task(course_key: str, course_name: str, meeting_target: str, target_step: str) -> dict:
    """
    Menambahkan tugas eksekusi ke antrean dan memastikan satu worker browser berjalan.
    Menghindari terbukanya banyak jendela Chrome secara bersamaan.
    """
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with file_lock(str(QUEUE_FILE) + '.guard'):
        tasks = read_json(QUEUE_FILE, [])
        if not isinstance(tasks, list):
            raise ValueError("Format antrean harus berupa daftar tugas.")
        fields = {"course_key": course_key, "course_name": course_name,
                  "meeting_target": str(meeting_target), "target_step": target_step}
        worker_running = is_worker_active()
        if not worker_running:
            interrupted = read_json(LOCK_FILE, {}).get('task')
            if interrupted:
                interrupted.update(status='interrupted', error='Worker berhenti; periksa LMS sebelum mengulang.')
                write_json(QUEUE_FILE.parent / 'pipeline_last_result.json', interrupted)
        running = read_json(LOCK_FILE, {}).get('task') if worker_running else None
        if running and all(running.get(k) == v for k, v in fields.items()):
            return {"status": "running", "position": 0, "total_in_queue": len(tasks)}
        existing = next((i for i, task in enumerate(tasks) if all(task.get(k) == v for k, v in fields.items())), None)
        if existing is None:
            tasks.append({"id": uuid.uuid4().hex, **fields, "created_at": time.time()})
            write_json(QUEUE_FILE, tasks)
        position = (existing + 1) if existing is not None else len(tasks)
        if not worker_running:
            cmd = [sys.executable, str(BASE_DIR / "pipeline_runner.py"), "--run-queue", "--non-interactive"]
            proc = subprocess.Popen(cmd, cwd=str(BASE_DIR))
            write_json(LOCK_FILE, {"pid": proc.pid, "process_created": psutil.Process(proc.pid).create_time(), "started_at": time.time()})
        return {"status": "queued" if worker_running else "started", "position": position, "total_in_queue": len(tasks)}


def take_next_task():
    """Reserve one task; clear ownership atomically when the queue is empty."""
    with file_lock(str(QUEUE_FILE) + '.guard'):
        state = read_json(LOCK_FILE, {})
        if is_worker_active() and state.get('pid') != os.getpid():
            raise RuntimeError("Worker lain masih aktif.")
        tasks = read_json(QUEUE_FILE, [])
        if not isinstance(tasks, list):
            raise ValueError("Format antrean harus berupa daftar tugas.")
        if not tasks:
            LOCK_FILE.unlink(missing_ok=True)
            return None
        task = tasks.pop(0)
        write_json(LOCK_FILE, {"pid": os.getpid(), "process_created": psutil.Process().create_time(),
                               "started_at": time.time(), "task": task})
        write_json(QUEUE_FILE, tasks)
        return task


def finish_task(task, error=None):
    with file_lock(str(QUEUE_FILE) + '.guard'):
        state = read_json(LOCK_FILE, {})
        if state.get('pid') != os.getpid():
            return
        task.update(finished_at=time.time(), status='failed' if error else 'completed')
        if error:
            task['error'] = str(error)
        write_json(QUEUE_FILE.parent / 'pipeline_last_result.json', task)
        state.pop('task', None)
        write_json(LOCK_FILE, state)
