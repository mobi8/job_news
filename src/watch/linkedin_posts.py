#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import html
import json
import os
import random
import re
import signal
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

from utils.collection_config import (  # noqa: E402
    LINKEDIN_POST_FILTERS,
    LINKEDIN_POST_LOCATION_TERMS_BY_COUNTRY,
    LINKEDIN_POST_SEARCH_PLANS,
)
from utils.config import (  # noqa: E402
    LINKEDIN_POSTS_PROBE_PATH,
    LINKEDIN_POSTS_PROFILE_DIR,
    OUTPUT_DIR,
)
from utils.route_observability import (  # noqa: E402
    append_jsonl,
    classify_health,
    new_run_id,
    render_compact_telegram_summary,
    run_dir,
    write_markdown_summary,
)

def _resolve_node_bin() -> str:
    """Resolve Node executable path from multiple sources."""
    candidates = [
        os.getenv("JOBHUNT_NODE_BIN"),
        os.getenv("NODE_BIN"),
    ]

    # Check explicit env vars first
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate

    # Check PATH
    try:
        result = subprocess.run(["which", "node"], capture_output=True, text=True, timeout=2)
        if result.returncode == 0 and result.stdout.strip():
            node_path = result.stdout.strip()
            if os.path.isfile(node_path) and os.access(node_path, os.X_OK):
                return node_path
    except Exception:
        pass

    # Check common installation paths
    nvm_node = Path.home() / ".nvm" / "versions" / "node" / "current" / "bin" / "node"
    if nvm_node.exists():
        return str(nvm_node)

    homebrew_node = Path("/opt/homebrew/bin/node")
    if homebrew_node.exists():
        return str(homebrew_node)

    usrlocal_node = Path("/usr/local/bin/node")
    if usrlocal_node.exists():
        return str(usrlocal_node)

    # Fallback: fail with clear error
    error_msg = (
        "Node executable not found. Please set NODE_BIN or JOBHUNT_NODE_BIN environment variable. "
        "Checked: PATH, NVM, /opt/homebrew/bin/node, /usr/local/bin/node"
    )
    print(f"ERROR: {error_msg}", file=sys.stderr, flush=True)
    sys.exit(1)

NODE_BIN = _resolve_node_bin()
ACTIVE_LINKEDIN_POSTS_PROFILE_DIR = Path(
    os.getenv("LINKEDIN_POSTS_PROFILE_DIR") or str(LINKEDIN_POSTS_PROFILE_DIR)
).resolve()
LOCK_PATH = OUTPUT_DIR / "linkedin_posts.lock"
CURRENT_STAGE = "startup"
LOCK_ACQUIRED = False


def _posts_run_context() -> tuple[str, Path]:
    run_id = os.getenv("COLLECTION_RUN_ID") or new_run_id("posts")
    os.environ["COLLECTION_RUN_ID"] = run_id
    return run_id, run_dir(run_id)


def _post_plan_record(plan: Dict[str, Any], *, raw: int | None, filtered: int | None, elapsed_ms: int | None, error: str | None) -> Dict[str, Any]:
    status = "failed" if error else "success"
    parsed = raw
    return {
        "source": "linkedin_posts",
        "origin": "matrix",
        "location_id": plan.get("location_id"),
        "location": plan.get("display_location") or plan.get("country"),
        "role_id": plan.get("role_id") or plan.get("domain"),
        "lead_id": plan.get("lead_id"),
        "category": plan.get("category"),
        "target_id": f"{plan.get('location_id')}_{plan.get('role_id')}_{plan.get('lead_id')}",
        "keyword_group_id": plan.get("role_id") or plan.get("domain"),
        "query": plan.get("query"),
        "url": None,
        "attempted": True,
        "status": status,
        "health": classify_health(
            attempted=True,
            status=status,
            raw=raw,
            parsed=parsed,
            filtered=filtered,
            error=error,
        ),
        "raw": raw,
        "parsed": parsed,
        "filtered": filtered,
        "new": None,
        "saved": None,
        "duplicates": None,
        "elapsed_ms": elapsed_ms,
        "error": error,
    }


def _write_post_records(run_output_dir: Path, records: List[Dict[str, Any]]) -> None:
    if records:
        append_jsonl(run_output_dir / "targets.jsonl", records)


class LoginRequiredError(RuntimeError):
    pass


class CheckpointRequiredError(RuntimeError):
    pass


class StageTimeoutError(TimeoutError):
    def __init__(self, stage: str, seconds: int):
        super().__init__(f"{stage} timed out after {seconds}s")
        self.stage = stage
        self.seconds = seconds


def _set_stage(stage: str) -> None:
    global CURRENT_STAGE
    CURRENT_STAGE = stage
    print(f"LinkedIn posts stage: {stage}", flush=True)


def _send_telegram(message: str) -> None:
    try:
        from utils.notifications import send_telegram_text
        send_telegram_text(message)
    except Exception as exc:
        print(f"Telegram notification failed: {exc}", flush=True)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _read_lock() -> Dict[str, Any] | None:
    if not LOCK_PATH.exists():
        return None
    try:
        text = LOCK_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return json.loads(text)
    except Exception:
        return None


def _format_runtime(started_at: float | int | str | None) -> str:
    try:
        elapsed = max(0, int(time.time() - float(started_at)))
    except Exception:
        return "unknown"
    hours, rem = divmod(elapsed, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def acquire_lock() -> None:
    global LOCK_ACQUIRED
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    info = _read_lock()
    if info:
        pid = int(info.get("pid") or 0)
        if _pid_exists(pid):
            runtime = _format_runtime(info.get("started_at_epoch"))
            message = f"LinkedIn posts already running: PID={pid}, runtime={runtime}"
            print(message, flush=True)
            _send_telegram(f"⚠️ LinkedIn 포스트가 이미 실행 중입니다. PID={pid}, 실행시간={runtime}")
            raise SystemExit(75)
        print(f"Removing stale LinkedIn posts lock: {LOCK_PATH}", flush=True)
        LOCK_PATH.unlink(missing_ok=True)

    payload = {
        "pid": os.getpid(),
        "started_at_epoch": time.time(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "command": " ".join([sys.executable, *sys.argv]),
    }
    LOCK_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    LOCK_ACQUIRED = True
    print(f"LinkedIn posts lock acquired: {LOCK_PATH} PID={os.getpid()}", flush=True)


def release_lock() -> None:
    global LOCK_ACQUIRED
    if not LOCK_ACQUIRED:
        return
    info = _read_lock()
    if not info or int(info.get("pid") or 0) == os.getpid():
        LOCK_PATH.unlink(missing_ok=True)
        print(f"LinkedIn posts lock released: {LOCK_PATH}", flush=True)
    LOCK_ACQUIRED = False


def _signal_handler(signum, frame):  # pragma: no cover - signal path
    print(f"LinkedIn posts received signal {signum}; stage={CURRENT_STAGE}", flush=True)
    _kill_profile_processes()
    release_lock()
    raise SystemExit(128 + int(signum))


for _sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(_sig, _signal_handler)

HIRING_TERMS = list(LINKEDIN_POST_FILTERS.get("hiring_terms") or [
    "hiring", "we are hiring", "we're hiring", "open role", "job alert", "looking for",
    "vacancy", "join our team", "apply", "referral", "recruiting",
])
JOB_POST_SIGNAL_PATTERNS = [
    r"\b(?:we(?: are|'re)|is|now|actively)\s+hiring\b",
    r"#hiring\b",
    r"\bhiring\s+(?:for|:|-|–|—)\b",
    r"\bjob\s+alert\b",
    r"\bopen\s+(?:role|roles|position|positions|vacancy|vacancies)\b",
    r"\bvacanc(?:y|ies)\b",
    r"\bjoin\s+our\s+team\b",
    r"\bapply\s+(?:now|here|today)\b",
    r"\bjob\s+title\s*:",
    r"\b(?:role|position)\s*:",
    r"\b(?:we(?: are|'re)\s+)?looking\s+for\s+(?:a|an|our)?\s*.{0,50}\b(?:manager|engineer|developer|lead|specialist|candidate|talent|product|sales|business development|bd)\b",
]
JOB_DESTINATION_TERMS = list(LINKEDIN_POST_FILTERS.get("job_destination_terms") or [
    "/jobs/", "/careers/", "greenhouse.io", "lever.co", "ashbyhq.com",
    "workable.com", "recruitee.com", "smartrecruiters.com",
])
DOMAIN_TERMS = list(LINKEDIN_POST_FILTERS.get("domain_terms") or [
    "crypto", "web3", "blockchain", "payment", "payments", "fintech", "igaming",
    "gaming", "casino", "sportsbook", "product", "business development", "wallet",
    "backlog",
])
LOCATION_TERMS_BY_COUNTRY = dict(LINKEDIN_POST_LOCATION_TERMS_BY_COUNTRY or {
    "UAE": ["uae", "dubai", "abu dhabi", "united arab emirates", "emirates"],
})


def _probe_env(plans: List[Dict[str, Any]] | None = None) -> Dict[str, str]:
    env = os.environ.copy()
    env["LINKEDIN_POSTS_PROFILE_DIR"] = str(ACTIVE_LINKEDIN_POSTS_PROFILE_DIR)
    env["LINKEDIN_POST_SEARCH_PLANS"] = json.dumps(plans or LINKEDIN_POST_SEARCH_PLANS, ensure_ascii=False)
    return env


def _profile_processes() -> List[int]:
    try:
        result = subprocess.run(["ps", "axo", "pid=,command="], capture_output=True, text=True, timeout=5)
        needle = f"--user-data-dir={ACTIVE_LINKEDIN_POSTS_PROFILE_DIR}"
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
    timeout_seconds = int(os.getenv("LINKEDIN_POST_TIMEOUT", "900"))
    _set_stage("probe subprocess")
    print(
        f"LinkedIn posts probe: launching Chrome/search worker with {NODE_BIN} timeout={timeout_seconds}s...",
        flush=True,
    )
    try:
        result = subprocess.run(
            [NODE_BIN, str(LINKEDIN_POSTS_PROBE_PATH)],
            cwd=str(Path(__file__).resolve().parents[2]),
            env=_probe_env(plans),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stderr_value = exc.stderr or ""
        if isinstance(stderr_value, bytes):
            stderr_text = stderr_value.decode("utf-8", errors="replace").strip()
        else:
            stderr_text = str(stderr_value).strip()
        if stderr_text:
            for line in stderr_text.splitlines()[-80:]:
                print(line, file=sys.stderr, flush=True)
        _kill_profile_processes()
        raise StageTimeoutError(CURRENT_STAGE, timeout_seconds) from exc

    stderr_text = (result.stderr or "").strip()
    if stderr_text:
        for line in stderr_text.splitlines()[-80:]:
            print(line, file=sys.stderr, flush=True)

    if result.returncode != 0:
        # If the probe managed to print a partial JSON payload before failing,
        # keep the collected posts instead of dropping the whole run.
        try:
            partial = json.loads(result.stdout or "{}")
            if partial.get("posts") is not None:
                partial.setdefault("errors", []).append({"query": "probe", "error": stderr_text or f"exit {result.returncode}"})
                return partial
        except Exception:
            pass
        raise RuntimeError(stderr_text or f"probe exited with {result.returncode}")

    data = json.loads(result.stdout or "{}")
    if data.get("checkpoint_required"):
        raise CheckpointRequiredError(data.get("reason") or "LinkedIn checkpoint/additional verification required")
    if data.get("login_required"):
        raise LoginRequiredError(data.get("reason") or "LinkedIn login required")
    return data


def _check_playwright_ready() -> None:
    timeout_seconds = _env_int("LINKEDIN_POST_REQUIRE_TIMEOUT", 20)
    _set_stage("Playwright require")
    probe_script = (
        "console.error(`node=${process.execPath} version=${process.version}`);"
        "require('playwright');"
        "console.error('playwright=require-ok');"
    )
    try:
        result = subprocess.run(
            [NODE_BIN, "-e", probe_script],
            cwd=str(Path(__file__).resolve().parents[2]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stderr_value = exc.stderr or ""
        if isinstance(stderr_value, bytes):
            stderr_text = stderr_value.decode("utf-8", errors="replace").strip()
        else:
            stderr_text = str(stderr_value).strip()
        if stderr_text:
            print(stderr_text, file=sys.stderr, flush=True)
        hint = (
            f"Playwright require timed out after {timeout_seconds}s. "
            "The local Node/Playwright install may be corrupt; try `npm install`."
        )
        raise StageTimeoutError(hint, timeout_seconds) from exc
    if result.returncode != 0:
        stderr_text = (result.stderr or "").strip()
        raise RuntimeError(
            f"{stderr_text or f'Playwright require exited with {result.returncode}'}\n"
            "Dependency preflight failed; try `npm install` from /Users/lewis/Desktop/agent."
        )


def _run_login_setup() -> None:
    print("LinkedIn 세션이 없거나 만료되었습니다. 일반 Chrome 로그인 창을 띄웁니다.")
    subprocess.run(
        [NODE_BIN, "linkedin_posts_login_setup.js"],
        cwd=str(Path(__file__).resolve().parents[2]),
        env=_probe_env(),
        check=True,
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    from utils.scoring import is_hard_excluded_job

    if not _is_post_permalink(post.get("url", "")):
        return False
    body = _post_body(post)
    text = f"{body} {post.get('text', '')}".lower()
    if not _has_job_post_signal(body, post.get("outbound_links") or []):
        return False
    country = post.get("country") or "UAE"
    location_terms = post.get("location_terms") or LOCATION_TERMS_BY_COUNTRY.get(country, LOCATION_TERMS_BY_COUNTRY["UAE"])
    if not any(term in text for term in location_terms):
        return False
    if not any(term in text for term in DOMAIN_TERMS):
        return False
    hard_exclusion_location = post.get("display_location") or post.get("country") or "UAE"
    if is_hard_excluded_job(post.get("text", "")[:160], "LinkedIn", hard_exclusion_location, post.get("text", "")):
        return False
    return True


def _has_job_post_signal(body: str, outbound_links: List[str]) -> bool:
    lowered = body.lower()
    if any(re.search(pattern, lowered, re.IGNORECASE) for pattern in JOB_POST_SIGNAL_PATTERNS):
        return True
    return any(
        any(term in (url or "").lower() for term in JOB_DESTINATION_TERMS)
        for url in outbound_links
    )


def _is_post_permalink(url: str) -> bool:
    return bool(url) and ("/feed/update/" in url or "urn:li:share:" in url or "urn:li:ugcPost:" in url)


def _to_job(post: Dict[str, Any]) -> JobPosting:
    from utils.models import JobPosting
    from utils.utils import utc_now

    outbound = post.get("outbound_links") or []
    source = post.get("source") or "linkedin_post"
    location = post.get("display_location") or post.get("country") or "UAE"
    country = post.get("store_country") or post.get("country") or "UAE"
    metadata = [
        "[LinkedIn Post Lead]",
        f"Category: {post.get('category', '')}",
        f"Domain: {post.get('domain', '')}",
        f"Country: {post.get('country') or country}",
        f"Dashboard country: {country}",
        f"Location: {location}",
        f"Query: {post.get('query', '')}",
        f"Author: {post.get('author', '')}",
    ]
    if outbound:
        metadata.append("Outbound links:")
        metadata.extend(f"- {url}" for url in outbound[:6])
    metadata.extend(["", post.get("text", "")])

    return JobPosting(
        source=source,
        source_job_id=post.get("source_job_id") or post.get("url", ""),
        title=_title_from_post(post),
        company=_infer_company(post),
        location=location,
        url=post.get("url", ""),
        description="\n".join(metadata).strip(),
        remote=False,
        country=country,
        collected_at=utc_now().isoformat(),
    )


def _refresh_dashboard_outputs(db: Database, inserted: int, inserted_jobs: List[JobPosting], resume_text: str) -> None:
    from utils.reporter import save_json
    from utils.scoring import annotate_records
    from utils.utils import utc_now

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
    from utils.notifications import send_telegram_text
    return len(jobs) if send_telegram_text("\n".join(lines)) else 0


def _send_spot_telegram(inserted_jobs: List[JobPosting], location: str, keywords: List[str], limit: int) -> int:
    jobs = [job for job in sorted(inserted_jobs, key=lambda job: job.match_score, reverse=True) if _is_post_permalink(job.url)][:limit]
    keyword_text = ", ".join(keywords)
    lines = [
        f"<b>🔎 LinkedIn Spot · {html.escape(location)}</b>",
        f"신규 {len(inserted_jobs)}개 · 기타 저장 · {html.escape(keyword_text)}",
        "",
    ]
    if not jobs:
        lines.append("새로 저장된 permalink 결과가 없습니다.")
        from utils.notifications import send_telegram_text
        return 0 if send_telegram_text("\n".join(lines)) else 0
    for idx, job in enumerate(jobs, start=1):
        title = html.escape(_clean_linkedin_post_title(job))
        score = int(job.match_score or 0)
        url = html.escape(job.url or "", quote=True)
        lines.append(f"{idx}. <a href=\"{url}\">{title}</a> · {score}")
    from utils.notifications import send_telegram_text
    return len(jobs) if send_telegram_text("\n".join(lines)) else 0


def _spot_terms(location: str) -> List[str]:
    terms = {location.strip().lower()}
    for part in re.split(r"[,/| ]+", location.lower()):
        part = part.strip()
        if len(part) >= 3:
            terms.add(part)
    aliases = {
        "amsterdam": ["amsterdam", "netherlands", "nederland", "holland"],
        "portugal": ["portugal", "lisbon", "lisboa", "porto"],
    }
    for key, values in aliases.items():
        if key in terms:
            terms.update(values)
    return sorted(terms)


def _spot_plans(location: str, keywords: List[str]) -> List[Dict[str, Any]]:
    location_terms = _spot_terms(location)
    leads = ["hiring", "job alert"]
    return [
        {
            "category": "spot_post",
            "domain": keyword.strip().lower().replace(" ", "_"),
            "country": location,
            "store_country": "Other",
            "display_location": location,
            "location_terms": location_terms,
            "source": "linkedin_post_spot",
            "query": f"{lead} {keyword.strip()} {location}",
        }
        for keyword in keywords
        if keyword.strip()
        for lead in leads
    ]


def main_spot(argv: List[str]) -> None:
    if not argv:
        print("Usage: linkedin_posts.py spot <location> [keyword1,keyword2] [limit]", file=sys.stderr)
        raise SystemExit(2)
    location = argv[0].strip()
    keywords = [item.strip() for item in (argv[1] if len(argv) > 1 else "crypto,web3,payments,igaming,product").split(",") if item.strip()]
    limit = int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 8
    plans = _spot_plans(location, keywords)[:max(1, limit)]

    os.environ.setdefault("LINKEDIN_POST_SCROLL_ROUNDS", "1")
    os.environ.setdefault("LINKEDIN_POST_BATCH_SIZE", str(max(1, len(plans))))
    os.environ.setdefault("LINKEDIN_POST_QUERY_PAUSE_MIN_SECONDS", "2")
    os.environ.setdefault("LINKEDIN_POST_QUERY_PAUSE_MAX_SECONDS", "4")

    print(f"LinkedIn spot: location={location} keywords={','.join(keywords)} plans={len(plans)}")

    result = _run_probe(plans)

    raw_posts = result.get("posts", [])
    posts = [post for post in raw_posts if _passes_filters(post)]
    jobs = [_to_job(post) for post in posts]
    from utils.db import Database
    from utils.scoring import calculate_match_score
    from utils.utils import load_resume_text

    resume_text = load_resume_text()
    db = Database(OUTPUT_DIR / "jobs.sqlite3")
    for job in jobs:
        job.match_score = calculate_match_score(job, resume_text)

    inserted, inserted_jobs = db.upsert_jobs(jobs, return_jobs=True)
    if os.getenv("LINKEDIN_SPOT_REFRESH_DASHBOARD", "1").strip().lower() in {"1", "true", "yes", "on"}:
        _refresh_dashboard_outputs(db, inserted, inserted_jobs, resume_text)
    notified = _send_spot_telegram(inserted_jobs, location, keywords, limit)
    print(f"LinkedIn spot: raw={len(raw_posts)} filtered={len(posts)} inserted={inserted} notified={notified}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "spot":
        main_spot(sys.argv[2:])
        return

    print("LinkedIn posts runner starting...", flush=True)
    route_run_id, route_output_dir = _posts_run_context()
    max_plans = _env_int("LINKEDIN_POST_MAX_PLANS", len(LINKEDIN_POST_SEARCH_PLANS))
    start_plan = max(1, _env_int("LINKEDIN_POST_START_PLAN", 1))
    batch_size = _env_int("LINKEDIN_POST_BATCH_SIZE", 5)
    pause_min = _env_int("LINKEDIN_POST_BATCH_PAUSE_MIN_SECONDS", 60)
    pause_max = _env_int("LINKEDIN_POST_BATCH_PAUSE_MAX_SECONDS", 120)
    selected_plans = LINKEDIN_POST_SEARCH_PLANS[start_plan - 1:max_plans]
    plan_batches = _chunks(selected_plans, batch_size)
    print(
        f"LinkedIn posts config: start_plan={start_plan} max_plans={max_plans} "
        f"batch_size={batch_size} batches={len(plan_batches)}",
        flush=True,
    )

    total_raw = 0
    total_filtered = 0
    total_inserted = 0
    total_notified = 0
    total_errors = 0

    for batch_index, plans in enumerate(plan_batches, start=1):
        start = start_plan + (batch_index - 1) * batch_size if batch_size > 0 else start_plan
        end = start + len(plans) - 1
        print(f"LinkedIn posts batch {batch_index}/{len(plan_batches)}: plans {start}-{end}")
        for i, plan in enumerate(plans, start=start):
            print(f"  [{i}] {plan.get('query', 'N/A')}")

        try:
            result = _run_probe(plans)
        except LoginRequiredError as exc:
            _write_post_records(
                route_output_dir,
                [_post_plan_record(plan, raw=None, filtered=None, elapsed_ms=None, error=f"login_required: {exc}") for plan in plans],
            )
            raise
        except CheckpointRequiredError as exc:
            _write_post_records(
                route_output_dir,
                [_post_plan_record(plan, raw=None, filtered=None, elapsed_ms=None, error=f"checkpoint_required: {exc}") for plan in plans],
            )
            raise
        except RuntimeError as exc:
            error_msg = str(exc)[:300]
            print(f"LinkedIn posts batch {batch_index} failed: {error_msg}")
            _write_post_records(
                route_output_dir,
                [_post_plan_record(plan, raw=None, filtered=None, elapsed_ms=None, error=error_msg) for plan in plans],
            )
            if os.getenv("LINKEDIN_POST_AUTO_LOGIN_SETUP", "1").strip().lower() in {"1", "true", "yes", "on"}:
                print("Automatic login setup is disabled for /posts; login must be completed manually.")
            total_errors += 1
            if batch_index < len(plan_batches):
                _kill_profile_processes()
                pause_seconds = random.randint(min(pause_min, pause_max), max(pause_min, pause_max))
                print(f"LinkedIn posts cooldown: sleeping {pause_seconds}s before next batch")
                time.sleep(pause_seconds)
                continue
            break

        raw_posts = result.get("posts", [])
        probe_errors = result.get("errors", []) or []
        if probe_errors:
            print(f"LinkedIn posts batch {batch_index} completed with {len(probe_errors)} non-fatal error(s).")
            for error in probe_errors[:5]:
                print(f"  - {error.get('query', 'unknown')}: {str(error.get('error', ''))[:180]}")

        posts = [post for post in raw_posts if _passes_filters(post)]
        filtered_by_query: Dict[str, int] = {}
        for post in posts:
            query = str(post.get("query") or "")
            filtered_by_query[query] = filtered_by_query.get(query, 0) + 1
        plan_records = []
        for plan_result in result.get("plan_results", []) or []:
            query = str(plan_result.get("query") or "")
            plan_records.append(
                _post_plan_record(
                    plan_result,
                    raw=int(plan_result.get("raw") or 0),
                    filtered=filtered_by_query.get(query, 0),
                    elapsed_ms=plan_result.get("elapsed_ms"),
                    error=str(plan_result.get("error") or "") or None,
                )
            )
        if not plan_records:
            raw_by_query: Dict[str, int] = {}
            for post in raw_posts:
                query = str(post.get("query") or "")
                raw_by_query[query] = raw_by_query.get(query, 0) + 1
            plan_records = [
                _post_plan_record(
                    plan,
                    raw=raw_by_query.get(str(plan.get("query") or ""), 0),
                    filtered=filtered_by_query.get(str(plan.get("query") or ""), 0),
                    elapsed_ms=None,
                    error=None,
                )
                for plan in plans
            ]
        _write_post_records(route_output_dir, plan_records)
        jobs = [_to_job(post) for post in posts]
        from utils.db import Database
        from utils.scoring import calculate_match_score
        from utils.utils import load_resume_text

        resume_text = load_resume_text()
        db = Database(OUTPUT_DIR / "jobs.sqlite3")
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
    targets_path = route_output_dir / "targets.jsonl"
    if targets_path.exists():
        records = [json.loads(line) for line in targets_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        write_markdown_summary(route_output_dir / "summary.md", run_id=route_run_id, records=records)
        print(f"LinkedIn posts route summary: {route_output_dir / 'summary.md'}")
        _send_telegram(
            render_compact_telegram_summary(
                run_id=route_run_id,
                records=records,
                summary_path=route_output_dir / "summary.md",
            )
        )


if __name__ == "__main__":
    try:
        acquire_lock()
        _set_stage("main")
        _check_playwright_ready()
        main()
    except LoginRequiredError as exc:
        print(f"LINKEDIN_LOGIN_REQUIRED: {exc}", flush=True)
        _send_telegram("⚠️ LinkedIn 로그인이 필요합니다. 브라우저에서 로그인한 뒤 /posts를 다시 실행해주세요.")
        raise SystemExit(2)
    except CheckpointRequiredError as exc:
        print(f"LINKEDIN_CHECKPOINT_REQUIRED: {exc}", flush=True)
        _send_telegram("⚠️ LinkedIn 추가 인증이 필요합니다. 로그인 Chrome에서 checkpoint/captcha를 완료한 뒤 /posts를 다시 실행해주세요.")
        raise SystemExit(3)
    except StageTimeoutError as exc:
        print(f"LINKEDIN_POST_TIMEOUT: stage={exc.stage} seconds={exc.seconds}", flush=True)
        _send_telegram(f"⚠️ LinkedIn posts timeout: {exc.stage} 단계에서 {exc.seconds}s 초과")
        raise SystemExit(124)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"LINKEDIN_POST_FAILED: stage={CURRENT_STAGE} error={repr(exc)}", flush=True)
        _send_telegram(f"⚠️ LinkedIn posts 실패: {CURRENT_STAGE} 단계 ({repr(exc)})")
        raise
    finally:
        if _env_bool("LINKEDIN_CLOSE_CHROME_AFTER", False):
            _kill_profile_processes()
        release_lock()
