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
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

# JobSpy for Indeed scraping
try:
    jobspy_site_packages = '/Users/lewis/Desktop/agent/jobspy_env/lib/python3.14/site-packages'
    if jobspy_site_packages not in sys.path:
        sys.path.insert(0, jobspy_site_packages)
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

from utils.logger import scraper_logger, setup_logger
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
    fetch_gamblingcareers_jobs_via_browser,
    fetch_himalayas_jobs_via_api,
    fetch_glassdoor_jobs_via_browserless,
    fetch_indeed_jobs_via_browserless,
    fetch_indeed_jobs_via_jobspy,
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
jobspy_logger = setup_logger("jobspy_progress", json_format=False)

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


def _console_step(message: str) -> None:
    print(f"\n>>> {datetime.now().isoformat(timespec='seconds')} {message}", flush=True)


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


def _source_allowed(allowed_sources: set[str] | None, source: str) -> bool:
    return allowed_sources is None or source in allowed_sources


def _any_source_allowed(allowed_sources: set[str] | None, *sources: str) -> bool:
    if allowed_sources is None:
        return True
    return any(source in allowed_sources for source in sources)


def _skip_news_collection() -> bool:
    return os.getenv("SKIP_NEWS_COLLECTION", "").strip().lower() in {"1", "true", "yes", "on"}


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
        jobspy_logger.info(
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
    if not scrape_jobs:
        raise ImportError("JobSpy not available")

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


def _process_jobspy_country(
    plan: dict,
    existing_fingerprints: set,
    now_iso: str,
    jobspy_lookback_hours: int,
) -> list:
    """Process Indeed scraping for a single country. Returns Indeed jobs only."""
    country = plan["country"]
    if country != "UAE":
        return []

    indeed_jobs: list = []
    jobspy_logger.info("Scraping JobSpy country bucket: %s", country)

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

    return indeed_jobs


def scrape_indeed_via_jobspy(db: Database) -> list:
    """Scrape Indeed jobs using JobSpy."""
    if not scrape_jobs:
        logger.warning("JobSpy not available, skipping Indeed scraping")
        return []

    try:
        indeed_jobs: list = []
        now_iso = utc_now().isoformat()
        last_completed_at = load_last_scrape_completed_at()
        jobspy_lookback_hours = _compute_jobspy_lookback_hours()

        _console_step("JobSpy phase starting")
        jobspy_logger.info(
            "JobSpy lookback window: %sh (overlap=%sh, last_batch_at=%s)",
            jobspy_lookback_hours,
            JOBSPY_LOOKBACK_OVERLAP_HOURS,
            last_completed_at or "n/a",
        )

        # Reuse one fingerprint set so the same posting does not get re-added in the same run.
        existing_fingerprints = db.get_recent_fingerprints(hours=jobspy_lookback_hours)

        with ProcessPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(
                    _process_jobspy_country,
                    plan,
                    existing_fingerprints,
                    now_iso,
                    jobspy_lookback_hours,
                )
                for plan in JOBSPY_COUNTRY_PLANS
            ]
            for future in futures:
                indeed_jobs.extend(future.result())

        _console_step(
            f"JobSpy phase finished: Indeed={len(indeed_jobs)}"
        )
        jobspy_logger.info(
            "Collected %s Indeed jobs",
            len(indeed_jobs),
        )
        return indeed_jobs

    except Exception as e:
        logger.error(f"Error scraping via JobSpy: {e}")
        return []


def scrape_linkedin_via_browser() -> list:
    """Scrape LinkedIn jobs via browser."""
    try:
        _console_step("Browser phase starting: LinkedIn")
        linkedin_jobs = fetch_linkedin_jobs_via_browser()
        logger.info(
            "Collected %s LinkedIn browser jobs",
            len(linkedin_jobs),
        )
        _console_step(f"Browser phase finished: LinkedIn={len(linkedin_jobs)}")
        return linkedin_jobs
    except Exception as e:
        logger.error(f"Error scraping via browser probe: {e}")
        return []


def scrape_indeed_via_browser() -> list:
    """Scrape Indeed jobs via browser."""
    try:
        _console_step("Browser phase starting: Indeed")
        indeed_jobs = fetch_indeed_jobs_via_browser()
        logger.info(
            "Collected %s Indeed browser jobs",
            len(indeed_jobs),
        )
        _console_step(f"Browser phase finished: Indeed={len(indeed_jobs)}")
        return indeed_jobs
    except Exception as e:
        logger.error(f"Error scraping Indeed via browser probe: {e}")
        return []


def scrape_gamblingcareers_via_browser() -> list:
    """Scrape GamblingCareers remote jobs via browser probe."""
    try:
        _console_step("Browser phase starting: GamblingCareers")
        gamblingcareers_jobs = fetch_gamblingcareers_jobs_via_browser()
        logger.info(
            "Collected %s GamblingCareers browser jobs",
            len(gamblingcareers_jobs),
        )
        _console_step(f"Browser phase finished: GamblingCareers={len(gamblingcareers_jobs)}")
        return gamblingcareers_jobs
    except Exception as e:
        logger.error(f"Error scraping GamblingCareers via browser probe: {e}")
        return []


def scrape_himalayas_igaming() -> list:
    """Scrape Himalayas iGaming jobs via the public API, with browser fallback."""
    try:
        _console_step("Fetching Himalayas board")
        himalayas_jobs = fetch_himalayas_jobs_via_api()
        logger.info(
            "Collected %s Himalayas iGaming jobs",
            len(himalayas_jobs),
        )
        _console_step(f"Finished Himalayas board: Himalayas={len(himalayas_jobs)}")
        return himalayas_jobs
    except Exception as e:
        logger.error(f"Error scraping Himalayas iGaming jobs: {e}")
        return []


def scrape_indeed_via_browserless() -> list:
    """Scrape Indeed jobs via Browserless."""
    try:
        _console_step("Browser phase starting: Indeed browserless")
        indeed_jobs = fetch_indeed_jobs_via_browserless()
        logger.info(
            "Collected %s Indeed browserless jobs",
            len(indeed_jobs),
        )
        _console_step(f"Browser phase finished: Indeed browserless={len(indeed_jobs)}")
        return indeed_jobs
    except Exception as e:
        logger.error(f"Error scraping Indeed browserless jobs: {e}")
        return []


def scrape_glassdoor_via_browserless() -> list:
    """Scrape Glassdoor jobs via Browserless."""
    try:
        _console_step("Browser phase starting: Glassdoor")
        glassdoor_jobs = fetch_glassdoor_jobs_via_browserless()
        logger.info(
            "Collected %s Glassdoor browserless jobs",
            len(glassdoor_jobs),
        )
        _console_step(f"Browser phase finished: Glassdoor={len(glassdoor_jobs)}")
        return glassdoor_jobs
    except Exception as e:
        logger.error(f"Error scraping Glassdoor via browserless probe: {e}")
        return []


def run(mode: str = "collect") -> Dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_started_at = utc_now()
    _console_step(f"Scrape run started (mode={mode})")
    db = Database(DB_PATH)
    db.purge_language_filtered_jobs()
    db.purge_hard_excluded_jobs()
    resume_text = load_resume_text()
    reject_feedback = load_reject_feedback()
    watch_hours = float(os.getenv("WATCH_WINDOW_HOURS", "3"))
    watch_interval_minutes = load_watch_interval_minutes()
    next_batch_at = (run_started_at + timedelta(minutes=watch_interval_minutes)).isoformat()
    # Record the new run immediately so the dashboard does not keep showing a stale next-batch time.
    save_scrape_state(
        mode,
        [],
        0,
        started_at=run_started_at.isoformat(),
        completed_at=None,
        next_scrape_at=next_batch_at,
        new_news_this_run=0,
        run_status="running",
    )

    allowed_sources = parse_requested_sources(os.getenv("JOB_WATCH_SOURCES"))
    sources = []
    jobs = []
    inserted_jobs = []
    inserted = 0
    news_items = []
    player_news_items = []
    all_news_items = []
    inserted_news_items = []
    news_inserted = 0
    try:
        # Apply reject_feedback patterns to existing jobs (retroactive cleanup)
        if reject_feedback:
            purged = db.purge_reject_feedback_jobs(reject_feedback)
            if purged:
                logger.info("Purged %d jobs based on reject feedback patterns.", purged)

        if allowed_sources is None or "jobvite_pragmaticplay" in allowed_sources:
            _console_step("Fetching Jobvite board")
            logger.info("Fetching Jobvite board...")
            jobvite_jobs = parse_jobvite_jobs(fetch_html(JOBVITE_URL))
            logger.info("Collected %s jobs from Jobvite.", len(jobvite_jobs))
            sources.append((JOBVITE_URL, jobvite_jobs))

        if allowed_sources is None or "smartrecruitment" in allowed_sources:
            _console_step("Fetching SmartRecruitment board")
            logger.info("Fetching SmartRecruitment board...")
            smartrecruitment_jobs = parse_smartrecruitment_jobs(fetch_html(SMARTRECRUITMENT_URL))
            logger.info("Collected %s jobs from SmartRecruitment.", len(smartrecruitment_jobs))
            sources.append((SMARTRECRUITMENT_URL, smartrecruitment_jobs))

        if allowed_sources is None or "igamingrecruitment" in allowed_sources:
            _console_step("Fetching iGaming Recruitment board")
            logger.info("Fetching iGaming Recruitment board...")
            igaming_recruitment_jobs = parse_igaming_recruitment_jobs(fetch_html(IGAMING_RECRUITMENT_URL))
            logger.info("Collected %s jobs from iGaming Recruitment.", len(igaming_recruitment_jobs))
            sources.append((IGAMING_RECRUITMENT_URL, igaming_recruitment_jobs))

        if allowed_sources is None or "jobrapido_uae" in allowed_sources:
            _console_step("Fetching Jobrapido board")
            logger.info("Fetching Jobrapido board...")
            jobrapido_jobs = parse_jobrapido_jobs(fetch_html(JOBRAPIDO_URL))
            logger.info("Collected %s jobs from Jobrapido.", len(jobrapido_jobs))
            sources.append((JOBRAPIDO_URL, jobrapido_jobs))

        if allowed_sources is None or "jobleads" in allowed_sources:
            _console_step("Fetching JobLeads board")
            logger.info("Fetching JobLeads board...")
            try:
                jobleads_jobs = parse_jobleads_jobs(fetch_html(JOBLEADS_URL))
                logger.info("Collected %s jobs from JobLeads.", len(jobleads_jobs))
                sources.append((JOBLEADS_URL, jobleads_jobs))
            except Exception as exc:
                logger.warning("Skipping JobLeads for this run: %s", exc)

        if False and (allowed_sources is None or (
            "telegram_job_crypto_uae" in allowed_sources or "telegram_cryptojobslist" in allowed_sources
        )):
            _console_step("Fetching Telegram public channels")
            logger.info("Fetching Telegram public job channels...")
            telegram_jobs = fetch_telegram_channel_jobs()
            if allowed_sources is not None:
                telegram_jobs = [job for job in telegram_jobs if job.source in allowed_sources]
            logger.info("Collected %s jobs from Telegram public channels.", len(telegram_jobs))
            sources.append(("Telegram public channels", telegram_jobs))

        gamblingcareers_jobs = []
        if _source_allowed(allowed_sources, "gamblingcareers_remote"):
            _console_step("Fetching GamblingCareers board")
            logger.info("Fetching GamblingCareers board...")
            gamblingcareers_jobs = scrape_gamblingcareers_via_browser()

        himalayas_jobs = []
        if _source_allowed(allowed_sources, "himalayas_igaming"):
            _console_step("Fetching Himalayas board")
            logger.info("Fetching Himalayas board...")
            himalayas_jobs = scrape_himalayas_igaming()

        # Scrape browser-based sources in a later pass so the HTML/API sources finish first.
        _console_step("Starting browser scrape pass")
        browser_linkedin_jobs = []
        if _any_source_allowed(allowed_sources, "linkedin_public", "linkedin_georgia", "linkedin_malta"):
            browser_linkedin_jobs = scrape_linkedin_via_browser()

        browser_indeed_jobs = []
        if _any_source_allowed(allowed_sources, "indeed_uae", "indeed_georgia", "indeed_malta"):
            browser_indeed_jobs = scrape_indeed_via_browser()

        browser_glassdoor_jobs = []
        if _source_allowed(allowed_sources, "glassdoor_uae"):
            _console_step("Running Glassdoor browserless scrape inline")
            try:
                browser_glassdoor_jobs = scrape_glassdoor_via_browserless()
            except Exception as exc:
                logger.error("Error collecting Glassdoor browserless result: %s", exc)
                browser_glassdoor_jobs = []

        # Keep JobSpy as a second pass for Indeed coverage.
        jobspy_indeed_jobs = []
        if _any_source_allowed(allowed_sources, "indeed_uae", "indeed_georgia", "indeed_malta"):
            _console_step("Starting JobSpy scrape pass")
            jobspy_indeed_jobs = scrape_indeed_via_jobspy(db)

        linkedin_jobs = browser_linkedin_jobs
        glassdoor_jobs = browser_glassdoor_jobs
        browser_indeed_jobs_filtered = browser_indeed_jobs
        jobspy_indeed_jobs_filtered = jobspy_indeed_jobs

        if allowed_sources is not None:
            linkedin_jobs = [job for job in linkedin_jobs if job.source in allowed_sources]
            glassdoor_jobs = [job for job in glassdoor_jobs if job.source in allowed_sources]
            browser_indeed_jobs_filtered = [job for job in browser_indeed_jobs_filtered if job.source in allowed_sources]
            jobspy_indeed_jobs_filtered = [job for job in jobspy_indeed_jobs_filtered if job.source in allowed_sources]

        if linkedin_jobs:
            sources.append(("LinkedIn browser", linkedin_jobs))

        if glassdoor_jobs:
            sources.append(("Glassdoor browserless", glassdoor_jobs))

        if browser_indeed_jobs_filtered:
            sources.append(("Indeed browser", browser_indeed_jobs_filtered))

        if jobspy_indeed_jobs_filtered:
            sources.append(("Indeed jobspy", jobspy_indeed_jobs_filtered))

        if gamblingcareers_jobs:
            sources.append(("GamblingCareers", gamblingcareers_jobs))

        if himalayas_jobs:
            sources.append(("Himalayas iGaming", himalayas_jobs))

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

        skip_news_collection = _skip_news_collection()
        if skip_news_collection:
            news_items = []
            player_news_items = []
            all_news_items = []
            inserted_news_items = []
            news_inserted = 0
            logger.info("Skipping news collection for this run.")
        else:
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
        save_scrape_state(
            mode,
            sources,
            inserted,
            started_at=run_started_at.isoformat(),
            completed_at=run_completed_at.isoformat(),
            next_scrape_at=next_batch_at,
            new_news_this_run=news_inserted,
            run_status="completed",
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

        _console_step("Saving outputs")
        if mode == "collect":
            batch_jobs = [job.to_dict() for job in inserted_jobs]
            maybe_send_telegram(inserted, batch_jobs)
            if not skip_news_collection:
                send_news_summary(inserted_news_items, db=db)
        elif mode == "incremental":
            send_incremental_summary(db, hours=watch_hours, allowed_sources=allowed_sources)

        logger.info("Saved outputs to %s", OUTPUT_DIR)
        _console_step(f"Scrape run complete: {inserted} new jobs, {news_inserted} new news")
        return payload
    except Exception:
        if "glassdoor_executor" in locals() and glassdoor_executor is not None:
            glassdoor_executor.shutdown(wait=False, cancel_futures=True)
        logger.exception("Scrape run failed")
        save_scrape_state(
            mode,
            sources,
            inserted,
            started_at=run_started_at.isoformat(),
            completed_at=None,
            next_scrape_at=next_batch_at,
            new_news_this_run=news_inserted,
            run_status="failed",
        )
        raise


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
