#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env for standalone LinkedIn post runs so Telegram alerts work
# the same way they do in src/watch/scraper.py.
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

from utils.config import (  # noqa: E402
    LINKEDIN_POST_SEARCH_PLANS,
    LINKEDIN_POSTS_PROBE_PATH,
    LINKEDIN_POSTS_PROFILE_DIR,
    OUTPUT_DIR,
)
from utils.db import Database  # noqa: E402
from utils.models import JobPosting  # noqa: E402
from utils.notifications import send_telegram_text  # noqa: E402
from utils.reporter import save_json  # noqa: E402
from utils.scoring import annotate_records, calculate_match_score, is_hard_excluded_job  # noqa: E402
from utils.utils import load_resume_text, utc_now  # noqa: E402

HIRING_TERMS = [
    "hiring", "we are hiring", "we're hiring", "open role", "job alert", "looking for",
    "vacancy", "join our team", "apply", "referral", "recruiting",
]
DOMAIN_TERMS = [
    "crypto", "web3", "blockchain", "payment", "payments", "fintech", "igaming",
    "gaming", "casino", "sportsbook", "product", "business development", "wallet",
    "backlog",
]
LOCATION_TERMS_BY_COUNTRY = {
    "UAE": ["uae", "dubai", "abu dhabi", "united arab emirates", "emirates"],
    "Remote": ["remote", "mena", "middle east", "gcc", "uae", "dubai", "saudi", "qatar", "bahrain", "kuwait", "oman"],
    "Georgia": ["georgia", "tbilisi", "tbilisi", "tbilisi", "tbilisi", "tbilishi", "tbilisi"],
    "Malta": ["malta", "sliema", "valletta", "st julian", "st. julian"],
}


def _probe_env(plans: List[Dict[str, Any]] | None = None) -> Dict[str, str]:
    env = os.environ.copy()
    env["LINKEDIN_POSTS_PROFILE_DIR"] = str(LINKEDIN_POSTS_PROFILE_DIR)
    env["LINKEDIN_POST_SEARCH_PLANS"] = json.dumps(plans or LINKEDIN_POST_SEARCH_PLANS, ensure_ascii=False)
    return env


def _profile_processes() -> List[int]:
    try:
        result = subprocess.run(["ps", "axo", "pid=,command="], capture_output=True, text=True, timeout=5)
        needle = f"--user-data-dir={LINKEDIN_POSTS_PROFILE_DIR}"
        pids: List[int] = []
        for line in result.stdout.splitlines():
            if needle not in line:
                continue
            pid_text = line.strip().split(None, 1)[0]
            try:
                pids.append(int(pid_text))
            except ValueError:
                pass
        return pids
    except Exception:
        return []


def _profile_in_use() -> bool:
    return bool(_profile_processes())


def _kill_profile_processes() -> None:
    pids = _profile_processes()
    if not pids:
        return
    print(f"남아있는 LinkedIn Chrome 프로세스를 정리합니다: {pids}")
    for pid in pids:
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    import time
    time.sleep(1)
    for pid in _profile_processes():
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def _wait_profile_released() -> None:
    while _profile_in_use():
        input(
            "LinkedIn 로그인용 Chrome이 아직 열려 있습니다. "
            "로그인 완료 후 그 Chrome 창을 완전히 닫고 Enter를 누르세요. "
            "이미 닫았다면 Enter를 누르면 남은 프로세스를 정리합니다."
        )
        if _profile_in_use():
            _kill_profile_processes()


def _run_probe(plans: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    result = subprocess.run(
        ["node", str(LINKEDIN_POSTS_PROBE_PATH)],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=_probe_env(plans),
        capture_output=True,
        text=True,
        timeout=int(os.getenv("LINKEDIN_POST_TIMEOUT", "900")),
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        # If the probe managed to print a partial JSON payload before failing,
        # keep the collected posts instead of dropping the whole run.
        try:
            partial = json.loads(result.stdout or "{}")
            if partial.get("posts") is not None:
                partial.setdefault("errors", []).append({"query": "probe", "error": stderr or f"exit {result.returncode}"})
                return partial
        except Exception:
            pass
        raise RuntimeError(stderr or f"probe exited with {result.returncode}")
    return json.loads(result.stdout or "{}")


def _run_login_setup() -> None:
    print("LinkedIn 세션이 없거나 만료되었습니다. 일반 Chrome 로그인 창을 띄웁니다.")
    subprocess.run(
        ["node", "linkedin_posts_login_setup.js"],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=_probe_env(),
        check=True,
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _chunks(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    if size <= 0:
        return [items]
    return [items[index:index + size] for index in range(0, len(items), size)]


def _post_lines(post: Dict[str, Any]) -> List[str]:
    return [line.strip() for line in (post.get("text") or "").splitlines() if line.strip()]


def _post_body(post: Dict[str, Any]) -> str:
    lines = _post_lines(post)
    if not lines:
        return ""
    # LinkedIn search cards often start with: 피드 게시물 / author / title / age / follow.
    # Prefer the actual post body after the follow marker if present.
    follow_index = next((i for i, line in enumerate(lines[:12]) if re.search(r"팔로우|follow", line, re.IGNORECASE)), -1)
    body_lines = lines[follow_index + 1:] if follow_index >= 0 and follow_index + 1 < len(lines) else []
    if not body_lines:
        trigger_index = next(
            (
                i for i, line in enumerate(lines[:16])
                if re.search(r"#?hiring|we.?re hiring|we are hiring|job alert|open role|vacancy|apply here|job title", line, re.IGNORECASE)
            ),
            -1,
        )
        body_lines = lines[trigger_index:] if trigger_index >= 0 else lines[:]
    return re.sub(r"\s+", " ", " ".join(body_lines)).strip()


def _infer_company(post: Dict[str, Any]) -> str:
    author = (post.get("author") or "").strip()
    body = _post_body(post)
    patterns = [
        r"Job Company:\s*([^|\n\r]{2,60})",
        r"Company:\s*([^|\n\r]{2,60})",
        r"at\s+([A-Z][A-Za-z0-9&.\- ]{2,40})",
        r"join\s+([A-Z][A-Za-z0-9&.\- ]{2,40})",
        r"([A-Z][A-Za-z0-9&.\- ]{2,40})\s+is hiring",
    ]
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return match.group(1).strip(" .,-|•")[:60]
    return re.sub(r"\s+", " ", author).strip()[:60] or "LinkedIn Post"


def _title_from_post(post: Dict[str, Any]) -> str:
    body = _post_body(post)
    patterns = [
        r"Job Title:\s*([^|\n\r]{3,90})",
        r"(?:hiring|job alert|open role|vacancy)[:\-–— ]+([^|\n\r]{3,90})",
    ]
    for pattern in patterns:
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return f"LinkedIn Post: {match.group(1).strip(' .,-|•')[:90]}"
    return f"LinkedIn Post: {body[:90] or 'Hiring post'}"


def _passes_filters(post: Dict[str, Any]) -> bool:
    if not _is_post_permalink(post.get("url", "")):
        return False
    text = f"{post.get('query', '')} {post.get('text', '')}".lower()
    if not any(term in text for term in HIRING_TERMS):
        return False
    country = post.get("country") or "UAE"
    location_terms = LOCATION_TERMS_BY_COUNTRY.get(country, LOCATION_TERMS_BY_COUNTRY["UAE"])
    if not any(term in text for term in location_terms):
        return False
    if not any(term in text for term in DOMAIN_TERMS):
        return False
    if is_hard_excluded_job(post.get("text", "")[:160], "LinkedIn", "UAE", post.get("text", "")):
        return False
    return True


def _is_post_permalink(url: str) -> bool:
    return bool(url) and ("/feed/update/" in url or "urn:li:share:" in url or "urn:li:ugcPost:" in url)


def _to_job(post: Dict[str, Any]) -> JobPosting:
    outbound = post.get("outbound_links") or []
    metadata = [
        "[LinkedIn Post Lead]",
        f"Category: {post.get('category', '')}",
        f"Domain: {post.get('domain', '')}",
        f"Country: {post.get('country') or 'UAE'}",
        f"Query: {post.get('query', '')}",
        f"Author: {post.get('author', '')}",
    ]
    if outbound:
        metadata.append("Outbound links:")
        metadata.extend(f"- {url}" for url in outbound[:6])
    metadata.extend(["", post.get("text", "")])

    return JobPosting(
        source="linkedin_post",
        source_job_id=post.get("source_job_id") or post.get("url", ""),
        title=_title_from_post(post),
        company=_infer_company(post),
        location=post.get("country") or "UAE",
        url=post.get("url", ""),
        description="\n".join(metadata).strip(),
        remote=False,
        country=post.get("country") or "UAE",
        collected_at=utc_now().isoformat(),
    )


def _refresh_dashboard_outputs(db: Database, inserted: int, inserted_jobs: List[JobPosting], resume_text: str) -> None:
    jobs = annotate_records(db.fetch_all_jobs(), resume_text)
    payload_path = OUTPUT_DIR / "jobs_analysis.json"
    if payload_path.exists():
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    else:
        payload = {}
    payload["all_tracked_jobs"] = jobs
    payload["filtered_jobs"] = [job for job in jobs if job.get("qualifies")]
    payload["collection_metadata"] = {
        **payload.get("collection_metadata", {}),
        "collected_at": utc_now().isoformat(),
        "sources": ["LinkedIn Posts"],
        "jobs_collected_this_run": len(inserted_jobs),
        "new_jobs_this_run": inserted,
        "new_jobs_this_run_details": [job.to_dict() for job in inserted_jobs],
        "resume_loaded": bool(resume_text),
    }
    save_json(payload_path, payload)


def _clean_linkedin_post_title(job: JobPosting) -> str:
    text = re.sub(r"^LinkedIn Post:\s*", "", job.title or "", flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:95].strip(" -•|") or "LinkedIn hiring post"


def _send_linkedin_post_telegram(inserted_jobs: List[JobPosting], batch_index: int, limit: int = 6) -> int:
    if not inserted_jobs:
        return 0
    jobs = [job for job in sorted(inserted_jobs, key=lambda job: job.match_score, reverse=True) if _is_post_permalink(job.url)][:limit]
    if not jobs:
        return 0
    countries: Dict[str, int] = {}
    for job in inserted_jobs:
        country = job.country or job.location or "Other"
        countries[country] = countries.get(country, 0) + 1
    country_line = " | ".join(f"{country} {count}" for country, count in sorted(countries.items()))
    lines = [f"<b>🔎 LinkedIn Posts batch {batch_index}</b>", f"신규 {len(inserted_jobs)}개 · {country_line}", ""]
    for idx, job in enumerate(jobs, start=1):
        title = html.escape(_clean_linkedin_post_title(job))
        country = html.escape(job.country or job.location or "")
        score = int(job.match_score or 0)
        url = html.escape(job.url or "", quote=True)
        lines.append(f"{idx}. [{country}] <a href=\"{url}\">{title}</a> · {score}")
    return len(jobs) if send_telegram_text("\n".join(lines)) else 0


def main() -> None:
    resume_text = load_resume_text()
    db = Database(OUTPUT_DIR / "jobs.sqlite3")

    max_plans = _env_int("LINKEDIN_POST_MAX_PLANS", len(LINKEDIN_POST_SEARCH_PLANS))
    start_plan = max(1, _env_int("LINKEDIN_POST_START_PLAN", 1))
    batch_size = _env_int("LINKEDIN_POST_BATCH_SIZE", 5)
    pause_min = _env_int("LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS", 60)
    pause_max = _env_int("LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS", 120)
    selected_plans = LINKEDIN_POST_SEARCH_PLANS[start_plan - 1:max_plans]
    plan_batches = _chunks(selected_plans, batch_size)

    total_raw = 0
    total_filtered = 0
    total_inserted = 0
    total_notified = 0
    total_errors = 0

    for batch_index, plans in enumerate(plan_batches, start=1):
        start = start_plan + (batch_index - 1) * batch_size if batch_size > 0 else start_plan
        end = start + len(plans) - 1
        print(f"LinkedIn posts batch {batch_index}/{len(plan_batches)}: plans {start}-{end}")

        try:
            result = _run_probe(plans)
        except RuntimeError as exc:
            total_errors += 1
            print(f"LinkedIn posts batch {batch_index} failed before collecting posts: {str(exc)[:300]}")
            if batch_index < len(plan_batches):
                _kill_profile_processes()
                pause_seconds = random.randint(min(pause_min, pause_max), max(pause_min, pause_max))
                print(f"LinkedIn posts cooldown: sleeping {pause_seconds}s before next batch")
                time.sleep(pause_seconds)
                continue
            break
        if result.get("login_required"):
            if os.getenv("LINKEDIN_POST_AUTO_LOGIN_SETUP", "1").strip().lower() in {"1", "true", "yes", "on"}:
                _run_login_setup()
                result = _run_probe(plans)
            if result.get("login_required"):
                print("LinkedIn login still required. Run ./setup_linkedin_posts_login.sh and try again.")
                return

        raw_posts = result.get("posts", [])
        probe_errors = result.get("errors", []) or []
        if probe_errors:
            print(f"LinkedIn posts batch {batch_index} completed with {len(probe_errors)} non-fatal error(s).")
            for error in probe_errors[:5]:
                print(f"  - {error.get('query', 'unknown')}: {str(error.get('error', ''))[:180]}")

        posts = [post for post in raw_posts if _passes_filters(post)]
        jobs = [_to_job(post) for post in posts]
        for job in jobs:
            job.match_score = calculate_match_score(job, resume_text)

        inserted, inserted_jobs = db.upsert_jobs(jobs, return_jobs=True)
        _refresh_dashboard_outputs(db, inserted, inserted_jobs, resume_text)
        notified = _send_linkedin_post_telegram(inserted_jobs, batch_index)

        total_raw += len(raw_posts)
        total_filtered += len(posts)
        total_inserted += inserted
        total_notified += notified
        total_errors += len(probe_errors)

        print(
            f"LinkedIn posts batch {batch_index}: raw={len(raw_posts)} filtered={len(posts)} "
            f"inserted={inserted} notified={notified} errors={len(probe_errors)}"
        )

        if batch_index < len(plan_batches):
            _kill_profile_processes()
            pause_seconds = random.randint(min(pause_min, pause_max), max(pause_min, pause_max))
            print(f"LinkedIn posts cooldown: sleeping {pause_seconds}s before next batch")
            time.sleep(pause_seconds)

    print(
        f"LinkedIn posts: raw={total_raw} filtered={total_filtered} "
        f"inserted={total_inserted} notified={total_notified} errors={total_errors}"
    )


if __name__ == "__main__":
    main()
