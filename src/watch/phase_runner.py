#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.queue_exporter import export_high_scoring_jobs
from utils.collection_config import (
    CollectionPhase,
    SelectorResolution,
    NEWS_RSS_FEEDS,
    PLAYER_RSS_FEEDS,
    REGISTRY,
    discovery_keyword_groups,
    discovery_target_groups,
    keyword_phase_ids,
    phase_registry,
    resolve_phase_id,
    resolve_selector,
    selector_phase_ids,
    validate_registry,
)
from utils.config import DB_PATH, OUTPUT_DIR
from utils.db import Database
from utils.scrapers import fetch_rss_news

ROOT = Path(__file__).resolve().parents[2]
SUMMARY_DIR = Path(os.getenv("PHASE_RUN_OUTPUT_DIR") or OUTPUT_DIR / "phase_runs")
STATUS_PATH = Path(os.getenv("PHASE_STATUS_PATH") or OUTPUT_DIR / "phase_status.json")
LOCK_DIR = Path(os.getenv("PHASE_LOCK_DIR") or OUTPUT_DIR / "phase_locks")
VALID_STATUSES = {"success", "partial_success", "failed", "timeout", "skipped", "locked", "dry_run", "disabled"}


class PhaseRunError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_default(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return str(value)


@contextlib.contextmanager
def _capture_process_output() -> Any:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    handlers: list[tuple[logging.Handler, Any]] = []
    for logger_name in ("", "scraper", "watch_loop", "notifications", "jobspy_progress"):
        logger = logging.getLogger(logger_name)
        for handler in logger.handlers:
            if hasattr(handler, "stream"):
                handlers.append((handler, handler.stream))
                handler.stream = stdout_buffer
    try:
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            yield stdout_buffer, stderr_buffer
    finally:
        for handler, stream in handlers:
            handler.stream = stream


def _base_summary(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    started_at = _utc_now()
    return {
        "run_id": f"{started_at.replace(':', '').replace('-', '')}-{phase.id}-{uuid.uuid4().hex[:8]}",
        "phase": phase.id,
        "label": phase.label,
        "status": "running",
        "dry_run": dry_run,
        "requested_target": target,
        "target": target,
        "requested_by": os.getenv("PHASE_REQUESTED_BY") or os.getenv("USER") or "cli",
        "started_at": started_at,
        "completed_at": None,
        "duration_seconds": 0.0,
        "counts": {
            "raw": None,
            "parsed": None,
            "filtered": None,
            "inserted": None,
            "updated": None,
            "notified": None,
            "exported": None,
        },
        "source_results": [],
        "phase_results": [],
        "side_effects": {
            "database": False,
            "dashboard": False,
            "telegram": False,
            "queue": False,
            "outputs": [],
        },
        "errors": [],
        "metadata": {
            "execution_mode": phase.execution_mode,
            "timeout_seconds": phase.timeout_seconds,
            "writes_database": phase.writes_database,
            "sends_notification": phase.sends_notification,
            "full_run_included": phase.full_run_included,
            "python_executable": sys.executable,
            "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        },
    }


def _finish_summary(summary: dict[str, Any], status: str, started: float) -> dict[str, Any]:
    summary["status"] = status
    summary["completed_at"] = _utc_now()
    summary["duration_seconds"] = round(time.time() - started, 3)
    return summary


def _write_summary(summary: dict[str, Any]) -> None:
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    path = SUMMARY_DIR / f"{summary['run_id']}.json"
    summary["summary_path"] = str(path)
    tmp_path = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    tmp_path.replace(path)
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if STATUS_PATH.exists():
        try:
            current = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    current[str(summary["phase"])] = {
        "status": summary.get("status"),
        "run_id": summary.get("run_id"),
        "completed_at": summary.get("completed_at"),
        "summary_path": str(path),
        "target": summary.get("target"),
    }
    tmp_status = STATUS_PATH.with_suffix(STATUS_PATH.suffix + f".tmp.{os.getpid()}")
    tmp_status.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_status.replace(STATUS_PATH)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _read_lock(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _active_locks() -> list[tuple[Path, dict[str, Any]]]:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    active: list[tuple[Path, dict[str, Any]]] = []
    for path in LOCK_DIR.glob("*.lock"):
        info = _read_lock(path)
        pid = int((info or {}).get("pid") or 0)
        if info and _pid_alive(pid):
            active.append((path, info))
        else:
            path.unlink(missing_ok=True)
    return active


class PhaseLock:
    def __init__(self, phase: CollectionPhase, run_id: str):
        self.phase = phase
        self.run_id = run_id
        self.path = LOCK_DIR / f"{phase.id}.lock"
        self.acquired = False

    def acquire(self) -> dict[str, Any] | None:
        for _, info in _active_locks():
            active_phase = str(info.get("phase") or "")
            if self.phase.id == "all" or active_phase == "all" or active_phase == self.phase.id:
                return info
        payload = {
            "pid": os.getpid(),
            "phase": self.phase.id,
            "run_id": self.run_id,
            "started_at": _utc_now(),
        }
        LOCK_DIR.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            _active_locks()
            if self.path.exists():
                return _read_lock(self.path) or {"phase": self.phase.id, "pid": None}
            return self.acquire()
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
        self.acquired = True
        return None

    def release(self) -> None:
        if not self.acquired:
            return
        info = _read_lock(self.path)
        if info and info.get("run_id") == self.run_id:
            self.path.unlink(missing_ok=True)
        self.acquired = False


def _run_subprocess(
    phase: CollectionPhase,
    command: list[str],
    *,
    env_updates: dict[str, str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    summary = _base_summary(phase, target=env_updates.get("PHASE_TARGET") if env_updates else None, dry_run=dry_run)
    summary["metadata"]["command"] = command
    if dry_run:
        summary["status"] = "dry_run"
        return summary

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", f"{ROOT / 'src'}:{env.get('PYTHONPATH', '')}")
    env.setdefault("PYTHON_BIN", sys.executable)
    if env_updates:
        env.update(env_updates)
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=phase.timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, 15)
            time.sleep(1)
            os.killpg(process.pid, 9)
        except Exception:
            pass
        stdout, stderr = process.communicate()
        summary["errors"].append(f"timeout after {phase.timeout_seconds}s")
        summary["metadata"]["stdout_tail"] = (stdout or exc.stdout or "")[-4000:]
        summary["metadata"]["stderr_tail"] = (stderr or exc.stderr or "")[-4000:]
        summary["status"] = "timeout"
        return summary

    output = (stdout or "") + (stderr or "")
    summary["metadata"]["returncode"] = process.returncode
    summary["metadata"]["log_tail"] = output[-4000:]
    if process.returncode == 0:
        summary["status"] = "success"
    elif process.returncode in {2, 75}:
        summary["status"] = "partial_success" if process.returncode == 2 else "locked"
        summary["errors"].append(f"exit code {process.returncode}")
    else:
        summary["status"] = "failed"
        summary["errors"].append(f"exit code {process.returncode}")

    if summary["status"] == "success" and ("Final status: partial_success" in output or "status=partial_success" in output):
        summary["status"] = "partial_success"
        summary["errors"].append("child runner reported partial_success")
    posts_match = re.search(
        r"LinkedIn posts:\s+raw=(\d+)\s+filtered=(\d+)\s+inserted=(\d+)\s+notified=(\d+)\s+errors=(\d+)",
        output,
    )
    if posts_match:
        raw, filtered, inserted, notified, errors = (int(value) for value in posts_match.groups())
        summary["counts"]["raw"] = raw
        summary["counts"]["filtered"] = filtered
        summary["counts"]["inserted"] = inserted
        summary["counts"]["notified"] = notified
        if errors and summary["status"] == "success":
            summary["status"] = "partial_success"
            summary["errors"].append(f"child runner reported errors={errors}")
    return summary


FIXED_SOURCES = "jobvite_pragmaticplay,smartrecruitment,igamingrecruitment,igaminghunt_bamboohr,jobrapido_uae,jobleads"
LINKEDIN_SOURCES = "linkedin_public,linkedin_emea,linkedin_georgia,linkedin_malta"
INDEED_SOURCES = "indeed_uae,indeed_georgia,indeed_malta"
SELECTOR_PHASES = {"fixed", "drjobs", "linkedin", "indeed", "jobspy", "glassdoor", "rss", "player", "posts", "recruiters"}


def _selector_target_ids(selection: SelectorResolution | None) -> list[str]:
    if not selection:
        return []
    seen: set[str] = set()
    ids: list[str] = []
    for target in selection.targets:
        if target.target_id and target.target_id not in seen:
            ids.append(target.target_id)
            seen.add(target.target_id)
    return ids


def _selector_urls(selection: SelectorResolution | None) -> list[str]:
    if not selection:
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for target in selection.targets:
        if target.url and target.url not in seen:
            urls.append(target.url)
            seen.add(target.url)
    return urls


def _selector_sources(selection: SelectorResolution | None) -> list[str]:
    if not selection:
        return []
    seen: set[str] = set()
    sources: list[str] = []
    for target in selection.targets:
        if target.source and target.source not in seen:
            sources.append(target.source)
            seen.add(target.source)
    return sources


def _selector_countries(selection: SelectorResolution | None) -> list[str]:
    if not selection:
        return []
    seen: set[str] = set()
    countries: list[str] = []
    for target in selection.targets:
        if target.country and target.country not in seen:
            countries.append(target.country)
            seen.add(target.country)
    return countries


def _selector_url_count(selection: SelectorResolution | None) -> int:
    if not selection:
        return 0
    if selection.phase == "posts":
        posts_config = (REGISTRY.get("sources", {}) or {}).get("linkedin_posts", {}) or {}
        roles = [role for role in posts_config.get("roles", []) or [] if isinstance(role, dict)]
        leads = [lead for lead in posts_config.get("leads", []) or [] if isinstance(lead, dict)]
        role_ids = set(selection.keyword_group_ids)
        if role_ids:
            roles = [
                role
                for role in roles
                if str(role.get("id") or "") in role_ids or str(role.get("domain") or "") in role_ids
            ]
        return max(1, len(selection.targets)) * len(roles) * len(leads)
    return len(_selector_urls(selection)) or len(selection.targets)


def _selector_filter_env(selection: SelectorResolution | None) -> dict[str, str]:
    if not selection:
        return {}
    payload = {
        "phase": selection.phase,
        "selector": selection.selector,
        "match_kind": selection.match_kind,
        "target_ids": _selector_target_ids(selection),
        "urls": _selector_urls(selection),
        "keyword_group_ids": list(selection.keyword_group_ids),
        "keyword_queries": list(selection.keyword_queries),
    }
    return {"COLLECTION_TARGET_FILTER_JSON": json.dumps(payload, ensure_ascii=False, sort_keys=True)}


def _format_resolution(selection: SelectorResolution | None, phase: CollectionPhase) -> str:
    if not selection:
        return ""
    return "\n".join(
        [
            f"Resolved Phase : {phase.id}",
            f"Resolved Target Group : {selection.target_group_id or selection.selector}",
            f"Resolved Keyword Group : {selection.keyword_group_id or '-'}",
            f"Resolved Targets : {len(_selector_target_ids(selection))}",
            f"Resolved URL Count : {_selector_url_count(selection)}",
            f"Country : {', '.join(_selector_countries(selection)) or '-'}",
            f"Source : {', '.join(_selector_sources(selection)) or '-'}",
            "Running...",
        ]
    )


def _scraper_env_for_phase(
    phase_id: str,
    target: str | None = None,
    selection: SelectorResolution | None = None,
) -> dict[str, str]:
    env = {
        "SKIP_NEWS": "1",
        "SKIP_LINKEDIN_BROWSER": "1",
        "SKIP_INDEED_BROWSER": "1",
        "SKIP_JOBSPY": "1",
        "SKIP_DRJOBS_BROWSER": "1",
        "SKIP_GLASSDOOR_BROWSER": "1",
    }
    if target:
        env["PHASE_TARGET"] = target
    env.update(_selector_filter_env(selection))
    selected_sources = ",".join(_selector_sources(selection))
    if phase_id == "fixed":
        env["JOB_WATCH_SOURCES"] = selected_sources or FIXED_SOURCES
    elif phase_id == "drjobs":
        env["JOB_WATCH_SOURCES"] = selected_sources or "drjobs"
        env["SKIP_DRJOBS_BROWSER"] = "0"
    elif phase_id == "linkedin":
        env["JOB_WATCH_SOURCES"] = selected_sources or LINKEDIN_SOURCES
        env["SKIP_LINKEDIN_BROWSER"] = "0"
    elif phase_id == "indeed":
        env["JOB_WATCH_SOURCES"] = selected_sources or INDEED_SOURCES
        env["SKIP_INDEED_BROWSER"] = "0"
    elif phase_id == "jobspy":
        env["JOB_WATCH_SOURCES"] = selected_sources or INDEED_SOURCES
        env["SKIP_JOBSPY"] = "0"
    elif phase_id == "recruiters":
        env["JOB_WATCH_SOURCES"] = selected_sources or "linkedin_public"
        env["SKIP_LINKEDIN_BROWSER"] = "0"
    return env


def _run_scraper_phase(
    phase: CollectionPhase,
    *,
    target: str | None,
    dry_run: bool,
    selection: SelectorResolution | None = None,
) -> dict[str, Any]:
    return _run_subprocess(
        phase,
        [sys.executable, "src/watch/scraper.py", "collect"],
        env_updates=_scraper_env_for_phase(phase.id, target, selection),
        dry_run=dry_run,
    )


def _run_all(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    return _run_subprocess(phase, ["/bin/bash", "run_collect_once.sh"], env_updates={}, dry_run=dry_run)


def _run_glassdoor(
    phase: CollectionPhase,
    *,
    target: str | None,
    dry_run: bool,
    selection: SelectorResolution | None = None,
) -> dict[str, Any]:
    updates = {"PHASE_TARGET": target} if target else {}
    updates.update(_selector_filter_env(selection))
    return _run_subprocess(phase, ["/bin/bash", "run_glassdoor.sh"], env_updates=updates, dry_run=dry_run)


def _run_posts(
    phase: CollectionPhase,
    *,
    target: str | None,
    dry_run: bool,
    selection: SelectorResolution | None = None,
) -> dict[str, Any]:
    updates: dict[str, str] = {}
    command = ["/bin/bash", "run_linkedin_posts.sh"]
    if target:
        updates["PHASE_TARGET"] = target
    updates.update(_selector_filter_env(selection))
    if target and not selection:
        if not target.isdigit() or int(target) <= 0:
            summary = _base_summary(phase, target=target, dry_run=dry_run)
            summary["status"] = "failed"
            summary["errors"].append("posts --target currently supports a positive plan number only")
            return summary
        command.extend([target, str(int(target))])
    return _run_subprocess(phase, command, env_updates=updates, dry_run=dry_run)


def _matching_feeds(feeds: list[dict[str, Any]], target: str | None) -> list[dict[str, Any]]:
    if not target:
        return feeds
    needle = target.strip().lower()
    return [
        feed for feed in feeds
        if needle in str(feed.get("id", "")).lower()
        or needle in str(feed.get("source", "")).lower()
        or needle in str(feed.get("label", "")).lower()
    ]


def _run_feed_phase(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    summary = _base_summary(phase, target=target, dry_run=dry_run)
    feeds = NEWS_RSS_FEEDS if phase.id == "rss" else PLAYER_RSS_FEEDS
    if target:
        target_ids = set(_selector_target_ids(resolve_selector(phase.id, target)))
        feeds = [feed for feed in feeds if str(feed.get("id") or "") in target_ids] if target_ids else []
    summary["targets"] = [{"id": feed.get("id"), "source": feed.get("source"), "url": feed.get("url")} for feed in feeds]
    if target and not feeds:
        summary["status"] = "failed"
        summary["errors"].append(f"target not found: {target}")
        return summary
    if dry_run:
        summary["counts"]["raw"] = len(feeds)
        summary["status"] = "dry_run"
        return summary
    with _capture_process_output() as (captured_stdout, captured_stderr):
        items = []
        for feed in feeds:
            try:
                items.extend(fetch_rss_news(str(feed.get("url") or ""), str(feed.get("source") or "")))
            except Exception as exc:
                summary["errors"].append(f"{feed.get('id')}: {type(exc).__name__}: {exc}")
        db = Database(DB_PATH)
        inserted, inserted_items = db.upsert_news(items, return_items=True)
    summary["counts"]["raw"] = len(items)
    summary["counts"]["parsed"] = len(items)
    summary["counts"]["inserted"] = inserted
    summary["side_effects"]["database"] = True
    summary["status"] = "partial_success" if summary["errors"] else "success"
    summary["metadata"]["inserted_items"] = [item.to_dict() for item in inserted_items[:20]]
    summary["metadata"]["log_tail"] = (captured_stdout.getvalue() + captured_stderr.getvalue())[-4000:]
    return summary


def _run_telegram(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    updates = {"DB_PATH": str(DB_PATH)}
    if target:
        updates["PHASE_TARGET"] = target
    return _run_subprocess(phase, [sys.executable, "src/services/telegram_scraper.py"], env_updates=updates, dry_run=dry_run)


def _run_queue(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    summary = _base_summary(phase, target=target, dry_run=dry_run)
    if dry_run:
        summary["status"] = "dry_run"
        return summary
    min_score = int(os.getenv("PHASE_QUEUE_MIN_SCORE", "60"))
    with _capture_process_output() as (captured_stdout, captured_stderr):
        result = export_high_scoring_jobs(str(DB_PATH), min_score=min_score)
    summary["counts"]["raw"] = int(result.get("candidate_count") or 0)
    summary["counts"]["exported"] = int(result.get("newly_exported_count") or result.get("count") or 0)
    summary["side_effects"]["queue"] = True
    summary["metadata"]["queue_result"] = result
    summary["metadata"]["log_tail"] = (captured_stdout.getvalue() + captured_stderr.getvalue())[-4000:]
    summary["status"] = "failed" if result.get("status") == "failed" else "success"
    if result.get("error"):
        summary["errors"].append(str(result.get("error")))
    return summary


def _run_dashboard(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    summary = _base_summary(phase, target=target, dry_run=dry_run)
    paths = [OUTPUT_DIR / "jobs_analysis.json", OUTPUT_DIR / "job_stats_data.json"]
    summary["side_effects"]["outputs"] = [str(path) for path in paths if path.exists()]
    summary["counts"]["raw"] = len(summary["side_effects"]["outputs"])
    summary["status"] = "dry_run" if dry_run else ("success" if summary["side_effects"]["outputs"] else "failed")
    if summary["status"] == "failed":
        summary["errors"].append("dashboard output files not found")
    return summary


def _run_notifications(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    summary = _base_summary(phase, target=target, dry_run=dry_run)
    summary["metadata"]["telegram_configured"] = bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))
    summary["status"] = "dry_run" if dry_run else "success"
    return summary


Handler = Callable[[CollectionPhase], dict[str, Any]]


def _handlers(
    target: str | None,
    dry_run: bool,
    selection: SelectorResolution | None = None,
) -> dict[str, Callable[[CollectionPhase], dict[str, Any]]]:
    return {
        "all": lambda phase: _run_all(phase, target=target, dry_run=dry_run),
        "fixed": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run, selection=selection),
        "drjobs": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run, selection=selection),
        "linkedin": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run, selection=selection),
        "indeed": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run, selection=selection),
        "jobspy": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run, selection=selection),
        "glassdoor": lambda phase: _run_glassdoor(phase, target=target, dry_run=dry_run, selection=selection),
        "rss": lambda phase: _run_feed_phase(phase, target=target, dry_run=dry_run),
        "player": lambda phase: _run_feed_phase(phase, target=target, dry_run=dry_run),
        "telegram": lambda phase: _run_telegram(phase, target=target, dry_run=dry_run),
        "posts": lambda phase: _run_posts(phase, target=target, dry_run=dry_run, selection=selection),
        "recruiters": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run, selection=selection),
        "queue": lambda phase: _run_queue(phase, target=target, dry_run=dry_run),
        "dashboard": lambda phase: _run_dashboard(phase, target=target, dry_run=dry_run),
        "notifications": lambda phase: _run_notifications(phase, target=target, dry_run=dry_run),
    }


def validate_phase_handlers() -> tuple[list[str], list[str]]:
    handlers = _handlers(target=None, dry_run=True)
    errors: list[str] = []
    target_resolvers = {"fixed", "drjobs", "linkedin", "indeed", "jobspy", "glassdoor", "rss", "player", "posts", "recruiters"}
    for phase in phase_registry():
        if phase.enabled and phase.id not in handlers:
            errors.append(f"runtime.phases[{phase.id}]: enabled phase has no execution handler")
        if phase.enabled and phase.supports_target and phase.id not in target_resolvers:
            errors.append(f"runtime.phases[{phase.id}]: supports_target=true but no target resolver exists")
    return errors, []


def _phase_by_id(phase_id: str) -> CollectionPhase | None:
    return next((phase for phase in phase_registry() if phase.id == phase_id), None)


def _suggest_phase(value: str) -> str:
    candidates = sorted({phase.id for phase in phase_registry()} | set(alias for phase in phase_registry() for alias in phase.aliases))
    suggestion = difflib.get_close_matches(value, candidates, n=1)
    return suggestion[0] if suggestion else ""


def list_phases(phase_name: str | None = None, selector: str | None = None) -> int:
    if phase_name:
        resolved = resolve_phase_id(phase_name)
        if not resolved or resolved in {"help", "list"}:
            suggestion = _suggest_phase(phase_name)
            suffix = f" Did you mean '{suggestion}'?" if suggestion else ""
            print(f"Unknown phase: {phase_name}.{suffix}")
            print("Available phases: " + ", ".join(phase.id for phase in phase_registry() if phase.telegram_visible))
            return 2
        phase = _phase_by_id(resolved)
        if not phase:
            print(f"Unknown phase: {phase_name}")
            return 2
        if not phase.supports_target:
            print(f"{phase.id}\nselector -\nkeyword -")
            return 0
        if selector:
            status, keywords, candidates, message = discovery_keyword_groups(phase.id, selector)
            if status != "ok":
                print(message or f"No keyword groups found for {phase.id} {selector}.")
                if candidates:
                    print("Candidates: " + ", ".join(candidates))
                return 2 if status in {"unknown", "ambiguous"} else 0
            print(f"{phase.id} {selector} keyword groups")
            for keyword in keywords:
                aliases = keyword.get("aliases") or []
                alias_text = f" aliases: {', '.join(aliases)}" if aliases else ""
                print(f"- {keyword.get('id')}: {keyword.get('label')}{alias_text}")
            return 0
        status, groups = discovery_target_groups(phase.id)
        if status != "ok":
            print(f"{phase.id}\nNo selectable target groups.")
            return 0
        print(f"{phase.id} target groups")
        for group in groups:
            aliases = group.get("aliases") or []
            alias_text = f" aliases: {', '.join(aliases)}" if aliases else ""
            print(f"- {group.get('label') or group.get('id')}{alias_text}")
            print(f"  Targets: {group.get('target_count')}")
            print(f"  URLs: {group.get('url_count')}")
            if phase.id in keyword_phase_ids():
                print(f"  Keywords: {group.get('keyword_count')}")
        return 0

    for phase in phase_registry():
        if not phase.telegram_visible:
            continue
        selector = "✓" if phase.id in selector_phase_ids() and phase.supports_target else "-"
        keyword = "✓" if phase.id in keyword_phase_ids() and phase.supports_target else "-"
        print(f"{phase.id} - {phase.label}")
        print(f"selector {selector}")
        if selector == "✓":
            print(f"keyword {keyword}")
    return 0


def show_help() -> int:
    lines = [
        "Phase 전체",
        "/collect <phase>",
        "",
        "Target Group",
        "/collect <phase> <selector>",
        "",
        "Keyword Group",
        "/collect <phase> <selector> <subselector>",
        "",
        "RSS",
        "/collect rss <feed_id>",
        "",
        "Posts",
        "/collect posts <location> <role>",
        "",
        "Examples",
    ]
    examples = []
    for phase in phase_registry():
        if phase.id in {"linkedin", "indeed", "rss", "posts"} and phase.telegram_visible:
            status, groups = discovery_target_groups(phase.id)
            if status != "ok" or not groups:
                continue
            aliases = groups[0].get("aliases") or []
            selector = aliases[0] if aliases else groups[0]["id"]
            if phase.id == "rss":
                examples.append(f"/collect {phase.id} {selector}")
                continue
            kw_status, keywords, _, _ = discovery_keyword_groups(phase.id, selector)
            if kw_status == "ok" and keywords:
                examples.append(f"/collect {phase.id} {selector} {keywords[0]['id']}")
            else:
                examples.append(f"/collect {phase.id} {selector}")
    lines.extend(examples[:6])
    print("\n".join(lines))
    return 0


def show_status() -> int:
    active = [
        {
            "phase": info.get("phase"),
            "pid": info.get("pid"),
            "run_id": info.get("run_id"),
            "started_at": info.get("started_at"),
        }
        for _, info in _active_locks()
    ]
    if not STATUS_PATH.exists():
        print(json.dumps({"status": "empty", "active_runs": active, "path": str(STATUS_PATH)}, ensure_ascii=False, indent=2))
        return 0
    try:
        latest = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        latest = {}
    print(json.dumps({"status": "ok", "active_runs": active, "latest": latest}, ensure_ascii=False, indent=2))
    return 0


def run_phase(
    phase_name: str,
    *,
    target: str | None,
    subselector: str | None = None,
    dry_run: bool,
    write_summary: bool = True,
) -> int:
    registry_errors, registry_warnings = validate_registry()
    handler_errors, _ = validate_phase_handlers()
    errors = [*registry_errors, *handler_errors]
    if errors:
        print(json.dumps({"status": "invalid_registry", "errors": errors, "warnings": registry_warnings}, ensure_ascii=False, indent=2))
        return 2

    resolved = resolve_phase_id(phase_name)
    if resolved == "help":
        return show_help()
    if resolved == "list":
        return list_phases()
    if not resolved:
        candidates = sorted({phase.id for phase in phase_registry()} | set(resolve_phase_id(alias) or alias for phase in phase_registry() for alias in phase.aliases))
        suggestion = difflib.get_close_matches(phase_name, candidates, n=1)
        suffix = f" Did you mean '{suggestion[0]}'?" if suggestion else ""
        print(f"Unknown phase: {phase_name}.{suffix}")
        return 2
    phase = _phase_by_id(resolved)
    if not phase:
        print(f"Unknown phase: {phase_name}")
        return 2
    if not phase.enabled:
        print(json.dumps({"phase": phase.id, "status": "disabled"}, ensure_ascii=False, indent=2))
        return 0
    if target and not phase.supports_target:
        print(json.dumps({"phase": phase.id, "status": "invalid_target", "error": "phase does not support --target"}, ensure_ascii=False, indent=2))
        return 2
    selection: SelectorResolution | None = None
    if subselector and not target:
        print(json.dumps({"phase": phase.id, "status": "invalid_target", "error": "subselector requires selector"}, ensure_ascii=False, indent=2))
        return 2
    if subselector and phase.id in {"rss", "player", "fixed"}:
        print(json.dumps({"phase": phase.id, "status": "invalid_target", "error": "phase does not support subselector"}, ensure_ascii=False, indent=2))
        return 2
    if target and phase.id in SELECTOR_PHASES and not (phase.id == "posts" and target.isdigit() and not subselector):
        selection = resolve_selector(phase.id, target, subselector)
        if selection.status != "matched":
            print(
                json.dumps(
                    {
                        "phase": phase.id,
                        "target": target,
                        "subselector": subselector,
                        "status": "invalid_target",
                        "error": selection.message or f"target not found: {target}",
                        "candidates": list(selection.candidates),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2
        print(_format_resolution(selection, phase), file=sys.stderr)
    elif not target and phase.id == "recruiters":
        selection = resolve_selector(phase.id, "")

    started = time.time()
    if dry_run:
        summary = _handlers(target=target, dry_run=True, selection=selection)[phase.id](phase)
        if selection:
            summary["resolved_selector"] = {
                "selector": selection.selector,
                "subselector": selection.subselector,
                "match_kind": selection.match_kind,
                "target_group_id": selection.target_group_id,
                "keyword_group_id": selection.keyword_group_id,
                "target_ids": _selector_target_ids(selection),
                "url_count": _selector_url_count(selection),
                "countries": _selector_countries(selection),
                "sources": _selector_sources(selection),
                "keyword_group_ids": list(selection.keyword_group_ids),
            }
            summary["counts"]["attempted_targets"] = len(_selector_target_ids(selection))
        if summary.get("completed_at") is None:
            _finish_summary(summary, str(summary.get("status") or "dry_run"), started)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default))
        return 0 if summary.get("status") == "dry_run" else 1

    pre_summary = _base_summary(phase, target=target, dry_run=False)
    lock = PhaseLock(phase, str(pre_summary["run_id"]))
    conflict = lock.acquire()
    if conflict:
        summary = _finish_summary(pre_summary, "locked", started)
        summary["errors"].append(f"phase already running: {conflict.get('phase')}")
        summary["metadata"]["conflict"] = {
            "phase": conflict.get("phase"),
            "pid": conflict.get("pid"),
            "run_id": conflict.get("run_id"),
        }
        if write_summary:
            _write_summary(summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default))
        return 75
    try:
        summary = _handlers(target=target, dry_run=False, selection=selection)[phase.id](phase)
        summary["run_id"] = pre_summary["run_id"]
        summary["requested_by"] = pre_summary["requested_by"]
        if selection:
            summary["resolved_selector"] = {
                "selector": selection.selector,
                "subselector": selection.subselector,
                "match_kind": selection.match_kind,
                "target_group_id": selection.target_group_id,
                "keyword_group_id": selection.keyword_group_id,
                "target_ids": _selector_target_ids(selection),
                "url_count": _selector_url_count(selection),
                "countries": _selector_countries(selection),
                "sources": _selector_sources(selection),
                "keyword_group_ids": list(selection.keyword_group_ids),
            }
            summary["counts"]["attempted_targets"] = len(_selector_target_ids(selection))
        if summary.get("completed_at") is None:
            _finish_summary(summary, str(summary.get("status") or "success"), started)
        if write_summary:
            _write_summary(summary)
    finally:
        lock.release()
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default))
    return 0 if summary.get("status") in {"success", "dry_run", "partial_success", "locked"} else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="phase_runner")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("help")
    list_parser = sub.add_parser("list")
    list_parser.add_argument("phase", nargs="?")
    list_parser.add_argument("selector", nargs="?")
    sub.add_parser("status")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("phase")
    run_parser.add_argument("--target")
    run_parser.add_argument("--subselector")
    run_parser.add_argument("--requested-by")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--no-summary", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "help":
        return show_help()
    if args.command == "list":
        return list_phases(args.phase, args.selector)
    if args.command == "status":
        return show_status()
    if args.command == "run":
        if args.requested_by:
            os.environ["PHASE_REQUESTED_BY"] = args.requested_by
        return run_phase(args.phase, target=args.target, subselector=args.subselector, dry_run=args.dry_run, write_summary=not args.no_summary)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
