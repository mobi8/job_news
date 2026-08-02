#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from utils.collection_config import phase_registry, resolve_phase_id, validate_phase_registry
from watch.phase_runner import validate_phase_handlers


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
