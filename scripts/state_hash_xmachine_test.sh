#!/bin/bash
# v8 state_hash cross-machine determinism test — PRD DELTA-N2 + Task #21
#
# Simulates "machine B" by running the same fixture under a different locale
# (LANG=C / TZ=UTC / LC_ALL=C). If the canonical form leaks locale-dependent
# behavior, hashes will diverge; DELTA-N2 G1 gate then fails.
#
# Exit codes:
#   0 — diff = 0 (PASS, cross-machine deterministic)
#   1 — hashes diverge (FAIL, normalization rules need reinforcement)
#   2 — environment issue (Python/state_hash unavailable)

set -euo pipefail

PY="/opt/conda/envs/wm_env/bin/python"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_HASH_PATH="${SCRIPT_DIR}/v8_state_hash.py"

if [ ! -f "${STATE_HASH_PATH}" ]; then
  echo "ERROR: state_hash module missing at ${STATE_HASH_PATH}" >&2
  exit 2
fi
if [ ! -x "${PY}" ]; then
  echo "ERROR: wm_env Python missing at ${PY}" >&2
  exit 2
fi

# Single fixture (kept identical to first FIXTURES entry in the pytest suite).
FIXTURE_PY='
import sys, json
sys.path.insert(0, "scripts")
from v8_state_hash import Cell, state_hash
cell = Cell(
  route_pattern="/customers/:customerId",
  role="PB",
  content_state="customers#LOADED",
  interaction_state="click",
  visible_text="고객 김민준 - 자산 5억원 - 2026-05-20T13:25:00.123456Z",
)
print(state_hash(cell))
'

echo "=== machine A (native env: LANG=${LANG:-unset}, TZ=${TZ:-unset}) ==="
HASH_A=$("${PY}" -c "${FIXTURE_PY}")
echo "${HASH_A}"

echo "=== machine B (forced env: LANG=C, TZ=UTC, LC_ALL=C) ==="
HASH_B=$(env -i HOME="${HOME}" PATH="${PATH}" LANG=C LC_ALL=C TZ=UTC "${PY}" -c "${FIXTURE_PY}")
echo "${HASH_B}"

# Second fixture: visible_text embeds a UUID NOT in any stable_index_map, exercising
# normalize_uuids' fallback — the path that was process-randomized via builtin hash()
# before the sha256 fix (v8_state_hash.py). Run twice in SEPARATE processes (fresh
# PYTHONHASHSEED) and require identical hashes to catch that non-determinism class.
FIXTURE_UUID_PY='
import sys
sys.path.insert(0, "scripts")
from v8_state_hash import Cell, state_hash
cell = Cell(
  route_pattern="/dispute-cases/:disputeId",
  role="PB",
  content_state="disputeCase#LOADED",
  interaction_state="click",
  visible_text="case 12345678-1234-1234-1234-123456789abc 자산 5억원",
)
print(state_hash(cell))
'
echo "=== UUID-fixture process determinism (2 fresh processes) ==="
HASH_U1=$("${PY}" -c "${FIXTURE_UUID_PY}")
HASH_U2=$("${PY}" -c "${FIXTURE_UUID_PY}")
echo "  proc1: ${HASH_U1}"
echo "  proc2: ${HASH_U2}"

echo "=== diff ==="
if [ "${HASH_A}" = "${HASH_B}" ] && [ "${HASH_U1}" = "${HASH_U2}" ]; then
  echo "PASS — cross-machine (locale) + cross-process (UUID fallback) deterministic (diff = 0)"
  exit 0
else
  echo "FAIL — hashes diverge" >&2
  [ "${HASH_A}" != "${HASH_B}" ] && echo "  locale: A=${HASH_A} B=${HASH_B}" >&2
  [ "${HASH_U1}" != "${HASH_U2}" ] && echo "  UUID proc: 1=${HASH_U1} 2=${HASH_U2} (normalize_uuids non-determinism)" >&2
  exit 1
fi
