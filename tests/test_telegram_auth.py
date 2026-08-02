#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from api.telegram_auth import allowed_chat_ids, collect_commands_enabled, is_chat_authorized


def test_allowed_chat_ids_prefers_explicit_list():
    env = {"TELEGRAM_ALLOWED_CHAT_IDS": "111, 222", "TELEGRAM_CHAT_ID": "999"}
    assert allowed_chat_ids(env) == {"111", "222"}


def test_allowed_chat_ids_falls_back_to_chat_id():
    env = {"TELEGRAM_CHAT_ID": "999"}
    assert allowed_chat_ids(env) == {"999"}


def test_collect_commands_disabled_without_chat_config():
    assert collect_commands_enabled({}) is False
    assert is_chat_authorized("123", {}) is False


def test_chat_authorization_normalizes_values():
    env = {"TELEGRAM_ALLOWED_CHAT_IDS": "111,222"}
    assert is_chat_authorized(111, env) is True
    assert is_chat_authorized("222", env) is True
    assert is_chat_authorized("333", env) is False


def test_negative_chat_id_supported():
    env = {"TELEGRAM_ALLOWED_CHAT_IDS": "-100123, 456"}
    assert is_chat_authorized("-100123", env) is True
    assert is_chat_authorized(-100123, env) is True


def test_empty_allowed_list_falls_back_to_chat_id():
    env = {"TELEGRAM_ALLOWED_CHAT_IDS": " , ", "TELEGRAM_CHAT_ID": "999"}
    assert allowed_chat_ids(env) == {"999"}


def test_invalid_values_are_not_executed_by_default():
    env = {"TELEGRAM_ALLOWED_CHAT_IDS": "abc"}
    assert collect_commands_enabled(env) is True
    assert is_chat_authorized("123", env) is False
    assert is_chat_authorized("abc", env) is True
