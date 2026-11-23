#!/usr/bin/env bash
# Wave-Audit-Defect-Fix Wave-D follow-up D.5 — portable backend launcher.
#
# Resolves the "ModuleNotFoundError: No module named 'apps'" problem that
# occurs when uvicorn is invoked without the project root on PYTHONPATH or
# from the wrong cwd. The script:
#   1. cd to project root (the directory containing this script's parent).
#   2. Set PYTHONPATH to the project root.
#   3. Hand off to the project's wm_env conda Python binary running
#      uvicorn against apps.api.harness.main:app.
#
# Override anything via environment variables before invocation, e.g.:
#   PORT=8080 HOST=0.0.0.0 bash scripts/run_backend.sh
#
# Defaults match the in-tree dev workflow used by other audit scripts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Honor the .env SoT (HARNESS_API_HOST / HARNESS_API_PORT) used by the rest of
# the lifecycle tooling (common.sh / start.sh / status.sh). load_dotenv exports
# the HARNESS_API_* keys so they are visible below; explicit PORT/HOST env
# overrides still win.
# shellcheck source=scripts/common.sh
source "${SCRIPT_DIR}/common.sh"
load_dotenv "${PROJECT_ROOT}/.env"

HOST="${HOST:-${HARNESS_API_HOST:-127.0.0.1}}"
PORT="${PORT:-${HARNESS_API_PORT:-8000}}"
WORKERS="${WORKERS:-1}"
PYTHON_BIN="${PYTHON_BIN:-/opt/conda/envs/wm_env/bin/python}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
    echo "scripts/run_backend.sh: PYTHON_BIN not executable: ${PYTHON_BIN}" >&2
    echo "  Override via PYTHON_BIN=/path/to/python" >&2
    exit 1
fi

cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

exec "${PYTHON_BIN}" -m uvicorn apps.api.harness.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --workers "${WORKERS}" \
    "$@"
