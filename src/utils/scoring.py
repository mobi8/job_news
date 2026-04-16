#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .config import (
    ALLOWED_LANGUAGE_TERMS,
    COMMERCIAL_ROLE_TERMS,
    EXCLUDED_LANGUAGE_TERMS,
    FOCUS_DOMAIN_TERMS,
    FOCUS_LOCATION_TERMS,
    FOCUS_ROLE_TERMS,
    GENERIC_FINANCE_TERMS,
    GENERIC_PAYMENT_TERMS,
    HARD_EXCLUDE_LOCATION_PATTERNS,
    HARD_EXCLUDE_TITLE_TERMS,
    NEGATIVE_ROLE_TERMS,
    NON_COMMERCIAL_ROLE_TERMS,
    PRODUCT_ROLE_TERMS,
    RECRUITER_COMPANIES,
    REMOTE_GCC_LOCATION_TERMS,
    RESUME_SKILL_LEXICON,
    STRONG_DOMAIN_TERMS,
)
from .models import JobPosting
from .utils import inferred_profile_text, normalize_linkedin_identifier


def is_language_filtered_out(text: str) -> bool:
    lowered = text.lower()
    has_allowed = any(term in lowered for term in ALLOWED_LANGUAGE_TERMS)
    has_excluded = any(term in lowered for term in EXCLUDED_LANGUAGE_TERMS)
    if has_excluded:
        return True
    return False if has_allowed else False


def is_hard_excluded_job(title: str, company: str = "", location: str = "", description: str = "") -> bool:
    text_blob = " ".join([title, company, location, description]).lower()

    # Check title/company/description terms
    if any(term in text_blob for term in HARD_EXCLUDE_TITLE_TERMS):
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


def auto_category_for_record(record: Dict[str, Any]) -> str:
    text_blob = " ".join(
        [
            str(record.get("title", "")),
            str(record.get("company", "")),
            str(record.get("location", "")),
            str(record.get("description", "")),
            " ".join(record.get("fit_tags", [])) if isinstance(record.get("fit_tags"), list) else "",
        ]
    ).lower()

    # =========================================================
    # Job Category Classification
    # =========================================================


    # ---------------------------------------------------------
    # Crypto / Web3
    # ---------------------------------------------------------
    # - Crypto exchange
    # - Web3 infra
    # - Wallet / custody
    # - DeFi / trading
    # - Stablecoin / onchain infra
    # ---------------------------------------------------------
    if any(term in text_blob for term in [

        # Core crypto keywords
        "crypto", "web3", "blockchain", "digital asset", "stablecoin",
        "custody", "wallet", "defi", "token", "tokenization",
        "smart contract", "on-chain", "off-chain",
        "dex", "cex", "exchange", "crypto exchange",
        "layer 1", "layer 2", "l2", "l3",
        "evm", "solana", "ethereum", "bitcoin",
        "custodial", "non-custodial",

        # Wallet / custody infra
        "crypto wallet", "digital wallet", "custodian",
        "mpc", "multi party computation", "multisig",
        "private key", "key management",
        "fireblocks", "bitgo", "coinbase custody",

        # Trading / exchange infra
        "trading", "spot trading", "margin trading",
        "derivatives", "perpetual", "futures",
        "order book", "market maker",
        "matching engine", "trading platform",

        # DeFi / onchain infra
        "yield", "staking", "restaking",
        "liquidity pool", "amm",
        "bridge", "cross-chain", "cross chain",
        "oracle", "vrf",

        # Token standards
        "erc20", "erc721", "erc1155",
        "nft", "nfts",

        # Crypto payments
        "on-ramp", "on ramp",
        "off-ramp", "off ramp",
        "crypto payment", "crypto payments",
        "fiat to crypto", "crypto to fiat",

        # Stablecoins
        "usdt", "usdc", "dai",

        # Node / infra
        "rpc", "node", "validator",
        "rollup", "zk"
    ]):
        return "crypto_product"



    # ---------------------------------------------------------
    # Payments / Fintech
    # ---------------------------------------------------------
    # - Payment infra
    # - PSP / gateway
    # - Cross-border payments
    # - Card issuing / acquiring
    # ---------------------------------------------------------
    if any(term in text_blob for term in [

        # Core payments
        "payment", "payments", "psp", "settlement", "fintech",
        "remittance", "payout", "payouts",
        "payin", "pay-in", "pay-out",

        # Merchant / gateway
        "merchant", "gateway", "payment gateway",
        "payment processing", "payment infrastructure",

        # Treasury / settlement
        "cross-border", "treasury", "reconciliation",
        "acquirer", "issuer",

        # Payment infra
        "payment processor", "payment provider",
        "payment orchestration", "payment routing",
        "payment rails", "transaction processing",

        # Card payments
        "credit card", "debit card",
        "visa", "mastercard", "amex",
        "issuing", "acquiring",

        # Banking rails
        "bank transfer", "sepa", "swift", "iban",

        # Fintech infra
        "embedded finance", "embedded payments",
        "banking as a service", "baas",
        "open banking",

        # Merchant flow
        "merchant acquiring", "merchant onboarding",
        "checkout", "subscription billing",

        # Risk / disputes
        "chargeback", "dispute",

        # Cross-border FX
        "fx", "foreign exchange",
        "currency conversion",
        "multi-currency", "multi currency"
    ]):
        return "payments"



    # ---------------------------------------------------------
    # Casino / iGaming
    # ---------------------------------------------------------
    # - Casino operators
    # - Game providers
    # - iGaming platforms
    # ---------------------------------------------------------
    if any(term in text_blob for term in [

        # Core iGaming
        "casino", "sportsbook", "live casino",
        "betting", "igaming", "gambling",

        # Game providers
        "game provider",
        "slot", "roulette", "blackjack",
        "poker", "lottery", "rgs",

        # Casino platforms
        "white label casino",
        "casino platform",

        # Game types
        "sports betting",
        "live dealer",
        "table games",
        "virtual sports",
        "jackpot",

        # Player systems
        "player management",
        "pam",
        "player account",

        # Aggregators / studios
        "game aggregation",
        "casino aggregator",
        "game studio",

        # Casino operations roles
        "affiliate manager",
        "vip manager",

        # Platform / backend
        "turnkey",
        "casino solution",
        "gaming solution",
        "casino backoffice",
        "gaming wallet"
    ]):
        return "casino"



    # ---------------------------------------------------------
    # Commercial / Business / BD
    # ---------------------------------------------------------
    # - Sales
    # - Partnerships
    # - Business Development
    # ---------------------------------------------------------
    if any(term in text_blob for term in [

        # Account / BD roles
        "account manager",
        "business development",
        "business development manager",

        # Sales roles
        "sales manager",

        # Regional roles
        "country manager",

        # Commercial roles
        "commercial",
        "partnership manager",

        # Client roles
        "client manager",
        "customer success",
        "relationship manager"
    ]):
        return "commercial"



    # ---------------------------------------------------------
    # Compliance / Regulatory
    # ---------------------------------------------------------
    # - Crypto compliance
    # - Gaming compliance
    # - Regulatory roles
    # ---------------------------------------------------------
    if any(term in text_blob for term in [

        # UAE regulators
        "adgm", "vara", "fsra", "gcgra", "sca", "dfsa",

        # Compliance keywords
        "compliance", "regulatory",
        "licensing", "regulated",
        "regulation",

        # Risk / AML
        "kyc", "aml", "kyb",
        "risk management",

        # Governance
        "governance",
        "audit"
    ]):
        return "compliance"


    # ---------------------------------------------------------
    # Recruiter / Agency
    # ---------------------------------------------------------
    if any(term in text_blob for term in RECRUITER_COMPANIES):
        return "recruiter"


    # ---------------------------------------------------------
    # Default
    # ---------------------------------------------------------
    return ""


def unique_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    ordered = []
    for item in items:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def filter_records_by_sources(
    records: List[Dict[str, Any]],
    allowed_sources: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    if allowed_sources is None:
        return records
    return [record for record in records if record.get("source") in allowed_sources]


def evaluate_fit(record: Dict[str, Any], resume_text: str) -> Dict[str, Any]:
    title = record.get("title", "")
    company = record.get("company", "")
    location = record.get("location", "")
    description = record.get("description", "")
    source = record.get("source", "")

    text_blob = " ".join([title, company, location, description, source]).lower()
    title_lower = title.lower()
    resume_blob = (resume_text or inferred_profile_text()).lower()
    is_remote = "remote" in text_blob
    is_global = "global" in text_blob
    remote_gcc_tags = [term for term in REMOTE_GCC_LOCATION_TERMS if term in text_blob]

    location_tags = [term for term in FOCUS_LOCATION_TERMS if term in text_blob]
    if is_remote and remote_gcc_tags:
        location_tags = unique_preserve_order(location_tags + remote_gcc_tags)
    location_ok = bool(location_tags) or (is_remote and bool(remote_gcc_tags))

    domain_tags = [term for term in FOCUS_DOMAIN_TERMS if term in text_blob]
    strong_domain_tags = [term for term in STRONG_DOMAIN_TERMS if term in text_blob]
    generic_payment_tags = [term for term in GENERIC_PAYMENT_TERMS if term in text_blob]
    if source in {"jobvite_pragmaticplay", "igamingrecruitment"} and "igaming" not in domain_tags:
        domain_tags.append("igaming")
    if source in {"jobvite_pragmaticplay", "igamingrecruitment"} and "igaming" not in strong_domain_tags:
        strong_domain_tags.append("igaming")
    role_tags = [term for term in FOCUS_ROLE_TERMS if term in title_lower]
    commercial_role_tags = [term for term in COMMERCIAL_ROLE_TERMS if term in title_lower]
    product_role_tags = [term for term in PRODUCT_ROLE_TERMS if term in title_lower]
    recruiter_company_tags = [term for term in RECRUITER_COMPANIES if term in company.lower()]
    resume_tags = [term for term in RESUME_SKILL_LEXICON if term in resume_blob and term in text_blob]
    negative_tags = [term for term in NEGATIVE_ROLE_TERMS if term in text_blob]
    non_commercial_role_tags = [term for term in NON_COMMERCIAL_ROLE_TERMS if term in title_lower]
    generic_finance_tags = [term for term in GENERIC_FINANCE_TERMS if term in text_blob]
    telegram_remote_role_tags = [
        term for term in ["affiliate", "network builder", "player operations", "retention"]
        if term in title_lower
    ]

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

    if source == "igamingrecruitment":
        score += 6
    if "manager" in title_lower:
        score += 4
    if "lead" in title_lower or "head" in title_lower:
        score += 4

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
    }


def calculate_match_score(job: JobPosting, resume_text: str) -> int:
    return evaluate_fit(job.to_dict(), resume_text)["score"]


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
        record_copy["auto_category"] = auto_category_for_record(record_copy)
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
    mapping = {
        "jobvite_pragmaticplay": "Jobvite",
        "smartrecruitment": "SmartRecruitment",
        "igamingrecruitment": "iGaming Recruitment",
        "indeed_uae": "Indeed UAE",
        "indeed_georgia": "Indeed Georgia",
        "linkedin_public": "LinkedIn",
        "linkedin_georgia": "LinkedIn Georgia",
        "linkedin_malta": "LinkedIn Malta",
        "jobrapido_uae": "Jobrapido",
        "jobleads": "JobLeads",
        "telegram_job_crypto_uae": "TG Jobs UAE",
        "telegram_cryptojobslist": "TG Crypto",
    }
    return mapping.get(source, source)
