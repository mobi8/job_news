#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    ALLOWED_LANGUAGE_TERMS,
    COMMERCIAL_ROLE_TERMS,
    EXCLUDED_LANGUAGE_TERMS,
    FOCUS_ROLE_TERMS,
    GENERIC_FINANCE_TERMS,
    GENERIC_PAYMENT_TERMS,
    HARD_EXCLUDE_LOCATION_PATTERNS,
    HARD_EXCLUDE_TITLE_TERMS,
    NEGATIVE_ROLE_TERMS,
    NON_COMMERCIAL_ROLE_TERMS,
    PRODUCT_ROLE_TERMS,
    RESUME_SKILL_LEXICON,
    STRONG_DOMAIN_TERMS,
)
from .collection_config import (
    FOCUS_DOMAIN_TERMS,
    FOCUS_LOCATION_TERMS,
    RECRUITER_COMPANIES,
    REMOTE_GCC_LOCATION_TERMS,
    SOURCE_LABELS,
    load_collection_registry,
)
from .models import JobPosting
from .utils import inferred_profile_text, normalize_linkedin_identifier

SCORING_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "collection" / "scoring.yaml"
COMPANY_CONTEXT_PATH = Path(__file__).resolve().parents[2] / "config" / "collection" / "company_context.yaml"
INTENT_GROUPS_PATH = Path(__file__).resolve().parents[2] / "config" / "collection" / "intent_groups.yaml"


def is_language_filtered_out(text: str) -> bool:
    lowered = text.lower()
    has_allowed = any(term in lowered for term in ALLOWED_LANGUAGE_TERMS)
    has_excluded = any(term in lowered for term in EXCLUDED_LANGUAGE_TERMS)
    if has_excluded:
        return True
    return False if has_allowed else False


def is_hard_excluded_job(title: str, company: str | None = None, location: str = "", description: str = "") -> bool:
    text_blob = " ".join([title, company or "", location, description]).lower()

    # Check title/company/description terms
    config_hard_excludes = _terms(load_scoring_config(), "negative_groups", "hard_exclude_title")
    if any(term.lower() in text_blob for term in [*HARD_EXCLUDE_TITLE_TERMS, *config_hard_excludes]):
        return True

    # Check location patterns (e.g., "Georgia, USA")
    if location:
        location_lower = location.lower()
        for pattern in HARD_EXCLUDE_LOCATION_PATTERNS:
            if re.search(pattern, location_lower):
                return True

    return False


def is_exec_tech_reject_job(title: str, company: str = "", location: str = "", description: str = "") -> bool:
    text_blob = " ".join([title, company, location, description]).lower()
    return (
        bool(re.search(r"\bcto\b", text_blob))
        or "chief technology officer" in text_blob
        or "head of engineering" in text_blob
        or "vp engineering" in text_blob
        or "vice president engineering" in text_blob
        or "director of engineering" in text_blob
    )


def unique_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    ordered = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _term_matches_text(term: str, text: str) -> bool:
    """Match terms with word boundaries for short tokens to avoid substring noise."""
    normalized_term = term.lower().strip()
    normalized_text = text.lower()
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in normalized_text
    if len(normalized_term) <= 4:
        return re.search(rf"(?<!\w){re.escape(normalized_term)}(?!\w)", normalized_text) is not None
    return normalized_term in normalized_text


@lru_cache(maxsize=1)
def load_scoring_config() -> Dict[str, Any]:
    return _load_collection_yaml(SCORING_CONFIG_PATH, "scoring")


@lru_cache(maxsize=1)
def load_company_context() -> Dict[str, Any]:
    return _load_collection_yaml(COMPANY_CONTEXT_PATH, "company_groups")


@lru_cache(maxsize=1)
def load_intent_groups() -> Dict[str, Any]:
    return _load_collection_yaml(INTENT_GROUPS_PATH, "intent_groups")


def _load_collection_yaml(path: Path, top_key: str) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError:
        return {}
    if not path.exists():
        return {}
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    section = payload.get(top_key, {})
    return section if isinstance(section, dict) else {}


@lru_cache(maxsize=1)
def active_search_location_terms() -> tuple[str, ...]:
    registry = load_collection_registry()
    scoring_config = load_scoring_config()
    terms: list[str] = []
    for location_id, config in registry.get("locations", {}).items():
        if not isinstance(config, dict) or not config.get("enabled", True):
            continue
        linkedin = config.get("linkedin") or {}
        if not linkedin or linkedin.get("enabled", True) is False:
            continue
        for value in (
            location_id,
            config.get("label"),
            config.get("country"),
            linkedin.get("location"),
            linkedin.get("source"),
        ):
            if value:
                terms.append(str(value).lower())
        for alias in linkedin.get("aliases") or []:
            terms.append(str(alias).lower())
    for aliases in (scoring_config.get("location_aliases") or {}).values():
        if isinstance(aliases, list):
            terms.extend(str(alias).lower() for alias in aliases)
    return tuple(unique_preserve_order([term for term in terms if term]))


def _terms(config: Dict[str, Any], *path: str, fallback: list[str] | None = None) -> list[str]:
    node: Any = config
    for key in path:
        if not isinstance(node, dict):
            return list(fallback or [])
        node = node.get(key)
    if isinstance(node, dict):
        terms = list(node.get("terms") or [])
        for group_id in node.get("include_groups") or []:
            terms.extend(_terms(config, path[0], str(group_id)))
        return [str(item) for item in terms] if terms else list(fallback or [])
    if isinstance(node, list):
        return [str(item) for item in node]
    return list(fallback or [])


def _score_value(config: Dict[str, Any], section: str, key: str, default: int) -> int:
    node = config.get(section, {}) if isinstance(config, dict) else {}
    if isinstance(node, dict):
        value = node.get(key, default)
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return default


def _matched_terms(terms: list[str], text: str) -> list[str]:
    return [term for term in terms if _term_matches_text(term, text)]


def _field_texts(record: Dict[str, Any]) -> Dict[str, str]:
    return {
        "title": str(record.get("title", "") or "").lower(),
        "company": str(record.get("company", "") or "").lower(),
        "description": str(record.get("description", "") or "").lower(),
        "source": str(record.get("source", "") or "").lower(),
        "location": str(record.get("location", "") or "").lower(),
    }


def _field_matches(terms: list[str], fields: Dict[str, str], field_names: list[str]) -> Dict[str, list[str]]:
    matches: Dict[str, list[str]] = {}
    for field_name in field_names:
        matched = _matched_terms(terms, fields.get(field_name, ""))
        if matched:
            matches[field_name] = matched
    return matches


def _flatten_field_matches(matches: Dict[str, list[str]]) -> list[str]:
    flattened: list[str] = []
    for terms in matches.values():
        flattened.extend(terms)
    return unique_preserve_order(flattened)


def _component(rule_id: str, score: int, terms: list[str] | None = None, field: str | None = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {"rule_id": rule_id, "score": score}
    if field:
        item["field"] = field
    if terms:
        item["terms"] = terms[:5]
    return item


def filter_records_by_sources(
    records: List[Dict[str, Any]],
    allowed_sources: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    if allowed_sources is None:
        return records
    return [record for record in records if record.get("source") in allowed_sources]


def evaluate_fit_legacy(record: Dict[str, Any], resume_text: str) -> Dict[str, Any]:
    title = record.get("title", "")
    company = record.get("company", "")
    location = record.get("location", "")
    description = record.get("description", "")
    source = record.get("source", "")

    text_blob = " ".join([title, company, location, description, source]).lower()
    intent_blob = " ".join([title, location, description, source]).lower()
    title_lower = title.lower()
    resume_blob = (resume_text or inferred_profile_text()).lower()
    is_remote = "remote" in text_blob
    is_global = "global" in text_blob
    remote_gcc_tags = [term for term in REMOTE_GCC_LOCATION_TERMS if _term_matches_text(term, text_blob)]

    location_tags = [term for term in FOCUS_LOCATION_TERMS if _term_matches_text(term, text_blob)]
    if is_remote and remote_gcc_tags:
        location_tags = unique_preserve_order(location_tags + remote_gcc_tags)
    location_ok = bool(location_tags) or (is_remote and bool(remote_gcc_tags))

    domain_tags = [term for term in FOCUS_DOMAIN_TERMS if _term_matches_text(term, text_blob)]
    strong_domain_tags = [term for term in STRONG_DOMAIN_TERMS if _term_matches_text(term, text_blob)]
    generic_payment_tags = [term for term in GENERIC_PAYMENT_TERMS if _term_matches_text(term, text_blob)]
    if source in {"jobvite_pragmaticplay", "igamingrecruitment", "igaminghunt_bamboohr"} and "igaming" not in domain_tags:
        domain_tags.append("igaming")
    if source in {"jobvite_pragmaticplay", "igamingrecruitment", "igaminghunt_bamboohr"} and "igaming" not in strong_domain_tags:
        strong_domain_tags.append("igaming")
    role_tags = [term for term in FOCUS_ROLE_TERMS if _term_matches_text(term, title_lower)]
    commercial_role_tags = [term for term in COMMERCIAL_ROLE_TERMS if _term_matches_text(term, title_lower)]
    product_role_tags = [term for term in PRODUCT_ROLE_TERMS if _term_matches_text(term, title_lower)]
    recruiter_company_tags = [term for term in RECRUITER_COMPANIES if _term_matches_text(term, company.lower())]
    resume_tags = [term for term in RESUME_SKILL_LEXICON if _term_matches_text(term, resume_blob) and _term_matches_text(term, text_blob)]
    negative_tags = [term for term in NEGATIVE_ROLE_TERMS if _term_matches_text(term, text_blob)]
    non_commercial_role_tags = [term for term in NON_COMMERCIAL_ROLE_TERMS if _term_matches_text(term, title_lower)]
    generic_finance_tags = [term for term in GENERIC_FINANCE_TERMS if _term_matches_text(term, text_blob)]
    telegram_remote_role_tags = [
        term for term in ["affiliate", "network builder", "player operations", "retention"]
        if _term_matches_text(term, title_lower)
    ]
    healthcare_exclude_terms = [
        "hospital",
        "clinic",
        "medical",
        "medicine",
        "healthcare",
        "health care",
        "medical center",
        "medical centre",
        "nurse",
        "nursing",
        "doctor",
        "physician",
        "surgeon",
        "patient",
        "dental",
        "pharma",
        "pharmaceutical",
        "wellness",
        "therapy",
        "therapist",
        "rehabilitation",
        "oncology",
        "radiology",
        "immunology",
    ]
    healthcare_tags = [term for term in healthcare_exclude_terms if _term_matches_text(term, text_blob)]

    telegram_remote_ok = (
        source.startswith("telegram_")
        and (is_remote or is_global)
        and bool(strong_domain_tags)
        and bool(commercial_role_tags or product_role_tags or telegram_remote_role_tags)
    )
    telegram_korea_ok = (
        source.startswith("telegram_")
        and bool(strong_domain_tags)
        and bool(commercial_role_tags or product_role_tags)
        and any(term in text_blob for term in ["south korea", "korean"])
    )

    if telegram_remote_ok or telegram_korea_ok:
        location_ok = True

    score = 0

    if "dubai" in text_blob:
        score += 32
    elif "abu dhabi" in text_blob or "adgm" in text_blob:
        score += 28
    elif "ras al-khaimah" in text_blob or "ras al khaimah" in text_blob:
        score += 24
    elif "united arab emirates" in text_blob or "uae" in text_blob:
        score += 22
    elif "georgia" in text_blob or "tbilisi" in text_blob or "batumi" in text_blob or "조지아" in text_blob:
        score += 20  # 조지아 점수 추가
    elif "malta" in text_blob or "valletta" in text_blob or "몰타" in text_blob:
        score += 20  # 몰타 점수 추가
    elif is_remote and remote_gcc_tags:
        score += 16
    elif telegram_remote_ok or telegram_korea_ok:
        score += 14

    score += min(len(strong_domain_tags) * 16, 48)
    if not strong_domain_tags and generic_payment_tags:
        score += min(len(generic_payment_tags) * 4, 8)
    score += min(len(role_tags) * 8, 24)
    score += min(len(commercial_role_tags) * 14, 28)
    score += min(len(product_role_tags) * 13, 26)
    score += min(len(telegram_remote_role_tags) * 8, 16)
    score += min(len(recruiter_company_tags) * 8, 16)
    score += min(len(resume_tags) * 5, 20)

    if source in {"igamingrecruitment", "igaminghunt_bamboohr"}:
        score += 6
    if "manager" in title_lower:
        score += 4
    if "lead" in title_lower or "head" in title_lower:
        score += 4

    # Domain-role pairing bonuses reflecting job search priorities:
    # - iGaming: AM / BD / PM all targeted
    # - Crypto/Payments: PM/PO primary focus
    is_igaming = any(t in text_blob for t in ["igaming", "casino", "sportsbook", "betting", "gaming platform", "live casino"])
    is_crypto_payments = any(t in text_blob for t in ["crypto", "web3", "digital asset", "stablecoin", "blockchain", "wallet", "exchange", "payment", "neobank"])
    if is_igaming and (commercial_role_tags or product_role_tags):
        score += 8
    if is_crypto_payments and product_role_tags:
        score += 10

    if not location_ok:
        score -= 35
    if not domain_tags:
        score -= 20
    if generic_payment_tags and not strong_domain_tags and not role_tags:
        score -= 12
    if generic_finance_tags and not strong_domain_tags:
        score -= 18
    if generic_finance_tags and "compliance" not in title_lower and "risk" not in title_lower:
        score -= 8
    if healthcare_tags:
        score -= 30
    if not commercial_role_tags and not product_role_tags:
        score -= 22
    if non_commercial_role_tags and not commercial_role_tags and not product_role_tags:
        score -= 24
    if negative_tags:
        score -= 24

    score = max(0, min(score, 100))
    tags = unique_preserve_order(location_tags + domain_tags + recruiter_company_tags + commercial_role_tags + product_role_tags + role_tags + resume_tags)
    role_path_ok = bool(commercial_role_tags) or bool(product_role_tags)
    has_domain_signal = bool(domain_tags) or bool(generic_payment_tags)
    qualifies = (
        location_ok
        and role_path_ok
        and not negative_tags
        and has_domain_signal
        and (
            bool(strong_domain_tags)
            or bool(product_role_tags)
            or (bool(commercial_role_tags) and bool(domain_tags))
            or (bool(generic_payment_tags) and score >= 55)
        )
    )

    return {
        "score": score,
        "qualifies": qualifies,
        "tags": tags[:8],
        "location_ok": location_ok,
        "domain_tags": domain_tags,
        "strong_domain_tags": strong_domain_tags,
        "role_tags": role_tags,
        "commercial_role_tags": commercial_role_tags,
        "product_role_tags": product_role_tags,
        "recruiter_company_tags": recruiter_company_tags,
        "resume_tags": resume_tags,
        "negative_tags": negative_tags,
        "non_commercial_role_tags": non_commercial_role_tags,
        "generic_finance_tags": generic_finance_tags,
        "healthcare_tags": healthcare_tags,
    }


def evaluate_fit(record: Dict[str, Any], resume_text: str) -> Dict[str, Any]:
    config = load_scoring_config()
    company_context = load_company_context()
    intent_groups = load_intent_groups()
    fit = evaluate_fit_legacy(record, resume_text)
    components: list[dict[str, Any]] = []

    fields = _field_texts(record)
    title = str(record.get("title", "") or "")
    company = str(record.get("company", "") or "")
    location = str(record.get("location", "") or "")
    description = str(record.get("description", "") or "")
    source = str(record.get("source", "") or "")
    text_blob = " ".join([title, company, location, description, source]).lower()
    intent_blob = " ".join([title, location, description, source]).lower()
    title_description_blob = " ".join([title, description]).lower()
    title_lower = fields["title"]

    target_domain_terms = _terms(config, "domain_groups", "target", fallback=FOCUS_DOMAIN_TERMS + GENERIC_PAYMENT_TERMS + STRONG_DOMAIN_TERMS)
    target_domain_matches = _field_matches(target_domain_terms, fields, ["title", "description", "company", "source"])
    target_domain_tags = _flatten_field_matches(target_domain_matches)
    title_description_domain_matches = _field_matches(target_domain_terms, fields, ["title", "description"])
    title_description_domain_tags = _flatten_field_matches(title_description_domain_matches)

    strong_domain_terms = _terms(config, "domain_groups", "strong", fallback=STRONG_DOMAIN_TERMS)
    strong_domain_matches = _field_matches(strong_domain_terms, fields, ["title", "description", "company", "source"])
    strong_domain_tags = _flatten_field_matches(strong_domain_matches)
    generic_payment_terms = _terms(config, "domain_groups", "generic_payment", fallback=GENERIC_PAYMENT_TERMS)
    generic_payment_matches = _field_matches(generic_payment_terms, fields, ["title", "description", "company", "source"])
    generic_payment_tags = _flatten_field_matches(generic_payment_matches)
    score = int(fit.get("score", 0) or 0)

    domain_group_matches: Dict[str, Dict[str, list[str]]] = {}
    for domain_id, domain_config in (config.get("domain_groups") or {}).items():
        if domain_id in {"strong", "generic_payment", "target", "crypto_payments"}:
            continue
        terms = _terms(config, "domain_groups", str(domain_id))
        matches = _field_matches(terms, fields, ["title", "description", "company", "source"])
        if matches:
            domain_group_matches[str(domain_id)] = matches
            value = int((domain_config or {}).get("score", 0) or 0) if isinstance(domain_config, dict) else 0
            if value:
                score += value
                components.append(
                    _component(
                        f"domain.{domain_id}",
                        value,
                        _flatten_field_matches(matches),
                        ",".join(matches.keys()),
                    )
                )

    role_terms = _terms(config, "role_groups", "technical_taxonomy")
    taxonomy_role_tags = _matched_terms(role_terms, title_lower)
    broad_terms = _terms(config, "role_groups", "broad_requires_domain")
    broad_role_tags = _matched_terms(broad_terms, title_lower)
    broad_safeguard_terms = [
        str(term) for term in (config.get("broad_role_safeguards", {}) or {}).get("require_domain_for", [])
    ]
    broad_safeguard_tags = _matched_terms(broad_safeguard_terms, title_lower)

    active_location_tags = _matched_terms(list(active_search_location_terms()), text_blob)
    location_ok = bool(fit.get("location_ok")) or bool(active_location_tags)

    if active_location_tags and not fit.get("location_ok"):
        value = int((config.get("location_bonuses", {}).get("active_search_location") or {}).get("score", 12))
        score += value
        components.append(_component("location.active_search_location", value, active_location_tags[:4], "location"))

    if taxonomy_role_tags:
        value = int((config.get("role_groups", {}).get("technical_taxonomy") or {}).get("score", 12))
        score += value
        components.append(_component("role.technical_taxonomy", value, taxonomy_role_tags[:4], "title"))

    company_group_matches: Dict[str, list[str]] = {}
    company_context_role_signal = bool(
        fit.get("product_role_tags")
        or taxonomy_role_tags
        or broad_role_tags
        or broad_safeguard_tags
    )
    for group_id, group_config in company_context.items():
        if not isinstance(group_config, dict):
            continue
        companies = [str(item) for item in group_config.get("companies") or []]
        matched = _matched_terms(companies, fields["company"])
        if matched:
            company_group_matches[str(group_id)] = matched
            value = int(group_config.get("score", 0) or 0)
            if value and company_context_role_signal:
                score += value
                components.append(_component(f"company.{group_id}", value, matched, "company"))

    intent_matches: Dict[str, list[str]] = {}
    intent_title_description_matches: Dict[str, list[str]] = {}
    for intent_id, intent_config in intent_groups.items():
        if not isinstance(intent_config, dict):
            continue
        terms = [str(item) for item in intent_config.get("terms") or []]
        matched = _matched_terms(terms, intent_blob)
        if matched:
            intent_matches[str(intent_id)] = matched
            value = int(intent_config.get("score", 0) or 0)
            if value:
                score += value
                components.append(_component(f"intent.{intent_id}", value, matched, "title_description_source"))
        title_description_matched = _matched_terms(terms, title_description_blob)
        if title_description_matched:
            intent_title_description_matches[str(intent_id)] = title_description_matched

    company_context_role_signal = bool(
        fit.get("product_role_tags")
        or
        taxonomy_role_tags
        or broad_role_tags
        or broad_safeguard_tags
        or intent_title_description_matches
    )

    infrastructure_payment_terms = [
        "payment infrastructure",
        "payments infrastructure",
        "payment operations",
        "payments operations",
        "payment orchestration",
        "payments orchestration",
        "payment network",
        "payment networks",
        "payment central",
        "payment systems",
        "payment partnerships",
        "payments partnerships",
        "acquiring",
        "merchant",
        "psp",
        "gateway",
    ]
    infrastructure_payment_tags = _matched_terms(infrastructure_payment_terms, title_description_blob)
    generic_payment_broad_noise = bool(
        (broad_role_tags or broad_safeguard_tags)
        and generic_payment_tags
        and not infrastructure_payment_tags
        and not taxonomy_role_tags
        and not any(intent_id in {"payments", "compliance", "integration", "implementation", "operations", "partnerships"} for intent_id in intent_matches)
    )

    for rule in config.get("combination_rules", []) or []:
        if not isinstance(rule, dict) or rule.get("enabled", True) is False:
            continue
        rule_id = str(rule.get("id", "combination"))
        value = int(rule.get("score", 0) or 0)
        matched = False
        if rule_id == "taxonomy_role_with_target_domain":
            matched = bool(taxonomy_role_tags and (target_domain_tags or company_group_matches))
        elif rule_id == "compliance_with_target_domain":
            title_terms = [str(term) for term in rule.get("title_terms", [])]
            matched = bool(_matched_terms(title_terms, title_lower) and (target_domain_tags or company_group_matches))
        elif rule_id == "broad_role_with_target_domain":
            matched = bool((broad_role_tags or broad_safeguard_tags) and title_description_domain_tags and not generic_payment_broad_noise)
        elif rule_id == "igaming_role_pair":
            matched = bool(domain_group_matches.get("igaming") or (company_group_matches.get("igaming") and company_context_role_signal)) and bool(
                fit.get("commercial_role_tags") or fit.get("product_role_tags") or broad_role_tags
            )
        elif rule_id == "crypto_payments_product_pair":
            matched = bool(
                any(domain_group_matches.get(group_id) for group_id in ["payments", "fintech", "crypto", "digital_assets"])
                or (
                    company_context_role_signal
                    and any(company_group_matches.get(group_id) for group_id in ["payments", "fintech", "crypto", "digital_assets"])
                )
            ) and bool(
                fit.get("product_role_tags")
            )
        elif rule_id == "intent_with_target_domain":
            matched = bool(intent_matches and (target_domain_tags or (company_group_matches and company_context_role_signal)))
        elif rule_id == "video_games_product_intent":
            matched = bool(intent_matches.get("video_game_product") and (domain_group_matches.get("video_games") or (company_group_matches.get("video_games") and company_context_role_signal)))
        if matched and value:
            score += value
            components.append(_component(f"combination.{rule_id}", value))

    if (broad_role_tags or broad_safeguard_tags) and not (target_domain_tags or company_group_matches):
        value = int((config.get("penalties", {}) or {}).get("broad_role_without_target_domain", -18))
        score += value
        components.append(_component("penalty.broad_role_without_target_domain", value, unique_preserve_order(broad_role_tags + broad_safeguard_tags), "title"))

    if (broad_role_tags or broad_safeguard_tags) and not title_description_domain_tags:
        value = int((config.get("penalties", {}) or {}).get("broad_role_without_title_description_domain", -30))
        score += value
        components.append(
            _component(
                "penalty.broad_role_without_title_description_domain",
                value,
                unique_preserve_order(broad_role_tags + broad_safeguard_tags),
                "title",
            )
        )

    if company_group_matches and not company_context_role_signal:
        value = int((config.get("penalties", {}) or {}).get("company_context_without_role_intent", -30))
        score += value
        components.append(_component("penalty.company_context_without_role_intent", value, list(company_group_matches), "company"))

    intent_domain_tags = _matched_terms(target_domain_terms, intent_blob)
    weak_company_groups = set(company_group_matches).intersection({"weak_company_context_requires_intent"})
    weak_company_domain_engineering = (
        bool(weak_company_groups)
        and not intent_domain_tags
        and any(term in title_lower for term in ["engineer", "engineering", "infrastructure"])
    )
    if weak_company_domain_engineering:
        value = int((config.get("penalties", {}) or {}).get("weak_company_domain_engineering", -22))
        score += value
        components.append(_component("penalty.weak_company_domain_engineering", value, list(weak_company_groups), "company"))

    ambiguous_game_terms = _matched_terms(["game", "games", "gaming"], title_lower)
    has_specific_game_context = bool(
        domain_group_matches.get("igaming")
        or domain_group_matches.get("video_games")
        or company_group_matches.get("igaming")
        or company_group_matches.get("video_games")
        or intent_matches.get("video_game_product")
        or intent_matches.get("live_ops")
    )
    if ambiguous_game_terms and not has_specific_game_context:
        value = int((config.get("penalties", {}) or {}).get("generic_game_role_without_intent", -20))
        score += value
        components.append(_component("penalty.generic_game_role_without_intent", value, ambiguous_game_terms, "title"))

    prequalification_role_signal = bool(
        fit.get("product_role_tags")
        or taxonomy_role_tags
        or intent_matches
        or broad_role_tags
        or broad_safeguard_tags
    )
    domain_without_role_or_intent = bool(domain_group_matches and not prequalification_role_signal)
    if domain_without_role_or_intent:
        value = int((config.get("penalties", {}) or {}).get("domain_without_role_or_intent", -16))
        score += value
        components.append(_component("penalty.domain_without_role_or_intent", value))

    weak_commercial_terms = _terms(config, "negative_groups", "weak_commercial_noise")
    weak_commercial_tags = _matched_terms(weak_commercial_terms, title_description_blob)
    if weak_commercial_tags:
        value = int((config.get("penalties", {}) or {}).get("weak_commercial_noise", -30))
        score += value
        components.append(_component("penalty.weak_commercial_noise", value, weak_commercial_tags, "title_description"))

    generic_payment_noise_terms = _terms(config, "negative_groups", "generic_payment_noise")
    generic_payment_noise_tags = _matched_terms(generic_payment_noise_terms, title_description_blob)
    if generic_payment_noise_tags and not infrastructure_payment_tags:
        value = int((config.get("penalties", {}) or {}).get("generic_payment_noise", -35))
        score += value
        components.append(_component("penalty.generic_payment_noise", value, generic_payment_noise_tags, "title_description"))

    if generic_payment_broad_noise:
        value = int((config.get("penalties", {}) or {}).get("generic_payment_noise", -35))
        score += value
        components.append(_component("penalty.generic_payment_broad_noise", value, generic_payment_tags, "title_description"))

    cash_management_without_payment_context = bool(
        _matched_terms(["cash management"], title_description_blob)
        and not _matched_terms(["payment", "payments", "payment network", "payment operations", "payments operations"], title_description_blob)
        and not any(company_group_matches.get(group_id) for group_id in ["payments", "fintech", "crypto", "digital_assets"])
    )
    if cash_management_without_payment_context:
        value = int((config.get("penalties", {}) or {}).get("generic_payment_noise", -35))
        score += value
        components.append(_component("penalty.cash_management_without_payment_context", value, ["cash management"], "title_description"))

    weak_broad_role_tags = _matched_terms(_terms(config, "negative_groups", "weak_broad_role"), title_lower)
    title_domain_tags = _flatten_field_matches(_field_matches(target_domain_terms, fields, ["title"]))
    if weak_broad_role_tags and not title_domain_tags:
        value = int((config.get("penalties", {}) or {}).get("broad_role_without_title_description_domain", -35))
        score += value
        components.append(_component("penalty.weak_broad_role_without_title_domain", value, weak_broad_role_tags, "title"))

    prequalification_domain_signal = bool(
        fit.get("domain_tags")
        or target_domain_tags
        or generic_payment_tags
        or strong_domain_tags
        or domain_group_matches
        or company_group_matches
    )
    if (taxonomy_role_tags or intent_matches) and not prequalification_domain_signal:
        value = int((config.get("penalties", {}) or {}).get("missing_domain", -20))
        score += value
        components.append(_component("penalty.missing_domain", value))

    minimum_score = int(config.get("minimum_score", 30) or 30)
    disqualifying_precision_noise = bool(
        weak_commercial_tags
        or generic_payment_broad_noise
        or cash_management_without_payment_context
        or (weak_broad_role_tags and not title_domain_tags)
        or (generic_payment_noise_tags and not infrastructure_payment_tags)
        or (company_group_matches and not company_context_role_signal and not domain_group_matches)
        or domain_without_role_or_intent
    )
    if disqualifying_precision_noise:
        score = min(score, minimum_score - 1)
        components.append(_component("penalty.precision_noise_cap", minimum_score - 1))

    score_min = _score_value(config, "caps", "score_min", 0)
    score_max = _score_value(config, "caps", "score_max", 100)
    score = max(score_min, min(score, score_max))

    role_path_ok = bool(
        fit.get("product_role_tags")
        or taxonomy_role_tags
        or intent_matches
        or ((broad_role_tags or broad_safeguard_tags) and title_description_domain_tags)
    )
    has_domain_signal = bool(
        fit.get("domain_tags")
        or target_domain_tags
        or generic_payment_tags
        or strong_domain_tags
        or domain_group_matches
        or company_group_matches
    )
    negative_tags = fit.get("negative_tags") or []
    qualifies = (
        score >= minimum_score
        and
        location_ok
        and role_path_ok
        and not negative_tags
        and not weak_company_domain_engineering
        and not (company_group_matches and not company_context_role_signal and not domain_group_matches)
        and not weak_commercial_tags
        and not (generic_payment_noise_tags and not infrastructure_payment_tags)
        and not generic_payment_broad_noise
        and not cash_management_without_payment_context
        and not (weak_broad_role_tags and not title_domain_tags)
        and has_domain_signal
        and (
            bool(fit.get("strong_domain_tags") or strong_domain_tags)
            or bool(fit.get("product_role_tags"))
            or bool(taxonomy_role_tags and (target_domain_tags or (company_group_matches and company_context_role_signal)))
            or bool(intent_matches and (target_domain_tags or (company_group_matches and company_context_role_signal) or domain_group_matches))
            or bool((broad_role_tags or broad_safeguard_tags) and title_description_domain_tags)
            or bool(broad_role_tags and (fit.get("domain_tags") or title_description_domain_tags))
            or bool(generic_payment_tags and score >= 55)
        )
    )

    merged_tags = unique_preserve_order(
        list(fit.get("tags") or [])
        + active_location_tags
        + target_domain_tags
        + taxonomy_role_tags
        + broad_role_tags
        + broad_safeguard_tags
        + list(company_group_matches.keys())
        + list(intent_matches.keys())
    )
    result = dict(fit)
    result.update(
        {
            "score": score,
            "final_score": score,
            "qualifies": qualifies,
            "tags": merged_tags[:8],
            "components": components,
            "location_ok": location_ok,
            "active_location_tags": active_location_tags,
            "target_domain_tags": target_domain_tags,
            "field_domain_matches": target_domain_matches,
            "title_description_domain_matches": title_description_domain_matches,
            "domain_group_matches": domain_group_matches,
            "company_group_matches": company_group_matches,
            "intent_matches": intent_matches,
            "intent_title_description_matches": intent_title_description_matches,
            "taxonomy_role_tags": taxonomy_role_tags,
            "broad_role_tags": broad_role_tags,
            "broad_safeguard_tags": broad_safeguard_tags,
        }
    )
    return result


def calculate_match_score(job: JobPosting, resume_text: str) -> int:
    return evaluate_fit(job.to_dict(), resume_text)["score"]


def auto_category_for_record(record: Dict[str, Any]) -> str:
    title = str(record.get("title", "") or "").lower()
    company = str(record.get("company", "") or "").lower()
    description = str(record.get("description", "") or "").lower()
    fit_tags = [str(tag).lower() for tag in record.get("fit_tags", []) if tag]
    text_blob = " ".join([title, company, description, " ".join(fit_tags)])

    if any(recruiter.lower() in company for recruiter in RECRUITER_COMPANIES):
        return "recruiter"

    if any(term in text_blob for term in ["compliance", "aml", "risk", "regulatory", "governance"]):
        return "compliance"

    if any(term in text_blob for term in ["casino", "igaming", "sportsbook", "live casino", "gaming platform", "betting"]):
        return "casino"

    if any(term in title for term in ["account manager", "business development", "sales", "partnership", "commercial"]):
        return "commercial"

    has_crypto_domain = any(
        term in text_blob
        for term in [
            "crypto",
            "web3",
            "blockchain",
            "wallet",
            "digital asset",
            "digital assets",
            "stablecoin",
            "custody",
            "exchange",
        ]
    )
    has_product_signal = any(
        term in title
        for term in [
            "product manager",
            "product owner",
            "product lead",
            "head of product",
        ]
    ) or "product" in fit_tags

    if has_crypto_domain and has_product_signal:
        return "crypto_product"

    if any(term in text_blob for term in ["payment", "payments", "wallet", "psp"]):
        return "payments"

    return ""


def annotate_records(records: List[Dict[str, Any]], resume_text: str) -> List[Dict[str, Any]]:
    annotated = []
    for record in records:
        language_blob = " ".join(
            [
                str(record.get("title", "")),
                str(record.get("description", "")),
            ]
        )
        if is_language_filtered_out(language_blob):
            continue
        if is_hard_excluded_job(
            str(record.get("title", "")),
            str(record.get("company", "")),
            str(record.get("location", "")),
            str(record.get("description", "")),
        ):
            continue
        fit = evaluate_fit(record, resume_text)
        record_copy = dict(record)
        auto_reject_exec = is_exec_tech_reject_job(
            str(record.get("title", "")),
            str(record.get("company", "")),
            str(record.get("location", "")),
            str(record.get("description", "")),
        )
        record_copy["match_score"] = fit["score"]
        record_copy["fit_tags"] = fit["tags"]
        record_copy["qualifies"] = False if auto_reject_exec else fit["qualifies"]
        record_copy["recruiter"] = bool(fit["recruiter_company_tags"])
        record_copy["recruiter_tags"] = fit["recruiter_company_tags"]
        record_copy["auto_reject_exec"] = auto_reject_exec
        record_copy["dashboard_key"] = (
            f"{record.get('source', '')}|"
            f"{normalize_linkedin_identifier(str(record.get('source', '')), str(record.get('source_job_id', '')))}|"
            f"{record.get('title', '')}|{record.get('company', '')}"
        )
        annotated.append(record_copy)
    return sorted(annotated, key=lambda item: (item["match_score"], item.get("first_seen_at") or ""), reverse=True)


def focus_records(records: List[Dict[str, Any]], resume_text: str) -> List[Dict[str, Any]]:
    return [record for record in annotate_records(records, resume_text) if record["qualifies"]]


def top_recommendations(jobs: List[JobPosting], resume_text: str, limit: int | None = None) -> List[JobPosting]:
    scored: List[JobPosting] = []
    seen_fingerprints = set()
    for job in jobs:
        fit = evaluate_fit(job.to_dict(), resume_text)
        job.match_score = fit["score"]
        if fit["qualifies"] and job.fingerprint not in seen_fingerprints:
            seen_fingerprints.add(job.fingerprint)
            scored.append(job)
    scored = sorted(scored, key=lambda item: item.match_score, reverse=True)
    return scored if limit is None else scored[:limit]


def source_label(source: str) -> str:
    if source in SOURCE_LABELS:
        return SOURCE_LABELS[source]
    mapping = {
        "jobvite_pragmaticplay": "Jobvite",
        "smartrecruitment": "SmartRecruitment",
        "igamingrecruitment": "iGaming Recruitment",
        "igaminghunt_bamboohr": "IGAMINGHUNT",
        "indeed_uae": "Indeed UAE",
        "indeed_jobspy": "Indeed UAE",
        "indeed_georgia": "Indeed Georgia",
        "indeed_malta": "Indeed Malta",
        "linkedin_public": "LinkedIn",
        "linkedin_emea": "LinkedIn EMEA",
        "linkedin_post": "LinkedIn Post",
        "linkedin_post_spot": "LinkedIn Spot",
        "linkedin_job_spot": "LinkedIn Jobs Spot",
        "linkedin_jobspy": "LinkedIn",
        "linkedin_georgia": "LinkedIn Georgia",
        "linkedin_malta": "LinkedIn Malta",
        "google_uae": "Google UAE",
        "google_georgia": "Google Georgia",
        "google_malta": "Google Malta",
        "jobrapido_uae": "Jobrapido",
        "jobleads": "JobLeads",
        "telegram_job_crypto_uae": "TG Jobs UAE",
        "telegram_cryptojobslist": "TG Crypto",
        "telegram_hr1win": "TG 1Win",
    }
    return mapping.get(source, source)
