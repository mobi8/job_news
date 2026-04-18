#!/usr/bin/env python3
"""Telegram bot message poller - runs independently to handle incoming messages"""

import json
import os
import sys
import time
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
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


def translate_text(text: str, target_lang: str = "en") -> str:
    """
    Translate text using Google Translate free API (no API key needed).

    Args:
        text: Text to translate
        target_lang: Target language code (en, ko, etc.)

    Returns:
        Translated text, or original text if translation fails
    """
    try:
        if not text or len(text.strip()) == 0:
            return text

        # URL encode the text
        encoded_text = urllib.parse.quote(text)
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={encoded_text}"

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        # Extract translated text from response
        # Response format: [[[translated_text, original_text, ...], ...], ...]
        if data and len(data) > 0 and isinstance(data[0], list):
            translated_parts = []
            for item in data[0]:
                if isinstance(item, list) and len(item) > 0:
                    translated_parts.append(item[0])
            if translated_parts:
                return "".join(translated_parts)

        return text
    except Exception as e:
        print(f"⚠️ Translation error (returning original): {e}")
        return text


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


def get_news_by_keyword(keyword: str):
    """Search news by keyword from database"""
    db_path = OUTPUT_DIR / "jobs.sqlite3"
    if not db_path.exists():
        return []

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query_lower = keyword.lower()
        cursor.execute(
            "SELECT * FROM news WHERE title LIKE ? OR summary LIKE ? ORDER BY published_at DESC LIMIT 20",
            (f"%{query_lower}%", f"%{query_lower}%")
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"❌ News search error: {e}")
        return []


def handle_reddit_request(text: str):
    """Handle Reddit on-demand scraping request with translation"""
    from utils.scrapers import fetch_reddit_posts
    from utils.notifications import send_telegram_messages_chunked

    # Parse: 레딧. r/dubai 두바이 취업 or 레딧. 두바이 취업
    _, query_part = text.split(".", 1)
    query_part = query_part.strip()

    subreddit = None
    query = query_part
    days_filter = None
    result_limit = 20  # Default number of results to show

    # Location keyword mapping for automatic subreddit detection
    location_subreddit_map = {
        "두바이": ["dubai", "uae", "abudhabi"],
        "dubai": ["dubai", "uae", "abudhabi"],
        "uae": ["uae", "dubai", "abudhabi"],
        "조지아": ["georgia", "tbilisi"],
        "georgia": ["georgia", "tbilisi"],
        "tbilisi": ["georgia", "tbilisi"],
        "트빌리시": ["georgia", "tbilisi"],
        "몰타": ["malta"],
        "malta": ["malta"],
        "바레인": ["bahrain"],
        "bahrain": ["bahrain"],
        "카타르": ["qatar"],
        "qatar": ["qatar"],
        "사우디": ["saudiarabia"],
        "saudi": ["saudiarabia"],
    }

    # Check if subreddit is explicitly specified (r/name format)
    parts = query_part.split(None, 1)  # Split on first whitespace
    if parts and parts[0].startswith("r/"):
        subreddit = parts[0][2:]  # Remove "r/" prefix
        query = parts[1] if len(parts) > 1 else subreddit  # Use second part as query
    else:
        # Auto-detect location from query and suggest subreddits
        query_lower = query_part.lower()
        for location_keyword, suggested_subs in location_subreddit_map.items():
            if location_keyword in query_lower:
                subreddit = suggested_subs[0]  # Use first suggested subreddit
                break

    # Check for days filter (e.g., "3일", "1day", "최근 7일")
    if any(keyword in query for keyword in ["일", "day", "최근"]):
        days_filter = parse_days(query)
        # Remove the date keyword from query for Reddit search
        for keyword in ["3일", "1일", "7일", "3day", "1day", "최근"]:
            query = query.replace(keyword, "").strip()

    # Check for custom limit (e.g., "30개", "30개", "30", but not "3일")
    import re
    # Look for number followed by 개 or standalone number (but not 일/day)
    limit_match = re.search(r'(\d+)개', query)  # Match "30개"
    if limit_match:
        potential_limit = int(limit_match.group(1))
        if 1 <= potential_limit <= 100:
            result_limit = potential_limit
        query = query.replace(limit_match.group(0), "").strip()
    elif not any(x in query for x in ["일", "day"]):  # Only if not a time filter
        # Try last number as limit only if it's not part of a time filter
        numbers = re.findall(r'(\d+)(?!일|day)', query)  # Exclude numbers followed by 일 or day
        if numbers:
            potential_limit = int(numbers[-1])
            if 1 <= potential_limit <= 100:
                result_limit = potential_limit
                query = re.sub(r'\d+$', '', query).strip()  # Remove trailing number

    # Translate query to English for Reddit search (if Korean detected)
    query_en = translate_text(query, target_lang="en")
    print(f"🌐 Translated '{query}' → '{query_en}'")

    # Fetch Reddit posts with translated query (fetch more to account for time filtering)
    fetch_limit = max(50, result_limit * 2) if days_filter else result_limit * 2
    posts = fetch_reddit_posts(query_en, subreddit, limit=fetch_limit)

    # Filter by days if specified
    if days_filter:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_filter)
        posts = [p for p in posts if p.get("created_utc", 0) > cutoff.timestamp()]

    # Limit to requested number of results
    posts = posts[:result_limit]

    if posts:
        # Build header with time filter info if present
        time_filter_text = f" (최근 {days_filter}일)" if days_filter else ""
        lines = [f"🔗 Reddit '{query}' 검색 결과 ({len(posts)}개){time_filter_text}"]
        if subreddit:
            lines[0] = f"🔗 r/{subreddit} '{query}' 검색 결과 ({len(posts)}개){time_filter_text}"

        for i, post in enumerate(posts, 1):
            title = post.get("title", "?")
            url = post.get("url", "")
            sr = post.get("subreddit", "")
            score = post.get("score", 0)
            summary = post.get("summary", "")

            # Translate title and summary to Korean
            title_ko = translate_text(title, target_lang="ko")
            summary_ko = translate_text(summary, target_lang="ko") if summary else ""

            if url:
                title_link = f'<a href="{url}">{title_ko}</a>'
            else:
                title_link = title_ko

            # Build post line with translation
            if summary_ko and len(summary_ko) > 0:
                summary_short = summary_ko[:100] + "..." if len(summary_ko) > 100 else summary_ko
                lines.append(f"{i}. {title_link}\n   {summary_short}\n   r/{sr} | ⬆️ {score}")
            else:
                lines.append(f"{i}. {title_link} (r/{sr}, ⬆️ {score})")

        send_telegram_messages_chunked(lines)
    else:
        send_telegram_text(f"'{query}' 관련 Reddit 포스트가 없습니다.")


def handle_message(text: str):
    """Process incoming message and send response"""
    if not text:
        return

    # Check for Reddit request first (must be exact match with . separator)
    if "." in text:
        parts = text.split(".", 1)
        prefix = parts[0].strip().lower()

        if prefix in ("레딧", "reddit"):
            try:
                handle_reddit_request(text)
            except Exception as e:
                print(f"❌ Reddit request error: {e}")
                from utils.notifications import send_telegram_text
                send_telegram_text(f"❌ Reddit 요청 처리 중 오류: {str(e)}")
            return

    from utils.notifications import send_telegram_messages_chunked

    jobs_data = get_jobs_data()
    all_jobs = jobs_data.get("all_tracked_jobs", [])

    # Check if it's a date filter or search query
    is_date_query = any(keyword in text for keyword in ["일", "day", "최근"])

    if is_date_query:
        days = parse_days(text)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        job_results = [
            j for j in all_jobs
            if j.get("first_seen_at")
            and datetime.fromisoformat(j["first_seen_at"].replace("Z", "+00:00")) >= cutoff
            and j.get("qualifies")
        ]
        news_results = []
        header = f"🔍 최근 {days}일 신규 공고 ({len(job_results)}개)"
    else:
        # Search query - search both jobs and news
        query = text.lower().strip()
        job_results = [
            j for j in all_jobs
            if j.get("qualifies") and (
                query in j.get("title", "").lower()
                or query in j.get("company", "").lower()
                or query in j.get("description", "").lower()
            )
        ]
        news_results = get_news_by_keyword(text)
        header = f"🔎 '{text}' 검색 결과 (공고: {len(job_results)}개, 뉴스: {len(news_results)}개)"

    recent = job_results
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

        # Add news if any
        if news_results:
            lines.append("\n📰 관련 뉴스:")
            for i, news in enumerate(news_results[:5], 1):
                title = news.get("title", "?")
                url = news.get("url", "")
                if url:
                    news_link = f'<a href="{url}">{title}</a>'
                else:
                    news_link = title
                lines.append(f"{i}. {news_link}")

        send_telegram_messages_chunked(lines)
    else:
        if is_date_query:
            send_telegram_text(f"최근 {days}일 신규 공고가 없습니다.")
        else:
            send_telegram_text(f"'{text}' 관련 공고나 뉴스가 없습니다.")


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
