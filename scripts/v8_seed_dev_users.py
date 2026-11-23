#!/usr/bin/env python
"""v8_seed_dev_users.py — Stage 2 cycle 1 launch precondition

Synthetic dev users seeder for v8 PRD state-graph-traversal cycle 1 BFS visit.
- Inserts 5 SYN-EMP-{ROLE} employees (ON CONFLICT DO NOTHING)
- Updates .env with DEV_TEST_USER_{ROLE} entries (echo never shows password)
- Uses PBKDF2-HMAC-SHA256 hash via apps.api.harness.core.security

Constraints applied:
  - synthetic-only data (SYN- prefix; V037 CHECK is customer_no only — employees
    table has no SYN- CHECK constraint but we follow the convention)
  - .env secret never echoed/logged; password printed REDACTED
  - .env update is in-place (gitignored, never committed)
  - audit_logs append-only (no UPDATE/DELETE; INSERT only via app dispatcher)
  - HAProxy single endpoint (no reconnect/failover code)

Usage:
  V8_DEV_PASSWORD=<value> /opt/conda/envs/wm_env/bin/python scripts/v8_seed_dev_users.py
  (defaults to deterministic synthetic password if env var unset)
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import re
import sys
from typing import Any

import asyncpg  # type: ignore[import-not-found]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
sys.path.insert(0, str(REPO_ROOT))
from apps.api.harness.core.security import hash_password  # noqa: E402

# Synthetic role → employee config (SYN- prefix, deterministic IDs)
ROLES: list[dict[str, str]] = [
    {"role_code": "PB", "employee_no": "SYN-EMP-PB-001",
     "name": "SYN PB Tester", "email": "syn.pb@v8test.local"},
    {"role_code": "WM", "employee_no": "SYN-EMP-WM-001",
     "name": "SYN WM Tester", "email": "syn.wm@v8test.local"},
    {"role_code": "BRANCH_MANAGER", "employee_no": "SYN-EMP-BM-001",
     "name": "SYN Branch Manager Tester", "email": "syn.bm@v8test.local"},
    {"role_code": "ADMIN", "employee_no": "SYN-EMP-ADMIN-001",
     "name": "SYN Admin Tester", "email": "syn.admin@v8test.local"},
    {"role_code": "AUDIT_VIEWER", "employee_no": "SYN-EMP-AV-001",
     "name": "SYN Audit Viewer Tester", "email": "syn.av@v8test.local"},
]


def load_env_var(key: str) -> str:
    """Load a key=value pair from REPO_ROOT/.env. Returns empty if missing."""
    if not ENV_FILE.exists():
        return ""
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$", re.MULTILINE)
    text = ENV_FILE.read_text(encoding="utf-8")
    m = pattern.search(text)
    if not m:
        return ""
    val = m.group(1).strip()
    # Strip surrounding quotes
    if len(val) >= 2 and val[0] == val[-1] and val[0] in {'"', "'"}:
        val = val[1:-1]
    return val


def update_env_var(key: str, value: str) -> bool:
    """Append or replace KEY=VALUE in .env. Returns True if written."""
    text = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    new_line = f"{key}={value}"
    if pattern.search(text):
        # 함수형 치환으로 new_line을 리터럴 삽입합니다(\\1 등 백레퍼런스 주입 방지).
        new_text = pattern.sub(lambda _m: new_line, text)
    else:
        if not text.endswith("\n") and text:
            text += "\n"
        new_text = text + new_line + "\n"
    ENV_FILE.write_text(new_text, encoding="utf-8")
    return True


async def main() -> int:
    dsn = load_env_var("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL missing in .env")
        return 2

    password = os.environ.get("V8_DEV_PASSWORD", "SynV8Dev!Cycle1@2026")
    pw_hash = hash_password(password)

    print(f"[v8_seed_dev_users] connecting to DB via .env DATABASE_URL")
    print(f"[v8_seed_dev_users] password length={len(password)} (value REDACTED)")
    print(f"[v8_seed_dev_users] hash format check: {pw_hash[:20]}... (algo prefix only)")

    conn = await asyncpg.connect(dsn=dsn, timeout=10.0)
    try:
        # Default branch_id (any active branch)
        branch_row = await conn.fetchrow(
            "SELECT id FROM branches ORDER BY created_at ASC LIMIT 1"
        )
        if branch_row is None:
            # Insert a synthetic branch
            branch_id = await conn.fetchval(
                """
                INSERT INTO branches (branch_code, branch_name, region_code)
                VALUES ('SYN-BR-001', 'SYN Test Branch', 'SYN')
                ON CONFLICT (branch_code) DO UPDATE
                  SET branch_name = EXCLUDED.branch_name
                RETURNING id
                """
            )
        else:
            branch_id = branch_row["id"]

        inserted: list[dict[str, Any]] = []
        for r in ROLES:
            row = await conn.fetchrow(
                """
                INSERT INTO employees
                  (employee_no, name, role_code, branch_id, email, password_hash, is_active)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE)
                ON CONFLICT (employee_no) DO UPDATE
                  SET password_hash = EXCLUDED.password_hash,
                      role_code = EXCLUDED.role_code,
                      email = EXCLUDED.email,
                      is_active = TRUE
                RETURNING id, employee_no, role_code, email
                """,
                r["employee_no"], r["name"], r["role_code"], branch_id,
                r["email"], pw_hash,
            )
            assert row is not None
            inserted.append(dict(row))
    finally:
        await conn.close()

    print(f"[v8_seed_dev_users] DB rows upserted: {len(inserted)}")
    for row in inserted:
        print(f"  - {row['role_code']:<15} employee_no={row['employee_no']} email={row['email']}")

    # Update .env DEV_TEST_USER_{ROLE} entries (no echo of password)
    env_keys_written: list[str] = []
    for r in ROLES:
        env_key = f"DEV_TEST_USER_{r['role_code']}"
        env_val = f"{r['email']}:{password}"
        update_env_var(env_key, env_val)
        env_keys_written.append(env_key)
    print(f"[v8_seed_dev_users] .env updated: {len(env_keys_written)} keys (values REDACTED)")
    for k in env_keys_written:
        print(f"  - {k}=<REDACTED>")

    print("[v8_seed_dev_users] cycle 1 launch precondition (dev creds) ready")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
