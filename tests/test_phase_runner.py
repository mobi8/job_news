#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from watch import phase_runner


def test_phase_runner_list_command(capsys):
    code = phase_runner.main(["list"])
    output = capsys.readouterr().out
    assert code == 0
    assert "linkedin" in output
    assert "rss" in output


def test_phase_runner_help_command(capsys):
    code = phase_runner.main(["help"])
    output = capsys.readouterr().out
    assert code == 0
    assert "Usage:" in output
    assert "Visible phases:" in output


def test_phase_runner_dry_run_posts_does_not_execute(capsys):
    code = phase_runner.main(["run", "posts", "--dry-run"])
    output = capsys.readouterr().out
    assert code == 0
    assert '"phase": "posts"' in output
    assert '"status": "dry_run"' in output


def test_phase_runner_dry_run_rss_target(capsys):
    code = phase_runner.main(["run", "rss", "--target", "igaming_business", "--dry-run"])
    output = capsys.readouterr().out
    assert code == 0
    assert '"phase": "rss"' in output
    assert '"target": "igaming_business"' in output
    assert '"status": "dry_run"' in output


def test_phase_runner_invalid_target_fails(capsys):
    code = phase_runner.main(["run", "rss", "--target", "invalid_target", "--dry-run"])
    output = capsys.readouterr().out
    assert code == 1
    assert '"status": "failed"' in output
    assert "target not found" in output


def test_phase_runner_unsupported_target_is_nonzero(capsys):
    code = phase_runner.main(["run", "linkedin", "--target", "linkedin_uae", "--dry-run"])
    output = capsys.readouterr().out
    assert code == 2
    assert '"status": "invalid_target"' in output


def test_phase_runner_unknown_phase_nonzero_with_suggestion(capsys):
    code = phase_runner.main(["run", "linkdin", "--dry-run"])
    output = capsys.readouterr().out
    assert code == 2
    assert "Unknown phase" in output
    assert "Did you mean" in output


def test_phase_runner_real_local_summary_written(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(phase_runner, "SUMMARY_DIR", tmp_path / "phase_runs")
    monkeypatch.setattr(phase_runner, "STATUS_PATH", tmp_path / "phase_status.json")
    monkeypatch.setattr(phase_runner, "LOCK_DIR", tmp_path / "phase_locks")
    code = phase_runner.main(["run", "notifications", "--requested-by", "pytest"])
    output = capsys.readouterr().out
    assert code == 0
    payload = json.loads(output)
    assert payload["requested_by"] == "pytest"
    assert payload["status"] == "success"
    summary_path = Path(payload["summary_path"])
    assert summary_path.exists()
    saved = json.loads(summary_path.read_text())
    assert saved["phase"] == "notifications"
    assert saved["requested_target"] is None
    assert saved["metadata"]["python_version"]
    assert set(saved["counts"]) == {"raw", "parsed", "filtered", "inserted", "updated", "notified", "exported"}
    assert isinstance(saved["source_results"], list)
    assert isinstance(saved["phase_results"], list)
    status = json.loads((tmp_path / "phase_status.json").read_text())
    assert status["notifications"]["run_id"] == saved["run_id"]
    assert not any((tmp_path / "phase_locks").glob("*.lock"))


def test_phase_lock_conflict_and_stale_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(phase_runner, "LOCK_DIR", tmp_path)
    phase = next(item for item in phase_runner.phase_registry() if item.id == "dashboard")
    first = phase_runner.PhaseLock(phase, "run-a")
    assert first.acquire() is None
    second = phase_runner.PhaseLock(phase, "run-b")
    conflict = second.acquire()
    assert conflict and conflict["run_id"] == "run-a"
    first.release()
    stale = tmp_path / "dashboard.lock"
    stale.write_text(json.dumps({"pid": 99999999, "phase": "dashboard", "run_id": "stale"}))
    third = phase_runner.PhaseLock(phase, "run-c")
    assert third.acquire() is None
    third.release()


def test_phase_runner_locked_summary_written(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(phase_runner, "SUMMARY_DIR", tmp_path / "phase_runs")
    monkeypatch.setattr(phase_runner, "STATUS_PATH", tmp_path / "phase_status.json")
    monkeypatch.setattr(phase_runner, "LOCK_DIR", tmp_path / "phase_locks")
    lock_dir = tmp_path / "phase_locks"
    lock_dir.mkdir()
    lock_dir.joinpath("all.lock").write_text(json.dumps({"pid": os.getpid(), "phase": "all", "run_id": "active"}))
    code = phase_runner.main(["run", "notifications"])
    output = capsys.readouterr().out
    assert code == 75
    payload = json.loads(output)
    assert payload["status"] == "locked"
    assert Path(payload["summary_path"]).exists()


def test_run_subprocess_timeout_path():
    phase = next(item for item in phase_runner.phase_registry() if item.id == "dashboard")
    timeout_phase = replace(phase, timeout_seconds=1)
    result = phase_runner._run_subprocess(
        timeout_phase,
        [sys.executable, "-c", "import time; time.sleep(2)"],
        dry_run=False,
    )
    assert result["status"] == "timeout"
    assert result["errors"]


def test_latest_yaml_reload_via_subprocess(tmp_path):
    source = Path("config/collection_sources.yaml")
    copied = tmp_path / "collection_sources.yaml"
    text = source.read_text()
    copied.write_text(text.replace("    label: LinkedIn Jobs", "    label: LinkedIn Jobs Reloaded", 1))
    env = os.environ.copy()
    env["COLLECTION_SOURCES_CONFIG_PATH"] = str(copied)
    env["PYTHONPATH"] = str(Path("src").resolve())
    result = subprocess.run(
        [sys.executable, "-m", "src.watch.phase_runner", "list"],
        cwd=str(Path.cwd()),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "LinkedIn Jobs Reloaded" in result.stdout
