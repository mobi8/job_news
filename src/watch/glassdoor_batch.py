#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = str(Path(__file__).parent / "scraper.py")
LOCK_PATH = "/Users/lewis/Desktop/agent/outputs/scrape_run.lock"


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _read_lock_pid() -> int:
    try:
        return int(Path(LOCK_PATH).read_text(encoding="utf-8").strip())
    except Exception:
        return 0


def _acquire_lock() -> bool:
    lock_path = Path(LOCK_PATH)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    existing_pid = _read_lock_pid() if lock_path.exists() else 0
    if existing_pid and _pid_exists(existing_pid):
        print(f"Another Glassdoor run is already active: PID={existing_pid}", flush=True)
        return False
    if lock_path.exists():
        print(f"Removing stale Glassdoor lock: {LOCK_PATH}", flush=True)
        lock_path.unlink(missing_ok=True)

    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing_pid = _read_lock_pid()
        if existing_pid and _pid_exists(existing_pid):
            print(f"Another Glassdoor run is already active: PID={existing_pid}", flush=True)
            return False
        print(f"Glassdoor lock appeared stale but could not be acquired: {LOCK_PATH}", flush=True)
        return False

    with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
        lock_file.write(str(os.getpid()))
    return True


def _release_lock() -> None:
    lock_path = Path(LOCK_PATH)
    if _read_lock_pid() == os.getpid():
        lock_path.unlink(missing_ok=True)


def _run_glassdoor_batch() -> int:
    env = os.environ.copy()
    env["JOB_WATCH_SOURCES"] = "glassdoor_uae"
    env.setdefault("BROWSER_GLASSDOOR_BATCH_SIZE", "1")
    env.setdefault("BROWSER_GLASSDOOR_BATCH_WORKERS", "1")

    if not _acquire_lock():
        return 75
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "collect"],
            env=env,
            check=False,
        )
        return result.returncode
    finally:
        _release_lock()


def main() -> int:
    return _run_glassdoor_batch()


if __name__ == "__main__":
    raise SystemExit(main())
