#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/lewis/Desktop/agent")
LOG_DIR = ROOT / "logs"


@dataclass
class SpotRequest:
    mode: str
    location: str
    keywords: str
    limit: str


PREFIX_TO_MODE = {
    "spot": "set",
    "스팟": "set",
    "링크드인스팟": "set",
    "linkedin spot": "set",
    "postspot": "posts",
    "posts": "posts",
    "포스트스팟": "posts",
    "jobspot": "jobs",
    "jobs": "jobs",
    "잡스팟": "jobs",
    "잡보드스팟": "jobs",
}

LOCATION_ALIASES = {
    "덴마크": "Denmark",
    "코펜하겐": "Copenhagen, Denmark",
    "포르투갈": "Portugal",
    "리스본": "Lisbon, Portugal",
    "암스테르담": "Amsterdam",
    "네덜란드": "Netherlands",
}

DEFAULT_KEYWORDS = "crypto,web3,payments,igaming,product"
DOMAIN_WORDS = [
    "crypto",
    "web3",
    "payment",
    "payments",
    "igaming",
    "gaming",
    "product",
    "fintech",
    "blockchain",
    "wallet",
    "backlog",
    "casino",
    "stablecoin",
]


def parse_spot_command(text: str) -> SpotRequest | None:
    if not text:
        return None
    normalized = re.sub(r"\s+", " ", text.strip())
    prefix = ""
    remainder = ""
    mode = None

    for candidate in sorted(PREFIX_TO_MODE, key=len, reverse=True):
        pattern = rf"^{re.escape(candidate)}(?:\s*[\.:：]\s*|\s+)(.+)?$"
        match = re.match(pattern, normalized, flags=re.IGNORECASE)
        if match:
            prefix = candidate
            remainder = (match.group(1) or "").strip()
            mode = PREFIX_TO_MODE[prefix]
            break

    if not mode:
        return None

    parts = [part.strip() for part in re.split(r"\s*[|/]\s*", remainder) if part.strip()]
    if len(parts) >= 2:
        location = parts[0]
        keywords = parts[1] or DEFAULT_KEYWORDS
        limit = parts[2] if len(parts) > 2 and parts[2].isdigit() else "8"
    else:
        location, keywords, limit = _parse_space_form(remainder)

    location = LOCATION_ALIASES.get(location.strip(), location.strip())
    if not location:
        return SpotRequest(mode=mode, location="", keywords=keywords, limit=limit)
    return SpotRequest(mode=mode, location=location, keywords=keywords, limit=limit)


def _parse_space_form(remainder: str) -> tuple[str, str, str]:
    text = remainder.strip()
    if not text:
        return "", DEFAULT_KEYWORDS, "8"

    limit = "8"
    limit_match = re.search(r"\s+(\d{1,3})\s*$", text)
    if limit_match:
        limit = limit_match.group(1)
        text = text[:limit_match.start()].strip()

    lowered = text.lower()
    keyword_start = -1
    for word in DOMAIN_WORDS:
        match = re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", lowered)
        if match and (keyword_start == -1 or match.start() < keyword_start):
            keyword_start = match.start()

    if keyword_start >= 0:
        location = text[:keyword_start].strip(" ,")
        keywords = text[keyword_start:].strip(" ,") or DEFAULT_KEYWORDS
    else:
        location = text.strip(" ,")
        keywords = DEFAULT_KEYWORDS

    return location, keywords, limit


def spot_usage() -> str:
    return "\n".join(
        [
            "사용법:",
            "스팟 덴마크 igaming, crypto payment 50",
            "잡스팟 덴마크 crypto web3 20",
            "spot. Copenhagen, Denmark | crypto,web3,payments | 8",
            "jobs. Copenhagen, Denmark | crypto,web3,payments | 8",
            "posts. Copenhagen, Denmark | crypto,web3,payments | 8",
        ]
    )


def start_spot_search(request: SpotRequest) -> str:
    if not request.location:
        return spot_usage()

    script = {
        "set": "run_linkedin_spot_set.sh",
        "posts": "run_linkedin_posts.sh",
        "jobs": "run_linkedin_jobs_spot.sh",
    }[request.mode]

    if request.mode == "posts":
        args = [str(ROOT / script), "spot", request.location, request.keywords, request.limit]
        label = "LinkedIn posts"
    elif request.mode == "jobs":
        args = [str(ROOT / script), request.location, request.keywords, request.limit]
        label = "LinkedIn jobs board"
    else:
        args = [str(ROOT / script), request.location, request.keywords, request.limit]
        label = "LinkedIn posts + jobs board"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"linkedin-spot-{request.mode}-{stamp}.log"
    log_file = log_path.open("a", encoding="utf-8")
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT / "src"))
    env["PATH"] = ":".join(
        [
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
            env.get("PATH", ""),
        ]
    )

    subprocess.Popen(
        args,
        cwd=str(ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )

    return "\n".join(
        [
            f"🔎 {label} 스팟 검색 시작",
            f"위치: {request.location}",
            f"키워드: {request.keywords}",
            f"한도: {request.limit}",
            f"로그: {log_path}",
            "결과는 완료되는 대로 텔레그램으로 따로 옵니다.",
        ]
    )
