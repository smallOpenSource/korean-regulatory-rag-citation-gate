"""Authentication repository."""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import fetch_one

from .common import row_to_dict

FIND_EMPLOYEE_BY_EMAIL_SQL = """
/* sql_id: find_employee_by_email */
SELECT e.id, e.employee_no, e.name, e.role_code, e.branch_id, e.email, e.password_hash, e.is_active
FROM employees e
WHERE lower(e.email) = lower($1)
  AND e.is_active IS TRUE;
"""

FIND_EMPLOYEE_BY_ID_SQL = """
/* sql_id: find_employee_by_id */
SELECT e.id, e.employee_no, e.name, e.role_code, e.branch_id, e.email, e.is_active
FROM employees e
WHERE e.id = $1
  AND e.is_active IS TRUE;
"""


async def find_employee_by_email(connection: Any, email: str) -> dict[str, Any] | None:
    """Find an active employee by login email."""

    return row_to_dict(await fetch_one(connection, FIND_EMPLOYEE_BY_EMAIL_SQL, email))


async def find_employee_by_id(connection: Any, employee_id: str) -> dict[str, Any] | None:
    """Find an active employee by id."""

    return row_to_dict(await fetch_one(connection, FIND_EMPLOYEE_BY_ID_SQL, employee_id))
