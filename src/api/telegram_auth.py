#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Any


def _split_chat_ids(value: str | None) -> set[str]:
    if not value:
        return set()
    return {chunk.strip() for chunk in value.split(",") if chunk.strip()}


def allowed_chat_ids(env: dict[str, str] | None = None) -> set[str]:
    values = env if env is not None else os.environ
    explicit = _split_chat_ids(values.get("TELEGRAM_ALLOWED_CHAT_IDS"))
    if explicit:
        return explicit
    fallback = str(values.get("TELEGRAM_CHAT_ID") or "").strip()
    return {fallback} if fallback else set()


def collect_commands_enabled(env: dict[str, str] | None = None) -> bool:
    return bool(allowed_chat_ids(env))


def is_chat_authorized(chat_id: Any, env: dict[str, str] | None = None) -> bool:
    allowed = allowed_chat_ids(env)
    if not allowed:
        return False
    return str(chat_id or "").strip() in allowed


def unauthorized_message() -> str:
    return "이 채팅에서는 실행형 수집 명령을 사용할 수 없습니다."
