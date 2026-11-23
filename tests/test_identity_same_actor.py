"""Unit tests for ``apps.api.harness.core.identity.same_actor``."""

from __future__ import annotations

import uuid

from apps.api.harness.core.identity import same_actor


def test_str_str_equal() -> None:
    assert same_actor("abc", "abc") is True


def test_str_str_unequal() -> None:
    assert same_actor("abc", "xyz") is False


def test_str_uuid_equal() -> None:
    raw = uuid.uuid4()
    assert same_actor(str(raw), raw) is True


def test_uuid_str_equal() -> None:
    raw = uuid.uuid4()
    assert same_actor(raw, str(raw)) is True


def test_uuid_uuid_equal() -> None:
    raw = uuid.uuid4()
    assert same_actor(raw, raw) is True


def test_uuid_uuid_unequal() -> None:
    assert same_actor(uuid.uuid4(), uuid.uuid4()) is False


def test_none_left() -> None:
    assert same_actor(None, "abc") is False


def test_none_right() -> None:
    assert same_actor("abc", None) is False


def test_both_none() -> None:
    assert same_actor(None, None) is False


def test_none_left_uuid() -> None:
    assert same_actor(None, uuid.uuid4()) is False
