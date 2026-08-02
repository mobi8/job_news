#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import sys
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "collection_sources.yaml"


@dataclass(frozen=True)
class SearchTarget:
    url: str
    target_id: str
    source: str
    country: str
    location: str
    location_terms: tuple[str, ...] = ()
    exclude_terms: tuple[str, ...] = ()
    keyword_group_id: str = ""
    keyword_query: str = ""


def _load_yaml(path: Path = CONFIG_PATH) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        raise RuntimeError(
            "PyYAML is required to read config/collection_sources.yaml. "
            "Install project dependencies with `pip install -r requirements.txt`."
        ) from None
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a mapping at the top level")
    return payload


def load_collection_registry(path: Path = CONFIG_PATH) -> dict[str, Any]:
    registry = _load_yaml(path)
    if registry.get("version") != 1:
        raise ValueError("collection source registry version must be 1")
    registry.setdefault("sources", {})
    registry.setdefault("source_metadata", [])
    return registry


REGISTRY = load_collection_registry()


def _enabled(item: dict[str, Any]) -> bool:
    return bool(item.get("enabled", True))


def _sources() -> dict[str, Any]:
    return REGISTRY.get("sources", {})


def _keyword_groups(target: dict[str, Any]) -> list[dict[str, str]]:
    groups = target.get("keyword_groups") or []
    if isinstance(groups, list):
        return [group for group in groups if isinstance(group, dict) and group.get("query")]
    return []


def _url_config(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("url") or {}
    return value if isinstance(value, dict) else {}


def _location_terms(item: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(term).lower() for term in item.get("location_terms", []) if str(term).strip())


def _exclude_terms(item: dict[str, Any]) -> tuple[str, ...]:
    return tuple(str(term).lower() for term in item.get("exclude_terms", []) if str(term).strip())


def build_linkedin_jobs_url(
    *,
    query: str | None,
    location: str | None,
    geo_id: str | None = None,
    remote: bool = False,
    extra_params: dict[str, str] | None = None,
) -> str:
    params: dict[str, str] = {}
    if query:
        params["keywords"] = query
    if geo_id:
        params["geoId"] = geo_id
    if location:
        params["location"] = location
    if remote:
        params["f_WT"] = "2"
    if extra_params:
        params.update({k: v for k, v in extra_params.items() if v is not None})
    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


def build_indeed_url(*, domain: str, query: str, location: str, sort: str = "date") -> str:
    params = {"q": query, "l": location}
    if sort:
        params["sort"] = sort
    return f"https://{domain}/jobs?" + urllib.parse.urlencode(params)


def build_glassdoor_uae_url(keyword: str) -> str:
    slug = keyword.strip().lower().replace(" ", "-")
    end = len(slug)
    return f"https://www.glassdoor.com/Job/{slug}-jobs-SRCH_IN6_KO0,{end}.htm"


def _drjobs_keyword_to_slug(keyword: str) -> str:
    cleaned = str(keyword).strip()
    cleaned = cleaned.split(" OR ", 1)[0].strip(" \"'()")
    slug = "".join(ch if ch.isalnum() else "-" for ch in cleaned.lower())
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "search"


def build_drjobs_url(keyword: str) -> str:
    return f"https://drjobs.ae/{_drjobs_keyword_to_slug(keyword)}-jobs"


def _search_target(
    *,
    url: str,
    target: dict[str, Any],
    keyword_group: dict[str, str] | None = None,
) -> SearchTarget:
    return SearchTarget(
        url=url,
        target_id=str(target.get("id") or ""),
        source=str(target.get("source") or ""),
        country=str(target.get("country") or ""),
        location=str(target.get("location") or target.get("display_location") or ""),
        location_terms=_location_terms(target),
        exclude_terms=_exclude_terms(target),
        keyword_group_id=str((keyword_group or {}).get("id") or ""),
        keyword_query=str((keyword_group or {}).get("query") or target.get("keyword_query") or ""),
    )


def build_linkedin_job_targets(include_recruiters: bool = True) -> list[SearchTarget]:
    targets: list[SearchTarget] = []
    source_config = _sources().get("linkedin_jobs", {})
    if source_config.get("enabled", True):
        for target in source_config.get("targets", []):
            if not _enabled(target):
                continue
            override = _url_config(target).get("explicit_override")
            groups = _keyword_groups(target)
            if override:
                targets.append(_search_target(url=override, target=target))
                continue
            for group in groups:
                targets.append(
                    _search_target(
                        url=build_linkedin_jobs_url(
                            query=group["query"],
                            location=target.get("location"),
                            geo_id=target.get("geo_id"),
                            remote=bool(target.get("remote")),
                        ),
                        target=target,
                        keyword_group=group,
                    )
                )
    if include_recruiters:
        recruiters = _sources().get("recruiters", {})
        if recruiters.get("enabled", True):
            for target in recruiters.get("targets", []):
                if not _enabled(target):
                    continue
                override = _url_config(target).get("explicit_override")
                url = override or build_linkedin_jobs_url(
                    query=target.get("keyword_query"),
                    location=target.get("location"),
                    geo_id=target.get("geo_id"),
                    remote=bool(target.get("remote")),
                )
                targets.append(_search_target(url=url, target=target))
    return targets


def build_recruiter_search_targets() -> list[SearchTarget]:
    all_targets = build_linkedin_job_targets(include_recruiters=True)
    recruiter_ids = {
        str(target.get("id"))
        for target in (_sources().get("recruiters", {}).get("targets") or [])
        if _enabled(target)
    }
    return [target for target in all_targets if target.target_id in recruiter_ids]


def build_indeed_search_targets() -> list[SearchTarget]:
    targets: list[SearchTarget] = []
    config = _sources().get("indeed", {})
    if not config.get("enabled", True):
        return targets
    for target in config.get("targets", []):
        if not _enabled(target):
            continue
        override = _url_config(target).get("explicit_override")
        groups = _keyword_groups(target)
        if override:
            targets.append(_search_target(url=override, target=target))
            continue
        for group in groups:
            targets.append(
                _search_target(
                    url=build_indeed_url(
                        domain=str(target.get("domain") or "ae.indeed.com"),
                        query=group["query"],
                        location=str(target.get("location") or ""),
                        sort=str(target.get("sort") or "date"),
                    ),
                    target=target,
                    keyword_group=group,
                )
            )
    return targets


def build_glassdoor_search_targets() -> list[SearchTarget]:
    config = _sources().get("glassdoor", {})
    if not config.get("enabled", True):
        return []
    target = {
        "id": "glassdoor_uae",
        "source": config.get("source", "glassdoor_uae"),
        "country": config.get("country", "UAE"),
        "location": config.get("country", "UAE"),
    }
    urls = list(config.get("explicit_urls") or [])
    urls.extend(build_glassdoor_uae_url(keyword) for keyword in config.get("keywords", []))
    return [_search_target(url=url, target={**target, "id": f"glassdoor_{idx}"}) for idx, url in enumerate(urls, 1)]


def build_drjobs_search_targets() -> list[SearchTarget]:
    config = _sources().get("drjobs", {})
    if not config.get("enabled", True):
        return []
    target = {
        "id": "drjobs",
        "source": config.get("source", "drjobs"),
        "country": config.get("country", "UAE"),
        "location": config.get("country", "UAE"),
    }
    urls: list[str] = []
    seen: set[str] = set()
    for url in config.get("explicit_urls", []):
        if url not in seen:
            urls.append(url)
            seen.add(url)
    for keyword in config.get("keywords", []):
        url = build_drjobs_url(keyword)
        if url not in seen:
            urls.append(url)
            seen.add(url)
    return [_search_target(url=url, target={**target, "id": f"drjobs_{idx}"}) for idx, url in enumerate(urls, 1)]


def build_linkedin_post_plans() -> list[dict[str, Any]]:
    config = _sources().get("linkedin_posts", {})
    if not config.get("enabled", True):
        return []
    plans: list[dict[str, Any]] = []
    for location in config.get("locations", []):
        if not _enabled(location):
            continue
        for role in config.get("roles", []):
            for lead in config.get("leads", []):
                plans.append(
                    {
                        "category": lead.get("category", "hiring_post"),
                        "domain": role.get("domain", role.get("id", "")),
                        "country": location.get("country"),
                        "store_country": location.get("store_country", location.get("country")),
                        "display_location": location.get("label", location.get("country")),
                        "location_terms": location.get("location_terms", []),
                        "source": config.get("source", "linkedin_post"),
                        "query": f"{lead.get('query')} {role.get('query')} {location.get('query_location')}",
                    }
                )
    return plans


def enabled_job_pages() -> list[dict[str, Any]]:
    return [item for item in _sources().get("job_pages", []) if _enabled(item)]


def enabled_news_feeds() -> list[dict[str, Any]]:
    return [item for item in _sources().get("news_feeds", []) if _enabled(item)]


def enabled_player_feeds() -> list[dict[str, Any]]:
    return [item for item in _sources().get("player_feeds", []) if _enabled(item)]


def source_metadata() -> list[dict[str, Any]]:
    feeds = []
    for item in enabled_news_feeds():
        feeds.append(
            {
                "id": item.get("source"),
                "label": item.get("label"),
                "kind": "news",
                "group": item.get("category", "News"),
                "enabled": True,
            }
        )
    for item in enabled_player_feeds():
        feeds.append(
            {
                "id": item.get("source"),
                "label": item.get("label") or item.get("player"),
                "kind": "news",
                "group": item.get("category", "Players"),
                "enabled": True,
            }
        )
    return [*REGISTRY.get("source_metadata", []), *feeds]


def source_label_map() -> dict[str, str]:
    return {str(item.get("id")): str(item.get("label")) for item in source_metadata() if item.get("id")}


def source_country_map() -> dict[str, str]:
    return {str(item.get("id")): str(item.get("country")) for item in source_metadata() if item.get("id") and item.get("country")}


def source_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in source_metadata():
        source_id = str(item.get("id") or "")
        if not source_id:
            continue
        aliases[source_id] = source_id
        for alias in item.get("aliases", []) or []:
            aliases[str(alias).strip().lower()] = source_id
    return aliases


def target_metadata_by_url(targets: list[SearchTarget]) -> dict[str, dict[str, Any]]:
    return {
        target.url: {
            "target_id": target.target_id,
            "source": target.source,
            "country": target.country,
            "location": target.location,
            "location_terms": list(target.location_terms),
            "exclude_terms": list(target.exclude_terms),
            "keyword_group_id": target.keyword_group_id,
            "keyword_query": target.keyword_query,
        }
        for target in targets
    }


def _runtime_int(section: str, key: str, default: int, env_name: str | None = None) -> int:
    if env_name and os.getenv(env_name):
        raw = os.getenv(env_name, "")
    else:
        raw = str(REGISTRY.get("runtime", {}).get(section, {}).get(key, default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def runtime_default_sources() -> str:
    return str(REGISTRY.get("runtime", {}).get("defaults", {}).get("job_watch_sources", ""))


def linkedin_post_filters() -> dict[str, Any]:
    return dict(_sources().get("linkedin_posts", {}).get("filters", {}))


def linkedin_post_location_terms_by_country() -> dict[str, list[str]]:
    config = _sources().get("linkedin_posts", {})
    return {
        str(location.get("country")): list(location.get("location_terms") or [])
        for location in config.get("locations", [])
        if _enabled(location)
    }


def validate_registry() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    url_sources: dict[str, list[str]] = defaultdict(list)

    def check_id(source_id: str, where: str) -> None:
        if not source_id:
            errors.append(f"{where}: missing id/source")
            return
        if source_id in seen_ids:
            errors.append(f"{where}: duplicate id {source_id}")
        seen_ids.add(source_id)

    def check_url(url: str, where: str, allow_duplicate: bool = False) -> None:
        if not url:
            errors.append(f"{where}: empty URL")
            return
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors.append(f"{where}: invalid URL {url}")
        url_sources[url].append(where if not allow_duplicate else f"{where} (allowed duplicate)")

    for page in enabled_job_pages():
        check_id(str(page.get("id") or ""), "job_pages")
        if not page.get("parser"):
            errors.append(f"job_pages.{page.get('id')}: missing parser")
        check_url(str(page.get("url") or ""), f"job_pages.{page.get('id')}", bool(page.get("allow_duplicate_url")))

    for feed in [*enabled_news_feeds(), *enabled_player_feeds()]:
        check_id(str(feed.get("id") or ""), "feeds")
        if not feed.get("parser"):
            errors.append(f"feed.{feed.get('id')}: missing parser")
        check_url(str(feed.get("url") or ""), f"feed.{feed.get('id')}", bool(feed.get("allow_duplicate_url")))

    for target in [
        *build_linkedin_job_targets(),
        *build_indeed_search_targets(),
        *build_glassdoor_search_targets(),
        *build_drjobs_search_targets(),
    ]:
        check_url(target.url, f"target.{target.target_id}")

    for url, where in sorted(url_sources.items()):
        if len(where) > 1 and not all("allowed duplicate" in item for item in where):
            warnings.append(f"duplicate URL {url}: {', '.join(where)}")

    return errors, warnings


def check_summary() -> str:
    errors, warnings = validate_registry()
    linkedin_targets = build_linkedin_job_targets(include_recruiters=False)
    recruiter_targets = build_recruiter_search_targets()
    indeed_targets = build_indeed_search_targets()
    glassdoor_targets = build_glassdoor_search_targets()
    drjobs_targets = build_drjobs_search_targets()
    rss_feeds = enabled_news_feeds()
    player_feeds = enabled_player_feeds()
    all_urls = [
        *(page.get("url") for page in enabled_job_pages()),
        *(target.url for target in linkedin_targets),
        *(target.url for target in recruiter_targets),
        *(target.url for target in indeed_targets),
        *(target.url for target in glassdoor_targets),
        *(target.url for target in drjobs_targets),
        *(feed.get("url") for feed in rss_feeds),
        *(feed.get("url") for feed in player_feeds),
    ]
    duplicate_count = sum(1 for _, count in Counter(all_urls).items() if count > 1)
    lines = ["Config valid" if not errors else "Config invalid", ""]
    lines.extend(
        [
            "Job collection:",
            f"- Generated LinkedIn URLs: {len(linkedin_targets)}",
            f"- Generated Indeed URLs: {len(indeed_targets)}",
            f"- Explicit job pages: {len(enabled_job_pages())}",
            f"- Browserless URLs: {len(glassdoor_targets)}",
            f"- DrJobs browser URLs: {len(drjobs_targets)}",
            f"- JobSpy targets: {len([t for t in _sources().get('jobspy', {}).get('targets', []) if _enabled(t)])}",
            f"- LinkedIn Posts plans: {len(build_linkedin_post_plans())}",
            "",
            "News collection:",
            f"- RSS feeds enabled: {len(rss_feeds)}",
            "- Atom feeds enabled: 0",
            f"- Player feeds enabled: {len(player_feeds)}",
            "",
            "URL validation:",
            f"- Unique external URLs: {len(set(all_urls))}",
            f"- Duplicate URL warnings: {duplicate_count}",
            f"- Invalid URLs: {len(errors)}",
            "",
            "Runtime:",
            f"- LinkedIn Posts batches: {_runtime_int('linkedin_posts', 'batch_size', 5)}",
        ]
    )
    if warnings:
        lines.extend(["", "Warnings:", *[f"- {warning}" for warning in warnings]])
    if errors:
        lines.extend(["", "Errors:", *[f"- {error}" for error in errors]])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-urls", action="store_true", help="Reserved for a future lightweight URL health check")
    args = parser.parse_args(argv)
    if args.check or args.check_urls:
        print(check_summary())
        errors, _ = validate_registry()
        return 1 if errors else 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


JOB_PAGES = enabled_job_pages()
JOBVITE_URL = next(item["url"] for item in JOB_PAGES if item["source"] == "jobvite_pragmaticplay")
SMARTRECRUITMENT_URL = next(item["url"] for item in JOB_PAGES if item["source"] == "smartrecruitment")
IGAMING_RECRUITMENT_URL = next(item["url"] for item in JOB_PAGES if item["source"] == "igamingrecruitment")
IGAMINGHUNT_BAMBOOHR_URL = next(item["url"] for item in JOB_PAGES if item["source"] == "igaminghunt_bamboohr")
JOBRAPIDO_URL = next(item["url"] for item in JOB_PAGES if item["source"] == "jobrapido_uae")
JOBLEADS_URL = next(item["url"] for item in JOB_PAGES if item["source"] == "jobleads")
TELEGRAM_CHANNELS = [item for item in _sources().get("telegram_channels", []) if _enabled(item)]

LINKEDIN_JOB_TARGETS = build_linkedin_job_targets(include_recruiters=False)
RECRUITER_SEARCH_TARGETS = build_recruiter_search_targets()
INDEED_SEARCH_TARGETS = build_indeed_search_targets()
GLASSDOOR_BROWSERLESS_TARGETS = build_glassdoor_search_targets()
DRJOBS_SEARCH_TARGETS = build_drjobs_search_targets()

LINKEDIN_SEARCH_URLS = [target.url for target in LINKEDIN_JOB_TARGETS]
RECRUITER_SEARCH_URLS = [target.url for target in RECRUITER_SEARCH_TARGETS]
INDEED_SEARCH_URLS = [target.url for target in INDEED_SEARCH_TARGETS]
GLASSDOOR_BROWSERLESS_SEARCH_URLS = [target.url for target in GLASSDOOR_BROWSERLESS_TARGETS]
GLASSDOOR_BROWSERLESS_KEYWORDS = list(_sources().get("glassdoor", {}).get("keywords", []))
DRJOBS_SEARCH_URLS = [target.url for target in DRJOBS_SEARCH_TARGETS]

LINKEDIN_SEARCH_URL_METADATA = target_metadata_by_url(LINKEDIN_JOB_TARGETS + RECRUITER_SEARCH_TARGETS)
INDEED_SEARCH_URL_METADATA = target_metadata_by_url(INDEED_SEARCH_TARGETS)
GLASSDOOR_SEARCH_URL_METADATA = target_metadata_by_url(GLASSDOOR_BROWSERLESS_TARGETS)
DRJOBS_SEARCH_URL_METADATA = target_metadata_by_url(DRJOBS_SEARCH_TARGETS)

LINKEDIN_POST_SEARCH_PLANS = build_linkedin_post_plans()
LINKEDIN_POST_FILTERS = linkedin_post_filters()
LINKEDIN_POST_LOCATION_TERMS_BY_COUNTRY = linkedin_post_location_terms_by_country()

NEWS_RSS_FEEDS = enabled_news_feeds()
PLAYER_RSS_FEEDS = enabled_player_feeds()
LINKEDIN_SEARCH_KEYWORDS = list(REGISTRY.get("keyword_groups", {}).get("linkedin", []))
INDEED_SEARCH_KEYWORDS = list(REGISTRY.get("keyword_groups", {}).get("indeed", []))
GLASSDOOR_SEARCH_KEYWORDS = list(INDEED_SEARCH_KEYWORDS)
GOOGLE_SEARCH_KEYWORDS = list(REGISTRY.get("keyword_groups", {}).get("google", []))
SEARCH_KEYWORDS = LINKEDIN_SEARCH_KEYWORDS
JOBSPY_COUNTRY_PLANS = [item for item in _sources().get("jobspy", {}).get("targets", []) if _enabled(item)]
RECRUITER_COMPANIES = list(_sources().get("recruiters", {}).get("companies", []))
NEWS_TOPICS = list(REGISTRY.get("topics", {}).get("news", []))
FOCUS_LOCATION_TERMS = list(REGISTRY.get("filters", {}).get("focus_location_terms", []))
REMOTE_GCC_LOCATION_TERMS = list(REGISTRY.get("filters", {}).get("remote_gcc_location_terms", []))
FOCUS_DOMAIN_TERMS = list(REGISTRY.get("filters", {}).get("focus_domain_terms", []))
SOURCE_METADATA = source_metadata()
SOURCE_LABELS = source_label_map()
SOURCE_COUNTRIES = source_country_map()
SOURCE_ALIASES = source_alias_map()
