#!/usr/bin/env bash
# scripts/check_no_poc_in_prod.sh — CI gate for ADR-004 §"Dead-Code Elimination".
#
# Fails the build if the production frontend bundle (or any explicitly listed
# "prod build" artifact) contains any reference to the PoC governance lane.
#
# Search scope:
#   1. apps/web/dist               — Vite production bundle output
#   2. apps/web/build              — alternative output dir (some CI configs)
#   3. apps/api/dist               — bundled backend artifacts (if any)
#   Override with the env var PROD_BUILD_DIRS (colon-separated).
#
# Forbidden tokens (case-sensitive — leaked source strings, not the human-prose
# documentation):
#   - PoC_AUTO_APPROVAL
#   - X-Poc-Demo-Mode
#   - VITE_IS_POC_BUILD
#   - poc_auto_approval_guard
#   - poc_auto_approval_used
#
# Pass criteria: every configured directory exists and contains none of the
# forbidden tokens. Missing build directory → soft pass with a WARN (so the
# gate is informational before the first prod build runs).
#
# Exit codes:
#   0 — clean (no PoC references)
#   1 — leak found
#   2 — invocation error (bad arguments)

set -euo pipefail
# DEFAULT_DIRS는 CWD 상대 경로이므로 리포지토리 루트로 이동해야 게이트가 동작합니다.
cd "$(dirname "$0")/.." || exit 1

DEFAULT_DIRS=("apps/web/dist" "apps/web/build" "apps/api/dist")
IFS=':' read -r -a PROD_DIRS_FROM_ENV <<<"${PROD_BUILD_DIRS:-}"

if [[ ${#PROD_DIRS_FROM_ENV[@]} -gt 0 && -n "${PROD_DIRS_FROM_ENV[0]}" ]]; then
    SEARCH_DIRS=("${PROD_DIRS_FROM_ENV[@]}")
else
    SEARCH_DIRS=("${DEFAULT_DIRS[@]}")
fi

FORBIDDEN_TOKENS=(
    "PoC_AUTO_APPROVAL"
    "X-Poc-Demo-Mode"
    "VITE_IS_POC_BUILD"
    "poc_auto_approval_guard"
    "poc_auto_approval_used"
)

# Per ADR-004: any file path *containing* /poc/ or /demo/ is allowed to mention
# the tokens (these segments cannot exist in a prod bundle anyway, but keeping
# the carve-out keeps the rule consistent with the ESLint backstop).
EXCLUDE_PATH_PATTERN='(/poc/|/demo/|\.map$|SOURCEMAP|sourcemap)'

leaks_found=0
checked_dirs=0

scan_dir() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        printf 'WARN  scripts/check_no_poc_in_prod.sh: prod-build dir %s not present (skipping)\n' "$dir" >&2
        return 0
    fi
    checked_dirs=$((checked_dirs + 1))
    local found_any=0
    for token in "${FORBIDDEN_TOKENS[@]}"; do
        # grep -F: literal, -r: recursive, -l: just file names, -I: skip binary.
        # `|| true` so empty matches don't trip `set -e`.
        local hits
        hits="$(grep -rIlF -- "$token" "$dir" 2>/dev/null || true)"
        if [[ -z "$hits" ]]; then
            continue
        fi
        local kept_hits=""
        while IFS= read -r path; do
            [[ -z "$path" ]] && continue
            if [[ "$path" =~ $EXCLUDE_PATH_PATTERN ]]; then
                continue
            fi
            kept_hits+="$path"$'\n'
        done <<<"$hits"
        if [[ -n "${kept_hits// /}" ]]; then
            printf 'FAIL  prod-build contains forbidden PoC token %q in %s:\n' "$token" "$dir" >&2
            printf '%s' "$kept_hits" | sed 's/^/      /' >&2
            found_any=1
        fi
    done
    if [[ "$found_any" -ne 0 ]]; then
        leaks_found=1
    fi
}

for dir in "${SEARCH_DIRS[@]}"; do
    scan_dir "$dir"
done

if [[ "$checked_dirs" -eq 0 ]]; then
    printf 'WARN  scripts/check_no_poc_in_prod.sh: no prod-build directories found; gate is a no-op.\n' >&2
    printf '      (informational pass — re-run after `pnpm build:prod`)\n' >&2
    exit 0
fi

if [[ "$leaks_found" -ne 0 ]]; then
    printf 'FAIL  prod-build dead-code-elimination gate detected PoC_AUTO_APPROVAL leakage (ADR-004 §5).\n' >&2
    exit 1
fi

printf 'OK    prod-build contains no PoC_AUTO_APPROVAL references (%d dir scanned).\n' "$checked_dirs"
exit 0
