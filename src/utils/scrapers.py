#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import logging
import os
import re
import subprocess
import threading
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List

from .config import (
    BROWSER_PROBE_PATH,
    GLASSDOOR_BROWSERLESS_PROBE_PATH,
    GLASSDOOR_BROWSERLESS_SEARCH_URLS,
    COMMERCIAL_ROLE_TERMS,
    HIMALAYAS_IGAMING_API_URL,
    GAMBLINGCAREERS_REMOTE_URL,
    GAMBLINGCAREERS_REMOTE_FALLBACK_URLS,
    IGAMING_RECRUITMENT_URL,
    INDEED_SEARCH_KEYWORDS,
    INDEED_SEARCH_URLS,
    JOBVITE_URL,
    LINKEDIN_SEARCH_URLS,
    NEWS_RSS_FEEDS,
    PLAYER_RSS_FEEDS,
    PRODUCT_ROLE_TERMS,
    RECRUITER_SEARCH_URLS,
    STRONG_DOMAIN_TERMS,
    TELEGRAM_CHANNELS,
)
from .models import JobPosting, NewsItem
from .scoring import evaluate_fit
from .logger import scraper_logger, setup_logger
from .utils import clean_text, normalize_linkedin_identifier, normalize_linkedin_url, utc_now

logger = scraper_logger
browser_logger = setup_logger("browser_progress", json_format=False)

BROWSER_BATCH_WORKERS = max(1, int(os.getenv("BROWSER_BATCH_WORKERS", "3")))
BROWSER_INDEED_BATCH_SIZE = max(1, int(os.getenv("BROWSER_INDEED_BATCH_SIZE", "2")))
BROWSER_LINKEDIN_BATCH_SIZE = max(1, int(os.getenv("BROWSER_LINKEDIN_BATCH_SIZE", "2")))
# Keep Glassdoor batches intentionally tiny so Browserless free-plan usage stays predictable.
BROWSER_GLASSDOOR_BATCH_SIZE = max(1, int(os.getenv("BROWSER_GLASSDOOR_BATCH_SIZE", "1")))
BROWSER_GLASSDOOR_BATCH_WORKERS = max(1, int(os.getenv("BROWSER_GLASSDOOR_BATCH_WORKERS", "1")))


def _emit_captured_stderr(prefix: str, stderr: str) -> None:
    text = (stderr or "").strip()
    if not text:
        return
    for line in text.splitlines():
        logger.info("%s%s", prefix, line)


def _run_browser_probe_with_progress(command: List[str], timeout: int) -> tuple[int, str, str]:
    # Capture stdout to a temp file so large browser JSON output cannot block the child process.
    stdout_file = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen(
        command,
        stdout=stdout_file,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    stderr_lines: list[str] = []

    def _pump_stderr() -> None:
        assert proc.stderr is not None
        for raw_line in iter(proc.stderr.readline, ""):
            line = raw_line.rstrip()
            if line:
                stderr_lines.append(line)
                if (
                    "[browser_probe]" in line
                    or line.startswith("Browser launch failed:")
                    or line.startswith("Playwright error for Indeed:")
                    or line.startswith("Error processing ")
                ):
                    browser_logger.info("%s", line)

    stderr_thread = threading.Thread(target=_pump_stderr, daemon=True)
    stderr_thread.start()

    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)
        stderr_thread.join(timeout=1)
        stdout_file.close()
        raise

    stdout_file.seek(0)
    stdout = stdout_file.read() or ""
    stdout_file.close()

    stderr_thread.join(timeout=1)
    return proc.returncode, stdout, "\n".join(stderr_lines)


def _get_jobspy_scrape_jobs():
    try:
        import sys

        jobspy_site_packages = "/Users/lewis/Desktop/agent/jobspy_env/lib/python3.14/site-packages"
        if jobspy_site_packages not in sys.path:
            sys.path.insert(0, jobspy_site_packages)
        from jobspy import scrape_jobs as jobspy_scrape_jobs
        return jobspy_scrape_jobs
    except ImportError:
        return None


def fetch_html(url: str, extra_headers: dict[str, str] | None = None) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def parse_jobvite_jobs(raw_html: str) -> List[JobPosting]:
    pattern = re.compile(
        r"<tr>\s*"
        r'<td class="jv-job-list-name">\s*<a href="(?P<href>[^"]+)">(?P<title>.*?)</a>\s*</td>\s*'
        r'<td class="jv-job-list-location">\s*(?P<location>.*?)\s*</td>\s*'
        r"</tr>",
        re.DOTALL,
    )

    jobs: List[JobPosting] = []
    for match in pattern.finditer(raw_html):
        href = html.unescape(match.group("href")).strip()
        title = clean_text(match.group("title"))
        location = clean_text(match.group("location"))
        source_job_id = href.rstrip("/").split("/")[-1]

        # Detect country from location
        location_lower = location.lower()
        country = "UAE"  # Default
        if "malta" in location_lower or "valletta" in location_lower or "몰타" in location_lower:
            country = "Malta"
        elif "georgia" in location_lower or "조지아" in location_lower or "tbilisi" in location_lower or "트빌리시" in location_lower:
            country = "Georgia"

        jobs.append(
            JobPosting(
                source="jobvite_pragmaticplay",
                source_job_id=source_job_id,
                title=title,
                company="ARRISE / Pragmatic Play",
                location=location,
                remote="remote" in location.lower(),
                url=urllib.parse.urljoin(JOBVITE_URL, href),
                country=country,
            )
        )

    return jobs


def parse_smartrecruitment_jobs(raw_html: str) -> List[JobPosting]:
    pattern = re.compile(
        r'<a class="hyphens-auto"[^>]+href="(?P<url>https://jobs\.smartrecruitment\.com/jobs/[^"]+)">\s*'
        r"<span[^>]*></span>\s*(?P<title>.*?)\s*</a>\s*"
        r'<span class="text-base">\s*'
        r"(?:<span>.*?</span>\s*<span[^>]*>&middot;</span>\s*)?"
        r"<span>(?P<location>.*?)</span>",
        re.DOTALL,
    )

    jobs: List[JobPosting] = []
    seen_urls = set()
    for match in pattern.finditer(raw_html):
        url = html.unescape(match.group("url")).strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = clean_text(match.group("title"))
        location = clean_text(match.group("location"))
        source_job_id = url.rstrip("/").split("/")[-1]

        # Detect country from location
        location_lower = location.lower()
        country = "UAE"  # Default
        if "malta" in location_lower or "valletta" in location_lower or "몰타" in location_lower:
            country = "Malta"
        elif "georgia" in location_lower or "조지아" in location_lower or "tbilisi" in location_lower or "트빌리시" in location_lower:
            country = "Georgia"

        jobs.append(
            JobPosting(
                source="smartrecruitment",
                source_job_id=source_job_id,
                title=title,
                company="SmartRecruitment.com",
                location=location,
                remote="remote" in f"{title} {location}".lower(),
                country=country,
                url=url,
            )
        )

    return jobs


def parse_igaming_recruitment_jobs(raw_html: str) -> List[JobPosting]:
    pattern = re.compile(
        r'<h4 class="et_pb_module_header"><a href="(?P<url>https://igamingrecruitment\.io/jobs/[^"]+/)">(?P<title>.*?)</a></h4>\s*'
        r'<div class="et_pb_blurb_description">.*?'
        r'<p[^>]*>\s*(?:<span[^>]*>)?(?P<location>.*?)(?:</span>)?\s*</p>',
        re.DOTALL,
    )

    jobs: List[JobPosting] = []
    seen_urls = set()
    for match in pattern.finditer(raw_html):
        url = html.unescape(match.group("url")).strip()
        if url in seen_urls:
            continue
        seen_urls.add(url)

        title = clean_text(match.group("title"))
        location = clean_text(match.group("location"))
        source_job_id = url.rstrip("/").split("/")[-1]

        # Detect country from location
        location_lower = location.lower()
        country = "UAE"  # Default
        if "malta" in location_lower or "valletta" in location_lower or "몰타" in location_lower:
            country = "Malta"
        elif "georgia" in location_lower or "조지아" in location_lower or "tbilisi" in location_lower or "트빌리시" in location_lower:
            country = "Georgia"

        jobs.append(
            JobPosting(
                source="igamingrecruitment",
                source_job_id=source_job_id,
                title=title,
                company="iGaming Recruitment",
                location=location,
                remote="remote" in f"{title} {location}".lower(),
                country=country,
                url=url,
            )
        )

    return jobs


def parse_jobrapido_jobs(raw_html: str) -> List[JobPosting]:
    pattern = re.compile(
        r"data-advert='(?P<json>\{.*?\})'",
        re.DOTALL,
    )

    jobs: List[JobPosting] = []
    seen_urls = set()
    for match in pattern.finditer(raw_html):
        advert_json = html.unescape(match.group("json"))
        try:
            advert = json.loads(advert_json)
        except json.JSONDecodeError:
            continue

        url = advert.get("openAdvertUrl", "").strip()
        title = clean_text(advert.get("title", ""))
        company = clean_text(advert.get("company", "")) or "Jobrapido"
        location = clean_text(advert.get("location", ""))
        source_job_id = clean_text(advert.get("advertId", "")) or urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]
        if not url or not title or url in seen_urls:
            continue

        seen_urls.add(url)
        description = clean_text(" ".join(filter(None, [
            advert.get("description", ""),
            advert.get("snippet", ""),
            advert.get("summary", ""),
            advert.get("extract", ""),
            advert.get("date", ""),
            advert.get("website", ""),
        ])))
        jobs.append(
            JobPosting(
                source="jobrapido_uae",
                source_job_id=source_job_id,
                title=title,
                company=company,
                location=location,
                url=url,
                description=description,
                remote="remote" in f"{title} {location}".lower(),
                country="UAE",
            )
        )

    return jobs


def parse_jobleads_jobs(raw_html: str) -> List[JobPosting]:
    pattern = re.compile(
        r'<div class="relative rounded-lg border-2 p-4.*?" data-testid="search-job-card">.*?'
        r'<h2[^>]*><!\-\-\[\-\-\><span[^>]*>(?P<title>.*?)</span>.*?'
        r'<a data-testid="search-job-card-link"[^>]+href="(?P<href>/job/[^"]+)".*?'
        r'<p[^>]+data-testid="search-job-card-company".*?<span>(?P<company>.*?)</span>.*?'
        r'data-testid="job-card-chip-location".*?<span><span>(?P<location>.*?)</span></span>.*?'
        r'data-testid="job-card-date".*?<span[^>]*><!\-\-\[\-\->(?P<date>.*?)<!\-\-\]\-\-></span>',
        re.DOTALL,
    )

    jobs: List[JobPosting] = []
    seen_urls = set()
    for match in pattern.finditer(raw_html):
        title = clean_text(match.group("title"))
        company = clean_text(match.group("company"))
        location = clean_text(match.group("location"))
        date = clean_text(match.group("date"))
        href = html.unescape(match.group("href")).strip()
        url = urllib.parse.urljoin("https://www.jobleads.com", href)
        source_job_id = href.rstrip("/").split("/")[-1]
        if not title or not url or url in seen_urls:
            continue

        seen_urls.add(url)
        if company.lower() == "only for registered members":
            company = "JobLeads member-only"
        jobs.append(
            JobPosting(
                source="jobleads",
                source_job_id=source_job_id,
                title=title,
                company=company,
                location=location,
                url=url,
                description=date,
                remote="remote" in f"{title} {location}".lower(),
                country="UAE",
            )
        )

    return jobs


def parse_gamblingcareers_jobs(raw_html: str) -> List[JobPosting]:
    """Parse GamblingCareers remote jobs from rendered HTML."""
    jobs: List[JobPosting] = []
    seen_urls = set()

    def _clean_lines(text: str) -> list[str]:
        lines = []
        for line in (text or "").splitlines():
            cleaned = clean_text(line)
            if cleaned:
                lines.append(cleaned)
        return lines

    def _split_company_location(candidate: str) -> tuple[str, str]:
        candidate = clean_text(candidate)
        patterns = [
            r"^(?P<company>.+?)\s+(?P<location>Remote(?:\s*\([^)]*\))?)$",
            r"^(?P<company>.+?)\s+(?P<location>Fully Remote(?:\s*\([^)]*\))?)$",
            r"^(?P<company>.+?)\s+(?P<location>Hybrid(?:\s*\([^)]*\))?)$",
            r"^(?P<company>.+?)\s+(?P<location>Onsite(?:\s*\([^)]*\))?)$",
        ]
        for pattern in patterns:
            match = re.match(pattern, candidate, re.IGNORECASE)
            if match:
                return clean_text(match.group("company")), clean_text(match.group("location"))
        if " remote" in candidate.lower():
            idx = candidate.lower().rfind(" remote")
            return clean_text(candidate[:idx]), clean_text(candidate[idx + 1 :])
        return candidate, ""

    anchor_pattern = re.compile(r'<a[^>]+href="(?P<href>/job/[^"]+)"[^>]*>(?P<title>.*?)</a>', re.DOTALL | re.IGNORECASE)
    anchors = list(anchor_pattern.finditer(raw_html))

    for match in anchors:
        href = html.unescape(match.group("href")).strip()
        title = clean_text(match.group("title"))
        if href in seen_urls:
            continue
        if len(title) < 3 or len(title) > 180:
            continue
        if re.search(r"(jobs found|find jobs|refine search|email me jobs like this)", title, re.IGNORECASE):
            continue
        seen_urls.add(href)

        start = max(0, match.start() - 600)
        end = min(len(raw_html), match.end() + 1400)
        context_html = raw_html[start:end]
        context_text = re.sub(r"<[^>]+>", "\n", context_html)
        card_lines = _clean_lines(context_text)
        title_index = next(
            (idx for idx, line in enumerate(card_lines) if title.lower() in line.lower()),
            -1,
        )

        company = ""
        location = ""
        description = ""
        if title_index >= 0:
            following = card_lines[title_index + 1 :]
            for idx, line in enumerate(following):
                line_lower = line.lower()
                if re.search(r"\b(remote|fully remote|hybrid|onsite)\b", line_lower):
                    company, location = _split_company_location(line)
                    description = " ".join(following[idx + 1 : idx + 4]).strip()
                    break
                if idx == 0:
                    company, location = _split_company_location(line)
                    if location:
                        description = " ".join(following[idx + 1 : idx + 4]).strip()
                        break

        if not company:
            company = "GamblingCareers"
        if not location and "remote" in f"{title} {clean_text(context_text)}".lower():
            location = "Remote"

        description = clean_text(description)
        if not description:
            description = clean_text(context_text)
            for token in [title, company, location]:
                if token:
                    description = description.replace(token, "").strip()

        jobs.append(
            JobPosting(
                source="gamblingcareers_remote",
                source_job_id=href.rstrip("/").split("/")[-1],
                title=title,
                company=company,
                location=location,
                url=urllib.parse.urljoin(GAMBLINGCAREERS_REMOTE_URL, href),
                description=description,
                remote="remote" in f"{title} {company} {location} {description}".lower(),
                country="Remote",
            )
        )

    return jobs


def fetch_gamblingcareers_jobs_via_browser() -> List[JobPosting]:
    """Fetch GamblingCareers remote jobs via the browser probe only."""
    candidate_urls = [GAMBLINGCAREERS_REMOTE_URL, *GAMBLINGCAREERS_REMOTE_FALLBACK_URLS]
    candidate_urls = [url for url in candidate_urls if url]
    if not candidate_urls:
        return []

    jobs: List[JobPosting] = []
    browser_logger.info("GamblingCareers browser fetch start: %d urls batch_size=1", len(candidate_urls))
    pages = _batch_browser_fetch(candidate_urls, batch_size=1)
    if not pages:
        logger.warning("GamblingCareers: no results from browser fetch")
        return []

    for page, url in zip(pages, candidate_urls):
        for item in page.get("jobs", []):
            url_value = clean_text(item.get("url", "").strip())
            title = clean_text(item.get("title", ""))
            company = clean_text(item.get("company", "")) or "GamblingCareers"
            location = clean_text(item.get("location", ""))
            description = clean_text(item.get("description", ""))
            source_job_id = clean_text(item.get("source_job_id", "")) or urllib.parse.urlparse(url_value).path.rstrip("/").split("/")[-1]
            if not url_value or not title:
                continue

            jobs.append(
                JobPosting(
                    source="gamblingcareers_remote",
                    source_job_id=source_job_id,
                    title=title,
                    company=company,
                    location=location,
                    url=url_value,
                    description=description,
                    remote=bool(item.get("remote", False)) or "remote" in f"{title} {company} {location} {description}".lower(),
                    country="Remote",
                )
            )

    return jobs


def fetch_himalayas_jobs_via_api() -> List[JobPosting]:
    """Fetch Himalayas iGaming jobs through the public JSON API only."""
    if not HIMALAYAS_IGAMING_API_URL:
        return []

    jobs: List[JobPosting] = []
    seen_ids = set()

    def _iter_himalayas_jobs(url: str) -> List[dict]:
        try:
            payload = fetch_json(url)
        except Exception as exc:
            logger.warning("Himalayas API fetch failed for %s: %s", url, exc)
            return []
        if isinstance(payload, dict):
            jobs_payload = payload.get("jobs", [])
            if isinstance(jobs_payload, list):
                return [item for item in jobs_payload if isinstance(item, dict)]
        return []

    def _job_text(job: dict) -> str:
        parts = [
            clean_text(job.get("title", "")),
            clean_text(job.get("companyName", "")),
            clean_text(job.get("excerpt", "")),
            clean_text(job.get("description", "")),
        ]
        for key in ("categories", "parentCategories", "seniority"):
            value = job.get(key, [])
            if isinstance(value, list):
                parts.extend(clean_text(str(item)) for item in value if item)
        return " ".join(part for part in parts if part).lower()

    def _parse_location(job: dict) -> tuple[str, str]:
        restrictions = job.get("locationRestrictions", [])
        if isinstance(restrictions, list) and restrictions:
            labels: list[str] = []
            country = "Remote"
            for restriction in restrictions:
                if isinstance(restriction, dict):
                    label = clean_text(
                        restriction.get("name")
                        or restriction.get("slug")
                        or restriction.get("alpha2")
                        or ""
                    )
                else:
                    label = clean_text(str(restriction))
                if label:
                    labels.append(label)
            location = ", ".join(labels) if labels else "Remote"
            location_lower = location.lower()
            if "malta" in location_lower or "valletta" in location_lower or "mt" == location_lower.strip():
                country = "Malta"
            elif "georgia" in location_lower or "tbilisi" in location_lower or "batumi" in location_lower or "ge" == location_lower.strip():
                country = "Georgia"
            elif "uae" in location_lower or "dubai" in location_lower or "abu dhabi" in location_lower:
                country = "UAE"
            return location, country
        return "Remote", "Remote"

    for page in range(1, 6):
        page_url = f"{HIMALAYAS_IGAMING_API_URL}&page={page}"
        items = _iter_himalayas_jobs(page_url)
        if not items:
            break
        for item in items:
            title = clean_text(item.get("title", ""))
            company = clean_text(item.get("companyName", "")) or "Himalayas"
            application_link = clean_text(item.get("applicationLink", ""))
            guid = clean_text(item.get("guid", ""))
            excerpt = clean_text(item.get("excerpt", ""))
            description = clean_text(item.get("description", ""))
            if not title:
                continue

            text_blob = _job_text(item)
            if "igaming" not in text_blob:
                # Keep the feed tightly scoped to iGaming roles.
                continue

            source_job_id = guid or application_link or title
            if source_job_id in seen_ids:
                continue
            seen_ids.add(source_job_id)

            location, country = _parse_location(item)
            remote = not location or "remote" in location.lower() or country == "Remote"
            url = application_link or page_url
            jobs.append(
                JobPosting(
                    source="himalayas_igaming",
                    source_job_id=source_job_id,
                    title=title,
                    company=company,
                    location=location,
                    url=url,
                    description=excerpt or description,
                    remote=remote,
                    country=country,
                )
            )

        if len(items) < 20:
            break

    if jobs:
        logger.info("Himalayas API parse produced %d jobs.", len(jobs))
        return jobs

    logger.warning("Himalayas API parse returned no jobs.")
    return []


def parse_ziprecruiter_jobs(raw_html: str) -> List[JobPosting]:
    """Parse ZipRecruiter remote iGaming jobs from rendered HTML."""
    jobs: List[JobPosting] = []
    seen_urls = set()

    def _is_job_title(text: str) -> bool:
        value = clean_text(text)
        if not value or len(value) < 4 or len(value) > 180:
            return False
        lowered = value.lower()
        if lowered in {
            "quick apply",
            "estimated pay",
            "all jobs",
            "remote igaming jobs (now hiring)",
            "remote igaming information",
            "what is a remote igaming job?",
        }:
            return False
        if value.startswith("$") or value.startswith("Image:"):
            return False
        return bool(re.search(r"[A-Za-z]", value))

    anchor_pattern = re.compile(
        r'<a[^>]+href="(?:(?:https?://www\.ziprecruiter\.com)|)(?P<href>/Jobs/[^"]+)"[^>]*>(?P<title>.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )

    for match in anchor_pattern.finditer(raw_html):
        href = html.unescape(match.group("href")).strip()
        title = clean_text(match.group("title"))
        if not _is_job_title(title):
            continue

        start = max(0, match.start() - 1400)
        end = min(len(raw_html), match.end() + 2200)
        context_html = raw_html[start:end]
        context_text = re.sub(r"<[^>]+>", "\n", context_html)
        lines: list[str] = []
        for line in context_text.splitlines():
            cleaned = clean_text(line)
            if cleaned:
                lines.append(cleaned)

        title_index = next(
            (
                idx
                for idx, line in enumerate(lines)
                if line.lower() == title.lower() or title.lower() in line.lower()
            ),
            -1,
        )
        if title_index < 0:
            continue

        company = ""
        location = ""
        description = ""

        before = lines[:title_index]
        after = lines[title_index + 1 :]
        for line in reversed(before[-4:]):
            line_lower = line.lower()
            if any(token in line_lower for token in ["quick apply", "estimated pay", "$", "image:", "now hiring"]):
                continue
            if len(line) <= 80 and re.search(r"[A-Za-z]", line):
                company = line
                break

        for idx, line in enumerate(after):
            line_lower = line.lower()
            if "remote" in line_lower or "on-site" in line_lower or "onsite" in line_lower or "hybrid" in line_lower or "·" in line:
                location = line
                description = " ".join(after[idx + 1 : idx + 4]).strip()
                break

        if not location:
            location = "Remote"
        if not company:
            company = "ZipRecruiter"

        url = urllib.parse.urljoin("https://www.ziprecruiter.com", href)
        source_job_id = clean_text(url.rstrip("/").split("/")[-1]) or url
        if url in seen_urls:
            continue
        seen_urls.add(url)

        location_lower = location.lower()
        country = "Remote"
        if "malta" in location_lower or "valletta" in location_lower:
            country = "Malta"
        elif "georgia" in location_lower and "atlanta" not in location_lower:
            country = "Georgia"
        elif "uae" in location_lower or "dubai" in location_lower or "abu dhabi" in location_lower:
            country = "UAE"

        jobs.append(
            JobPosting(
                source="ziprecruiter_igaming",
                source_job_id=source_job_id,
                title=title,
                company=company,
                location=location or "Remote",
                url=url,
                description=clean_text(description),
                remote=True,
                country=country,
            )
        )

    return jobs


def fetch_ziprecruiter_jobs_via_browser() -> List[JobPosting]:
    """ZipRecruiter has been removed from the active scrape set."""
    logger.info("ZipRecruiter scraping is disabled; skipping source.")
    return []


def parse_telegram_channel_jobs(raw_html: str, source: str, company_name: str) -> List[JobPosting]:
    if source == "telegram_cryptojobslist":
        return parse_cryptojobslist_jobs(raw_html)

    message_pattern = re.compile(
        r'<div class="tgme_widget_message[^"]*"[^>]*data-post="(?P<post>[^"]+)".*?>.*?'
        r'<div class="tgme_widget_message_text js-message_text"[^>]*>(?P<message>.*?)</div>'
        r'.*?<a class="tgme_widget_message_date" href="(?P<post_url>https://t\.me/[^"]+)">'
        r'<time datetime="(?P<datetime>[^"]+)"',
        re.DOTALL,
    )

    jobs: List[JobPosting] = []
    seen_urls = set()
    seen_signatures = set()
    for match in message_pattern.finditer(raw_html):
        message_html = match.group("message")
        text = clean_text(message_html)
        if not text:
            continue

        apply_match = re.search(
            r'Apply[^<]*<a href="(?P<url>https?://[^"]+)"',
            message_html,
            re.DOTALL,
        )
        preview_match = re.search(
            r'<a class="tgme_widget_message_link_preview" href="(?P<url>https?://[^"]+)"',
            match.group(0),
            re.DOTALL,
        )
        url = ""
        if apply_match:
            url = html.unescape(apply_match.group("url")).strip()
        elif preview_match:
            url = html.unescape(preview_match.group("url")).strip()
        else:
            url = html.unescape(match.group("post_url")).strip()

        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        title = ""
        company = company_name
        location = ""

        structured_company_link = re.search(
            r'<a href="https?://[^"]+"[^>]*>(?P<company>[^<]+)</a>\s+is hiring',
            message_html,
            re.IGNORECASE,
        )
        structured_company_text = re.search(
            r"^(?P<company>[A-Za-z0-9 .&/+_-]{2,80})\s+is hiring",
            text,
            re.IGNORECASE,
        )
        structured_company = re.search(r"\bat\s+(?P<company>[A-Za-z0-9 .&/+_-]{2,80})$", text, re.IGNORECASE)
        structured_location = re.search(r"(?:Location:?)[\s:]*([^\n💰✅🕑📩🔥]+)", text)

        if structured_company_link:
            company_candidate = clean_text(structured_company_link.group("company"))
            if company_candidate:
                company = company_candidate
        elif structured_company_text:
            company_candidate = clean_text(structured_company_text.group("company"))
            if company_candidate:
                company = company_candidate
        elif structured_company:
            company_candidate = clean_text(structured_company.group("company"))
            if company_candidate:
                company = company_candidate
        if structured_location:
            location_candidate = clean_text(structured_location.group(1))
            if location_candidate and len(location_candidate) <= 80:
                location = location_candidate

        if not title:
            hiring_match = re.search(r"([A-Za-z0-9 .&/-]+?)\s+is hiring[^\n]*", text, re.IGNORECASE)
            role_match = re.search(
                r"looking for (?:an?|the)\s+(?P<title>[^.!,\n]+?)(?:\s+to join|\s+who|\s+for|\.)",
                text,
                re.IGNORECASE,
            )
            if role_match:
                title = clean_text(role_match.group("title"))
            elif hiring_match:
                title = clean_text(hiring_match.group(0))
            else:
                title = clean_text(text[:120]).strip(" -|:")

        title = re.sub(r"^[^\w]+", "", title).strip()
        if title in {"🌍", "💼", "✅"}:
            title = ""
        if not title and "is hiring" in text.lower():
            title = "Business Development / Growth"

        if not location:
            if "remote" in text.lower():
                location = "Remote"
            elif "global opportunity" in text.lower() or "global" in text.lower():
                location = "Global"

        if not location:
            location_match = re.search(
                r"(Dubai|Abu Dhabi|UAE|United Arab Emirates|Remote(?: [^.]*)?|Ras Al Khaimah|Ras Al-Khaimah|Global)",
                text,
                re.IGNORECASE,
            )
            if location_match:
                location = clean_text(location_match.group(1))

        from .utils import normalize_phrase
        dedupe_signature = normalize_phrase(" | ".join([title or "telegram job post", company, location]))
        if dedupe_signature and dedupe_signature in seen_signatures:
            continue
        seen_signatures.add(dedupe_signature)

        source_job_id = match.group("post").split("/")[-1]
        jobs.append(
            JobPosting(
                source=source,
                source_job_id=source_job_id,
                title=title or "Telegram job post",
                company=company,
                location=location,
                url=url,
                description=f"{text} {match.group('datetime')}",
                country="UAE",
                remote="remote" in text.lower(),
            )
        )

    return jobs


def telegram_job_relevant(job: JobPosting, resume_text: str) -> bool:
    fit = evaluate_fit(job.to_dict(), resume_text)
    text_blob = " ".join([job.title, job.company, job.location, job.description]).lower()
    title_lower = job.title.lower()

    has_target_region = any(term in text_blob for term in ["dubai", "uae", "abu dhabi", "adgm", "south korea", "korean"])
    has_remote = "remote" in text_blob or "global" in text_blob
    has_strong_domain = any(term in text_blob for term in STRONG_DOMAIN_TERMS)
    has_target_role = any(term in title_lower for term in COMMERCIAL_ROLE_TERMS + PRODUCT_ROLE_TERMS)
    has_telegram_remote_role = any(
        term in title_lower for term in ["affiliate", "network builder", "player operations", "retention"]
    )

    if fit["qualifies"]:
        return True
    if job.source == "telegram_hr1win":
        has_1win_brand = "1win" in text_blob or "1 win" in text_blob
        has_hiring_cue = any(
            term in text_blob
            for term in [
                "hiring",
                "vacancy",
                "vacancies",
                "career",
                "apply",
                "вакан",
                "ищем",
                "карьер",
                "отклик",
            ]
        )
        if has_1win_brand and (has_target_role or has_strong_domain or has_target_region or has_remote or has_hiring_cue):
            return True
    if has_target_region and has_strong_domain and has_target_role:
        return True
    if has_remote and has_strong_domain and has_target_role and any(term in text_blob for term in ["crypto", "web3", "igaming", "casino", "digital asset", "stablecoin", "custody", "cex"]):
        return True
    if job.source == "telegram_cryptojobslist" and has_remote and has_strong_domain and (has_target_role or has_telegram_remote_role):
        return True
    return False


def parse_cryptojobslist_jobs(raw_html: str) -> List[JobPosting]:
    message_pattern = re.compile(
        r'<div class="tgme_widget_message[^"]*"[^>]*data-post="(?P<post>cryptojobslist/\d+)".*?>.*?'
        r'<div class="tgme_widget_message_text js-message_text"[^>]*>(?P<message>.*?)</div>'
        r'.*?<a class="tgme_widget_message_date" href="(?P<post_url>https://t\.me/cryptojobslist/\d+)">'
        r'<time datetime="(?P<datetime>[^"]+)"',
        re.DOTALL,
    )

    jobs: List[JobPosting] = []
    seen_urls = set()
    for match in message_pattern.finditer(raw_html):
        message_html = match.group("message")
        if "Apply" not in message_html or "💼" not in message_html or "🏛️" not in message_html:
            continue

        title_match = re.search(r"💼.*?</i>\s*<b>(?P<title>.*?)</b>", message_html, re.DOTALL)
        company_match = re.search(r"🏛️.*?</i>\s*at\s+(?P<company>[^<]+)<br", message_html, re.DOTALL)
        location_match = re.search(r"🌍.*?</i>\s*(?P<location>[^<]+)<br", message_html, re.DOTALL)
        apply_match = re.search(r'Apply\s*→\s*<a href="(?P<url>https://cjl\.ist/[^"]+)"', message_html, re.DOTALL)

        if not title_match or not company_match or not apply_match:
            continue

        title = clean_text(title_match.group("title"))
        company = clean_text(company_match.group("company"))
        location = clean_text(location_match.group("location")) if location_match else ""
        url = html.unescape(apply_match.group("url")).strip()
        if not title or not company or not url or url in seen_urls:
            continue
        seen_urls.add(url)

        text = clean_text(message_html)
        jobs.append(
            JobPosting(
                source="telegram_cryptojobslist",
                source_job_id=match.group("post").split("/")[-1],
                country="UAE",
                title=title,
                company=company,
                location=location,
                url=url,
                description=f"{text} {match.group('datetime')}",
                remote="remote" in text.lower(),
            )
        )

    return jobs


def fetch_telegram_channel_jobs() -> List[JobPosting]:
    if not BROWSER_PROBE_PATH.exists():
        logger.warning("Skipping Telegram: browser probe script not found at %s", BROWSER_PROBE_PATH)
        return []

    jobs: List[JobPosting] = []
    for channel in TELEGRAM_CHANNELS:
        try:
            logger.info("Telegram browser probe start: %s", channel["url"])
            returncode, stdout, _stderr = _run_browser_probe_with_progress(
                ["node", str(BROWSER_PROBE_PATH), channel["url"]],
                timeout=240,
            )
            if returncode != 0:
                raise subprocess.SubprocessError(f"browser probe exited with {returncode}")
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            logger.warning("Skipping Telegram channel %s: %s", channel["url"], exc)
            continue
        stdout = stdout.strip()
        if not stdout:
            logger.warning("Skipping Telegram channel %s: empty browser output.", channel["url"])
            continue
        try:
            page = json.loads(stdout)
        except json.JSONDecodeError as exc:
            logger.warning("Skipping Telegram channel %s: invalid JSON output (%s).", channel["url"], exc)
            continue
        raw_html = page.get("html", "")
        if not raw_html:
            logger.warning("Skipping Telegram channel %s: no HTML in browser output.", channel["url"])
            continue
        channel_jobs = parse_telegram_channel_jobs(
            raw_html,
            channel["source"],
            channel["company"],
        )
        logger.info("Collected %s jobs from Telegram channel %s.", len(channel_jobs), channel["company"])
        jobs.extend(channel_jobs)
    return jobs


def _batch_browser_fetch(urls: List[str], batch_size: int) -> List[dict]:
    """Fetch browser pages in parallel batches. Returns list of page results."""
    if not BROWSER_PROBE_PATH.exists():
        logger.warning("Browser probe script not found at %s", BROWSER_PROBE_PATH)
        return []

    indexed_batches = [
        (start, urls[start:start + batch_size])
        for start in range(0, len(urls), batch_size)
    ]
    ordered_results: list[dict | None] = [None] * len(urls)

    def run_batch(batch: List[str]) -> List[dict]:
        command = ["node", str(BROWSER_PROBE_PATH)] + batch
        try:
            browser_logger.info("Browser probe batch start: %d urls", len(batch))
            returncode, stdout, _stderr = _run_browser_probe_with_progress(command, timeout=600)
            if returncode != 0:
                raise subprocess.SubprocessError(f"browser probe exited with {returncode}")
            stdout = stdout.strip()
            if not stdout:
                return [{"jobs": [], "error": "empty output"} for _ in batch]

            pages = json.loads(stdout)
            if not isinstance(pages, list):
                pages = [pages]
            return pages
        except Exception as exc:
            browser_logger.warning("Batch processing failed: %s", exc)
            return [{"jobs": [], "error": str(exc)} for _ in batch]

    browser_logger.info(
        "Browser probe queue start: %d urls batch_size=%d workers=%d",
        len(urls),
        batch_size,
        BROWSER_BATCH_WORKERS,
    )
    with ThreadPoolExecutor(max_workers=BROWSER_BATCH_WORKERS) as executor:
        futures = {executor.submit(run_batch, batch): (start, len(batch)) for start, batch in indexed_batches}
        for future in as_completed(futures):
            try:
                results = future.result()
                start, batch_len = futures[future]
                for offset, page in enumerate(results[:batch_len]):
                    if start + offset < len(ordered_results):
                        ordered_results[start + offset] = page
            except Exception as exc:
                browser_logger.warning("Batch fetch failed: %s", exc)

    return [page for page in ordered_results if page is not None]


def _batch_browserless_fetch(
    script_path: Path,
    urls: List[str],
    batch_size: int,
    workers: int | None = None,
) -> List[dict]:
    """Fetch Browserless pages in parallel batches. Returns list of page results."""
    if not script_path.exists():
        logger.warning("Browserless probe script not found at %s", script_path)
        return []

    indexed_batches = [
        (start, urls[start:start + batch_size])
        for start in range(0, len(urls), batch_size)
    ]
    ordered_results: list[dict | None] = [None] * len(urls)

    def run_batch(batch: List[str]) -> List[dict]:
        command = ["node", str(script_path)] + batch
        try:
            browser_logger.info("Browserless batch start: %d urls", len(batch))
            returncode, stdout, stderr = _run_browser_probe_with_progress(command, timeout=600)
            if returncode != 0:
                stderr_tail = " | ".join((stderr or "").splitlines()[-6:])
                if stderr_tail:
                    logger.warning("Browserless probe stderr: %s", stderr_tail)
                raise subprocess.SubprocessError(f"browserless probe exited with {returncode}")
            stdout = stdout.strip()
            if not stdout:
                return [{"jobs": [], "error": "empty output"} for _ in batch]

            pages = json.loads(stdout)
            if not isinstance(pages, list):
                pages = [pages]
            return pages
        except Exception as exc:
            browser_logger.warning("Browserless batch processing failed: %s", exc)
            return [{"jobs": [], "error": str(exc)} for _ in batch]

    browser_logger.info(
        "Browserless probe queue start: %d urls batch_size=%d workers=%d",
        len(urls),
        batch_size,
        workers or BROWSER_BATCH_WORKERS,
    )
    with ThreadPoolExecutor(max_workers=workers or BROWSER_BATCH_WORKERS) as executor:
        futures = {executor.submit(run_batch, batch): (start, len(batch)) for start, batch in indexed_batches}
        for future in as_completed(futures):
            try:
                results = future.result()
                start, batch_len = futures[future]
                for offset, page in enumerate(results[:batch_len]):
                    if start + offset < len(ordered_results):
                        ordered_results[start + offset] = page
            except Exception as exc:
                browser_logger.warning("Browserless batch fetch failed: %s", exc)

    return [page for page in ordered_results if page is not None]


def fetch_indeed_jobs_via_browser() -> List[JobPosting]:
    if not INDEED_SEARCH_URLS:
        return []

    jobs: List[JobPosting] = []
    seen_urls = set()
    collected_at = utc_now().isoformat()

    browser_logger.info(
        "Indeed browser fetch start: %d urls batch_size=%d",
        len(INDEED_SEARCH_URLS),
        BROWSER_INDEED_BATCH_SIZE,
    )
    pages = _batch_browser_fetch(INDEED_SEARCH_URLS, batch_size=BROWSER_INDEED_BATCH_SIZE)
    if not pages:
        logger.warning("Indeed: no results from browser fetch")
        return []

    for search_url, page in zip(INDEED_SEARCH_URLS, pages):
        for item in page.get("jobs", []):
            url = normalize_linkedin_url(item.get("url", "").strip())
            title = clean_text(item.get("title", ""))
            if not url or not title or url in seen_urls:
                continue

            seen_urls.add(url)
            source_job_id = clean_text(item.get("source_job_id", "")) or urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]

            location_str = clean_text(item.get("location", "")).lower()
            search_lower = search_url.lower()

            # Determine country from job location or search URL
            country = None
            source_name = None

            # Check location_str first for explicit keywords
            if "malta" in location_str or "valletta" in location_str or "몰타" in location_str:
                country = "Malta"
                source_name = "indeed_malta"
            elif "georgia" in location_str or "조지아" in location_str or "tbilisi" in location_str or "트빌리시" in location_str:
                country = "Georgia"
                source_name = "indeed_georgia"
            elif "dubai" in location_str or "emirates" in location_str or "uae" in location_str or "abu dhabi" in location_str:
                country = "UAE"
                source_name = "indeed_uae"

            # Fallback to search URL if location is ambiguous or empty
            if not country:
                if "malta" in search_lower or "valletta" in search_lower:
                    country = "Malta"
                    source_name = "indeed_malta"
                elif "georgia" in search_lower or "tbilisi" in search_lower or "ge.indeed.com" in search_lower:
                    country = "Georgia"
                    source_name = "indeed_georgia"
                elif "dubai" in search_lower or "emirates" in search_lower or "uae" in search_lower:
                    country = "UAE"
                    source_name = "indeed_uae"

            # Skip jobs from wrong regions (e.g., USA jobs when searching UAE)
            if not country:
                logger.debug("Skipping Indeed job with unclear location: %s from URL %s", location_str, search_url)
                continue

            # Validate location doesn't contain excluded countries (USA, UK, etc.)
            if any(x in location_str for x in ["united states", "usa", "united kingdom", "uk", "canada", "california", "new york", "texas", "ohio", "oh", "florida", "fl", "remote - usa"]):
                logger.debug("Skipping Indeed job from excluded region: %s", location_str)
                continue

            jobs.append(
                JobPosting(
                    source=source_name,
                    source_job_id=source_job_id,
                    title=title,
                    company=clean_text(item.get("company", "")) or "Indeed",
                    location=clean_text(item.get("location", "")),
                    url=url,
                    description=clean_text(item.get("description", "")),
                    remote=bool(item.get("remote", False)),
                    country=country,
                    collected_at=collected_at,
                )
            )

    return jobs


def fetch_indeed_jobs_via_jobspy() -> List[JobPosting]:
    """Fetch Indeed jobs using JobSpy library across UAE, Malta, Georgia."""
    scrape_jobs = _get_jobspy_scrape_jobs()
    if not scrape_jobs:
        logger.warning("JobSpy not available, skipping Indeed scraping")
        return []

    jobs: List[JobPosting] = []
    seen_urls = set()
    collected_at = utc_now().isoformat()

    # Search locations
    locations = [
        {"name": "UAE", "country": "UAE", "query_location": "Dubai, United Arab Emirates"},
        {"name": "Malta", "country": "Malta", "query_location": "Malta"},
        {"name": "Georgia", "country": "Georgia", "query_location": "Tbilisi, Georgia"},
    ]

    for location in locations:
        for keyword in INDEED_SEARCH_KEYWORDS:
            try:
                # Clean up keyword: remove quotes if present
                clean_keyword = keyword.strip('"').strip()
                logger.debug(f"JobSpy search: {clean_keyword} in {location['name']}")

                jobs_df = scrape_jobs(
                    site_name=["indeed"],
                    search_term=clean_keyword,
                    location=location["query_location"],
                    results_wanted=50,
                    hours_old=24,
                    country_indeed=location["country"].lower(),
                )

                if jobs_df is None or jobs_df.empty:
                    continue

                for _, row in jobs_df.iterrows():
                    url = row.get("job_url", "").strip()
                    title = clean_text(row.get("job_title", ""))

                    if not url or not title or url in seen_urls:
                        continue

                    seen_urls.add(url)

                    jobs.append(
                        JobPosting(
                            source="indeed_jobspy" if location["country"] == "UAE" else f"indeed_{location['country'].lower()}",
                            source_job_id=urllib.parse.urlparse(url).query.split("&")[0] if url else "",
                            title=title,
                            company=clean_text(row.get("company", "")) or "Indeed",
                            location=clean_text(row.get("location", "")),
                            url=url,
                            description=clean_text(row.get("description", "")),
                            remote=bool(row.get("remote", False)),
                            country=location["country"],
                            collected_at=collected_at,
                        )
                    )

            except Exception as e:
                logger.warning(f"JobSpy error for '{keyword}' in {location['name']}: {e}")
                continue

    logger.info(f"JobSpy Indeed: collected {len(jobs)} jobs from {len(seen_urls)} unique URLs")
    return jobs


def fetch_linkedin_jobs_via_browser() -> List[JobPosting]:
    all_urls = [*LINKEDIN_SEARCH_URLS, *RECRUITER_SEARCH_URLS]
    if not all_urls:
        return []

    jobs: List[JobPosting] = []
    seen_urls = set()
    collected_at = utc_now().isoformat()

    browser_logger.info(
        "LinkedIn browser fetch start: %d urls batch_size=%d",
        len(all_urls),
        BROWSER_LINKEDIN_BATCH_SIZE,
    )
    pages = _batch_browser_fetch(all_urls, batch_size=BROWSER_LINKEDIN_BATCH_SIZE)
    if not pages:
        logger.warning("LinkedIn: no results from browser fetch")
        return []

    for search_url, page in zip(all_urls, pages):
        for item in page.get("jobs", []):
            url = item.get("url", "").strip()
            title = clean_text(item.get("title", ""))
            if not url or not title or url in seen_urls:
                continue

            seen_urls.add(url)
            source_job_id = clean_text(item.get("source_job_id", "")) or urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]

            location_str = clean_text(item.get("location", "")).lower()
            search_lower = search_url.lower()

            # Determine country from job location or search URL
            country = None
            source_name = None

            # Check location_str first for explicit keywords
            if "malta" in location_str or "valletta" in location_str or "몰타" in location_str:
                country = "Malta"
                source_name = "linkedin_malta"
            elif "georgia" in location_str or "조지아" in location_str or "tbilisi" in location_str or "트빌리시" in location_str or "batumi" in location_str or "바투미" in location_str:
                country = "Georgia"
                source_name = "linkedin_georgia"
            elif "dubai" in location_str or "emirates" in location_str or "uae" in location_str or "abu dhabi" in location_str or "sharjah" in location_str:
                country = "UAE"
                source_name = "linkedin_public"

            # Fallback to search URL if location is ambiguous or empty
            if not country:
                if "malta" in search_lower or "valletta" in search_lower:
                    country = "Malta"
                    source_name = "linkedin_malta"
                elif "georgia" in search_lower or "tbilisi" in search_lower:
                    country = "Georgia"
                    source_name = "linkedin_georgia"
                elif "dubai" in search_lower or "emirates" in search_lower or "uae" in search_lower:
                    country = "UAE"
                    source_name = "linkedin_public"

            # Skip jobs from wrong regions (e.g., USA jobs when searching UAE)
            if not country:
                logger.debug("Skipping LinkedIn job with unclear location: %s from URL %s", location_str, search_url)
                continue

            # Validate location doesn't contain excluded countries (USA, UK, etc.)
            if any(x in location_str for x in ["united states", "usa", "united kingdom", "uk", "canada", "california", "new york", "texas", "ohio", "oh", "florida", "fl"]):
                logger.debug("Skipping LinkedIn job from excluded region: %s", location_str)
                continue

            jobs.append(
                JobPosting(
                    source=source_name,
                    source_job_id=source_job_id,
                    title=title,
                    company=clean_text(item.get("company", "")) or "LinkedIn",
                    location=clean_text(item.get("location", "")),
                    url=url,
                    description=clean_text(item.get("description", "")),
                    remote=bool(item.get("remote", False)),
                    country=country,
                    collected_at=collected_at,
                )
            )

    return jobs


def fetch_glassdoor_jobs_via_browserless() -> List[JobPosting]:
    if not GLASSDOOR_BROWSERLESS_SEARCH_URLS:
        return []

    if not GLASSDOOR_BROWSERLESS_PROBE_PATH.exists():
        logger.warning("Glassdoor Browserless probe script not found at %s", GLASSDOOR_BROWSERLESS_PROBE_PATH)
        return []

    jobs: List[JobPosting] = []
    seen_urls = set()
    collected_at = utc_now().isoformat()

    browser_logger.info(
        "Glassdoor browserless fetch start: %d urls batch_size=%d",
        len(GLASSDOOR_BROWSERLESS_SEARCH_URLS),
        BROWSER_GLASSDOOR_BATCH_SIZE,
    )
    pages = _batch_browserless_fetch(
        GLASSDOOR_BROWSERLESS_PROBE_PATH,
        GLASSDOOR_BROWSERLESS_SEARCH_URLS,
        batch_size=BROWSER_GLASSDOOR_BATCH_SIZE,
        workers=BROWSER_GLASSDOOR_BATCH_WORKERS,
    )
    if not pages:
        logger.warning("Glassdoor: no results from browserless fetch")
        return []

    for search_url, page in zip(GLASSDOOR_BROWSERLESS_SEARCH_URLS, pages):
        for item in page.get("jobs", []):
            url = clean_text(item.get("url", "").strip())
            title = clean_text(item.get("title", ""))
            if not url or not title or url in seen_urls:
                continue

            seen_urls.add(url)
            source_job_id = clean_text(item.get("source_job_id", "")) or urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]

            location = clean_text(item.get("location", ""))
            location_lower = location.lower()
            search_lower = search_url.lower()

            country = "UAE"
            source_name = "glassdoor_uae"
            if any(x in location_lower for x in ["malta", "valletta", "georgia", "tbilisi"]):
                continue
            if any(x in search_lower for x in ["malta", "georgia"]):
                continue

            jobs.append(
                JobPosting(
                    source=source_name,
                    source_job_id=source_job_id,
                    title=title,
                    company=clean_text(item.get("company", "")) or "Glassdoor",
                    location=location,
                    url=url,
                    description=clean_text(item.get("description", "")),
                    remote=bool(item.get("remote", False)),
                    country=country,
                    collected_at=collected_at,
                )
            )

    return jobs



def fetch_rss_news(feed_url: str, source: str) -> List[NewsItem]:
    """
    Parse RSS 2.0 or Atom feed, extract title, link, published_at, description.
    Handles pubDate (RFC 2822) and published (ISO 8601) timestamps.
    Returns list of NewsItem, skipping malformed entries.
    """
    try:
        raw_xml = fetch_html(feed_url)
    except Exception as e:
        logger.warning("Failed to fetch RSS feed %s: %s", feed_url, e)
        return []

    items: List[NewsItem] = []

    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as e:
        logger.warning("Failed to parse RSS XML from %s: %s", feed_url, e)
        return []

    # Determine namespace (Atom vs RSS 2.0)
    ns = {"atom": "http://www.w3.org/2005/Atom"}

    # Try RSS 2.0 first (<rss><channel><item>)
    items_elements = root.findall(".//item")
    if not items_elements:
        # Try Atom (<feed><entry>)
        items_elements = root.findall("atom:entry", ns)

    for item_elem in items_elements:
        try:
            # Extract title
            title_elem = item_elem.find("title")
            if title_elem is None:
                title_elem = item_elem.find("atom:title", ns)
            title = clean_text(title_elem.text or "") if title_elem is not None else ""
            if not title:
                continue

            # Extract link
            link_elem = item_elem.find("link")
            if link_elem is None:
                link_elem = item_elem.find("atom:link", ns)
            link = ""
            if link_elem is not None:
                if link_elem.text:
                    link = link_elem.text
                elif link_elem.get("href"):
                    link = link_elem.get("href")
            if not link:
                continue

            # Extract published_at (pubDate or published)
            pub_elem = item_elem.find("pubDate")
            if pub_elem is None:
                pub_elem = item_elem.find("atom:published", ns)

            published_at = ""
            if pub_elem is not None and pub_elem.text:
                try:
                    # Try RFC 2822 (RSS pubDate)
                    dt = parsedate_to_datetime(pub_elem.text)
                    published_at = dt.isoformat()
                    
                    # 날짜 검증: 미래 날짜 방지
                    # Finextra 등 이벤트 페이지는 미래 날짜를 게시할 수 있음
                    # 현재 시간보다 1일 이상 미래면 현재 시간으로 대체
                    from datetime import datetime, timezone, timedelta
                    now = datetime.now(timezone.utc)
                    # Timezone-naive datetime을 UTC로 정규화
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt > now + timedelta(days=1):
                        # 이벤트 페이지 필터링 (URL에 event-info 포함)
                        if "event-info" not in link:
                            # 일반 기사가 1일 이상 미래 날짜면 문제 있음, 현재 시간으로
                            published_at = utc_now().isoformat()
                        else:
                            # 이벤트 페이지는 미래 날짜가 정상
                            published_at = dt.isoformat()
                except (TypeError, ValueError):
                    try:
                        # Try ISO 8601 (Atom published)
                        dt = datetime.fromisoformat(pub_elem.text.replace("Z", "+00:00"))
                        published_at = dt.isoformat()
                    except ValueError:
                        published_at = ""

            if not published_at:
                published_at = utc_now().isoformat()

            # Extract summary (description or summary)
            desc_elem = item_elem.find("description")
            if desc_elem is None:
                desc_elem = item_elem.find("atom:summary", ns)
            summary = clean_text(desc_elem.text or "") if desc_elem is not None else ""
            summary = summary[:150]  # Trim to 150 chars

            # 이벤트 페이지 필터링 (Finextra event-info)
            if "finextra.com" in link and "event-info" in link:
                logger.debug(f"Skipping event page: {title[:50]}...")
                continue
                    
            items.append(
                NewsItem(
                    source=source,
                    title=title,
                    url=link,
                    published_at=published_at,
                    summary=summary,
                )
            )

        except Exception as e:
            logger.warning("Skipped malformed RSS item from %s: %s", feed_url, e)
            continue

    return items


def fetch_all_player_rss_news() -> List[NewsItem]:
    """Fetch player official RSS feeds, skip individual failures, deduplicate by URL."""
    all_items: List[NewsItem] = []
    seen_urls: set[str] = set()

    for feed_config in PLAYER_RSS_FEEDS:
        try:
            url = feed_config.get("url")
            source = feed_config.get("source")
            player = feed_config.get("player", source)

            logger.info("Fetching player RSS feed: %s", player)
            items = fetch_rss_news(url, source)
            logger.info("Collected %d items from %s", len(items), player)

            for item in items:
                if item.url not in seen_urls:
                    all_items.append(item)
                    seen_urls.add(item.url)

        except Exception as e:
            logger.warning("Failed to fetch player RSS feed %s: %s", feed_config.get("player", "unknown"), e)
            continue

    return all_items


def fetch_all_rss_news() -> List[NewsItem]:
    """Fetch all configured RSS feeds in parallel, skip individual failures, deduplicate by URL."""
    all_items: List[NewsItem] = []
    seen_urls: set[str] = set()

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            executor.submit(fetch_rss_news, feed_config.get("url"), feed_config.get("source")): feed_config
            for feed_config in NEWS_RSS_FEEDS
        }

        for future in as_completed(futures):
            feed_config = futures[future]
            label = feed_config.get("label", feed_config.get("source"))
            try:
                logger.info("Fetching RSS feed: %s", label)
                items = future.result()
                logger.info("Collected %d items from %s", len(items), label)

                for item in items:
                    if item.url not in seen_urls:
                        all_items.append(item)
                        seen_urls.add(item.url)

            except Exception as e:
                logger.warning("Failed to fetch RSS feed %s: %s", label, e)

    return all_items


def fetch_reddit_posts(query: str, subreddit: str = None, limit: int = 10) -> List[dict]:
    """
    Fetch posts from Reddit via JSON API (on-demand).

    Args:
        query: Search keyword
        subreddit: Optional subreddit name (e.g., "dubai", "jobs", "igaming")
        limit: Number of results (default 10)

    Returns:
        List of dicts with: title, url, subreddit, score, created_utc, selftext (first 150 chars)
    """
    try:
        # Build URL
        if subreddit:
            url = f"https://www.reddit.com/r/{subreddit}/search.json?q={urllib.parse.quote(query)}&restrict_sr=on&sort=new&limit={limit}"
        else:
            url = f"https://www.reddit.com/search.json?q={urllib.parse.quote(query)}&sort=new&limit={limit}"

        # Custom User-Agent for Reddit
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "python:agent-job-scout:v1.0 (by /u/agent)"
            }
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        posts = []
        for child in data.get("data", {}).get("children", []):
            post_data = child.get("data", {})

            # Skip stickied/pinned posts and removed content
            if post_data.get("stickied") or post_data.get("removed_by_category"):
                continue

            # Extract fields
            title = post_data.get("title", "")
            post_url = post_data.get("url", "")
            if post_data.get("is_self"):  # Self-post, use permalink
                post_url = f"https://reddit.com{post_data.get('permalink', '')}"

            selftext = post_data.get("selftext", "")
            summary = selftext[:150] + "..." if len(selftext) > 150 else selftext

            posts.append({
                "title": title,
                "url": post_url,
                "subreddit": post_data.get("subreddit", "unknown"),
                "score": post_data.get("score", 0),
                "created_utc": post_data.get("created_utc", 0),
                "summary": summary,
            })

        logger.info("Fetched %d posts from Reddit (query='%s', subreddit=%s)", len(posts), query, subreddit or "all")
        return posts

    except Exception as e:
        logger.warning("Failed to fetch Reddit posts (query='%s', subreddit=%s): %s", query, subreddit, e)
        return []
