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

def _get_config_path() -> Path:
    """Get the config path, supporting both monolithic and split configurations.

    Behavior:
    - COLLECTION_SOURCES_CONFIG_PATH env var: use that path (file or directory)
    - config/collection/ directory exists: use that directory (split config)
    - default: config/collection_sources.yaml (monolithic config)
    """
    env_path = os.getenv("COLLECTION_SOURCES_CONFIG_PATH")
    if env_path:
        return Path(env_path)
    # Default to split directory if it exists, otherwise use monolithic file
    collection_dir = ROOT / "config" / "collection"
    if collection_dir.exists() and collection_dir.is_dir():
        return collection_dir
    return ROOT / "config" / "collection_sources.yaml"

CONFIG_PATH = _get_config_path()


@dataclass(frozen=True)
class SearchTarget:
    url: str
    target_id: str
    source: str
    country: str
    location: str
    location_id: str = ""
    role_id: str = ""
    origin: str = "manual"
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
    """Load collection registry from split YAML files or monolithic YAML file.

    If path is a directory: load all .yaml files from that directory (split mode).
    Each file can contain top-level sections: source_metadata, sources, filters,
    runtime, topics, keyword_groups. Single ownership enforced: each section-key
    appears in only one file.

    If path is a .yaml file: load that single file directly (monolithic mode).
    """
    if path.is_dir():
        # Split mode: load all YAML files from directory
        config_dir = path
    elif path.suffix == '.yaml' or path.suffix == '.yml':
        # Monolithic mode: load single file
        return _load_yaml(path)
    else:
        # Invalid path
        raise ValueError(f"CONFIG_PATH must be a directory or .yaml file, got: {path}")

    registry = {
        "version": 1,
        "source_metadata": [],
        "sources": {},
        "filters": {},
        "runtime": {},
        "topics": {},
        "keyword_groups": {},
        "locations": {},
        "role_profiles": {},
    }

    # Load all YAML files in collection/ directory (sorted for determinism)
    for yaml_file in sorted(config_dir.glob("*.yaml")):
        try:
            data = _load_yaml(yaml_file)
        except Exception as e:
            raise ValueError(f"Error loading {yaml_file.name}: {e}") from e

        if not data:
            continue

        # Merge source_metadata (single ownership per source_id)
        if "source_metadata" in data:
            metadata_list = data["source_metadata"]
            if isinstance(metadata_list, list):
                existing_ids = {item.get("id") for item in registry["source_metadata"]}
                for item in metadata_list:
                    source_id = item.get("id")
                    if source_id in existing_ids:
                        raise ValueError(
                            f"Duplicate source_id '{source_id}' found in {yaml_file.name}"
                        )
                    registry["source_metadata"].append(item)

        # Merge sources (single ownership per source name)
        if "sources" in data:
            sources_section = data["sources"]
            for source_name, source_value in sources_section.items():
                if source_name in registry["sources"]:
                    raise ValueError(
                        f"Duplicate source '{source_name}' found in {yaml_file.name}"
                    )
                registry["sources"][source_name] = source_value

        # Merge filters (single ownership per filter type)
        if "filters" in data:
            for filter_type, filter_list in data["filters"].items():
                if filter_type in registry["filters"]:
                    raise ValueError(
                        f"Duplicate filter type '{filter_type}' found in {yaml_file.name}"
                    )
                registry["filters"][filter_type] = filter_list

        # Merge keyword_groups (single ownership per source type)
        if "keyword_groups" in data:
            for kg_type, kg_list in data["keyword_groups"].items():
                if kg_type in registry["keyword_groups"]:
                    raise ValueError(
                        f"Duplicate keyword_groups type '{kg_type}' found in {yaml_file.name}"
                    )
                registry["keyword_groups"][kg_type] = kg_list

        # Merge runtime
        if "runtime" in data:
            runtime_section = data["runtime"]
            # Process phases if present
            if "phases" in runtime_section:
                if "phases" not in registry["runtime"]:
                    registry["runtime"]["phases"] = []
                phases_list = runtime_section["phases"]
                if isinstance(phases_list, list):
                    existing_phase_ids = {p.get("id") for p in registry["runtime"].get("phases", [])}
                    for phase in phases_list:
                        phase_id = phase.get("id")
                        if phase_id in existing_phase_ids:
                            raise ValueError(
                                f"Duplicate phase_id '{phase_id}' found in {yaml_file.name}"
                            )
                        registry["runtime"]["phases"].append(phase)
            # Process non-phase runtime config (always, not in else block)
            for key, value in runtime_section.items():
                if key != "phases":
                    if key in registry["runtime"] and registry["runtime"][key]:
                        raise ValueError(
                            f"Duplicate runtime.{key} found in {yaml_file.name}"
                        )
                    registry["runtime"][key] = value

        # Merge topics
        if "topics" in data:
            topics_section = data["topics"]
            for topics_key, topics_value in topics_section.items():
                if topics_key in registry["topics"]:
                    raise ValueError(
                        f"Duplicate topics section '{topics_key}' found in {yaml_file.name}"
                    )
                registry["topics"][topics_key] = topics_value

        # Merge locations (single ownership per location id)
        if "locations" in data:
            locations_section = data["locations"]
            if isinstance(locations_section, dict):
                for location_id, location_config in locations_section.items():
                    if location_id in registry["locations"]:
                        raise ValueError(
                            f"Duplicate location id '{location_id}' found in {yaml_file.name}"
                        )
                    registry["locations"][location_id] = location_config

        # Merge role_profiles (single ownership per role profile id)
        if "role_profiles" in data:
            role_profiles_section = data["role_profiles"]
            if isinstance(role_profiles_section, dict):
                for role_id, role_config in role_profiles_section.items():
                    if role_id in registry["role_profiles"]:
                        raise ValueError(
                            f"Duplicate role profile id '{role_id}' found in {yaml_file.name}"
                        )
                    registry["role_profiles"][role_id] = role_config

    # Validate loaded registry
    _validate_registry(registry)

    return registry


def _validate_registry(registry: dict[str, Any]) -> None:
    """Validate loaded registry for consistency.

    Only checks for errors that would break runtime behavior:
    - Duplicate target IDs across all sources
    - Malformed targets (missing required 'id' field)
    - Duplicate source metadata IDs
    """

    # Check for duplicate target IDs across all sources
    seen_target_ids = {}
    for source_name, source_value in registry.get("sources", {}).items():
        targets = source_value.get("targets", []) if isinstance(source_value, dict) else []
        if isinstance(targets, list):
            for target in targets:
                if isinstance(target, dict):
                    target_id = target.get("id")
                    # Targets must have an 'id' field
                    if not target_id:
                        raise ValueError(
                            f"Target in source '{source_name}' missing required 'id' field"
                        )
                    # Check for duplicates
                    if target_id in seen_target_ids:
                        raise ValueError(
                            f"Duplicate target id '{target_id}' found in "
                            f"{seen_target_ids[target_id]} and {source_name}"
                        )
                    seen_target_ids[target_id] = source_name

    # Check for duplicate source metadata IDs
    seen_metadata_ids = set()
    for metadata in registry.get("source_metadata", []):
        if isinstance(metadata, dict):
            metadata_id = metadata.get("id")
            if not metadata_id:
                raise ValueError("Source metadata entry missing required 'id' field")
            if metadata_id in seen_metadata_ids:
                raise ValueError(f"Duplicate source metadata id '{metadata_id}'")
            seen_metadata_ids.add(metadata_id)

    # Check for duplicate location IDs
    seen_location_ids = set()
    for location_id, location_config in registry.get("locations", {}).items():
        if location_id in seen_location_ids:
            raise ValueError(f"Duplicate location id '{location_id}'")
        if isinstance(location_config, dict):
            config_id = location_config.get("id")
            if config_id and config_id != location_id:
                raise ValueError(
                    f"Location key '{location_id}' does not match its id field '{config_id}'"
                )
        seen_location_ids.add(location_id)

    # Check for duplicate role profile IDs
    seen_role_ids = set()
    for role_id, role_config in registry.get("role_profiles", {}).items():
        if role_id in seen_role_ids:
            raise ValueError(f"Duplicate role profile id '{role_id}'")
        if isinstance(role_config, dict):
            config_id = role_config.get("id")
            if config_id and config_id != role_id:
                raise ValueError(
                    f"Role profile key '{role_id}' does not match its id field '{config_id}'"
                )
        seen_role_ids.add(role_id)


REGISTRY = load_collection_registry()


def generate_linkedin_matrix_targets(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate LinkedIn targets from location × role matrix.

    For each enabled location × role combination, creates a target with:
    - Preserved legacy target ID if it exists
    - Location-specific settings (source, location, geo_id, remote flag)
    - Role-specific keyword_group with merged queries
    - URL builder configuration

    Returns list of generated target objects sorted by location then role.
    """
    linkedin_source = registry.get("sources", {}).get("linkedin_jobs", {})
    matrix_config = linkedin_source.get("matrix", {})

    if not matrix_config.get("enabled"):
        return []

    locations = registry.get("locations", {})
    role_profiles = registry.get("role_profiles", {})

    generated_targets = []

    # Iterate over enabled locations from locations.yaml
    enabled_location_ids = [loc_id for loc_id, loc_cfg in locations.items() if loc_cfg.get("enabled")]
    for location_id in sorted(enabled_location_ids):
        location_config = locations.get(location_id)
        if not location_config or not location_config.get("enabled"):
            continue
        linkedin_location = location_config.get("linkedin", {})
        location_role_additions = location_config.get("role_query_additions", {})
        location_role_overrides = location_config.get("role_overrides", {})
        role_ids = _matrix_role_ids_for_location(matrix_config, location_config)

        for role_id in role_ids:
            role_config = role_profiles.get(role_id)
            if not role_config or not role_config.get("enabled"):
                continue

            # Use legacy target ID if available, otherwise generate new ID
            legacy_target_ids = location_config.get("legacy_target_ids", {})
            target_id = legacy_target_ids.get(role_id, f"linkedin_{location_id}_{role_id}")

            source = linkedin_location.get("source", "")
            location_str = linkedin_location.get("location", "")
            url_location = linkedin_location.get("url_location", location_str)
            geo_id = linkedin_location.get("geo_id")
            domain = linkedin_location.get("domain")
            remote = linkedin_location.get("remote", False)

            # Get role-specific LinkedIn settings
            linkedin_role = role_config.get("linkedin", {})
            role_override = (
                location_role_overrides.get(role_id, {})
                if isinstance(location_role_overrides, dict)
                else {}
            )
            keyword_group_id = role_override.get("keyword_group_id") or linkedin_role.get("keyword_group_id", "")
            legacy_location_queries = linkedin_role.get("location_queries", {})
            if isinstance(legacy_location_queries, dict) and legacy_location_queries.get(location_id):
                queries = legacy_location_queries.get(location_id) or []
            else:
                queries = list(linkedin_role.get("queries", []) or [])
                additions = []
                if isinstance(location_role_additions, dict):
                    additions = location_role_additions.get(role_id, []) or []
                queries.extend(str(item) for item in additions if str(item).strip())
            if role_override.get("query"):
                queries = [str(role_override.get("query"))]
            elif role_override.get("queries"):
                queries = [str(item) for item in role_override.get("queries") or [] if str(item).strip()]

            # Merge queries into a single query string
            query = " OR ".join(queries) if queries else ""

            # Build the target object
            target = {
                "id": target_id,
                "enabled": True,
                "origin": "matrix",
                "location_id": location_id,
                "role_id": role_id,
                "source": source,
                "country": location_config.get("country", ""),
                "location": location_str,
                "url_location": url_location,
                "keyword_groups": [
                    {
                        "id": keyword_group_id,
                        "query": query
                    }
                ],
                "url": {
                    "builder": "linkedin_jobs"
                }
            }

            # Add geo_id if present
            if geo_id:
                target["geo_id"] = geo_id
            if domain:
                target["domain"] = domain

            # Add remote flag if True
            if remote:
                target["remote"] = True

            generated_targets.append(target)

    # Sort by target ID for deterministic ordering
    return sorted(generated_targets, key=lambda t: t["id"])


def generate_indeed_matrix_targets(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate Indeed targets from verified source-specific location routing.

    Unlike LinkedIn, Indeed routing is not universal. A location must opt in with
    locations.<id>.indeed.enabled=true and explicit domain/location settings.
    """
    indeed_source = registry.get("sources", {}).get("indeed", {})
    matrix_config = indeed_source.get("matrix", {})
    if not matrix_config.get("enabled"):
        return []

    locations = registry.get("locations", {})
    role_profiles = registry.get("role_profiles", {})
    generated_targets: list[dict[str, Any]] = []

    configured_roles = [str(role_id) for role_id in matrix_config.get("roles", []) or []]
    enabled_location_ids = [loc_id for loc_id, loc_cfg in locations.items() if loc_cfg.get("enabled")]
    for location_id in sorted(enabled_location_ids):
        location_config = locations.get(location_id)
        if not isinstance(location_config, dict) or not location_config.get("enabled"):
            continue
        indeed_location = location_config.get("indeed") or {}
        if not isinstance(indeed_location, dict) or not indeed_location.get("enabled"):
            continue

        enabled_roles = indeed_location.get("enabled_roles") or location_config.get("indeed_enabled_roles") or []
        role_ids = [str(role_id) for role_id in enabled_roles if str(role_id) in configured_roles]
        excluded_roles = {str(role_id) for role_id in indeed_location.get("excluded_roles", []) or []}
        legacy_target_ids = indeed_location.get("legacy_target_ids") or {}

        for role_id in sorted(role_id for role_id in role_ids if role_id not in excluded_roles):
            role_config = role_profiles.get(role_id)
            if not isinstance(role_config, dict) or not role_config.get("enabled"):
                continue
            indeed_role = role_config.get("indeed") or {}
            queries = [str(item) for item in indeed_role.get("queries", []) or [] if str(item).strip()]
            if not queries:
                continue
            keyword_group_id = str(indeed_role.get("keyword_group_id") or role_id)
            target_id = str(legacy_target_ids.get(role_id) or f"indeed_{location_id}_{role_id}")
            generated_targets.append(
                {
                    "id": target_id,
                    "enabled": True,
                    "source": str(indeed_location.get("source") or f"indeed_{location_id}"),
                    "country": str(indeed_location.get("country") or location_config.get("country") or ""),
                    "location": str(indeed_location.get("location") or ""),
                    "indeed_country": str(indeed_location.get("country_indeed") or ""),
                    "domain": str(indeed_location.get("domain") or ""),
                    "locale": str(indeed_location.get("locale") or ""),
                    "routing_mode": str(indeed_location.get("routing_mode") or "domain"),
                    "sort": str(indeed_location.get("sort") or "date"),
                    "keyword_groups": [
                        {"id": keyword_group_id, "query": query}
                        for query in queries
                    ],
                    "url": {"builder": "indeed"},
                }
            )

    return sorted(
        generated_targets,
        key=lambda target: (
            str(target.get("source") or ""),
            str((target.get("keyword_groups") or [{}])[0].get("id") or ""),
            str(target.get("id") or ""),
        ),
    )


def _matrix_role_ids_for_location(matrix_config: dict[str, Any], location_config: dict[str, Any]) -> list[str]:
    configured_roles = [str(role_id) for role_id in matrix_config.get("roles", []) or []]
    enabled_roles = location_config.get("enabled_roles")
    if enabled_roles:
        selected = [str(role_id) for role_id in enabled_roles if str(role_id) in configured_roles]
    else:
        selected = configured_roles
    excluded_roles = {str(role_id) for role_id in location_config.get("excluded_roles", []) or []}
    return sorted(role_id for role_id in selected if role_id not in excluded_roles)


def _matrix_target_groups_for_linkedin(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """Build selector groups for standard matrix locations from canonical config."""
    linkedin_source = registry.get("sources", {}).get("linkedin_jobs", {})
    matrix_config = linkedin_source.get("matrix", {})
    if not matrix_config.get("enabled"):
        return []

    locations = registry.get("locations", {})
    role_profiles = registry.get("role_profiles", {})
    groups: list[dict[str, Any]] = []
    enabled_location_ids = [loc_id for loc_id, loc_cfg in locations.items() if loc_cfg.get("enabled")]
    for location_id in sorted(enabled_location_ids):
        location = locations.get(location_id)
        if not isinstance(location, dict) or not _enabled(location):
            continue
        linkedin_location = location.get("linkedin") or {}
        target_ids = []
        keyword_groups_by_id: dict[str, dict[str, Any]] = {}
        legacy_target_ids = location.get("legacy_target_ids", {})
        role_overrides = location.get("role_overrides", {})
        for role_id in _matrix_role_ids_for_location(matrix_config, location):
            role = role_profiles.get(role_id)
            if not isinstance(role, dict) or not _enabled(role):
                continue
            target_ids.append(legacy_target_ids.get(role_id, f"linkedin_{location_id}_{role_id}"))
            linkedin_role = role.get("linkedin") or {}
            role_override = role_overrides.get(role_id, {}) if isinstance(role_overrides, dict) else {}
            keyword_id = str(role_override.get("keyword_group_id") or linkedin_role.get("keyword_group_id") or role_id)
            selector_id = str(role.get("selector_group_id") or role_id)
            if selector_id not in keyword_groups_by_id:
                keyword_groups_by_id[selector_id] = {
                    "id": selector_id,
                    "label": str(role.get("label") or selector_id),
                    "aliases": [str(alias) for alias in role.get("aliases", []) or []],
                    "keyword_group_ids": [keyword_id],
                }
            elif keyword_id not in keyword_groups_by_id[selector_id]["keyword_group_ids"]:
                keyword_groups_by_id[selector_id]["keyword_group_ids"].append(keyword_id)

        aliases = [f"linkedin_{location_id}"]
        aliases.extend(str(alias) for alias in linkedin_location.get("aliases", []) or [])
        groups.append(
            {
                "id": location_id,
                "label": str(location.get("label") or location_id),
                "aliases": aliases,
                "country": str(location.get("country") or ""),
                "target_ids": target_ids,
                "keyword_groups": list(keyword_groups_by_id.values()),
            }
        )
    return groups


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
    domain: str = "www.linkedin.com",
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
    host = domain.strip() or "www.linkedin.com"
    return f"https://{host}/jobs/search/?" + urllib.parse.urlencode(params)


def build_indeed_url(
    *,
    domain: str,
    query: str,
    location: str,
    sort: str = "date",
    locale: str = "",
) -> str:
    params = {"q": query, "l": location}
    if sort:
        params["sort"] = sort
    if locale:
        params["hl"] = locale
    params = {key: value for key, value in params.items() if value}
    return f"https://{domain}/jobs?" + urllib.parse.urlencode(params)


def _build_indeed_url_from_routing(*, routing: dict[str, Any], query: str) -> str:
    explicit_url = str(routing.get("explicit_url") or "").strip()
    routing_mode = str(routing.get("routing_mode") or "domain")
    if routing_mode == "explicit_url" or explicit_url:
        if not explicit_url:
            return ""
        separator = "&" if "?" in explicit_url else "?"
        return explicit_url + separator + urllib.parse.urlencode({"q": query})
    return build_indeed_url(
        domain=str(routing.get("domain") or ""),
        query=query,
        location=str(routing.get("location") or ""),
        sort=str(routing.get("sort") or "date"),
        locale=str(routing.get("locale") or ""),
    )


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
        location_id=str(target.get("location_id") or ""),
        role_id=str(target.get("role_id") or ""),
        origin=str(target.get("origin") or "manual"),
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
        # Generate matrix targets if enabled
        generated_matrix = generate_linkedin_matrix_targets(REGISTRY)
        generated_ids = {t["id"] for t in generated_matrix}

        # Process manual targets, skipping those replaced by matrix generation
        for target in source_config.get("targets", []):
            if not _enabled(target):
                continue
            # Skip manual targets that have matrix equivalents
            if target.get("id") in generated_ids:
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
                            domain=str(target.get("domain") or "www.linkedin.com"),
                        ),
                        target=target,
                        keyword_group=group,
                    )
                )

        # Add generated matrix targets
        for matrix_target in generated_matrix:
            groups = matrix_target.get("keyword_groups", [])
            for group in groups:
                targets.append(
                    _search_target(
                        url=build_linkedin_jobs_url(
                            query=group["query"],
                            location=matrix_target.get("url_location", matrix_target.get("location")),
                            geo_id=matrix_target.get("geo_id"),
                            remote=bool(matrix_target.get("remote")),
                            domain=str(matrix_target.get("domain") or "www.linkedin.com"),
                        ),
                        target=matrix_target,
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
                    domain=str(target.get("domain") or "www.linkedin.com"),
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
    generated_matrix = generate_indeed_matrix_targets(REGISTRY)
    generated_ids = {target["id"] for target in generated_matrix}
    for target in config.get("targets", []):
        if not _enabled(target):
            continue
        if target.get("id") in generated_ids:
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
    for matrix_target in generated_matrix:
        override = _url_config(matrix_target).get("explicit_override")
        groups = _keyword_groups(matrix_target)
        if override:
            targets.append(_search_target(url=override, target=matrix_target))
            continue
        for group in groups:
            targets.append(
                _search_target(
                    url=_build_indeed_url_from_routing(routing=matrix_target, query=group["query"]),
                    target=matrix_target,
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


def _linkedin_post_locations(config: dict[str, Any]) -> list[dict[str, Any]]:
    shared_locations = REGISTRY.get("locations", {})
    locations = []
    for location in config.get("locations", []) or []:
        if not isinstance(location, dict) or not _enabled(location):
            continue
        location_ref = str(location.get("location_ref") or "")
        if not location_ref:
            locations.append(location)
            continue
        shared = shared_locations.get(location_ref)
        if not isinstance(shared, dict) or not _enabled(shared):
            continue
        posts = shared.get("linkedin_posts") or {}
        if not isinstance(posts, dict) or not _enabled(posts):
            continue
        locations.append(_linkedin_post_location_from_shared(location_ref, shared, posts))
    # Add Posts for all enabled locations from locations.yaml
    enabled_location_ids = [loc_id for loc_id, loc_cfg in shared_locations.items() if loc_cfg.get("enabled")]
    for location_id in sorted(enabled_location_ids):
        shared = shared_locations.get(location_id)
        if not isinstance(shared, dict) or not _enabled(shared):
            continue
        posts = shared.get("linkedin_posts") or {}
        if not isinstance(posts, dict) or not _enabled(posts):
            continue
        locations.append(_linkedin_post_location_from_shared(location_id, shared, posts))
    return locations


def _linkedin_post_location_from_shared(
    location_id: str,
    shared: dict[str, Any],
    posts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": posts.get("id") or f"posts_{location_id}",
        "enabled": True,
        "country": posts.get("country") or shared.get("label") or shared.get("country"),
        "store_country": posts.get("store_country") or posts.get("country") or shared.get("label") or shared.get("country"),
        "label": posts.get("label") or shared.get("label") or location_id,
        "aliases": posts.get("aliases") or [location_id],
        "query_location": posts.get("query_location"),
        "location_terms": posts.get("location_terms") or [],
    }


def build_linkedin_post_plans() -> list[dict[str, Any]]:
    config = _sources().get("linkedin_posts", {})
    if not config.get("enabled", True):
        return []
    plans: list[dict[str, Any]] = []
    for location in _linkedin_post_locations(config):
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
    lead_ids = {str(item) for item in payload.get("lead_ids", []) or []}
    if location_ids:
        plans = [plan for plan in plans if str(plan.get("location_id") or "") in location_ids]
    if role_ids:
        plans = [plan for plan in plans if str(plan.get("role_id") or plan.get("domain") or "") in role_ids]
    if lead_ids:
        plans = [plan for plan in plans if str(plan.get("lead_id") or "") in lead_ids]
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
            "location_id": target.location_id,
            "role_id": target.role_id,
            "origin": target.origin,
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
    configured = [group for group in groups if isinstance(group, dict) and _enabled(group)]
    if phase == "linkedin":
        configured.extend(_matrix_target_groups_for_linkedin(REGISTRY))
    return configured


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
        role_ids = tuple(
            dict.fromkeys(
                str(item)
                for item in [keyword_group.get("id"), keyword_group.get("domain")]
                if str(item or "").strip()
            )
        )
        return targets, role_ids, tuple(queries)
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
        posts_config = _phase_source_config("posts")
        locations = _linkedin_post_locations(posts_config)
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


def get_enabled_job_source_ids() -> list[str]:
    """Get all enabled job source IDs from YAML config (news sources excluded)."""
    news_sources = {"rss", "player"}  # News-only sources to exclude
    seen: set[str] = set()
    result: list[str] = []

    for source_key, source_config in (_sources() or {}).items():
        if not isinstance(source_config, dict):
            continue
        if source_key.startswith("telegram"):
            continue  # Telegram channels are not job sources
        if source_key in news_sources:
            continue  # Skip news-only sources
        if not _enabled(source_config):
            continue  # Skip disabled sources

        # For sources with targets (LinkedIn, Indeed, etc.), collect enabled target source IDs
        targets = source_config.get("targets", [])
        if targets:
            for target in targets:
                if isinstance(target, dict) and _enabled(target):
                    source_id = target.get("source")
                    if source_id and source_id not in seen:
                        seen.add(source_id)
                        result.append(source_id)
            if source_key == "linkedin_jobs":
                for target in generate_linkedin_matrix_targets(REGISTRY):
                    source_id = target.get("source")
                    if source_id and source_id not in seen:
                        seen.add(source_id)
                        result.append(source_id)
        else:
            # For flat sources (job_pages, recruiters), use source field or key
            source_id = source_config.get("source", source_key)
            if source_id and source_id not in seen:
                seen.add(source_id)
                result.append(source_id)

    return result


def get_collection_target_metadata() -> dict[str, dict[str, str]]:
    """Get target metadata mapping (target_id -> {source, country, location}).

    Includes both manual targets and matrix-generated targets.
    """
    metadata: dict[str, dict[str, str]] = {}

    for source_key, source_config in (_sources() or {}).items():
        if not isinstance(source_config, dict) or not _enabled(source_config):
            continue

        targets = source_config.get("targets", [])
        if not targets:
            continue

        for target in targets:
            if not isinstance(target, dict) or not _enabled(target):
                continue

            target_id = target.get("id", "")
            if not target_id:
                continue

            source_id = target.get("source", "")
            country = target.get("country", "")
            location = target.get("location", "")

            if target_id not in metadata:
                metadata[target_id] = {
                    "source": source_id,
                    "country": country,
                    "location": location,
                }

    # Also include matrix-generated targets
    matrix_targets = generate_linkedin_matrix_targets(REGISTRY)
    for target in matrix_targets:
        target_id = target.get("id", "")
        if target_id and target_id not in metadata:
            metadata[target_id] = {
                "source": target.get("source", ""),
                "country": target.get("country", ""),
                "location": target.get("location", ""),
            }

    return metadata


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
        for location in _linkedin_post_locations(config)
    }


def get_enabled_job_source_ids() -> list[str]:
    """Get all enabled job source IDs from YAML config (news sources excluded).

    Handles both dict sources (linkedin_jobs) and list sources (job_pages, recruiters).
    """
    news_sources = {"rss", "player"}  # News-only sources to exclude
    seen: set[str] = set()
    result: list[str] = []

    for source_key, source_config in (_sources() or {}).items():
        if source_key.startswith("telegram"):
            continue  # Telegram channels are not job sources
        if source_key in news_sources:
            continue  # Skip news-only sources

        # Handle list-based sources (job_pages, recruiters)
        if isinstance(source_config, list):
            for item in source_config:
                if isinstance(item, dict) and _enabled(item):
                    source_id = item.get("source", item.get("id", ""))
                    if source_id and source_id not in seen:
                        seen.add(source_id)
                        result.append(source_id)
            continue

        # Handle dict-based sources
        if not isinstance(source_config, dict):
            continue
        if not _enabled(source_config):
            continue

        # For sources with targets (LinkedIn, Indeed, etc.), collect enabled target source IDs
        targets = source_config.get("targets", [])
        if targets:
            for target in targets:
                if isinstance(target, dict) and _enabled(target):
                    source_id = target.get("source")
                    if source_id and source_id not in seen:
                        seen.add(source_id)
                        result.append(source_id)
            if source_key == "linkedin_jobs":
                for target in generate_linkedin_matrix_targets(REGISTRY):
                    source_id = target.get("source")
                    if source_id and source_id not in seen:
                        seen.add(source_id)
                        result.append(source_id)
        else:
            # For flat dict sources, use source field or key
            source_id = source_config.get("source", source_key)
            if source_id and source_id not in seen:
                seen.add(source_id)
                result.append(source_id)

    return result


def get_enabled_linkedin_source_ids() -> list[str]:
    """Get all enabled LinkedIn source IDs from YAML config."""
    linkedin_config = _sources().get("linkedin_jobs", {})
    if not isinstance(linkedin_config, dict):
        return []

    seen: set[str] = set()
    result: list[str] = []

    targets = linkedin_config.get("targets", [])
    for target in targets:
        if isinstance(target, dict) and _enabled(target):
            source_id = target.get("source")
            if source_id and source_id not in seen:
                seen.add(source_id)
                result.append(source_id)

    for target in generate_linkedin_matrix_targets(REGISTRY):
        source_id = target.get("source")
        if source_id and source_id not in seen:
            seen.add(source_id)
            result.append(source_id)

    return result


def get_source_metadata_by_id(source_id: str) -> dict[str, Any] | None:
    """Get source metadata by ID."""
    source_id = str(source_id or "").strip()
    if not source_id:
        return None
    for item in source_metadata():
        if str(item.get("id") or "") == source_id:
            return item
    return None


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
    parser.add_argument("--enabled-job-source-ids", action="store_true", help="Print enabled job source IDs (comma-separated)")
    parser.add_argument("--enabled-linkedin-source-ids", action="store_true", help="Print enabled LinkedIn source IDs (comma-separated)")
    args = parser.parse_args(argv)

    if args.check or args.check_urls:
        print(check_summary())
        errors, _ = validate_registry()
        return 1 if errors else 0

    if args.enabled_job_source_ids:
        sources = get_enabled_job_source_ids()
        print(",".join(sources))
        return 0

    if args.enabled_linkedin_source_ids:
        sources = get_enabled_linkedin_source_ids()
        print(",".join(sources))
        return 0

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
