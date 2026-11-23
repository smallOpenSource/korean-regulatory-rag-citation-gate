#!/usr/bin/env bash
# Run the Harness batch pipeline and write an operator evidence report.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HARNESS_ROOT="${HARNESS_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON_BIN="${PYTHON_PATH:-/opt/conda/envs/wm_env/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python interpreter not executable: $PYTHON_BIN" >&2
  exit 2
fi

cd "$HARNESS_ROOT"
PYTHONPATH="$HARNESS_ROOT:$HARNESS_ROOT/apps/api" \
  "$PYTHON_BIN" apps/api/harness/batch/runner.py "$@"
