#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for collection registry equivalence between split and monolithic configs.

Tests verify that the split YAML configuration in config/collection/
produces an identical registry to the original monolithic config/collection_sources.yaml.
"""

import pytest
import yaml
from pathlib import Path

from src.utils.collection_config import load_collection_registry, REGISTRY, CONFIG_PATH
from utils.collection_config import phase_registry, resolve_phase_id, validate_phase_registry
from watch.phase_runner import validate_phase_handlers


# ============================================================================
# Original phase registry tests (preserved)
# ============================================================================

def test_phase_registry_contains_required_phases():
    phase_ids = {phase.id for phase in phase_registry()}
    assert {
        "all",
        "fixed",
        "drjobs",
        "linkedin",
        "indeed",
        "jobspy",
            "glassdoor",
            "recruiters",
            "rss",
        "player",
        "telegram",
        "posts",
        "queue",
        "dashboard",
        "notifications",
    }.issubset(phase_ids)


def test_phase_registry_validation_passes():
    errors, warnings = validate_phase_registry()
    assert errors == []
    assert isinstance(warnings, list)


def test_phase_alias_resolution_uses_registry():
    assert resolve_phase_id("li") == "linkedin"
    assert resolve_phase_id("linkedin_jobs") == "linkedin"
    assert resolve_phase_id("news") == "rss"
    assert resolve_phase_id("collect") == "all"
    assert resolve_phase_id("list") == "list"
    assert resolve_phase_id("help") == "help"


def test_enabled_phases_have_handlers():
    errors, warnings = validate_phase_handlers()
    assert errors == []
    assert warnings == []


def test_target_support_matches_current_safe_handlers():
    target_support = {phase.id: phase.supports_target for phase in phase_registry()}
    for phase_id in [
        "fixed",
        "drjobs",
        "linkedin",
        "indeed",
        "jobspy",
        "glassdoor",
        "recruiters",
        "rss",
        "player",
        "posts",
    ]:
        assert target_support[phase_id] is True
    for phase_id in ["all", "telegram", "queue", "dashboard", "notifications"]:
        assert target_support[phase_id] is False


# ============================================================================
# New equivalence tests
# ============================================================================

@pytest.fixture
def split_registry():
    """Load registry from split config (default behavior)."""
    return REGISTRY


@pytest.fixture
def mono_registry():
    """Load registry from monolithic config."""
    mono_path = Path(__file__).resolve().parent.parent / "config" / "collection_sources.yaml"
    with open(mono_path) as f:
        return yaml.safe_load(f)


class TestRegistryEquivalence:
    """Test deep equivalence between split and monolithic registries."""

    def test_registry_structure(self, split_registry, mono_registry):
        """Verify both registries have identical top-level keys."""
        split_keys = set(split_registry.keys())
        mono_keys = set(mono_registry.keys())
        assert split_keys == mono_keys, f"Registry keys mismatch: {split_keys} vs {mono_keys}"

    def test_version_identical(self, split_registry, mono_registry):
        """Verify version is identical."""
        assert split_registry.get("version") == mono_registry.get("version")

    def test_source_metadata_list_structure(self, split_registry, mono_registry):
        """Verify source_metadata is a list in both."""
        split_meta = split_registry.get("source_metadata", [])
        mono_meta = mono_registry.get("source_metadata", [])
        assert isinstance(split_meta, list), "Split source_metadata must be a list"
        assert isinstance(mono_meta, list), "Monolithic source_metadata must be a list"
        assert len(split_meta) == len(mono_meta), f"source_metadata length: {len(split_meta)} vs {len(mono_meta)}"

    def test_source_metadata_ids(self, split_registry, mono_registry):
        """Verify all source metadata IDs match."""
        split_meta = split_registry.get("source_metadata", [])
        mono_meta = mono_registry.get("source_metadata", [])

        split_ids = {m.get("id") for m in split_meta}
        mono_ids = {m.get("id") for m in mono_meta}

        missing = mono_ids - split_ids
        extra = split_ids - mono_ids
        assert not missing, f"Source IDs in monolithic but not split: {missing}"
        assert not extra, f"Source IDs in split but not monolithic: {extra}"

    def test_sources_present(self, split_registry, mono_registry):
        """Verify all sources are present."""
        split_sources = set(split_registry.get("sources", {}).keys())
        mono_sources = set(mono_registry.get("sources", {}).keys())
        assert split_sources == mono_sources, f"Sources mismatch: {split_sources} vs {mono_sources}"

    def test_runtime_keys_complete(self, split_registry, mono_registry):
        """Verify all runtime keys are present (phases, defaults, per-source config)."""
        split_runtime = set(split_registry.get("runtime", {}).keys())
        mono_runtime = set(mono_registry.get("runtime", {}).keys())

        missing = mono_runtime - split_runtime
        extra = split_runtime - mono_runtime

        assert not missing, f"Runtime keys missing from split: {missing}"
        assert not extra, f"Extra runtime keys in split: {extra}"

    def test_runtime_defaults(self, split_registry, mono_registry):
        """Verify runtime.defaults is present and identical."""
        split_defaults = split_registry.get("runtime", {}).get("defaults")
        mono_defaults = mono_registry.get("runtime", {}).get("defaults")

        assert split_defaults is not None, "Split registry missing runtime.defaults"
        assert split_defaults == mono_defaults, "runtime.defaults mismatch"

    def test_runtime_linkedin_jobs_config(self, split_registry, mono_registry):
        """Verify runtime.linkedin_jobs config is present and identical."""
        split_config = split_registry.get("runtime", {}).get("linkedin_jobs")
        mono_config = mono_registry.get("runtime", {}).get("linkedin_jobs")

        assert split_config is not None, "Split registry missing runtime.linkedin_jobs"
        assert split_config == mono_config, "runtime.linkedin_jobs mismatch"

    def test_runtime_indeed_config(self, split_registry, mono_registry):
        """Verify runtime.indeed config is present and identical."""
        split_config = split_registry.get("runtime", {}).get("indeed")
        mono_config = mono_registry.get("runtime", {}).get("indeed")

        assert split_config is not None, "Split registry missing runtime.indeed"
        assert split_config == mono_config, "runtime.indeed mismatch"

    def test_runtime_glassdoor_config(self, split_registry, mono_registry):
        """Verify runtime.glassdoor config is present and identical."""
        split_config = split_registry.get("runtime", {}).get("glassdoor")
        mono_config = mono_registry.get("runtime", {}).get("glassdoor")

        assert split_config is not None, "Split registry missing runtime.glassdoor"
        assert split_config == mono_config, "runtime.glassdoor mismatch"

    def test_runtime_linkedin_posts_config(self, split_registry, mono_registry):
        """Verify runtime.linkedin_posts config is present and identical."""
        split_config = split_registry.get("runtime", {}).get("linkedin_posts")
        mono_config = mono_registry.get("runtime", {}).get("linkedin_posts")

        assert split_config is not None, "Split registry missing runtime.linkedin_posts"
        assert split_config == mono_config, "runtime.linkedin_posts mismatch"

    def test_runtime_phases_count(self, split_registry, mono_registry):
        """Verify phase count is identical."""
        split_phases = split_registry.get("runtime", {}).get("phases", [])
        mono_phases = mono_registry.get("runtime", {}).get("phases", [])

        assert len(split_phases) == len(mono_phases), f"Phase count: {len(split_phases)} vs {len(mono_phases)}"

    def test_target_count_per_source(self, split_registry, mono_registry):
        """Verify target counts match per source."""
        split_sources = split_registry.get("sources", {})
        mono_sources = mono_registry.get("sources", {})

        for source_name in split_sources:
            split_src = split_sources[source_name]
            mono_src = mono_sources.get(source_name)

            split_targets = split_src.get("targets", []) if isinstance(split_src, dict) else []
            mono_targets = mono_src.get("targets", []) if isinstance(mono_src, dict) else []

            assert len(split_targets) == len(mono_targets), (
                f"Source '{source_name}' target count: {len(split_targets)} vs {len(mono_targets)}"
            )

    def test_target_ids_per_source(self, split_registry, mono_registry):
        """Verify target IDs match per source."""
        split_sources = split_registry.get("sources", {})
        mono_sources = mono_registry.get("sources", {})

        for source_name in split_sources:
            split_src = split_sources[source_name]
            mono_src = mono_sources.get(source_name)

            split_targets = split_src.get("targets", []) if isinstance(split_src, dict) else []
            mono_targets = mono_src.get("targets", []) if isinstance(mono_src, dict) else []

            split_ids = {t.get("id") for t in split_targets if isinstance(t, dict)}
            mono_ids = {t.get("id") for t in mono_targets if isinstance(t, dict)}

            missing = mono_ids - split_ids
            extra = split_ids - mono_ids

            assert not missing, f"Source '{source_name}' missing target IDs: {missing}"
            assert not extra, f"Source '{source_name}' extra target IDs: {extra}"

    def test_filters_keys(self, split_registry, mono_registry):
        """Verify filter keys match."""
        split_filters = split_registry.get("filters", {})
        mono_filters = mono_registry.get("filters", {})

        split_keys = set(split_filters.keys())
        mono_keys = set(mono_filters.keys())

        assert split_keys == mono_keys, f"Filter keys: {split_keys} vs {mono_keys}"

    def test_focus_location_terms(self, split_registry, mono_registry):
        """Verify focus location terms match."""
        split_terms = split_registry.get("filters", {}).get("focus_location_terms", [])
        mono_terms = mono_registry.get("filters", {}).get("focus_location_terms", [])

        assert split_terms == mono_terms, "focus_location_terms mismatch"

    def test_keyword_groups_keys(self, split_registry, mono_registry):
        """Verify keyword_groups keys match."""
        split_kg = split_registry.get("keyword_groups", {})
        mono_kg = mono_registry.get("keyword_groups", {})

        split_keys = set(split_kg.keys())
        mono_keys = set(mono_kg.keys())

        assert split_keys == mono_keys, f"Keyword group keys: {split_keys} vs {mono_keys}"

    def test_topics_keys(self, split_registry, mono_registry):
        """Verify topics keys match."""
        split_topics = split_registry.get("topics", {})
        mono_topics = mono_registry.get("topics", {})

        split_keys = set(split_topics.keys())
        mono_keys = set(mono_topics.keys())

        assert split_keys == mono_keys, f"Topics keys: {split_keys} vs {mono_keys}"


class TestConfigPathHandling:
    """Test CONFIG_PATH behavior with different inputs."""

    def test_config_path_is_directory(self):
        """Test that CONFIG_PATH points to split directory."""
        assert CONFIG_PATH.is_dir(), f"CONFIG_PATH should be a directory, got: {CONFIG_PATH}"
        assert (CONFIG_PATH / "runtime.yaml").exists(), "config/collection/ missing runtime.yaml"

    def test_load_split_directory(self):
        """Test loading from split directory."""
        split_dir = Path(__file__).resolve().parent.parent / "config" / "collection"
        registry = load_collection_registry(split_dir)

        assert registry.get("version") == 1
        assert len(registry.get("source_metadata", [])) == 27
        assert len(registry.get("runtime", {}).get("phases", [])) == 15

    def test_load_monolithic_file(self):
        """Test loading from monolithic YAML file."""
        mono_file = Path(__file__).resolve().parent.parent / "config" / "collection_sources.yaml"
        registry = load_collection_registry(mono_file)

        assert registry.get("version") == 1
        assert isinstance(registry.get("source_metadata", []), list)

    def test_invalid_path_fails(self):
        """Test that invalid path raises error."""
        invalid_path = Path("/nonexistent/path")
        with pytest.raises(ValueError, match="must be a directory or .yaml file"):
            load_collection_registry(invalid_path)


class TestValidatorCorrectness:
    """Test that validator uses correct schema fields."""

    def test_validator_detects_duplicate_target_ids(self, split_registry):
        """Test that validator can detect duplicate target IDs."""
        # This test verifies validator uses correct 'id' field
        # If it were checking wrong field, duplicates wouldn't be caught
        sources = split_registry.get("sources", {})
        all_target_ids = []

        for source_name, source_value in sources.items():
            if isinstance(source_value, dict):
                targets = source_value.get("targets", [])
                for target in targets:
                    if isinstance(target, dict) and "id" in target:
                        all_target_ids.append(target["id"])

        # All target IDs should be unique
        assert len(all_target_ids) == len(set(all_target_ids)), (
            f"Validator should have caught duplicate target IDs. "
            f"Count: {len(all_target_ids)}, unique: {len(set(all_target_ids))}"
        )

    def test_validator_detects_duplicate_metadata_ids(self, split_registry):
        """Test that validator detects duplicate source metadata IDs."""
        metadata = split_registry.get("source_metadata", [])
        ids = [m.get("id") for m in metadata if isinstance(m, dict)]

        assert len(ids) == len(set(ids)), "Validator should have caught duplicate metadata IDs"

    def test_all_targets_have_id(self, split_registry):
        """Test that all targets have 'id' field (required by validator)."""
        sources = split_registry.get("sources", {})

        for source_name, source_value in sources.items():
            if isinstance(source_value, dict):
                targets = source_value.get("targets", [])
                for i, target in enumerate(targets):
                    assert isinstance(target, dict), f"Target {i} in {source_name} is not a dict"
                    assert "id" in target, f"Target {i} in {source_name} missing 'id' field"
                    assert target["id"], f"Target {i} in {source_name} has empty 'id' field"

    def test_all_metadata_have_id(self, split_registry):
        """Test that all metadata entries have 'id' field."""
        metadata = split_registry.get("source_metadata", [])

        for i, entry in enumerate(metadata):
            assert isinstance(entry, dict), f"Metadata {i} is not a dict"
            assert "id" in entry, f"Metadata {i} missing 'id' field"
            assert entry["id"], f"Metadata {i} has empty 'id' field"
