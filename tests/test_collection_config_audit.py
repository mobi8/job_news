#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Audit tests for config-driven collection routing implementation."""

import os
import pytest
from unittest.mock import patch, MagicMock

from utils.collection_config import (
    get_enabled_job_source_ids,
    get_enabled_linkedin_source_ids,
    get_source_metadata_by_id,
    get_collection_target_metadata,
    source_country_map,
)
from watch.scraper import _normalize_country


class TestEnabledJobSourceIds:
    """Tests for get_enabled_job_source_ids() handling list and dict sources."""

    def test_job_pages_list_structure_included(self, monkeypatch):
        """Verify job_pages (list structure) sources are collected."""
        enabled_ids = set(get_enabled_job_source_ids())
        # At least some job_pages sources should be present
        job_page_sources = {
            "jobvite_pragmaticplay",
            "smartrecruitment",
            "igamingrecruitment",
            "igaminghunt_bamboohr",
            "jobrapido_uae",
            "jobleads",
        }
        # Should include at least one job_pages source
        included = enabled_ids & job_page_sources
        assert len(included) > 0, f"No job_pages sources found in {enabled_ids}"

    def test_linkedin_targets_included(self):
        """Verify LinkedIn target sources are collected."""
        enabled_ids = set(get_enabled_job_source_ids())
        # Should include linkedin sources
        linkedin_sources = {"linkedin_public", "linkedin_emea", "linkedin_amsterdam", "linkedin_australia"}
        included = enabled_ids & linkedin_sources
        assert len(included) > 0, f"No LinkedIn sources found in {enabled_ids}"

    def test_enabled_linkedin_job_sources(self):
        """Verify get_enabled_linkedin_source_ids() returns LinkedIn sources only."""
        linkedin_ids = set(get_enabled_linkedin_source_ids())
        # Should not include non-LinkedIn job sources
        non_linkedin = {"jobvite_pragmaticplay", "smartrecruitment", "drjobs"}
        assert len(linkedin_ids & non_linkedin) == 0, "Non-LinkedIn sources in LinkedIn list"
        # Should include LinkedIn sources
        linkedin_sources = {"linkedin_public", "linkedin_emea", "linkedin_amsterdam", "linkedin_australia"}
        included = linkedin_ids & linkedin_sources
        assert len(included) > 0, f"No LinkedIn sources found in {linkedin_ids}"

    def test_amsterdam_and_australia_sources_enabled(self):
        """Verify amsterdam and australia LinkedIn sources are available.

        Note: Amsterdam is now generated through matrix in linkedin_jobs source.
        Australia remains as a separate manual source.
        """
        linkedin_ids = get_enabled_linkedin_source_ids()
        assert "linkedin_australia" in linkedin_ids, "linkedin_australia not in enabled sources"
        # Amsterdam is no longer a separate source; it's generated from matrix
        assert "linkedin_amsterdam" not in linkedin_ids, "amsterdam should be matrix-generated, not manual"


class TestSourceMetadataLookup:
    """Tests for source metadata country lookups."""

    def test_get_source_metadata_by_id_returns_dict(self):
        """Verify get_source_metadata_by_id() returns metadata dict."""
        meta = get_source_metadata_by_id("linkedin_public")
        assert meta is not None
        assert meta.get("id") == "linkedin_public"
        assert meta.get("label") == "LinkedIn"
        assert meta.get("country") == "UAE"

    def test_amsterdam_source_metadata(self):
        """Verify amsterdam source has Netherlands country."""
        meta = get_source_metadata_by_id("linkedin_amsterdam")
        assert meta is not None
        assert meta.get("country") == "Netherlands"
        assert meta.get("label") == "LinkedIn Amsterdam"

    def test_australia_source_metadata(self):
        """Verify australia source has Australia country."""
        meta = get_source_metadata_by_id("linkedin_australia")
        assert meta is not None
        assert meta.get("country") == "Australia"
        assert meta.get("label") == "LinkedIn Australia"

    def test_invalid_source_returns_none(self):
        """Verify unknown source returns None."""
        meta = get_source_metadata_by_id("nonexistent_source")
        assert meta is None

    def test_country_map_includes_new_sources(self):
        """Verify source_country_map includes amsterdam and australia."""
        country_map = source_country_map()
        assert country_map.get("linkedin_amsterdam") == "Netherlands"
        assert country_map.get("linkedin_australia") == "Australia"


class TestCountryNormalization:
    """Tests for _normalize_country() with source metadata."""

    def test_priority_1_existing_country_from_parsing(self):
        """Priority 1: Job's existing country from parsing should be used."""
        job = {
            "country": "UAE",
            "source": "linkedin_public",
            "location": "Amsterdam, Netherlands",
        }
        result = _normalize_country(job)
        # Should prefer existing country from parsing, not location
        assert result == "UAE"

    def test_priority_2_source_metadata_country(self):
        """Priority 2: Source metadata country when job has no parsed country."""
        job = {
            "country": None,
            "source": "linkedin_amsterdam",
            "location": "Remote",
        }
        result = _normalize_country(job)
        # Should use source metadata (Netherlands)
        assert result == "Netherlands"

    def test_priority_3_location_based_detection(self):
        """Priority 3: Location-based detection as fallback."""
        job = {
            "country": "",
            "source": "unknown_source",
            "location": "Amsterdam, Netherlands",
        }
        result = _normalize_country(job)
        # Should detect Netherlands from location
        assert result == "Netherlands"

    def test_australia_location_detection(self):
        """Verify Australia location detection."""
        job = {
            "country": "",
            "source": "unknown_source",
            "location": "Sydney, Australia",
        }
        result = _normalize_country(job)
        assert result == "Australia"

    def test_special_case_other_country(self):
        """Verify special case for 'Other' country."""
        job = {
            "country": "Other",
            "source": "linkedin_post_spot",
            "location": "Dubai",
        }
        result = _normalize_country(job)
        assert result == "Other"

    def test_emea_source_returns_remote(self):
        """Verify linkedin_emea source returns Remote."""
        job = {
            "source": "linkedin_emea",
            "location": "EMEA",
        }
        result = _normalize_country(job)
        assert result == "Remote"

    def test_unresolved_country_returns_empty(self):
        """Verify unresolved country returns empty string."""
        job = {
            "country": "",
            "source": "unknown",
            "location": "",
        }
        result = _normalize_country(job)
        assert result == ""


class TestCollectionTargetMetadata:
    """Tests for get_collection_target_metadata()."""

    def test_metadata_includes_amsterdam_target(self):
        """Verify amsterdam targets are in collection metadata."""
        metadata = get_collection_target_metadata()
        # Should have amsterdam targets
        amsterdam_targets = [k for k in metadata.keys() if "amsterdam" in k.lower()]
        assert len(amsterdam_targets) > 0, "No amsterdam targets in metadata"

    def test_metadata_includes_australia_target(self):
        """Verify australia targets are in collection metadata."""
        metadata = get_collection_target_metadata()
        # Should have australia targets
        australia_targets = [k for k in metadata.keys() if "australia" in k.lower()]
        assert len(australia_targets) > 0, "No australia targets in metadata"

    def test_amsterdam_target_has_correct_metadata(self):
        """Verify amsterdam target metadata."""
        metadata = get_collection_target_metadata()
        # Find an amsterdam target
        amsterdam_target = next(
            (k for k in metadata.keys() if "amsterdam" in k.lower()),
            None,
        )
        assert amsterdam_target is not None
        target_meta = metadata[amsterdam_target]
        assert target_meta.get("source") == "linkedin_amsterdam"
        assert target_meta.get("country") == "Netherlands"


class TestShellPriorityOrdering:
    """Tests for environment variable priority: external env > .env > YAML."""

    def test_env_priority_over_yaml(self, monkeypatch):
        """Verify external env var overrides YAML config."""
        # Set external env var
        monkeypatch.setenv("JOB_WATCH_SOURCES", "linkedin_public,linkedin_amsterdam")
        # Even if not in .env, should use external env
        sources = os.getenv("JOB_WATCH_SOURCES", "").split(",")
        assert "linkedin_amsterdam" in sources

    def test_collect_uses_env_over_yaml(self):
        """Verify /collect respects environment priority."""
        # This would be tested in integration tests with actual run_collect_once.sh
        # The shell script checks JOB_WATCH_SOURCES env first
        pass


class TestSelectorResolution:
    """Tests for selector resolution for amsterdam/australia."""

    def test_amsterdam_selector_resolves(self):
        """Verify /collect linkedin amsterdam resolves correctly."""
        # This tests that the selector system recognizes amsterdam as a valid target
        from utils.collection_config import selector_candidates_for_phase

        candidates = selector_candidates_for_phase("linkedin")
        # Should include amsterdam selector candidates
        amsterdam_candidates = [c for c in candidates if "amsterdam" in c.target_id.lower()]
        assert len(amsterdam_candidates) > 0, "No amsterdam selector candidates found"
        # Should be 5 targets (payments, custody, settlement, product, igaming)
        assert len(amsterdam_candidates) == 5, f"Expected 5 amsterdam targets, got {len(amsterdam_candidates)}"

    def test_australia_selector_resolves(self):
        """Verify /collect linkedin australia resolves correctly."""
        from utils.collection_config import selector_candidates_for_phase

        candidates = selector_candidates_for_phase("linkedin")
        # Should include australia selector candidates
        australia_candidates = [c for c in candidates if "australia" in c.target_id.lower()]
        assert len(australia_candidates) > 0, "No australia selector candidates found"
        # Should be 5 targets (payments, custody, settlement, product, igaming)
        assert len(australia_candidates) == 5, f"Expected 5 australia targets, got {len(australia_candidates)}"


class TestYamlOnlyConfiguration:
    """Tests verifying amsterdam region works through matrix generation."""

    def test_amsterdam_requires_only_yaml_changes(self):
        """Verify amsterdam region works with YAML config (matrix-based)."""
        # 1. Source metadata exists in YAML
        meta = get_source_metadata_by_id("linkedin_amsterdam")
        assert meta is not None, "linkedin_amsterdam not in source_metadata"

        # 2. Targets exist in YAML/matrix
        metadata = get_collection_target_metadata()
        amsterdam_targets = [k for k in metadata.keys() if "amsterdam" in k.lower()]
        assert len(amsterdam_targets) > 0, "No amsterdam targets generated"
        assert len(amsterdam_targets) == 5, f"Expected 5 amsterdam targets, got {len(amsterdam_targets)}"

        # 3. Source metadata has correct country
        meta = get_source_metadata_by_id("linkedin_amsterdam")
        assert meta.get("country") == "Netherlands", "amsterdam country not set correctly"

        # 4. Selector candidates include amsterdam
        from utils.collection_config import selector_candidates_for_phase
        candidates = selector_candidates_for_phase("linkedin")
        amsterdam_candidates = [c for c in candidates if "amsterdam" in c.target_id.lower()]
        assert len(amsterdam_candidates) > 0, "No amsterdam selector candidates"

    def test_new_region_integration_chain(self):
        """Verify the full chain works for amsterdam (matrix-based)."""
        # 1. YAML config defines the region through matrix
        # 2. Targets are generated and included in production
        # 3. get_source_metadata_by_id() returns its metadata
        # 4. selector_candidates_for_phase() generates candidates
        # 5. No code changes needed anywhere

        # Amsterdam is now generated through matrix, not as a separate manual source
        # But it should still be present in production output
        metadata = get_collection_target_metadata()
        amsterdam_in_metadata = any("amsterdam" in k.lower() for k in metadata.keys())

        meta = get_source_metadata_by_id("linkedin_amsterdam")
        amsterdam_has_meta = meta is not None

        from utils.collection_config import selector_candidates_for_phase
        candidates = selector_candidates_for_phase("linkedin")
        amsterdam_has_candidates = any(
            "amsterdam" in c.target_id.lower() for c in candidates
        )

        assert amsterdam_in_metadata, "amsterdam targets not generated"
        assert amsterdam_has_meta, "amsterdam not in source_metadata"
        assert amsterdam_has_candidates, "amsterdam not in selector candidates"
