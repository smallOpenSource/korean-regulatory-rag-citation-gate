#!/usr/bin/env bash
# Shared helpers for local Harness PoC lifecycle scripts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${HARNESS_ROOT:-}" ]]; then
  HARNESS_ROOT="$(cd "$HARNESS_ROOT" && pwd)"
else
  HARNESS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

DEFAULT_PYTHON_BIN="$(command -v python3 || command -v python)"
PYTHON_BIN="${PYTHON_PATH:-$DEFAULT_PYTHON_BIN}"
RUN_DIR="${HARNESS_RUN_DIR:-$HARNESS_ROOT/.omx/run}"
LOG_DIR="${HARNESS_LOG_DIR:-$HARNESS_ROOT/.omx/logs/runtime}"
# shellcheck disable=SC2034 # sourced by start/stop/status scripts
API_PID_FILE="$RUN_DIR/harness-api.pid"
# shellcheck disable=SC2034 # sourced by start/stop/status scripts
WEB_PID_FILE="$RUN_DIR/harness-web.pid"
# shellcheck disable=SC2034 # sourced by start/stop/status scripts
API_LOG_FILE="$LOG_DIR/harness-api.log"
# shellcheck disable=SC2034 # sourced by start/stop/status scripts
WEB_LOG_FILE="$LOG_DIR/harness-web.log"

msg() {
  printf '%s\n' "$*"
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

is_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

ensure_dirs() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"
}

strip_matching_quotes() {
  local value="$1"
  if [[ ${#value} -ge 2 ]]; then
    local first="${value:0:1}"
    local last="${value: -1}"
    if [[ "$first" == "$last" && ( "$first" == '"' || "$first" == "'" ) ]]; then
      value="${value:1:${#value}-2}"
    fi
  fi
  printf '%s' "$value"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

load_dotenv() {
  local env_file="${1:-$HARNESS_ROOT/.env}"
  [[ -f "$env_file" ]] || return 0

  local raw line key value
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    raw="${raw%$'\r'}"
    line="$(trim "$raw")"
    [[ -z "$line" ]] && continue
    [[ "$line" == \#* ]] && continue
    [[ "$raw" == *"="* ]] || continue
    key="$(trim "${raw%%=*}")"
    value="$(trim "${raw#*=}")"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    value="$(strip_matching_quotes "$value")"
    export "$key=$value"
  done < "$env_file"
}

python_bin() {
  printf '%s' "${PYTHON_PATH:-$PYTHON_BIN}"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 command is required"
}

read_pid() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  tr -d '[:space:]' < "$pid_file"
}

pid_running() {
  local pid_file="$1"
  local expected_pattern="${2:-}"
  local expected_cwd="${3:-}"
  local pid
  pid="$(read_pid "$pid_file" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" >/dev/null 2>&1 || return 1
  [[ -z "$expected_pattern" ]] || pid_matches_identity "$pid" "$expected_pattern" "$expected_cwd"
}

pid_matches_identity() {
  local pid="$1"
  local expected_pattern="$2"
  local expected_cwd="${3:-}"
  local command_file="/proc/$pid/cmdline"
  local cwd_link="/proc/$pid/cwd"
  local command_line
  local actual_cwd
  [[ -r "$command_file" ]] || return 1
  command_line="$(tr '\0' ' ' < "$command_file")"
  [[ "$command_line" == *"$expected_pattern"* ]] || return 1
  if [[ -n "$expected_cwd" ]]; then
    actual_cwd="$(readlink -f "$cwd_link" 2>/dev/null || true)"
    [[ "$actual_cwd" == "$expected_cwd" ]] || return 1
  fi
  return 0
}

pid_label() {
  local pid_file="$1"
  local pid
  pid="$(read_pid "$pid_file" 2>/dev/null || true)"
  [[ -n "$pid" ]] && printf '%s' "$pid" || printf '-'
}

bind_host_to_status_host() {
  local host="$1"
  case "$host" in
    ""|"0.0.0.0"|"::"|"[::]") printf '127.0.0.1' ;;
    *) printf '%s' "$host" ;;
  esac
}

api_host() { printf '%s' "${HARNESS_API_HOST:-127.0.0.1}"; }
api_port() { printf '%s' "${HARNESS_API_PORT:-8010}"; }
web_host() { printf '%s' "${HARNESS_WEB_HOST:-0.0.0.0}"; }
web_port() { printf '%s' "${HARNESS_WEB_PORT:-8000}"; }
status_timeout() { printf '%s' "${HARNESS_STATUS_TIMEOUT_SECONDS:-5}"; }
stop_timeout() { printf '%s' "${HARNESS_STOP_TIMEOUT_SECONDS:-10}"; }

api_status_url() {
  local host="${HARNESS_API_STATUS_HOST:-$(bind_host_to_status_host "$(api_host)")}"
  printf 'http://%s:%s/health' "$host" "$(api_port)"
}

web_status_url() {
  local host="${HARNESS_WEB_STATUS_HOST:-$(bind_host_to_status_host "$(web_host)")}"
  printf 'http://%s:%s/' "$host" "$(web_port)"
}

http_check() {
  local url="$1"
  local timeout_seconds
  timeout_seconds="$(status_timeout)"
  "$(python_bin)" - "$url" "$timeout_seconds" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
timeout = float(sys.argv[2])
try:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        if 200 <= response.status < 300:
            print(f"http={response.status}")
            raise SystemExit(0)
        print(f"http={response.status}")
        raise SystemExit(1)
except urllib.error.HTTPError as exc:
    print(f"http={exc.code}")
    raise SystemExit(1)
except (urllib.error.URLError, TimeoutError, OSError) as exc:
    print(f"unreachable={exc.__class__.__name__}")
    raise SystemExit(1)
PY
}

start_background() {
  local name="$1"
  local pid_file="$2"
  local log_file="$3"
  local work_dir="$4"
  local expected_pattern="$5"
  shift 5

  ensure_dirs
  if pid_running "$pid_file" "$expected_pattern" "$work_dir"; then
    msg "$name already running (pid=$(pid_label "$pid_file"))"
    return 0
  fi
  if [[ -f "$pid_file" ]]; then
    warn "$name had a stale or mismatched pid file; removing it"
    rm -f "$pid_file"
  fi
  if is_true "${HARNESS_DRY_RUN:-0}"; then
    msg "dry-run: would start $name (root=$HARNESS_ROOT, log=$log_file, pid_file=$pid_file)"
    return 0
  fi

  : >> "$log_file"
  (
    cd "$work_dir"
    if command -v setsid >/dev/null 2>&1; then
      setsid "$@" >> "$log_file" 2>&1 < /dev/null &
    else
      nohup "$@" >> "$log_file" 2>&1 < /dev/null &
    fi
    printf '%s' "$!" > "$pid_file"
  )
  sleep 1
  if pid_running "$pid_file" "$expected_pattern" "$work_dir"; then
    msg "$name started (pid=$(pid_label "$pid_file"), log=$log_file)"
    return 0
  fi
  rm -f "$pid_file"
  warn "$name did not stay running; inspect log=$log_file"
  return 1
}

stop_background() {
  local name="$1"
  local pid_file="$2"
  local expected_pattern="${3:-}"
  local expected_cwd="${4:-}"
  local timeout_seconds
  local pid elapsed

  timeout_seconds="$(stop_timeout)"

  if ! [[ -f "$pid_file" ]]; then
    msg "$name not running (no pid file)"
    return 0
  fi
  pid="$(read_pid "$pid_file" 2>/dev/null || true)"
  if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
    warn "$name pid file is invalid; removing it"
    rm -f "$pid_file"
    return 0
  fi
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    msg "$name not running (stale pid=$pid); removing pid file"
    rm -f "$pid_file"
    return 0
  fi
  if [[ -n "$expected_pattern" ]] && ! pid_matches_identity "$pid" "$expected_pattern" "$expected_cwd"; then
    warn "$name pid=$pid does not match expected process; removing pid file without stopping"
    rm -f "$pid_file"
    return 0
  fi
  if is_true "${HARNESS_DRY_RUN:-0}"; then
    msg "dry-run: would stop $name (pid=$pid)"
    return 0
  fi

  kill -TERM "$pid" >/dev/null 2>&1 || true
  elapsed=0
  while kill -0 "$pid" >/dev/null 2>&1; do
    if (( elapsed >= timeout_seconds )); then
      warn "$name did not stop after ${timeout_seconds}s; sending KILL"
      kill -KILL "$pid" >/dev/null 2>&1 || true
      break
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  rm -f "$pid_file"
  msg "$name stopped"
}
