#!/usr/bin/env bash
# Run read-only provider target discovery commands and write secret-free reports.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_ROOT="${HARNESS_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON_BIN="${PYTHON_PATH:-/opt/conda/envs/wm_env/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python interpreter not executable: $PYTHON_BIN" >&2
  exit 2
fi

PROVIDER="ecos"
ARGS=()
while (($#)); do
  case "$1" in
    --provider)
      PROVIDER="${2:-}"
      shift 2
      ;;
    --provider=*)
      PROVIDER="${1#--provider=}"
      shift
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

cd "$HARNESS_ROOT"
case "${PROVIDER,,}" in
  ecos)
    PYTHONPATH="$HARNESS_ROOT:$HARNESS_ROOT/apps/api" \
      "$PYTHON_BIN" -m apps.api.harness.batch.ecos_discovery "${ARGS[@]}"
    ;;
  dart|opendart)
    PYTHONPATH="$HARNESS_ROOT:$HARNESS_ROOT/apps/api" \
      "$PYTHON_BIN" -m apps.api.harness.batch.discovery --provider dart "${ARGS[@]}"
    ;;
  *)
    echo "ERROR: unsupported provider discovery target: $PROVIDER" >&2
    exit 2
    ;;
esac
