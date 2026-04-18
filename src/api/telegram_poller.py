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

# Subreddit candidate mapping for keyword-based search
TOPIC_SUBREDDIT_MAP = {
    "job": ["jobs", "hiring", "jobsearch", "careerguidance"],
    "취업": ["jobs", "hiring", "jobsearch"],
    "hiring": ["hiring", "jobs", "recruits"],
    "recruit": ["recruits", "hiring", "jobs"],
    "채용": ["jobs", "hiring", "recruits"],
    "개발": ["learnprogramming", "programming", "webdev", "cscareerquestions"],
    "개발자": ["learnprogramming", "programming", "cscareerquestions"],
    "developer": ["learnprogramming", "programming", "webdev", "cscareerquestions"],
    "python": ["Python", "learnprogramming"],
    "javascript": ["javascript", "learnprogramming"],
    "golang": ["golang", "learnprogramming"],
    "visa": ["ImmigrationCanada", "ukvisa", "immigrationau"],
    "비자": ["ImmigrationCanada", "ukvisa"],
    "salary": ["cscareerquestions", "jobs"],
    "연봉": ["jobs", "cscareerquestions"],
}

LOCATION_SUBREDDIT_MAP = {
    "두바이": ["dubaijobs", "dubai", "uaejobs"],
    "dubai": ["dubaijobs", "dubai", "uaejobs"],
    "uae": ["uaejobs", "dubai"],
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


def get_subreddit_candidates(query_original: str, query_parts: list) -> list:
    """
    Extract subreddit candidates from query based on keywords.
    Returns list of subreddit names sorted by priority.

    Args:
        query_original: Original query string
        query_parts: List of keywords extracted from query

    Returns:
        List of subreddit candidates (e.g., ["dubaijobs", "jobs", "dubai"])
    """
    candidates = []
    candidates_set = set()

    query_lower = query_original.lower()

    # 1. Topic-based subreddits (highest priority)
    for keyword, subs in TOPIC_SUBREDDIT_MAP.items():
        if keyword.lower() in query_lower:
            for sub in subs:
                if sub not in candidates_set:
                    candidates.append(sub)
                    candidates_set.add(sub)

    # 2. Location-based subreddits
    for keyword, subs in LOCATION_SUBREDDIT_MAP.items():
        if keyword.lower() in query_lower:
            for sub in subs:
                if sub not in candidates_set:
                    candidates.append(sub)
                    candidates_set.add(sub)

    # 3. If no candidates found, use general subreddits
    if not candidates:
        candidates = ["jobs", "learnprogramming", "AskReddit"]

    return candidates


def search_multiple_subreddits(query: str, candidates: list, fetch_limit: int = 50) -> list:
    """
    Search multiple subreddits and combine results.

    Args:
        query: Search query
        candidates: List of subreddit names
        fetch_limit: How many posts to fetch per subreddit

    Returns:
        Combined list of posts from all subreddits
    """
    from utils.scrapers import fetch_reddit_posts

    all_posts = []

    for sr in candidates[:5]:  # Limit to 5 subreddits max
        try:
            posts = fetch_reddit_posts(query, subreddit=sr, limit=fetch_limit)
            # Ensure posts is a list
            if not isinstance(posts, list):
                print(f"⚠️ r/{sr}: Invalid response type (expected list, got {type(posts).__name__})")
                continue

            # Add subreddit to each post for tracking
            for post in posts:
                if isinstance(post, dict):
                    post["_searched_subreddit"] = sr
            all_posts.extend(posts)
        except Exception as e:
            print(f"⚠️ Error searching r/{sr}: {str(e)[:80]}")
            continue

    return all_posts


def calculate_relevance_score(post: dict, query_keywords: list) -> float:
    """
    Calculate relevance score based on keyword matching.

    Args:
        post: Reddit post dict
        query_keywords: List of search keywords

    Returns:
        Relevance score (0.0 to 1.0)
    """
    if not query_keywords:
        return 0.0

    title = (post.get("title", "") or "").lower()
    summary = (post.get("summary", "") or "").lower()
    text = f"{title} {summary}"

    matches = 0
    for keyword in query_keywords:
        if keyword.lower() in text:
            matches += 1

    # Score: number of matched keywords / total keywords
    return matches / len(query_keywords) if query_keywords else 0.0


def filter_and_rank_posts(posts: list, query_keywords: list, min_score: float = 0.3) -> list:
    """
    Filter posts by relevance score and sort by score.

    Args:
        posts: List of posts to filter
        query_keywords: List of search keywords
        min_score: Minimum relevance score to include (0.0 to 1.0)

    Returns:
        Sorted list of relevant posts
    """
    # Calculate scores for all posts
    posts_with_scores = []
    for post in posts:
        score = calculate_relevance_score(post, query_keywords)
        if score >= min_score:
            post["_relevance_score"] = score
            posts_with_scores.append(post)

    # Sort by score (descending)
    posts_with_scores.sort(key=lambda p: p["_relevance_score"], reverse=True)

    return posts_with_scores


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
    """Handle Reddit on-demand scraping request with translation and multi-subreddit search"""
    from utils.notifications import send_telegram_messages_chunked

    # Parse: 레딧. r/dubai 두바이 취업 or 레딧. 두바이 취업
    _, query_part = text.split(".", 1)
    query_part = query_part.strip()
    query_original = query_part

    subreddit = None
    query = query_part
    days_filter = None
    result_limit = 20  # Default number of results to show

    # Check if subreddit is explicitly specified (r/name format)
    parts = query_part.split(None, 1)  # Split on first whitespace
    if parts and parts[0].startswith("r/"):
        subreddit = parts[0][2:]  # Remove "r/" prefix
        query = parts[1] if len(parts) > 1 else subreddit  # Use second part as query
        query_original = query

    # Remove location keywords from query for cleaner search
    query_lower = query.lower()
    for location_keyword in LOCATION_SUBREDDIT_MAP.keys():
        if location_keyword.lower() in query_lower:
            query = query.replace(location_keyword, " ").strip()

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

    # If explicit subreddit specified, search only that one
    if subreddit:
        from utils.scrapers import fetch_reddit_posts
        fetch_limit = max(50, result_limit * 2) if days_filter else result_limit * 2
        posts = fetch_reddit_posts(query_en, subreddit, limit=fetch_limit)
    else:
        # Multi-subreddit search with relevance filtering
        fetch_limit = max(50, result_limit * 3) if days_filter else result_limit * 3
        candidates = get_subreddit_candidates(query_original, query_en.split())
        print(f"🔍 Searching subreddits: {candidates[:5]}")
        posts = search_multiple_subreddits(query_en, candidates, fetch_limit=fetch_limit)

        # Filter by relevance using original query keywords
        query_keywords = [kw for kw in query_original.split() if len(kw) > 2]
        posts = filter_and_rank_posts(posts, query_keywords, min_score=0.25)

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
