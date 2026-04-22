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

def _resolve_url(key: str) -> str:
    """Look up full URL from url_map.json by short key."""
    import json as _json
    url_map_path = OUTPUT_DIR / "url_map.json"
    if url_map_path.exists():
        url_map = _json.loads(url_map_path.read_text())
        return url_map.get(key, key)
    return key


def _get_job_description(key: str) -> str | None:
    """Look up job description by dashboard_key or url from jobs_analysis.json."""
    if not JOBS_DATA_PATH.exists():
        return None
    try:
        # Resolve numerical key to actual URL first
        resolved_url = _resolve_url(key)

        data = json.loads(JOBS_DATA_PATH.read_text(encoding="utf-8"))
        all_jobs = data.get("all_tracked_jobs", data.get("filtered_jobs", []))
        for job in all_jobs:
            if job.get("url") == resolved_url:
                description = job.get("description", "").strip()
                if description:
                    return description[:2000]
        return None
    except Exception:
        return None

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
    "visa": ["ImmigrationCanada", "ukvisa", "immigrationau", "expats"],
    "비자": ["ImmigrationCanada", "ukvisa", "expats"],
    "expatriate": ["expats", "ImmigrationCanada", "jobs"],
    "외국인": ["expats", "ImmigrationCanada", "jobs"],
    "expat": ["expats", "ImmigrationCanada"],
    "immigration": ["ImmigrationCanada", "ukvisa", "immigrationau"],
    "이민": ["ImmigrationCanada", "expats"],
    "salary": ["cscareerquestions", "jobs"],
    "연봉": ["jobs", "cscareerquestions"],
}

# Subreddit pools by location (not fixed - can be expanded)
LOCATION_SUBREDDIT_POOLS = {
    "georgia": {
        "keywords": ["조지아", "georgia", "tbilisi", "트빌리시"],
        "candidates": ["georgiajobs", "georgiaexpats", "georgia", "tbilisi"],
    },
    "dubai": {
        "keywords": ["두바이", "dubai", "uae"],
        "candidates": ["dubaijobs", "dubai", "uaejobs"],
    },
    "malta": {
        "keywords": ["몰타", "malta"],
        "candidates": ["malta"],
    },
    "bahrain": {
        "keywords": ["바레인", "bahrain"],
        "candidates": ["bahrain"],
    },
    "qatar": {
        "keywords": ["카타르", "qatar"],
        "candidates": ["qatar"],
    },
    "saudi": {
        "keywords": ["사우디", "saudi"],
        "candidates": ["saudiarabia"],
    },
}

# Subreddit performance scores (loaded from file, updated after each search)
SUBREDDIT_SCORES = {}  # Format: {location: {subreddit: score}}


def get_subreddit_candidates(query_original: str, query_parts: list) -> dict:
    """
    Extract subreddit candidates with dynamic priority based on:
    1. Location detection (highest priority)
    2. Topic matching (medium priority)
    3. General fallback (low priority)

    Uses performance scores for ordering within each tier.

    Args:
        query_original: Original query string
        query_parts: List of keywords extracted from query

    Returns:
        Dict with priority levels: {"high": [...], "medium": [...], "low": [...]}
    """
    candidates = {"high": [], "medium": [], "low": []}
    seen = set()

    query_lower = query_original.lower()

    # 1. LOCATION-BASED (highest priority - from LOCATION_SUBREDDIT_POOLS)
    detected_location = None
    for location, pool_data in LOCATION_SUBREDDIT_POOLS.items():
        keywords = pool_data.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in query_lower:
                detected_location = location
                # Get sorted candidates for this location
                sorted_subs = get_sorted_candidates(location)
                for sub in sorted_subs:
                    if sub not in seen:
                        candidates["high"].append(sub)
                        seen.add(sub)
                break
        if detected_location:
            break

    # 2. EXPAT/IMMIGRATION (medium priority)
    expat_subs = ["expats", "ImmigrationCanada", "ukvisa", "immigrationau"]
    for keyword in ["foreign", "expat", "expatriate", "immigrant", "visa", "relocation", "외국인", "비자"]:
        if keyword.lower() in query_lower:
            for sub in expat_subs:
                if sub not in seen:
                    candidates["medium"].append(sub)
                    seen.add(sub)
            break

    # 3. TOPIC-BASED (medium priority for specific topics)
    for keyword, subs in TOPIC_SUBREDDIT_MAP.items():
        if keyword.lower() in query_lower and keyword not in ["외국인", "expatriate"]:
            for sub in subs:
                if sub not in seen and sub not in ["AskReddit", "programming"]:
                    candidates["medium"].append(sub)
                    seen.add(sub)

    # 4. GENERAL JOBS (low priority - fallback)
    general_jobs = ["jobs", "hiring", "jobsearch"]
    for sub in general_jobs:
        if sub not in seen:
            candidates["low"].append(sub)
            seen.add(sub)

    # 5. If no candidates at all, use fallback
    if not candidates["high"] and not candidates["medium"] and not candidates["low"]:
        candidates["low"] = ["jobs"]

    return candidates


def search_multiple_subreddits(query: str, candidates: dict, fetch_limit: int = 50, location: str = None) -> list:
    """
    Search multiple subreddits by priority level and evaluate performance.

    Priority levels:
    - "high": location-specific subreddits (r/georgia, r/dubai)
    - "medium": expat/topic-specific (r/expats, r/jobs)
    - "low": general fallback subreddits

    Args:
        query: Search query
        candidates: Dict with priority levels {"high": [...], "medium": [...], "low": [...]}
        fetch_limit: How many posts to fetch per subreddit
        location: Location name (for performance tracking)

    Returns:
        Combined list of posts from all subreddits (by priority)
    """
    from utils.scrapers import fetch_reddit_posts

    all_posts = []
    priority_order = ["high", "medium", "low"]
    subreddit_posts = {}  # Track posts per subreddit for evaluation

    for priority in priority_order:
        subs = candidates.get(priority, [])
        if not subs:
            continue

        print(f"🔍 Searching {priority}-priority subreddits: {subs[:3]}{'...' if len(subs) > 3 else ''}")

        for sr in subs[:4]:  # Max 4 per priority level
            try:
                posts = fetch_reddit_posts(query, subreddit=sr, limit=fetch_limit)
                # Ensure posts is a list
                if not isinstance(posts, list):
                    print(f"  ⚠️ r/{sr}: Invalid response")
                    continue

                # Add priority and subreddit to each post
                for post in posts:
                    if isinstance(post, dict):
                        post["_searched_subreddit"] = sr
                        post["_priority"] = priority
                all_posts.extend(posts)
                subreddit_posts[sr] = posts

                if posts:
                    print(f"  ✓ r/{sr}: {len(posts)} posts")
            except Exception as e:
                print(f"  ⚠️ r/{sr}: {str(e)[:60]}")
                continue

        # Early exit if we have enough from high-priority sources
        if priority == "high" and len(all_posts) >= fetch_limit:
            print(f"   → Enough from high-priority, skipping lower tiers")
            break

    # Evaluate performance of each subreddit
    if location:
        print(f"📊 Evaluating subreddit performance:")
        for sr, posts in subreddit_posts.items():
            evaluate_subreddit_performance(location, sr, posts, all_posts)

    print(f"📊 Total collected from all tiers: {len(all_posts)}")
    return all_posts


def calculate_relevance_score(post: dict, query_keywords: list) -> float:
    """
    Calculate relevance score based on keyword matching (substring matching).
    Simple scoring: how many keywords are found in the post.

    Args:
        post: Reddit post dict
        query_keywords: List of search keywords

    Returns:
        Relevance score (0.0 to 1.0)
    """
    if not query_keywords:
        return 0.5  # Neutral score if no keywords

    title = (post.get("title", "") or "").lower()
    summary = (post.get("summary", "") or "").lower()
    text = f"{title} {summary}"

    # Simple substring matching - count how many keywords appear
    matches = sum(1 for keyword in query_keywords if keyword.lower() in text)

    # Score: 0.0 to 1.0 based on keyword matches
    return matches / len(query_keywords) if query_keywords else 0.5


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


def analyze_score_distribution(posts: list) -> dict:
    """
    Analyze score distribution of collected posts.

    Args:
        posts: List of posts with _relevance_score

    Returns:
        Dict with avg_score, min_score, max_score, median_score
    """
    if not posts:
        return {"avg_score": 0, "min_score": 0, "max_score": 0, "median_score": 0}

    scores = [p.get("_relevance_score", 0) for p in posts]
    scores.sort()

    return {
        "avg_score": sum(scores) / len(scores),
        "min_score": min(scores),
        "max_score": max(scores),
        "median_score": scores[len(scores) // 2],
        "count": len(scores),
    }


def decide_dynamic_min_score(collected_count: int, target_count: int, current_distribution: dict) -> float:
    """
    Decide min_score dynamically based on current collection status.

    Args:
        collected_count: How many posts collected so far
        target_count: Target number of posts needed
        current_distribution: Score distribution from analyze_score_distribution()

    Returns:
        New min_score to use for next search
    """
    if collected_count == 0:
        return 0.3  # Start high

    progress = collected_count / target_count
    current_min = current_distribution.get("min_score", 0)
    current_median = current_distribution.get("median_score", 0)

    if progress < 0.3:  # Very early stage (0-30%)
        return current_min * 0.85  # Drop aggressively
    elif progress < 0.6:  # Mid stage (30-60%)
        return current_median * 0.9  # Drop moderately
    elif progress < 0.9:  # Near completion (60-90%)
        return current_min * 0.95  # Drop slightly
    else:  # Almost done (90%+)
        return current_min * 0.98  # Minimal drop


def adaptive_reddit_search(query_en: str, candidates: dict, query_keywords_en: list, target_count: int = 20, location: str = None) -> list:
    """
    Adaptively search multiple subreddits until target count is reached.
    Uses progressive threshold reduction and performance tracking.

    Strategy: Collect as many posts as possible, filter by relevance, and track subreddit performance.

    Args:
        query_en: Translated English query
        candidates: Dict with priority levels {"high": [...], "medium": [...], "low": [...]}
        query_keywords_en: Translated keywords for filtering
        target_count: Target number of posts to collect
        location: Detected location for performance tracking

    Returns:
        Sorted list of top posts meeting target count
    """
    all_collected = []
    current_min_score = 0.3  # Start with 1/3 keyword requirement (location + topic filter)
    attempt = 0
    max_attempts = 5

    while len(all_collected) < target_count and attempt < max_attempts:
        attempt += 1
        print(f"🔄 Attempt {attempt}/{max_attempts}: min_score={current_min_score:.2f} (collected: {len(all_collected)}/{target_count})")

        # Search multiple subreddits (with location for performance tracking)
        batch_posts = search_multiple_subreddits(query_en, candidates, fetch_limit=max(50, target_count * 3), location=location)
        print(f"   Raw posts from Reddit: {len(batch_posts)}")

        if not batch_posts:
            print(f"⚠️ No results from subreddits, stopping.")
            break

        # Filter with current min_score
        filtered = filter_and_rank_posts(batch_posts, query_keywords_en, min_score=current_min_score)
        print(f"   Filtered (score≥{current_min_score:.2f}): {len(filtered)}")

        if filtered:
            all_collected.extend(filtered)
            print(f"✓ Added {len(filtered)} posts (total: {len(all_collected)})")

        # Check if we have enough
        if len(all_collected) >= target_count:
            print(f"✓ Target reached!")
            break

        # If still not enough, lower the threshold gradually (but not below 0.15)
        if all_collected:
            dist = analyze_score_distribution(all_collected)
            # Progressive reduction: 0.30 → 0.25 → 0.20 → 0.15 (keep meaningful filtering)
            if len(all_collected) < target_count * 0.3:
                # Very low collection - reduce moderately
                current_min_score = max(0.15, current_min_score * 0.8)
            elif len(all_collected) < target_count * 0.6:
                # Some collection - reduce slightly
                current_min_score = max(0.15, current_min_score * 0.85)
            else:
                # Good progress - minimal reduction
                current_min_score = max(0.15, current_min_score * 0.9)
            print(f"📊 Score dist: min={dist['min_score']:.2f}, median={dist['median_score']:.2f}, avg={dist['avg_score']:.2f}")
            print(f"📉 Next threshold: {current_min_score:.2f}")
        else:
            # No posts collected yet - lower to 0.25 (still requires some keyword match)
            current_min_score = max(0.15, current_min_score * 0.8)

    # Deduplicate
    seen = set()
    unique_posts = []
    for post in all_collected:
        post_id = post.get("url", post.get("title", ""))
        if post_id not in seen:
            seen.add(post_id)
            unique_posts.append(post)

    print(f"   Deduped: {len(all_collected)} → {len(unique_posts)}")

    # Final sort by score (highest first)
    unique_posts.sort(key=lambda p: p.get("_relevance_score", 0), reverse=True)
    final_result = unique_posts[:target_count]
    print(f"   Returning top {len(final_result)}/{target_count}")

    return final_result


def load_subreddit_scores() -> None:
    """Load subreddit performance scores from file"""
    global SUBREDDIT_SCORES
    scores_file = OUTPUT_DIR / "subreddit_scores.json"
    if scores_file.exists():
        try:
            SUBREDDIT_SCORES = json.loads(scores_file.read_text(encoding="utf-8"))
            print(f"📊 Loaded subreddit scores from {scores_file}")
        except (json.JSONDecodeError, OSError):
            SUBREDDIT_SCORES = {}
    else:
        SUBREDDIT_SCORES = {}


def save_subreddit_scores():
    """Save subreddit performance scores to file"""
    scores_file = OUTPUT_DIR / "subreddit_scores.json"
    try:
        scores_file.write_text(json.dumps(SUBREDDIT_SCORES, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Failed to save subreddit scores: {e}")


def evaluate_subreddit_performance(location: str, subreddit: str, posts: list, all_collected: list) -> float:
    """
    Evaluate subreddit performance based on:
    - Number of posts collected
    - Match rate (posts with score >= 0.5)
    - Freshness (average post age)

    Returns normalized score (0.0 to 1.0)
    """
    if not posts:
        return 0.0

    # Calculate match rate
    matched = sum(1 for p in posts if p.get("_relevance_score", 0) >= 0.5)
    match_rate = matched / len(posts) if posts else 0.0

    # Calculate freshness (prefer recent posts)
    now_ts = datetime.now(timezone.utc).timestamp()
    ages = [now_ts - p.get("created_utc", now_ts) for p in posts]
    avg_age_days = sum(ages) / len(ages) / 86400 if ages else 999
    freshness = max(0.0, 1.0 - (avg_age_days / 30))  # Decay over 30 days

    # Composite score: 60% match rate, 40% freshness
    score = (match_rate * 0.6) + (freshness * 0.4)

    # Update global scores
    if location not in SUBREDDIT_SCORES:
        SUBREDDIT_SCORES[location] = {}

    # Exponential moving average: new_score = 0.7 * old_score + 0.3 * current_score
    old_score = SUBREDDIT_SCORES[location].get(subreddit, 0.5)
    new_score = (old_score * 0.7) + (score * 0.3)
    SUBREDDIT_SCORES[location][subreddit] = new_score

    print(f"   📈 r/{subreddit}: match={match_rate:.1%}, fresh={freshness:.1%} → score={new_score:.2f}")
    return score


def get_sorted_candidates(location: str) -> list:
    """
    Get subreddit candidates sorted by performance scores.
    High-scoring subreddits first, new candidates mixed in for exploration.

    Returns: sorted list of subreddit names
    """
    pool = LOCATION_SUBREDDIT_POOLS.get(location, {})
    candidates = pool.get("candidates", [])

    if not candidates:
        return []

    # Get scores for this location
    location_scores = SUBREDDIT_SCORES.get(location, {})

    # Sort by score (descending) with exploration boost for new subreddits
    def score_key(sr):
        score = location_scores.get(sr, 0.5)  # Default 0.5 for new subreddits
        # Boost for new subreddits (not yet evaluated)
        if sr not in location_scores:
            score += 0.1  # Explore new candidates
        return score

    sorted_candidates = sorted(candidates, key=score_key, reverse=True)

    print(f"   Candidate order: {sorted_candidates}")
    return sorted_candidates


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
    except (json.JSONDecodeError, OSError):
        return {}


def parse_days(text: str) -> int:
    """Extract days from message. Returns None if no specific day filter requested."""
    if "3일" in text or "3day" in text:
        return 3
    elif "1일" in text or "1day" in text or "오늘" in text:
        return 1
    elif "7일" in text or "7day" in text or "일주" in text:
        return 7
    elif "30일" in text or "30day" in text or "한달" in text or "한 달" in text:
        return 30
    return None  # No specific filter requested


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


def handle_reddit_request(text: str) -> None:
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

    # Detect location from query (for performance tracking)
    detected_location = None
    query_lower = query.lower()
    for location, pool_data in LOCATION_SUBREDDIT_POOLS.items():
        keywords = pool_data.get("keywords", [])
        for keyword in keywords:
            if keyword.lower() in query_lower:
                detected_location = location
                break
        if detected_location:
            break

    # Check for days filter (only if explicitly specified: "1일", "3일", "7일", etc.)
    days_filter = parse_days(query)
    if days_filter:
        # Remove the date keyword from query for Reddit search
        for keyword in ["1일", "3일", "7일", "30일", "1day", "3day", "7day", "30day", "오늘", "일주", "한달", "한 달"]:
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

    # Keep location in query for better filtering
    # Remove duplicate location keywords only
    query_lower = query.lower()
    for location, pool_data in LOCATION_SUBREDDIT_POOLS.items():
        keywords = pool_data.get("keywords", [])
        for keyword in keywords[1:]:  # Skip first keyword, remove duplicates
            if keyword.lower() in query_lower:
                query = query.replace(keyword, " ").strip()

    # Translate query to English for Reddit search (if Korean detected)
    query_en = translate_text(query, target_lang="en")
    print(f"🌐 Translated '{query}' → '{query_en}'")

    # If explicit subreddit specified, search only that one
    if subreddit:
        from utils.scrapers import fetch_reddit_posts
        fetch_limit = max(50, result_limit * 2) if days_filter else result_limit * 2
        posts = fetch_reddit_posts(query_en, subreddit, limit=fetch_limit)
    else:
        # Multi-subreddit adaptive search with priority-based collection
        candidates = get_subreddit_candidates(query_original, query_en.split())

        # Log candidates by priority
        high = candidates.get("high", [])
        medium = candidates.get("medium", [])
        low = candidates.get("low", [])
        print(f"📋 Subreddit candidates:")
        if high:
            print(f"   🔴 HIGH (location): {high[:3]}{'...' if len(high) > 3 else ''}")
        if medium:
            print(f"   🟡 MEDIUM (topic/expat): {medium[:3]}{'...' if len(medium) > 3 else ''}")
        if low:
            print(f"   🟢 LOW (fallback): {low[:3]}{'...' if len(low) > 3 else ''}")

        # Extract keywords for filtering
        query_keywords_en = [kw.strip() for kw in query_en.split() if len(kw.strip()) > 2]

        # Adaptive search: collect until target_count is reached with dynamic min_score adjustment
        # Pass detected_location for performance tracking
        posts = adaptive_reddit_search(query_en, candidates, query_keywords_en, target_count=result_limit, location=detected_location)

    # Filter by days if specified
    posts_before_date_filter = len(posts)
    if days_filter:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_filter)
        print(f"📅 Applying date filter: last {days_filter} days (cutoff: {cutoff})")
        posts = [p for p in posts if p.get("created_utc", 0) > cutoff.timestamp()]
        print(f"   After date filter: {posts_before_date_filter} → {len(posts)}")

    # Limit to requested number of results
    posts = posts[:result_limit]
    print(f"   Final result (limited to {result_limit}): {len(posts)}")

    # Save performance scores
    save_subreddit_scores()

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


def handle_message(text: str) -> None:
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
                send_telegram_text(f"❌ Reddit 요청 처리 중 오류: {str(e)}")
            return

        if prefix in ("분석", "analyze"):
            query = parts[1].strip()
            if not query:
                send_telegram_text("사용법: 분석. 회사명 포지션 위치\n예) 분석. Stake.com Product Manager UAE")
                return
            try:
                send_telegram_text(f"🔍 career-ops 분석 중...\n{query}")
                from services.career_bridge import analyze
                result = analyze(query)
                # Split if too long for Telegram (4096 char limit)
                if len(result) <= 4000:
                    send_telegram_text(result)
                else:
                    chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
                    for chunk in chunks:
                        send_telegram_text(chunk)
            except Exception as e:
                print(f"❌ Career bridge error: {e}")
                send_telegram_text(f"❌ 분석 오류: {str(e)}")
            return

    from utils.notifications import send_telegram_messages_chunked

    jobs_data = get_jobs_data()
    all_jobs = jobs_data.get("all_tracked_jobs", [])

    # Check if it's a date filter or search query
    days = parse_days(text)
    is_date_query = days is not None

    if is_date_query:
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


def poll_messages() -> None:
    """Poll Telegram API for new messages"""
    # Load previous subreddit performance scores
    load_subreddit_scores()

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
                # Handle inline button callback
                callback = update.get("callback_query")
                if callback:
                    callback_id = callback.get("id")
                    callback_data = callback.get("data", "")
                    user = callback.get("from", {}).get("first_name", "User")
                    # Acknowledge the callback immediately
                    ack_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery?callback_query_id={callback_id}"
                    try:
                        urllib.request.urlopen(ack_url, timeout=5)
                    except Exception:
                        pass
                    if callback_data.startswith("a:"):
                        key = callback_data[2:]
                        description = _get_job_description(key)
                        url = _resolve_url(key)
                        print(f"📨 {user} [분석 버튼]: {url}")
                        try:
                            if description:
                                send_telegram_text(f"🔍 career-ops 분석 중...\n(공고 요약)")
                                from services.career_bridge import analyze
                                result = analyze(description)
                            else:
                                send_telegram_text(f"🔍 career-ops 분석 중...\n{url}")
                                from services.career_bridge import analyze
                                result = analyze(url)
                            chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
                            for chunk in chunks:
                                send_telegram_text(chunk)
                        except Exception as e:
                            send_telegram_text(f"❌ 분석 오류: {e}")
                    offset = update.get("update_id", 0) + 1
                    continue

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
