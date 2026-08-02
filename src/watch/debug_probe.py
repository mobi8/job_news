#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single-keyword debug probes for browserless Glassdoor and JobSpy Indeed."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from utils.collection_config import build_glassdoor_uae_url
from utils.scrapers import fetch_glassdoor_jobs_via_browserless
from watch.scraper import _run_jobspy_query


def _cmd_glassdoor(args: argparse.Namespace) -> int:
    keyword = args.keyword.strip()
    url = args.url or build_glassdoor_uae_url(keyword)
    jobs = fetch_glassdoor_jobs_via_browserless(search_urls=[url], keywords=[keyword])
    print(json.dumps(
        {
            "probe": "glassdoor",
            "keyword": keyword,
            "url": url,
            "jobs": len(jobs),
            "sample": [job.__dict__ for job in jobs[: args.sample]],
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


def _cmd_indeed(args: argparse.Namespace) -> int:
    rows = _run_jobspy_query(
        site_name=["indeed"],
        search_term=args.keyword,
        location=args.location,
        hours_old=args.hours_old,
        results_wanted=args.results_wanted,
        country_indeed=args.country_indeed,
    )
    rows = rows or []
    print(json.dumps(
        {
            "probe": "indeed_jobspy",
            "keyword": args.keyword,
            "location": args.location,
            "country_indeed": args.country_indeed,
            "rows": len(rows),
            "sample": rows[: args.sample],
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    ))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=3)
    subparsers = parser.add_subparsers(dest="probe", required=True)

    glassdoor = subparsers.add_parser("glassdoor", help="Run one Glassdoor browserless keyword")
    glassdoor.add_argument("--keyword", default="crypto")
    glassdoor.add_argument("--url", default="")
    glassdoor.set_defaults(func=_cmd_glassdoor)

    indeed = subparsers.add_parser("indeed", help="Run one Indeed JobSpy keyword")
    indeed.add_argument("--keyword", default="Cryptocurrency")
    indeed.add_argument("--location", default="Dubai, United Arab Emirates")
    indeed.add_argument("--country-indeed", default="United Arab Emirates")
    indeed.add_argument("--hours-old", type=int, default=int(os.getenv("JOBSPY_HOURS_OLD", "24")))
    indeed.add_argument("--results-wanted", type=int, default=5)
    indeed.set_defaults(func=_cmd_indeed)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
