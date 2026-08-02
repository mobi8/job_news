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
    NEWS_RSS_FEEDS,
    PLAYER_RSS_FEEDS,
    phase_registry,
    resolve_phase_id,
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


def _scraper_env_for_phase(phase_id: str, target: str | None = None) -> dict[str, str]:
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
    if phase_id == "fixed":
        env["JOB_WATCH_SOURCES"] = target or FIXED_SOURCES
    elif phase_id == "drjobs":
        env["JOB_WATCH_SOURCES"] = target or "drjobs"
        env["SKIP_DRJOBS_BROWSER"] = "0"
    elif phase_id == "linkedin":
        env["JOB_WATCH_SOURCES"] = target or LINKEDIN_SOURCES
        env["SKIP_LINKEDIN_BROWSER"] = "0"
    elif phase_id == "indeed":
        env["JOB_WATCH_SOURCES"] = target or INDEED_SOURCES
        env["SKIP_INDEED_BROWSER"] = "0"
    elif phase_id == "jobspy":
        env["JOB_WATCH_SOURCES"] = target or INDEED_SOURCES
        env["SKIP_JOBSPY"] = "0"
    return env


def _run_scraper_phase(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    return _run_subprocess(
        phase,
        [sys.executable, "src/watch/scraper.py", "collect"],
        env_updates=_scraper_env_for_phase(phase.id, target),
        dry_run=dry_run,
    )


def _run_all(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    return _run_subprocess(phase, ["/bin/bash", "run_collect_once.sh"], env_updates={}, dry_run=dry_run)


def _run_glassdoor(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    updates = {"PHASE_TARGET": target} if target else {}
    return _run_subprocess(phase, ["/bin/bash", "run_glassdoor.sh"], env_updates=updates, dry_run=dry_run)


def _run_posts(phase: CollectionPhase, *, target: str | None, dry_run: bool) -> dict[str, Any]:
    updates: dict[str, str] = {}
    command = ["/bin/bash", "run_linkedin_posts.sh"]
    if target:
        if not target.isdigit() or int(target) <= 0:
            summary = _base_summary(phase, target=target, dry_run=dry_run)
            summary["status"] = "failed"
            summary["errors"].append("posts --target currently supports a positive plan number only")
            return summary
        updates["PHASE_TARGET"] = target
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
    feeds = _matching_feeds(NEWS_RSS_FEEDS if phase.id == "rss" else PLAYER_RSS_FEEDS, target)
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


def _handlers(target: str | None, dry_run: bool) -> dict[str, Callable[[CollectionPhase], dict[str, Any]]]:
    return {
        "all": lambda phase: _run_all(phase, target=target, dry_run=dry_run),
        "fixed": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run),
        "drjobs": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run),
        "linkedin": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run),
        "indeed": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run),
        "jobspy": lambda phase: _run_scraper_phase(phase, target=target, dry_run=dry_run),
        "glassdoor": lambda phase: _run_glassdoor(phase, target=target, dry_run=dry_run),
        "rss": lambda phase: _run_feed_phase(phase, target=target, dry_run=dry_run),
        "player": lambda phase: _run_feed_phase(phase, target=target, dry_run=dry_run),
        "telegram": lambda phase: _run_telegram(phase, target=target, dry_run=dry_run),
        "posts": lambda phase: _run_posts(phase, target=target, dry_run=dry_run),
        "queue": lambda phase: _run_queue(phase, target=target, dry_run=dry_run),
        "dashboard": lambda phase: _run_dashboard(phase, target=target, dry_run=dry_run),
        "notifications": lambda phase: _run_notifications(phase, target=target, dry_run=dry_run),
    }


def validate_phase_handlers() -> tuple[list[str], list[str]]:
    handlers = _handlers(target=None, dry_run=True)
    errors: list[str] = []
    target_resolvers = {"rss", "player", "posts"}
    for phase in phase_registry():
        if phase.enabled and phase.id not in handlers:
            errors.append(f"runtime.phases[{phase.id}]: enabled phase has no execution handler")
        if phase.enabled and phase.supports_target and phase.id not in target_resolvers:
            errors.append(f"runtime.phases[{phase.id}]: supports_target=true but no target resolver exists")
    return errors, []


def _phase_by_id(phase_id: str) -> CollectionPhase | None:
    return next((phase for phase in phase_registry() if phase.id == phase_id), None)


def list_phases() -> int:
    for phase in phase_registry():
        aliases = ",".join(phase.aliases)
        print(f"{phase.id}\t{phase.label}\torder={phase.order}\tenabled={phase.enabled}\taliases={aliases}")
    return 0


def show_help() -> int:
    lines = [
        "Usage:",
        "  python -m src.watch.phase_runner list",
        "  python -m src.watch.phase_runner status",
        "  python -m src.watch.phase_runner run <phase> [--target TARGET] [--dry-run]",
        "",
        "Visible phases:",
    ]
    for phase in phase_registry():
        if not phase.telegram_visible:
            continue
        aliases = f" aliases: {', '.join(phase.aliases)}" if phase.aliases else ""
        lines.append(f"  {phase.id:<14} {phase.label}{aliases}")
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


def run_phase(phase_name: str, *, target: str | None, dry_run: bool, write_summary: bool = True) -> int:
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

    started = time.time()
    if dry_run:
        summary = _handlers(target=target, dry_run=True)[phase.id](phase)
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
        summary = _handlers(target=target, dry_run=False)[phase.id](phase)
        summary["run_id"] = pre_summary["run_id"]
        summary["requested_by"] = pre_summary["requested_by"]
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
    sub.add_parser("list")
    sub.add_parser("status")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("phase")
    run_parser.add_argument("--target")
    run_parser.add_argument("--requested-by")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--no-summary", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "help":
        return show_help()
    if args.command == "list":
        return list_phases()
    if args.command == "status":
        return show_status()
    if args.command == "run":
        if args.requested_by:
            os.environ["PHASE_REQUESTED_BY"] = args.requested_by
        return run_phase(args.phase, target=args.target, dry_run=args.dry_run, write_summary=not args.no_summary)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
