#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for models.py

Tests JobPosting and NewsItem dataclasses including:
- Fingerprint generation (SHA1 hash of normalized fields)
- Data serialization via to_dict()
- Field validation and defaults
- Edge cases and boundary conditions
"""

import hashlib
from datetime import datetime
from dataclasses import asdict

import pytest

from utils.models import JobPosting, NewsItem


class TestJobPosting:
    """Tests for JobPosting dataclass"""

    def test_job_posting_creation_with_required_fields(self):
        """Test basic JobPosting creation with required fields"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="12345",
            title="Senior Developer",
            company="Tech Corp",
            location="Dubai",
            url="https://indeed.com/job/12345"
        )
        assert job.source == "indeed_uae"
        assert job.source_job_id == "12345"
        assert job.title == "Senior Developer"
        assert job.company == "Tech Corp"
        assert job.location == "Dubai"
        assert job.url == "https://indeed.com/job/12345"

    def test_job_posting_creation_with_all_fields(self):
        """Test JobPosting creation with all fields including optional ones"""
        job = JobPosting(
            source="linkedin_public",
            source_job_id="98765",
            title="Product Manager",
            company="FinTech Inc",
            location="Abu Dhabi",
            url="https://linkedin.com/jobs/view/98765",
            description="Looking for an experienced PM",
            remote=True,
            first_seen_at="2026-03-30T10:00:00",
            last_seen_at="2026-03-30T12:00:00",
            match_score=85
        )
        assert job.description == "Looking for an experienced PM"
        assert job.remote is True
        assert job.first_seen_at == "2026-03-30T10:00:00"
        assert job.last_seen_at == "2026-03-30T12:00:00"
        assert job.match_score == 85

    def test_job_posting_default_values(self):
        """Test that optional fields have correct default values"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Developer",
            company="Corp",
            location="Dubai",
            url="https://example.com"
        )
        assert job.description == ""
        assert job.remote is False
        assert job.first_seen_at is None
        assert job.last_seen_at is None
        assert job.match_score == 0

    def test_job_posting_fingerprint_basic(self):
        """Test fingerprint generation from title, company, location"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://example.com"
        )
        raw = "senior developer|techcorp|dubai"
        expected_fingerprint = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        assert job.fingerprint == expected_fingerprint

    def test_job_posting_fingerprint_case_insensitive(self):
        """Test that fingerprint is case-insensitive"""
        job1 = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://example.com"
        )
        job2 = JobPosting(
            source="indeed_uae",
            source_job_id="456",
            title="SENIOR DEVELOPER",
            company="techcorp",
            location="DUBAI",
            url="https://other.com"
        )
        assert job1.fingerprint == job2.fingerprint

    def test_job_posting_fingerprint_whitespace_normalized(self):
        """Test that fingerprint strips and normalizes whitespace"""
        job1 = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://example.com"
        )
        job2 = JobPosting(
            source="indeed_uae",
            source_job_id="456",
            title="  Senior Developer  ",
            company="  TechCorp  ",
            location="  Dubai  ",
            url="https://example.com"
        )
        assert job1.fingerprint == job2.fingerprint

    def test_job_posting_fingerprint_different_jobs(self):
        """Test that different jobs have different fingerprints"""
        job1 = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://example.com"
        )
        job2 = JobPosting(
            source="indeed_uae",
            source_job_id="456",
            title="Junior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://example.com"
        )
        assert job1.fingerprint != job2.fingerprint

    def test_job_posting_fingerprint_with_special_characters(self):
        """Test fingerprint generation with special characters"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="C++ / Rust Developer",
            company="Tech & Co.",
            location="Dubai, UAE",
            url="https://example.com"
        )
        raw = "c++ / rust developer|tech & co.|dubai, uae"
        expected = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        assert job.fingerprint == expected

    def test_job_posting_to_dict(self):
        """Test conversion to dictionary"""
        job = JobPosting(
            source="linkedin_public",
            source_job_id="98765",
            title="Product Manager",
            company="FinTech Inc",
            location="Abu Dhabi",
            url="https://linkedin.com/jobs/view/98765",
            description="Seeking PM",
            remote=True,
            first_seen_at="2026-03-30T10:00:00",
            last_seen_at="2026-03-30T12:00:00",
            match_score=85
        )
        result = job.to_dict()
        assert isinstance(result, dict)
        assert result["source"] == "linkedin_public"
        assert result["title"] == "Product Manager"
        assert result["description"] == "Seeking PM"
        assert result["match_score"] == 85
        assert result["remote"] is True

    def test_job_posting_to_dict_with_defaults(self):
        """Test to_dict with default values"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Developer",
            company="Corp",
            location="Dubai",
            url="https://example.com"
        )
        result = job.to_dict()
        assert result["description"] == ""
        assert result["remote"] is False
        assert result["first_seen_at"] is None
        assert result["last_seen_at"] is None
        assert result["match_score"] == 0

    def test_job_posting_empty_strings(self):
        """Test JobPosting with empty strings"""
        job = JobPosting(
            source="",
            source_job_id="",
            title="",
            company="",
            location="",
            url=""
        )
        assert job.source == ""
        assert job.title == ""
        # Fingerprint should still generate from empty strings
        assert isinstance(job.fingerprint, str)
        assert len(job.fingerprint) == 40  # SHA1 hex length

    def test_job_posting_unicode_characters(self):
        """Test JobPosting with unicode characters"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="مدير المنتج",
            company="شركة التقنية",
            location="دبي",
            url="https://example.com"
        )
        assert job.title == "مدير المنتج"
        assert isinstance(job.fingerprint, str)
        assert len(job.fingerprint) == 40


class TestNewsItem:
    """Tests for NewsItem dataclass"""

    def test_news_item_creation_with_required_fields(self):
        """Test basic NewsItem creation with required fields"""
        item = NewsItem(
            source="rss_igaming_business",
            title="New Gaming Regulations",
            url="https://igamingbusiness.com/article/123",
            published_at="2026-03-30T10:00:00"
        )
        assert item.source == "rss_igaming_business"
        assert item.title == "New Gaming Regulations"
        assert item.url == "https://igamingbusiness.com/article/123"
        assert item.published_at == "2026-03-30T10:00:00"

    def test_news_item_creation_with_all_fields(self):
        """Test NewsItem creation with all fields"""
        item = NewsItem(
            source="rss_fintech_uae",
            title="Crypto Market Update",
            url="https://fintechnews.ae/article/456",
            published_at="2026-03-30T14:30:00",
            summary="Market saw 5% growth today"
        )
        assert item.summary == "Market saw 5% growth today"

    def test_news_item_default_summary(self):
        """Test that summary has default value"""
        item = NewsItem(
            source="rss_igaming_business",
            title="News Title",
            url="https://example.com",
            published_at="2026-03-30T10:00:00"
        )
        assert item.summary == ""

    def test_news_item_fingerprint_from_url(self):
        """Test fingerprint generation from URL"""
        item = NewsItem(
            source="rss_igaming_business",
            title="Title",
            url="https://igamingbusiness.com/article/123",
            published_at="2026-03-30T10:00:00"
        )
        raw = "https://igamingbusiness.com/article/123".lower()
        expected = hashlib.sha1(raw.encode("utf-8")).hexdigest()
        assert item.fingerprint == expected

    def test_news_item_fingerprint_case_insensitive(self):
        """Test that fingerprint is case-insensitive"""
        item1 = NewsItem(
            source="rss_igaming_business",
            title="Title 1",
            url="https://igamingbusiness.com/article/123",
            published_at="2026-03-30T10:00:00"
        )
        item2 = NewsItem(
            source="rss_igaming_business",
            title="Title 2",
            url="HTTPS://IGAMINGBUSINESS.COM/ARTICLE/123",
            published_at="2026-03-30T10:00:00"
        )
        assert item1.fingerprint == item2.fingerprint

    def test_news_item_fingerprint_whitespace_normalized(self):
        """Test that fingerprint strips whitespace from URL"""
        item1 = NewsItem(
            source="rss_igaming_business",
            title="Title",
            url="https://example.com/article",
            published_at="2026-03-30T10:00:00"
        )
        item2 = NewsItem(
            source="rss_igaming_business",
            title="Title",
            url="  https://example.com/article  ",
            published_at="2026-03-30T10:00:00"
        )
        assert item1.fingerprint == item2.fingerprint

    def test_news_item_fingerprint_different_urls(self):
        """Test that different URLs produce different fingerprints"""
        item1 = NewsItem(
            source="rss_igaming_business",
            title="Title",
            url="https://example.com/article/1",
            published_at="2026-03-30T10:00:00"
        )
        item2 = NewsItem(
            source="rss_igaming_business",
            title="Title",
            url="https://example.com/article/2",
            published_at="2026-03-30T10:00:00"
        )
        assert item1.fingerprint != item2.fingerprint

    def test_news_item_to_dict(self):
        """Test conversion to dictionary"""
        item = NewsItem(
            source="rss_fintech_uae",
            title="Crypto Market Update",
            url="https://fintechnews.ae/article/456",
            published_at="2026-03-30T14:30:00",
            summary="Market saw 5% growth today"
        )
        result = item.to_dict()
        assert isinstance(result, dict)
        assert result["source"] == "rss_fintech_uae"
        assert result["title"] == "Crypto Market Update"
        assert result["url"] == "https://fintechnews.ae/article/456"
        assert result["summary"] == "Market saw 5% growth today"
        assert result["published_at"] == "2026-03-30T14:30:00"

    def test_news_item_to_dict_with_defaults(self):
        """Test to_dict with default summary"""
        item = NewsItem(
            source="rss_igaming_business",
            title="Title",
            url="https://example.com",
            published_at="2026-03-30T10:00:00"
        )
        result = item.to_dict()
        assert result["summary"] == ""

    def test_news_item_empty_strings(self):
        """Test NewsItem with empty strings"""
        item = NewsItem(
            source="",
            title="",
            url="",
            published_at=""
        )
        assert item.source == ""
        # Fingerprint should still generate from empty URL
        assert isinstance(item.fingerprint, str)
        assert len(item.fingerprint) == 40  # SHA1 hex length

    def test_news_item_unicode_title(self):
        """Test NewsItem with unicode characters"""
        item = NewsItem(
            source="rss_igaming_business",
            title="أخبار الألعاب",
            url="https://example.com",
            published_at="2026-03-30T10:00:00"
        )
        assert item.title == "أخبار الألعاب"
        result = item.to_dict()
        assert result["title"] == "أخبار الألعاب"

    def test_news_item_special_characters_in_url(self):
        """Test NewsItem with special characters in URL"""
        item = NewsItem(
            source="rss_igaming_business",
            title="Title",
            url="https://example.com/article?id=123&type=crypto",
            published_at="2026-03-30T10:00:00"
        )
        assert item.url == "https://example.com/article?id=123&type=crypto"
        assert isinstance(item.fingerprint, str)
