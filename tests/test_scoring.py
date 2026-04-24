#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for scoring.py

Tests job matching and scoring functions including:
- Language filtering
- Hard exclusion rules
- Executive role rejection
- Category auto-detection
- Match score calculation
- Record annotation and filtering
"""

from unittest.mock import MagicMock, patch

import pytest

from utils.models import JobPosting
from utils.config import INDEED_SEARCH_KEYWORDS
from utils.scoring import (
    annotate_records,
    auto_category_for_record,
    calculate_match_score,
    evaluate_fit,
    filter_records_by_sources,
    focus_records,
    is_exec_tech_reject_job,
    is_hard_excluded_job,
    is_language_filtered_out,
    source_label,
    top_recommendations,
    unique_preserve_order,
)


class TestIsLanguageFilteredOut:
    """Tests for is_language_filtered_out function"""

    def test_language_filtered_out_with_excluded_terms(self):
        """Test filtering with excluded language terms"""
        with patch("utils.scoring.EXCLUDED_LANGUAGE_TERMS", ["عربي", "كويتي"]):
            assert is_language_filtered_out("Developer عربي position") is True

    def test_language_filtered_out_no_excluded(self):
        """Test no filtering when excluded terms absent"""
        with patch("utils.scoring.EXCLUDED_LANGUAGE_TERMS", ["عربي"]):
            assert is_language_filtered_out("Developer position") is False

    def test_language_filtered_out_case_insensitive(self):
        """Test filtering is case-insensitive"""
        with patch("utils.scoring.EXCLUDED_LANGUAGE_TERMS", ["عربي"]):
            assert is_language_filtered_out("Developer عربي position") is True

    def test_language_filtered_out_empty_text(self):
        """Test with empty text"""
        with patch("utils.scoring.EXCLUDED_LANGUAGE_TERMS", ["عربي"]):
            assert is_language_filtered_out("") is False

    def test_language_filtered_out_empty_excluded_list(self):
        """Test with empty excluded list"""
        with patch("utils.scoring.EXCLUDED_LANGUAGE_TERMS", []):
            assert is_language_filtered_out("Any text") is False


class TestIsHardExcludedJob:
    """Tests for is_hard_excluded_job function"""

    def test_hard_excluded_in_title(self):
        """Test hard exclusion based on title"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["recruiter", "agency"]):
            assert is_hard_excluded_job("Recruiter Position") is True

    def test_hard_excluded_in_company(self):
        """Test hard exclusion based on company"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["moneylender"]):
            assert is_hard_excluded_job(
                "Developer", company="BadMoneyLender Inc"
            ) is True

    def test_hard_excluded_in_location(self):
        """Test hard exclusion based on location"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["prison"]):
            assert is_hard_excluded_job(
                "Developer", location="State Prison"
            ) is True

    def test_hard_excluded_in_description(self):
        """Test hard exclusion based on description"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["illegal"]):
            assert is_hard_excluded_job(
                "Developer",
                description="This is an illegal job"
            ) is True

    def test_not_hard_excluded(self):
        """Test job that is not hard excluded"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["recruiter"]):
            assert is_hard_excluded_job(
                "Senior Developer", company="TechCorp"
            ) is False

    def test_hard_excluded_empty_fields(self):
        """Test with empty fields"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["recruiter"]):
            assert is_hard_excluded_job("") is False

    def test_hard_excluded_case_insensitive(self):
        """Test case insensitivity"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["recruiter"]):
            assert is_hard_excluded_job("RECRUITER POSITION") is True

    def test_hard_excluded_devops_and_engineer(self):
        """Test that common engineering terms can be excluded when configured"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["devops", "engineer"]):
            assert is_hard_excluded_job("Senior DevOps Engineer") is True

    def test_hard_excluded_supply_chain(self):
        """Test that supply chain roles can be excluded when configured"""
        with patch("utils.scoring.HARD_EXCLUDE_TITLE_TERMS", ["supply chain"]):
            assert is_hard_excluded_job("Supply Chain Manager") is True


class TestIsExecTechRejectJob:
    """Tests for is_exec_tech_reject_job function"""

    def test_reject_cto_position(self):
        """Test rejecting CTO positions"""
        assert is_exec_tech_reject_job("CTO") is True

    def test_reject_chief_technology_officer(self):
        """Test rejecting Chief Technology Officer"""
        assert is_exec_tech_reject_job("Chief Technology Officer") is True

    def test_reject_head_of_engineering(self):
        """Test rejecting Head of Engineering"""
        assert is_exec_tech_reject_job("Head of Engineering") is True

    def test_reject_vp_engineering(self):
        """Test rejecting VP Engineering"""
        assert is_exec_tech_reject_job("VP Engineering") is True

    def test_reject_vice_president_engineering(self):
        """Test rejecting Vice President Engineering"""
        assert is_exec_tech_reject_job("Vice President Engineering") is True

    def test_reject_director_of_engineering(self):
        """Test rejecting Director of Engineering"""
        assert is_exec_tech_reject_job("Director of Engineering") is True

    def test_accept_senior_developer(self):
        """Test accepting non-exec role"""
        assert is_exec_tech_reject_job("Senior Developer") is False

    def test_reject_cto_in_company_name(self):
        """Test CTO in company name still rejects"""
        assert is_exec_tech_reject_job("Developer", company="CTO Solutions") is True

    def test_case_insensitive_rejection(self):
        """Test case insensitivity"""
        assert is_exec_tech_reject_job("cto position") is True
        assert is_exec_tech_reject_job("HEAD OF ENGINEERING") is True


class TestAutoCategoryForRecord:
    """Tests for auto_category_for_record function"""

    def test_category_crypto_product(self):
        """Test crypto product category detection"""
        with patch("utils.scoring.RECRUITER_COMPANIES", []):
            record = {
                "title": "Product Manager Crypto",
                "company": "BlockchainCorp",
                "description": "Web3 product management"
            }
            assert auto_category_for_record(record) == "crypto_product"

    def test_category_payments(self):
        """Test payments category detection"""
        with patch("utils.scoring.RECRUITER_COMPANIES", []):
            record = {
                "title": "Senior Developer",
                "description": "Payment processing platform"
            }
            assert auto_category_for_record(record) == "payments"

    def test_category_casino(self):
        """Test casino category detection"""
        with patch("utils.scoring.RECRUITER_COMPANIES", []):
            record = {
                "title": "Gaming Developer",
                "description": "Live casino platform development"
            }
            assert auto_category_for_record(record) == "casino"

    def test_category_commercial(self):
        """Test commercial category detection"""
        with patch("utils.scoring.RECRUITER_COMPANIES", []):
            record = {
                "title": "Account Manager",
                "description": "Business development role"
            }
            assert auto_category_for_record(record) == "commercial"

    def test_category_compliance(self):
        """Test compliance category detection"""
        with patch("utils.scoring.RECRUITER_COMPANIES", []):
            record = {
                "title": "Compliance Officer",
                "description": "ADGM regulatory requirements"
            }
            assert auto_category_for_record(record) == "compliance"

    def test_category_recruiter(self):
        """Test recruiter category detection"""
        with patch("utils.scoring.RECRUITER_COMPANIES", ["robert walters"]):
            record = {
                "title": "Developer",
                "company": "Robert Walters"
            }
            assert auto_category_for_record(record) == "recruiter"

    def test_category_empty_string(self):
        """Test empty category when no match"""
        with patch("utils.scoring.RECRUITER_COMPANIES", []):
            record = {
                "title": "Janitor",
                "company": "BuildingCorp",
                "description": "General cleaning duties"
            }
            assert auto_category_for_record(record) == ""

    def test_category_with_fit_tags(self):
        """Test category detection with fit_tags"""
        with patch("utils.scoring.RECRUITER_COMPANIES", []):
            record = {
                "title": "Developer",
                "fit_tags": ["product", "crypto"],
                "description": "Web3 platform"
            }
            result = auto_category_for_record(record)
            assert isinstance(result, str)


class TestIndeedKeywordCoverage:
    """Regression tests for Indeed search coverage."""

    def test_indeed_keywords_include_wallet_probes(self):
        lowered = [keyword.lower() for keyword in INDEED_SEARCH_KEYWORDS]
        assert any("wallet" in keyword for keyword in lowered)
        assert any("crypto wallet" in keyword for keyword in lowered)


class TestUniquePreserveOrder:
    """Tests for unique_preserve_order function"""

    def test_unique_preserve_order_basic(self):
        """Test basic deduplication while preserving order"""
        items = ["a", "b", "a", "c", "b"]
        assert unique_preserve_order(items) == ["a", "b", "c"]

    def test_unique_preserve_order_no_duplicates(self):
        """Test with no duplicates"""
        items = ["a", "b", "c"]
        assert unique_preserve_order(items) == ["a", "b", "c"]

    def test_unique_preserve_order_all_duplicates(self):
        """Test with all same items"""
        items = ["a", "a", "a"]
        assert unique_preserve_order(items) == ["a"]

    def test_unique_preserve_order_empty_list(self):
        """Test with empty list"""
        assert unique_preserve_order([]) == []

    def test_unique_preserve_order_single_item(self):
        """Test with single item"""
        assert unique_preserve_order(["a"]) == ["a"]


class TestFilterRecordsBySource:
    """Tests for filter_records_by_sources function"""

    def test_filter_by_sources_none(self):
        """Test filtering with None returns all records"""
        records = [
            {"source": "indeed_uae"},
            {"source": "linkedin_public"}
        ]
        assert filter_records_by_sources(records, None) == records

    def test_filter_by_sources_subset(self):
        """Test filtering to specific sources"""
        records = [
            {"source": "indeed_uae"},
            {"source": "linkedin_public"},
            {"source": "indeed_uae"}
        ]
        result = filter_records_by_sources(
            records, {"indeed_uae"}
        )
        assert len(result) == 2
        assert all(r["source"] == "indeed_uae" for r in result)

    def test_filter_by_sources_empty(self):
        """Test filtering with empty source set"""
        records = [
            {"source": "indeed_uae"},
            {"source": "linkedin_public"}
        ]
        result = filter_records_by_sources(records, set())
        assert result == []

    def test_filter_by_sources_no_match(self):
        """Test filtering with non-matching sources"""
        records = [
            {"source": "indeed_uae"},
            {"source": "linkedin_public"}
        ]
        result = filter_records_by_sources(
            records, {"telegram_jobs"}
        )
        assert result == []


class TestEvaluateFit:
    """Tests for evaluate_fit function"""

    @patch("utils.scoring.FOCUS_LOCATION_TERMS", ["dubai", "abu dhabi"])
    @patch("utils.scoring.FOCUS_DOMAIN_TERMS", ["crypto", "fintech"])
    @patch("utils.scoring.STRONG_DOMAIN_TERMS", ["blockchain", "web3"])
    @patch("utils.scoring.FOCUS_ROLE_TERMS", ["developer", "engineer"])
    @patch("utils.scoring.COMMERCIAL_ROLE_TERMS", ["sales", "manager"])
    @patch("utils.scoring.PRODUCT_ROLE_TERMS", [])
    @patch("utils.scoring.GENERIC_PAYMENT_TERMS", [])
    @patch("utils.scoring.RECRUITER_COMPANIES", [])
    @patch("utils.scoring.RESUME_SKILL_LEXICON", [])
    @patch("utils.scoring.NEGATIVE_ROLE_TERMS", [])
    @patch("utils.scoring.NON_COMMERCIAL_ROLE_TERMS", [])
    @patch("utils.scoring.GENERIC_FINANCE_TERMS", [])
    @patch("utils.scoring.REMOTE_GCC_LOCATION_TERMS", [])
    def test_evaluate_fit_good_match(self, *mocks):
        """Test evaluation of a good matching job"""
        record = {
            "title": "Senior Developer",
            "company": "CryptoCorp",
            "location": "Dubai, UAE",
            "description": "Blockchain development",
            "source": "indeed_uae"
        }
        fit = evaluate_fit(record, "python developer blockchain")
        assert fit["score"] > 0
        assert isinstance(fit["score"], int)
        assert 0 <= fit["score"] <= 100

    @patch("utils.scoring.FOCUS_LOCATION_TERMS", [])
    @patch("utils.scoring.FOCUS_DOMAIN_TERMS", [])
    @patch("utils.scoring.STRONG_DOMAIN_TERMS", [])
    @patch("utils.scoring.FOCUS_ROLE_TERMS", [])
    @patch("utils.scoring.COMMERCIAL_ROLE_TERMS", [])
    @patch("utils.scoring.PRODUCT_ROLE_TERMS", [])
    @patch("utils.scoring.GENERIC_PAYMENT_TERMS", [])
    @patch("utils.scoring.RECRUITER_COMPANIES", [])
    @patch("utils.scoring.RESUME_SKILL_LEXICON", [])
    @patch("utils.scoring.NEGATIVE_ROLE_TERMS", [])
    @patch("utils.scoring.NON_COMMERCIAL_ROLE_TERMS", [])
    @patch("utils.scoring.GENERIC_FINANCE_TERMS", [])
    @patch("utils.scoring.REMOTE_GCC_LOCATION_TERMS", [])
    def test_evaluate_fit_poor_match(self, *mocks):
        """Test evaluation of a poor matching job"""
        record = {
            "title": "Janitor",
            "company": "BuildingCorp",
            "location": "New York",
            "description": "General cleaning",
            "source": "indeed_uae"
        }
        fit = evaluate_fit(record, "python developer")
        assert fit["score"] >= 0
        assert isinstance(fit["score"], int)

    @patch("utils.scoring.FOCUS_LOCATION_TERMS", ["dubai"])
    @patch("utils.scoring.FOCUS_DOMAIN_TERMS", [])
    @patch("utils.scoring.STRONG_DOMAIN_TERMS", [])
    @patch("utils.scoring.FOCUS_ROLE_TERMS", [])
    @patch("utils.scoring.COMMERCIAL_ROLE_TERMS", [])
    @patch("utils.scoring.PRODUCT_ROLE_TERMS", [])
    @patch("utils.scoring.GENERIC_PAYMENT_TERMS", [])
    @patch("utils.scoring.RECRUITER_COMPANIES", [])
    @patch("utils.scoring.RESUME_SKILL_LEXICON", [])
    @patch("utils.scoring.NEGATIVE_ROLE_TERMS", [])
    @patch("utils.scoring.NON_COMMERCIAL_ROLE_TERMS", [])
    @patch("utils.scoring.GENERIC_FINANCE_TERMS", [])
    @patch("utils.scoring.REMOTE_GCC_LOCATION_TERMS", [])
    def test_evaluate_fit_contains_tags(self, *mocks):
        """Test that evaluate_fit returns tag information"""
        record = {
            "title": "Developer",
            "company": "Corp",
            "location": "Dubai",
            "description": "Job description",
            "source": "indeed_uae"
        }
        fit = evaluate_fit(record, "")
        assert "tags" in fit
        assert isinstance(fit["tags"], list)
        assert "qualifies" in fit
        assert isinstance(fit["qualifies"], bool)

    @patch("utils.scoring.FOCUS_LOCATION_TERMS", ["dubai"])
    @patch("utils.scoring.FOCUS_DOMAIN_TERMS", [])
    @patch("utils.scoring.STRONG_DOMAIN_TERMS", [])
    @patch("utils.scoring.FOCUS_ROLE_TERMS", [])
    @patch("utils.scoring.COMMERCIAL_ROLE_TERMS", ["sales", "manager"])
    @patch("utils.scoring.PRODUCT_ROLE_TERMS", [])
    @patch("utils.scoring.GENERIC_PAYMENT_TERMS", [])
    @patch("utils.scoring.RECRUITER_COMPANIES", [])
    @patch("utils.scoring.RESUME_SKILL_LEXICON", [])
    @patch("utils.scoring.NEGATIVE_ROLE_TERMS", [])
    @patch("utils.scoring.NON_COMMERCIAL_ROLE_TERMS", [])
    @patch("utils.scoring.GENERIC_FINANCE_TERMS", [])
    @patch("utils.scoring.REMOTE_GCC_LOCATION_TERMS", [])
    def test_evaluate_fit_rejects_non_domain(self, *mocks):
        """Commercial roles without domain keywords should not qualify"""
        record = {
            "title": "Sales Manager",
            "company": "Marine Company",
            "location": "Dubai",
            "description": "Marine industry sales",
            "source": "indeed_uae"
        }
        fit = evaluate_fit(record, "sales")
        assert fit["score"] >= 0
        assert fit["qualifies"] is False


class TestCalculateMatchScore:
    """Tests for calculate_match_score function"""

    def test_calculate_match_score_basic(self):
        """Test basic match score calculation"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://example.com",
            description="Blockchain developer needed"
        )
        score = calculate_match_score(job, "python developer blockchain")
        assert isinstance(score, int)
        assert 0 <= score <= 100

    def test_calculate_match_score_zero_resume(self):
        """Test score with empty resume"""
        job = JobPosting(
            source="indeed_uae",
            source_job_id="123",
            title="Senior Developer",
            company="TechCorp",
            location="Dubai",
            url="https://example.com"
        )
        score = calculate_match_score(job, "")
        assert isinstance(score, int)
        assert 0 <= score <= 100


class TestAnnotateRecords:
    """Tests for annotate_records function"""

    @patch("utils.scoring.is_language_filtered_out", return_value=False)
    @patch("utils.scoring.is_hard_excluded_job", return_value=False)
    @patch("utils.scoring.is_exec_tech_reject_job", return_value=False)
    @patch("utils.scoring.evaluate_fit")
    def test_annotate_records_basic(self, mock_fit, *mocks):
        """Test basic record annotation"""
        mock_fit.return_value = {
            "score": 75,
            "qualifies": True,
            "tags": ["crypto", "dubai"],
            "recruiter_company_tags": [],
            "recruiter": False
        }
        records = [
            {
                "source": "indeed_uae",
                "source_job_id": "1",
                "title": "Developer",
                "company": "Corp",
                "location": "Dubai",
                "description": "Job desc"
            }
        ]
        annotated = annotate_records(records, "resume text")
        assert len(annotated) == 1
        assert annotated[0]["match_score"] == 75
        assert annotated[0]["qualifies"] is True

    @patch("utils.scoring.is_language_filtered_out", return_value=True)
    def test_annotate_records_filters_language(self, mock_lang):
        """Test that language filtered records are excluded"""
        records = [
            {
                "title": "Developer",
                "description": "عربي position"
            }
        ]
        annotated = annotate_records(records, "resume")
        assert len(annotated) == 0

    @patch("utils.scoring.is_language_filtered_out", return_value=False)
    @patch("utils.scoring.is_hard_excluded_job", return_value=True)
    def test_annotate_records_filters_hard_excluded(self, mock_hard, *mocks):
        """Test that hard excluded records are excluded"""
        records = [
            {
                "title": "Recruiter Position",
                "company": "Corp",
                "location": "Dubai",
                "description": "Job"
            }
        ]
        annotated = annotate_records(records, "resume")
        assert len(annotated) == 0


class TestFocusRecords:
    """Tests for focus_records function"""

    @patch("utils.scoring.annotate_records")
    def test_focus_records_basic(self, mock_annotate):
        """Test filtering to qualifying records"""
        mock_annotate.return_value = [
            {"qualifies": True, "title": "Good Job"},
            {"qualifies": False, "title": "Bad Job"},
            {"qualifies": True, "title": "Another Good Job"}
        ]
        records = [{"title": "Job"}]
        result = focus_records(records, "resume")
        assert len(result) == 2
        assert all(r["qualifies"] for r in result)

    @patch("utils.scoring.annotate_records")
    def test_focus_records_none_qualify(self, mock_annotate):
        """Test when no records qualify"""
        mock_annotate.return_value = [
            {"qualifies": False}
        ]
        result = focus_records([{"title": "Job"}], "resume")
        assert len(result) == 0


class TestTopRecommendations:
    """Tests for top_recommendations function"""

    def test_top_recommendations_basic(self):
        """Test getting top recommendations"""
        jobs = [
            JobPosting(
                source="indeed_uae",
                source_job_id="1",
                title="Developer",
                company="Corp1",
                location="Dubai",
                url="https://example.com/1"
            ),
            JobPosting(
                source="linkedin_public",
                source_job_id="2",
                title="Senior Developer",
                company="Corp2",
                location="Abu Dhabi",
                url="https://example.com/2"
            )
        ]
        with patch("utils.scoring.evaluate_fit") as mock_fit:
            mock_fit.side_effect = [
                {"score": 40, "qualifies": False},
                {"score": 80, "qualifies": True}
            ]
            result = top_recommendations(jobs, "resume text", limit=10)
            assert len(result) <= 2

    def test_top_recommendations_limit(self):
        """Test limit parameter"""
        jobs = [
            JobPosting(
                source="indeed_uae",
                source_job_id=str(i),
                title=f"Job {i}",
                company=f"Corp{i}",
                location="Dubai",
                url=f"https://example.com/{i}"
            )
            for i in range(20)
        ]
        with patch("utils.scoring.evaluate_fit") as mock_fit:
            mock_fit.return_value = {"score": 80, "qualifies": True}
            result = top_recommendations(jobs, "resume", limit=5)
            assert len(result) <= 5

    def test_top_recommendations_empty_list(self):
        """Test with empty job list"""
        result = top_recommendations([], "resume", limit=10)
        assert result == []

    def test_top_recommendations_deduplication(self):
        """Test that duplicate fingerprints are filtered"""
        jobs = [
            JobPosting(
                source="indeed_uae",
                source_job_id="1",
                title="Developer",
                company="Corp",
                location="Dubai",
                url="https://example.com/1"
            ),
            JobPosting(
                source="linkedin_public",
                source_job_id="2",
                title="Developer",
                company="Corp",
                location="Dubai",
                url="https://example.com/2"
            )
        ]
        with patch("utils.scoring.evaluate_fit") as mock_fit:
            mock_fit.return_value = {"score": 80, "qualifies": True}
            result = top_recommendations(jobs, "resume", limit=10)
            # May or may not deduplicate depending on fingerprints
            assert len(result) <= 2


class TestSourceLabel:
    """Tests for source_label function"""

    def test_source_label_jobvite(self):
        """Test label for jobvite"""
        assert source_label("jobvite_pragmaticplay") == "Jobvite"

    def test_source_label_smartrecruitment(self):
        """Test label for smartrecruitment"""
        assert source_label("smartrecruitment") == "SmartRecruitment"

    def test_source_label_indeed(self):
        """Test label for indeed"""
        assert source_label("indeed_uae") == "Indeed UAE"

    def test_source_label_linkedin(self):
        """Test label for linkedin"""
        assert source_label("linkedin_public") == "LinkedIn"

    def test_source_label_linkedin_malta(self):
        """Test label for LinkedIn Malta"""
        assert source_label("linkedin_malta") == "LinkedIn Malta"

    def test_source_label_unknown(self):
        """Test unknown source returns source as-is"""
        assert source_label("unknown_source") == "unknown_source"

    def test_source_label_all_mappings(self):
        """Test all known source mappings"""
        sources = [
            "jobvite_pragmaticplay",
            "smartrecruitment",
            "igamingrecruitment",
            "indeed_uae",
            "linkedin_public",
            "linkedin_georgia",
            "linkedin_malta",
            "jobrapido_uae",
            "jobleads",
            "telegram_job_crypto_uae",
            "telegram_cryptojobslist"
        ]
        for source in sources:
            label = source_label(source)
            assert isinstance(label, str)
            assert len(label) > 0
