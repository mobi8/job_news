#!/usr/bin/env python3

from __future__ import annotations

import os
import json
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
from utils.logger import watch_logger

# Updated path: scraper.py is in src/watch/
SCRIPT_PATH = str(Path(__file__).parent / "scraper.py")
WATCH_SETTINGS_PATH = "/Users/lewis/Desktop/agent/outputs/watch_settings.json"
DB_PATH = "/Users/lewis/Desktop/agent/outputs/jobs.sqlite3"


def load_watch_settings() -> dict:
    try:
        with open(WATCH_SETTINGS_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {"scrape_interval_minutes": 1440}
    return {
        "scrape_interval_minutes": max(1, int(payload.get("scrape_interval_minutes", 1440))),
    }


def run_once() -> int:
    env = os.environ.copy()
    settings = load_watch_settings()
    interval_seconds = int(settings["scrape_interval_minutes"] * 60)
    watch_mode = "collect"

    watch_logger.info(f"Running watcher (mode={watch_mode}, interval={interval_seconds}s)")

    result = subprocess.run(
        [sys.executable, SCRIPT_PATH, watch_mode],
        env=env,
        check=False,
    )

    return result.returncode




def main() -> int:
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)

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
