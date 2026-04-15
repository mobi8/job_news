#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


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
        raw = "|".join(
            [
                self.title.strip().lower(),
                self.company.strip().lower(),
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
