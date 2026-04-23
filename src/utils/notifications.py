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
from .models import JobPosting
from .scoring import focus_records, is_hard_excluded_job, source_label
from .utils import (
    dedupe_records_for_display,
    load_resume_text,
    utc_now,
)
from .config import OUTPUT_DIR
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
    "linkedin_jobspy": "UAE",
    "linkedin_malta": "Malta",
    "indeed_jobspy": "UAE",
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
    explicit_country = _job_attr(job, "country")
    if explicit_country:
        lowered = explicit_country.strip().lower()
        if lowered in {"uae", "dubai"}:
            return "UAE"
        if lowered in {"malta"}:
            return "Malta"
        if lowered in {"georgia"}:
            return "Georgia"
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
        country = country_label_for_job(job) or "Other"
        label = html.escape(f"[{country}] {_job_attr(job, 'company')} | {_job_attr(job, 'title')}")
        url = html.escape(_job_attr(job, "url"), quote=True)
        items.append({"label": label, "url": url, "country": country})
    return items


def _coerce_job_record(job: Any) -> Dict[str, Any]:
    if isinstance(job, dict):
        return dict(job)
    if isinstance(job, JobPosting):
        return job.to_dict()
    return {
        "source": _job_attr(job, "source"),
        "source_job_id": _job_attr(job, "source_job_id"),
        "title": _job_attr(job, "title"),
        "company": _job_attr(job, "company"),
        "location": _job_attr(job, "location"),
        "url": _job_attr(job, "url"),
        "description": _job_attr(job, "description"),
        "remote": bool(_job_attr(job, "remote")),
        "country": _job_attr(job, "country"),
        "first_seen_at": _job_attr(job, "first_seen_at"),
        "last_seen_at": _job_attr(job, "last_seen_at"),
        "match_score": _job_attr(job, "match_score"),
    }


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


def _job_score(job: Any) -> int:
    raw_score = job.get("match_score", 0) if isinstance(job, dict) else getattr(job, "match_score", 0)
    try:
        return int(raw_score)
    except Exception:
        return 0


def _prepare_notification_jobs(jobs: List[Any]) -> List[Dict[str, Any]]:
    normalized = []
    for job in jobs:
        record = _coerce_job_record(job)
        if is_hard_excluded_job(
            record.get("title", ""),
            record.get("company", ""),
            record.get("location", ""),
            record.get("description", ""),
        ):
            continue
        normalized.append(record)
    normalized.sort(
        key=lambda job: (
            -_job_score(job),
            country_label_for_job(job) or "ZZZ",
            _job_attr(job, "company").lower(),
            _job_attr(job, "title").lower(),
        )
    )
    return dedupe_records_for_display(normalized)


def send_telegram_text(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("Telegram notification skipped: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
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
    last_exc: Exception | None = None
    for attempt in range(1, 3):
        try:
            with urllib.request.urlopen(request, timeout=20):
                logger.info("Telegram notification sent.")
            return True
        except Exception as exc:
            last_exc = exc
            logger.warning("Telegram notification attempt %d failed: %s", attempt, exc)
            if attempt == 1:
                import time
                time.sleep(2)
    if last_exc is not None:
        logger.warning("Telegram notification failed after retries: %s", last_exc)
    return False


def send_job_analysis_cards(jobs: List[Any], min_score: int = 70) -> None:
    """Send individual job cards with inline [🔍 분석] button for high-score jobs."""
    import json as _json
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    # Load/update URL map (short numeric key → full URL)
    url_map_path = OUTPUT_DIR / "url_map.json"
    url_map = _json.loads(url_map_path.read_text()) if url_map_path.exists() else {}
    next_id = max((int(k) for k in url_map), default=0) + 1

    country_emoji = {"UAE": "🇦🇪", "Georgia": "🇬🇪", "Malta": "🇲🇹", "Bahrain": "🇧🇭", "Qatar": "🇶🇦", "Saudi Arabia": "🇸🇦"}
    high_score_jobs = [
        j for j in jobs
        if _job_score(j) >= min_score
        and j.get("url")
        and not is_hard_excluded_job(j.get("title", ""), j.get("company", ""), j.get("location", ""), j.get("description", ""))
    ]

    for job in high_score_jobs:
        url = job.get("url", "")
        # Reuse existing key or assign new one
        existing = next((k for k, v in url_map.items() if v == url), None)
        if existing:
            key = existing
        else:
            key = str(next_id)
            url_map[key] = url
            next_id += 1

        flag = country_emoji.get(job.get("country", ""), "")
        title = html.escape(job.get("title", "?"))
        company = html.escape(job.get("company", "?"))
        score = _job_score(job)
        country = job.get("country", "")

        text = f"{flag} <b>{company}</b> — {title}\nScore: {score} | {country}"
        reply_markup = _json.dumps({
            "inline_keyboard": [[{"text": "🔍 career-ops 분석", "callback_data": f"a:{key}"}]]
        })
        payload = urllib.parse.urlencode({
            "chat_id": chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true", "reply_markup": reply_markup,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            urllib.request.urlopen(req, timeout=10)
            logger.info("Sent analysis card: %s - %s", company, title)
        except Exception as e:
            logger.warning("Failed to send analysis card: %s", e)

    url_map_path.write_text(_json.dumps(url_map))


def maybe_send_telegram(inserted: int, jobs: List[Any], min_score: int = 30) -> None:
    prepared_jobs = _prepare_notification_jobs(jobs)
    qualifying_jobs = [job for job in prepared_jobs if _job_score(job) >= min_score]

    if not qualifying_jobs:
        message_text = (
            "<b>🆕 New Jobs (0 new)</b>\n\n"
            f"이번 배치에 신규 공고는 {max(inserted, len(prepared_jobs))}건 있었지만 "
            f"알림 조건(min_score={min_score})을 넘은 항목이 없습니다."
        )
        if send_telegram_text(message_text):
            logger.info(
                "Sent zero-update Telegram job alert (inserted=%s, qualifying=%s, min_score=%s).",
                inserted,
                len(qualifying_jobs),
                min_score,
            )
        else:
            logger.info("No new jobs to send via Telegram at score >= %s.", min_score)
        return

    country_line = country_line_for_jobs(qualifying_jobs)
    job_items = build_job_template_items(qualifying_jobs)
    country_groups = group_job_items_by_country(job_items)
    context = {
        "new_count": len(qualifying_jobs),
        "country_line": country_line,
        "country_groups": country_groups,
    }

    message_text = render_template("telegram/job_alert.txt", context)
    logger.debug("Rendered job_alert template: %s", message_text)
    if len(message_text) <= 4000:
        if not send_telegram_text(message_text):
            return
    else:
        logger.warning(
            "Job alert (%d chars) exceeds Telegram limit; chunking into shorter messages.",
            len(message_text),
        )
        if not send_telegram_messages_chunked(message_text.splitlines()):
            return

    send_job_analysis_cards(qualifying_jobs, min_score=30)


def send_incremental_summary(
    db: Database,
    hours: float = 3,
    limit: int = 8,
    allowed_sources: Optional[set[str]] = None,
) -> None:
    new_jobs = _prepare_notification_jobs(db.jobs_first_seen_since(hours))
    if allowed_sources is not None:
        new_jobs = [job for job in new_jobs if job["source"] in allowed_sources]
    new_jobs = [job for job in new_jobs if _job_score(job) >= 30]
    if new_jobs:
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
        return

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


def send_daily_summary(
    db: Database,
    hours: float = 24,
    limit: int = 8,
    allowed_sources: Optional[set[str]] = None,
) -> None:
    send_incremental_summary(db, hours=hours, limit=limit, allowed_sources=allowed_sources)


def send_news_summary(news_items: List[Any], limit: int = 100, db: Database | None = None) -> None:
    def news_url(item: Any) -> str:
        return _job_attr(item, "url")

    def news_title(item: Any) -> str:
        return _job_attr(item, "title")

    unsent_items = [item for item in news_items if news_url(item)]

    if not unsent_items:
        message_text = "<b>📈 Industry News (0 new)</b>\n\n이번 배치에 신규 뉴스가 없습니다."
        if send_telegram_text(message_text):
            logger.info("Sent zero-update Telegram news summary.")
        else:
            logger.info("No new articles to send via Telegram.")
        return

    if db is None:
        lines = [f"<b>📈 Industry News ({len(unsent_items)} articles)</b>", ""]
        for item in unsent_items[:limit]:
            title = html.escape(news_title(item)[:80])
            url = html.escape(news_url(item), quote=True)
            lines.append(f"• <a href=\"{url}\">{title}</a>")

        message_text = "\n".join(lines)
        if len(message_text) > 4000:
            logger.warning("Telegram news summary too long (%d chars), truncating.", len(message_text))
            lines = lines[:15]
            lines.append(f"\n... and {len(unsent_items) - 15} more articles")
            message_text = "\n".join(lines)

        logger.debug("Rendered simple news_summary: %s", message_text)
        if not send_telegram_text(message_text):
            return
    else:
        topics = db.compute_news_topics(168)
        if not topics:
            logger.info("No topics found from news items.")
            return

        unsent_urls = {news_url(item) for item in unsent_items}
        topics_with_unsent = []
        for topic in topics:
            topic_unsent = [article for article in topic["articles"] if article["url"] in unsent_urls]
            if not topic_unsent:
                continue
            topic["articles"] = topic_unsent[:15]
            topic["article_count"] = len(topic_unsent)
            topics_with_unsent.append(topic)

        if not topics_with_unsent:
            message_text = "<b>📈 Industry News (0 new)</b>\n\n이번 배치에 신규 뉴스가 없습니다."
            if send_telegram_text(message_text):
                logger.info("Sent zero-update Telegram news summary.")
            else:
                logger.info("No new articles in any topic. Skipping Telegram news summary.")
            return

        max_topics = min(len(topics_with_unsent), 5)
        total_sent_count = sum(min(len(t["articles"]), 10) for t in topics_with_unsent[:max_topics])

        context_full = {
            "total_articles": len(unsent_items),
            "topics": [
                {
                    "label_ko": html.escape(topic["label_ko"]),
                    "article_count": topic["article_count"],
                    "articles": [
                        {
                            "title": html.escape(article["title"][:70]),
                            "url": html.escape(article["url"], quote=True),
                        }
                        for article in topic["articles"][:10]
                    ],
                }
                for topic in topics_with_unsent[:max_topics]
            ],
            "showing_partial": len(unsent_items) > total_sent_count,
            "shown_count": total_sent_count,
        }

        message_text = render_template("telegram/news_summary.txt", context_full)
        logger.debug("Rendered news_summary: %s", message_text)
        if len(message_text) <= 4000:
            if not send_telegram_text(message_text):
                return
        else:
            logger.warning(
                "News summary (%d chars) exceeds Telegram limit; chunking into shorter messages.",
                len(message_text),
            )
            if not send_telegram_messages_chunked(message_text.splitlines()):
                return



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


def _news_source_label(source: str) -> str:
    """Convert news source code to human-readable label."""
    mapping = {
        "rss_igaming_business": "iGaming Business",
        "rss_fintech_uae": "Fintech News UAE",
    }
    return mapping.get(source, source)
