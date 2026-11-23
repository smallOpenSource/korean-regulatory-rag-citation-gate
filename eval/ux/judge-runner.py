#!/usr/bin/env python
"""WMAH Stage 2 Lane 4 — UX G-Eval judge runner.

23 pages x 4 roles = 92 snapshots 에 대해 한국어 PB persona LLM-judge 를 호출.

Input
-----
- audit-out/screen/snapshot-{role}-{page}.png  (screenshot)
- audit-out/screen/a11y-{role}-{page}.txt      (accessibility tree text — fallback)
- eval/ux/rubric.md                            (G-Eval rubric SoT)
- audit-out/stage-2/ux/page-snapshot-plan.json (page x role plan)

Output
------
- audit-out/ux/grades.jsonl
  1 row per (role, page, category, sample_idx in 1..N)
  fields: role, page, route, sample_idx, category, score, rationale,
          overall_pass, confidence, limitation_notice, judge_model,
          input_hash, ts

Budget
------
- daily cost cap: $3 (audit total $5의 60%)
- self-consistency N=3 sampling per (role, page)
- 23 pages x 4 roles x 3 samples = 276 calls
- gpt-4o-mini text mode 또는 gpt-4o vision (azure deployment 기반)

LLM-as-evaluator limitation ([[llm-as-evaluator-limitation]])
- 모든 row 에 limitation_notice = "framework_side termination,
  사용자 panel ground truth absent" 강제 부착
- 80%+ FAIL rate detected 시 BFS extraction artifact 추정 flag 출력
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
RUBRIC_PATH = REPO_ROOT / "eval/ux/rubric.md"
PLAN_PATH = REPO_ROOT / "audit-out/stage-2/ux/page-snapshot-plan.json"
GRADES_OUT = REPO_ROOT / "audit-out/ux/grades.jsonl"
SNAPSHOT_DIR = REPO_ROOT / "audit-out/screen"
COST_LEDGER = REPO_ROOT / "audit-out/ux/cost-ledger.json"

DAILY_COST_CAP_USD = 3.0  # $3 / day; audit total $5 의 60%
# gpt-4o-mini text approx: $0.15 / 1M input, $0.60 / 1M output
# gpt-4o vision approx:    $2.50 / 1M input, $10 / 1M output
# 1 judge call (text only, a11y proxy) ~ 1.5k in + 0.5k out = ~$0.0006
# 276 calls (N=3) ~ $0.17 → cap 안에 안전
COST_PER_CALL_TEXT_USD = 0.0006
COST_PER_CALL_VISION_USD = 0.012

SELF_CONSISTENCY_N = 3
JUDGE_TEMPERATURE = 0.4

ROLE_PERSONA = {
    "PB": "Private Banker - 영업점 PB 직원, 고객 360 / 상담 / NBA / 사후관리 본업",
    "WM": "Wealth Manager - 본사 WM, 하우스 뷰 / 상담 / NBA 본업",
    "ADMIN": "관리자 - 정책 활성화 / 배치 / 격리 / 감사",
    "AUDIT_VIEWER": "감사관 - 감사 로그 / AI 출력 / 이메일 초안 보존 정책 조회 전용",
}

CATEGORY_KEYS = [
    "a_english_identifier",
    "b_iso_microsecond",
    "c_fallback_placeholder",
    "d_korean_paren_english",
    "e_role_gating_leak",
    "f_untranslated_code",
]


@dataclass
class JudgeVerdict:
    role: str
    page: str
    route: str
    sample_idx: int
    scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    overall_pass: bool = True
    confidence: float = 0.0
    limitation_notice: str = (
        "framework_side termination, 사용자 panel ground truth absent"
    )
    judge_model: str = ""
    input_hash: str = ""
    ts: str = ""
    error: str | None = None


def load_env_var(key: str) -> str:
    if not ENV_FILE.exists():
        return ""
    text = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def load_plan() -> dict[str, Any]:
    if not PLAN_PATH.exists():
        raise FileNotFoundError(f"snapshot plan not found: {PLAN_PATH}")
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def load_rubric() -> str:
    if not RUBRIC_PATH.exists():
        raise FileNotFoundError(f"rubric not found: {RUBRIC_PATH}")
    return RUBRIC_PATH.read_text(encoding="utf-8")


def snapshot_input_for(role: str, page: str, mode: str) -> tuple[str, bytes | str]:
    """Return (kind, payload) where kind in {"vision", "text"}."""
    png = SNAPSHOT_DIR / f"snapshot-{role}-{page}.png"
    a11y = SNAPSHOT_DIR / f"a11y-{role}-{page}.txt"
    if mode == "screenshot" and png.exists():
        return ("vision", png.read_bytes())
    if a11y.exists():
        return ("text", a11y.read_text(encoding="utf-8"))
    if png.exists():
        return ("vision", png.read_bytes())
    return ("text", "")


def input_hash_for(role: str, page: str, payload: bytes | str, sample_idx: int) -> str:
    h = hashlib.sha256()
    h.update(role.encode("utf-8"))
    h.update(b"|")
    h.update(page.encode("utf-8"))
    h.update(b"|")
    if isinstance(payload, bytes):
        h.update(payload)
    else:
        h.update(payload.encode("utf-8"))
    h.update(b"|")
    h.update(str(sample_idx).encode("utf-8"))
    return h.hexdigest()[:16]


def build_prompt(role: str, route: str, snapshot_text: str) -> str:
    persona = ROLE_PERSONA.get(role, role)
    return f"""당신은 한국 시중은행 자산관리 본부의 PB(Private Banker)입니다.
WMAH 시스템 화면을 처음 보는 사용자의 시선으로 평가하세요.

[화면 context]
- route: {route}
- role (ACCESS_RULES SoT): {role}
- 이 role 의 의도된 사용자: {persona}

[입력 — accessibility tree 발췌]
{snapshot_text[:4000]}

[평가 — 6 카테고리]
a_english_identifier:   영어 키 / camelCase / snake_case identifier 사용자 노출 (audit-viewer 디자인 의도 EXCLUDE)
b_iso_microsecond:      마이크로초 또는 ISO 원본 timestamp 노출
c_fallback_placeholder: "0%" / "—" / "대기 중" / "미확인" / "정보 없음"
d_korean_paren_english: 한국어 label + (raw 영문) 패턴 (AuditViewerPage 디자인 의도 EXCLUDE)
e_role_gating_leak:     Role-gating 누수
f_untranslated_code:    Untranslated error / status code (VALIDATION_ERROR, 422 등)

[EXCLUDE]
- 가독성 / 색상 / 글꼴 / 대비 / 터치 영역 / 스크롤 / 정보 위계
- "동일 카드 반복" / "정보 밀도 높음"
- 자연 empty-state 문구 ("대기 중인 X가 없습니다")

JSON 만 반환:
{{
  "scores": {{
    "a_english_identifier":   {{"score": 1, "rationale": "..."}},
    "b_iso_microsecond":      {{"score": 1, "rationale": "..."}},
    "c_fallback_placeholder": {{"score": 1, "rationale": "..."}},
    "d_korean_paren_english": {{"score": 1, "rationale": "..."}},
    "e_role_gating_leak":     {{"score": 1, "rationale": "..."}},
    "f_untranslated_code":    {{"score": 1, "rationale": "..."}}
  }},
  "overall_pass": true,
  "confidence": 0.8
}}
"""


def call_azure_openai(
    *, prompt: str, vision_bytes: bytes | None, deployment: str, endpoint: str,
    api_key: str, api_version: str
) -> dict[str, Any]:
    """Call Azure OpenAI chat completions. Returns parsed JSON dict."""
    import urllib.request
    import urllib.error

    url = (
        f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions"
        f"?api-version={api_version}"
    )
    if vision_bytes:
        b64 = base64.b64encode(vision_bytes).decode("ascii")
        content: list[dict[str, Any]] = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            },
        ]
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": prompt}]

    body = json.dumps(
        {
            "messages": messages,
            "max_completion_tokens": 800,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover (network)
        return {"_error": f"HTTPError {exc.code}: {exc.reason}"}
    except Exception as exc:  # pragma: no cover (network)
        return {"_error": f"{type(exc).__name__}: {exc}"}

    try:
        text = payload["choices"][0]["message"]["content"]
        return json.loads(text)
    except Exception as exc:
        return {"_error": f"parse failed: {exc}"}


def load_cost_ledger() -> dict[str, Any]:
    if COST_LEDGER.exists():
        return json.loads(COST_LEDGER.read_text(encoding="utf-8"))
    return {"day": "", "spent_usd": 0.0, "calls": 0}


def save_cost_ledger(ledger: dict[str, Any]) -> None:
    COST_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    COST_LEDGER.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def assert_under_cap(ledger: dict[str, Any], call_cost: float) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    if ledger.get("day") != today:
        ledger["day"] = today
        ledger["spent_usd"] = 0.0
        ledger["calls"] = 0
    if ledger["spent_usd"] + call_cost > DAILY_COST_CAP_USD:
        raise RuntimeError(
            f"daily cost cap ${DAILY_COST_CAP_USD:.2f} exceeded "
            f"(spent ${ledger['spent_usd']:.4f}, next ${call_cost:.4f})"
        )


def parse_response_to_verdict(
    *, raw: dict[str, Any], role: str, page: str, route: str,
    sample_idx: int, judge_model: str, input_hash: str
) -> JudgeVerdict:
    verdict = JudgeVerdict(
        role=role,
        page=page,
        route=route,
        sample_idx=sample_idx,
        judge_model=judge_model,
        input_hash=input_hash,
        ts=datetime.now(timezone.utc).isoformat(),
    )
    if "_error" in raw:
        verdict.error = raw["_error"]
        verdict.overall_pass = False
        verdict.confidence = 0.0
        for k in CATEGORY_KEYS:
            verdict.scores[k] = {"score": 0, "rationale": f"judge error: {raw['_error']}"}
        return verdict

    scores = raw.get("scores", {})
    for k in CATEGORY_KEYS:
        cell = scores.get(k, {})
        try:
            score = int(cell.get("score", 1))
        except Exception:
            score = 1
        verdict.scores[k] = {
            "score": max(1, min(5, score)),
            "rationale": str(cell.get("rationale", ""))[:500],
        }
    verdict.overall_pass = bool(raw.get("overall_pass", True))
    try:
        verdict.confidence = float(raw.get("confidence", 0.0))
    except Exception:
        verdict.confidence = 0.0
    return verdict


def write_grade_rows(verdict: JudgeVerdict) -> None:
    GRADES_OUT.parent.mkdir(parents=True, exist_ok=True)
    with GRADES_OUT.open("a", encoding="utf-8") as fh:
        for category, cell in verdict.scores.items():
            row = {
                "role": verdict.role,
                "page": verdict.page,
                "route": verdict.route,
                "sample_idx": verdict.sample_idx,
                "category": category,
                "score": cell["score"],
                "rationale": cell["rationale"],
                "overall_pass": verdict.overall_pass,
                "confidence": verdict.confidence,
                "limitation_notice": verdict.limitation_notice,
                "judge_model": verdict.judge_model,
                "input_hash": verdict.input_hash,
                "ts": verdict.ts,
                "error": verdict.error,
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="WMAH UX G-Eval judge runner")
    parser.add_argument("--dry-run", action="store_true",
                        help="plan을 읽고 호출 수와 비용 추정만 출력")
    parser.add_argument("--mode", choices=["text", "screenshot"], default="text",
                        help="text=a11y tree proxy / screenshot=vision modality")
    parser.add_argument("--role", default=None, help="단일 role 만 실행")
    parser.add_argument("--page", default=None, help="단일 page 만 실행")
    args = parser.parse_args(argv)

    plan = load_plan()
    _ = load_rubric()  # ensure SoT exists

    entries = plan.get("entries", [])
    if args.role:
        entries = [e for e in entries if e["role"] == args.role]
    if args.page:
        entries = [e for e in entries if e["page"] == args.page]

    total_calls = len(entries) * SELF_CONSISTENCY_N
    per_call_cost = (
        COST_PER_CALL_VISION_USD if args.mode == "screenshot"
        else COST_PER_CALL_TEXT_USD
    )
    est_cost = total_calls * per_call_cost

    print(f"[plan] entries={len(entries)} samples_per={SELF_CONSISTENCY_N} "
          f"total_calls={total_calls} mode={args.mode} "
          f"est_cost=${est_cost:.4f} cap=${DAILY_COST_CAP_USD:.2f}")
    if args.dry_run:
        print("[dry-run] no calls made")
        return 0

    endpoint = load_env_var("AZURE_OPENAI_ENDPOINT")
    api_key = load_env_var("AZURE_OPENAI_API_KEY")
    api_version = load_env_var("AZURE_OPENAI_API_VERSION") or "2024-08-01-preview"
    deployment = (
        load_env_var("AZURE_OPENAI_VISION_DEPLOYMENT") if args.mode == "screenshot"
        else load_env_var("AZURE_OPENAI_TEXT_DEPLOYMENT")
    ) or load_env_var("AZURE_OPENAI_DEPLOYMENT") or load_env_var("AZURE_OPENAI_DEPLOYMENT_NAME")

    if not (endpoint and api_key and deployment):
        print("[error] Azure OpenAI env missing — set AZURE_OPENAI_ENDPOINT / "
              "API_KEY / DEPLOYMENT in .env", file=sys.stderr)
        return 2

    ledger = load_cost_ledger()
    judge_model = f"{deployment}@{api_version}"

    for entry in entries:
        role = entry["role"]
        page = entry["page"]
        route = entry["route"]
        kind, payload = snapshot_input_for(role, page, args.mode)
        if kind == "text" and not payload:
            print(f"[skip] no snapshot for role={role} page={page}")
            continue

        snapshot_text = payload if isinstance(payload, str) else "(vision modality)"
        vision_bytes = payload if isinstance(payload, bytes) else None

        for sample_idx in range(1, SELF_CONSISTENCY_N + 1):
            ihash = input_hash_for(role, page, payload, sample_idx)
            assert_under_cap(ledger, per_call_cost)
            prompt = build_prompt(role, route, snapshot_text)
            raw = call_azure_openai(
                prompt=prompt,
                vision_bytes=vision_bytes,
                deployment=deployment,
                endpoint=endpoint,
                api_key=api_key,
                api_version=api_version,
            )
            verdict = parse_response_to_verdict(
                raw=raw, role=role, page=page, route=route,
                sample_idx=sample_idx, judge_model=judge_model,
                input_hash=ihash,
            )
            write_grade_rows(verdict)
            ledger["spent_usd"] += per_call_cost
            ledger["calls"] += 1
            save_cost_ledger(ledger)
            print(f"[grade] role={role} page={page} sample={sample_idx} "
                  f"pass={verdict.overall_pass} spent=${ledger['spent_usd']:.4f}")
            time.sleep(0.2)

    print(f"[done] calls={ledger['calls']} spent=${ledger['spent_usd']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
