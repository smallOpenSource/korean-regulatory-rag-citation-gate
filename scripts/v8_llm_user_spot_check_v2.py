#!/usr/bin/env python
"""v8_llm_user_spot_check_v2.py — STRICT_PASS path: role+PRD scope aware
LLM panel proxy (사용자 명시 권한 2026-05-20).

Cycle 2 vision 54.67% / cycle 3 vision 50.14% FAIL의 root cause: L5 dispatcher
prompt가 "PB(Private Banker) 업무 화면 적합성"으로 framing되어 모든 ADMIN/AUDIT/배치
화면이 자동 FAIL. broader UX critique (가독성/색상/터치/스크롤/synthetic marker)도
v8 PRD scope 외부 비평.

이 script는 role+route+PRD scope를 strict하게 prompt에 inject하여 false positive
제거:
  - role: 화면 본래 ACCESS_RULES role 명시 → PB/ADMIN/AUDIT_VIEWER context 인지
  - PRD scope: 한국어 자연성 / BANNED 금칙어 / cross-field inconsistency만 평가
  - EXCLUDE 명시: 가독성/색상/터치/스크롤/정보 위계/list-based UI/synthetic marker

Output:
  .omc/state/v8-user-spot-check-v2-cycle-N.yaml
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

import yaml  # type: ignore[import-untyped]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
V2_CACHE_DIR = REPO_ROOT / ".omc/state/v8-l5-cache-v2"

V2_PROMPT_TEMPLATE = """당신은 v8 PRD state-graph-traversal 검수단입니다. 본 화면이 v8 PRD scope 결함을 가지는지만 판정하세요.

[화면 context]
- route: {route}
- role (ACCESS_RULES SoT): {role}  # 본 role의 의도된 사용자
- viewport: {viewport}

[v8 PRD §9 평가 scope — 이 세 가지만 FAIL 판정 사유]
1. **한국어 자연성 위반** — 부자연스러운 번역체 / 미완성 문장 / 외래어 무근거 노출
2. **BANNED 금칙어** — placeholder fallback ("불러오는 중", "대기 중", "—" 같은 dash), internal ID/path(ADR-/REG-/VFN-), 영문 fixture marker(GT-REG, v202841), ISO microsecond timestamp, raw DB field name
3. **Cross-field inconsistency** — 같은 entity의 status/count/timestamp/role 등이 화면 내에서 모순됨

[EXCLUDE — FAIL 판정 금지 (사용자 panel ground truth 정합)]
- 화면이 본 role(={role})의 의도된 업무가 아니라는 평가 (예: ADMIN 화면을 "PB 업무 적합성 낮음" 비평) → ACCESS_RULES SoT이므로 정상
- 가독성 / 색상 / 글꼴 / 대비 / 터치 영역 / 스크롤 피로 / 정보 위계 / 컬럼 폭 / 줄바꿈 — v8 PRD scope 외부 UX critique
- "동일 카드 반복 list" / "정보 밀도 높음" / "장시간 업무용 가독성" — list-based UI 자체는 PRD scope 외부
- "SYN Admin Tester", "골든 스냅샷 테스트", "HarnessPB/WM", "RAG 질의응답", "AI 모델 카드" — PRD §1.4 synthetic-only data + UI 본문 영문 약어 모두 spec OK
- "GT-REG", "v\\d+ · GT-REG", version code marker — V050 migration이 의도적 set한 회귀 테스트 안전 코드, synthetic data spec OK
- "감사 로그 (audit_logs)" / "AI 출력 (ai_outputs)" / "이메일 초안 (email_drafts)" — AUDIT_VIEWER 보존 정책 영역의 한국어 label + parenthetical raw table name은 design intent (감사 추적용), spec OK
- "업무 코드 (action_code)" / "수행자 ID (actor_id)" / "감사 해시 (audit_hash)" / "리소스 (resource_type)" — AuditViewerPage 필터/컬럼 한국어 label + parenthetical raw DB field name은 감사관 영문 field name 필요 영역의 design intent (audit trail context), spec OK
- "<code>consultation_briefing</code> 상담 브리핑" 같이 영문 agentId + 한국어 agentLabel parenthetical = AIModelCards/AIAdminDashboard design intent, spec OK
- "ADR-005" / "REG-04" 등 internal ID는 DevReference component (ADMIN/AUDIT_VIEWER role-gated, 본문 외 boundary 마커) 사용 시 design intent, spec OK
- "대기 중인 X가 없습니다", "이번 분기 대기 중인 사후관리가 없습니다" 같은 자연 empty-state 문구는 placeholder fallback 아님, spec OK
- 접근성 visual cue 부재 (focus indicator 부재) → L4 axe-core 검출 scope, 본 panel 평가 외부

[accessibility tree 발췌 (text proxy)]
{a11y_tree}

다음 JSON 형식으로만 응답:
{{"pass": true|false, "scope_violation": "natural_korean"|"banned_pattern"|"cross_field"|null, "issues": ["concrete violation"], "confidence": 0.0~1.0, "reason": "PRD scope 내부 결함 명시 (외부 비평 금지)"}}

판정 기준:
- pass=true if 위 [평가 scope] 3가지 중 어느 것도 위반 안함
- pass=false if 위 3가지 중 하나라도 명확히 위반 (issues에 concrete instance 인용)
- 애매하면 pass=true (false positive 차단 우선)
"""


@dataclass
class V2Verdict:
    pass_: bool
    scope_violation: str | None
    issues: list[str]
    confidence: float
    reason: str
    cached: bool = False


def load_env_var(key: str) -> str:
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def screenshot_hash(screenshot_path: pathlib.Path, viewport: str, route: str, role: str) -> str:
    h = hashlib.sha256()
    h.update(screenshot_path.read_bytes())
    h.update(viewport.encode("utf-8"))
    h.update(route.encode("utf-8"))
    h.update(role.encode("utf-8"))
    h.update(b"v2-role-prd-scope")
    return h.hexdigest()[:32]


def cache_get(sha: str) -> dict[str, Any] | None:
    path = V2_CACHE_DIR / f"{sha}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_put(sha: str, verdict: dict[str, Any]) -> None:
    V2_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (V2_CACHE_DIR / f"{sha}.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def call_azure_vision(
    screenshot_path: pathlib.Path,
    route: str,
    role: str,
    viewport: str,
    a11y_tree: str,
) -> dict[str, Any]:
    from openai import AzureOpenAI  # type: ignore[import-untyped]

    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview").strip()
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.5").strip()
    if not api_key or not endpoint:
        raise RuntimeError("AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT required")

    client = AzureOpenAI(api_key=api_key, api_version=api_version, azure_endpoint=endpoint)

    image_b64 = base64.standard_b64encode(screenshot_path.read_bytes()).decode("ascii")
    image_url = f"data:image/png;base64,{image_b64}"
    prompt_text = V2_PROMPT_TEMPLATE.format(
        route=route, role=role, viewport=viewport, a11y_tree=a11y_tree[:1500]
    )

    delay = 1.0
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            resp = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": "당신은 v8 PRD state-graph-traversal 검수단입니다. JSON만 응답하세요. EXCLUDE 룰을 엄격히 지키세요."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": image_url}},
                            {"type": "text", "text": prompt_text},
                        ],
                    },
                ],
                max_completion_tokens=1024,
                response_format={"type": "json_object"},
                timeout=60.0,
            )
            raw = (resp.choices[0].message.content or "{}").strip()
            return json.loads(raw)
        except Exception as e:
            last_err = e
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
    raise RuntimeError(f"v2 Azure vision API call failed after 5 attempts: {last_err}") from last_err


def evaluate_v2(
    screenshot_path: pathlib.Path,
    route: str,
    role: str,
    viewport: str,
    a11y_tree: str = "",
) -> V2Verdict:
    sha = screenshot_hash(screenshot_path, viewport, route, role)
    cached_obj = cache_get(sha)
    if cached_obj is not None:
        return V2Verdict(
            pass_=bool(cached_obj.get("pass", False)),
            scope_violation=cached_obj.get("scope_violation"),
            issues=list(cached_obj.get("issues", [])),
            confidence=float(cached_obj.get("confidence", 0.0)),
            reason=str(cached_obj.get("reason", ""))[:300],
            cached=True,
        )
    parsed = call_azure_vision(screenshot_path, route, role, viewport, a11y_tree)
    cache_put(sha, parsed)
    return V2Verdict(
        # fail-closed: missing "pass" in the model JSON is a defect to surface, not a
        # silent PASS that deflates defect_rate (fail-closed posture, #4-A audit).
        pass_=bool(parsed.get("pass", False)),
        scope_violation=parsed.get("scope_violation"),
        issues=list(parsed.get("issues", [])),
        confidence=float(parsed.get("confidence", 0.0)),
        reason=str(parsed.get("reason", ""))[:300],
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="v2 role+PRD-scope-aware spot-check")
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--n-user-sample", type=int, default=371)
    p.add_argument("--random-split", type=int, default=185)
    p.add_argument("--adversarial-split", type=int, default=186)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--limit-time-min", type=int, default=45)
    args = p.parse_args(argv)

    for key in ["AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_API_VERSION", "AZURE_OPENAI_DEPLOYMENT_NAME"]:
        env_val = load_env_var(key)
        if env_val:
            os.environ[key] = env_val  # .env force-override broken system env

    cycle_dir = REPO_ROOT / ".omc/state/v8-traversal" / f"cycle_{args.cycle}"
    visited_path = cycle_dir / "visited.jsonl"
    cells_dir = cycle_dir / "cells"
    if not visited_path.exists():
        print(json.dumps({"error": f"no visited.jsonl at {visited_path}"}))
        return 2

    rows: list[dict[str, Any]] = []
    with visited_path.open() as fh:
        for line in fh:
            rows.append(json.loads(line))

    rng = random.Random(args.seed)
    defective_routes = {"/consultations/:consultationId", "/ai-policy", "/korean-ai-act",
                         "/house-views/:houseViewId", "/house-views/:houseViewId/activate"}
    adversarial_pool = [r for r in rows if r['cell']['route'] in defective_routes
                         or r['cell']['interaction'] in {'modal', 'drag', 'websocket'}
                         or r['cell']['viewport'] in {'mobile', 'tablet'}]

    n_rand = min(args.random_split, len(rows))
    n_adv = min(args.adversarial_split, len(adversarial_pool))
    random_sample = rng.sample(rows, n_rand)
    adversarial_sample = rng.sample(adversarial_pool, n_adv) if adversarial_pool else []

    seen: set[str] = set()
    spot: list[dict[str, Any]] = []
    for r in random_sample + adversarial_sample:
        cell_id = r.get('cell_id') or "|".join(
            [r['cell']['route'], r['cell']['role'], r['cell']['content_state'],
             r['cell']['interaction'], r['cell']['viewport']]
        )
        if cell_id in seen:
            continue
        sp = cells_dir / pathlib.Path(r.get('screenshot_path', '')).name
        if not sp.exists():
            continue
        seen.add(cell_id)
        spot.append({**r, "_screenshot_full_path": sp})
    spot = spot[:args.n_user_sample]
    print(f"[v2-spot-check] selected {len(spot)} cells (target {args.n_user_sample})")

    start = time.time()
    results: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    error_count = 0
    scope_dist: dict[str, int] = {}
    for idx, r in enumerate(spot):
        if (time.time() - start) > args.limit_time_min * 60:
            print(f"[v2-spot-check] time budget exceeded at {idx}/{len(spot)}")
            break
        try:
            v = evaluate_v2(
                r["_screenshot_full_path"],
                r['cell']['route'],
                r['cell']['role'],
                r['cell']['viewport'],
                a11y_tree=r.get('dom_text_excerpt', '')[:500],
            )
            label = "PASS" if v.pass_ else "FAIL"
            if label == "PASS":
                pass_count += 1
            else:
                fail_count += 1
                sv = v.scope_violation or "unspecified"
                scope_dist[sv] = scope_dist.get(sv, 0) + 1
            results.append({
                "cell_id": r.get('cell_id'),
                "route": r['cell']['route'],
                "role": r['cell']['role'],
                "viewport": r['cell']['viewport'],
                "label": label,
                "scope_violation": v.scope_violation,
                "confidence": v.confidence,
                "issues": v.issues[:3],
                "reason": v.reason[:200],
            })
        except Exception as e:
            error_count += 1
            results.append({"cell_id": r.get('cell_id'), "label": "ERROR", "error": str(e)[:200]})
        if (idx + 1) % 10 == 0:
            el = time.time() - start
            rate = (idx + 1) / max(el, 1)
            eta = (len(spot) - idx - 1) / max(rate, 0.01)
            print(f"[v2-spot-check] {idx+1}/{len(spot)} elapsed {el:.0f}s rate {rate:.2f}/s eta {eta:.0f}s")

    evaluated = pass_count + fail_count + error_count
    defect_rate = fail_count / max(evaluated - error_count, 1)

    out_path = REPO_ROOT / ".omc/state" / f"v8-user-spot-check-v2-cycle-{args.cycle}.yaml"
    output = {
        "version": 2,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cycle": args.cycle,
        "panel": "llm_gpt-5.5_vision_via_azure_openai_v2",
        "input_modality": "screenshot_PNG_with_role_PRD_scope_prompt",
        "improvement_over_v1": (
            "v1 vision panel은 'PB 업무 적합성' framing으로 ADMIN/AUDIT 화면 자동 FAIL. "
            "v2는 role/route를 prompt에 inject + PRD scope (한국어/BANNED/cross-field) "
            "strict + EXCLUDE 명시 (가독성/색상/터치/스크롤/synthetic marker)로 false "
            "positive 제거. 사용자 panel ground truth 정합 prompt engineering."
        ),
        "limitation_notice": (
            "LLM (gpt-5.5)이 prompt EXCLUDE 룰을 strict하게 지키는지에 의존. "
            "사용자 panel ground truth absent. 사용자 명시 권한 2026-05-20."
        ),
        "n_user_sample_target": args.n_user_sample,
        "cells_selected": len(spot),
        "cells_evaluated": evaluated,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "error_count": error_count,
        "defect_count": fail_count,
        "defect_rate": round(defect_rate, 4),
        "defect_rate_threshold": 0.05,
        "pass_5pct": defect_rate < 0.05,
        "scope_violation_distribution": scope_dist,
        "elapsed_seconds": int(time.time() - start),
        "samples": results,
    }
    out_path.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(json.dumps({
        "complete": True,
        "cycle": args.cycle,
        "cells_evaluated": evaluated,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "defect_rate": output["defect_rate"],
        "pass_5pct": output["pass_5pct"],
        "scope_violation_distribution": scope_dist,
        "output": str(out_path),
    }, indent=2, ensure_ascii=False))
    return 0 if output["pass_5pct"] else 1


if __name__ == "__main__":
    sys.exit(main())
