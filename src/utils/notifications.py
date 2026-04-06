#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import logging
import os
import urllib.parse
import urllib.request
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

logger = notifications_logger


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


def send_telegram_text(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

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
    with urllib.request.urlopen(request, timeout=20):
        logger.info("Telegram notification sent.")


def maybe_send_telegram(inserted: int, jobs: List[JobPosting]) -> None:
    if inserted <= 0:
        return

    # 중복 제거: 이전에 보낸 job 제외
    sent_history = prune_telegram_sent_history(load_telegram_sent_history())

    def job_notification_key(job: JobPosting) -> str:
        return "|".join([job.source, job.source_job_id, job.title, job.company])

    unsent_jobs = [job for job in jobs if job_notification_key(job) not in sent_history]

    if not unsent_jobs:
        logger.info("All jobs already sent in previous notifications, skipping.")
        return

    top_jobs = unsent_jobs[:3]
    message_lines = [f"New UAE job matches: {len(unsent_jobs)}", ""]
    for job in top_jobs:
        label = html.escape(f"{job.company} | {job.title}")
        message_lines.append(f'- <a href="{html.escape(job.url, quote=True)}">{label}</a>')
    send_telegram_text("\n".join(message_lines))

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
        lines = [f"New jobs in last {hours}h: 0", "", "Previously sent jobs already notified."]
        send_telegram_text("\n".join(lines))
        save_telegram_sent_history(sent_history)
        logger.info("Skipped duplicate Telegram jobs for the last %s hours.", hours)
        return
    new_jobs = unsent_jobs
    if not new_jobs:
        lines = [f"New jobs in last {hours}h: 0"]
        if allowed_sources:
            lines.extend(
                [
                    "",
                    " | ".join(
                        f"{source_label(source)} 0"
                        for source in sorted(allowed_sources, key=source_label)
                    ),
                ]
            )
        send_telegram_text("\n".join(lines))
        logger.info("No new jobs for the last %s hours. Sent zero-update Telegram summary.", hours)
        return

    source_counts = source_total_counts(new_jobs)
    lines = [f"New jobs in last {hours}h: {len(new_jobs)}", ""]

    if source_counts:
        counts_line = " | ".join(f"{source_label(item['source'])} {item['jobs']}" for item in source_counts)
        lines.append(counts_line)
        lines.append("")

    for job in new_jobs[:limit]:
        label = html.escape(f"{job['company']} | {job['title']}")
        lines.append(f'- <a href="{html.escape(job["url"], quote=True)}">{label}</a>')

    send_telegram_text("\n".join(lines))
    sent_at = utc_now().isoformat()
    for job in new_jobs:
        sent_history[notification_key(job)] = sent_at
    save_telegram_sent_history(prune_telegram_sent_history(sent_history))


def send_daily_summary(db: Database, limit: int = 10) -> None:
    resume_text = load_resume_text()
    new_today = focus_records(db.jobs_first_seen_since(24), resume_text)
    all_focused = focus_records(db.fetch_all_jobs(), resume_text)

    # 중복 제거: 이전에 보낸 job 제외
    sent_history = prune_telegram_sent_history(load_telegram_sent_history())
    unsent_today = [job for job in new_today if notification_key(job) not in sent_history]

    # 새 공고가 없으면 메시지를 보내지 않음
    if not unsent_today:
        logger.info("No new unsent jobs in last 24h. Skipping daily summary.")
        return

    source_today = source_total_counts(unsent_today)
    source_total = source_total_counts(all_focused)

    lines = [
        f"<b>🆕 Daily Jobs ({len(unsent_today)} new)</b>",
        "",
    ]

    # 새 공고 소스별 현황
    if source_today:
        lines.append("<b>By Source (new):</b>")
        for item in source_today:
            lines.append(f"  {source_label(item['source'])}: {item['jobs']}")
        lines.append("")

    # 전체 추적 현황
    if source_total:
        lines.append("<b>Tracked Totals:</b>")
        for item in source_total:
            lines.append(f"  {source_label(item['source'])}: {item['jobs']}")
        lines.append("")

    # 신규 매칭 공고
    lines.append("<b>Top Matches:</b>")
    for i, job in enumerate(unsent_today[:limit], 1):
        label = html.escape(f"{job['company']} | {job['title']}")
        lines.append(f"{i}. <a href=\"{html.escape(job['url'], quote=True)}\">{label}</a>")

    send_telegram_text("\n".join(lines))

    # sent_history 업데이트
    sent_at = utc_now().isoformat()
    for job in unsent_today:
        sent_history[notification_key(job)] = sent_at
    save_telegram_sent_history(prune_telegram_sent_history(sent_history))


def send_telegram_messages_chunked(lines: List[str], max_length: int = 4000) -> None:
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
        send_telegram_text(message)
        logger.info(f"Sent message chunk {i+1}/{len(messages)} ({len(message)} chars)")


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

    # 발송 제한: 실제로 보낼 최대 기사 수
    actual_limit = min(limit, len(unsent))
    
    # 소스 라벨 매핑
    source_labels = {
        "rss_igaming_business": "🎮 iGaming Business",
        "rss_fintech_uae": "💰 Fintech UAE",
        "rss_intergame_news": "🎲 InterGame News",
        "rss_intergame_crypto": "₿ InterGame Crypto",
        "rss_intergame_all": "🎰 InterGame All",
        "rss_intergame_abbrev": "📰 InterGame Abbrev",
        "rss_finextra_headlines": "📈 FinExtra Headlines",
        "rss_finextra_payments": "💳 FinExtra Payments",
        "rss_finextra_crypto": "🔗 FinExtra Crypto",
    }

    if db is None:
        # 단순 리스트 형식으로 모든 기사 보내기
        lines = [f"<b>📰 Industry News ({len(unsent)} new)</b>", ""]
        for item in unsent[:limit]:
            title = html.escape(item.title[:80])
            url = html.escape(item.url, quote=True)
            lines.append(f"• <a href=\"{url}\">{title}</a>")
        
        # 텔레그램 메시지 길이 제한(4096자) 확인
        message_text = "\n".join(lines)
        if len(message_text) > 4000:
            logger.warning("Telegram message too long (%d chars), truncating.", len(message_text))
            # 메시지를 분할하거나 줄임
            lines = lines[:15]  # 처음 15개만 보냄
            lines.append(f"\n... and {len(unsent) - 15} more articles")
            message_text = "\n".join(lines)
        
        send_telegram_text(message_text)
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
            topic["articles"] = topic_unsent[:15]  # 주제당 최대 15개
            topic["article_count"] = len(topic_unsent)
            topics_with_unsent.append(topic)

        if not topics_with_unsent:
            logger.info("No new articles in any topic. Skipping Telegram news summary.")
            return

        # Build telegram message - 최대 5개 주제, 주제당 최대 10개 기사
        lines = [f"<b>📈 Industry News Summary ({len(unsent)} articles)</b>", ""]
        total_sent_count = 0
        max_topics = min(len(topics_with_unsent), 5)  # 최대 5개 주제
        
        for topic_idx, topic in enumerate(topics_with_unsent[:max_topics]):
            label = html.escape(topic["label_ko"])
            lines.append(f"<b>{label} ({topic['article_count']} articles)</b>")
            
            # 주제당 최대 10개 기사
            max_articles_per_topic = min(len(topic["articles"]), 10)
            for idx, article in enumerate(topic["articles"][:max_articles_per_topic], 1):
                title = html.escape(article["title"][:70])
                url = html.escape(article["url"], quote=True)
                lines.append(f"  {idx}. <a href=\"{url}\">{title}</a>")
                total_sent_count += 1
            
            lines.append("")
        
        # 전체 요약 추가
        if total_sent_count < len(unsent):
            lines.append(f"<i>Showing {total_sent_count} of {len(unsent)} total articles</i>")
        
        # 텔레그램 메시지 길이 제한 확인
        message_text = "\n".join(lines)
        if len(message_text) > 4000:
            logger.warning("Telegram message too long (%d chars), sending simplified version.", len(message_text))
            # 간소화된 버전 보내기
            lines = [
                f"<b>📈 Industry News ({len(unsent)} articles)</b>",
                "",
                f"<b>Topics:</b>"
            ]
            for topic in topics_with_unsent[:3]:
                label = html.escape(topic["label_ko"])
                lines.append(f"• {label}: {topic['article_count']} articles")
            
            lines.append("")
            lines.append("<b>Top Articles:</b>")
            # 각 주제별 상위 2개 기사
            for topic in topics_with_unsent[:3]:
                for article in topic["articles"][:2]:
                    title = html.escape(article["title"][:60])
                    url = html.escape(article["url"], quote=True)
                    lines.append(f"• <a href=\"{url}\">{title}</a>")
            
            message_text = "\n".join(lines)
        
        send_telegram_text(message_text)

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

