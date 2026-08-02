#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

OUTPUT_DIR = Path("/Users/lewis/Desktop/agent/outputs")
DB_PATH = OUTPUT_DIR / "jobs.sqlite3"
REJECT_FEEDBACK_PATH = OUTPUT_DIR / "reject_feedback.json"
TELEGRAM_SENT_HISTORY_PATH = OUTPUT_DIR / "telegram_sent_history.json"
SCRAPE_STATE_PATH = OUTPUT_DIR / "scrape_state.json"


def _env_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        return int(raw_value)
    except ValueError:
        return default


# Watch / batch defaults
WATCH_INTERVAL_MINUTES_DEFAULT = 120
JOBSPY_HOURS_OLD_DEFAULT = 24
JOBSPY_LOOKBACK_OVERLAP_HOURS_DEFAULT = 3
JOBSPY_MIN_LOOKBACK_HOURS_DEFAULT = 12
JOBSPY_MAX_LOOKBACK_HOURS_DEFAULT = 48
BROWSER_LOOKBACK_HOURS_DEFAULT = 6

# Runtime-tunable values with environment overrides
JOBSPY_HOURS_OLD = _env_int("JOBSPY_HOURS_OLD", JOBSPY_HOURS_OLD_DEFAULT)
JOBSPY_LOOKBACK_OVERLAP_HOURS = _env_int("JOBSPY_LOOKBACK_OVERLAP_HOURS", JOBSPY_LOOKBACK_OVERLAP_HOURS_DEFAULT)
JOBSPY_MIN_LOOKBACK_HOURS = _env_int("JOBSPY_MIN_LOOKBACK_HOURS", JOBSPY_MIN_LOOKBACK_HOURS_DEFAULT)
JOBSPY_MAX_LOOKBACK_HOURS = _env_int("JOBSPY_MAX_LOOKBACK_HOURS", JOBSPY_MAX_LOOKBACK_HOURS_DEFAULT)
BROWSER_LOOKBACK_HOURS = _env_int("BROWSER_LOOKBACK_HOURS", BROWSER_LOOKBACK_HOURS_DEFAULT)

BROWSER_PROBE_PATH = Path("/Users/lewis/Desktop/agent/browser_probe.js")
GLASSDOOR_BROWSERLESS_PROBE_PATH = Path("/Users/lewis/Desktop/agent/browserless_glassdoor_probe.js")
LINKEDIN_POSTS_PROFILE_DIR = OUTPUT_DIR / "linkedin-post-profile"
LINKEDIN_POSTS_PROBE_PATH = Path("/Users/lewis/Desktop/agent/linkedin_posts_probe.js")

# iGaming & Crypto Casino Players
CRYPTO_CASINO_PLAYERS = [
    "Stake",
    "Rollbit",
    "BC.Game",
    "Bitcasino",
    "Ignition",
    "FortuneJack",
    "Cloudbet",
    "Mega Dice",
    "Shuffle",
    "Wolf.bet",
    "Fairspin",
    "Crypto Thrills",
    "Slotimo",
    "Bizzo",
]

IGAMING_PLAYERS = [
    "Playtech",
    "Pragmatic Play",
    "DraftKings",
    "FanDuel",
    "Codere",
    "Sportradar",
    "Betking",
    "Wynn",
    "Caesars",
    "MGM",
    "Penn Entertainment",
    "Kambi",
    "Gamesys",
    "Kambi",
    "Inspired",
    "Kambi",
    "Betsson",
    "Kindred",
    "GVC",
    "Entain",
]

DEFAULT_RESUME_CANDIDATES = [
    Path("/Users/lewis/Desktop/agent/resume.md"),
    Path("/Users/lewis/Desktop/agent/profile_resume.md"),
    Path("/Users/lewis/Desktop/agent/my_resume.md"),
]

STRONG_DOMAIN_TERMS = [
    "web3",
    "stablecoin",
    "stable coin",
    "digital asset",
    "digital assets",
    "crypto payment",
    "crypto payments",
    "neobank",
    "neobanking",
    "digital assets",
    "custody",
    "exchange",
    "wallet",
    "psp",
    "mto",
    "casino",
    "crypto casino",
    "live casino",
    "sportsbook",
    "casino tech",
    "gaming platform",
    "betting",
    "sports betting",
    "gaming",
    "gaming resort",
    "game",
    "hospitality tech",
    "gaming technology",
    "it product",
    "dmcc",
    "dtc",
    "wynn",
    "al marjan",
    "blockchain",
    "crypto",
    "adgm",
    "vara",
    "fsra",
    "igaming",
    "tokenization",
    "virtual assets",
    "cex",
    "binance",
    "bybit",
    "okx",
    "coinbase",
    "kraken",
    "bitget",
    "gate.io",
    "kucoin",
    "htx",
    "crypto.com",
    "mexc",
    "xsolla",
    "ai",
    "artificial intelligence",
    "genai",
    "generative ai",
    "machine learning",
    "mlops",
    "llm",
    "llmops",
    "prompt engineering",
    "prompt engineer",
    "rag",
    "retrieval augmented generation",
    "fine tuning",
    "model training",
    "inference",
    "embeddings",
    "data scientist",
    "research scientist",
    "applied scientist",
    "computer vision",
    "natural language processing",
]

GENERIC_PAYMENT_TERMS = [
    "payment",
    "payments",
]

FOCUS_ROLE_TERMS = [
    "product",
    "compliance",
    "risk",
    "fraud",
    "payments",
    "payment",
    "backend",
    "engineering",
    "engineer",
    "integration",
    "technical",
    "ops",
    "operations",
    "ai",
    "machine learning",
    "ml",
    "llm",
    "genai",
    "prompt",
]

COMMERCIAL_ROLE_TERMS = [
    "account manager",
    "key account",
    "business development",
    "business development specialist",
    "bd manager",
    "sales manager",
    "head of sales",
    "director of sales",
    "country manager",
    "partnership",
    "partner manager",
    "account executive",
    "affiliate",
    "affiliate manager",
    "network builder",
    "growth manager",
    "commercial manager",
    "listings manager",
    "engineer",
    "architect",
    "designer",
    "manager",
    "director",
    "lead",
    "head of",
    "specialist",
]

PRODUCT_ROLE_TERMS = [
    "product manager",
    "product owner",
    "head of product",
    "product lead",
    "payments product",
    "growth product",
    "ai product manager",
    "genai product manager",
    "machine learning product manager",
]

NEGATIVE_ROLE_TERMS = [
    "game presenter",
    "customer service",
    "teacher",
    "appearance manager",
]

EXECUTIVE_TECH_REJECT_TERMS = [
    "chief technology officer",
    "cto",
    "head of engineering",
    "vp engineering",
    "vice president engineering",
    "director of engineering",
]

HARD_EXCLUDE_TITLE_TERMS = [
    "nordic",
    "nordics",
    "presenter",
    "프레젠터",
    "game presenter",
    "live casino presenter",
    "dealer",
    "make-up",
    "makeup",
    "hairstylist",
    "beauty",
    "guest relations",
    "guest experience",
    "villa services",
    "kids club",
    "restaurant",
    "cleaning",
    "cleaning staff",
    "handyman",
    "front desk",
    "appearance",
    "entertainment",
    "streamer relations",
    "stage manager",
    "ticketing",
    "cage",
    "floor supervisor",
    "studio interior",
    "workforce manager",
    "security agent",
    "downtime specialist",
    "maintenance",
    "hospital",
    "medical",
    "medical center",
    "medical centre",
    "clinic",
    "patient",
    "nurse",
    "doctor",
    "physician",
    "surgeon",
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
    "construction",
    "construction worker",
    "field worker",
    "site worker",
    "offline",
    "Surveillance",
    "food",
    "3d",
    "supply chain",
    "supply chain manager",
    "supply chain specialist",
    "supply chain coordinator",
    "logistics",
    "procurement",
    "purchasing",
    "room",
    "print"

]

# 위치 기반 제외 (미국 조지아 등)
HARD_EXCLUDE_LOCATION_PATTERNS = [
    r"georgia.*usa",
    r"georgia.*us\b",
    r"georgia.*united\s+states",
    r"\bohio\b",
    r"atlanta",
    r"savannah.*georgia",
]

NON_COMMERCIAL_ROLE_TERMS = [
    "compliance",
    "legal",
    "counsel",
    "integration",
    "operations",
    "operator",
    "data scientist",
    "administrator",
    "finance",
    "accountant",
    "accounts payable",
    "accounts receivable",
    "training",
    "trainer",
    "supervisor",
    "presenter",
    "dealer",
    "technician",
    "qa",
    "quality",
    "seo",
    "media buyer",
    "content",
    "fraud",
    "risk",
]

GENERIC_FINANCE_TERMS = [
    "accountant",
    "accounts payable",
    "accounts receivable",
    "auditor",
    "bookkeeper",
    "clerk",
    "voucher",
    "invoice",
]

RESUME_SKILL_LEXICON = [
    "web3",
    "stablecoin",
    "crypto",
    "payment",
    "payments",
    "blockchain",
    "solana",
    "adgm",
    "vara",
    "fsra",
    "igaming",
    "kyc",
    "aml",
    "compliance",
    "backend",
    "python",
    "postgresql",
    "product",
    "integration",
    "wallet",
    "custody",
    "digital assets",
    "operations",
    "ai",
    "machine learning",
    "llm",
    "genai",
    "mlops",
    "prompt engineering",
    "rag",
    "data science",
    "data scientist",
    "applied scientist",
    "research scientist",
]

ALLOWED_LANGUAGE_TERMS = [
    "korean",
    "korea",
    "한국어",
    "한국",
]

EXCLUDED_LANGUAGE_TERMS = [
    "arabic",
    "chinese",
    "russian",
    "turkish",
    "thai",
    "japanese",
    "vietnamese",
    "indonesian",
    "spanish",
    "french",
    "german",
    "italian",
    "portuguese",
    "dutch",
    "hindi",
    "urdu",
    "tagalog",
    "mandarin",
]

# External collection source settings are loaded from config/collection_sources.yaml.
# Keep the names below as compatibility constants for existing consumers.
from .collection_config import (  # noqa: E402,F401
    DRJOBS_SEARCH_URL_METADATA,
    DRJOBS_SEARCH_URLS,
    FOCUS_DOMAIN_TERMS,
    FOCUS_LOCATION_TERMS,
    GLASSDOOR_BROWSERLESS_KEYWORDS,
    GLASSDOOR_BROWSERLESS_SEARCH_URLS,
    GLASSDOOR_SEARCH_KEYWORDS,
    GLASSDOOR_SEARCH_URL_METADATA,
    GOOGLE_SEARCH_KEYWORDS,
    IGAMINGHUNT_BAMBOOHR_URL,
    IGAMING_RECRUITMENT_URL,
    INDEED_SEARCH_KEYWORDS,
    INDEED_SEARCH_URL_METADATA,
    INDEED_SEARCH_URLS,
    JOBLEADS_URL,
    JOBRAPIDO_URL,
    JOBSPY_COUNTRY_PLANS,
    JOBVITE_URL,
    LINKEDIN_POST_FILTERS,
    LINKEDIN_POST_LOCATION_TERMS_BY_COUNTRY,
    LINKEDIN_POST_SEARCH_PLANS,
    LINKEDIN_SEARCH_KEYWORDS,
    LINKEDIN_SEARCH_URL_METADATA,
    LINKEDIN_SEARCH_URLS,
    NEWS_RSS_FEEDS,
    NEWS_TOPICS,
    PLAYER_RSS_FEEDS,
    RECRUITER_COMPANIES,
    RECRUITER_SEARCH_URLS,
    REMOTE_GCC_LOCATION_TERMS,
    SEARCH_KEYWORDS,
    SMARTRECRUITMENT_URL,
    SOURCE_ALIASES,
    SOURCE_COUNTRIES,
    SOURCE_LABELS,
    SOURCE_METADATA,
    TELEGRAM_CHANNELS,
)
