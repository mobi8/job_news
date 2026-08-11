from pathlib import Path

from services.telegram_scraper import (
    convert_to_job_posting_with_reason,
    scrape_and_save,
)
from utils.models import JobPosting
from watch import scraper


ROOT = Path(__file__).resolve().parents[1]


def test_full_run_shell_invokes_telegram_once_and_scraper_collect_does_not():
    run_script = (ROOT / "run_collect_once.sh").read_text(encoding="utf-8")
    scraper_source = (ROOT / "src/watch/scraper.py").read_text(encoding="utf-8")

    assert run_script.count("src/services/telegram_scraper.py") == 1
    assert "if False and (allowed_sources is None or (" in scraper_source


def test_jobspy_parent_dedupe_removes_cross_worker_duplicate():
    first = JobPosting(
        source="indeed_uae",
        source_job_id="1",
        title="Product Manager",
        company="Acme",
        location="Dubai",
        url="https://example.com/1",
    )
    duplicate = JobPosting(
        source="indeed_georgia",
        source_job_id="2",
        title="Product Manager",
        company="Acme",
        location="Dubai",
        url="https://example.com/2",
    )

    deduped = scraper._dedupe_jobspy_parent_results([first, duplicate], set())

    assert deduped == [first]


def test_jobspy_parent_dedupe_respects_recent_db_fingerprints():
    job = JobPosting(
        source="indeed_uae",
        source_job_id="1",
        title="Product Manager",
        company="Acme",
        location="Dubai",
        url="https://example.com/1",
    )

    assert scraper._dedupe_jobspy_parent_results([job], {job.fingerprint}) == []


def test_telegram_reject_reasons_are_reported(monkeypatch, tmp_path):
    messages = [
        {"text": "short"},
        {"text": "General market update with no role", "links": ["https://example.com/post"]},
        {"text": "🔍Product Manager💼Company: Acme📍Dubai", "links": ["https://t.me/job_crypto_uae/1"]},
        {
            "text": "🔍Product Manager💼Company: Acme📍Dubai",
            "links": ["https://example.com/job"],
            "timestamp": "2026-08-10T10:00:00+00:00",
        },
    ]
    monkeypatch.setattr(
        "services.telegram_scraper.scrape_all_channels",
        lambda: {
            "job_crypto_uae": {
                "name": "Crypto Jobs UAE",
                "messages": messages,
                "error": None,
                "count": len(messages),
            }
        },
    )

    result = scrape_and_save(str(tmp_path / "jobs.sqlite3"))

    assert result["total_messages"] == 4
    assert result["total_jobs"] == 2
    assert result["reject_counts"]["excluded_content"] == 1
    assert result["reject_counts"]["missing_role"] == 1
    assert result["reject_counts"]["missing_external_url"] == 0


def test_telegram_missing_external_url_reason():
    job, reason = convert_to_job_posting_with_reason(
        {"text": "🔍Product Manager💼Company: Acme📍Dubai", "links": []},
        "job_crypto_uae",
        "Crypto Jobs UAE",
    )

    assert job is None
    assert reason == "missing_external_url"


def test_telegram_message_permalink_is_url_fallback():
    job, reason = convert_to_job_posting_with_reason(
        {
            "text": "🔍Product Manager💼Company: Acme📍Dubai",
            "links": ["https://t.me/job_crypto_uae/1"],
            "timestamp": "2026-08-10T10:00:00+00:00",
        },
        "job_crypto_uae",
        "Crypto Jobs UAE",
    )

    assert reason is None
    assert job is not None
    assert job.url == "https://t.me/job_crypto_uae/1"


def test_linkedin_enabled_route_filter_keeps_all_enabled_sources():
    jobs = [
        JobPosting(source="linkedin_public", source_job_id="uae-1", title="UAE One", company="A", location="Dubai", url="https://example.com/uae-1"),
        JobPosting(source="linkedin_public", source_job_id="uae-2", title="UAE Two", company="A", location="Dubai", url="https://example.com/uae-2"),
        JobPosting(source="linkedin_amsterdam", source_job_id="ams-1", title="AMS One", company="B", location="Amsterdam", url="https://example.com/ams-1"),
        JobPosting(source="linkedin_amsterdam", source_job_id="ams-2", title="AMS Two", company="B", location="Amsterdam", url="https://example.com/ams-2"),
    ]

    defective_before = [job for job in jobs if job.source in {"linkedin_public"}]
    fixed_after = scraper._filter_linkedin_jobs_for_enabled_routes(
        jobs,
        {"linkedin_public"},
        ["linkedin_public", "linkedin_amsterdam"],
    )

    assert len(defective_before) == 2
    assert len(fixed_after) == 4
    assert [job.source for job in fixed_after] == [
        "linkedin_public",
        "linkedin_public",
        "linkedin_amsterdam",
        "linkedin_amsterdam",
    ]
    assert [job.location for job in fixed_after] == ["Dubai", "Dubai", "Amsterdam", "Amsterdam"]
