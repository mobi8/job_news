#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

from utils.config import BROWSER_PROBE_PATH, OUTPUT_DIR  # noqa: E402
from utils.db import Database  # noqa: E402
from utils.models import JobPosting  # noqa: E402
from utils.notifications import send_telegram_text  # noqa: E402
from utils.reporter import save_json  # noqa: E402
from utils.scoring import annotate_records, calculate_match_score, is_hard_excluded_job  # noqa: E402
from utils.utils import load_resume_text, normalize_linkedin_identifier, normalize_linkedin_url, utc_now  # noqa: E402


DEFAULT_KEYWORDS = "crypto,web3,payments,igaming,product"


def _build_search_url(location: str, keyword: str) -> str:
    params = {
        "keywords": keyword,
        "location": location,
        "sortBy": "DD",
        "f_TPR": "r604800",
        "origin": "JOB_SEARCH_PAGE_SEARCH_BUTTON",
    }
    return "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)


def _run_probe(urls: List[str]) -> List[Dict[str, Any]]:
    env = os.environ.copy()
    env.setdefault("BROWSER_HEADLESS", "1")
    result = subprocess.run(
        ["node", str(BROWSER_PROBE_PATH), *urls],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
        capture_output=True,
        text=True,
        timeout=int(os.getenv("LINKEDIN_JOB_SPOT_TIMEOUT", "300")),
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"browser_probe exited with {result.returncode}")
    payload = json.loads(result.stdout or "[]")
    if isinstance(payload, dict):
        return [payload]
    return payload


def _refresh_dashboard_outputs(db: Database, inserted: int, inserted_jobs: List[JobPosting], resume_text: str) -> None:
    jobs = annotate_records(db.fetch_all_jobs(), resume_text)
    payload_path = OUTPUT_DIR / "jobs_analysis.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8")) if payload_path.exists() else {}
    payload["all_tracked_jobs"] = jobs
    payload["filtered_jobs"] = [job for job in jobs if job.get("qualifies")]
    payload["collection_metadata"] = {
        **payload.get("collection_metadata", {}),
        "collected_at": utc_now().isoformat(),
        "sources": ["LinkedIn Jobs Spot"],
        "jobs_collected_this_run": len(inserted_jobs),
        "new_jobs_this_run": inserted,
        "new_jobs_this_run_details": [job.to_dict() for job in inserted_jobs],
        "resume_loaded": bool(resume_text),
    }
    save_json(payload_path, payload)


def _to_jobs(pages: List[Dict[str, Any]], location: str) -> List[JobPosting]:
    collected_at = utc_now().isoformat()
    jobs: List[JobPosting] = []
    seen_urls: set[str] = set()
    for page in pages:
        for item in page.get("jobs", []) or []:
            url = normalize_linkedin_url((item.get("url") or "").strip())
            title = (item.get("title") or "").strip()
            if not url or not title or url in seen_urls:
                continue
            seen_urls.add(url)

            company = (item.get("company") or "LinkedIn").strip()
            item_location = (item.get("location") or location).strip()
            description = (item.get("description") or "").strip()
            if is_hard_excluded_job(title, company, item_location, description):
                continue

            source_job_id = normalize_linkedin_identifier(
                "linkedin_job_spot",
                (item.get("source_job_id") or url).strip(),
            )
            jobs.append(
                JobPosting(
                    source="linkedin_job_spot",
                    source_job_id=source_job_id,
                    title=title,
                    company=company,
                    location=item_location or location,
                    url=url,
                    description=description,
                    remote="remote" in f"{title} {item_location} {description}".lower(),
                    country="Other",
                    collected_at=collected_at,
                )
            )
    return jobs


def _send_telegram(inserted_jobs: List[JobPosting], location: str, keywords: List[str], limit: int) -> int:
    keyword_text = ", ".join(keywords)
    jobs = sorted(inserted_jobs, key=lambda job: job.match_score, reverse=True)[:limit]
    lines = [
        f"<b>💼 LinkedIn Jobs Spot · {html.escape(location)}</b>",
        f"신규 {len(inserted_jobs)}개 · 기타 저장 · {html.escape(keyword_text)}",
        "",
    ]
    if not jobs:
        lines.append("새로 저장된 잡보드 결과가 없습니다.")
        return 0 if send_telegram_text("\n".join(lines)) else 0
    for idx, job in enumerate(jobs, start=1):
        title = html.escape((job.title or "")[:95])
        company = html.escape(job.company or "LinkedIn")
        score = int(job.match_score or 0)
        url = html.escape(job.url or "", quote=True)
        lines.append(f"{idx}. <a href=\"{url}\">{title}</a> · {company} · {score}")
    return len(jobs) if send_telegram_text("\n".join(lines)) else 0


def main(argv: List[str]) -> None:
    if not argv:
        print("Usage: linkedin_jobs_spot.py <location> [keyword1,keyword2] [limit]", file=sys.stderr)
        raise SystemExit(2)

    location = argv[0].strip()
    keywords = [item.strip() for item in (argv[1] if len(argv) > 1 else DEFAULT_KEYWORDS).split(",") if item.strip()]
    limit = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 8
    urls = [_build_search_url(location, keyword) for keyword in keywords[:max(1, limit)]]

    print(f"LinkedIn jobs spot: location={location} keywords={','.join(keywords)} urls={len(urls)}")
    pages = _run_probe(urls)
    resume_text = load_resume_text()
    db = Database(OUTPUT_DIR / "jobs.sqlite3")
    jobs = _to_jobs(pages, location)
    for job in jobs:
        job.match_score = calculate_match_score(job, resume_text)

    inserted, inserted_jobs = db.upsert_jobs(jobs, return_jobs=True)
    if os.getenv("LINKEDIN_JOB_SPOT_REFRESH_DASHBOARD", "1").strip().lower() in {"1", "true", "yes", "on"}:
        _refresh_dashboard_outputs(db, inserted, inserted_jobs, resume_text)
    notified = _send_telegram(inserted_jobs, location, keywords, limit)
    print(f"LinkedIn jobs spot: raw={sum(len(page.get('jobs', []) or []) for page in pages)} inserted={inserted} notified={notified}")


if __name__ == "__main__":
    main(sys.argv[1:])
