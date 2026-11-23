"""Repository helpers for raw asyncpg records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def row_to_dict(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Convert an asyncpg record-like row into a plain dict."""

    return dict(row) if row is not None else None


def rows_to_dicts(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Convert asyncpg record-like rows into plain dicts."""

    return [dict(row) for row in rows]
