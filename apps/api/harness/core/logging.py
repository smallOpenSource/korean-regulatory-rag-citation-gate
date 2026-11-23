"""Secret and PII-safe logging helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|auth[_-]?key|client[_-]?secret|authorization|service[_-]?key)",
    re.IGNORECASE,
)
# asyncpg appends "DETAIL: Failing row contains (..., 2026-05-16 13:19:53.281638+00, ...)"
# to CHECK/UNIQUE violations. The row dump leaks raw PG microsecond timestamps
# and column tuples into admin /batch — strip it before persisting/displaying.
FAILING_ROW_RE = re.compile(
    r"\s*DETAIL:\s*Failing row contains\s*\([^)]*\)\.?",
    re.IGNORECASE,
)
CHECK_VIOLATION_RE = re.compile(
    r'new row for relation "([^"]+)" violates check constraint "([^"]+)"',
    re.IGNORECASE,
)
UNIQUE_VIOLATION_RE = re.compile(
    r'duplicate key value violates unique constraint "([^"]+)"',
    re.IGNORECASE,
)
FOREIGN_KEY_VIOLATION_RE = re.compile(
    r'insert or update on table "([^"]+)" violates foreign key constraint "([^"]+)"',
    re.IGNORECASE,
)
TOKEN_VALUE_RE = re.compile(
    r"(?i)(bearer\s+)[a-z0-9._~+/=-]+|([?&](?:api_key|serviceKey|auth_key|key)=)[^&\s]+"
)
URI_USERINFO_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/@\s:]+)(?::([^/@\s]*))?@")
KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|auth[_-]?key|service[_-]?key)\s*=\s*[^&\s,;]+"
)


def is_sensitive_key(key: str) -> bool:
    """Return whether a field name should be redacted."""

    return bool(SENSITIVE_KEY_RE.search(key))


def redact_secret_text(value: str) -> str:
    """Redact common token forms from free-form text."""

    def replace(match: re.Match[str]) -> str:
        prefix = match.group(1) or match.group(2) or ""
        return f"{prefix}<redacted>"

    text = TOKEN_VALUE_RE.sub(replace, value)
    text = URI_USERINFO_RE.sub(r"\1<redacted>@", text)
    return KEY_VALUE_SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)


def summarize_db_error(value: str) -> str:
    """Translate common asyncpg/PG error texts into PB/admin-readable Korean.

    Strips the noisy "DETAIL: Failing row contains (...)" suffix that leaks
    raw column tuples (including microsecond timestamps and identifiers) into
    admin-facing copy, and rewrites CHECK/UNIQUE/FK violations into short
    Korean phrases that name the offending relation/constraint without the
    English boilerplate.
    """

    text = FAILING_ROW_RE.sub("", value).strip()
    check_match = CHECK_VIOLATION_RE.search(text)
    if check_match:
        relation, constraint = check_match.group(1), check_match.group(2)
        return f"제약 조건 위반 (CHECK · 관계 {relation} · 조건 {constraint})"
    unique_match = UNIQUE_VIOLATION_RE.search(text)
    if unique_match:
        return f"중복 키 (UNIQUE · 제약 {unique_match.group(1)})"
    fk_match = FOREIGN_KEY_VIOLATION_RE.search(text)
    if fk_match:
        relation, constraint = fk_match.group(1), fk_match.group(2)
        return f"외래 키 위반 (FK · 관계 {relation} · 제약 {constraint})"
    return text


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with secret-like keys and values redacted."""

    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if is_sensitive_key(key):
            redacted[key] = "<redacted>"
        elif isinstance(value, str):
            redacted[key] = redact_secret_text(value)
        elif isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted
