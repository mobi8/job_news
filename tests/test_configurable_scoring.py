#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from utils.scoring import (
    active_search_location_terms,
    evaluate_fit,
    evaluate_fit_legacy,
    load_scoring_config,
)
from utils.notifications import cap_telegram_recommendations


RESUME_TEXT = "payments igaming crypto account management product operations implementation"


def _record(title: str, company: str, location: str, source: str, description: str = "") -> dict:
    return {
        "source": source,
        "source_job_id": f"{source}|{company}|{title}",
        "title": title,
        "company": company,
        "location": location,
        "description": description,
        "url": "https://www.linkedin.com/jobs/view/test/",
        "remote": False,
    }


def test_scoring_config_keeps_minimum_score_at_30():
    assert load_scoring_config()["minimum_score"] == 30


@pytest.mark.parametrize(
    "record",
    [
        _record("Senior Backend Engineer - Cloud", "Tech Corp", "Dubai, UAE", "linkedin_public"),
        _record("Office Assistant", "TechCorp", "Dubai, UAE", "indeed_uae"),
        _record("Customer Service Representative", "GenericCo", "Remote", "linkedin_emea"),
    ],
)
def test_configurable_scoring_preserves_existing_core_examples(record):
    old = evaluate_fit_legacy(record, RESUME_TEXT)
    new = evaluate_fit(record, RESUME_TEXT)
    assert new["score"] == old["score"]
    assert new["qualifies"] == old["qualifies"]


@pytest.mark.parametrize(
    "record",
    [
        _record("Manager, Technical Account Management", "Stripe", "Dublin, Ireland", "linkedin_ireland", "Payments infrastructure and financial technology platform."),
        _record("Payments Orchestration Specialist", "FYST", "Lithuania", "linkedin_lithuania"),
        _record("Solutions Architect - Payments", "Airwallex", "Sydney, Australia", "linkedin_australia"),
        _record("Regulatory Compliance Manager (Crypto)", "Revolut", "Spain", "linkedin_spain"),
        _record("Payments Contract Specialist", "PGWAY", "Lisbon, Portugal", "linkedin_portugal"),
        _record("Senior Technical Account Manager - Payments", "Airwallex", "London, United Kingdom", "linkedin_united_kingdom"),
        _record("VIP Account Manager Greek Speaker", "SkillOnNet", "Limassol, Cyprus", "linkedin_cyprus", "Online casino and iGaming operator."),
        _record("Partnerships Manager", "payabl.", "Vilnius, Lithuania", "linkedin_lithuania", "Payments and acquiring partnerships."),
        _record("Account Manager - RNG", "Evolution", "St Julian's, Malta", "linkedin_malta", "Live casino and gaming provider."),
    ],
)
def test_taxonomy_false_negatives_reach_threshold(record):
    fit = evaluate_fit(record, RESUME_TEXT)
    assert fit["score"] >= 30
    assert fit["qualifies"] is True
    assert fit["components"]


@pytest.mark.parametrize(
    "record",
    [
        _record("Graphic Designer", "CKC Technologies", "Dubai, UAE", "indeed_uae"),
        _record("General Manager", "Moxy Hotels", "Nottingham, United Kingdom", "linkedin_united_kingdom"),
        _record("Account manager", "Travelport", "Lisbon, Portugal", "linkedin_portugal"),
        _record("Customer Success Manager", "Generic SaaS", "Ireland", "linkedin_ireland"),
        _record("Marketing Manager", "Generic Agency", "Malta", "linkedin_malta"),
        _record("Senior AI Compute Infrastructure Engineer", "Kraken", "Lithuania", "linkedin_lithuania"),
        _record("Account Manager - Fund Accounting", "Apex Group Ltd", "Malta", "linkedin_malta"),
        _record("Senior Software Engineer", "Pentasia", "Malta", "linkedin_malta"),
        _record("Senior Voice Engineer", "Pentasia", "Malta", "linkedin_malta"),
        _record("Lead Generation Specialist (Africa) - Senior", "SOFTSWISS", "Cyprus", "linkedin_cyprus"),
        _record("Account Manager - Marine/Oilfield After-Sales Experience Required", "3S group", "Dubai, UAE", "indeed_uae", "Payment terms appear only in a generic benefits description."),
        _record("Business Consultant / Account Manager", "Property Finder", "Dubai, UAE", "indeed_uae", "CRM, reconciliation, and payment administration for real estate advertisers."),
        _record("Field Sales Engineer II", "Alfa Laval", "Dubai, UAE", "indeed_uae", "Solutions engineer for industrial equipment."),
        _record("Affiliate Manager", "CKC Technologies", "Dubai, UAE", "indeed_uae", "Generic crypto and fintech content in a company description."),
        _record("Payments and Credit Control Manager", "Pimlico Plumbers", "London, United Kingdom", "linkedin_united_kingdom"),
        _record("Cash Management Specialist", "Saint-Gobain UK & Ireland", "London, United Kingdom", "linkedin_united_kingdom"),
        _record("Consulting AI Architect - Banking and Financial Services", "NTT DATA", "Dubai, UAE", "indeed_uae", "Generic consulting profile mentions payment transformation."),
    ],
)
def test_broad_or_generic_negative_controls_stay_below_threshold(record):
    fit = evaluate_fit(record, RESUME_TEXT)
    assert fit["score"] < 30
    assert fit["qualifies"] is False


def test_active_scoring_locations_are_derived_from_collection_locations():
    terms = set(active_search_location_terms())
    assert "united kingdom" in terms
    assert "uk" in terms
    assert "london" in terms
    assert "ireland" in terms
    assert "portugal" in terms
    assert "amsterdam" in terms


def test_scoring_yaml_separates_igaming_and_video_games_domains():
    config = load_scoring_config()
    strong_terms = set(config["domain_groups"]["strong"].get("terms") or [])
    igaming_terms = set(config["domain_groups"]["igaming"]["terms"])
    video_game_terms = set(config["domain_groups"]["video_games"]["terms"])
    assert {"game", "games", "gaming"}.isdisjoint(strong_terms)
    assert "igaming" in igaming_terms
    assert "game producer" in video_game_terms
    assert "gaming" not in igaming_terms


@pytest.mark.parametrize(
    ("domain", "role", "record"),
    [
        ("payments", "technical_account", _record("Manager, Technical Account Management", "Stripe", "Dublin, Ireland", "linkedin_ireland", "Payments infrastructure.")),
        ("payments", "implementation_integration", _record("Solutions Architect - Payments", "Airwallex", "Sydney, Australia", "linkedin_australia")),
        ("payments", "operations", _record("Payments Orchestration Specialist", "FYST", "Lithuania", "linkedin_lithuania")),
        ("payments", "operations", _record("Senior / Lead Consultant (m/f/d) - SAP Payment Central", "SAP Fioneer", "London, United Kingdom", "linkedin_united_kingdom")),
        ("payments", "operations", _record("Payment Systems Supervision Specialist", "Payment Systems Regulator", "London, United Kingdom", "linkedin_united_kingdom")),
        ("payments", "operations", _record("Head of Payment Network Development & Oversight", "Convera", "London, United Kingdom", "linkedin_united_kingdom")),
        ("payments", "implementation_integration", _record("Application Support Specialist - Payment Network", "HCLTech", "Portugal", "linkedin_portugal")),
        ("payments", "treasury_settlement", _record("Cash Management & Payments Specialist (m/f/d)", "Siemens", "Lisbon, Portugal", "linkedin_portugal")),
        ("payments", "partnerships", _record("Partnerships Manager", "payabl.", "Vilnius, Lithuania", "linkedin_lithuania", "Payments and acquiring partnerships.")),
        ("payments", "partnerships", _record("Senior Business Growth Manager", "payabl.", "London, United Kingdom", "linkedin_united_kingdom", "Payments acquiring and merchant growth.")),
        ("crypto", "account_manager", _record("Relationship Manager (Digital Asset Banking)", "EPS Consultants Singapore", "Dubai, UAE", "linkedin_public")),
        ("crypto", "operations", _record("Operations Senior Associate", "Coinbase", "London, United Kingdom", "linkedin_united_kingdom", "Crypto exchange operations and blockchain asset workflows.")),
        ("crypto", "compliance_risk", _record("Regulatory Compliance Manager (Crypto)", "Revolut", "Spain", "linkedin_spain")),
        ("digital_assets", "custody_wallet", _record("Custody Operations Specialist", "Coinbase", "Ireland", "linkedin_ireland", "Digital asset custody operations.")),
        ("igaming", "account_manager", _record("VIP Account Manager Greek Speaker", "SkillOnNet", "Limassol, Cyprus", "linkedin_cyprus", "Online casino operator.")),
        ("igaming", "compliance_risk", _record("Senior Product Compliance Manager", "ARRISE", "Sliema, Malta", "linkedin_malta")),
        ("igaming", "compliance_risk", _record("Product Compliance Manager", "Pentasia", "Valletta, Malta", "linkedin_malta")),
        ("igaming", "compliance_risk", _record("Product Compliance Manager", "ARRISE", "Dubai, UAE", "jobvite_pragmaticplay", "iGaming and casino product compliance.")),
        ("igaming", "account_manager", _record("Account Manager", "TPF", "Cyprus", "linkedin_cyprus", "iGaming operator account management.")),
        ("video_games", "product", _record("Product Lead - Portfolio Midcore Games", "Voodoo", "Amsterdam, Netherlands", "linkedin_amsterdam")),
        ("video_games", "product", _record("Game Producer - Slots", "Art of Spin", "Malta", "linkedin_malta")),
        ("video_games", "operations", _record("Games Delivery Manager", "LeoVegas Group", "Sliema, Malta", "linkedin_malta")),
    ],
)
def test_domain_role_positive_matrix_reaches_threshold(domain, role, record):
    fit = evaluate_fit(record, RESUME_TEXT)
    assert fit["score"] >= 30, (domain, role, fit)
    assert fit["qualifies"] is True
    assert fit["components"]


@pytest.mark.parametrize(
    "record",
    [
        _record("Game QA Tester", "Platin Gaming Ltd.", "Malta", "linkedin_malta"),
        _record("Community Manager", "NetEase Games", "Nottingham, United Kingdom", "linkedin_united_kingdom"),
        _record("HR Manager", "Voodoo", "Portugal", "linkedin_portugal"),
        _record("Game Designer", "Generic Studio", "Australia", "linkedin_australia"),
        _record("Unity Game Developer", "Skylink Studio", "Vietnam", "linkedin_emea"),
    ],
)
def test_video_games_negative_controls_stay_below_threshold(record):
    fit = evaluate_fit(record, RESUME_TEXT)
    assert fit["score"] < 30
    assert fit["qualifies"] is False


def test_score_components_identify_signal_fields():
    fit = evaluate_fit(
        _record("Product Compliance Manager", "ARRISE", "Sliema, Malta", "linkedin_malta"),
        RESUME_TEXT,
    )
    assert any(component["rule_id"] == "company.igaming" and component["field"] == "company" for component in fit["components"])
    assert any(component["rule_id"].startswith("intent.") and component["field"] == "title_description_source" for component in fit["components"])


def test_company_context_alone_cannot_qualify():
    fit = evaluate_fit(
        _record("Senior Software Engineer", "Pentasia", "Malta", "linkedin_malta"),
        RESUME_TEXT,
    )
    assert fit["company_group_matches"] == {"igaming": ["Pentasia"]}
    assert fit["score"] < 30
    assert fit["qualifies"] is False
    assert any(component["rule_id"] == "penalty.company_context_without_role_intent" for component in fit["components"])


def test_broad_role_requires_title_or_description_domain_signal():
    fit = evaluate_fit(
        _record(
            "Account Manager",
            "Property Finder",
            "Dubai, UAE",
            "indeed_uae",
            "Real-estate advertiser reconciliation and payment administration.",
        ),
        RESUME_TEXT,
    )
    assert fit["qualifies"] is False
    assert any(component["rule_id"] in {"penalty.broad_role_without_title_description_domain", "penalty.generic_payment_broad_noise"} for component in fit["components"])


def test_telegram_recommendations_are_capped_and_diversified():
    jobs = []
    for idx in range(12):
        jobs.append({"title": f"Payments Role {idx}", "company": "MegaPay", "country": "United Kingdom", "source": "linkedin_united_kingdom", "match_score": 100 - idx, "url": f"https://example.com/uk/{idx}"})
    for idx in range(12):
        jobs.append({"title": f"iGaming Role {idx}", "company": f"Casino {idx}", "country": "Malta", "source": "linkedin_malta", "match_score": 90 - idx, "url": f"https://example.com/mt/{idx}"})
    capped = cap_telegram_recommendations(jobs)
    assert len(capped) <= 30
    assert sum(1 for job in capped if job["country"] == "United Kingdom") <= 8
    assert sum(1 for job in capped if job["company"] == "MegaPay") <= 3
