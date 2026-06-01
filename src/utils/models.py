#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


LINKEDIN_POST_SOURCES = {"linkedin_post", "linkedin_post_spot"}


@dataclass
class JobPosting:
    source: str
    source_job_id: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    remote: bool = False
    country: str = "UAE"
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    collected_at: Optional[str] = None
    match_score: int = 0

    @property
    def fingerprint(self) -> str:
        if self.source in LINKEDIN_POST_SOURCES:
            stable_id = (self.source_job_id or "").strip().lower()
            stable_url = (self.url or "").strip().lower()
            if stable_id:
                return f"{self.source}|{stable_id}"
            if stable_url:
                return f"{self.source}|{stable_url}"

        company_key = self.company.strip().lower() or self.source_job_id.strip().lower()
        raw = "|".join(
            [
                self.title.strip().lower(),
                company_key,
                self.location.strip().lower(),
            ]
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NewsItem:
    source: str
    title: str
    url: str
    published_at: str
    summary: str = ""

    @property
    def fingerprint(self) -> str:
        return hashlib.sha1(self.url.strip().lower().encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
