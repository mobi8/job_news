#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LinkedIn 공고 점수 계산 테스트
"""

import pytest
from utils.models import JobPosting
from utils.scoring import calculate_match_score, evaluate_fit


class TestLinkedInScoring:
    """LinkedIn 공고의 점수 계산 테스트"""

    def test_linkedin_with_empty_description(self):
        """description이 비어있는 LinkedIn 공고 점수 계산"""
        job = JobPosting(
            source="linkedin_public",
            source_job_id="123456",
            title="Senior Backend Engineer - Cloud",
            company="Tech Corp",
            location="Dubai, UAE",
            url="https://www.linkedin.com/jobs/view/123456/",
            description="",  # 비어있음
            remote=False,
        )

        resume_text = "cloud engineer backend fintech"
        score = calculate_match_score(job, resume_text)

        # 점수가 0이 아니어야 함
        assert score > 0, f"LinkedIn 공고의 점수가 0입니다. score={score}"
        print(f"✓ 빈 description → score={score}")

    def test_linkedin_with_valid_description(self):
        """description이 있는 LinkedIn 공고 점수 계산"""
        job = JobPosting(
            source="linkedin_public",
            source_job_id="789012",
            title="Senior Backend Engineer - Cloud",
            company="Tech Corp",
            location="Dubai, UAE",
            url="https://www.linkedin.com/jobs/view/789012/",
            description="We are looking for a senior backend engineer with experience in cloud infrastructure and fintech solutions.",
            remote=False,
        )

        resume_text = "cloud engineer backend fintech"
        score = calculate_match_score(job, resume_text)

        assert score > 0, f"LinkedIn 공고 (description 있음)의 점수가 0입니다. score={score}"
        print(f"✓ 유효한 description → score={score}")

    def test_linkedin_remote_with_empty_description(self):
        """Remote LinkedIn 공고 (description 비어있음)"""
        job = JobPosting(
            source="linkedin_public",
            source_job_id="345678",
            title="Remote Product Manager - Crypto",
            company="Crypto Startup",
            location="Remote",
            url="https://www.linkedin.com/jobs/view/345678/",
            description="",  # 비어있음
            remote=True,
        )

        resume_text = "product manager crypto fintech"
        score = calculate_match_score(job, resume_text)

        # 원격 + 관련 키워드 있으면 점수 나옴
        assert score >= 0, f"점수가 음수입니다: {score}"
        print(f"✓ Remote (빈 description) → score={score}")

    def test_evaluate_fit_with_empty_description(self):
        """evaluate_fit 직접 테스트: 빈 description"""
        record = {
            "source": "linkedin_public",
            "source_job_id": "111111",
            "title": "Senior Backend Engineer",
            "company": "Tech Corp",
            "location": "Dubai",
            "description": "",  # 빈 description
            "url": "https://linkedin.com",
            "remote": False,
        }

        resume_text = "backend engineer cloud"
        fit = evaluate_fit(record, resume_text)

        # 점수 계산 과정을 상세히 보기
        print(f"\n점수 분석:")
        print(f"  fit['score'] = {fit['score']}")
        print(f"  fit['qualifies'] = {fit['qualifies']}")
        print(f"  fit['tags'] = {fit['tags']}")

        assert fit["score"] > 0, f"빈 description → score={fit['score']}, 0이어야 하지 않음"
        print(f"✓ evaluate_fit (빈 description) → score={fit['score']}")

    def test_evaluate_fit_with_valid_description(self):
        """evaluate_fit 직접 테스트: 유효한 description"""
        record = {
            "source": "linkedin_public",
            "source_job_id": "222222",
            "title": "Senior Backend Engineer",
            "company": "Tech Corp",
            "location": "Dubai",
            "description": "We seek a backend engineer skilled in Python, Go, cloud infrastructure",
            "url": "https://linkedin.com",
            "remote": False,
        }

        resume_text = "backend engineer cloud fintech"
        fit = evaluate_fit(record, resume_text)

        assert fit["score"] > 0, f"유효한 description → score={fit['score']}"
        print(f"✓ evaluate_fit (유효한 description) → score={fit['score']}")
