#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

OUTPUT_DIR = Path("/Users/lewis/Desktop/agent/outputs")
DB_PATH = OUTPUT_DIR / "jobs.sqlite3"
REJECT_FEEDBACK_PATH = OUTPUT_DIR / "reject_feedback.json"
TELEGRAM_SENT_HISTORY_PATH = OUTPUT_DIR / "telegram_sent_history.json"
SCRAPE_STATE_PATH = OUTPUT_DIR / "scrape_state.json"
JOBVITE_URL = "https://jobs.jobvite.com/pragmaticplay/jobs"
SMARTRECRUITMENT_URL = "https://jobs.smartrecruitment.com/jobs?department_id=20888"
IGAMING_RECRUITMENT_URL = "https://igamingrecruitment.io/jobs/"
JOBRAPIDO_URL = "https://ae.jobrapido.com/?w=igaming&l=dubai&r=&shm=all"
JOBLEADS_URL = "https://www.jobleads.com/search/jobs?keywords=igaming&location=las+al+kaima&location_country=AE&filter_by_daysReleased=31&location_radius=50&minSalary=120000&page=2"
TELEGRAM_CHANNELS = [
    {
        "url": "https://t.me/s/job_crypto_uae",
        "source": "telegram_job_crypto_uae",
        "company": "Jobs Crypto UAE",
    },
    {
        "url": "https://t.me/s/cryptojobslist",
        "source": "telegram_cryptojobslist",
        "company": "CryptoJobsList",
    },
]
BROWSER_PROBE_PATH = Path("/Users/lewis/Desktop/agent/browser_probe.js")
INDEED_SEARCH_URLS = [
    "https://ae.indeed.com/jobs?q=korean&l=dubai&sort=date",
    "https://ae.indeed.com/jobs?q=payment+OR+crypto+OR+igaming+OR+neobanking&l=dubai&sort=date",
    "https://ae.indeed.com/jobs?q=adgm+OR+fsra+OR+vara&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=crypto+product+manager+OR+product+owner+OR+neobank+OR+digital+asset+OR+stable+coin&l=dubai&sort=date",
    "https://ae.indeed.com/jobs?q=custody+OR+digital+asset+OR+digital+assets+OR+digital+asset+custody+OR+stable+coin+OR+game+OR+gaming&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=casino+OR+gaming+resort+OR+wynn+OR+al+marjan+OR+IT+product+manager&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=crypto+casino+OR+sportsbook+OR+live+casino+OR+gaming+platform&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=dmcc+OR+dtc+OR+gaming&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=binance+OR+bybit+OR+okx+OR+coinbase+OR+kraken+OR+bitget+OR+gate.io+OR+kucoin+OR+htx+OR+crypto.com+OR+mexc&l=united+arab+emirates&sort=date",
    "https://ae.indeed.com/jobs?q=crypto+OR+custody+OR+digital+asset+OR+stable+coin+OR+game+OR+gaming+OR+payments+OR+neobanking+remote&l=saudi+arabia&sort=date",
    "https://ae.indeed.com/jobs?q=crypto+OR+custody+OR+digital+asset+OR+stable+coin+OR+game+OR+gaming+OR+payments+OR+neobanking+remote&l=qatar&sort=date",
    "https://ae.indeed.com/jobs?q=crypto+OR+custody+OR+digital+asset+OR+stable+coin+OR+game+OR+gaming+OR+payments+OR+neobanking+remote&l=bahrain&sort=date",
    # 모바일 게임 관련 검색
    "https://ae.indeed.com/jobs?q=mobile+game+OR+game+developer+OR+unity+OR+unreal+OR+dtc&l=dubai&sort=date",
    "https://ae.indeed.com/jobs?q=game+studio+OR+indie+game+OR+game+design+OR+dtc&l=united+arab+emirates&sort=date",
    # 조지아 검색 추가
    "https://ge.indeed.com/jobs?q=crypto+OR+web3+OR+blockchain+OR+igaming+OR+casino+OR+payment+OR+neobanking&l=georgia&sort=date",
    "https://ge.indeed.com/jobs?q=product+manager+OR+product+owner+OR+business+development+OR+sales&l=tbilisi&sort=date",
    "https://ge.indeed.com/jobs?q=mobile+game+OR+game+developer+OR+unity+OR+unreal+OR+dtc&l=tbilisi&sort=date",
]
LINKEDIN_SEARCH_URLS = [
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20payment%20OR%20stablecoin%20payment%20OR%20crypto%20payments%20OR%20neobanking&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=web3%20OR%20stablecoin%20OR%20crypto%20OR%20wallet%20OR%20neobanking&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=ADGM%20OR%20FSRA%20OR%20VARA&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=igaming&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20product%20manager%20OR%20product%20owner%20OR%20neobank%20OR%20digital%20asset%20OR%20stable%20coin&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=custody%20OR%20digital%20asset%20OR%20digital%20assets%20OR%20digital%20asset%20custody%20OR%20stable%20coin%20OR%20game%20OR%20gaming&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=casino%20OR%20gaming%20resort%20OR%20wynn%20OR%20al%20marjan%20OR%20IT%20product%20manager&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20casino%20OR%20sportsbook%20OR%20live%20casino%20OR%20gaming%20platform&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=DMCC%20OR%20DTC%20OR%20gaming&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=binance%20OR%20bybit%20OR%20okx%20OR%20coinbase%20OR%20kraken%20OR%20bitget%20OR%20gate.io%20OR%20kucoin%20OR%20htx%20OR%20crypto.com%20OR%20mexc&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=xsolla%20OR%20payment%20platform%20OR%20payment%20gateway&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=payments%20engineer%20OR%20payments%20developer%20OR%20crypto%20payments%20OR%20stablecoin&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=sales%20manager%20OR%20business%20development%20OR%20account%20manager&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=designer%20OR%20ux%20OR%20ui&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=wallet%20specialist%20OR%20exchange%20operations%20OR%20digital%20asset%20operations&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20OR%20custody%20OR%20digital%20asset%20OR%20stable%20coin%20OR%20game%20OR%20gaming%20OR%20payments%20OR%20neobanking&location=Saudi%20Arabia",
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20OR%20custody%20OR%20digital%20asset%20OR%20stable%20coin%20OR%20game%20OR%20gaming%20OR%20payments%20OR%20neobanking&location=Qatar",
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20OR%20custody%20OR%20digital%20asset%20OR%20stable%20coin%20OR%20game%20OR%20gaming%20OR%20payments%20OR%20neobanking&location=Bahrain",
    # 조지아 (나라) 검색 추가 - Tbilisi만 사용하여 미국 조지아 제외
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20OR%20web3%20OR%20blockchain%20OR%20igaming%20OR%20casino%20OR%20payment%20OR%20neobanking&location=Tbilisi%2C%20Georgia",
    "https://www.linkedin.com/jobs/search/?keywords=product%20manager%20OR%20product%20owner%20OR%20business%20development%20OR%20sales&location=Tbilisi%2C%20Georgia",
    "https://www.linkedin.com/jobs/search/?keywords=backend%20OR%20engineer%20OR%20developer%20OR%20software&location=Tbilisi%2C%20Georgia",
    # 몰타 검색 추가
    "https://www.linkedin.com/jobs/search/?keywords=crypto%20OR%20web3%20OR%20blockchain%20OR%20igaming%20OR%20casino%20OR%20payment%20OR%20neobanking&location=Malta",
    "https://www.linkedin.com/jobs/search/?keywords=product%20manager%20OR%20product%20owner%20OR%20business%20development%20OR%20sales&location=Valletta%2C%20Malta",
    "https://www.linkedin.com/jobs/search/?keywords=backend%20OR%20engineer%20OR%20developer%20OR%20software&location=Malta",
    # 모바일 게임 관련 검색
    "https://www.linkedin.com/jobs/search/?keywords=mobile%20game%20OR%20game%20developer%20OR%20unity%20OR%20unreal%20OR%20game%20engine%20OR%20DTC&location=Dubai%2C%20United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=game%20studio%20OR%20indie%20game%20OR%20game%20design%20OR%20game%20artist%20OR%20DTC&location=United%20Arab%20Emirates",
    "https://www.linkedin.com/jobs/search/?keywords=mobile%20game%20OR%20game%20developer%20OR%20unity%20OR%20unreal%20OR%20DTC&location=Tbilisi%2C%20Georgia",
    "https://www.linkedin.com/jobs/search/?keywords=mobile%20game%20OR%20game%20developer%20OR%20unity%20OR%20unreal%20OR%20DTC&location=Malta",
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
    "vera",
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
    "vera",
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
    "construction",
    "construction worker",
    "field worker",
    "site worker",
    "offline",
    "Surveillance",
    "food",
    "3D",
    "frontend",
    "backend",
    "DevOps",
    "Developer",
    "Room",
    "print"

]

# 위치 기반 제외 (미국 조지아 등)
HARD_EXCLUDE_LOCATION_PATTERNS = [
    r"georgia.*usa",
    r"georgia.*us\b",
    r"georgia.*united\s+states",
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
