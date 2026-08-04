#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from utils.route_observability import (
    aggregate_location_role,
    append_jsonl,
    classify_health,
    render_compact_telegram_summary,
    write_markdown_summary,
)


def test_linkedin_jobs_route_record_creation(monkeypatch):
    from utils import scrapers

    url = "https://www.linkedin.com/jobs/search/?keywords=payments&location=Malta"
    monkeypatch.setattr(scrapers, "LINKEDIN_SEARCH_URLS", [url])
    monkeypatch.setattr(scrapers, "RECRUITER_SEARCH_URLS", [])
    monkeypatch.setattr(
        scrapers,
        "LINKEDIN_SEARCH_URL_METADATA",
        {
            url: {
                "target_id": "linkedin_malta_payments",
                "source": "linkedin_malta",
                "origin": "matrix",
                "location_id": "malta",
                "location": "Malta",
                "country": "Malta",
                "role_id": "payments",
                "keyword_group_id": "payments",
                "keyword_query": "payment operations",
            }
        },
    )
    monkeypatch.setattr(
        scrapers,
        "_batch_browser_fetch",
        lambda urls, batch_size: [
            {
                "href": url,
                "elapsed_ms": 1234,
                "jobs": [
                    {
                        "url": "https://www.linkedin.com/jobs/view/1",
                        "source_job_id": "1",
                        "title": "Payments Operations Manager",
                        "company": "Acme",
                        "location": "Malta",
                        "description": "payments",
                    }
                ],
            }
        ],
    )
    monkeypatch.delenv("COLLECTION_RUN_ID", raising=False)

    jobs = scrapers.fetch_linkedin_jobs_via_browser()

    assert len(jobs) == 1
    record = scrapers.fetch_linkedin_jobs_via_browser.last_route_records[0]
    assert record["source"] == "linkedin_jobs"
    assert record["origin"] == "matrix"
    assert record["location_id"] == "malta"
    assert record["role_id"] == "payments"
    assert record["target_id"] == "linkedin_malta_payments"
    assert record["keyword_group_id"] == "payments"
    assert record["query"] == "payment operations"
    assert record["url"] == url
    assert record["attempted"] is True
    assert record["status"] == "success"
    assert record["health"] == "healthy"
    assert record["raw"] == 1
    assert record["parsed"] == 1
    assert record["filtered"] is None
    assert record["new"] is None
    assert record["saved"] is None
    assert record["duplicates"] is None
    assert record["elapsed_ms"] == 1234
    assert record["error"] is None


def test_linkedin_posts_lead_level_record_creation():
    from watch.linkedin_posts import _post_plan_record

    record = _post_plan_record(
        {
            "location_id": "malta",
            "display_location": "Malta",
            "role_id": "igaming",
            "lead_id": "hiring",
            "category": "hiring_post",
            "query": "hiring igaming Malta",
        },
        raw=3,
        filtered=2,
        elapsed_ms=500,
        error=None,
    )

    assert record["source"] == "linkedin_posts"
    assert record["location_id"] == "malta"
    assert record["role_id"] == "igaming"
    assert record["lead_id"] == "hiring"
    assert record["target_id"] == "malta_igaming_hiring"
    assert record["raw"] == 3
    assert record["parsed"] == 3
    assert record["filtered"] == 2
    assert record["new"] is None
    assert record["health"] == "healthy"


def test_matrix_aggregation_by_location_role():
    records = [
        {"source": "linkedin_posts", "location_id": "malta", "location": "Malta", "role_id": "igaming", "attempted": True, "health": "healthy", "raw": 2, "parsed": 2, "filtered": 1, "elapsed_ms": 10},
        {"source": "linkedin_posts", "location_id": "malta", "location": "Malta", "role_id": "igaming", "attempted": True, "health": "zero", "raw": 0, "parsed": 0, "filtered": 0, "elapsed_ms": 20},
    ]

    cells = aggregate_location_role(records)

    assert len(cells) == 1
    assert cells[0]["location_id"] == "malta"
    assert cells[0]["role_id"] == "igaming"
    assert cells[0]["raw"] == 2
    assert cells[0]["parsed"] == 2
    assert cells[0]["filtered"] == 1
    assert cells[0]["health"] == "zero"


def test_health_classification_cases():
    assert classify_health(attempted=False, status="skipped", parsed=None) == "skipped"
    assert classify_health(attempted=True, status="success", parsed=2) == "healthy"
    assert classify_health(attempted=True, status="success", parsed=0) == "zero"
    assert classify_health(attempted=True, status="failed", parsed=None, error="boom") == "failed"
    assert classify_health(attempted=True, status="success", raw=30, parsed=30, filtered=1) == "noisy"


def test_jsonl_persistence(tmp_path):
    path = tmp_path / "targets.jsonl"
    count = append_jsonl(path, [{"source": "linkedin_jobs", "target_id": "x"}])

    assert count == 1
    assert json.loads(path.read_text(encoding="utf-8"))["target_id"] == "x"


def test_markdown_summary_generation(tmp_path):
    path = tmp_path / "summary.md"
    write_markdown_summary(
        path,
        run_id="run1",
        records=[
            {"source": "linkedin_jobs", "location_id": "malta", "location": "Malta", "role_id": "payments", "attempted": True, "health": "healthy", "raw": 1, "parsed": 1}
        ],
    )

    text = path.read_text(encoding="utf-8")
    assert "LinkedIn Jobs" in text
    assert "| malta | OK r=1 p=1 |" in text


def test_markdown_summary_preserves_unavailable_failed_counts(tmp_path):
    path = tmp_path / "summary.md"
    write_markdown_summary(
        path,
        run_id="run1",
        records=[
            {"source": "linkedin_posts", "location_id": "posts_amsterdam", "location": "Amsterdam", "role_id": "igaming", "attempted": True, "health": "failed", "raw": None, "parsed": None, "error": "fixture failure"}
        ],
    )

    assert "| posts_amsterdam | FAIL r=- p=- |" in path.read_text(encoding="utf-8")


def test_compact_telegram_format_excludes_full_url_and_query(tmp_path):
    summary_path = tmp_path / "summary.md"
    message = render_compact_telegram_summary(
        run_id="run1",
        summary_path=summary_path,
        records=[
            {
                "source": "linkedin_jobs",
                "location_id": "malta",
                "location": "Malta",
                "role_id": "payments",
                "health": "failed",
                "parsed": 0,
                "url": "https://www.linkedin.com/jobs/search/?keywords=very+long",
                "query": "very long query",
                "error": "x" * 200,
            }
        ],
    )

    assert "linkedin_jobs" in message
    assert "https://www.linkedin.com" not in message
    assert "very long query" not in message
    assert str(summary_path) in message


def test_no_isle_of_man_targets_or_plans_remain():
    from utils.collection_config import build_linkedin_job_targets, build_linkedin_post_plans, get_source_metadata_by_id

    job_blob = json.dumps([target.__dict__ for target in build_linkedin_job_targets(include_recruiters=False)], ensure_ascii=False).lower()
    post_blob = json.dumps(build_linkedin_post_plans(), ensure_ascii=False).lower()

    assert "isle_of_man" not in job_blob
    assert "isle of man" not in job_blob
    assert "linkedin_isle_of_man" not in job_blob
    assert "isle_of_man" not in post_blob
    assert "isle of man" not in post_blob
    assert get_source_metadata_by_id("linkedin_isle_of_man") is None


def test_linkedin_posts_filter_can_limit_to_one_lead_per_role(monkeypatch):
    monkeypatch.setenv(
        "COLLECTION_TARGET_FILTER_JSON",
        json.dumps(
            {
                "phase": "posts",
                "target_ids": ["posts_amsterdam"],
                "keyword_group_ids": ["digital_asset", "igaming"],
                "lead_ids": ["hiring"],
            }
        ),
    )
    import importlib
    from utils import collection_config

    importlib.reload(collection_config)
    plans = collection_config.build_linkedin_post_plans()

    assert [(plan["role_id"], plan["lead_id"]) for plan in plans] == [
        ("igaming", "hiring"),
        ("digital_asset", "hiring"),
    ]
