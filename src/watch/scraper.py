#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UAE job watcher — thin entry point.

All logic lives in the modules below:
  config.py        — constants & URLs
  models.py        — JobPosting dataclass
  db.py            — Database (SQLite wrapper)
  utils.py         — utility helpers
  scoring.py       — match scoring & filtering
  scrapers.py      — per-source fetch/parse functions
  reporter.py      — save_json / save_csv / save_markdown / save_dashboard
  notifications.py — Telegram send helpers + source_*_counts
"""

from __future__ import annotations

import logging
import os
import sys
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

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

from utils.logger import scraper_logger
from utils.config import (
    DB_PATH,
    IGAMING_RECRUITMENT_URL,
    JOBRAPIDO_URL,
    JOBVITE_URL,
    JOBLEADS_URL,
    OUTPUT_DIR,
    SMARTRECRUITMENT_URL,
)
from utils.db import Database
from utils.notifications import (
    maybe_send_telegram,
    send_incremental_summary,
    send_news_summary,
    source_daily_counts,
    source_total_counts,
)
from utils.reporter import save_csv, save_dashboard, save_dashboard_data, save_json, save_markdown, save_news_dashboard
from utils.scoring import (
    annotate_records,
    calculate_match_score,
    focus_records,
    is_hard_excluded_job,
    is_language_filtered_out,
    top_recommendations,
)
from utils.scrapers import (
    fetch_all_player_rss_news,
    fetch_all_rss_news,
    fetch_html,
    fetch_indeed_jobs_via_browser,
    fetch_linkedin_jobs_via_browser,
    fetch_telegram_channel_jobs,
    parse_igaming_recruitment_jobs,
    parse_jobrapido_jobs,
    parse_jobvite_jobs,
    parse_jobleads_jobs,
    parse_smartrecruitment_jobs,
    telegram_job_relevant,
)
from utils.utils import (
    load_reject_feedback,
    load_resume_text,
    load_last_scrape_completed_at,
    load_watch_interval_minutes,
    matches_reject_feedback,
    parse_requested_sources,
    save_scrape_state,
    utc_now,
)

# Use centralized logger from utils.logger
logger = scraper_logger


def load_browser_lookback_hours() -> int:
    raw_value = os.getenv("BROWSER_LOOKBACK_HOURS", "72")
    try:
        return max(1, int(raw_value))
    except ValueError:
        logger.warning("Invalid BROWSER_LOOKBACK_HOURS=%r; falling back to 72.", raw_value)
        return 72


def run(mode: str = "collect") -> Dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_started_at = utc_now()
    db = Database(DB_PATH)
    db.purge_language_filtered_jobs()
    db.purge_hard_excluded_jobs()
    resume_text = load_resume_text()
    reject_feedback = load_reject_feedback()

    # Use the most recent completed batch time as the anchor for lookback filtering.
    # This keeps the window aligned with the last successful run instead of the current start time.
    browser_lookback_hours = load_browser_lookback_hours()
    batch_time_str = load_last_scrape_completed_at() or utc_now().isoformat()
    batch_time = datetime.fromisoformat(batch_time_str)
    cutoff_time = batch_time - timedelta(hours=browser_lookback_hours)
    cutoff_time_iso = cutoff_time.isoformat()

    # Apply reject_feedback patterns to existing jobs (retroactive cleanup)
    if reject_feedback:
        purged = db.purge_reject_feedback_jobs(reject_feedback)
        if purged:
            logger.info("Purged %d jobs based on reject feedback patterns.", purged)
    watch_hours = float(os.getenv("WATCH_WINDOW_HOURS", "3"))
    allowed_sources = parse_requested_sources(os.getenv("JOB_WATCH_SOURCES"))

    sources = []

    if allowed_sources is None or "jobvite_pragmaticplay" in allowed_sources:
        logger.info("Fetching Jobvite board...")
        jobvite_jobs = parse_jobvite_jobs(fetch_html(JOBVITE_URL))
        logger.info("Collected %s jobs from Jobvite.", len(jobvite_jobs))
        sources.append((JOBVITE_URL, jobvite_jobs))

    if allowed_sources is None or "smartrecruitment" in allowed_sources:
        logger.info("Fetching SmartRecruitment board...")
        smartrecruitment_jobs = parse_smartrecruitment_jobs(fetch_html(SMARTRECRUITMENT_URL))
        logger.info("Collected %s jobs from SmartRecruitment.", len(smartrecruitment_jobs))
        sources.append((SMARTRECRUITMENT_URL, smartrecruitment_jobs))

    if allowed_sources is None or "igamingrecruitment" in allowed_sources:
        logger.info("Fetching iGaming Recruitment board...")
        igaming_recruitment_jobs = parse_igaming_recruitment_jobs(fetch_html(IGAMING_RECRUITMENT_URL))
        logger.info("Collected %s jobs from iGaming Recruitment.", len(igaming_recruitment_jobs))
        sources.append((IGAMING_RECRUITMENT_URL, igaming_recruitment_jobs))

    if allowed_sources is None or "jobrapido_uae" in allowed_sources:
        logger.info("Fetching Jobrapido board...")
        jobrapido_jobs = parse_jobrapido_jobs(fetch_html(JOBRAPIDO_URL))
        logger.info("Collected %s jobs from Jobrapido.", len(jobrapido_jobs))
        sources.append((JOBRAPIDO_URL, jobrapido_jobs))

    if allowed_sources is None or "jobleads" in allowed_sources:
        logger.info("Fetching JobLeads board...")
        try:
            jobleads_jobs = parse_jobleads_jobs(fetch_html(JOBLEADS_URL))
            logger.info("Collected %s jobs from JobLeads.", len(jobleads_jobs))
            sources.append((JOBLEADS_URL, jobleads_jobs))
        except Exception as exc:
            logger.warning("Skipping JobLeads for this run: %s", exc)

    if allowed_sources is None or (
        "telegram_job_crypto_uae" in allowed_sources or "telegram_cryptojobslist" in allowed_sources
    ):
        logger.info("Fetching Telegram public job channels...")
        telegram_jobs = fetch_telegram_channel_jobs()
        if allowed_sources is not None:
            telegram_jobs = [job for job in telegram_jobs if job.source in allowed_sources]
        logger.info("Collected %s jobs from Telegram public channels.", len(telegram_jobs))
        sources.append(("Telegram public channels", telegram_jobs))


    if allowed_sources is None or "indeed_uae" in allowed_sources:
        logger.info("Fetching Indeed UAE via browser session...")
        indeed_jobs = fetch_indeed_jobs_via_browser()
        # Apply browser lookback filtering (collected_at >= cutoff_time)
        cutoff_time_iso = cutoff_time.isoformat()
        indeed_jobs = [j for j in indeed_jobs if j.collected_at and j.collected_at >= cutoff_time_iso]
        logger.info("Collected %s jobs from Indeed UAE.", len(indeed_jobs))
        sources.append(("Indeed UAE browser searches", indeed_jobs))

    if allowed_sources is None or "linkedin_public" in allowed_sources:
        logger.info("Fetching LinkedIn public jobs via browser session...")
        linkedin_jobs = fetch_linkedin_jobs_via_browser()
        # Apply browser lookback filtering (collected_at >= cutoff_time)
        linkedin_jobs = [j for j in linkedin_jobs if j.collected_at and j.collected_at >= cutoff_time_iso]
        logger.info("Collected %s jobs from LinkedIn.", len(linkedin_jobs))
        sources.append(("LinkedIn public browser searches", linkedin_jobs))

    jobs = [
        job
        for _, source_jobs in sources
        for job in source_jobs
        if not is_language_filtered_out(f"{job.title} {job.description}")
        and not is_hard_excluded_job(job.title, job.company, job.location, job.description)
        and not matches_reject_feedback(job, reject_feedback)
        and (
            not job.source.startswith("telegram_")
            or telegram_job_relevant(job, resume_text)
        )
    ]

    for job in jobs:
        job.match_score = calculate_match_score(job, resume_text)

    inserted, inserted_jobs = db.upsert_jobs(jobs, return_jobs=True)

    # Collect and store news from RSS feeds
    news_items = fetch_all_rss_news()
    player_news_items = fetch_all_player_rss_news()
    all_news_items = news_items + player_news_items
    news_inserted = db.upsert_news(all_news_items)
    logger.info("Collected %d news items (%d industry + %d player), %d new.",
                len(all_news_items), len(news_items), len(player_news_items), news_inserted)

    all_jobs_annotated = annotate_records(db.fetch_all_jobs(), resume_text)
    tracked_jobs = [job for job in all_jobs_annotated if job["qualifies"]]
    new_last_1_day = focus_records(db.jobs_first_seen_since(24), resume_text)
    stats = {
        "total_jobs": len(tracked_jobs),
        "new_last_1_day": len(new_last_1_day),
        "new_last_7_days": len([
            job for job in tracked_jobs
            if job.get("first_seen_at")
            and datetime.fromisoformat(job["first_seen_at"]) >= utc_now() - timedelta(days=7)
        ]),
        "new_last_30_days": len([
            job for job in tracked_jobs
            if job.get("first_seen_at")
            and datetime.fromisoformat(job["first_seen_at"]) >= utc_now() - timedelta(days=30)
        ]),
        "top_locations": [],
    }
    by_location: Dict[str, int] = {}
    for job in tracked_jobs:
        by_location[job["location"]] = by_location.get(job["location"], 0) + 1
    stats["top_locations"] = sorted(by_location.items(), key=lambda item: item[1], reverse=True)[:10]
    source_total = source_total_counts(tracked_jobs)
    source_daily = source_daily_counts(tracked_jobs)
    recommendations = top_recommendations(jobs, resume_text)

    run_completed_at = utc_now()
    watch_interval_minutes = load_watch_interval_minutes()
    next_batch_at = (run_started_at + timedelta(minutes=watch_interval_minutes)).isoformat()
    save_scrape_state(
        mode,
        sources,
        inserted,
        started_at=run_started_at.isoformat(),
        completed_at=run_completed_at.isoformat(),
        next_scrape_at=next_batch_at,
    )
    payload = {
        "collection_metadata": {
            "collected_at": run_completed_at.isoformat(),
            "batch_started_at": run_started_at.isoformat(),
            "next_batch_at": next_batch_at,
            "sources": [source for source, _ in sources],
            "jobs_collected_this_run": len(jobs),
            "new_jobs_this_run": inserted,
            "new_jobs_this_run_details": [job.to_dict() for job in inserted_jobs],
            "resume_loaded": bool(resume_text),
        },
        "statistics": stats,
        "top_recommendations": [job.to_dict() for job in recommendations],
        "filtered_jobs": tracked_jobs,
        "all_tracked_jobs": all_jobs_annotated,
    }

    save_json(OUTPUT_DIR / "jobs_analysis.json", payload)
    save_csv(OUTPUT_DIR / "jobs_recommendations.csv", recommendations)
    save_markdown(
        OUTPUT_DIR / "jobs_analysis.md",
        stats,
        recommendations,
        inserted,
        [source for source, _ in sources],
    )
    # Generate news dashboard HTML only if it doesn't exist
    news_dashboard_path = OUTPUT_DIR / "all_news.html"
    if not news_dashboard_path.exists():
        logger.info("Generating news dashboard HTML template...")
        save_news_dashboard(news_dashboard_path)

    # Update dashboard data (JSON) on every run
    save_dashboard_data(
        OUTPUT_DIR / "job_stats_data.json",
        stats,
        source_total,
        source_daily,
        tracked_jobs,
        all_jobs_annotated,
        collection_metadata=payload["collection_metadata"],
    )

    # Add recent news data to dashboard JSON with source labels
    import json
    dashboard_data_path = OUTPUT_DIR / "job_stats_data.json"
    if dashboard_data_path.exists():
        dashboard_data = json.loads(dashboard_data_path.read_text(encoding="utf-8"))
        recent_news = db.fetch_recent_news(336)  # 2 weeks of news

        # Add source labels and descriptions
        source_info = {
            "rss_igaming_business": {
                "label": "iGaming Business",
                "emoji": "🎮",
                "description": "글로벌 iGaming 업계 뉴스, 규제, 채용 동향",
                "color": "#FF6B6B"
            },
            "rss_fintech_uae": {
                "label": "Fintech News UAE",
                "emoji": "💰",
                "description": "UAE/GCC 핀테크 시장, 규제, 라이선스, 채용 정보",
                "color": "#4ECDC4"
            }
        }

        for item in recent_news:
            source = item.get("source", "")
            if source in source_info:
                item["source_label"] = source_info[source]["label"]
                item["source_emoji"] = source_info[source]["emoji"]
                item["source_description"] = source_info[source]["description"]
                item["source_color"] = source_info[source]["color"]

        dashboard_data["news_items"] = recent_news

        # Add topics to dashboard data
        topics = db.compute_news_topics(168)
        dashboard_data["topics"] = topics

        # Add player mentions to dashboard data
        player_mentions = db.track_player_mentions(168)
        dashboard_data["player_mentions"] = player_mentions

        dashboard_data_path.write_text(
            json.dumps(dashboard_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    if mode == "collect":
        batch_jobs = focus_records([job.to_dict() for job in inserted_jobs], resume_text)
        maybe_send_telegram(inserted, batch_jobs)
        send_news_summary(all_news_items, db=db)
    elif mode == "incremental":
        send_incremental_summary(db, hours=watch_hours, allowed_sources=allowed_sources)

    logger.info("Saved outputs to %s", OUTPUT_DIR)
    return payload


def main() -> int:
    try:
        mode = "collect"
        if len(sys.argv) > 1:
            mode = sys.argv[1].strip().lower()
        run(mode=mode)

        return 0
    except urllib.error.URLError as exc:
        logger.error("Network error: %s", exc)
        return 1
    except Exception as exc:  # pragma: no cover
        logger.exception("Unexpected error: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
