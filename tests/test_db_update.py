#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
데이터베이스 업데이트 검증 테스트
"""

import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from utils.db import Database
from utils.models import JobPosting
from utils.utils import utc_now


class TestUpsertUpdate:
    """기존 공고 업데이트 테스트"""

    def test_upsert_updates_last_seen_at(self):
        """같은 공고를 다시 업로드하면 last_seen_at이 업데이트되어야 함"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)

            # 첫 번째 공고 업로드
            job1 = JobPosting(
                source="linkedin_public",
                source_job_id="123",
                title="Backend Engineer",
                company="Tech Corp",
                location="Dubai",
                url="https://linkedin.com/jobs/123",
                description="Seeking backend engineer",
            )

            inserted = db.upsert_jobs([job1])
            assert inserted == 1, "첫 번째 업로드에서 1개 삽입되어야 함"

            # 같은 공고를 다시 업로드 (약간 변경)
            import time
            time.sleep(0.1)

            job2 = JobPosting(
                source="linkedin_public",
                source_job_id="123",
                title="Backend Engineer",
                company="Tech Corp",
                location="Dubai",
                url="https://linkedin.com/jobs/123",
                description="Seeking backend engineer with new skill requirement",  # 약간 변경
            )

            inserted2 = db.upsert_jobs([job2])
            assert inserted2 == 0, "같은 지문으로 다시 업로드하면 새로 삽입되지 않음"

            # 데이터 확인
            all_jobs = db.fetch_all_jobs()
            assert len(all_jobs) == 1, "공고는 1개여야 함 (중복 제거)"

            job = all_jobs[0]
            assert job["description"] == job2.description, "description이 업데이트되어야 함"
            assert job["last_seen_at"] > job["first_seen_at"], "last_seen_at > first_seen_at"
            print(f"✓ last_seen_at 업데이트됨: {job['last_seen_at']}")

    def test_upsert_score_persists(self):
        """match_score가 업데이트될 때 유지되어야 함"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)

            job1 = JobPosting(
                source="indeed_uae",
                source_job_id="456",
                title="Senior Backend Engineer",
                company="Fintech Corp",
                location="Dubai",
                url="https://indeed.com/jobs/456",
                description="Senior backend engineer needed",
                match_score=75,  # 점수 설정
            )

            db.upsert_jobs([job1])

            # 같은 공고를 다시 업로드 (점수 변경)
            job2 = JobPosting(
                source="indeed_uae",
                source_job_id="456",
                title="Senior Backend Engineer",
                company="Fintech Corp",
                location="Dubai",
                url="https://indeed.com/jobs/456",
                description="Senior backend engineer needed",
                match_score=80,  # 새 점수
            )

            db.upsert_jobs([job2])

            # 데이터 확인
            all_jobs = db.fetch_all_jobs()
            job = all_jobs[0]
            assert job["match_score"] == 80, "점수가 업데이트되어야 함"
            print(f"✓ 점수 업데이트됨: {job['match_score']}")


class TestStaleJobs:
    """오래된 공고 처리"""

    def test_identify_stale_jobs(self):
        """3일 이상 업데이트되지 않은 공고 식별"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)

            # 오래된 공고 직접 삽입 (테스트용)
            old_time = (utc_now() - timedelta(days=4)).isoformat()
            current_time = utc_now().isoformat()

            db.conn.execute(
                """
                INSERT INTO jobs (fingerprint, source, source_job_id, title, company,
                                location, url, description, first_seen_at, last_seen_at, match_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "old_fingerprint_1",
                    "linkedin_public",
                    "old_123",
                    "Old Job",
                    "Old Corp",
                    "Dubai",
                    "https://example.com",
                    "Old description",
                    old_time,
                    old_time,  # 마지막 업데이트가 4일 전
                    50,
                ),
            )
            db.conn.commit()

            # 쿼리로 오래된 공고 찾기
            stale_jobs = db.conn.execute(
                "SELECT COUNT(*) FROM jobs WHERE last_seen_at < datetime('now', '-3 days')"
            ).fetchone()[0]

            assert stale_jobs > 0, "3일 이상 미업데이트 공고가 있어야 함"
            print(f"✓ 오래된 공고 감지: {stale_jobs}개")
