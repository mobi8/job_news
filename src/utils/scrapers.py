#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import logging
import re
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List

from .config import (
    BROWSER_PROBE_PATH,
    COMMERCIAL_ROLE_TERMS,
    IGAMING_RECRUITMENT_URL,
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
from .utils import clean_text, normalize_linkedin_identifier, normalize_linkedin_url, utc_now

logger = logging.getLogger(__name__)


def fetch_html(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


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

        title_match = re.search(r"💼</b></i>\s*<b>(?P<title>.*?)</b><br/>", message_html, re.DOTALL)
        company_match = re.search(r"🏛️</b></i>\s*at\s*(?P<company>.*?)<br/>", message_html, re.DOTALL)
        location_match = re.search(r"🌍</b></i>\s*(?P<location>.*?)<br/>", message_html, re.DOTALL)
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
            completed = subprocess.run(
                ["node", str(BROWSER_PROBE_PATH), channel["url"]],
                capture_output=True,
                text=True,
                check=True,
                timeout=240,
            )
        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            logger.warning("Skipping Telegram channel %s: %s", channel["url"], exc)
            continue
        stdout = completed.stdout.strip()
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


def fetch_indeed_jobs_via_browser() -> List[JobPosting]:
    if not BROWSER_PROBE_PATH.exists():
        logger.warning("Skipping Indeed: browser probe script not found at %s", BROWSER_PROBE_PATH)
        return []

    jobs: List[JobPosting] = []
    seen_urls = set()
    collected_at = utc_now().isoformat()

    # Batch all Indeed URLs in one node call
    command = ["node", str(BROWSER_PROBE_PATH)] + INDEED_SEARCH_URLS

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("Indeed browser scraping failed: %s", exc)
        return []

    stdout = completed.stdout.strip()
    if not stdout:
        logger.warning("Indeed: empty browser output")
        return []

    try:
        pages = json.loads(stdout)
        # Handle both single page and array of pages
        if not isinstance(pages, list):
            pages = [pages]
    except json.JSONDecodeError as exc:
        logger.warning("Indeed: invalid JSON output (%s)", exc)
        return []

    for search_url, page in zip(INDEED_SEARCH_URLS, pages):
        for item in page.get("jobs", []):
            url = normalize_linkedin_url(item.get("url", "").strip())
            title = clean_text(item.get("title", ""))
            if not url or not title or url in seen_urls:
                continue

            seen_urls.add(url)
            source_job_id = clean_text(item.get("source_job_id", "")) or urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]

            # Location 필드를 확인해서 country 결정
            location_str = clean_text(item.get("location", "")).lower()
            source_name = "indeed_uae"
            country = "UAE"

            # Location 기반 국가 판단 (우선순위 높음)
            if "malta" in location_str or "valletta" in location_str or "몰타" in location_str:
                country = "Malta"
                source_name = "indeed_malta"
            elif "georgia" in location_str or "조지아" in location_str or "tbilisi" in location_str or "트빌리시" in location_str:
                country = "Georgia"
                source_name = "indeed_georgia"
            # URL 기반 판단 (location이 없을 때 폴백)
            elif "ge.indeed.com" in search_url:
                country = "Georgia"
                source_name = "indeed_georgia"

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


def fetch_linkedin_jobs_via_browser() -> List[JobPosting]:
    if not BROWSER_PROBE_PATH.exists():
        logger.warning("Skipping LinkedIn: browser probe script not found at %s", BROWSER_PROBE_PATH)
        return []

    jobs: List[JobPosting] = []
    seen_urls = set()
    all_urls = [*LINKEDIN_SEARCH_URLS, *RECRUITER_SEARCH_URLS]
    collected_at = utc_now().isoformat()

    # Batch all LinkedIn URLs in one node call
    command = ["node", str(BROWSER_PROBE_PATH)] + all_urls

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        logger.warning("LinkedIn browser scraping failed: %s", exc)
        return []

    stdout = completed.stdout.strip()
    if not stdout:
        logger.warning("LinkedIn: empty browser output")
        return []

    try:
        pages = json.loads(stdout)
        # Handle both single page and array of pages
        if not isinstance(pages, list):
            pages = [pages]
    except json.JSONDecodeError as exc:
        logger.warning("LinkedIn: invalid JSON output (%s)", exc)
        return []

    for search_url, page in zip(all_urls, pages):

        for item in page.get("jobs", []):
            url = item.get("url", "").strip()
            title = clean_text(item.get("title", ""))
            if not url or not title or url in seen_urls:
                continue

            seen_urls.add(url)
            source_job_id = clean_text(item.get("source_job_id", "")) or urllib.parse.urlparse(url).path.rstrip("/").split("/")[-1]

            # Location 필드를 확인해서 country 결정
            location_str = clean_text(item.get("location", "")).lower()
            source_name = "linkedin_public"
            country = "UAE"
            search_lower = search_url.lower()

            # Location 기반 국가 판단 (우선순위 높음)
            if "malta" in location_str or "valletta" in location_str or "몰타" in location_str:
                country = "Malta"
                source_name = "linkedin_malta"
            elif "georgia" in location_str or "조지아" in location_str or "tbilisi" in location_str or "트빌리시" in location_str or "batumi" in location_str or "바투미" in location_str:
                country = "Georgia"
                source_name = "linkedin_georgia"
            # URL 기반 판단 (location이 없을 때 폴백)
            elif "malta" in search_lower or "valletta" in search_lower:
                country = "Malta"
                source_name = "linkedin_malta"
            elif "georgia" in search_lower or "tbilisi" in search_lower:
                country = "Georgia"
                source_name = "linkedin_georgia"

            jobs.append(
                JobPosting(
                    source=source_name,
                    source_job_id=source_job_id,
                    title=title,
                    company=clean_text(item.get("company", "")) or "LinkedIn",
                    location=clean_text(item.get("location", "")),
                    url=url,
                    country=country,
                    description=clean_text(item.get("description", "")),
                    remote=bool(item.get("remote", False)),
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
    """Fetch all configured RSS feeds, skip individual failures, deduplicate by URL."""
    all_items: List[NewsItem] = []
    seen_urls: set[str] = set()

    for feed_config in NEWS_RSS_FEEDS:
        try:
            url = feed_config.get("url")
            source = feed_config.get("source")
            label = feed_config.get("label", source)

            logger.info("Fetching RSS feed: %s", label)
            items = fetch_rss_news(url, source)
            logger.info("Collected %d items from %s", len(items), label)

            for item in items:
                if item.url not in seen_urls:
                    all_items.append(item)
                    seen_urls.add(item.url)

        except Exception as e:
            logger.warning("Failed to fetch RSS feed %s: %s", feed_config.get("label", "unknown"), e)
            continue

    return all_items
