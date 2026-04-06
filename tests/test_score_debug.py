#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
점수 계산 디버그
"""

from utils.scoring import evaluate_fit


def test_detailed_scoring():
    """점수 계산 상세 분석"""
    record = {
        "source": "linkedin_public",
        "source_job_id": "111111",
        "title": "Senior Backend Engineer",
        "company": "Tech Corp",
        "location": "Dubai",
        "description": "",
        "url": "https://linkedin.com",
        "remote": False,
    }

    resume_text = "backend engineer cloud"
    fit = evaluate_fit(record, resume_text)

    print("\n=== 점수 계산 디버그 ===")
    print(f"Location tags: {fit.get('location_tags', [])}")
    print(f"Domain tags: {fit.get('domain_tags', [])}")
    print(f"Strong domain tags: {fit.get('strong_domain_tags', [])}")
    print(f"Role tags: {fit.get('role_tags', [])}")
    print(f"Commercial role tags: {fit.get('commercial_role_tags', [])}")
    print(f"Product role tags: {fit.get('product_role_tags', [])}")
    print(f"Location OK: {fit.get('location_ok')}")
    print(f"Role path OK: ?")
    print(f"Final score: {fit['score']}")
    print(f"Qualifies: {fit['qualifies']}")


if __name__ == "__main__":
    test_detailed_scoring()
