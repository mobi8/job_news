#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from utils import collection_config
from watch import phase_runner


def test_phase_runner_list_command(capsys):
    code = phase_runner.main(["list"])
    output = capsys.readouterr().out
    assert code == 0
    assert "linkedin" in output
    assert "selector ✓" in output
    assert "keyword ✓" in output
    assert "notifications" in output
    assert "selector -" in output


def test_phase_runner_help_command(capsys):
    code = phase_runner.main(["help"])
    output = capsys.readouterr().out
    assert code == 0
    assert "Phase 전체" in output
    assert "/collect <phase> <selector> <subselector>" in output


def test_phase_runner_list_phase_target_groups(capsys):
    code = phase_runner.main(["list", "linkedin"])
    output = capsys.readouterr().out
    assert code == 0
    assert "linkedin target groups" in output
    assert "UAE" in output
    assert "Targets:" in output
    assert "URLs:" in output
    assert "Keywords:" in output


def test_phase_runner_list_phase_selector_keywords(capsys):
    code = phase_runner.main(["list", "linkedin", "uae"])
    output = capsys.readouterr().out
    assert code == 0
    assert "linkedin uae keyword groups" in output
    assert "payments" in output
    assert "crypto" in output


def test_phase_runner_list_unknown_phase(capsys):
    code = phase_runner.main(["list", "linkdin"])
    output = capsys.readouterr().out
    assert code == 2
    assert "Unknown phase" in output
    assert "Available phases:" in output


def test_phase_runner_list_unknown_selector(capsys):
    code = phase_runner.main(["list", "linkedin", "korea"])
    output = capsys.readouterr().out
    assert code == 2
    assert "unknown selector" in output
    assert "Candidates:" in output


def test_phase_runner_list_selector_unsupported_phase(capsys):
    code = phase_runner.main(["list", "notifications"])
    output = capsys.readouterr().out
    assert code == 0
    assert "selector -" in output


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
    assert code == 2
    assert '"status": "invalid_target"' in output
    assert "unknown selector" in output


def test_phase_runner_linkedin_selector_target_id(capsys):
    code = phase_runner.main(["run", "linkedin", "--target", "linkedin_uae_crypto_payment", "--dry-run"])
    captured = capsys.readouterr()
    output = captured.out
    error = captured.err
    payload = json.loads(output)
    assert code == 0
    assert payload["resolved_selector"]["match_kind"] == "target_id"
    assert payload["resolved_selector"]["target_ids"] == ["linkedin_uae_crypto_payment"]
    assert payload["resolved_selector"]["url_count"] == 1
    assert "Resolved Phase : linkedin" in error


def test_phase_runner_linkedin_selector_country(capsys):
    code = phase_runner.main(["run", "linkedin", "--target", "uae", "--dry-run"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert code == 0
    assert payload["resolved_selector"]["match_kind"] == "target_group"
    assert payload["resolved_selector"]["target_group_id"] == "uae"
    assert payload["resolved_selector"]["url_count"] >= 10
    assert payload["resolved_selector"]["countries"] == ["UAE"]


def test_phase_runner_fixed_selector_partial(capsys):
    code = phase_runner.main(["run", "fixed", "--target", "jobvite", "--dry-run"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert code == 0
    assert payload["resolved_selector"]["match_kind"] in {"alias", "source", "partial"}
    assert payload["resolved_selector"]["target_ids"] == ["pragmatic_jobvite"]


def test_phase_runner_selector_ambiguous(capsys):
    code = phase_runner.main(["run", "linkedin", "--target", "linkedin_uae_crypto", "--dry-run"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert code == 2
    assert payload["status"] == "invalid_target"
    assert "ambiguous selector" in payload["error"]
    assert len(payload["candidates"]) > 1


def test_phase_runner_linkedin_target_group_alias(capsys):
    code = phase_runner.main(["run", "linkedin", "--target", "linkedin_uae", "--dry-run"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert code == 0
    assert payload["resolved_selector"]["match_kind"] == "target_group"
    assert payload["resolved_selector"]["target_group_id"] == "uae"
    assert payload["resolved_selector"]["url_count"] == 14


def test_phase_runner_linkedin_keyword_group(capsys):
    code = phase_runner.main(["run", "linkedin", "--target", "uae", "--subselector", "payments", "--dry-run"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert code == 0
    assert "Resolved Keyword Group : payments" in captured.err
    assert payload["resolved_selector"]["target_group_id"] == "uae"
    assert payload["resolved_selector"]["keyword_group_id"] == "payments"
    assert payload["resolved_selector"]["target_ids"] == [
        "linkedin_uae_crypto_payment",
        "linkedin_uae_payments_engineer",
    ]


def test_phase_runner_indeed_keyword_group(capsys):
    code = phase_runner.main(["run", "indeed", "--target", "uae", "--subselector", "product", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["resolved_selector"]["keyword_group_id"] == "product"
    assert payload["resolved_selector"]["keyword_group_ids"] == ["crypto_product"]
    assert payload["resolved_selector"]["url_count"] == 1


def test_phase_runner_jobspy_keyword_reference(capsys):
    code = phase_runner.main(["run", "jobspy", "--target", "uae", "--subselector", "product-manager", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["resolved_selector"]["target_ids"] == ["jobspy_uae_indeed"]
    assert payload["resolved_selector"]["keyword_group_ids"] == ["crypto_product"]


def test_phase_runner_posts_location_role_selector(capsys):
    code = phase_runner.main(["run", "posts", "--target", "uae", "--subselector", "product", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["resolved_selector"]["target_ids"] == ["posts_uae"]
    assert payload["resolved_selector"]["keyword_group_id"] == "backlog"
    assert payload["resolved_selector"]["url_count"] == 4


def test_selector_resolution_priority_and_metadata(monkeypatch):
    registry = deepcopy(collection_config.REGISTRY)
    targets = registry["sources"]["linkedin_jobs"]["targets"]
    targets[0]["id"] = "uae"
    targets[0]["country"] = "Remote"
    targets[0]["aliases"] = ["special_alias"]
    targets[1]["region"] = "test_region"
    targets.append(
        {
            "id": "disabled_selector_test",
            "enabled": False,
            "source": "linkedin_public",
            "country": "UAE",
            "location": "Dubai, United Arab Emirates",
            "keyword_groups": [{"id": "disabled", "query": "disabled"}],
        }
    )
    monkeypatch.setattr(collection_config, "REGISTRY", registry)

    exact_id = collection_config.resolve_selector("linkedin", "uae")
    assert exact_id.status == "matched"
    assert exact_id.match_kind == "target_id"
    assert {target.target_id for target in exact_id.targets} == {"uae"}

    alias = collection_config.resolve_selector("linkedin", "special_alias")
    assert alias.status == "matched"
    assert alias.match_kind == "alias"

    region = collection_config.resolve_selector("linkedin", "test-region")
    assert region.status == "matched"
    assert region.match_kind == "region"

    disabled = collection_config.resolve_selector("linkedin", "disabled_selector_test")
    assert disabled.status == "unknown"


def test_phase_runner_jobspy_source_selector(capsys):
    code = phase_runner.main(["run", "jobspy", "--target", "indeed_uae", "--dry-run"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert code == 0
    assert payload["resolved_selector"]["match_kind"] == "source"
    assert payload["resolved_selector"]["target_ids"] == ["jobspy_uae_indeed"]


def test_phase_runner_recruiters_country_selector(capsys):
    code = phase_runner.main(["run", "recruiters", "--target", "uae", "--dry-run"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert code == 0
    assert payload["resolved_selector"]["match_kind"] == "target_group"
    assert payload["resolved_selector"]["url_count"] == 4


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
