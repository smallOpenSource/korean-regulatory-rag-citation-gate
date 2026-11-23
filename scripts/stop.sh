#!/usr/bin/env bash
# Stop the local Harness PoC API and/or Vite web dev server.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"

STOP_API=1
STOP_WEB=1

usage() {
  cat <<USAGE
Usage: scripts/stop.sh [--api-only|--web-only] [--dry-run]

Stops local PoC processes started by scripts/start.sh.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-only) STOP_WEB=0 ;;
    --web-only) STOP_API=0 ;;
    --dry-run) export HARNESS_DRY_RUN=1 ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
  shift
done

load_dotenv "$HARNESS_ROOT/.env"
if (( STOP_WEB )); then
  stop_background "harness-web" "$WEB_PID_FILE" "vite" "$HARNESS_ROOT/apps/web"
fi
if (( STOP_API )); then
  stop_background "harness-api" "$API_PID_FILE" "apps.api.harness.main:app" "$HARNESS_ROOT"
fi
