#!/bin/bash
# scripts/run_zap_baseline.sh
# REG-05 T296 — OWASP ZAP baseline scan (PoC demo mode, single shot).
# Exit codes match ADR-007 validator convention:
#   0 = pass (no HIGH severity unresolved)
#   2 = fail (HIGH severity finding remains)
#   3 = config error (docker unavailable, target unreachable, ZAP image pull failed)
#
# Usage:
#   scripts/run_zap_baseline.sh                       # uses HARNESS_API_URL or http://localhost:${HARNESS_API_PORT:-8010}
#   HARNESS_API_URL=https://demo.example.invalid scripts/run_zap_baseline.sh
#
# Output:
#   .omx/reports/zap/zap-baseline-<TS>.json
#   .omx/reports/zap/zap-baseline-<TS>.html
#   .omx/reports/zap/zap-baseline-<TS>.summary.json  (sanitized — feeds SEC-03)
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

# Honor the .env SoT (HARNESS_API_PORT) used by the rest of the lifecycle
# tooling (common.sh / start.sh / run_backend.sh). load_dotenv exports the
# HARNESS_API_* keys so the default below tracks the .env topology; an explicit
# HARNESS_API_URL override still wins.
# shellcheck source=scripts/common.sh
source "${PROJECT_ROOT}/scripts/common.sh"
load_dotenv "${PROJECT_ROOT}/.env"

HARNESS_API_URL="${HARNESS_API_URL:-http://localhost:${HARNESS_API_PORT:-8010}}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_DIR="${PROJECT_ROOT}/.omx/reports/zap"
mkdir -p "${REPORT_DIR}"

JSON_NAME="zap-baseline-${TS}.json"
HTML_NAME="zap-baseline-${TS}.html"
SUMMARY_NAME="zap-baseline-${TS}.summary.json"

# 1) docker must be available (ADR-003 — docker itself is host infra, not a manifest dependency).
if ! command -v docker >/dev/null 2>&1; then
    echo "[zap] config error: docker not on PATH" >&2
    exit 3
fi

# 2) target must be reachable (fail-closed before we burn ZAP startup time)
if ! curl --max-time 5 --silent --fail --output /dev/null "${HARNESS_API_URL}/health" 2>/dev/null; then
    if ! curl --max-time 5 --silent --fail --output /dev/null "${HARNESS_API_URL}" 2>/dev/null; then
        echo "[zap] config error: target ${HARNESS_API_URL} unreachable on /health and /" >&2
        exit 3
    fi
fi

# 3) Run ZAP baseline. -I = informational pass; we enforce HIGH severity below.
echo "[zap] starting baseline scan of ${HARNESS_API_URL}"
set +e
docker run --rm \
    --network=host \
    -v "${REPORT_DIR}:/zap/wrk/:rw" \
    -t ghcr.io/zaproxy/zaproxy:stable zap-baseline.py \
        -t "${HARNESS_API_URL}" \
        -J "${JSON_NAME}" \
        -r "${HTML_NAME}" \
        -I
ZAP_RC=$?
set -e

REPORT_JSON="${REPORT_DIR}/${JSON_NAME}"
SUMMARY_JSON="${REPORT_DIR}/${SUMMARY_NAME}"

if [[ ! -s "${REPORT_JSON}" ]]; then
    echo "[zap] config error: ZAP did not produce ${REPORT_JSON} (rc=${ZAP_RC})" >&2
    exit 3
fi

# 4) Sanitize report: keep counts + CWE + plugin ids; drop request bodies, full URLs,
#    internal hostnames. Feeds SEC-03 publication step.
python3 - "${REPORT_JSON}" "${SUMMARY_JSON}" "${HARNESS_API_URL}" <<'PY'
import json
import re
import sys
from urllib.parse import urlparse

src, dst, target = sys.argv[1], sys.argv[2], sys.argv[3]
host = urlparse(target).hostname or ""
host_re = re.compile(re.escape(host), re.IGNORECASE) if host else None

with open(src) as fh:
    data = json.load(fh)

severity_counts = {"High": 0, "Medium": 0, "Low": 0, "Informational": 0}
findings = []
for site in data.get("site", []):
    for alert in site.get("alerts", []):
        risk = alert.get("riskdesc", "").split(" ", 1)[0] or "Informational"
        severity_counts[risk] = severity_counts.get(risk, 0) + 1
        findings.append({
            "alert": alert.get("alert"),
            "risk": risk,
            "confidence": alert.get("confidence"),
            "cweid": alert.get("cweid"),
            "wascid": alert.get("wascid"),
            "pluginid": alert.get("pluginid"),
            "instance_count": len(alert.get("instances", [])),
            # remediation reference only — no payload echo
            "solution_summary": (alert.get("solution") or "")[:280],
            "reference": (alert.get("reference") or "")[:280],
        })

summary = {
    "scan_target_host_sanitized": host_re.sub("***target-host***", host) if host_re else "unknown",
    "scanner": "ghcr.io/zaproxy/zaproxy:stable",
    "severity_counts": severity_counts,
    "high_count": severity_counts.get("High", 0),
    "findings": findings,
}
with open(dst, "w") as fh:
    json.dump(summary, fh, indent=2)
print(f"[zap] sanitized summary -> {dst} (high={summary['high_count']})")
PY

# 5) Enforce HIGH-severity acceptance gate
HIGH_COUNT=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['high_count'])" "${SUMMARY_JSON}" 2>/dev/null || { echo "[zap] config error: could not read high_count from ${SUMMARY_JSON}" >&2; exit 3; })
# high_count가 비어 있으면 -eq 비교가 무효이므로 별도로 차단합니다.
[[ -z "${HIGH_COUNT}" ]] && { echo "[zap] config error: empty high_count" >&2; exit 3; }
echo "[zap] HIGH-severity findings: ${HIGH_COUNT}"

if [[ "${HIGH_COUNT}" -eq 0 ]]; then
    echo "[zap] PASS — no HIGH findings (raw=${REPORT_JSON}, summary=${SUMMARY_JSON})"
    exit 0
fi

echo "[zap] FAIL — ${HIGH_COUNT} HIGH severity finding(s) remain (summary=${SUMMARY_JSON})" >&2
exit 2
