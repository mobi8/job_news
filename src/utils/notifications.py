#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import logging
import os
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import timedelta
from typing import Any, Dict, List, Optional

from .db import Database
from .models import JobPosting, NewsItem
from .scoring import focus_records, source_label
from .utils import (
    load_resume_text,
    load_telegram_sent_history,
    notification_key,
    prune_telegram_sent_history,
    save_telegram_sent_history,
    utc_now,
)
from .logger import notifications_logger
from .template_renderer import render_template

logger = notifications_logger

SOURCE_COUNTRY_OVERRIDES = {
    "jobvite_pragmaticplay": "UAE",
    "smartrecruitment": "UAE",
    "igamingrecruitment": "UAE",
    "jobrapido_uae": "UAE",
    "jobleads": "UAE",
    "telegram_job_crypto_uae": "UAE",
    "telegram_cryptojobslist": "UAE",
    "indeed_uae": "UAE",
    "linkedin_public": "UAE",
    "linkedin_malta": "Malta",
}


def _job_attr(job: Any, name: str) -> str:
    if isinstance(job, dict):
        return str(job.get(name, "") or "")
    return str(getattr(job, name, "") or "")


def detect_country_from_location(location: str) -> str:
    if not location:
        return ""
    location_lower = location.lower()
    # Exclude USA (미국 in Korean, usa/us/united states in English)
    # Must check for "미국 조지아" (US Georgia) before checking for "georgia"
    if any(x in location_lower for x in ["미국", "usa", "united states", "american gaming", "ags -", "fanduel", "atlanta", "duluth", "alpharetta", "sandy", "remote in", "acc", "anduril"]):
        return ""
    if "미국 조지아" in location_lower:  # Korean "US Georgia" - explicitly exclude
        return ""
    if "malta" in location_lower or "valletta" in location_lower or "몰타" in location_lower:
        return "Malta"
    if "georgia" in location_lower or "조지아" in location_lower or "tbilisi" in location_lower or "트빌리시" in location_lower or "batumi" in location_lower or "바투미" in location_lower:
        return "Georgia"
    if "dubai" in location_lower or "두바이" in location_lower or "united arab emirates" in location_lower or "uae" in location_lower:
        return "UAE"
    return ""


def country_label_for_job(job: Any) -> str:
    source = _job_attr(job, "source").lower()
    if not source:
        return ""
    country = SOURCE_COUNTRY_OVERRIDES.get(source)
    if country:
        return country
    location = _job_attr(job, "location")
    return detect_country_from_location(location)


def country_line_for_jobs(jobs: List[Any]) -> str:
    counts: Dict[str, int] = {}
    for job in jobs:
        label = country_label_for_job(job)
        if not label:
            continue
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return ""
    sorted_counts = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return " | ".join(f"{label} {count}" for label, count in sorted_counts)


def build_job_template_items(jobs: List[Any], limit: int | None = None) -> List[Dict[str, str]]:
    trimmed = jobs[:limit] if isinstance(limit, int) else list(jobs)
    items: List[Dict[str, str]] = []
    for job in trimmed:
        label = html.escape(f"{_job_attr(job, 'company')} | {_job_attr(job, 'title')}")
        url = html.escape(_job_attr(job, "url"), quote=True)
        country = country_label_for_job(job) or "Other"
        items.append({"label": label, "url": url, "country": country})
    return items


def group_job_items_by_country(items: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    grouped: OrderedDict[str, List[Dict[str, str]]] = OrderedDict()
    for item in items:
        country = item.get("country") or "Other"
        grouped.setdefault(country, []).append(item)
    return [{"country": country, "jobs": jobs} for country, jobs in grouped.items()]


def source_total_counts(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for record in records:
        counts[record["source"]] = counts.get(record["source"], 0) + 1
    return [
        {"source": source, "jobs": jobs}
        for source, jobs in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def source_daily_counts(records: List[Dict[str, Any]], days: int = 14) -> List[Dict[str, Any]]:
    from datetime import datetime
    cutoff = utc_now().date() - timedelta(days=days)
    counts: Dict[tuple[str, str], int] = {}
    for record in records:
        seen_value = record.get("first_seen_at")
        if not seen_value:
            continue
        seen_date = datetime.fromisoformat(seen_value).date()
        if seen_date < cutoff:
            continue
        key = (record["source"], seen_date.isoformat())
        counts[key] = counts.get(key, 0) + 1
    items = [
        {"source": source, "seen_date": seen_date, "jobs": jobs}
        for (source, seen_date), jobs in counts.items()
    ]
    return sorted(items, key=lambda item: (item["source"], item["seen_date"]), reverse=True)


def send_telegram_text(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": "true",
            "parse_mode": "HTML",
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20):
            logger.info("Telegram notification sent.")
        return True
    except Exception as exc:
        logger.warning("Telegram notification failed: %s", exc)
        return False


def maybe_send_telegram(inserted: int, jobs: List[JobPosting]) -> None:
    # 중복 제거: 이전에 보낸 job 제외
    sent_history = prune_telegram_sent_history(load_telegram_sent_history())

    def job_notification_key(job: JobPosting) -> str:
        return "|".join([job.source, job.source_job_id, job.title, job.company])

    unsent_jobs = [job for job in jobs if job_notification_key(job) not in sent_history]

    country_line = country_line_for_jobs(unsent_jobs)
    job_items = build_job_template_items(unsent_jobs, limit=3)
    country_groups = group_job_items_by_country(job_items)
    context = {
        "new_count": len(unsent_jobs),
        "country_line": country_line,
        "country_groups": country_groups,
    }

    message_text = render_template("telegram/job_alert.txt", context)
    logger.debug("Rendered job_alert template: %s", message_text)
    if not send_telegram_text(message_text):
        return

    if not unsent_jobs:
        logger.info("No new jobs to mark as sent, but sent a zero-update Telegram alert.")
        return

    # sent_history 업데이트
    sent_at = utc_now().isoformat()
    for job in unsent_jobs:
        sent_history[job_notification_key(job)] = sent_at
    save_telegram_sent_history(prune_telegram_sent_history(sent_history))


def send_incremental_summary(
    db: Database,
    hours: float = 3,
    limit: int = 8,
    allowed_sources: Optional[set[str]] = None,
) -> None:
    resume_text = load_resume_text()
    sent_history = prune_telegram_sent_history(load_telegram_sent_history())
    new_jobs = focus_records(db.jobs_first_seen_since(hours), resume_text)
    if allowed_sources is not None:
        new_jobs = [job for job in new_jobs if job["source"] in allowed_sources]
    unsent_jobs = [job for job in new_jobs if notification_key(job) not in sent_history]
    if new_jobs and not unsent_jobs:
        context = {
            "hours": hours,
            "job_count": 0,
            "country_line": "",
            "source_counts": False,
            "source_line": "",
            "jobs": [],
            "country_groups": [],
        }
        message_text = render_template("telegram/incremental_summary.txt", context)
        logger.debug("Rendered incremental_summary (no new unsent): %s", message_text)
        if not send_telegram_text(message_text):
            return
        save_telegram_sent_history(sent_history)
        logger.info("Skipped duplicate Telegram jobs for the last %s hours.", hours)
        return
    new_jobs = unsent_jobs
    if not new_jobs:
        source_line = ""
        if allowed_sources:
            source_line = " | ".join(
                f"{source_label(source)} 0"
                for source in sorted(allowed_sources, key=source_label)
            )
        context = {
            "hours": hours,
            "job_count": 0,
            "source_counts": bool(source_line),
            "source_line": source_line,
            "country_line": "",
            "jobs": [],
        }
        message_text = render_template("telegram/incremental_summary.txt", context)
        logger.debug("Rendered incremental_summary (no jobs): %s", message_text)
        if not send_telegram_text(message_text):
            return
        logger.info("No new jobs for the last %s hours. Sent zero-update Telegram summary.", hours)
        return

    source_counts = source_total_counts(new_jobs)
    source_line = ""
    if source_counts:
        source_line = " | ".join(
            f"{source_label(item['source'])} {item['jobs']}" for item in source_counts
        )
    country_line = country_line_for_jobs(new_jobs)

    job_items = build_job_template_items(new_jobs, limit=limit)
    country_groups = group_job_items_by_country(job_items)

    context = {
        "hours": hours,
        "job_count": len(new_jobs),
        "source_counts": bool(source_counts),
        "source_line": source_line,
        "country_line": country_line,
        "country_groups": country_groups,
        "jobs": job_items,
    }
    message_text = render_template("telegram/incremental_summary.txt", context)
    logger.debug("Rendered incremental_summary: %s", message_text)
    if not send_telegram_text(message_text):
        return

    sent_at = utc_now().isoformat()
    for job in new_jobs:
        sent_history[notification_key(job)] = sent_at
    save_telegram_sent_history(prune_telegram_sent_history(sent_history))


def send_daily_summary(db: Database, limit: int = 100) -> None:
    resume_text = load_resume_text()
    new_today = focus_records(db.jobs_first_seen_since(24), resume_text)
    all_focused = focus_records(db.fetch_all_jobs(), resume_text)

    # 중복 제거: 이전에 보낸 job 제외
    sent_history = prune_telegram_sent_history(load_telegram_sent_history())
    unsent_today = [job for job in new_today if notification_key(job) not in sent_history]

    source_today = source_total_counts(unsent_today)
    source_total = source_total_counts(all_focused)

    context = {
        "new_count": len(unsent_today),
        "source_today": [
            {"label": source_label(item["source"]), "count": item["jobs"]}
            for item in source_today
        ],
        "source_total": [
            {"label": source_label(item["source"]), "count": item["jobs"]}
            for item in source_total
        ],
        "jobs": [
            {
                "label": html.escape(f"{job['company']} | {job['title']}"),
                "url": html.escape(job["url"], quote=True),
            }
            for job in unsent_today[:limit]
        ],
    }

    message_text = render_template("telegram/daily_summary.txt", context)
    logger.debug("Rendered daily_summary: %s", message_text)
    if len(message_text) <= 4000:
        if not send_telegram_text(message_text):
            return
    else:
        logger.warning(
            "Daily summary (%d chars) exceeds Telegram limit; chunking into shorter messages.",
            len(message_text),
        )
        if not send_telegram_messages_chunked(message_text.splitlines()):
            return

    if not unsent_today:
        logger.info("No new unsent jobs in last 24h, but sent a zero-update daily summary.")
        return

    # sent_history 업데이트
    sent_at = utc_now().isoformat()
    for job in unsent_today:
        sent_history[notification_key(job)] = sent_at
    save_telegram_sent_history(prune_telegram_sent_history(sent_history))


def send_telegram_messages_chunked(lines: List[str], max_length: int = 4000) -> bool:
    """
    텔레그램 메시지를 청크로 나누어 전송합니다.
    텔레그램 API 제한(4096자)을 고려합니다.
    """
    messages = []
    current_message = []
    current_length = 0
    
    for line in lines:
        line_length = len(line) + 1  # +1 for newline
        
        if current_length + line_length > max_length and current_message:
            # 현재 메시지 저장하고 새 메시지 시작
            messages.append("\n".join(current_message))
            current_message = [line]
            current_length = line_length
        else:
            current_message.append(line)
            current_length += line_length
    
    if current_message:
        messages.append("\n".join(current_message))
    
    # 각 메시지 전송
    for i, message in enumerate(messages):
        if i > 0:
            # 첫 번째 메시지 이후에는 지연 추가 (API 제한 방지)
            import time
            time.sleep(0.5)
        if not send_telegram_text(message):
            return False
        logger.info(f"Sent message chunk {i+1}/{len(messages)} ({len(message)} chars)")
    return True


def send_news_summary(news_items: List[NewsItem], limit: int = 100, db: Database | None = None) -> None:
    """
    Send topic-based news summary via Telegram.
    If db is provided, uses compute_news_topics(). Otherwise sends raw news items.

    Parameters:
    - limit: 최대 보낼 기사 수 (기본값 100)
    """
    if not news_items:
        return

    sent_history = prune_telegram_sent_history(load_telegram_sent_history())
    unsent = [item for item in news_items if item.url not in sent_history]

    if not unsent:
        logger.info("All news items already sent. Skipping Telegram news summary.")
        return

    if db is None:
        # Simple list format for raw news items
        lines = [f"<b>📰 Industry News ({len(unsent)} new)</b>", ""]
        for item in unsent[:limit]:
            title = html.escape(item.title[:80])
            url = html.escape(item.url, quote=True)
            lines.append(f"• <a href=\"{url}\">{title}</a>")

        message_text = "\n".join(lines)
        if len(message_text) > 4000:
            logger.warning("Telegram message too long (%d chars), truncating.", len(message_text))
            lines = lines[:15]
            lines.append(f"\n... and {len(unsent) - 15} more articles")
            message_text = "\n".join(lines)

        logger.debug("Rendered simple news_summary: %s", message_text)
        if not send_telegram_text(message_text):
            return
    else:
        # Topic-based approach
        topics = db.compute_news_topics(168)
        if not topics:
            logger.info("No topics found from news items.")
            return

        # Filter topics to only include unsent articles
        unsent_urls = {item.url for item in unsent}
        topics_with_unsent = []
        for topic in topics:
            topic_unsent = [a for a in topic["articles"] if a["url"] in unsent_urls]
            if not topic_unsent:
                continue
            topic["articles"] = topic_unsent[:15]
            topic["article_count"] = len(topic_unsent)
            topics_with_unsent.append(topic)

        if not topics_with_unsent:
            logger.info("No new articles in any topic. Skipping Telegram news summary.")
            return

        # Build context for full version
        max_topics = min(len(topics_with_unsent), 5)
        total_sent_count = sum(
            min(len(t["articles"]), 10) for t in topics_with_unsent[:max_topics]
        )

        context_full = {
            "total_articles": len(unsent),
            "topics": [
                {
                    "label_ko": html.escape(topic["label_ko"]),
                    "article_count": topic["article_count"],
                    "articles": [
                        {
                            "title": html.escape(a["title"][:70]),
                            "url": html.escape(a["url"], quote=True),
                        }
                        for a in topic["articles"][:10]
                    ],
                }
                for topic in topics_with_unsent[:max_topics]
            ],
            "showing_partial": total_sent_count < len(unsent),
            "shown_count": total_sent_count,
        }

        message_text = render_template("telegram/news_summary.txt", context_full)
        logger.debug("Rendered news_summary (full): %s", message_text)

        # Check length and use simplified version if needed
        if len(message_text) > 4000:
            logger.warning("Telegram message too long (%d chars), using simplified version.", len(message_text))
            context_simple = {
                "total_articles": len(unsent),
                "topics": [
                    {
                        "label_ko": html.escape(topic["label_ko"]),
                        "article_count": topic["article_count"],
                        "articles": [
                            {
                                "title": html.escape(a["title"][:60]),
                                "url": html.escape(a["url"], quote=True),
                            }
                            for a in topic["articles"][:2]
                        ],
                    }
                    for topic in topics_with_unsent[:3]
                ],
            }
            message_text = render_template("telegram/news_summary_simplified.txt", context_simple)
            logger.debug("Rendered news_summary (simplified): %s", message_text)

        if not send_telegram_text(message_text):
            return

    # Update sent_history
    sent_at = utc_now().isoformat()
    for item in unsent:
        sent_history[item.url] = sent_at
    save_telegram_sent_history(prune_telegram_sent_history(sent_history))
    logger.info("Sent news summary via Telegram. %d articles marked as sent.", len(unsent))


def _news_source_label(source: str) -> str:
    """Convert news source code to human-readable label."""
    mapping = {
        "rss_igaming_business": "iGaming Business",
        "rss_fintech_uae": "Fintech News UAE",
    }
    return mapping.get(source, source)
