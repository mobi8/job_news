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
            stdout="rss\nselector ✓\nkeyword -\n",
            stderr="",
        )

    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", fake_run)

    telegram_poller._handle_collect_command("/collect list", chat_id="111", background=False)

    assert calls and calls[0][1:4] == ["-m", "src.watch.phase_runner", "list"]
    assert "📋 /collect list" in messages[0][0]
    assert "rss\nselector ✓" in messages[0][0]


def test_collect_list_phase_selector_subprocess(monkeypatch):
    messages = _capture_messages(monkeypatch)
    calls = []
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    def fake_run(args, timeout_seconds):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="- payments: Payments\n", stderr="")

    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", fake_run)

    telegram_poller._handle_collect_command("/collect list linkedin uae", chat_id="111", background=False)

    assert calls[0][-3:] == ["list", "linkedin", "uae"]
    assert "payments" in messages[0][0]


def test_collect_list_rejects_extra_arguments(monkeypatch):
    messages = _capture_messages(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    telegram_poller._handle_collect_command("/collect list one two three", chat_id="111", background=False)

    assert messages[-1][0] == "Usage: /collect list [phase] [selector]"


def test_collect_list_html_escape_title(monkeypatch):
    messages = _capture_messages(monkeypatch)
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    def fake_run(args, timeout_seconds):
        return subprocess.CompletedProcess(args, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", fake_run)

    telegram_poller._handle_collect_command("/collect list <bad&phase>", chat_id="111", background=False)

    assert "&lt;bad&amp;phase&gt;" in messages[0][0]


def test_collect_chunking(monkeypatch):
    messages = _capture_messages(monkeypatch)
    telegram_poller._send_collect_chunks("a\n" + ("b" * 3600), chat_id="111", limit=100)
    assert len(messages) == 2


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


def test_collect_run_selector_subselector_args(monkeypatch):
    messages = _capture_messages(monkeypatch)
    calls = []
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    def fake_run(args, timeout_seconds):
        calls.append(args)
        payload = {
            "phase": "linkedin",
            "status": "dry_run" if "--dry-run" in args else "success",
            "counts": {"attempted_targets": 2},
            "errors": [],
            "resolved_selector": {
                "selector": "uae",
                "subselector": "payments",
                "keyword_group_id": "payments",
            },
        }
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(telegram_poller, "_run_collect_subprocess", fake_run)

    telegram_poller._handle_collect_command("/collect linkedin uae payments", chat_id="111", background=False)

    assert any("시작됨" in message for message, _ in messages)
    assert len(calls) == 2
    assert calls[0][-4:] == ["--target", "uae", "--subselector", "payments"]
    assert calls[1][-4:] == ["--target", "uae", "--subselector", "payments"]


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

    telegram_poller._handle_collect_command("/collect rss one two three", chat_id="111", background=False)

    assert messages[-1][0] == "Usage: /collect <phase> [selector] [subselector]"


def test_help_and_commands_share_collect_help(monkeypatch):
    messages = []
    monkeypatch.setattr(telegram_poller, "send_telegram_text", lambda text: messages.append(text) or True)

    telegram_poller.handle_message("/help", chat_id="111")
    telegram_poller.handle_message("/commands", chat_id="111")

    assert len(messages) == 2
    assert messages[0] == messages[1]
    help_text = messages[0]
    assert "/collect — phase 단위 수집 실행" in help_text
    assert "/collect list — 실행 가능한 phase 목록" in help_text
    assert "/collect status — 현재 실행 상태 확인" in help_text
    assert "/collect help — 상세 사용법" in help_text
    assert "/collect &lt;phase&gt; — 특정 phase 실행" in help_text
    assert "/collect &lt;phase&gt; &lt;selector&gt; — target group 실행" in help_text
    assert "/collect &lt;phase&gt; &lt;selector&gt; &lt;subselector&gt; — keyword/role 범위 실행" in help_text
    assert "Target 지원: linkedin, indeed, glassdoor, drjobs, jobspy, fixed, recruiters, rss, player, posts" in help_text
    assert "Target 미지원: dashboard, telegram, notifications, queue, all" in help_text
    assert "Example: /collect rss | /collect posts 1 | /collect status" in help_text
    assert "/run — 전체 수집 실행" in help_text
    assert "/glass — Glassdoor 수집" in help_text
    assert "/posts — LinkedIn 포스트 분석" in help_text
    assert "spot. [위치] | [키워드] | [개수]" in help_text
