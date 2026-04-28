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

JOBVITE_URL = "https://jobs.jobvite.com/pragmaticplay/jobs"
SMARTRECRUITMENT_URL = "https://jobs.smartrecruitment.com/jobs?department_id=20888"
IGAMING_RECRUITMENT_URL = "https://igamingrecruitment.io/jobs/"
JOBRAPIDO_URL = "https://ae.jobrapido.com/?w=igaming&l=dubai&r=&shm=all"
JOBLEADS_URL = "https://www.jobleads.com/search/jobs?keywords=igaming&location=las+al+kaima&location_country=AE&filter_by_daysReleased=31&location_radius=50&minSalary=120000&page=2"
TELEGRAM_CHANNELS = [
    # Temporarily disabled - browser_probe headless handling needs fix
    # {
    #     "url": "https://t.me/s/job_crypto_uae",
    #     "source": "telegram_job_crypto_uae",
    #     "company": "Jobs Crypto UAE",
    # },
    # {
    #     "url": "https://t.me/s/cryptojobslist",
    #     "source": "telegram_cryptojobslist",
    #     "company": "CryptoJobsList",
    # },
    # {
    #     "url": "https://t.me/s/hr1win",
    #     "source": "telegram_hr1win",
    #     "company": "1Win HR",
    # },
]
BROWSER_PROBE_PATH = Path("/Users/lewis/Desktop/agent/browser_probe.js")
INDEED_SEARCH_URLS = [
    "https://ae.indeed.com/jobs?q=korean&l=dubai&sort=date",
    "https://ae.indeed.com/jobs?q=payment+OR+crypto+OR+igaming+OR+neobanking&l=dubai&sort=date",
    "https://ae.indeed.com/jobs?q=adgm+OR+fsra+OR+vara&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=crypto+product+manager+OR+product+owner+OR+neobank+OR+digital+asset+OR+stable+coin&l=dubai&sort=date",
    "https://ae.indeed.com/jobs?q=custody+OR+digital+asset+OR+digital+assets+OR+digital+asset+custody+OR+stable+coin+OR+game+OR+gaming&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=casino+OR+gaming+resort+OR+wynn+OR+al+marjan+OR+IT+product+manager&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=binance+OR+bybit+OR+okx+OR+coinbase+OR+kraken+OR+bitget+OR+gate.io+OR+kucoin+OR+htx+OR+crypto.com+OR+mexc&l=united+arab+emirates&sort=date",
]
LINKEDIN_SEARCH_URLS = [
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20payment%20OR%20stablecoin%20payment%20OR%20crypto%20payments%20OR%20neobanking&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=web3%20OR%20stablecoin%20OR%20crypto%20OR%20wallet%20OR%20neobanking&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=ADGM%20OR%20FSRA%20OR%20VARA&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=igaming&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20product%20manager%20OR%20product%20owner%20OR%20neobank%20OR%20digital%20asset%20OR%20stable%20coin&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=custody%20OR%20digital%20asset%20OR%20digital%20assets%20OR%20digital%20asset%20custody%20OR%20stable%20coin%20OR%20game%20OR%20gaming&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=casino%20OR%20gaming%20resort%20OR%20wynn%20OR%20al%20marjan%20OR%20IT%20product%20manager&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=binance%20OR%20bybit%20OR%20okx%20OR%20coinbase%20OR%20kraken%20OR%20bitget%20OR%20gate.io%20OR%20kucoin%20OR%20htx%20OR%20crypto.com%20OR%20mexc&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=payments%20engineer%20OR%20payments%20developer%20OR%20crypto%20payments%20OR%20stablecoin&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=sales%20manager%20OR%20business%20development%20OR%20account%20manager&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=wallet%20specialist%20OR%20exchange%20operations%20OR%20digital%20asset%20operations&location=Dubai%2C%20United%20Arab%20Emirates",
    # 모바일 게임 관련 검색
    "https://www.linkedin.com/jobs/search/?keywords=mobile%20game%20OR%20game%20developer%20OR%20unity%20OR%20unreal%20OR%20game%20engine%20OR%20DTC&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=game%20studio%20OR%20indie%20game%20OR%20game%20design%20OR%20game%20artist%20OR%20DTC&location=United%20Arab%20Emirates",
]

# Search keywords are intentionally kept compact so each batch stays lighter and
# less likely to trigger rate limits or human verification prompts.
LINKEDIN_SEARCH_KEYWORDS = [
    "korean",
    "Cryptocurrency",
    "Blockchain",
    '"crypto payment"',
    '"stablecoin"',
    '"web3"',
    '"neobanking"',
    '"payments engineer"',
    '"wallet"',
    '"custody"',
    '"crypto product manager"',
    '"product owner"',
    '"business development"',
    '"account manager"',
    '"igaming"',
    '"casino"',
    '"mobile game"',
    '"DTC"',
]

INDEED_SEARCH_KEYWORDS = [
    "Cryptocurrency",
    "Blockchain",
    "crypto",
    "crypto wallet",
    "payment",
    "digital asset",
    "virtual assets",
    "stablecoin",
    "custody",
    "neobanking",
    "operations manager",
    "business development",
    "product manager",
    "sales",
    "compliance",
    "risk",
    "game",
    "gaming",
    "igaming",
    "casino",
    "wallet",
]

# Google Jobs keeps the broader, current-style probes. We convert these into google_search_term
# queries so each keyword bucket stays visible and easy to compare against LinkedIn / Indeed.
GOOGLE_SEARCH_KEYWORDS = [
    "korean",
    "ADGM OR FSRA OR VARA",
    "crypto payment OR stablecoin payment OR crypto payments OR neobanking",
    "web3 OR stablecoin OR crypto OR neobanking",
    "payments engineer OR payments developer OR crypto payments OR stablecoin OR wallet OR custody",
    "crypto product manager OR product owner OR neobank OR digital asset OR stable coin",
    "product manager OR product owner OR business development OR sales OR account manager",
    "ai engineer OR machine learning engineer OR llm engineer OR genai engineer",
    "ai product manager OR genai product manager OR machine learning product manager OR prompt engineer OR rag",
    "data scientist OR research scientist OR applied scientist OR mlops OR inference OR embeddings",
    "igaming",
    "casino OR gaming resort OR wynn OR al marjan OR IT product manager",
    "crypto casino OR sportsbook OR live casino OR gaming platform",
    "binance OR bybit OR okx OR coinbase OR kraken OR bitget OR gate.io OR kucoin OR htx OR crypto.com OR mexc",
    "crypto OR web3 OR blockchain OR payment OR neobanking",
    "mobile game OR game developer OR unity OR unreal OR game engine OR game studio OR indie game OR game design OR game artist OR DTC",
]

# Preserve the old name as a LinkedIn-oriented alias so any older callers still behave sensibly.
SEARCH_KEYWORDS = LINKEDIN_SEARCH_KEYWORDS

JOBSPY_COUNTRY_PLANS = [
    {
        "country": "UAE",
        "linkedin_source": "linkedin_public",
        "linkedin_location": "Dubai, United Arab Emirates",
        "indeed_source": "indeed_uae",
        "indeed_location": "Dubai, United Arab Emirates",
        "indeed_country": "United Arab Emirates",
        "google_source": "google_uae",
        "google_location": "Dubai, United Arab Emirates",
    },
]

RECRUITER_COMPANIES = [
    "robert walters",
    "michael page",
    "hays",
    "salt",
    "discovered mena",
    "stanley james",
    "cander group",
    "mint selection",
    "ateca consulting",
    "ap executive",
    "crypto recruit",
    "blockchain talent",
    "Hyphen Connect",
]
RECRUITER_SEARCH_URLS = [
    "https://www.linkedin.com/jobs/search/?keywords=Robert%20Walters%20crypto%20OR%20web3%20OR%20payments&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=Michael%20Page%20crypto%20OR%20payments%20OR%20product&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=Hays%20crypto%20OR%20fintech%20OR%20payments&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=Crypto%20Recruit%20web3%20OR%20crypto&location=Dubai%2C%20United%20Arab%20Emirates",
]


NEWS_RSS_FEEDS = [
    {
        "url": "https://igamingbusiness.com/feed/",
        "source": "rss_igaming_business",
        "label": "iGaming Business",
    },
    {
        "url": "https://fintechnews.ae/feed/",
        "source": "rss_fintech_uae",
        "label": "Fintech News UAE",
    },
    # 추가된 RSS 피드들
    {
        "url": "https://www.intergameonline.com/rss/igaming/news",
        "source": "rss_intergame_news",
        "label": "InterGame iGaming News",
    },
    {
        "url": "https://www.intergameonline.com/rss/igaming/cryptocurrency",
        "source": "rss_intergame_crypto",
        "label": "InterGame Cryptocurrency",
    },
    {
        "url": "https://www.intergameonline.com/rss/igaming/all",
        "source": "rss_intergame_all",
        "label": "InterGame All iGaming",
    },
    {
        "url": "https://www.intergameonline.com/rss/igaming/abbreviated",
        "source": "rss_intergame_abbrev",
        "label": "InterGame Abbreviated",
    },
    {
        "url": "https://www.finextra.com/rss/headlines.aspx",
        "source": "rss_finextra_headlines",
        "label": "FinExtra Headlines",
    },
    {
        "url": "https://www.finextra.com/rss/channel.aspx?channel=payments",
        "source": "rss_finextra_payments",
        "label": "FinExtra Payments",
    },
    {
        "url": "https://www.finextra.com/rss/channel.aspx?channel=crypto",
        "source": "rss_finextra_crypto",
        "label": "FinExtra Crypto",
    },
    {
        "url": "https://focusgn.com/feed/",
        "source": "rss_focusgn",
        "label": "FocusGN",
    },
    # 모바일/게임 산업 RSS 피드
    {
        "url": "https://venturebeat.com/games/feed/",
        "source": "rss_venturebeat_games",
        "label": "VentureBeat Games",
    },
    {
        "url": "https://www.pocketgamer.biz/feed/",
        "source": "rss_pocket_gamer",
        "label": "Pocket Gamer",
    },
    {
        "url": "https://www.gamesindustry.biz/feed",
        "source": "rss_gamesindus_news",
        "label": "GamesIndustry.biz",
    },
]

# Player Official RSS Feeds (verified working)
PLAYER_RSS_FEEDS = [
    {
        "url": "https://www.pragmaticplay.com/news/feed/",
        "player": "Pragmatic Play",
        "category": "iGaming",
        "source": "rss_player_pragmatic",
    },
    # Removed feeds that consistently fail (DNS/SSL errors):
    # - playtechcareers.com (DNS timeout)
    # - stake.com (SSL timeout)
    # - ir.draftkings.com (DNS timeout)
    # - ir.wynn.com (DNS timeout)
]

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

NEWS_TOPICS = [
    {"key": "regulation_license", "label_ko": "규제·라이센스",
     "keywords": ["regulation", "license", "compliance", "authority", "gaming commission",
                  "central bank", "VARA", "DFSA", "approved", "ban"]},
    {"key": "igaming_market",     "label_ko": "iGaming 시장",
     "keywords": ["igaming", "casino", "betting", "sports betting", "online gaming",
                  "gambling", "lottery", "esports"]},
    {"key": "game_industry",      "label_ko": "게임 산업",
     "keywords": ["game", "mobile game", "game development", "game developer", "game studio",
                  "game design", "indie game", "unity", "unreal", "game engine", "game industry"]},
    {"key": "fintech_uae",        "label_ko": "핀테크 UAE",
     "keywords": ["fintech", "UAE", "Dubai", "Abu Dhabi", "DIFC", "ADGM",
                  "neobank", "digital bank", "open banking"]},
    {"key": "crypto_web3",        "label_ko": "암호화폐·Web3",
     "keywords": ["crypto", "bitcoin", "blockchain", "web3", "NFT", "DeFi",
                  "token", "stablecoin", "CBDC"]},
    {"key": "payments",           "label_ko": "결제·송금",
     "keywords": ["payment", "wallet", "transaction", "remittance",
                  "cross-border", "instant payment", "POS"]},
    {"key": "hiring_expansion",   "label_ko": "채용·사업확장",
     "keywords": ["hire", "hiring", "jobs", "talent", "launch", "expand",
                  "partnership", "agreement", "opens"]},
    {"key": "investment_funding", "label_ko": "투자·펀딩",
     "keywords": ["investment", "funding", "raise", "capital", "venture",
                  "series A", "series B", "IPO", "valuation"]},
]
DEFAULT_RESUME_CANDIDATES = [
    Path("/Users/lewis/Desktop/agent/resume.md"),
    Path("/Users/lewis/Desktop/agent/profile_resume.md"),
    Path("/Users/lewis/Desktop/agent/my_resume.md"),
]

FOCUS_LOCATION_TERMS = [
    "dubai",
    "united arab emirates",
    "uae",
    "abu dhabi",
    "adgm",
    "ras al-khaimah",
    "ras al khaimah",
    "두바이",
    "아랍에미리트",
    "아부다비",
    "georgia",           # 조지아 추가
    "tbilisi",           # 트빌리시 (수도)
    "batumi",            # 바투미 (도시)
    "조지아",            # 한국어
    "malta",             # 몰타 추가
    "valletta",          # 수도
    "몰타",
]
REMOTE_GCC_LOCATION_TERMS = [
    "bahrain",
    "qatar",
    "saudi",
    "saudi arabia",
    "riyadh",
    "jeddah",
    "doha",
    "manama",
    "georgia",           # 조지아 추가 (원격 위치로 고려)
    "tbilisi",
    "batumi",
]

FOCUS_DOMAIN_TERMS = [
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
    "resort",
    "hospitality tech",
    "gaming technology",
    "it product",
    "product technology",
    "dmcc",
    "dtc",
    "wynn",
    "al marjan",
    "marjan",
    "payment",
    "payments",
    "adgm",
    "vara",
    "fsra",
    "igaming",
    "blockchain",
    "crypto",
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
