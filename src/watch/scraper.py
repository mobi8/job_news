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

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import signal
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

# JobSpy for LinkedIn + Indeed scraping
try:
    sys.path.insert(0, '/Users/lewis/Desktop/agent/jobspy_env/lib/python3.14/site-packages')
    from jobspy import scrape_jobs
except ImportError:
    scrape_jobs = None

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
    BROWSER_LOOKBACK_HOURS,
    GOOGLE_SEARCH_KEYWORDS,
    INDEED_SEARCH_KEYWORDS,
    JOBSPY_COUNTRY_PLANS,
    JOBSPY_HOURS_OLD,
    JOBSPY_LOOKBACK_OVERLAP_HOURS,
    JOBSPY_MAX_LOOKBACK_HOURS,
    JOBSPY_MIN_LOOKBACK_HOURS,
    LINKEDIN_SEARCH_KEYWORDS,
    IGAMING_RECRUITMENT_URL,
    JOBRAPIDO_URL,
    JOBVITE_URL,
    JOBLEADS_URL,
    OUTPUT_DIR,
    SMARTRECRUITMENT_URL,
)
from utils.models import JobPosting
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
    fetch_telegram_channel_jobs,
    parse_igaming_recruitment_jobs,
    parse_jobrapido_jobs,
    parse_jobvite_jobs,
    parse_jobleads_jobs,
    parse_smartrecruitment_jobs,
    telegram_job_relevant,
)
from utils.utils import (
    dedupe_job_postings,
    load_reject_feedback,
    load_resume_text,
    load_last_scrape_completed_at,
    load_watch_interval_minutes,
    matches_reject_feedback,
    parse_requested_sources,
    safe_bool,
    safe_text,
    save_scrape_state,
    utc_now,
)

# Use centralized logger from utils.logger
logger = scraper_logger

JOBSPY_RESULTS_WANTED = int(os.getenv("JOBSPY_RESULTS_WANTED", "20"))
JOBSPY_INDEED_RESULTS_WANTED = int(os.getenv("JOBSPY_INDEED_RESULTS_WANTED", "30"))
JOBSPY_GOOGLE_RESULTS_WANTED = int(os.getenv("JOBSPY_GOOGLE_RESULTS_WANTED", "20"))
JOBSPY_TIMEOUT_SECONDS = int(os.getenv("JOBSPY_TIMEOUT_SECONDS", "90"))
JOBSPY_MAX_RETRIES = int(os.getenv("JOBSPY_MAX_RETRIES", "3"))
JOBSPY_RETRY_BASE_DELAY_SECONDS = int(os.getenv("JOBSPY_RETRY_BASE_DELAY_SECONDS", "20"))
JOBSPY_INTER_KEYWORD_DELAY_SECONDS = float(os.getenv("JOBSPY_INTER_KEYWORD_DELAY_SECONDS", "2.0"))
JOBSPY_INDEED_INTER_KEYWORD_DELAY_SECONDS = float(
    os.getenv("JOBSPY_INDEED_INTER_KEYWORD_DELAY_SECONDS", "4.0")
)
JOBSPY_GOOGLE_INTER_KEYWORD_DELAY_SECONDS = float(
    os.getenv("JOBSPY_GOOGLE_INTER_KEYWORD_DELAY_SECONDS", "2.0")
)


def _is_missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return value != value
    if isinstance(value, str):
        return value.strip().lower() in {"", "nan", "none", "null", "<na>"}
    try:
        return bool(value) is False and str(value).strip() == ""
    except Exception:
        return False


def _row_value(row: Any, *names: str, default: Any = "") -> Any:
    for name in names:
        try:
            value = row.get(name, default)
        except Exception:
            try:
                value = row[name]
            except Exception:
                continue
        if not _is_missing_value(value):
            return value
    return default


@contextmanager
def _time_limit(seconds: int):
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    def _handler(signum, frame):  # pragma: no cover - signal handler
        raise TimeoutError(f"JobSpy call timed out after {seconds}s")

    previous_handler = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _is_rate_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in [
            "429",
            "rate limit",
            "too many requests",
            "forbidden",
            "captcha",
            "blocked",
            "access denied",
        ]
    )


def _jobspy_source_name(site_name: str, country: str) -> str:
    country_key = country.strip().lower()
    if site_name == "linkedin":
        return "linkedin_public" if country_key == "uae" else f"linkedin_{country_key}"
    if site_name == "indeed":
        return "indeed_uae" if country_key == "uae" else f"indeed_{country_key}"
    if site_name == "google":
        return f"google_{country_key}"
    raise ValueError(f"Unsupported JobSpy site: {site_name}")


def _build_google_search_term(keyword: str, location: str) -> str:
    cleaned_keyword = keyword.strip()
    cleaned_location = location.strip()
    if cleaned_location:
        return f"{cleaned_keyword} jobs in {cleaned_location} since yesterday"
    return f"{cleaned_keyword} jobs since yesterday"


def _run_jobspy_keyword_bucket(
    *,
    jobs: list,
    existing_fingerprints: set[str],
    now_iso: str,
    site_name: str,
    keywords: list[str],
    source: str,
    country: str,
    location: str,
    results_wanted: int,
    hours_old: int,
    linkedin_fetch_description: bool = False,
    country_indeed: str | None = None,
    use_google_search_term: bool = False,
    inter_keyword_delay_seconds: float = 0.0,
) -> None:
    for keyword in keywords:
        google_search_term = _build_google_search_term(keyword, location) if use_google_search_term else None
        logger.info(
            "JobSpy %s %s keyword=%r location=%r%s",
            site_name,
            country,
            keyword,
            location,
            f" google_search_term={google_search_term!r}" if google_search_term else "",
        )
        rows = _run_jobspy_query(
            site_name=[site_name],
            search_term=keyword,
            location=location,
            results_wanted=results_wanted,
            hours_old=hours_old,
            linkedin_fetch_description=linkedin_fetch_description,
            country_indeed=country_indeed,
            google_search_term=google_search_term,
        )
        if rows is not None:
            _append_jobspy_rows(
                jobs=jobs,
                rows=rows,
                source=source,
                country=country,
                default_location=location,
                now_iso=now_iso,
                existing_fingerprints=existing_fingerprints,
            )
        if inter_keyword_delay_seconds > 0:
            time.sleep(inter_keyword_delay_seconds)


def _compute_jobspy_lookback_hours() -> int:
    """Look back from the last completed batch, with overlap to avoid missing late posts."""
    last_completed_at = load_last_scrape_completed_at()
    if not last_completed_at:
        return max(JOBSPY_HOURS_OLD, JOBSPY_MIN_LOOKBACK_HOURS)

    try:
        completed_at = datetime.fromisoformat(last_completed_at)
    except ValueError:
        return max(JOBSPY_HOURS_OLD, JOBSPY_MIN_LOOKBACK_HOURS)

    current_at = utc_now()
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=current_at.tzinfo)

    lookback_start = completed_at - timedelta(hours=JOBSPY_LOOKBACK_OVERLAP_HOURS)
    delta_hours = (current_at - lookback_start).total_seconds() / 3600.0
    effective_hours = int(delta_hours + 0.999999)
    return max(JOBSPY_MIN_LOOKBACK_HOURS, min(JOBSPY_MAX_LOOKBACK_HOURS, effective_hours))


def _run_jobspy_query(
    *,
    site_name: list[str],
    search_term: str,
    location: str,
    hours_old: int,
    results_wanted: int,
    linkedin_fetch_description: bool = False,
    country_indeed: str | None = None,
    google_search_term: str | None = None,
) -> Any:
    kwargs: Dict[str, Any] = {
        "site_name": site_name,
        "search_term": search_term,
        "location": location,
        "results_wanted": results_wanted,
        "hours_old": hours_old,
        "verbose": 0,
    }
    if linkedin_fetch_description:
        kwargs["linkedin_fetch_description"] = True
    if country_indeed:
        kwargs["country_indeed"] = country_indeed
    if google_search_term:
        kwargs["google_search_term"] = google_search_term

    last_error: Exception | None = None
    for attempt in range(1, JOBSPY_MAX_RETRIES + 1):
        try:
            with _time_limit(JOBSPY_TIMEOUT_SECONDS):
                return scrape_jobs(**kwargs)
        except TimeoutError as exc:
            last_error = exc
            logger.warning(
                "JobSpy timeout for %s keyword %r on attempt %d/%d: %s",
                site_name[0],
                search_term,
                attempt,
                JOBSPY_MAX_RETRIES,
                exc,
            )
        except Exception as exc:
            last_error = exc
            if _is_rate_limit_error(exc):
                logger.warning(
                    "JobSpy rate-limit for %s keyword %r on attempt %d/%d: %s",
                    site_name[0],
                    search_term,
                    attempt,
                    JOBSPY_MAX_RETRIES,
                    exc,
                )
            else:
                logger.warning(
                    "JobSpy error for %s keyword %r on attempt %d/%d: %s",
                    site_name[0],
                    search_term,
                    attempt,
                    JOBSPY_MAX_RETRIES,
                    exc,
                )

        if attempt < JOBSPY_MAX_RETRIES:
            sleep_seconds = min(
                120,
                JOBSPY_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
            )
            time.sleep(sleep_seconds)

    if last_error is not None:
        logger.warning("Giving up on %s keyword %r after retries.", site_name[0], search_term)
    return None


def _append_jobspy_rows(
    *,
    jobs: list,
    rows: Any,
    source: str,
    country: str,
    default_location: str,
    now_iso: str,
    existing_fingerprints: set[str],
) -> int:
    added = 0
    if rows is None:
        return 0

    if hasattr(rows, "iterrows"):
        iterator = rows.iterrows()
    elif isinstance(rows, list):
        iterator = enumerate(rows)
    else:
        return 0

    for _, row in iterator:
        title = safe_text(_row_value(row, "title"), "")
        company = safe_text(_row_value(row, "company"), "")
        location = safe_text(_row_value(row, "location"), default_location)
        url = safe_text(_row_value(row, "job_url", "url"), "")
        source_job_id = safe_text(_row_value(row, "id", "job_id", "job_url", "url"), url)
        description = safe_text(_row_value(row, "description"), "")

        if not title or not url:
            continue

        fp = hashlib.sha1("|".join([
            title.strip().lower(),
            company.strip().lower(),
            location.strip().lower(),
        ]).encode("utf-8")).hexdigest()
        if fp in existing_fingerprints:
            continue

        existing_fingerprints.add(fp)
        job = JobPosting(
            source=source,
            source_job_id=source_job_id or url,
            title=title,
            company=company,
            location=location,
            url=url,
            description=description,
            remote=safe_bool(_row_value(row, "is_remote")),
            country=country,
            collected_at=now_iso,
        )
        jobs.append(job)
        added += 1

    return added


def load_browser_lookback_hours() -> int:
    raw_value = os.getenv("BROWSER_LOOKBACK_HOURS")
    if raw_value is None:
        return BROWSER_LOOKBACK_HOURS
    try:
        return max(1, int(raw_value))
    except ValueError:
        logger.warning("Invalid BROWSER_LOOKBACK_HOURS=%r; falling back to %s.", raw_value, BROWSER_LOOKBACK_HOURS)
        return BROWSER_LOOKBACK_HOURS


def scrape_linkedin_indeed_via_jobspy(db: Database) -> tuple[list, list, list]:
    """Scrape LinkedIn, Indeed, and Google jobs using JobSpy."""
    if not scrape_jobs:
        logger.warning("JobSpy not available, skipping LinkedIn/Indeed/Google scraping")
        return [], [], []

    try:
        linkedin_jobs: list = []
        indeed_jobs: list = []
        google_jobs: list = []
        now_iso = utc_now().isoformat()
        last_completed_at = load_last_scrape_completed_at()
        jobspy_lookback_hours = _compute_jobspy_lookback_hours()

        logger.info(
            "JobSpy lookback window: %sh (overlap=%sh, last_batch_at=%s)",
            jobspy_lookback_hours,
            JOBSPY_LOOKBACK_OVERLAP_HOURS,
            last_completed_at or "n/a",
        )

        # Reuse one fingerprint set across all JobSpy sites so LinkedIn / Indeed / Google
        # do not re-add the same posting in the same run.
        existing_fingerprints = db.get_recent_fingerprints(hours=jobspy_lookback_hours)

        for plan in JOBSPY_COUNTRY_PLANS:
            country = plan["country"]
            logger.info("Scraping JobSpy country bucket: %s", country)

            _run_jobspy_keyword_bucket(
                jobs=linkedin_jobs,
                existing_fingerprints=existing_fingerprints,
                now_iso=now_iso,
                site_name="linkedin",
                keywords=LINKEDIN_SEARCH_KEYWORDS,
                source=plan["linkedin_source"],
                country=country,
                location=plan["linkedin_location"],
                results_wanted=JOBSPY_RESULTS_WANTED,
                hours_old=jobspy_lookback_hours,
                linkedin_fetch_description=True,
                inter_keyword_delay_seconds=JOBSPY_INTER_KEYWORD_DELAY_SECONDS,
            )

            _run_jobspy_keyword_bucket(
                jobs=indeed_jobs,
                existing_fingerprints=existing_fingerprints,
                now_iso=now_iso,
                site_name="indeed",
                keywords=INDEED_SEARCH_KEYWORDS,
                source=plan["indeed_source"],
                country=country,
                location=plan["indeed_location"],
                results_wanted=JOBSPY_INDEED_RESULTS_WANTED,
                hours_old=jobspy_lookback_hours,
                country_indeed=plan["indeed_country"],
                inter_keyword_delay_seconds=JOBSPY_INDEED_INTER_KEYWORD_DELAY_SECONDS,
            )

            _run_jobspy_keyword_bucket(
                jobs=google_jobs,
                existing_fingerprints=existing_fingerprints,
                now_iso=now_iso,
                site_name="google",
                keywords=GOOGLE_SEARCH_KEYWORDS,
                source=plan["google_source"],
                country=country,
                location=plan["google_location"],
                results_wanted=JOBSPY_GOOGLE_RESULTS_WANTED,
                hours_old=jobspy_lookback_hours,
                use_google_search_term=True,
                inter_keyword_delay_seconds=JOBSPY_GOOGLE_INTER_KEYWORD_DELAY_SECONDS,
            )

        logger.info(
            "Collected %s LinkedIn jobs, %s Indeed jobs, %s Google jobs",
            len(linkedin_jobs),
            len(indeed_jobs),
            len(google_jobs),
        )
        return linkedin_jobs, indeed_jobs, google_jobs

    except Exception as e:
        logger.error(f"Error scraping via JobSpy: {e}")
        return [], [], []


def run(mode: str = "collect") -> Dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_started_at = utc_now()
    db = Database(DB_PATH)
    db.purge_language_filtered_jobs()
    db.purge_hard_excluded_jobs()
    resume_text = load_resume_text()
    reject_feedback = load_reject_feedback()


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


    # Scrape LinkedIn + Indeed + Google via JobSpy (includes descriptions, with dedup filter)
    linkedin_jobs, indeed_jobs, google_jobs = scrape_linkedin_indeed_via_jobspy(db)

    if allowed_sources is not None:
        linkedin_jobs = [job for job in linkedin_jobs if job.source in allowed_sources]
        indeed_jobs = [job for job in indeed_jobs if job.source in allowed_sources]
        google_jobs = [job for job in google_jobs if job.source in allowed_sources]

    if linkedin_jobs:
        sources.append(("LinkedIn jobspy", linkedin_jobs))

    if indeed_jobs:
        sources.append(("Indeed jobspy", indeed_jobs))

    if google_jobs:
        sources.append(("Google jobspy", google_jobs))

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
    jobs = dedupe_job_postings(jobs)

    for job in jobs:
        job.match_score = calculate_match_score(job, resume_text)

    inserted, inserted_jobs = db.upsert_jobs(jobs, return_jobs=True)

    # Collect and store news from RSS feeds
    news_items = fetch_all_rss_news()
    player_news_items = fetch_all_player_rss_news()
    all_news_items = news_items + player_news_items
    news_inserted, inserted_news_items = db.upsert_news(all_news_items, return_items=True)
    logger.info("Collected %d news items (%d industry + %d player), %d new.",
                len(all_news_items), len(news_items), len(player_news_items), news_inserted)

    all_jobs_annotated = annotate_records(db.fetch_all_jobs(), resume_text)

    # Re-detect country based on location for all jobs
    # This ensures old jobs are properly classified even if they were stored with wrong country
    for job in all_jobs_annotated:
        location = (job.get("location") or "").lower()

        # Malta (high priority)
        if "malta" in location or "valletta" in location or "몰타" in location or "sliema" in location or "gzira" in location:
            job["country"] = "Malta"
        # Georgia (check before USA to handle Georgia properly)
        elif "미국 조지아" in location or "us georgia" in location or "georgia, usa" in location or "georgia, united states" in location:
            job["country"] = ""
        # Georgia
        elif "georgia" in location or "조지아" in location or "tbilisi" in location or "트빌리시" in location or "batumi" in location or "바투미" in location:
            job["country"] = "Georgia"
        # Exclude USA/Hong Kong
        elif any(x in location for x in ["미국", "usa", "united states", "american gaming", "ags -", "fanduel", "atlanta", "duluth", "hong kong", "홍콩"]):
            job["country"] = ""
        # UAE
        elif "dubai" in location or "두바이" in location or "united arab emirates" in location or "uae" in location:
            job["country"] = "UAE"
        # Default: if location doesn't match any specific country, clear country field
        # This prevents old UAE jobs from being incorrectly classified when location doesn't clearly indicate UAE
        else:
            # Only set to empty if location exists but doesn't match any country
            # Preserve country only if location is completely empty
            if location and location.strip():  # Non-empty location that didn't match any condition
                job["country"] = ""

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
        "new_jobs_this_batch": inserted,
        "new_news_this_batch": news_inserted,
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
            "news_collected_this_run": len(all_news_items),
            "new_news_this_run": news_inserted,
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
        batch_jobs = [job.to_dict() for job in inserted_jobs]
        maybe_send_telegram(inserted, batch_jobs)
        send_news_summary(inserted_news_items, db=db)
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
