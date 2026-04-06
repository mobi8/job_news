#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from .config import EXCLUDED_LANGUAGE_TERMS, HARD_EXCLUDE_TITLE_TERMS
from .models import JobPosting, NewsItem
from .utils import normalize_linkedin_identifier, normalize_linkedin_url, utc_now


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                fingerprint TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_job_id TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                remote INTEGER NOT NULL DEFAULT 0,
                url TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                match_score INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news (
                fingerprint TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def upsert_jobs(self, jobs: List[JobPosting]) -> int:
        now = utc_now().isoformat()
        inserted = 0

        for job in jobs:
            if job.source == "linkedin_public":
                job.url = normalize_linkedin_url(job.url)
                job.source_job_id = normalize_linkedin_identifier(job.source, job.source_job_id)
            row = self.conn.execute(
                "SELECT first_seen_at FROM jobs WHERE fingerprint = ?",
                (job.fingerprint,),
            ).fetchone()

            first_seen_at = row["first_seen_at"] if row else now
            if row is None:
                inserted += 1

            job.first_seen_at = first_seen_at
            job.last_seen_at = now

            self.conn.execute(
                """
                INSERT INTO jobs (
                    fingerprint, source, source_job_id, title, company, location,
                    remote, url, description, first_seen_at, last_seen_at, match_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    source = excluded.source,
                    source_job_id = excluded.source_job_id,
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    remote = excluded.remote,
                    url = excluded.url,
                    description = excluded.description,
                    last_seen_at = excluded.last_seen_at,
                    match_score = excluded.match_score
                """,
                (
                    job.fingerprint,
                    job.source,
                    job.source_job_id,
                    job.title,
                    job.company,
                    job.location,
                    int(job.remote),
                    job.url,
                    job.description,
                    job.first_seen_at,
                    job.last_seen_at,
                    job.match_score,
                ),
            )

        self.conn.commit()
        return inserted

    def upsert_news(self, items: List[NewsItem]) -> int:
        now = utc_now().isoformat()
        inserted = 0

        for item in items:
            row = self.conn.execute(
                "SELECT first_seen_at FROM news WHERE fingerprint = ?",
                (item.fingerprint,),
            ).fetchone()

            first_seen_at = row["first_seen_at"] if row else now
            if row is None:
                inserted += 1

            self.conn.execute(
                """
                INSERT INTO news (
                    fingerprint, source, title, url, published_at, summary, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    source = excluded.source,
                    title = excluded.title,
                    url = excluded.url,
                    published_at = excluded.published_at,
                    summary = excluded.summary,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    item.fingerprint,
                    item.source,
                    item.title,
                    item.url,
                    item.published_at,
                    item.summary,
                    first_seen_at,
                    now,
                ),
            )

        self.conn.commit()
        return inserted

    def fetch_recent_news(self, hours: int = 48) -> List[Dict[str, Any]]:
        cutoff = (utc_now() - timedelta(hours=hours)).isoformat()
        rows = self.conn.execute(
            """
            SELECT source, title, url, published_at, summary, first_seen_at, last_seen_at
            FROM news
            WHERE first_seen_at >= ?
            ORDER BY published_at DESC
            """,
            (cutoff,),
        ).fetchall()
        return [dict(row) for row in rows]

    def track_player_mentions(self, hours: int = 168) -> Dict[str, Dict[str, Any]]:
        """
        Track crypto casino and iGaming player mentions from recent news.
        Returns dict: {player_name: {count: int, latest_date: str, articles: [...]}}
        """
        from .config import CRYPTO_CASINO_PLAYERS, IGAMING_PLAYERS

        rows = self.fetch_recent_news(hours)
        all_players = {p: {"category": "Crypto Casino"} for p in CRYPTO_CASINO_PLAYERS}
        all_players.update({p: {"category": "iGaming"} for p in IGAMING_PLAYERS})

        result = {}
        for player in all_players:
            matched = []
            for row in rows:
                text = (row["title"] + " " + row["summary"]).lower()
                if player.lower() in text:
                    matched.append(row)

            if not matched:
                continue

            matched.sort(key=lambda r: r["published_at"], reverse=True)
            result[player] = {
                "category": all_players[player]["category"],
                "count": len(matched),
                "latest_date": matched[0]["published_at"][:10],
                "articles": matched[:5],  # 최대 5개
            }

        # 멘션 수 내림차순 정렬
        result = dict(sorted(result.items(), key=lambda x: x[1]["count"], reverse=True))
        return result

    def compute_news_topics(self, hours: int = 168) -> List[Dict[str, Any]]:
        """
        Classify recent news items into topics based on keywords.
        Returns list of topics sorted by article count (descending).
        Each topic: {"key", "label_ko", "article_count", "latest_date", "articles": [...]}
        """
        from .config import NEWS_TOPICS
        rows = self.fetch_recent_news(hours)
        result = []
        for topic in NEWS_TOPICS:
            kws = [k.lower() for k in topic["keywords"]]
            matched = [
                r for r in rows
                if any(kw in (r["title"] + " " + r["summary"]).lower() for kw in kws)
            ]
            if not matched:
                continue
            matched.sort(key=lambda r: r["published_at"], reverse=True)
            result.append({
                "key": topic["key"],
                "label_ko": topic["label_ko"],
                "article_count": len(matched),
                "latest_date": matched[0]["published_at"],
                "articles": matched,
            })
        result.sort(key=lambda t: t["article_count"], reverse=True)
        return result

    def normalize_linkedin_urls(self) -> int:
        rows = self.conn.execute(
            """
            SELECT fingerprint, url, source_job_id
            FROM jobs
            WHERE source = 'linkedin_public'
            """
        ).fetchall()
        updated = 0
        for row in rows:
            current_url = row["url"]
            current_source_job_id = row["source_job_id"]
            normalized_url = normalize_linkedin_url(current_url)
            normalized_source_job_id = normalize_linkedin_identifier("linkedin_public", current_source_job_id)
            if normalized_url != current_url or normalized_source_job_id != current_source_job_id:
                self.conn.execute(
                    "UPDATE jobs SET url = ?, source_job_id = ? WHERE fingerprint = ?",
                    (normalized_url, normalized_source_job_id, row["fingerprint"]),
                )
                updated += 1
        if updated:
            self.conn.commit()
        return updated

    def fetch_all_jobs(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT fingerprint, source, source_job_id, title, company, location, url, description,
                   remote, first_seen_at, last_seen_at, match_score
            FROM jobs
            ORDER BY match_score DESC, first_seen_at DESC
            """
        ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            if item.get("source") == "linkedin_public":
                item["url"] = normalize_linkedin_url(item.get("url", ""))
                item["source_job_id"] = normalize_linkedin_identifier("linkedin_public", item.get("source_job_id", ""))
        return items

    def stats(self) -> Dict[str, Any]:
        now = utc_now()
        all_rows = self.conn.execute("SELECT source, location, first_seen_at FROM jobs").fetchall()

        def count_since(days: int) -> int:
            cutoff = now - timedelta(days=days)
            return sum(
                1
                for row in all_rows
                if datetime.fromisoformat(row["first_seen_at"]) >= cutoff
            )

        by_location: Dict[str, int] = {}
        for row in all_rows:
            by_location[row["location"]] = by_location.get(row["location"], 0) + 1

        return {
            "total_jobs": len(all_rows),
            "new_last_1_day": count_since(1),
            "new_last_7_days": count_since(7),
            "new_last_30_days": count_since(30),
            "top_locations": sorted(by_location.items(), key=lambda item: item[1], reverse=True)[:10],
        }

    def jobs_first_seen_since(self, hours: int) -> List[Dict[str, Any]]:
        cutoff = (utc_now() - timedelta(hours=hours)).isoformat()
        rows = self.conn.execute(
            """
            SELECT source, source_job_id, title, company, location, url, description,
                   remote, first_seen_at, last_seen_at, match_score
            FROM jobs
            WHERE first_seen_at >= ?
            ORDER BY match_score DESC, first_seen_at DESC
            """,
            (cutoff,),
        ).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            if item.get("source") == "linkedin_public":
                item["url"] = normalize_linkedin_url(item.get("url", ""))
                item["source_job_id"] = normalize_linkedin_identifier("linkedin_public", item.get("source_job_id", ""))
        return items

    def source_new_counts(self, hours: int) -> List[Dict[str, Any]]:
        cutoff = (utc_now() - timedelta(hours=hours)).isoformat()
        rows = self.conn.execute(
            """
            SELECT source, COUNT(*) AS jobs
            FROM jobs
            WHERE first_seen_at >= ?
            GROUP BY source
            ORDER BY jobs DESC, source ASC
            """,
            (cutoff,),
        ).fetchall()
        return [dict(row) for row in rows]

    def source_total_counts(self) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT source, COUNT(*) AS jobs
            FROM jobs
            GROUP BY source
            ORDER BY jobs DESC, source ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def source_daily_counts(self, days: int = 14) -> List[Dict[str, Any]]:
        cutoff = (utc_now() - timedelta(days=days)).date().isoformat()
        rows = self.conn.execute(
            """
            SELECT source,
                   substr(first_seen_at, 1, 10) AS seen_date,
                   COUNT(*) AS jobs
            FROM jobs
            WHERE substr(first_seen_at, 1, 10) >= ?
            GROUP BY source, seen_date
            ORDER BY seen_date DESC, source ASC
            """,
            (cutoff,),
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_sources(self, sources: List[str]) -> None:
        if not sources:
            return
        placeholders = ",".join("?" for _ in sources)
        self.conn.execute(f"DELETE FROM jobs WHERE source IN ({placeholders})", tuple(sources))
        self.conn.commit()

    def purge_language_filtered_jobs(self) -> None:
        clauses = " OR ".join(["lower(title) LIKE ?"] * len(EXCLUDED_LANGUAGE_TERMS))
        params = [f"%{term}%" for term in EXCLUDED_LANGUAGE_TERMS]
        self.conn.execute(
            f"DELETE FROM jobs WHERE ({clauses})",
            params,
        )
        self.conn.commit()

    def purge_hard_excluded_jobs(self) -> None:
        clauses = " OR ".join(["lower(title) LIKE ?"] * len(HARD_EXCLUDE_TITLE_TERMS))
        params = [f"%{term}%" for term in HARD_EXCLUDE_TITLE_TERMS]
        self.conn.execute(
            f"DELETE FROM jobs WHERE ({clauses})",
            params,
        )
        self.conn.commit()

    def purge_reject_feedback_jobs(self, reject_feedback: List[Dict[str, Any]]) -> int:
        """Remove jobs that match reject_feedback patterns. Returns count removed."""
        from .models import JobPosting
        from .utils import matches_reject_feedback

        if not reject_feedback:
            return 0

        all_jobs = self.fetch_all_jobs()
        fingerprints_to_remove = []

        for job_dict in all_jobs:
            # Convert dict back to JobPosting for matching
            try:
                job = JobPosting(
                    source=job_dict.get("source", ""),
                    source_job_id=job_dict.get("source_job_id", ""),
                    title=job_dict.get("title", ""),
                    company=job_dict.get("company", ""),
                    location=job_dict.get("location", ""),
                    url=job_dict.get("url", ""),
                    description=job_dict.get("description", ""),
                    remote=bool(job_dict.get("remote", False)),
                )
                if matches_reject_feedback(job, reject_feedback):
                    fingerprints_to_remove.append(job_dict.get("fingerprint"))
            except Exception:
                continue

        if fingerprints_to_remove:
            placeholders = ",".join(["?"] * len(fingerprints_to_remove))
            self.conn.execute(
                f"DELETE FROM jobs WHERE fingerprint IN ({placeholders})",
                fingerprints_to_remove,
            )
            self.conn.commit()

        return len(fingerprints_to_remove)

