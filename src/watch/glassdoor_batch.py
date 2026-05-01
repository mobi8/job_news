#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = str(Path(__file__).parent / "scraper.py")
LOCK_PATH = "/Users/lewis/Desktop/agent/outputs/scrape_run.lock"


def _run_glassdoor_batch() -> int:
    env = os.environ.copy()
    env["JOB_WATCH_SOURCES"] = "glassdoor_uae"
    env["SKIP_NEWS_COLLECTION"] = "1"
    env.setdefault("BROWSER_GLASSDOOR_BATCH_SIZE", "1")
    env.setdefault("BROWSER_GLASSDOOR_BATCH_WORKERS", "1")

    Path(LOCK_PATH).parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Another scrape run is already active; skipping Glassdoor batch.", flush=True)
            return 0

        result = subprocess.run(
            [sys.executable, SCRIPT_PATH, "collect"],
            env=env,
            check=False,
        )
        return result.returncode
    finally:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
        except Exception:
            pass
        lock_file.close()


def main() -> int:
    return _run_glassdoor_batch()


if __name__ == "__main__":
    raise SystemExit(main())
