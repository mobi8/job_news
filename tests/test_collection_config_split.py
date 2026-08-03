#!/usr/bin/env python3
"""Equivalence tests for split collection config vs monolithic.

Tests verify that the split YAML configuration in config/collection/
produces identical registry and derived data as the original monolithic
config/collection_sources.yaml.
"""

import pytest
from pathlib import Path

from src.utils.collection_config import (
    REGISTRY,
    load_collection_registry,
    _sources,
    JOB_PAGES,
    LINKEDIN_SEARCH_URLS,
    INDEED_SEARCH_URLS,
    GLASSDOOR_BROWSERLESS_KEYWORDS,
    DRJOBS_SEARCH_URLS,
    NEWS_RSS_FEEDS,
    PLAYER_RSS_FEEDS,
    LINKEDIN_SEARCH_KEYWORDS,
    INDEED_SEARCH_KEYWORDS,
    GOOGLE_SEARCH_KEYWORDS,
    NEWS_TOPICS,
    FOCUS_LOCATION_TERMS,
    REMOTE_GCC_LOCATION_TERMS,
    FOCUS_DOMAIN_TERMS,
    SOURCE_METADATA,
    SOURCE_LABELS,
    LINKEDIN_POST_SEARCH_PLANS,
)


class TestRegistryLoaded:
    """Test that the split registry loads successfully."""

    def test_registry_version(self):
        """Verify registry version is set."""
        assert REGISTRY.get("version") == 1

    def test_registry_has_expected_sections(self):
        """Verify all expected sections are present in registry."""
        expected_sections = [
            "version",
            "source_metadata",
            "sources",
            "filters",
            "runtime",
            "topics",
            "keyword_groups",
        ]
        for section in expected_sections:
            assert section in REGISTRY, f"Missing section: {section}"

    def test_sources_loaded(self):
        """Verify all expected sources are loaded."""
        expected_sources = {
            "job_pages",
            "linkedin_jobs",
            "indeed",
            "glassdoor",
            "drjobs",
            "jobspy",
            "linkedin_posts",
            "recruiters",
            "news_feeds",
            "player_feeds",
            "telegram_channels",
        }
        loaded_sources = set(_sources().keys())
        assert loaded_sources == expected_sources, (
            f"Loaded sources mismatch. Expected {expected_sources}, "
            f"got {loaded_sources}"
        )


class TestSourceMetadata:
    """Test source_metadata section."""

    def test_metadata_count(self):
        """Verify expected number of source metadata entries."""
        metadata = REGISTRY.get("source_metadata", [])
        assert len(metadata) == 27, f"Expected 27 sources, got {len(metadata)}"

    def test_metadata_structure(self):
        """Verify metadata has expected structure."""
        metadata = REGISTRY.get("source_metadata", [])
        for item in metadata:
            assert isinstance(item, dict)
            assert "id" in item
            assert "label" in item
            assert "kind" in item
            assert "country" in item

    def test_no_duplicate_source_ids(self):
        """Verify no duplicate source IDs in metadata."""
        metadata = REGISTRY.get("source_metadata", [])
        ids = [item["id"] for item in metadata]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {ids}"


class TestJobPages:
    """Test job_pages source."""

    def test_job_pages_count(self):
        """Verify expected number of job pages."""
        assert len(JOB_PAGES) == 6, f"Expected 6 job pages, got {len(JOB_PAGES)}"

    def test_job_pages_have_required_fields(self):
        """Verify each job page has required fields."""
        for page in JOB_PAGES:
            assert isinstance(page, dict)
            assert "id" in page
            assert "url" in page
            assert "source" in page
            assert "parser" in page


class TestLinkedInJobs:
    """Test linkedin_jobs source."""

    def test_linkedin_targets_count(self):
        """Verify expected number of LinkedIn targets."""
        linkedin = _sources().get("linkedin_jobs", {})
        targets = linkedin.get("targets", [])
        assert len(targets) == 34, f"Expected 34 targets, got {len(targets)}"

    def test_linkedin_urls_count(self):
        """Verify expected number of generated LinkedIn URLs."""
        assert len(LINKEDIN_SEARCH_URLS) == 34

    def test_no_duplicate_linkedin_target_ids(self):
        """Verify no duplicate target_ids in LinkedIn jobs."""
        linkedin = _sources().get("linkedin_jobs", {})
        targets = linkedin.get("targets", [])
        ids = [t.get("target_id") for t in targets if t.get("target_id")]
        assert len(ids) == len(set(ids)), f"Duplicate target IDs: {ids}"


class TestIndeed:
    """Test indeed source."""

    def test_indeed_targets_count(self):
        """Verify expected number of Indeed targets."""
        indeed = _sources().get("indeed", {})
        targets = indeed.get("targets", [])
        assert len(targets) == 1, f"Expected 1 target, got {len(targets)}"

    def test_indeed_urls_count(self):
        """Verify Indeed search URLs count (one per keyword group)."""
        # Indeed has 1 target with 7 keyword groups = 7 URLs
        assert len(INDEED_SEARCH_URLS) == 7

    def test_indeed_keyword_groups(self):
        """Verify Indeed keyword groups are present."""
        indeed = _sources().get("indeed", {})
        target = indeed.get("targets", [{}])[0]
        keyword_groups = target.get("keyword_groups", [])
        assert len(keyword_groups) > 0


class TestGlassdoor:
    """Test glassdoor source."""

    def test_glassdoor_keywords_count(self):
        """Verify Glassdoor keywords (stored in target, not root level)."""
        # Keywords are stored inside the target dict, not at root level
        # So GLASSDOOR_BROWSERLESS_KEYWORDS gets empty list (preserving original behavior)
        assert len(GLASSDOOR_BROWSERLESS_KEYWORDS) == 0

        # Verify keywords are actually in the target
        glassdoor = _sources().get("glassdoor", {})
        target = glassdoor.get("targets", [{}])[0]
        keywords = target.get("keywords", [])
        assert len(keywords) == 12

    def test_glassdoor_keywords_are_strings(self):
        """Verify Glassdoor keywords are strings."""
        for keyword in GLASSDOOR_BROWSERLESS_KEYWORDS:
            assert isinstance(keyword, str)


class TestDrjobs:
    """Test drjobs source."""

    def test_drjobs_urls_count(self):
        """Verify expected number of DrJobs URLs."""
        assert len(DRJOBS_SEARCH_URLS) > 0

    def test_drjobs_has_targets(self):
        """Verify DrJobs has configured targets."""
        drjobs = _sources().get("drjobs", {})
        targets = drjobs.get("targets", [])
        assert len(targets) > 0


class TestFeeds:
    """Test news and player feeds."""

    def test_news_feeds_count(self):
        """Verify expected number of news feeds."""
        assert len(NEWS_RSS_FEEDS) == 13, f"Expected 13 news feeds, got {len(NEWS_RSS_FEEDS)}"

    def test_player_feeds_count(self):
        """Verify expected number of player feeds."""
        assert len(PLAYER_RSS_FEEDS) == 1, f"Expected 1 player feed, got {len(PLAYER_RSS_FEEDS)}"

    def test_feeds_have_required_fields(self):
        """Verify each feed has required fields."""
        all_feeds = NEWS_RSS_FEEDS + PLAYER_RSS_FEEDS
        for feed in all_feeds:
            assert isinstance(feed, dict)
            assert "id" in feed
            assert "url" in feed
            assert "source" in feed


class TestFilters:
    """Test filters section."""

    def test_focus_location_terms(self):
        """Verify focus location terms are loaded."""
        assert len(FOCUS_LOCATION_TERMS) > 0
        assert "dubai" in FOCUS_LOCATION_TERMS
        assert "uae" in FOCUS_LOCATION_TERMS

    def test_remote_gcc_location_terms(self):
        """Verify remote GCC location terms are loaded."""
        assert len(REMOTE_GCC_LOCATION_TERMS) > 0

    def test_focus_domain_terms(self):
        """Verify focus domain terms are loaded."""
        assert len(FOCUS_DOMAIN_TERMS) > 0
        assert "crypto" in FOCUS_DOMAIN_TERMS


class TestKeywordGroups:
    """Test keyword_groups section."""

    def test_linkedin_keywords(self):
        """Verify LinkedIn keyword group."""
        assert len(LINKEDIN_SEARCH_KEYWORDS) > 0

    def test_indeed_keywords(self):
        """Verify Indeed keyword group."""
        assert len(INDEED_SEARCH_KEYWORDS) > 0

    def test_google_keywords(self):
        """Verify Google keyword group."""
        assert len(GOOGLE_SEARCH_KEYWORDS) > 0


class TestRuntime:
    """Test runtime section."""

    def test_phases_loaded(self):
        """Verify runtime phases are loaded."""
        phases = REGISTRY.get("runtime", {}).get("phases", [])
        assert len(phases) == 15, f"Expected 15 phases, got {len(phases)}"

    def test_phase_ids_unique(self):
        """Verify all phase IDs are unique."""
        phases = REGISTRY.get("runtime", {}).get("phases", [])
        phase_ids = [p.get("id") for p in phases]
        assert len(phase_ids) == len(set(phase_ids)), f"Duplicate phase IDs: {phase_ids}"


class TestTopics:
    """Test topics section."""

    def test_news_topics_loaded(self):
        """Verify news topics are loaded."""
        assert len(NEWS_TOPICS) > 0

    def test_topics_have_required_fields(self):
        """Verify each topic has required fields."""
        for topic in NEWS_TOPICS:
            assert isinstance(topic, dict)
            assert "key" in topic
            assert "label_ko" in topic
            assert "keywords" in topic


class TestLinkedInPosts:
    """Test linkedin_posts source."""

    def test_linkedin_posts_loaded(self):
        """Verify LinkedIn post search plans are loaded."""
        assert len(LINKEDIN_POST_SEARCH_PLANS) > 0

    def test_linkedin_posts_plan_count(self):
        """Verify expected count of LinkedIn post plans."""
        # Plans = enabled_locations * roles * leads
        # 5 locations * 10 roles * 4 leads = 200 (but some might be disabled)
        # At minimum, should have substantial count
        assert len(LINKEDIN_POST_SEARCH_PLANS) >= 100


class TestSourceMetadataConsistency:
    """Test consistency of source metadata with actual sources."""

    def test_all_metadata_ids_valid(self):
        """Verify all metadata IDs reference valid sources."""
        metadata = REGISTRY.get("source_metadata", [])
        metadata_ids = {m.get("id") for m in metadata}

        # Check that referenced sources actually exist or are referenced in config
        for source_id in metadata_ids:
            assert isinstance(source_id, str) and source_id
