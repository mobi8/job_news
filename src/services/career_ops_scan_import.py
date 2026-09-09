#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import career-ops scan results into the job watch DB and Telegram flow."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.db import Database
from utils.logger import watch_logger
from utils.models import JobPosting
from utils.notifications import maybe_send_telegram


CAREER_OPS_DIR = Path(os.getenv("CAREER_OPS_DIR", "/Users/lewis/Desktop/career/career-ops"))
DB_PATH = Path(os.getenv("DB_PATH", "/Users/lewis/Desktop/agent/outputs/jobs.sqlite3"))


def _select_node_bin() -> str:
    candidates = [
        os.getenv("NODE_BIN", ""),
        os.getenv("JOBHUNT_NODE_BIN", ""),
        shutil.which("node") or "",
        "/opt/homebrew/bin/node",
        "/usr/local/bin/node",
        str(Path.home() / ".nvm/versions/node/current/bin/node"),
        str(Path.home() / ".nvm/versions/node/v23.5.0/bin/node"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return "node"


def _neutral_import_score() -> int:
    return 60


def _country_for_location(location: str) -> str:
    value = (location or "").lower()
    if "dubai" in value or "abu dhabi" in value or "uae" in value:
        return "UAE"
    if "malta" in value:
        return "Malta"
    if "cyprus" in value:
        return "Cyprus"
    if "korea" in value:
        return "Korea"
    if "remote" in value:
        return "Remote"
    return "Global"


def _to_job_posting(job: dict[str, Any]) -> JobPosting:
    title = str(job.get("title") or "").strip()
    company = str(job.get("company") or "").strip()
    location = str(job.get("location") or "").strip()
    url = str(job.get("url") or "").strip()
    provider = str(job.get("provider") or "custom").strip()
    source_type = str(job.get("source_type") or "careers_scan").strip()
    source = "career_ops_scan"
    return JobPosting(
        source=source,
        source_job_id=url or f"{company}|{title}|{location}",
        title=title,
        company=company,
        location=location,
        url=url,
        description=f"{title} at {company}. Provider: {provider}. Source type: {source_type}.",
        remote="remote" in location.lower(),
        country=_country_for_location(location),
        collected_at=str(job.get("posted_at") or ""),
        match_score=_neutral_import_score(),
    )


def run_import(dry_run: bool = False, notify: bool = True) -> dict[str, Any]:
    node_bin = _select_node_bin()
    args = [node_bin, "scan.mjs", "--json"]
    if dry_run:
        args.append("--dry-run")
    watch_logger.info(
        "Career-Ops scan import starting: cwd=%s dry_run=%s notify=%s",
        CAREER_OPS_DIR,
        dry_run,
        notify,
    )
    try:
        result = subprocess.run(
            args,
            cwd=CAREER_OPS_DIR,
            text=True,
            capture_output=True,
            check=False,
            timeout=int(os.getenv("CAREER_OPS_SCAN_TIMEOUT_SECONDS", "240")),
        )
    except Exception as exc:
        watch_logger.warning("Career-Ops scan import failed before scan completed: %r", exc, exc_info=True)
        return {
            "status": "failed",
            "error": repr(exc),
            "node_bin": node_bin,
        }
    if result.returncode != 0:
        watch_logger.warning(
            "Career-Ops scan import failed: returncode=%s stderr=%s",
            result.returncode,
            result.stderr[-1000:],
        )
        return {
            "status": "failed",
            "returncode": result.returncode,
            "stderr": result.stderr[-2000:],
        }

    payload = json.loads(result.stdout)
    postings = [_to_job_posting(job) for job in payload.get("offers", []) if job.get("title") and job.get("company")]
    summary = {
        "companies_scanned": payload.get("companies_scanned"),
        "fetch_successes": payload.get("fetch_successes"),
        "fetch_failures": payload.get("fetch_failures"),
        "total_jobs_found": payload.get("total_jobs_found"),
        "new_offers_added": payload.get("new_offers_added"),
    }
    inserted = 0
    inserted_jobs: list[JobPosting] = []
    if not dry_run and postings:
        db = Database(DB_PATH)
        try:
            inserted, inserted_jobs = db.upsert_jobs(postings, return_jobs=True)
        finally:
            db.conn.close()
        if notify:
            maybe_send_telegram(inserted, [job.to_dict() for job in inserted_jobs], min_score=30)

    watch_logger.info(
        "Career-Ops scan import complete: summary=%s jobs_from_scan=%s db_inserted=%s telegram_candidates=%s",
        summary,
        len(postings),
        inserted,
        len(inserted_jobs),
    )
    return {
        "status": "success",
        "dry_run": dry_run,
        "scan_summary": summary,
        "jobs_from_scan": len(postings),
        "db_inserted": inserted,
        "telegram_candidates": len(inserted_jobs),
    }


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    notify = "--no-notify" not in sys.argv
    print(json.dumps(run_import(dry_run=dry_run, notify=notify), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
