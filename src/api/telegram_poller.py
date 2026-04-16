#!/usr/bin/env python3
"""Telegram bot message poller - runs independently to handle incoming messages"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config import OUTPUT_DIR
from utils.notifications import send_telegram_text

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
JOBS_DATA_PATH = OUTPUT_DIR / "jobs_analysis.json"


def get_jobs_data():
    if not JOBS_DATA_PATH.exists():
        return {}
    try:
        return json.loads(JOBS_DATA_PATH.read_text(encoding="utf-8"))
    except:
        return {}


def parse_days(text: str) -> int:
    """Extract days from message"""
    if "3일" in text or "3day" in text:
        return 3
    elif "1일" in text or "1day" in text or "오늘" in text:
        return 1
    return 7  # default


def handle_message(text: str):
    """Process incoming message and send response"""
    if not text:
        return

    from utils.notifications import send_telegram_messages_chunked

    jobs_data = get_jobs_data()
    all_jobs = jobs_data.get("all_tracked_jobs", [])

    # Check if it's a date filter or search query
    is_date_query = any(keyword in text for keyword in ["일", "day", "최근"])

    if is_date_query:
        days = parse_days(text)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results = [
            j for j in all_jobs
            if j.get("first_seen_at")
            and datetime.fromisoformat(j["first_seen_at"].replace("Z", "+00:00")) >= cutoff
            and j.get("qualifies")
        ]
        header = f"🔍 최근 {days}일 신규 공고 ({len(results)}개)"
    else:
        # Search query
        query = text.lower().strip()
        results = [
            j for j in all_jobs
            if j.get("qualifies") and (
                query in j.get("title", "").lower()
                or query in j.get("company", "").lower()
                or query in j.get("description", "").lower()
            )
        ]
        header = f"🔎 '{text}' 검색 결과 ({len(results)}개)"

    recent = results
    # Sort by score (highest first)
    recent.sort(key=lambda j: j.get("match_score", 0), reverse=True)

    # Format and send
    if recent:
        lines = [header]

        # Country emoji mapping
        country_emoji = {
            "UAE": "🇦🇪",
            "Georgia": "🇬🇪",
            "Malta": "🇲🇹",
            "Bahrain": "🇧🇭",
            "Qatar": "🇶🇦",
            "Saudi Arabia": "🇸🇦",
        }

        for i, job in enumerate(recent, 1):
            title = job.get("title", "?")
            company = job.get("company", "?")
            score = job.get("match_score", 0)
            url = job.get("url", "")
            country = job.get("country", "")

            if url:
                title_link = f'<a href="{url}">{title}</a>'
            else:
                title_link = title

            country_flag = country_emoji.get(country, country or "")
            lines.append(f"{i}. {country_flag} {title_link} - {company} ({score}점)")

        send_telegram_messages_chunked(lines)
    else:
        send_telegram_text(f"최근 {days}일 신규 공고가 없습니다.")


def poll_messages():
    """Poll Telegram API for new messages"""
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return

    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset={offset}&timeout=30"
            with urllib.request.urlopen(url, timeout=35) as response:
                data = json.loads(response.read().decode())

            if not data.get("ok"):
                print(f"❌ Telegram API error: {data}")
                time.sleep(5)
                continue

            for update in data.get("result", []):
                msg = update.get("message", {})
                text = msg.get("text", "").strip()
                user = msg.get("from", {}).get("first_name", "User")

                if text:
                    print(f"📨 {user}: {text}")
                    handle_message(text)

                offset = update.get("update_id", 0) + 1

            time.sleep(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    print("🤖 Starting Telegram bot poller...")
    poll_messages()
