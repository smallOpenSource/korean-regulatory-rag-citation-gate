#!/usr/bin/env bash
# Run real read-only provider smoke checks with optional strict skip semantics.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_ROOT="${HARNESS_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON_BIN="${PYTHON_PATH:-/opt/conda/envs/wm_env/bin/python}"
APP_ENV_VALUE="${APP_ENV:-}"
STRICT="${HARNESS_PROVIDER_STRICT:-}"
PYTEST_ARGS=()

if [[ -f "$HARNESS_ROOT/.env" ]]; then
  while IFS= read -r raw_line; do
    line="${raw_line%%#*}"
    case "$line" in
      APP_ENV=*)
        if [[ -z "$APP_ENV_VALUE" ]]; then
          APP_ENV_VALUE="${line#APP_ENV=}"
          APP_ENV_VALUE="${APP_ENV_VALUE%\"}"
          APP_ENV_VALUE="${APP_ENV_VALUE#\"}"
          APP_ENV_VALUE="${APP_ENV_VALUE%\'}"
          APP_ENV_VALUE="${APP_ENV_VALUE#\'}"
        fi
        ;;
      HARNESS_PROVIDER_STRICT=*)
        if [[ -z "$STRICT" ]]; then
          STRICT="${line#HARNESS_PROVIDER_STRICT=}"
          STRICT="${STRICT%\"}"
          STRICT="${STRICT#\"}"
          STRICT="${STRICT%\'}"
          STRICT="${STRICT#\'}"
        fi
        ;;
    esac
  done < "$HARNESS_ROOT/.env"
fi

if [[ "${APP_ENV_VALUE,,}" == "production" ]]; then
  STRICT=1
elif [[ -z "$STRICT" ]]; then
  STRICT=0
fi

while (($#)); do
  case "$1" in
    --strict|--strict-external)
      STRICT=1
      shift
      ;;
    --no-strict|--no-strict-external)
      STRICT=0
      shift
      ;;
    --)
      shift
      PYTEST_ARGS+=("$@")
      break
      ;;
    *)
      PYTEST_ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python interpreter not executable: $PYTHON_BIN" >&2
  exit 2
fi

cd "$HARNESS_ROOT"
TMP_OUTPUT="$(mktemp)"
trap 'rm -f "$TMP_OUTPUT"' EXIT

set +e
PYTHONPATH="$HARNESS_ROOT:$HARNESS_ROOT/apps/api" \
  "$PYTHON_BIN" -m pytest -q -rs tests/test_external_clients_smoke.py "${PYTEST_ARGS[@]}" \
  2>&1 | tee "$TMP_OUTPUT"
STATUS=${PIPESTATUS[0]}
set -e

if [[ "$STATUS" -ne 0 ]]; then
  exit "$STATUS"
fi

case "${STRICT,,}" in
  1|true|yes|on)
    if grep -q "SKIPPED/BLOCKED_WITH_REDACTED_REASON" "$TMP_OUTPUT"; then
      echo "provider_smoke=strict_failed reason=provider smoke contained SKIPPED/BLOCKED evidence" >&2
      exit 2
    fi
    ;;
esac
