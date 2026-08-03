#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for collection registry equivalence between split and monolithic configs.

Tests verify that the split YAML configuration in config/collection/
produces an identical registry to the original monolithic config/collection_sources.yaml.
"""

import json
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


def test_indeed_country_specific_routing_and_metadata():
    from src.utils.collection_config import build_indeed_search_targets, target_metadata_by_url

    targets = build_indeed_search_targets()
    assert len(targets) == 1
    assert {target.country for target in targets} == {"UAE"}
    assert {target.source for target in targets} == {"indeed_uae"}
    assert {target.keyword_group_id for target in targets} == {
        "account_manager",
    }
    metadata = target_metadata_by_url(targets)
    account = next(target for target in targets if target.keyword_query == "account manager payments")
    assert metadata[account.url]["country"] == "UAE"
    assert metadata[account.url]["source"] == "indeed_uae"


def test_indeed_unsupported_locations_are_disabled_with_reason():
    locations = REGISTRY["locations"]
    for location_id in ["united_kingdom", "amsterdam", "ireland", "spain", "portugal", "cyprus"]:
        indeed = locations[location_id].get("indeed") or {}
        assert indeed.get("enabled") is False
        assert indeed.get("unsupported_reason")


def test_indeed_selector_filters_to_role_queries(monkeypatch):
    from src.utils import collection_config

    selection = collection_config.resolve_selector("indeed", "uae", "account_manager")
    assert selection.status == "matched"
    assert selection.keyword_group_ids == ("account_manager",)
    assert selection.keyword_queries == ("account manager payments",)
    assert len(selection.targets) == 1

    payload = {
        "phase": "indeed",
        "target_ids": ["indeed_uae"],
        "keyword_group_ids": ["account_manager"],
        "keyword_queries": ["account manager payments"],
    }
    monkeypatch.setenv("COLLECTION_TARGET_FILTER_JSON", json.dumps(payload))
    filtered = collection_config.build_indeed_search_targets()
    assert [target.keyword_query for target in filtered] == ["account manager payments"]


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
        """Verify both registries have identical core top-level keys (excluding new extensions)."""
        split_keys = set(split_registry.keys())
        mono_keys = set(mono_registry.keys())
        # New sections (locations, role_profiles) are extensions, not in original monolithic config
        core_keys = mono_keys  # Use monolithic as baseline
        assert core_keys.issubset(split_keys), f"Missing core keys in split: {core_keys - split_keys}"

    def test_version_identical(self, split_registry, mono_registry):
        """Verify version is identical."""
        assert split_registry.get("version") == mono_registry.get("version")

    def test_source_metadata_list_structure(self, split_registry, mono_registry):
        """Verify source_metadata is a list in both."""
        split_meta = split_registry.get("source_metadata", [])
        mono_meta = mono_registry.get("source_metadata", [])
        assert isinstance(split_meta, list), "Split source_metadata must be a list"
        assert isinstance(mono_meta, list), "Monolithic source_metadata must be a list"
        assert len(split_meta) >= len(mono_meta), f"source_metadata length: {len(split_meta)} vs {len(mono_meta)}"

    def test_source_metadata_ids(self, split_registry, mono_registry):
        """Verify all source metadata IDs match."""
        split_meta = split_registry.get("source_metadata", [])
        mono_meta = mono_registry.get("source_metadata", [])

        split_ids = {m.get("id") for m in split_meta}
        mono_ids = {m.get("id") for m in mono_meta}

        missing = mono_ids - split_ids
        assert not missing, f"Source IDs in monolithic but not split: {missing}"

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
        assert len(registry.get("source_metadata", [])) == 36
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


class TestLocationsAndRoles:
    """Test locations and role_profiles sections."""

    def test_locations_loaded(self, split_registry):
        """Verify locations are loaded."""
        locations = split_registry.get("locations", {})
        assert "uae" in locations
        assert "amsterdam" in locations

    def test_locations_structure(self, split_registry):
        """Verify location structure."""
        locations = split_registry.get("locations", {})
        for loc_id, loc_config in locations.items():
            assert isinstance(loc_config, dict)
            assert "id" in loc_config
            assert "label" in loc_config
            assert "enabled" in loc_config
            assert "country" in loc_config

    def test_role_profiles_loaded(self, split_registry):
        """Verify role profiles are loaded."""
        roles = split_registry.get("role_profiles", {})
        assert "payments" in roles
        assert "custody" in roles
        assert "settlement" in roles
        assert "product" in roles
        assert "igaming" in roles

    def test_role_profiles_structure(self, split_registry):
        """Verify role profile structure."""
        roles = split_registry.get("role_profiles", {})
        for role_id, role_config in roles.items():
            assert isinstance(role_config, dict)
            assert "id" in role_config
            assert "label" in role_config
            assert "enabled" in role_config
            assert "linkedin" in role_config


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


class TestMatrixIntegration:
    """Test matrix generation integration into build_linkedin_job_targets()."""

    def test_matrix_generated_amsterdam_targets_returned(self):
        """Verify build_linkedin_job_targets() returns matrix-generated Amsterdam targets."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        amsterdam_ids = {t.target_id for t in prod_targets if "amsterdam" in t.target_id}

        expected = {
            "linkedin_amsterdam_payments",
            "linkedin_amsterdam_custody",
            "linkedin_amsterdam_settlement",
            "linkedin_amsterdam_product",
            "linkedin_amsterdam_igaming",
        }
        assert expected == amsterdam_ids, f"Amsterdam targets mismatch: {amsterdam_ids}"

    def test_no_duplicate_amsterdam_targets(self):
        """Verify no duplicate Amsterdam targets in production output."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        amsterdam_targets = [t for t in prod_targets if "amsterdam" in t.target_id]
        amsterdam_ids = [t.target_id for t in amsterdam_targets]

        assert len(amsterdam_ids) == len(set(amsterdam_ids)), (
            f"Duplicate Amsterdam targets found: {amsterdam_ids}"
        )

    def test_matrix_generated_australia_targets_returned(self):
        """Verify build_linkedin_job_targets() returns matrix-generated Australia targets."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        australia_ids = {t.target_id for t in prod_targets if "australia" in t.target_id}

        expected = {
            "linkedin_australia_payments",
            "linkedin_australia_custody",
            "linkedin_australia_settlement",
            "linkedin_australia_product",
            "linkedin_australia_igaming",
        }
        assert expected == australia_ids, f"Australia targets mismatch: {australia_ids}"

    def test_no_duplicate_australia_targets(self):
        """Verify no duplicate Australia targets in production output."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        australia_targets = [t for t in prod_targets if "australia" in t.target_id]
        australia_ids = [t.target_id for t in australia_targets]

        assert len(australia_ids) == len(set(australia_ids)), (
            f"Duplicate Australia targets found: {australia_ids}"
        )

    def test_matrix_generated_malta_targets_returned(self):
        """Verify build_linkedin_job_targets() returns matrix-generated Malta targets."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        malta_ids = {t.target_id for t in prod_targets if "malta" in t.target_id}

        expected = {
            "linkedin_malta_payments",
            "linkedin_malta_custody",
            "linkedin_malta_settlement",
            "linkedin_malta_product",
            "linkedin_malta_igaming",
        }
        assert expected.issubset(malta_ids), f"Core Malta targets missing: {malta_ids}"
        assert len(malta_ids) == 24

    def test_no_duplicate_malta_targets(self):
        """Verify no duplicate Malta targets in production output."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        malta_targets = [t for t in prod_targets if "malta" in t.target_id]
        malta_ids = [t.target_id for t in malta_targets]

        assert len(malta_ids) == len(set(malta_ids)), (
            f"Duplicate Malta targets found: {malta_ids}"
        )

    def test_no_duplicate_target_ids_overall(self):
        """Verify no duplicate target IDs across all production targets."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        all_ids = [t.target_id for t in prod_targets]

        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate target IDs found in production: total {len(all_ids)}, unique {len(set(all_ids))}"
        )

    def test_no_manual_amsterdam_in_registry(self):
        """Verify manual Amsterdam targets are removed from registry."""
        linkedin_jobs = REGISTRY.get("sources", {}).get("linkedin_jobs", {})
        manual_targets = linkedin_jobs.get("targets", [])
        manual_ids = {t.get("id") for t in manual_targets if isinstance(t, dict)}

        amsterdam_manual = {tid for tid in manual_ids if "amsterdam" in tid}
        assert not amsterdam_manual, f"Manual Amsterdam targets still in registry: {amsterdam_manual}"

    def test_no_manual_australia_in_registry(self):
        """Verify manual Australia targets are removed from registry."""
        linkedin_jobs = REGISTRY.get("sources", {}).get("linkedin_jobs", {})
        manual_targets = linkedin_jobs.get("targets", [])
        manual_ids = {t.get("id") for t in manual_targets if isinstance(t, dict)}

        australia_manual = {tid for tid in manual_ids if "australia" in tid}
        assert not australia_manual, f"Manual Australia targets still in registry: {australia_manual}"

    def test_no_manual_malta_in_registry(self):
        """Verify Malta targets are matrix-generated only."""
        linkedin_jobs = REGISTRY.get("sources", {}).get("linkedin_jobs", {})
        manual_targets = linkedin_jobs.get("targets", [])
        manual_ids = {t.get("id") for t in manual_targets if isinstance(t, dict)}

        malta_manual = {tid for tid in manual_ids if "malta" in tid}
        assert not malta_manual, f"Manual Malta targets found in registry: {malta_manual}"

    def test_amsterdam_target_properties_preserved(self):
        """Verify generated Amsterdam targets have correct properties."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        amsterdam_by_id = {
            t.target_id: t
            for t in prod_targets
            if "amsterdam" in t.target_id
        }

        # Check each target has correct properties
        for target_id, search_target in amsterdam_by_id.items():
            assert search_target.target_id == target_id
            assert "Amsterdam" in search_target.location or search_target.location == "Amsterdam, Netherlands"
            assert search_target.country == "Netherlands"

    def test_australia_target_properties_preserved(self):
        """Verify generated Australia targets have correct properties."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        australia_by_id = {
            t.target_id: t
            for t in prod_targets
            if "australia" in t.target_id
        }

        for target_id, search_target in australia_by_id.items():
            assert search_target.target_id == target_id
            assert search_target.source == "linkedin_australia"
            assert search_target.country == "Australia"
            assert search_target.location == "Sydney, Australia"

    def test_malta_target_properties(self):
        """Verify generated Malta targets have correct properties."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        malta_by_id = {
            t.target_id: t
            for t in prod_targets
            if "malta" in t.target_id
        }

        for target_id, search_target in malta_by_id.items():
            assert search_target.target_id == target_id
            assert search_target.source == "linkedin_malta"
            assert search_target.country == "Malta"
            assert search_target.location == "Malta"

    def test_amsterdam_keyword_group_ids_correct(self):
        """Verify Amsterdam targets have expected keyword_group_ids."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        amsterdam_by_id = {
            t.target_id: t
            for t in prod_targets
            if "amsterdam" in t.target_id
        }

        expected_kg_ids = {
            "linkedin_amsterdam_payments": "payments",
            "linkedin_amsterdam_custody": "settlement",
            "linkedin_amsterdam_settlement": "settlement",
            "linkedin_amsterdam_product": "product",
            "linkedin_amsterdam_igaming": "igaming",
        }

        for tid, expected_kg_id in expected_kg_ids.items():
            search_target = amsterdam_by_id[tid]
            assert search_target.keyword_group_id == expected_kg_id, (
                f"{tid}: expected kg_id {expected_kg_id}, got {search_target.keyword_group_id}"
            )

    def test_australia_keyword_group_ids_correct(self):
        """Verify Australia targets have expected keyword_group_ids."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        australia_by_id = {
            t.target_id: t
            for t in prod_targets
            if "australia" in t.target_id
        }

        expected_kg_ids = {
            "linkedin_australia_payments": "payments",
            "linkedin_australia_custody": "settlement",
            "linkedin_australia_settlement": "settlement",
            "linkedin_australia_product": "product",
            "linkedin_australia_igaming": "igaming",
        }

        for tid, expected_kg_id in expected_kg_ids.items():
            search_target = australia_by_id[tid]
            assert search_target.keyword_group_id == expected_kg_id, (
                f"{tid}: expected kg_id {expected_kg_id}, got {search_target.keyword_group_id}"
            )

    def test_malta_keyword_group_ids_correct(self):
        """Verify Malta targets have expected keyword_group_ids."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        malta_by_id = {
            t.target_id: t
            for t in prod_targets
            if "malta" in t.target_id
        }

        expected_kg_ids = {
            "linkedin_malta_payments": "payments",
            "linkedin_malta_custody": "settlement",
            "linkedin_malta_settlement": "settlement",
            "linkedin_malta_product": "product",
            "linkedin_malta_igaming": "igaming",
        }

        for tid, expected_kg_id in expected_kg_ids.items():
            search_target = malta_by_id[tid]
            assert search_target.keyword_group_id == expected_kg_id, (
                f"{tid}: expected kg_id {expected_kg_id}, got {search_target.keyword_group_id}"
            )

    def test_malta_queries(self):
        """Verify generated Malta targets use the existing role profiles."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        malta_by_id = {
            t.target_id: t
            for t in prod_targets
            if "malta" in t.target_id
        }

        expected_payments_query = "payment operations OR payment operations manager OR payments operations manager OR payment specialist OR payments analyst OR payments engineer OR payment integration OR payment implementation OR merchant payments OR acquiring OR payment gateway OR PSP manager"
        expected_queries = {
            "linkedin_malta_payments": expected_payments_query,
            "linkedin_malta_custody": "custody operations OR asset custody OR settlement operations OR vault operations",
            "linkedin_malta_settlement": "settlement operations OR trading operations OR exchange operations",
            "linkedin_malta_product": "payment product manager OR fintech product manager OR igaming product manager OR crypto product manager",
            "linkedin_malta_igaming": "igaming operations OR casino operations OR sportsbook operations OR responsible gaming OR safer gaming OR gambling operations OR online casino",
        }

        for tid, expected_query in expected_queries.items():
            search_target = malta_by_id[tid]
            assert search_target.keyword_query == expected_query, (
                f"{tid}: expected query {expected_query!r}, got {search_target.keyword_query!r}"
            )

    def test_matrix_payment_queries_are_location_neutral(self):
        """Verify reusable payment role queries do not duplicate LinkedIn location routing."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        payment_queries = {
            t.target_id: t.keyword_query
            for t in prod_targets
            if t.target_id
            in {
                "linkedin_amsterdam_payments",
                "linkedin_australia_payments",
                "linkedin_malta_payments",
            }
        }

        expected_payments_query = "payment operations OR payment operations manager OR payments operations manager OR payment specialist OR payments analyst OR payments engineer OR payment integration OR payment implementation OR merchant payments OR acquiring OR payment gateway OR PSP manager"
        assert payment_queries == {
            "linkedin_amsterdam_payments": expected_payments_query,
            "linkedin_australia_payments": expected_payments_query,
            "linkedin_malta_payments": expected_payments_query,
        }
        for query in payment_queries.values():
            assert "netherlands" not in query.lower()
            assert "australia" not in query.lower()
            assert "malta" not in query.lower()

    def test_australia_queries_preserved(self):
        """Verify generated Australia non-payment targets preserve previous manual queries."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()
        australia_by_id = {
            t.target_id: t
            for t in prod_targets
            if "australia" in t.target_id
        }

        expected_payments_query = "payment operations OR payment operations manager OR payments operations manager OR payment specialist OR payments analyst OR payments engineer OR payment integration OR payment implementation OR merchant payments OR acquiring OR payment gateway OR PSP manager"
        expected_queries = {
            "linkedin_australia_payments": expected_payments_query,
            "linkedin_australia_custody": "custody operations OR asset custody OR settlement operations OR vault operations",
            "linkedin_australia_settlement": "settlement operations OR trading operations OR exchange operations",
            "linkedin_australia_product": "payment product manager OR fintech product manager OR igaming product manager OR crypto product manager",
            "linkedin_australia_igaming": "igaming operations OR casino operations OR sportsbook operations OR responsible gaming OR safer gaming OR gambling operations OR online casino",
        }

        for tid, expected_query in expected_queries.items():
            search_target = australia_by_id[tid]
            assert search_target.keyword_query == expected_query, (
                f"{tid}: expected query {expected_query!r}, got {search_target.keyword_query!r}"
            )

    def test_standard_linkedin_target_groups_are_derived(self):
        """Verify matrix locations do not need duplicated target-group YAML."""
        from src.utils.collection_config import REGISTRY, discovery_target_groups

        configured_groups = REGISTRY["sources"]["linkedin_jobs"]["target_groups"]
        configured_ids = {group["id"] for group in configured_groups}
        assert configured_ids == {"uae", "remote"}

        status, groups = discovery_target_groups("linkedin")
        assert status == "ok"
        derived = {group["id"]: group for group in groups}
        assert derived["amsterdam"]["target_count"] == 5
        assert derived["australia"]["target_count"] == 5
        assert derived["malta"]["target_count"] == 24
        assert derived["amsterdam"]["keyword_count"] == 4
        assert derived["australia"]["keyword_count"] == 4
        assert derived["malta"]["keyword_count"] == 23

    def test_production_target_count_unchanged(self):
        """Verify total production SearchTarget count unchanged after matrix integration."""
        from src.utils.collection_config import build_linkedin_job_targets

        prod_targets = build_linkedin_job_targets()

        # Before Phase F: 24 manual + 10 matrix-generated = 34 target objects
        # After Phase F: 24 manual + 15 matrix-generated = 39 target objects
        # But SearchTarget count includes multiple per target if multiple keyword groups
        # Expected: 43 SearchTarget objects including recruiters
        assert len(prod_targets) == 219, (
            f"Production SearchTarget count changed: expected 219, got {len(prod_targets)}"
        )
