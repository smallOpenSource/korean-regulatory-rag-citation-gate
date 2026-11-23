#!/usr/bin/env bash
# Start the local Harness PoC API and/or Vite web dev server.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

START_API=1
START_WEB=1
RUN_STATUS=1

usage() {
  cat <<USAGE
Usage: scripts/start.sh [--api-only|--web-only] [--no-status] [--dry-run]

Starts local PoC processes using .env without printing secret values.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-only) START_WEB=0 ;;
    --web-only) START_API=0 ;;
    --no-status) RUN_STATUS=0 ;;
    --dry-run) export HARNESS_DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
  shift
done

load_dotenv "$HARNESS_ROOT/.env"
PYTHON_BIN="$(python_bin)"
require_command "$PYTHON_BIN"

WEB_ENV_ARGS=()
add_web_env_if_set() {
  local key="$1"
  if [[ -n "${!key+x}" ]]; then
    WEB_ENV_ARGS+=("$key=${!key}")
  fi
}
for key in PATH HOME USER LOGNAME SHELL TERM LANG LC_ALL TMPDIR CI NO_COLOR FORCE_COLOR; do
  add_web_env_if_set "$key"
done
while IFS= read -r key; do
  case "$key" in
    VITE_*|HARNESS_*) WEB_ENV_ARGS+=("$key=${!key}") ;;
  esac
done < <(compgen -e)

if (( START_WEB )); then
  require_command npm
  if [[ ! -d "$HARNESS_ROOT/apps/web/node_modules" ]]; then
    if is_true "${HARNESS_AUTO_NPM_INSTALL:-0}"; then
      msg "Installing web dependencies with npm ci (no secrets printed)"
      (cd "$HARNESS_ROOT/apps/web" && env -i "${WEB_ENV_ARGS[@]}" npm ci)
    else
      fail "apps/web/node_modules is missing; run npm ci or set HARNESS_AUTO_NPM_INSTALL=1"
    fi
  fi
fi

API_PYTHONPATH="$HARNESS_ROOT:$HARNESS_ROOT/apps/api"

preflight_api_startup() {
  msg "Checking harness-api startup dependencies"
  (
    cd "$HARNESS_ROOT"
    PYTHONPATH="$API_PYTHONPATH" "$PYTHON_BIN" - <<'PY'
import asyncio
import sys
from pathlib import Path

from apps.api.harness.core.db import create_pool
from apps.api.harness.core.config import load_config


async def probe() -> None:
    config = load_config(Path.cwd() / ".env")
    pool = await create_pool(config.database, min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection:
            await connection.fetchval("/* sql_id: startup_preflight_select */ select 1")
    finally:
        await pool.close()


try:
    asyncio.run(probe())
except Exception as exc:  # noqa: BLE001 - CLI boundary reports sanitized failure only
    print(f"harness-api preflight failed: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY
  )
}

if (( START_API )); then
  if ! is_true "${HARNESS_DRY_RUN:-0}"; then
    preflight_api_startup
  fi
  start_background \
    "harness-api" \
    "$API_PID_FILE" \
    "$API_LOG_FILE" \
    "$HARNESS_ROOT" \
    "apps.api.harness.main:app" \
    env PYTHONPATH="$API_PYTHONPATH" "$PYTHON_BIN" -m uvicorn \
      apps.api.harness.main:app --host "$(api_host)" --port "$(api_port)"
fi

if (( START_WEB )); then
  start_background \
    "harness-web" \
    "$WEB_PID_FILE" \
    "$WEB_LOG_FILE" \
    "$HARNESS_ROOT/apps/web" \
    "vite" \
    env -i "${WEB_ENV_ARGS[@]}" npm exec vite -- --host "$(web_host)" --port "$(web_port)"
fi

if (( RUN_STATUS )) && ! is_true "${HARNESS_DRY_RUN:-0}"; then
  "$SCRIPT_DIR/status.sh" --no-fail
fi
