#!/usr/bin/env python
"""v8_detector_L5_visual_critic.py — Stage 2 G2 deliverable (T107)

L5 시각 quality LLM vision critic. Opus-4-7 vision (image + accessibility tree).
Per-cell PASS = (zero L1-L4 finding ∧ matches expected layout ∧ no console error
∧ axe-core violations = 0).

NOTE: Stage 2 framework deliverable. Live Anthropic vision API call requires
ANTHROPIC_API_KEY env var. Without key, returns dry-run skeleton.

Cache: key = sha256(screenshot bytes + viewport), value = vision verdict JSON.
Per-viewport independent assessment (4 viewports per cell).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
L5_CACHE_DIR = REPO_ROOT / ".omc/state/v8-l5-cache"
DEFAULT_MODEL = os.environ.get("V8_L5_MODEL", "claude-opus-4-7")

L5_PROMPT_TEMPLATE = """당신은 웹화면 시각 품질 검토자입니다. 이 screenshot이 PB(Private Banker) 업무 화면으로 적합한지 평가하세요.

평가 기준:
1. 레이아웃: 잘림/겹침/scroll bar 미정렬 여부
2. placeholder/empty-state: "—" / "대기 중" / 빈 박스 영구 노출 여부
3. 한국어 텍스트 가독성: 글꼴 크기/줄간격/색상 대비
4. 시각 일관성: 컴포넌트 간 간격/정렬/색상 통일성
5. 접근성: focus indicator/aria-label 시각 단서

viewport: {viewport}
accessibility tree (요약):
{a11y_tree}

다음 JSON 형식으로만 응답:
{{"pass": true|false, "issues": ["issue1", "issue2"], "confidence": 0.0~1.0, "reason": "간단 사유"}}
"""


@dataclass
class L5Verdict:
    pass_: bool
    issues: list[str]
    confidence: float
    reason: str
    cached: bool = False
    model: str = DEFAULT_MODEL


def screenshot_hash(screenshot_path: pathlib.Path, viewport: str) -> str:
    h = hashlib.sha256()
    h.update(screenshot_path.read_bytes())
    h.update(viewport.encode("utf-8"))
    return h.hexdigest()[:32]


def cache_get(sha: str) -> dict[str, Any] | None:
    path = L5_CACHE_DIR / f"{sha}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def cache_put(sha: str, verdict: dict[str, Any]) -> None:
    L5_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (L5_CACHE_DIR / f"{sha}.json").write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def call_azure_openai_vision_api(
    screenshot_path: pathlib.Path,
    viewport: str,
    a11y_tree: str,
) -> dict[str, Any]:
    """Live Azure OpenAI vision API call (gpt-5.5 multimodal).

    Reuses wmah dispatcher pattern. Multimodal message format per OpenAI Chat
    Completions: content array with image_url + text parts.
    """
    try:
        from openai import AzureOpenAI  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError("openai package missing. Required for L5 Azure critic.") from e

    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview").strip()
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.5").strip()
    if not api_key or not endpoint:
        raise RuntimeError(
            "AZURE_OPENAI_API_KEY + AZURE_OPENAI_ENDPOINT required for L5 Azure critic"
        )

    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )
    image_b64 = base64.standard_b64encode(screenshot_path.read_bytes()).decode("ascii")
    image_url = f"data:image/png;base64,{image_b64}"
    prompt = L5_PROMPT_TEMPLATE.format(viewport=viewport, a11y_tree=a11y_tree[:2000])

    delay = 1.0
    for attempt in range(5):
        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": "당신은 웹화면 시각 품질 검토자입니다. JSON만 응답하세요."},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": prompt},
                    ]},
                ],
                max_completion_tokens=1024,
                response_format={"type": "json_object"},
            )
            raw = (response.choices[0].message.content or "{}").strip()
            return json.loads(raw)
        except Exception as e:
            if attempt < 4:
                time.sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"L5 Azure vision API call failed after 5 attempts: {e}") from e
    raise RuntimeError("unreachable")


def evaluate_l5(
    screenshot_path: pathlib.Path,
    viewport: str,
    a11y_tree: str = "",
    dry_run: bool = False,
) -> L5Verdict:
    if not screenshot_path.exists():
        return L5Verdict(
            pass_=False,
            issues=[f"screenshot missing: {screenshot_path}"],
            confidence=1.0,
            reason="screenshot_path not found",
        )
    sha = screenshot_hash(screenshot_path, viewport)
    cached = cache_get(sha)
    if cached is not None:
        return L5Verdict(
            pass_=cached.get("pass", False),
            issues=cached.get("issues", []),
            confidence=cached.get("confidence", 0.0),
            reason=cached.get("reason", ""),
            cached=True,
            model=cached.get("model", DEFAULT_MODEL),
        )
    if dry_run:
        return L5Verdict(
            pass_=True,
            issues=[],
            confidence=0.0,
            reason="dry-run (no vision API call)",
            cached=False,
            model="dry-run",
        )
    result = call_azure_openai_vision_api(screenshot_path, viewport, a11y_tree)
    model_used = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.5")
    result["model"] = model_used
    cache_put(sha, result)
    return L5Verdict(
        # fail-closed: a malformed/truncated vision verdict missing "pass" is a defect
        # to surface for human review, not a silent PASS (fail-closed posture, #4-A audit).
        pass_=result.get("pass", False),
        issues=result.get("issues", []),
        confidence=result.get("confidence", 0.0),
        reason=result.get("reason", ""),
        cached=False,
        model=model_used,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L5 visual quality LLM critic")
    p.add_argument("--screenshot", type=pathlib.Path, required=True)
    p.add_argument("--viewport", type=str, required=True,
                   choices=["desktop_wide", "desktop_narrow", "tablet", "mobile"])
    p.add_argument("--a11y-tree-file", type=pathlib.Path, default=None)
    p.add_argument("--dry-run", action="store_true",
                   help="skeleton mode, no API call")
    args = p.parse_args(argv)

    a11y_tree = ""
    if args.a11y_tree_file is not None and args.a11y_tree_file.exists():
        a11y_tree = args.a11y_tree_file.read_text(encoding="utf-8")

    verdict = evaluate_l5(args.screenshot, args.viewport, a11y_tree,
                          dry_run=args.dry_run)
    out: dict[str, Any] = {
        "pass": verdict.pass_,
        "issues": verdict.issues,
        "confidence": verdict.confidence,
        "reason": verdict.reason,
        "cached": verdict.cached,
        "model": verdict.model,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if verdict.pass_ else 1


if __name__ == "__main__":
    sys.exit(main())
