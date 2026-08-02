#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess

from api import telegram_poller


def _capture_messages(monkeypatch):
    messages = []
    monkeypatch.setattr(telegram_poller, "_send_collect_text", lambda text, chat_id=None: messages.append((text, chat_id)) or True)
    return messages


def test_collect_requires_authorized_chat(monkeypatch):
    messages = _capture_messages(monkeypatch)
    calls = []
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")
    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", lambda *args, **kwargs: calls.append(args) or None)

    telegram_poller._handle_collect_command("/collect list", chat_id="222", background=False)

    assert calls == []
    assert messages
    assert "실행형 수집 명령" in messages[0][0]


def test_collect_disabled_without_auth_env(monkeypatch):
    messages = _capture_messages(monkeypatch)
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    telegram_poller._handle_collect_command("/collect status", chat_id="111", background=False)

    assert "비활성화" in messages[0][0]


def test_collect_list_uses_phase_runner_subprocess(monkeypatch):
    messages = _capture_messages(monkeypatch)
    calls = []
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    def fake_run(args, timeout_seconds):
        calls.append(args)
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="rss\tRSS Feeds\torder=80\tenabled=True\taliases=news\n",
            stderr="",
        )

    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", fake_run)

    telegram_poller._handle_collect_command("/collect list", chat_id="111", background=False)

    assert calls and calls[0][1:4] == ["-m", "src.watch.phase_runner", "list"]
    assert "rss: RSS Feeds" in messages[0][0]
    assert "aliases: news" in messages[0][0]


def test_collect_run_alias_target_subprocess_args(monkeypatch):
    messages = _capture_messages(monkeypatch)
    calls = []
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    def fake_run(args, timeout_seconds):
        calls.append(args)
        if "--dry-run" in args:
            payload = {
                "phase": "rss",
                "status": "dry_run",
                "counts": {"attempted_targets": 1},
                "errors": [],
            }
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")
        payload = {
            "phase": "rss",
            "status": "success",
            "counts": {"raw": 1, "inserted": 1},
            "duration_seconds": 0.2,
            "errors": [],
        }
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", fake_run)

    telegram_poller._handle_collect_command("/collect news igaming_business", chat_id="111", background=False)

    assert any("시작됨" in message for message, _ in messages)
    assert any("완료" in message and "raw=1" in message for message, _ in messages)
    assert len(calls) == 2
    assert calls[0][1:5] == ["-m", "src.watch.phase_runner", "run", "news"]
    assert "--dry-run" in calls[0]
    assert "--requested-by" in calls[1]
    assert calls[1][-2:] == ["--target", "igaming_business"]


def test_collect_unsupported_target_message(monkeypatch):
    messages = _capture_messages(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    def fake_run(args, timeout_seconds):
        payload = {"phase": "linkedin", "status": "invalid_target", "error": "phase does not support --target"}
        return subprocess.CompletedProcess(args, 2, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", fake_run)

    telegram_poller._handle_collect_command("/collect linkedin linkedin_uae", chat_id="111", background=False)

    assert len(messages) == 1
    assert messages[-1][0] == "Target selection is not supported for linkedin."


def test_collect_unknown_phase_suggestion(monkeypatch):
    messages = _capture_messages(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    def fake_run(args, timeout_seconds):
        return subprocess.CompletedProcess(args, 2, stdout="Unknown phase: linkdin. Did you mean 'linkedin'?\n", stderr="")

    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", fake_run)

    telegram_poller._handle_collect_command("/collect linkdin", chat_id="111", background=False)

    assert len(messages) == 1
    assert "Did you mean 'linkedin'" in messages[-1][0]


def test_collect_rejects_extra_arguments(monkeypatch):
    messages = _capture_messages(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    telegram_poller._handle_collect_command("/collect rss one two", chat_id="111", background=False)

    assert messages[-1][0] == "Usage: /collect <phase> [target]"
