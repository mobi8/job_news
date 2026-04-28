#!/usr/bin/env python3

from __future__ import annotations

import os
import json
import fcntl
import subprocess
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

# Load .env file if it exists
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

# Add src/ to path so utils, config, etc. can be imported directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import Database
from utils.config import WATCH_INTERVAL_MINUTES_DEFAULT
from utils.logger import watch_logger
from services.queue_exporter import export_high_scoring_jobs
from services.telegram_scraper import scrape_and_save

# Updated path: scraper.py is in src/watch/
SCRIPT_PATH = str(Path(__file__).parent / "scraper.py")
WATCH_SETTINGS_PATH = "/Users/lewis/Desktop/agent/outputs/watch_settings.json"
DB_PATH = "/Users/lewis/Desktop/agent/outputs/jobs.sqlite3"
LOCK_PATH = "/Users/lewis/Desktop/agent/outputs/watch_loop.lock"


def _console_step(message: str) -> None:
    print(f"\n>>> {datetime.now().isoformat(timespec='seconds')} {message}", flush=True)


def load_watch_settings() -> dict:
    try:
        with open(WATCH_SETTINGS_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {"scrape_interval_minutes": WATCH_INTERVAL_MINUTES_DEFAULT}
    return {
        "scrape_interval_minutes": max(1, int(payload.get("scrape_interval_minutes", WATCH_INTERVAL_MINUTES_DEFAULT))),
    }


def run_once() -> int:
    env = os.environ.copy()
    settings = load_watch_settings()
    interval_seconds = int(settings["scrape_interval_minutes"] * 60)
    watch_mode = "collect"

    _console_step(f"Watcher starting (mode={watch_mode}, interval={interval_seconds}s)")
    watch_logger.info(f"Running watcher (mode={watch_mode}, interval={interval_seconds}s)")

    result = subprocess.run(
        [sys.executable, SCRIPT_PATH, watch_mode],
        env=env,
        check=False,
    )

    if result.returncode == 0:
        watch_logger.info("✓ Scraper completed with detailed descriptions")
        _console_step("Watcher finished successfully")

        # Scrape Telegram channels
        try:
            watch_logger.info("Starting Telegram channel scraping...")
            tg_result = scrape_and_save(DB_PATH)
            watch_logger.info(f"Telegram scraping complete: {tg_result['total_saved']} jobs saved")
            _console_step(f"Telegram: {tg_result['total_saved']} jobs scraped")
        except Exception as e:
            watch_logger.error(f"Failed to scrape Telegram channels: {e}")
            _console_step(f"Telegram scraping failed: {e}")

        # Export high-scoring jobs to career-ops queue
        try:
            export_result = export_high_scoring_jobs(DB_PATH, min_score=60)
            if export_result.get("count", 0) > 0:
                watch_logger.info(f"Queue export: {export_result['count']} jobs added to career-ops")
                _console_step(f"Queue updated: {export_result['count']} jobs exported")
        except Exception as e:
            watch_logger.error(f"Failed to export queue: {e}")
    else:
        _console_step(f"Watcher finished with exit code {result.returncode}")

    return result.returncode


def acquire_single_instance_lock() -> object | None:
    Path(LOCK_PATH).parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        watch_logger.warning("Another watch loop is already running; exiting.")
        lock_file.close()
        return None

    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return lock_file





def main() -> int:
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)

    _lock_file = acquire_single_instance_lock()
    if _lock_file is None:
        return 0

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        watch_logger.warning("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID; running without Telegram alerts")

    while True:
        try:
            settings = load_watch_settings()
            interval_seconds = int(settings["scrape_interval_minutes"] * 60)
            started_at = time.time()
            code = run_once()
            watch_logger.info(f"Watcher exit code: {code}")
            elapsed = time.time() - started_at
            sleep_seconds = max(0, interval_seconds - elapsed)
            watch_logger.info(f"Sleeping {int(sleep_seconds)}s until next run")
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            watch_logger.info("Watcher interrupted; exiting.")
            return 0
        except Exception as exc:
            watch_logger.exception("Watcher loop error: %s", exc)
            time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
