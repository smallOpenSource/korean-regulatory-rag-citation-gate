#!/usr/bin/env python3
"""v8 state_hash — PRD §4 #2 cell hash 정의 + normalization rules.

PRD §4 #2:
  sha256(canonical(route_pattern, role, content_state_enum,
                   interaction_state_enum, normalized_visible_text))

Normalization rules:
  - timestamp → KST format "YYYY-MM-DD HH:mm" truncated (no seconds, no microseconds)
  - UUID → "{resource_type}#{stable_index}" (e.g., "house_view#0", "consultation#1")
  - data-* attributes 제외
  - dynamic ID → "{resource_type}#{stable_position}"
    (stable_position = alphabetical sort by (resource_type, created_at ASC) + 0-indexed)
  - whitespace 정규화 (multiple → single space)
  - 한국어 unicode NFC normalize

DELTA-N2 audit-table self-verification: cycle 1 G1 entry deliverable.
Cross-ref: [[test-determinism-against-random-input]] 50× repeat strictness.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass


# Regex for normalization (compile once for determinism + speed)
_RE_ISO_MICRO = re.compile(r"(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}):\d{2}(?:\.\d+)?Z?")
_RE_PG_MICRO = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}):\d{2}(?:\.\d+)?(?:[+-]\d{2}(?::?\d{2})?)?")
_RE_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_RE_DATA_ATTR = re.compile(r'\s*data-[a-zA-Z0-9_-]+="[^"]*"')
_RE_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Cell:
    """v8 4-axis cell + visible text (5-tuple input to state_hash)."""

    route_pattern: str  # URL pattern (e.g., "/customers/:customerId")
    role: str  # PB | WM | BRANCH_MANAGER | ADMIN | AUDIT_VIEWER
    content_state: str  # entity_table#enum (e.g., "consultations#COMPLETED")
    interaction_state: str  # interaction class (e.g., "click", "keyboard")
    visible_text: str  # body text snippet (pre-normalization)


def normalize_timestamps(text: str) -> str:
    """ISO/PG microsecond timestamps → KST truncated 'YYYY-MM-DD HH:mm'.

    Strips seconds + microseconds + timezone offset to remove jitter.
    """
    # ISO format: 2026-04-20T13:52:53.650391Z → 2026-04-20 13:52
    text = _RE_ISO_MICRO.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)
    # PG format: 2026-05-16 14:52:16.847752+09 → 2026-05-16 14:52
    text = _RE_PG_MICRO.sub(lambda m: f"{m.group(1)} {m.group(2)}", text)
    return text


def normalize_uuids(text: str, stable_index_map: dict[str, str] | None = None) -> str:
    """UUID → "{resource_type}#{stable_index}".

    stable_index_map is optional; when not provided, all UUIDs become "uuid#0"
    (deterministic but coarse). For cycle 1 traversal use the BFS visitor's
    persistent index map.
    """
    if stable_index_map is None:
        return _RE_UUID.sub("uuid#0", text)

    def replace(match: re.Match[str]) -> str:
        uid = match.group(0)
        # 내장 hash()는 프로세스마다 randomize되어 비결정적이므로 sha256 다이제스트로 대체합니다.
        fallback_idx = int(hashlib.sha256(uid.encode()).hexdigest()[:8], 16) % 10000
        return stable_index_map.get(uid, f"uuid#{fallback_idx}")

    return _RE_UUID.sub(replace, text)


def strip_data_attributes(text: str) -> str:
    """Remove data-* attributes from any HTML/JSX-like snippet."""
    return _RE_DATA_ATTR.sub("", text)


def normalize_whitespace(text: str) -> str:
    """Multiple whitespace → single space, strip."""
    return _RE_WHITESPACE.sub(" ", text).strip()


def normalize_korean_unicode(text: str) -> str:
    """Korean NFC normalization (handles combined vs decomposed Hangul)."""
    return unicodedata.normalize("NFC", text)


def canonicalize(cell: Cell, stable_index_map: dict[str, str] | None = None) -> str:
    """Apply full normalization pipeline → canonical 5-tuple string."""
    text = cell.visible_text
    text = normalize_timestamps(text)
    text = normalize_uuids(text, stable_index_map)
    text = strip_data_attributes(text)
    text = normalize_whitespace(text)
    text = normalize_korean_unicode(text)

    # 5-tuple canonical separator (unit separator U+001F, ASCII 0x1F).
    sep = "\x1f"
    return sep.join((cell.route_pattern, cell.role, cell.content_state, cell.interaction_state, text))


def state_hash(cell: Cell, stable_index_map: dict[str, str] | None = None) -> str:
    """sha256 of canonical 5-tuple — DELTA-N2 deterministic cell identity."""
    canonical = canonicalize(cell, stable_index_map)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    # CLI self-test: ensure 50× repeat is identical.
    fixture = Cell(
        route_pattern="/customers/:customerId",
        role="PB",
        content_state="customers#LOADED",
        interaction_state="click",
        visible_text="고객 김민준 - 자산 5억원 - 2026-05-20T13:25:00.123456Z",
    )
    hashes = {state_hash(fixture) for _ in range(50)}
    assert len(hashes) == 1, f"determinism FAIL: {len(hashes)} distinct hashes"
    print(f"50× determinism PASS — hash: {next(iter(hashes))}")
