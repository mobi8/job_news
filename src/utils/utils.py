#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    ALLOWED_LANGUAGE_TERMS,
    DEFAULT_RESUME_CANDIDATES,
    EXCLUDED_LANGUAGE_TERMS,
    REJECT_FEEDBACK_PATH,
    SCRAPE_STATE_PATH,
    TELEGRAM_SENT_HISTORY_PATH,
)
from .models import JobPosting


def utc_now() -> datetime:
    return datetime.now(UTC)


def format_seen_timestamp(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value.replace("T", " ")[:19]


def clean_text(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    unescaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def normalize_linkedin_url(url: str) -> str:
    if not url or "linkedin.com" not in url:
        return url
    parsed = urllib.parse.urlparse(url)
    job_id_match = re.search(r"/jobs/view/(?:[^/]*-)?(\d+)", parsed.path)
    if not job_id_match:
        job_id_match = re.search(r"(\d{7,})", url)
    if job_id_match:
        return f"https://www.linkedin.com/jobs/view/{job_id_match.group(1)}/"
    normalized_path = parsed.path.rstrip("/") + "/"
    return urllib.parse.urlunparse(("https", "www.linkedin.com", normalized_path, "", "", ""))

def normalize_linkedin_identifier(source: str, value: str) -> str:
    if source in ["linkedin_public", "linkedin_georgia", "linkedin_malta"]:
        return normalize_linkedin_url(value)
    return value


def normalize_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def load_reject_feedback() -> List[Dict[str, Any]]:
    if not REJECT_FEEDBACK_PATH.exists():
        return []
    try:
        payload = json.loads(REJECT_FEEDBACK_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = payload.get("rejected_jobs", []) if isinstance(payload, dict) else []
    normalized_items: List[Dict[str, Any]] = []
    changed = False
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        key = str(entry.get("key", ""))
        if key.startswith("linkedin_public|https://"):
            parts = key.split("|", 3)
            if len(parts) >= 4:
                normalized_key = "|".join(
                    [parts[0], normalize_linkedin_url(parts[1]), parts[2], parts[3]]
                )
                if normalized_key != key:
                    entry["key"] = normalized_key
                    changed = True
        normalized_items.append(entry)
    if changed:
        REJECT_FEEDBACK_PATH.write_text(
            json.dumps({"rejected_jobs": normalized_items, "synced_at": utc_now().isoformat()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return normalized_items


def load_telegram_sent_history() -> Dict[str, str]:
    if not TELEGRAM_SENT_HISTORY_PATH.exists():
        return {}
    try:
        payload = json.loads(TELEGRAM_SENT_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    history = payload.get("sent_job_keys", {}) if isinstance(payload, dict) else {}
    if not isinstance(history, dict):
        return {}
    normalized_history: Dict[str, str] = {}
    changed = False
    for key, value in history.items():
        key_str = str(key)
        if key_str.startswith("linkedin_public|https://"):
            parts = key_str.split("|", 3)
            if len(parts) >= 4:
                normalized_key = "|".join(
                    [parts[0], normalize_linkedin_url(parts[1]), parts[2], parts[3]]
                )
                if normalized_key != key_str:
                    key_str = normalized_key
                    changed = True
        normalized_history[key_str] = str(value)
    if changed:
        save_telegram_sent_history(normalized_history)
    return normalized_history


def save_telegram_sent_history(history: Dict[str, str]) -> None:
    TELEGRAM_SENT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    TELEGRAM_SENT_HISTORY_PATH.write_text(
        json.dumps({"sent_job_keys": history, "updated_at": utc_now().isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_scrape_state(mode: str, sources: List[tuple[str, List[JobPosting]]], inserted: int) -> None:
    from pathlib import Path
    import sqlite3

    source_state = {}
    scraped_at = utc_now().isoformat()

    # 이전 상태 로드 (이전 DB 카운트 알기 위함)
    previous_counts = {}
    if SCRAPE_STATE_PATH.exists():
        try:
            prev_data = json.loads(SCRAPE_STATE_PATH.read_text(encoding="utf-8"))
            if "sources" in prev_data:
                for src_key, src_info in prev_data["sources"].items():
                    previous_counts[src_key] = src_info.get("count", 0)
        except Exception:
            pass

    # 배치 개수 계산 (job.source 기반)
    source_batch_counts = {}
    for label, jobs in sources:
        for job in jobs:
            src_key = job.source
            source_batch_counts[src_key] = source_batch_counts.get(src_key, 0) + 1

    # DB에서 각 소스의 총 누적 개수 조회
    db_counts = {}
    db_path = Path("/Users/lewis/Desktop/agent/outputs/jobs.sqlite3")
    if db_path.exists():
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT source, COUNT(*) FROM jobs GROUP BY source")
            for source, count in cursor.fetchall():
                db_counts[source] = count
            conn.close()
        except Exception:
            pass

    # 모든 채용 소스 (기본값: 0)
    all_job_sources = [
        "jobvite_pragmaticplay", "smartrecruitment", "igamingrecruitment",
        "jobrapido_uae", "jobleads", "telegram_job_crypto_uae", "telegram_cryptojobslist",
        "indeed_uae", "linkedin_public"
    ]

    for src_key in all_job_sources:
        batch_count = source_batch_counts.get(src_key, 0)
        # DB에서 조회한 총 개수 사용 (더 정확함)
        total_count = db_counts.get(src_key, 0)
        # 이번 배치에서 실제 추가된 개수 = (현재 누적) - (이전 누적)
        prev_count = previous_counts.get(src_key, 0)
        added_this_batch = max(0, total_count - prev_count)

        source_state[src_key] = {
            "count": total_count,
            "count_this_batch": batch_count,
            "added_this_batch": added_this_batch,
            "last_scraped_at": scraped_at
        }

    # 뉴스 소스 개수 계산
    news_state = {}
    # 이전 뉴스 소스 상태 로드
    previous_news_counts = {}
    if SCRAPE_STATE_PATH.exists():
        try:
            prev_data = json.loads(SCRAPE_STATE_PATH.read_text(encoding="utf-8"))
            if "news_sources" in prev_data:
                for src_key, src_info in prev_data["news_sources"].items():
                    previous_news_counts[src_key] = src_info.get("count", 0)
        except Exception:
            pass

    dashboard_data_path = Path("/Users/lewis/Desktop/agent/outputs/job_stats_data.json")
    if dashboard_data_path.exists():
        try:
            dashboard_data = json.loads(dashboard_data_path.read_text(encoding="utf-8"))
            news_items = dashboard_data.get("news_items", [])
            topics = dashboard_data.get("topics", [])

            # 뉴스 소스별 개수 계산
            news_count = {}
            for item in news_items:
                src = item.get("source", "")
                news_count[src] = news_count.get(src, 0) + 1

            # 뉴스 소스 정의
            all_news_sources = [
                "rss_igaming_business", "rss_fintech_uae", "player_feed"
            ]

            for src_key in all_news_sources:
                if src_key == "player_feed":
                    total_count = len(topics)
                else:
                    total_count = news_count.get(src_key, 0)

                # 이번 배치에서 실제 추가된 개수
                prev_count = previous_news_counts.get(src_key, 0)
                added_this_batch = max(0, total_count - prev_count)

                news_state[src_key] = {
                    "count": total_count,
                    "added_this_batch": added_this_batch,
                    "last_scraped_at": scraped_at
                }
        except Exception:
            pass

    payload = {
        "last_scraped_at": scraped_at,
        "mode": mode,
        "new_jobs_this_run": inserted,
        "sources": source_state,
        "news_sources": news_state,
    }
    SCRAPE_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_last_scrape_completed_at() -> Optional[str]:
    if not SCRAPE_STATE_PATH.exists():
        return None
    try:
        payload = json.loads(SCRAPE_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None
    last_scraped_at = payload.get("last_scraped_at")
    return str(last_scraped_at) if last_scraped_at else None


def prune_telegram_sent_history(history: Dict[str, str], days: int = 14) -> Dict[str, str]:
    cutoff = utc_now() - timedelta(days=days)
    kept: Dict[str, str] = {}
    for key, sent_at in history.items():
        try:
            if datetime.fromisoformat(sent_at) >= cutoff:
                kept[key] = sent_at
        except ValueError:
            continue
    return kept


def notification_key(record: Dict[str, Any]) -> str:
    source = str(record.get("source", ""))
    source_job_id = normalize_linkedin_identifier(source, str(record.get("source_job_id", "")))
    return "|".join(
        [
            source,
            source_job_id,
            str(record.get("title", "")),
            str(record.get("company", "")),
        ]
    )


def derive_reject_block_phrase(title: str) -> str:
    stopwords = {
        "senior", "junior", "lead", "principal", "staff", "global", "regional",
        "remote", "dubai", "uae", "united", "arab", "emirates", "the", "and",
        "for", "with", "at", "of", "in",
    }
    tokens = [token for token in normalize_phrase(title).split() if len(token) > 2 and token not in stopwords]
    if len(tokens) >= 2:
        return " ".join(tokens[:5])
    return normalize_phrase(title)


def reject_note_patterns(note: str) -> Dict[str, List[str]]:
    note_norm = normalize_phrase(note)
    patterns: Dict[str, List[str]] = {"must": [], "any": []}
    if not note_norm:
        return patterns
    if "uae national" in note_norm:
        patterns["must"].append("uae national")
    if "latam" in note_norm:
        patterns["must"].append("latam")
    if "china" in note_norm or "중국" in note:
        patterns["must"].append("china")
    if "sportsbook" in note_norm or "스포츠북" in note:
        patterns["must"].append("sportsbook")
    if "전통 it 벤더" in note or "traditional it" in note_norm or "it vendor" in note_norm:
        patterns["any"].extend(["canonical", "desktop", "networking", "crm", "traditional it", "it vendor"])
    if "클라우드 회사" in note or "cloud" in note_norm:
        patterns["any"].extend(["cloud", "crm", "canonical"])
    if "같은거" in note or "duplicate" in note_norm:
        patterns["any"].append("account manager")
    if "developers affairs" in note_norm:
        patterns["must"].append("developers affairs")
    return patterns


def matches_reject_feedback(job: JobPosting, feedback_items: List[Dict[str, Any]]) -> bool:
    if not feedback_items:
        return False

    title_norm = normalize_phrase(job.title)
    company_norm = normalize_phrase(job.company)
    location_norm = normalize_phrase(job.location)
    text_blob = normalize_phrase(" ".join([job.title, job.company, job.location, job.description]))

    for item in feedback_items:
        reason = (item.get("remove_reason") or "").strip().lower()
        note = str(item.get("note", "")).strip()

        rejected_title = normalize_phrase(str(item.get("title", "")))
        rejected_company = normalize_phrase(str(item.get("company", "")))
        rejected_location = normalize_phrase(str(item.get("location", "")))
        block_phrase = derive_reject_block_phrase(str(item.get("title", "")))
        note_patterns = reject_note_patterns(note)

        if note_patterns["must"] and all(pattern in text_blob for pattern in note_patterns["must"]):
            return True
        if note_patterns["any"] and any(pattern in text_blob for pattern in note_patterns["any"]):
            return True

        if reason and reason not in {"wrong_function", "wrong_domain", "not_interested", "wrong_location"}:
            continue

        if rejected_title and title_norm == rejected_title:
            return True
        if rejected_company and rejected_title and company_norm == rejected_company and block_phrase and block_phrase in text_blob:
            return True
        if block_phrase and len(block_phrase.split()) >= 2 and block_phrase in text_blob:
            if reason != "wrong_location" or (rejected_location and rejected_location in location_norm):
                return True

    return False


def load_resume_text() -> str:
    env_path = os.getenv("JOB_MATCH_PROFILE_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(DEFAULT_RESUME_CANDIDATES)

    for candidate in candidates:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8", errors="replace")
    return ""


def inferred_profile_text() -> str:
    return (
        "web3 stablecoin crypto payment payments blockchain adgm vara fsra "
        "igaming compliance backend product integration operations risk fraud "
        "python postgresql solana"
    )


def parse_requested_sources(raw_value: Optional[str]) -> Optional[set[str]]:
    if not raw_value:
        return None

    alias_map = {
        "jobvite": "jobvite_pragmaticplay",
        "jobvite_pragmaticplay": "jobvite_pragmaticplay",
        "smartrecruitment": "smartrecruitment",
        "smartrecruit": "smartrecruitment",
        "igamingrecruitment": "igamingrecruitment",
        "igaming_recruitment": "igamingrecruitment",
        "igaming recruitment": "igamingrecruitment",
        "indeed": "indeed_uae",
        "indeed_uae": "indeed_uae",
        "linkedin": "linkedin_public",
        "linkedin_public": "linkedin_public",
        "linkedin_malta": "linkedin_malta",
        "jobrapido": "jobrapido_uae",
        "jobrapido_uae": "jobrapido_uae",
        "jobleads": "jobleads",
        "telegram_job_crypto_uae": "telegram_job_crypto_uae",
        "telegram_cryptojobslist": "telegram_cryptojobslist",
    }

    import logging as _logging
    _logger = _logging.getLogger(__name__)
    normalized_sources = set()
    for chunk in raw_value.split(","):
        key = chunk.strip().lower()
        if not key:
            continue
        mapped = alias_map.get(key)
        if mapped:
            normalized_sources.add(mapped)
            continue
        _logger.warning("Ignoring unknown source filter: %s", chunk.strip())

    return normalized_sources or None


def dedupe_records_for_display(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for record in records:
        title_key = normalize_phrase(str(record.get("title", "")))
        company_key = normalize_phrase(str(record.get("company", "")))
        location_key = normalize_phrase(str(record.get("location", "")))
        key = (title_key, company_key, location_key)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    return deduped
