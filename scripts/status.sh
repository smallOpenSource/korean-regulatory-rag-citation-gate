#!/usr/bin/env bash
# Report local Harness PoC process and optional dependency health.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

CHECK_DEEP=0
NO_FAIL=0
FAILURES=0

usage() {
  cat <<USAGE
Usage: scripts/status.sh [--deep] [--no-fail]

Default checks process PID files and HTTP endpoints.
--deep additionally pings configured PostgreSQL and Redis using .env.
USAGE
}

record_failure() {
  FAILURES=$((FAILURES + 1))
}

process_line() {
  local name="$1"
  local pid_file="$2"
  local expected_pattern="${3:-}"
  local expected_cwd="${4:-}"
  if pid_running "$pid_file" "$expected_pattern" "$expected_cwd"; then
    msg "$name process=running pid=$(pid_label "$pid_file")"
  elif [[ -f "$pid_file" ]]; then
    msg "$name process=stale_or_mismatched pid=$(pid_label "$pid_file")"
    record_failure
  else
    msg "$name process=stopped pid=-"
    record_failure
  fi
}

http_line() {
  local name="$1"
  local url="$2"
  local output
  if output="$(http_check "$url" 2>&1)"; then
    msg "$name endpoint=ok url=$url $output"
  else
    msg "$name endpoint=blocked url=$url $output"
    record_failure
  fi
}

deep_checks() {
  local result
  if result="$($(python_bin) - "$HARNESS_ROOT" <<'PY'
import asyncio
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "apps/api"))

from apps.api.harness.core.config import load_config  # noqa: E402
from apps.api.harness.core.db import create_pool  # noqa: E402
from apps.api.harness.core.redis_client import create_redis_client  # noqa: E402

status = 0
try:
    config = load_config(root / ".env")
except Exception as exc:  # noqa: BLE001
    print(f"config=blocked reason_class={exc.__class__.__name__}")
    raise SystemExit(1)

try:
    redis_client = create_redis_client(config.redis)
    redis_client.ping()
    print("redis=ok")
except Exception as exc:  # noqa: BLE001
    status = 1
    print(f"redis=blocked reason_class={exc.__class__.__name__}")

async def check_db() -> None:
    pool = await create_pool(config.database, min_size=1, max_size=1)
    try:
        async with pool.acquire() as connection:
            await connection.fetchval("/* sql_id: script_status_db_ping */ SELECT 1")
    finally:
        await pool.close()

try:
    asyncio.run(check_db())
    print("postgres=ok")
except Exception as exc:  # noqa: BLE001
    status = 1
    print(f"postgres=blocked reason_class={exc.__class__.__name__}")

raise SystemExit(status)
PY
  )"; then
    msg "$result"
  else
    msg "$result"
    record_failure
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deep) CHECK_DEEP=1 ;;
    --no-fail) NO_FAIL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
  shift
done

load_dotenv "$HARNESS_ROOT/.env"
PYTHON_BIN="$(python_bin)"
require_command "$PYTHON_BIN"

msg "Harness root=$HARNESS_ROOT"
process_line "harness-api" "$API_PID_FILE" "apps.api.harness.main:app" "$HARNESS_ROOT"
process_line "harness-web" "$WEB_PID_FILE" "vite" "$HARNESS_ROOT/apps/web"
http_line "harness-api" "$(api_status_url)"
http_line "harness-web" "$(web_status_url)"

if (( CHECK_DEEP )); then
  deep_checks
fi

if (( FAILURES == 0 )); then
  msg "status=ok"
elif (( NO_FAIL )); then
  msg "status=blocked failures=$FAILURES no_fail=1"
else
  msg "status=blocked failures=$FAILURES"
  exit 1
fi
