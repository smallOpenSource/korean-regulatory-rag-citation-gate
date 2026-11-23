# DEV-04 Secret Scan (gitleaks)

## 1. Metadata
- 문서 ID: DEV-04
- Scope: REG-05 T289 의 gitleaks 정적 비밀 스캔 통합 (pre-commit + CI)
- Cross-refs: ADR-003 §3 (gitleaks pre-approved), `.gitleaks.toml`, `scripts/run_gitleaks_scan.sh`, `scripts/validate_no_secrets.py`, SEC-04

## 2. Why
인터넷망 노출 PoC 의 비밀(BGE/Azure/BROKER/JWT/data.go.kr) 이 git 또는 working tree 에 평문으로 유입되면 invalidate 비용 + 재발급 부담 + 감사 risk 가 발생한다. gitleaks 는 ADR-003 §3 에 사전승인되어 있다.

## 3. Components

| 파일 | 역할 |
|---|---|
| `.gitleaks.toml` | 규칙 + 화이트리스트(`replace-*`, `change-me-*`, `example.invalid`, synthetic seed) 단일 진실 |
| `scripts/run_gitleaks_scan.sh` | gitleaks 바이너리 직접 호출 wrapper; report→`.omx/reports/verification/gitleaks-<TS>.json` |
| `scripts/validate_no_secrets.py` | Python wrapper, **ADR-007 JSON triple** 출력(`{verified_at, status, passed, evidence_paths, findings_count, findings_sample}`) |

종료 코드(ADR-007 계약):
- `0` pass — no findings
- `2` fail — findings (sanitized report attached; secret 값은 gitleaks `--redact` 로 마스킹)
- `3` config error — 바이너리/설정 누락 또는 비정상 종료
- `4` token-budget exhaustion — gitleaks 에는 해당사항 없음 (reserved)

## 4. Install (one-time, host)
gitleaks 는 ADR-003 에 따라 바이너리 설치 (pip/npm 금지):
```bash
# Linux x86_64 (Stage 1 PoC 환경)
curl -sSfL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_linux_x64.tar.gz \
  | tar -xz -C /usr/local/bin gitleaks
gitleaks version
```

## 5. Usage

### 5.1 로컬 working-tree 스캔 (default)
```bash
cd <repo-root>
/opt/conda/envs/wm_env/bin/python scripts/validate_no_secrets.py
echo $?   # 0 pass / 2 fail / 3 config error
```

### 5.2 git history 포함 (PR 머지 전 권장)
```bash
/opt/conda/envs/wm_env/bin/python scripts/validate_no_secrets.py --git
```

### 5.3 JSON-only 출력 (CI 파이프라인용)
```bash
/opt/conda/envs/wm_env/bin/python scripts/validate_no_secrets.py --json-only > /tmp/triple.json
jq '.status, .passed' /tmp/triple.json
```

## 6. Pre-commit Hook (optional)

`.git/hooks/pre-commit` 예시 (개발자 로컬용; ADR-003 정합 — 외부 hook 패키지 미사용):
```bash
#!/bin/bash
set -euo pipefail
exec /opt/conda/envs/wm_env/bin/python scripts/validate_no_secrets.py --json-only > /tmp/gitleaks-pre-commit.json
RC=$?
if [[ "${RC}" -ne 0 ]]; then
    echo "[pre-commit] gitleaks blocked commit; see /tmp/gitleaks-pre-commit.json" >&2
    exit "${RC}"
fi
```

## 7. CI Gate (Stage 7 runbook)
- 단계: `verification` 잡 직전.
- 게이트:
  - `0` 또는 `3` (도구 미설치 호스트) → CI 빌드는 fail-close 가 아니라 명시 `tool_unavailable` 로 표시(운영 격상 시 무조건 fail-close 로 전환).
  - `2` → PR 즉시 차단.
- 산출물: `.omx/reports/verification/gitleaks-<TS>.json` 을 CI artifact 로 업로드.

## 8. False Positive 처리

1. 정말로 secret 처럼 보이는 합성/템플릿 토큰이라면 `.gitleaks.toml` `[allowlist].regexes` 에 추가하고 PR description 에 사유 명시.
2. 한 파일 전체를 제외해야 할 경우 `[allowlist].paths` 에 정규식 추가 (예: 합성 seed 파일).
3. **절대로** allowlist 에 실제 운영 비밀 패턴을 추가하지 않는다. allowlist 추가는 reviewer 가 ADR-003 정합 검토 후 머지.

## 9. Audit
- 스캔 결과는 `audit_logs` 에는 기록하지 않는다 (CI 산출물). 단, 비밀 유출 발견 시 후속 조치(`actor_role_change`, 비밀 회전) 는 audit 대상.
- 운영 격상: SIEM 으로 CI gitleaks 결과 forwarder.

## 10. Reference
- gitleaks: https://github.com/gitleaks/gitleaks
- ADR-003 §3 (pre-approved tools).
- REG-05 T289.
- ADR-007 (validator contract specs).
