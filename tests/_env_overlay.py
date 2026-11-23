"""Per-test env overlay so a spawned harness server honors fixture overrides.

``core.config.load_env_file`` applies the project ``.env`` with override=True
(service-viability F8 — ``.env`` is the single source of truth for runtime
config). A consequence: a fixture that injects env vars into a subprocess
(``env["APP_ENV"] = "staging"``, ``env["CORS_ENABLED"] = "true"``, ...) has
those values CLOBBERED back to the repo ``.env`` at server startup, so the
fixture's intended configuration never takes effect.

To make a fixture's overrides authoritative without weakening override=True,
write a temp env file = the repo ``.env`` with the override keys replaced, then
point the spawned server at it via ``HARNESS_ENV_FILE`` (honored by
``core.config.default_env_path``). The overlay is a full copy of ``.env`` with
only test-scoped keys changed, so ``assert_critical_env_override`` still holds.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def write_env_overlay(overrides: dict[str, str], *, base: Path | None = None) -> str:
    """Write a temp env file = ``base`` (default repo .env) with ``overrides``
    applied (replaced in place for existing keys, appended otherwise) and return
    its path.

    Point the spawned server at the result via ``HARNESS_ENV_FILE=<path>`` so
    ``load_env_file`` reads these values instead of the repo ``.env``. The caller
    owns cleanup (``os.unlink`` on teardown).
    """

    base_path = base or (PROJECT_ROOT / ".env")
    lines = base_path.read_text().splitlines() if base_path.exists() else []
    applied: set[str] = set()
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in overrides:
                out.append(f"{key}={overrides[key]}")
                applied.add(key)
                continue
        out.append(raw)
    for key, value in overrides.items():
        if key not in applied:
            out.append(f"{key}={value}")
    fd, path = tempfile.mkstemp(prefix="harness_env_overlay_", suffix=".env")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(out) + "\n")
    return path
