"""Raw SQL contract checks for Harness.

The project intentionally avoids ORM/migration frameworks. These helpers keep
application and migration SQL aligned with the documented ``sql_id`` rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

SQL_ID_PREFIX = "/* sql_id:"
SQL_ID_RE = re.compile(r"^/\*\s*sql_id:\s*[a-z0-9_]+\s*\*/", re.IGNORECASE)
SELECT_STAR_RE = re.compile(r"\bSELECT\s+\*(?=\s|,|;|$)", re.IGNORECASE)


@dataclass(frozen=True)
class SqlValidationResult:
    """Validation result for one SQL statement or file."""

    ok: bool
    errors: tuple[str, ...]


def first_significant_token(sql_text: str) -> str:
    """Return the first non-whitespace SQL token/comment prefix."""

    return sql_text.lstrip()[: len(SQL_ID_PREFIX)]


def ensure_sql_id(sql_text: str, *, context: str = "sql") -> None:
    """Raise when a SQL statement does not start with a ``sql_id`` comment."""

    stripped = sql_text.lstrip()
    if not SQL_ID_RE.match(stripped):
        raise ValueError(f"{context} must start with /* sql_id: short_name */")
    if SELECT_STAR_RE.search(stripped):
        raise ValueError(f"{context} must not use SELECT *")


def validate_sql_text(sql_text: str, *, context: str = "sql") -> SqlValidationResult:
    """Validate a SQL statement without raising."""

    errors: list[str] = []
    try:
        ensure_sql_id(sql_text, context=context)
    except ValueError as exc:
        errors.append(str(exc))
    return SqlValidationResult(ok=not errors, errors=tuple(errors))


def validate_sql_file(path: Path, splitter) -> SqlValidationResult:
    """Validate every statement returned by ``splitter`` for a SQL file."""

    errors: list[str] = []
    for index, statement in enumerate(splitter(path.read_text()), start=1):
        result = validate_sql_text(statement, context=f"{path}:{index}")
        errors.extend(result.errors)
    return SqlValidationResult(ok=not errors, errors=tuple(errors))
