#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.getenv("COLLECTION_SOURCES_CONFIG_PATH") or ROOT / "config" / "collection_sources.yaml")


@dataclass(frozen=True)
class SearchTarget:
    url: str
    target_id: str
    source: str
    country: str
    location: str
    region: str = ""
    location_terms: tuple[str, ...] = ()
    exclude_terms: tuple[str, ...] = ()
    keyword_group_id: str = ""
    keyword_query: str = ""
    company: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CollectionPhase:
    id: str
    label: str
    description: str
    aliases: tuple[str, ...]
    order: int
    enabled: bool
    timeout_seconds: int
    supports_target: bool
    telegram_visible: bool
    writes_database: bool
    sends_notification: bool
    full_run_included: bool
    execution_mode: str


@dataclass(frozen=True)
class SelectorCandidate:
    phase: str
    target_id: str
    label: str
    source: str
    country: str
    region: str
    url: str = ""
    player: str = ""
    company: str = ""
    category: str = ""
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectorResolution:
    phase: str
    selector: str
    status: str
    match_kind: str = ""
    targets: tuple[SelectorCandidate, ...] = ()
    candidates: tuple[str, ...] = ()
    message: str = ""
    target_group_id: str = ""
    target_group_label: str = ""
    subselector: str = ""
    keyword_group_id: str = ""
    keyword_group_label: str = ""
    keyword_group_ids: tuple[str, ...] = ()
    keyword_queries: tuple[str, ...] = ()


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


def _normalize_selector(value: Any) -> str:
    return "_".join(str(value or "").strip().lower().replace("-", "_").split())


def _target_filter() -> dict[str, Any] | None:
    raw = os.getenv("COLLECTION_TARGET_FILTER_JSON", "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _target_filter_phase() -> str:
    payload = _target_filter() or {}
    return str(payload.get("phase") or "")


def target_filter_keyword_queries(default: list[str]) -> list[str]:
    payload = _target_filter()
    if not payload:
        return default
    queries = [str(item) for item in payload.get("keyword_queries", []) or [] if str(item).strip()]
    return queries or default


def _filter_search_targets(phase: str, targets: list["SearchTarget"]) -> list["SearchTarget"]:
    payload = _target_filter()
    if not payload:
        return targets
    active_phase = str(payload.get("phase") or "")
    if active_phase != phase:
        return [] if active_phase in {"linkedin", "recruiters"} and phase in {"linkedin", "recruiters"} else targets
    target_ids = {str(item) for item in payload.get("target_ids", []) or []}
    urls = {str(item) for item in payload.get("urls", []) or []}
    keyword_group_ids = {str(item) for item in payload.get("keyword_group_ids", []) or []}
    keyword_queries = {str(item) for item in payload.get("keyword_queries", []) or []}
    if not target_ids and not urls and not keyword_group_ids and not keyword_queries:
        return targets
    return [
        target
        for target in targets
        if (not target_ids or target.target_id in target_ids)
        and (not urls or target.url in urls)
        and (not keyword_group_ids or target.keyword_group_id in keyword_group_ids)
        and (not keyword_queries or target.keyword_query in keyword_queries)
    ]


def _filter_dict_targets(phase: str, targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = _target_filter()
    if not payload or str(payload.get("phase") or "") != phase:
        return targets
    target_ids = {str(item) for item in payload.get("target_ids", []) or []}
    if not target_ids:
        return targets
    return [target for target in targets if str(target.get("id") or "") in target_ids]


def _sources() -> dict[str, Any]:
    return REGISTRY.get("sources", {})


def _runtime() -> dict[str, Any]:
    return REGISTRY.get("runtime", {})


def _int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _keyword_groups(target: dict[str, Any]) -> list[dict[str, str]]:
    groups = target.get("keyword_groups") or []
    if isinstance(groups, list):
        return [group for group in groups if isinstance(group, dict) and group.get("query")]
    return []


def _keyword_id(value: Any) -> str:
    return _normalize_selector(value).strip("_")


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
        region=str(target.get("region") or ""),
        location=str(target.get("location") or target.get("display_location") or ""),
        location_terms=_location_terms(target),
        exclude_terms=_exclude_terms(target),
        keyword_group_id=str((keyword_group or {}).get("id") or ""),
        keyword_query=str((keyword_group or {}).get("query") or target.get("keyword_query") or ""),
        company=str(target.get("company") or ""),
        aliases=tuple(str(alias) for alias in target.get("aliases", []) or [] if str(alias).strip()),
    )


def build_linkedin_job_targets(include_recruiters: bool = True) -> list[SearchTarget]:
    targets: list[SearchTarget] = []
    if not include_recruiters and _target_filter_phase() == "recruiters":
        return []
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
    if include_recruiters:
        return targets
    return _filter_search_targets("linkedin", targets)


def build_recruiter_search_targets() -> list[SearchTarget]:
    if _target_filter_phase() == "linkedin":
        return []
    all_targets = build_linkedin_job_targets(include_recruiters=True)
    recruiter_ids = {
        str(target.get("id"))
        for target in (_sources().get("recruiters", {}).get("targets") or [])
        if _enabled(target)
    }
    return _filter_search_targets("recruiters", [target for target in all_targets if target.target_id in recruiter_ids])


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
    return _filter_search_targets("indeed", targets)


def build_glassdoor_search_targets() -> list[SearchTarget]:
    config = _sources().get("glassdoor", {})
    if not config.get("enabled", True):
        return []
    targets: list[SearchTarget] = []
    for target in config.get("targets", []):
        if not _enabled(target):
            continue
        groups: list[dict[str, str]] = []
        urls = []
        for index, url in enumerate(target.get("explicit_urls") or [], start=1):
            urls.append(str(url))
            groups.append({"id": f"explicit_{index}", "query": str(url)})
        for keyword in target.get("keywords", []):
            urls.append(build_glassdoor_uae_url(keyword))
            groups.append({"id": _keyword_id(keyword), "query": str(keyword)})
        for idx, url in enumerate(urls, 1):
            targets.append(
                _search_target(
                    url=url,
                    target={**target, "id": f"{target.get('id', 'glassdoor')}_{idx}"},
                    keyword_group=groups[idx - 1],
                )
            )
    return _filter_search_targets("glassdoor", targets)


def build_drjobs_search_targets() -> list[SearchTarget]:
    config = _sources().get("drjobs", {})
    if not config.get("enabled", True):
        return []
    targets: list[SearchTarget] = []
    for target in config.get("targets", []):
        if not _enabled(target):
            continue
        urls: list[str] = []
        seen: set[str] = set()
        groups: list[dict[str, str]] = []
        for url in target.get("explicit_urls", []):
            if url not in seen:
                urls.append(url)
                seen.add(url)
                slug = str(url).rstrip("/").split("/")[-1].removesuffix("-jobs")
                groups.append({"id": _keyword_id(slug), "query": slug.replace("-", " ")})
        for keyword in target.get("keywords", []):
            url = build_drjobs_url(keyword)
            if url not in seen:
                urls.append(url)
                seen.add(url)
                groups.append({"id": _keyword_id(keyword), "query": str(keyword)})
        for idx, url in enumerate(urls, 1):
            targets.append(
                _search_target(
                    url=url,
                    target={**target, "id": f"{target.get('id', 'drjobs')}_{idx}"},
                    keyword_group=groups[idx - 1],
                )
            )
    return _filter_search_targets("drjobs", targets)


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
                        "location_id": location.get("id"),
                        "role_id": role.get("id"),
                        "lead_id": lead.get("id"),
                        "domain": role.get("domain", role.get("id", "")),
                        "country": location.get("country"),
                        "store_country": location.get("store_country", location.get("country")),
                        "display_location": location.get("label", location.get("country")),
                        "location_terms": location.get("location_terms", []),
                        "source": config.get("source", "linkedin_post"),
                        "query": f"{lead.get('query')} {role.get('query')} {location.get('query_location')}",
                    }
                )
    return _filter_post_plans(plans)


def _filter_post_plans(plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = _target_filter()
    if not payload or str(payload.get("phase") or "") != "posts":
        return plans
    location_ids = {str(item) for item in payload.get("target_ids", []) or []}
    role_ids = {str(item) for item in payload.get("keyword_group_ids", []) or []}
    if location_ids:
        plans = [plan for plan in plans if str(plan.get("location_id") or "") in location_ids]
    if role_ids:
        plans = [plan for plan in plans if str(plan.get("role_id") or plan.get("domain") or "") in role_ids]
    return plans


def enabled_job_pages() -> list[dict[str, Any]]:
    return _filter_dict_targets("fixed", [item for item in _sources().get("job_pages", []) if _enabled(item)])


def enabled_news_feeds() -> list[dict[str, Any]]:
    return _filter_dict_targets("rss", [item for item in _sources().get("news_feeds", []) if _enabled(item)])


def enabled_player_feeds() -> list[dict[str, Any]]:
    return _filter_dict_targets("player", [item for item in _sources().get("player_feeds", []) if _enabled(item)])


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
            "region": target.region,
            "location": target.location,
            "location_terms": list(target.location_terms),
            "exclude_terms": list(target.exclude_terms),
            "keyword_group_id": target.keyword_group_id,
            "keyword_query": target.keyword_query,
            "company": target.company,
            "aliases": list(target.aliases),
        }
        for target in targets
    }


def _source_aliases(source: str) -> tuple[str, ...]:
    aliases = []
    source_key = str(source or "")
    for item in REGISTRY.get("source_metadata", []) or []:
        if str(item.get("id") or "") == source_key:
            aliases.extend(str(alias) for alias in item.get("aliases", []) or [])
    return tuple(alias for alias in aliases if alias)


def _candidate_from_search_target(phase: str, target: SearchTarget) -> SelectorCandidate:
    aliases = (*target.aliases, *_source_aliases(target.source))
    return SelectorCandidate(
        phase=phase,
        target_id=target.target_id,
        label=target.target_id,
        source=target.source,
        country=target.country,
        region=target.region,
        url=target.url,
        company=target.company,
        aliases=aliases,
    )


def _candidate_from_mapping(phase: str, item: dict[str, Any]) -> SelectorCandidate:
    source = str(item.get("source") or "")
    return SelectorCandidate(
        phase=phase,
        target_id=str(item.get("id") or source or item.get("label") or ""),
        label=str(item.get("label") or item.get("company") or item.get("player") or item.get("id") or source or ""),
        source=source,
        country=str(item.get("country") or ""),
        region=str(item.get("region") or ""),
        url=str(item.get("url") or ""),
        player=str(item.get("player") or ""),
        company=str(item.get("company") or ""),
        category=str(item.get("category") or item.get("parser") or ""),
        aliases=tuple(str(alias) for alias in item.get("aliases", []) or []) + _source_aliases(source),
    )


def _phase_source_config(phase: str) -> dict[str, Any]:
    sources = _sources()
    mapping = {
        "linkedin": "linkedin_jobs",
        "indeed": "indeed",
        "jobspy": "jobspy",
        "glassdoor": "glassdoor",
        "drjobs": "drjobs",
        "posts": "linkedin_posts",
        "recruiters": "recruiters",
    }
    value = sources.get(mapping.get(phase, ""), {})
    return value if isinstance(value, dict) else {}


def _target_groups_for_phase(phase: str) -> list[dict[str, Any]]:
    groups = _phase_source_config(phase).get("target_groups") or []
    return [group for group in groups if isinstance(group, dict) and _enabled(group)]


def _target_group_values(group: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(value)
        for value in [
            group.get("id"),
            group.get("label"),
            group.get("country"),
            group.get("region"),
            group.get("source"),
            group.get("site"),
            *(group.get("aliases", []) or []),
        ]
        if str(value or "").strip()
    )


def _targets_for_group(group: dict[str, Any], candidates: list[SelectorCandidate]) -> list[SelectorCandidate]:
    target_ids = {str(item) for item in group.get("target_ids", []) or []}
    sources = {str(item) for item in group.get("sources", []) or []}
    country = str(group.get("country") or "")
    region = str(group.get("region") or "")
    if target_ids:
        return [candidate for candidate in candidates if candidate.target_id in target_ids]
    matched = candidates
    if sources:
        matched = [candidate for candidate in matched if candidate.source in sources]
    if country:
        matched = [candidate for candidate in matched if _normalize_selector(candidate.country) == _normalize_selector(country)]
    if region:
        matched = [candidate for candidate in matched if _normalize_selector(candidate.region) == _normalize_selector(region)]
    return matched


def _resolve_target_group(phase: str, selector: str, candidates: list[SelectorCandidate]) -> tuple[dict[str, Any] | None, list[SelectorCandidate]]:
    needle = _normalize_selector(selector)
    for group in _target_groups_for_phase(phase):
        if _normalize_selector(group.get("id")) == needle:
            return group, _targets_for_group(group, candidates)
    for group in _target_groups_for_phase(phase):
        aliases = [group.get("label"), *(group.get("aliases", []) or [])]
        if any(_normalize_selector(value) == needle for value in aliases if value):
            return group, _targets_for_group(group, candidates)
    return None, []


def _keyword_group_values(group: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        str(value)
        for value in [
            group.get("id"),
            group.get("label"),
            group.get("name"),
            *(group.get("aliases", []) or []),
        ]
        if str(value or "").strip()
    )


def _keyword_groups_for_selection(phase: str, target_group: dict[str, Any] | None, targets: list[SelectorCandidate]) -> list[dict[str, Any]]:
    configured = (target_group or {}).get("keyword_groups") or []
    if configured:
        return [group for group in configured if isinstance(group, dict) and _enabled(group)]
    if phase in {"linkedin", "indeed", "glassdoor", "drjobs"}:
        groups: dict[str, dict[str, Any]] = {}
        for target in targets:
            metadata = target_metadata_by_url(_search_targets_for_phase(phase)).get(target.url, {})
            group_id = str(metadata.get("keyword_group_id") or "")
            query = str(metadata.get("keyword_query") or "")
            if group_id and group_id not in groups:
                groups[group_id] = {"id": group_id, "query": query}
        return list(groups.values())
    if phase == "posts":
        roles = _phase_source_config("posts").get("roles") or []
        return [role for role in roles if isinstance(role, dict)]
    if phase == "recruiters":
        groups = []
        for target in targets:
            if target.company:
                groups.append({"id": _keyword_id(target.company), "label": target.company, "target_ids": [target.target_id]})
            query = target_metadata_by_url(_search_targets_for_phase("recruiters")).get(target.url, {}).get("keyword_query")
            if query:
                for token in str(query).replace("OR", " ").split():
                    if len(token) >= 4:
                        groups.append({"id": _keyword_id(token), "label": token, "target_ids": [target.target_id]})
        return groups
    return []


def _search_targets_for_phase(phase: str) -> list[SearchTarget]:
    if phase == "linkedin":
        return build_linkedin_job_targets(include_recruiters=False)
    if phase == "recruiters":
        return build_recruiter_search_targets()
    if phase == "indeed":
        return build_indeed_search_targets()
    if phase == "glassdoor":
        return build_glassdoor_search_targets()
    if phase == "drjobs":
        return build_drjobs_search_targets()
    return []


def _keyword_group_payload(
    phase: str,
    keyword_group: dict[str, Any],
    targets: list[SelectorCandidate],
) -> tuple[list[SelectorCandidate], tuple[str, ...], tuple[str, ...]]:
    target_ids = {str(item) for item in keyword_group.get("target_ids", []) or []}
    keyword_group_ids = {str(item) for item in keyword_group.get("keyword_group_ids", []) or []}
    queries = [str(item) for item in keyword_group.get("keyword_queries", []) or [] if str(item).strip()]
    if keyword_group.get("query"):
        queries.append(str(keyword_group.get("query")))
    if phase == "posts":
        role_ids = {str(keyword_group.get("id") or ""), str(keyword_group.get("domain") or "")}
        return targets, tuple(item for item in role_ids if item), tuple(queries)
    if target_ids:
        targets = [target for target in targets if target.target_id in target_ids]
    if phase == "jobspy" and keyword_group_ids:
        for target in _phase_source_config("indeed").get("targets", []) or []:
            for group in target.get("keyword_groups", []) or []:
                if isinstance(group, dict) and str(group.get("id") or "") in keyword_group_ids and group.get("query"):
                    queries.append(str(group.get("query")))
    if keyword_group_ids:
        search_targets = [
            target
            for target in _search_targets_for_phase(phase)
            if target.target_id in {candidate.target_id for candidate in targets}
            and target.keyword_group_id in keyword_group_ids
        ]
        if search_targets:
            urls = {target.url for target in search_targets}
            targets = [target for target in targets if target.url in urls]
            queries.extend(target.keyword_query for target in search_targets if target.keyword_query)
    return targets, tuple(keyword_group_ids or [str(keyword_group.get("id") or "")]), tuple(dict.fromkeys(queries))


def _resolve_keyword_group(
    phase: str,
    subselector: str,
    target_group: dict[str, Any] | None,
    targets: list[SelectorCandidate],
) -> tuple[dict[str, Any] | None, list[SelectorCandidate], tuple[str, ...], tuple[str, ...], str]:
    groups = _keyword_groups_for_selection(phase, target_group, targets)
    needle = _normalize_selector(subselector)
    for kind in ("exact", "partial"):
        matches = []
        for group in groups:
            values = _keyword_group_values(group)
            if kind == "exact" and any(_normalize_selector(value) == needle for value in values):
                matches.append(group)
            elif kind == "partial" and any(needle and needle in _normalize_selector(value) for value in values):
                matches.append(group)
        unique = {_normalize_selector(group.get("id") or group.get("label")) for group in matches}
        if len(unique) == 1 and matches:
            selected = matches[0]
            filtered_targets, keyword_ids, queries = _keyword_group_payload(phase, selected, targets)
            return selected, filtered_targets, keyword_ids, queries, kind
        if len(unique) > 1:
            return None, [], (), (), "ambiguous"
    return None, [], (), (), "unknown"


def selector_candidates_for_phase(phase: str) -> list[SelectorCandidate]:
    phase = str(phase or "").strip().lower()
    if phase == "linkedin":
        return [_candidate_from_search_target("linkedin", target) for target in build_linkedin_job_targets(include_recruiters=False)]
    if phase == "recruiters":
        return [_candidate_from_search_target("recruiters", target) for target in build_recruiter_search_targets()]
    if phase == "indeed":
        return [_candidate_from_search_target("indeed", target) for target in build_indeed_search_targets()]
    if phase == "glassdoor":
        return [_candidate_from_search_target("glassdoor", target) for target in build_glassdoor_search_targets()]
    if phase == "drjobs":
        return [_candidate_from_search_target("drjobs", target) for target in build_drjobs_search_targets()]
    if phase == "jobspy":
        return [_candidate_from_mapping("jobspy", target) for target in JOBSPY_COUNTRY_PLANS]
    if phase == "fixed":
        return [_candidate_from_mapping("fixed", target) for target in enabled_job_pages()]
    if phase == "rss":
        return [_candidate_from_mapping("rss", target) for target in enabled_news_feeds()]
    if phase == "player":
        return [_candidate_from_mapping("player", target) for target in enabled_player_feeds()]
    if phase == "posts":
        locations = _phase_source_config("posts").get("locations") or []
        return [
            _candidate_from_mapping(
                "posts",
                {
                    **location,
                    "source": _phase_source_config("posts").get("source", "linkedin_post"),
                    "id": location.get("id"),
                    "url": "",
                },
            )
            for location in locations
            if isinstance(location, dict) and _enabled(location)
        ]
    return []


def _resolution_options(candidate: SelectorCandidate) -> dict[str, tuple[str, ...]]:
    return {
        "target_id": (candidate.target_id,),
        "alias": candidate.aliases,
        "country": (candidate.country,),
        "region": (candidate.region,),
        "source": (candidate.source, candidate.player, candidate.company, candidate.category),
    }


def _candidate_labels(candidates: list[SelectorCandidate]) -> tuple[str, ...]:
    labels = []
    seen = set()
    for candidate in candidates:
        label = candidate.target_id or candidate.label or candidate.source
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return tuple(labels[:12])


def _matching_by_kind(candidates: list[SelectorCandidate], selector: str, kind: str) -> list[SelectorCandidate]:
    needle = _normalize_selector(selector)
    matched: list[SelectorCandidate] = []
    for candidate in candidates:
        values = _resolution_options(candidate).get(kind, ())
        if any(_normalize_selector(value) == needle for value in values if value):
            matched.append(candidate)
    return matched


def _keyword_group_labels(groups: list[dict[str, Any]]) -> tuple[str, ...]:
    labels = []
    seen = set()
    for group in groups:
        label = str(group.get("id") or group.get("label") or group.get("name") or "")
        if label and label not in seen:
            labels.append(label)
            seen.add(label)
    return tuple(labels[:12])


def selector_phase_ids() -> set[str]:
    return {
        "fixed",
        "drjobs",
        "linkedin",
        "indeed",
        "jobspy",
        "glassdoor",
        "rss",
        "player",
        "posts",
        "recruiters",
    }


def keyword_phase_ids() -> set[str]:
    return {"linkedin", "indeed", "jobspy", "glassdoor", "drjobs", "posts", "recruiters"}


def _discovery_url_count(phase: str, targets: list[SelectorCandidate], keyword_groups: list[dict[str, Any]] | None = None) -> int:
    if phase == "posts":
        posts_config = _phase_source_config("posts")
        leads = [lead for lead in posts_config.get("leads", []) or [] if isinstance(lead, dict)]
        roles = keyword_groups or [role for role in posts_config.get("roles", []) or [] if isinstance(role, dict)]
        return len(targets) * len(roles) * len(leads)
    urls = {target.url for target in targets if target.url}
    return len(urls) or len(targets)


def discovery_target_groups(phase: str) -> tuple[str, list[dict[str, Any]]]:
    phase = str(phase or "").strip().lower()
    candidates = selector_candidates_for_phase(phase)
    if not candidates:
        return "empty", []
    configured = _target_groups_for_phase(phase)
    groups: list[dict[str, Any]] = []
    for group in configured:
        targets = _targets_for_group(group, candidates)
        keywords = _keyword_groups_for_selection(phase, group, targets)
        groups.append(
            {
                "id": str(group.get("id") or ""),
                "label": str(group.get("label") or group.get("id") or ""),
                "aliases": [str(alias) for alias in group.get("aliases", []) or []],
                "target_count": len({target.target_id for target in targets}),
                "url_count": _discovery_url_count(phase, targets, keywords),
                "keyword_count": len(keywords),
            }
        )
    if groups:
        return "ok", groups

    by_id: dict[str, list[SelectorCandidate]] = {}
    for candidate in candidates:
        by_id.setdefault(candidate.target_id, []).append(candidate)
    for target_id, items in by_id.items():
        first = items[0]
        label = first.label or target_id
        groups.append(
            {
                "id": target_id,
                "label": label,
                "aliases": list(first.aliases),
                "target_count": 1,
                "url_count": _discovery_url_count(phase, items),
                "keyword_count": 0,
            }
        )
    return "ok", groups


def discovery_keyword_groups(phase: str, selector: str) -> tuple[str, list[dict[str, Any]], tuple[str, ...], str]:
    phase = str(phase or "").strip().lower()
    selector = str(selector or "").strip()
    candidates = selector_candidates_for_phase(phase)
    group, targets = _resolve_target_group(phase, selector, candidates)
    if not targets:
        resolution = resolve_selector(phase, selector)
        if resolution.status != "matched":
            _, groups = discovery_target_groups(phase)
            group_candidates = tuple(str(group.get("id") or group.get("label") or "") for group in groups if group.get("id") or group.get("label"))
            return resolution.status, [], group_candidates or resolution.candidates, resolution.message
        targets = list(resolution.targets)
    keywords = _keyword_groups_for_selection(phase, group, targets)
    rows = []
    for keyword in keywords:
        rows.append(
            {
                "id": str(keyword.get("id") or keyword.get("domain") or keyword.get("label") or ""),
                "label": str(keyword.get("label") or keyword.get("id") or keyword.get("domain") or ""),
                "aliases": [str(alias) for alias in keyword.get("aliases", []) or []],
            }
        )
    return "ok" if rows else "empty", rows, (), ""


def resolve_selector(phase: str, selector: str, subselector: str | None = None) -> SelectorResolution:
    phase = str(phase or "").strip().lower()
    selector = str(selector or "").strip()
    subselector = str(subselector or "").strip()
    candidates = selector_candidates_for_phase(phase)
    if not selector:
        return SelectorResolution(phase=phase, selector=selector, status="all", targets=tuple(candidates))
    if not candidates:
        return SelectorResolution(
            phase=phase,
            selector=selector,
            status="unknown",
            candidates=(),
            message=f"phase has no selectable targets: {phase}",
        )

    selected_group: dict[str, Any] | None = None
    matched: list[SelectorCandidate] = []
    match_kind = ""
    for kind in ("target_id", "alias"):
        matched = _matching_by_kind(candidates, selector, kind)
        if matched:
            match_kind = kind
            break
    if not matched:
        selected_group, matched = _resolve_target_group(phase, selector, candidates)
        if matched:
            match_kind = "target_group"
    if not matched:
        for kind in ("country", "region", "source"):
            matched = _matching_by_kind(candidates, selector, kind)
            if matched:
                match_kind = kind
                break

    if matched:
        if subselector:
            keyword_group, keyword_targets, keyword_ids, keyword_queries, keyword_match_kind = _resolve_keyword_group(
                phase,
                subselector,
                selected_group,
                matched,
            )
            if not keyword_group:
                groups = _keyword_groups_for_selection(phase, selected_group, matched)
                status = "ambiguous" if keyword_match_kind == "ambiguous" else "unknown"
                return SelectorResolution(
                    phase=phase,
                    selector=selector,
                    status=status,
                    match_kind=match_kind,
                    targets=tuple(matched),
                    candidates=_keyword_group_labels(groups),
                    message=f"{status} subselector: {subselector}",
                    target_group_id=str((selected_group or {}).get("id") or selector),
                    target_group_label=str((selected_group or {}).get("label") or (selected_group or {}).get("id") or selector),
                    subselector=subselector,
                )
            matched = keyword_targets
            return SelectorResolution(
                phase=phase,
                selector=selector,
                status="matched",
                match_kind=match_kind,
                targets=tuple(matched),
                candidates=_candidate_labels(matched),
                target_group_id=str((selected_group or {}).get("id") or selector),
                target_group_label=str((selected_group or {}).get("label") or (selected_group or {}).get("id") or selector),
                subselector=subselector,
                keyword_group_id=str(keyword_group.get("id") or ""),
                keyword_group_label=str(keyword_group.get("label") or keyword_group.get("id") or ""),
                keyword_group_ids=keyword_ids,
                keyword_queries=keyword_queries,
            )
        return SelectorResolution(
            phase=phase,
            selector=selector,
            status="matched",
            match_kind=match_kind,
            targets=tuple(matched),
            candidates=_candidate_labels(matched),
            target_group_id=str((selected_group or {}).get("id") or (selector if match_kind in {"country", "region", "source"} else "")),
            target_group_label=str((selected_group or {}).get("label") or (selected_group or {}).get("id") or (selector if match_kind in {"country", "region", "source"} else "")),
        )

    needle = _normalize_selector(selector)
    partial: list[SelectorCandidate] = []
    for candidate in candidates:
        values = (
            candidate.target_id,
            candidate.label,
            candidate.source,
            candidate.country,
            candidate.region,
            candidate.player,
            candidate.company,
            candidate.category,
            *candidate.aliases,
        )
        if any(needle and needle in _normalize_selector(value) for value in values if value):
            partial.append(candidate)
    unique_targets = {candidate.target_id for candidate in partial}
    if len(unique_targets) == 1:
        return SelectorResolution(
            phase=phase,
            selector=selector,
            status="matched",
            match_kind="partial",
            targets=tuple(partial),
            candidates=_candidate_labels(partial),
            target_group_id=selector,
            target_group_label=selector,
        )
    if partial:
        return SelectorResolution(
            phase=phase,
            selector=selector,
            status="ambiguous",
            match_kind="partial",
            candidates=_candidate_labels(partial),
            message=f"ambiguous selector: {selector}",
        )
    return SelectorResolution(
        phase=phase,
        selector=selector,
        status="unknown",
        candidates=_candidate_labels(candidates),
        message=f"unknown selector: {selector}",
    )


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


def phase_registry() -> list[CollectionPhase]:
    phases: list[CollectionPhase] = []
    for item in _runtime().get("phases", []) or []:
        if not isinstance(item, dict):
            continue
        phases.append(
            CollectionPhase(
                id=str(item.get("id") or ""),
                label=str(item.get("label") or item.get("id") or ""),
                description=str(item.get("description") or ""),
                aliases=tuple(str(alias).strip().lower() for alias in item.get("aliases", []) or [] if str(alias).strip()),
                order=_int_value(item.get("order"), 0),
                enabled=_enabled(item),
                timeout_seconds=_int_value(item.get("timeout_seconds"), 0),
                supports_target=bool(item.get("supports_target", False)),
                telegram_visible=bool(item.get("telegram_visible", False)),
                writes_database=bool(item.get("writes_database", False)),
                sends_notification=bool(item.get("sends_notification", False)),
                full_run_included=bool(item.get("full_run_included", False)),
                execution_mode=str(item.get("execution_mode") or "python"),
            )
        )
    return sorted(phases, key=lambda phase: (phase.order, phase.id))


def phase_alias_map() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for phase in phase_registry():
        aliases[phase.id.lower()] = phase.id
        for alias in phase.aliases:
            aliases[alias] = phase.id
    aliases["help"] = "help"
    aliases["list"] = "list"
    return aliases


def resolve_phase_id(value: str) -> str | None:
    return phase_alias_map().get(str(value or "").strip().lower())


def validate_phase_registry() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    phases = _runtime().get("phases", []) or []
    if not isinstance(phases, list):
        return ["runtime.phases must be a list"], warnings

    seen_ids: set[str] = set()
    seen_aliases: dict[str, str] = {}
    seen_orders: dict[int, str] = {}
    valid_modes = {"python", "shell", "internal"}
    for index, item in enumerate(phases):
        if not isinstance(item, dict):
            errors.append(f"runtime.phases[{index}] must be a mapping")
            continue
        phase_id = str(item.get("id") or "").strip()
        where = f"runtime.phases[{phase_id or index}]"
        if not phase_id:
            errors.append(f"{where}: missing id")
        elif phase_id in seen_ids:
            errors.append(f"{where}: duplicate phase id {phase_id}")
        seen_ids.add(phase_id)

        mode = str(item.get("execution_mode") or "").strip()
        if mode not in valid_modes:
            errors.append(f"{where}: unknown execution_mode {mode!r}")

        timeout = item.get("timeout_seconds")
        if not isinstance(timeout, int) or timeout <= 0:
            errors.append(f"{where}: timeout_seconds must be a positive integer")

        order = item.get("order")
        if not isinstance(order, int):
            errors.append(f"{where}: order must be an integer")
        elif order in seen_orders:
            warnings.append(f"runtime.phases: duplicate order {order} for {seen_orders[order]} and {phase_id}")
        else:
            seen_orders[order] = phase_id

        for alias in item.get("aliases", []) or []:
            key = str(alias).strip().lower()
            if not key:
                continue
            if key in seen_aliases:
                errors.append(f"{where}: duplicate alias {key!r} also used by {seen_aliases[key]}")
            if key in seen_ids:
                errors.append(f"{where}: alias {key!r} conflicts with a phase id")
            seen_aliases[key] = phase_id

    return errors, warnings


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
    phase_errors, phase_warnings = validate_phase_registry()
    errors.extend(phase_errors)
    warnings.extend(phase_warnings)
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
            f"- Collection phases: {len(phase_registry())}",
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
_ALL_JOB_PAGES = [item for item in _sources().get("job_pages", []) if _enabled(item)]
JOBVITE_URL = next(item["url"] for item in _ALL_JOB_PAGES if item["source"] == "jobvite_pragmaticplay")
SMARTRECRUITMENT_URL = next(item["url"] for item in _ALL_JOB_PAGES if item["source"] == "smartrecruitment")
IGAMING_RECRUITMENT_URL = next(item["url"] for item in _ALL_JOB_PAGES if item["source"] == "igamingrecruitment")
IGAMINGHUNT_BAMBOOHR_URL = next(item["url"] for item in _ALL_JOB_PAGES if item["source"] == "igaminghunt_bamboohr")
JOBRAPIDO_URL = next(item["url"] for item in _ALL_JOB_PAGES if item["source"] == "jobrapido_uae")
JOBLEADS_URL = next(item["url"] for item in _ALL_JOB_PAGES if item["source"] == "jobleads")
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
JOBSPY_COUNTRY_PLANS = _filter_dict_targets("jobspy", [item for item in _sources().get("jobspy", {}).get("targets", []) if _enabled(item)])
RECRUITER_COMPANIES = list(_sources().get("recruiters", {}).get("companies", []))
NEWS_TOPICS = list(REGISTRY.get("topics", {}).get("news", []))
FOCUS_LOCATION_TERMS = list(REGISTRY.get("filters", {}).get("focus_location_terms", []))
REMOTE_GCC_LOCATION_TERMS = list(REGISTRY.get("filters", {}).get("remote_gcc_location_terms", []))
FOCUS_DOMAIN_TERMS = list(REGISTRY.get("filters", {}).get("focus_domain_terms", []))
SOURCE_METADATA = source_metadata()
SOURCE_LABELS = source_label_map()
SOURCE_COUNTRIES = source_country_map()
SOURCE_ALIASES = source_alias_map()
