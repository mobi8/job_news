#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram channel job scraper - fetches jobs from public channels"""

from __future__ import annotations

import json
import sys
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import watch_logger
from utils.models import JobPosting
from utils.db import Database

TELEGRAM_CHANNELS = {
    "uaejobsdaily2025": "UAE Jobs Daily",
    "job_crypto_uae": "Crypto Jobs UAE",
    "cryptojobslist": "Crypto Jobs List",
    "hr1win": "1WIN HR Channel",
}

REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def scrape_channel(channel_username: str) -> tuple[list[dict], Optional[str]]:
    """
    Scrape a single Telegram public channel.

    Returns:
        (messages list, error message or None)
    """
    url = f"https://t.me/s/{channel_username}"

    try:
        watch_logger.info(f"Fetching Telegram channel: @{channel_username}")
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)

        if resp.status_code != 200:
            error = f"HTTP {resp.status_code}"
            watch_logger.warning(f"  ✗ @{channel_username}: {error}")
            return [], error

        soup = BeautifulSoup(resp.content, "html.parser")
        msg_divs = soup.find_all("div", class_="tgme_widget_message_bubble")

        messages = []
        for div in msg_divs:
            msg = {}

            # Extract text
            text_elem = div.find("div", class_="tgme_widget_message_text")
            if text_elem:
                msg["text"] = text_elem.get_text(strip=True)

            # Extract links
            links = div.find_all("a", href=True)
            msg["links"] = [link.get("href") for link in links if link.get("href")]

            # Extract timestamp
            time_elem = div.find("time")
            if time_elem:
                msg["timestamp"] = time_elem.get("datetime")

            if msg.get("text"):
                messages.append(msg)

        watch_logger.info(f"  ✓ @{channel_username}: Found {len(messages)} messages")
        return messages, None

    except requests.Timeout:
        error = "Request timeout"
        watch_logger.error(f"  ✗ @{channel_username}: {error}")
        return [], error
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        watch_logger.error(f"  ✗ @{channel_username}: {error}")
        return [], error


def scrape_all_channels() -> Dict[str, Any]:
    """Scrape all configured Telegram channels.

    Returns:
        Dict with results: {channel: {messages: [...], error: None/str}, ...}
    """
    watch_logger.info("="*60)
    watch_logger.info("Starting Telegram channel scraping")
    watch_logger.info("="*60)

    results = {}
    total_messages = 0

    for channel_username, channel_name in TELEGRAM_CHANNELS.items():
        messages, error = scrape_channel(channel_username)
        total_messages += len(messages)
        results[channel_username] = {
            "name": channel_name,
            "messages": messages,
            "error": error,
            "count": len(messages),
        }

    watch_logger.info("="*60)
    watch_logger.info(
        f"Telegram scraping complete: {total_messages} messages from {len(TELEGRAM_CHANNELS)} channels"
    )
    watch_logger.info("="*60)

    return results


def extract_job_postings(message_text: str) -> Optional[Dict[str, str]]:
    """
    Extract job posting info from Telegram message text.
    Handles both multi-line and single-line formats with emoji markers.
    """
    result = {}

    # Try single-line format: 🔍[Role]💼Company: [Company]📍Location: [Location]🔗
    if "💼" in message_text:
        # Extract role: text between 🔍/start and 💼
        import re
        role_match = re.search(r'[🔍]?(.+?)(?:💼|🏛️)', message_text)
        if role_match:
            result["role"] = role_match.group(1).strip()

        # Extract location: text after 📍 and before 🔗 or end
        loc_match = re.search(r'(?:📍|🌍)([^🔗]*)', message_text)
        if loc_match:
            loc_text = loc_match.group(1).strip()
            # Remove "Location:" prefix if present
            loc_text = re.sub(r'^Location:\s*', '', loc_text)
            if loc_text:
                result["location"] = loc_text

    # Fallback to multi-line format
    if not result:
        lines = message_text.split("\n")
        for line in lines:
            line = line.strip()
            if "💼" in line or "🏛️" in line:
                result["role"] = line.replace("💼", "").replace("🏛️", "").strip()
            elif "🌍" in line or "📍" in line:
                result["location"] = line.replace("🌍", "").replace("📍", "").strip()

    return result if result else None


def clean_description(text: str) -> str:
    """Clean Telegram message text for display: remove emoji, URLs, timestamps"""
    import re

    # Remove timestamps (ISO format)
    text = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s]*', '', text)

    # Remove URLs
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'→Https?://[^\s]+', '', text)

    # Replace emoji with space (so adjacent words don't get concatenated)
    text = re.sub(r'[^\w\s,.$%/()--￿]', lambda m: ' ' if ord(m.group()) > 127 else m.group(), text)

    # Remove remaining non-ASCII characters (other emoji/special chars)
    text = re.sub(r'[^\w\s,.$%/()-]', '', text, flags=re.UNICODE)

    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text[:300] if text else ""


def convert_to_job_posting(message: Dict, channel: str, channel_name: str) -> Optional[JobPosting]:
    """Convert Telegram message to JobPosting object"""
    text = message.get("text", "")
    if not text or len(text) < 10:
        return None

    # Extract basic info
    extracted = extract_job_postings(text)
    if not extracted:
        return None

    # Generate source job ID from timestamp and text hash
    timestamp = message.get("timestamp", datetime.utcnow().isoformat())
    text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
    source_job_id = f"{timestamp.replace('T', '-').replace(':', '')[:-6]}-{text_hash}"

    # Get first link as job URL
    links = message.get("links", [])
    job_url = next((l for l in links if "http" in l and "t.me" not in l), "")

    if not job_url:
        return None

    # Parse company and title from extracted data
    import re
    role_line = extracted.get("role", "")
    company = "Unknown"
    company_match = re.search(r'(?:Company:\s*|@)([^📍🔗\n]+?)(?=📍|🔗|$)', text)
    if company_match:
        company_text = company_match.group(1).strip()
        company = clean_description(company_text).title() or "Unknown"

    # Fallback: parse from role line if "at" pattern exists
    if company == "Unknown" and "at " in role_line.lower():
        parts = role_line.lower().split("at ")
        if len(parts) > 1:
            company = clean_description(parts[1].split(",")[0].strip()).title()

    title = role_line.split(" at ")[0].strip() if " at " in role_line else role_line
    title = clean_description(title)
    location = clean_description(extracted.get("location", "UAE"))

    # Detect if job is remote
    is_remote = 0
    location_lower = location.lower().strip()
    if location_lower.startswith('remote') or location_lower.startswith('anywhere') or '100% remote' in location_lower:
        is_remote = 1

    return JobPosting(
        source=f"telegram_{channel}",
        source_job_id=source_job_id,
        title=title or "Job Posting",
        company=company,
        location=location,
        url=job_url,
        description=clean_description(text),
        country="UAE",
        remote=is_remote,
        match_score=70,  # Default score for Telegram jobs
        first_seen_at=timestamp,
        last_seen_at=timestamp,
    )


def save_jobs_to_db(db_path: str, jobs: List[JobPosting]) -> int:
    """Save job postings to database"""
    if not jobs:
        return 0

    db = Database(Path(db_path))
    inserted, _ = db.upsert_jobs(jobs, return_jobs=True)
    return inserted


def scrape_and_save(db_path: str) -> Dict[str, Any]:
    """Scrape all Telegram channels and save to database"""
    results = scrape_all_channels()

    total_jobs = 0
    total_saved = 0

    for channel_username, channel_data in results.items():
        channel_name = channel_data.get("name", "")
        messages = channel_data.get("messages", [])

        watch_logger.info(f"Converting {len(messages)} messages from @{channel_username}...")

        # Convert messages to JobPosting objects
        jobs = []
        for msg in messages:
            job = convert_to_job_posting(msg, channel_username, channel_name)
            if job:
                jobs.append(job)

        # Save to database
        if jobs:
            saved = save_jobs_to_db(db_path, jobs)
            total_jobs += len(jobs)
            total_saved += saved
            watch_logger.info(f"  ✓ Saved {saved}/{len(jobs)} jobs from @{channel_username}")
        else:
            watch_logger.info(f"  - No valid jobs found in @{channel_username}")

    watch_logger.info(f"Telegram scraping complete: {total_saved}/{total_jobs} jobs saved to database")

    return {
        "total_messages": sum(c.get("count", 0) for c in results.values()),
        "total_jobs": total_jobs,
        "total_saved": total_saved,
        "channels": results,
    }


if __name__ == "__main__":
    import os
    db_path = os.getenv("DB_PATH", "/Users/lewis/Desktop/agent/outputs/jobs.sqlite3")
    result = scrape_and_save(db_path)
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
