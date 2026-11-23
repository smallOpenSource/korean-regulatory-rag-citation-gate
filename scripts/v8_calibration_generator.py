#!/usr/bin/env python3
"""
v8_calibration_generator.py
LLM 비평가 보정 후보 셀 100개 생성기 (50 PASS + 50 FAIL)

Usage:
    /opt/conda/envs/playwright/bin/python scripts/v8_calibration_generator.py
    /opt/conda/envs/playwright/bin/python scripts/v8_calibration_generator.py --dry-run
    /opt/conda/envs/playwright/bin/python scripts/v8_calibration_generator.py --start-from 20

Output:
    .omc/state/v8-calibration-candidates/{cell_id}.png
    .omc/state/v8-calibration-candidates/{cell_id}.json
    .omc/state/v8-calibration-candidates-index.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

_ = os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/playwright-browsers")
_ = os.environ.setdefault("DISPLAY", ":99")

from playwright.sync_api import sync_playwright, Page  # pyright: ignore[reportMissingImports]

# ── 상수 ────────────────────────────────────────────────────────────────────────
_WEB_PORT = os.environ.get("HARNESS_WEB_PORT", "8000")
BASE_URL = os.environ.get("V8_BASE_URL", f"http://127.0.0.1:{_WEB_PORT}")
PASSWORD = "HarnessSynthetic!2026"
OUTPUT_DIR = (Path(__file__).resolve().parents[1] / ".omc/state/v8-calibration-candidates")
INDEX_PATH = (Path(__file__).resolve().parents[1] / ".omc/state/v8-calibration-candidates-index.yaml")
VIEWPORT = {"width": 1440, "height": 900}

ACCOUNTS = {
    "PB": "synthetic.pb1@example.invalid",
    "WM": "synthetic.wm1@example.invalid",
    "BRANCH_MANAGER": "synthetic.branch.manager@example.invalid",
    "ADMIN": "synthetic.admin@example.invalid",
    "AUDIT_VIEWER": "synthetic.audit@example.invalid",
}

# 금지 패턴 텍스트 정의 (주입은 textContent 사용 — XSS-safe)
BANNED_INJECTIONS = {
    "BANNED_PLACEHOLDER": {
        "text": "응답을 기다리는 중",
        "reason": "BANNED_PLACEHOLDER 패턴 노출 — 안정화 후에도 로딩 메시지 잔존",
    },
    "BANNED_ISO_MICRO": {
        "text": "2026-04-20T13:52:53.650391Z",
        "reason": "BANNED_ISO_MICRO 패턴 노출 — ISO 마이크로초 타임스탬프 원본 노출",
    },
    "BANNED_ENGLISH": {
        "text": "evidence persisted: 0.91",
        "reason": "BANNED_ENGLISH 패턴 노출 — 내부 영문 용어(evidence, persisted) PB 화면 노출",
    },
    "BANNED_DASH": {
        "text": " - ",
        "reason": "BANNED_DASH 패턴 노출 — null 필드 단독 대시(-) 렌더링",
    },
    "BANNED_RAW_DB_FIELD": {
        "text": "source_as_of: 2026-05-20 09:30:00",
        "reason": "BANNED_RAW_DB_FIELD 패턴 노출 — DB 컬럼명(source_as_of) 한국어 화면 노출",
    },
}

# JS 주입 함수 (textContent 전용 — innerHTML 미사용)
_JS_INJECT = """
(text) => {
    const target = document.querySelector(
        'main, [role="main"], .main-content, #root > div > div, #root > div, body'
    );
    if (!target) return;
    const wrapper = document.createElement('div');
    wrapper.setAttribute('data-cal-inject', 'banned');
    wrapper.style.position = 'relative';
    wrapper.style.zIndex = '1000';
    wrapper.style.padding = '6px 12px';
    wrapper.style.border = '1px solid #dc3545';
    wrapper.style.background = '#fff8f8';
    wrapper.style.margin = '8px';
    wrapper.style.borderRadius = '4px';
    wrapper.style.fontSize = '13px';
    wrapper.style.fontFamily = 'inherit';
    const label = document.createElement('span');
    label.style.color = '#495057';
    label.textContent = text;
    wrapper.appendChild(label);
    target.insertBefore(wrapper, target.firstChild);
}
"""

# JS 가시적 텍스트 추출 (TreeWalker — aria-hidden / display:none 제외)
_JS_VISIBLE_TEXT = r"""
() => {
    const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
        { acceptNode(node) {
            const el = node.parentElement;
            if (!el) return NodeFilter.FILTER_REJECT;
            if (el.closest("[aria-hidden='true']")) return NodeFilter.FILTER_REJECT;
            const s = window.getComputedStyle(el);
            if (s.display === 'none') return NodeFilter.FILTER_REJECT;
            if (s.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
            return NodeFilter.FILTER_ACCEPT;
        }}
    );
    const chunks = [];
    let node;
    while ((node = walker.nextNode())) {
        const t = node.textContent?.trim();
        if (t) chunks.push(t);
    }
    return chunks.join('\n');
}
"""


def build_cell_list() -> list[dict[str, Any]]:
    """100개 셀 정의 (cal-001~050: PASS, cal-051~100: FAIL)"""
    cells: list[dict[str, Any]] = []

    # ── PASS 셀 50개 ──────────────────────────────────────────────────────────
    pass_specs = [
        # dashboard × 5 역할
        ("/dashboard", "PB",             "대시보드 정상 로드"),
        ("/dashboard", "WM",             "대시보드 정상 로드"),
        ("/dashboard", "BRANCH_MANAGER", "대시보드 정상 로드"),
        ("/dashboard", "ADMIN",          "대시보드 정상 로드"),
        ("/dashboard", "AUDIT_VIEWER",   "대시보드 정상 로드"),
        # customers × 4
        ("/customers", "PB",             "고객 목록 정상 로드"),
        ("/customers", "WM",             "고객 목록 정상 로드"),
        ("/customers", "BRANCH_MANAGER", "고객 목록 정상 로드"),
        ("/customers", "ADMIN",          "고객 목록 정상 로드"),
        # customer360 × 3
        ("/customers/33333333-3333-3333-3333-333333333305", "PB",    "고객 상세 정상 로드"),
        ("/customers/33333333-3333-3333-3333-333333333306", "WM",    "고객 상세 정상 로드"),
        ("/customers/33333333-3333-3333-3333-333333333307", "ADMIN", "고객 상세 정상 로드"),
        # nba × 2
        ("/nba", "PB", "후속 조치 관리함 정상 로드"),
        ("/nba", "WM", "후속 조치 관리함 정상 로드"),
        # aftercare × 3
        ("/aftercare", "PB",             "사후 관리 정상 로드"),
        ("/aftercare", "WM",             "사후 관리 정상 로드"),
        ("/aftercare", "BRANCH_MANAGER", "사후 관리 정상 로드"),
        # email-drafts × 2
        ("/email-drafts", "PB", "이메일 초안 정상 로드"),
        ("/email-drafts", "WM", "이메일 초안 정상 로드"),
        # house-views × 4
        ("/house-views", "PB",           "하우스뷰 목록 정상 로드"),
        ("/house-views", "WM",           "하우스뷰 목록 정상 로드"),
        ("/house-views", "AUDIT_VIEWER", "하우스뷰 목록 정상 로드"),
        ("/house-views", "ADMIN",        "하우스뷰 목록 정상 로드"),
        # house-views detail × 3
        ("/house-views/33e6a059-8f3d-482f-8fcb-e33d0884b556", "PB",           "하우스뷰 상세 정상 로드"),
        ("/house-views/de6d7a63-c94a-4a10-b362-83c269ebf61b", "WM",           "하우스뷰 상세 정상 로드"),
        ("/house-views/2a63b510-e80a-4c2e-b564-b90d445eba05", "AUDIT_VIEWER", "하우스뷰 상세 정상 로드"),
        # rag × 3
        ("/rag", "PB",             "RAG 질의응답 정상 로드"),
        ("/rag", "WM",             "RAG 질의응답 정상 로드"),
        ("/rag", "BRANCH_MANAGER", "RAG 질의응답 정상 로드"),
        # batch × 1
        ("/batch", "ADMIN", "배치 모니터링 정상 로드"),
        # audit × 2
        ("/audit", "ADMIN",        "감사 로그 정상 로드"),
        ("/audit", "AUDIT_VIEWER", "감사 로그 정상 로드"),
        # audit-viewer × 2
        ("/audit-viewer", "ADMIN",        "감사 열람 정상 로드"),
        ("/audit-viewer", "AUDIT_VIEWER", "감사 열람 정상 로드"),
        # quarantine × 1
        ("/quarantine", "ADMIN", "격리 대시보드 정상 로드"),
        # rights-notice × 2
        ("/rights-notice", "PB", "권리 안내 정상 로드"),
        ("/rights-notice", "WM", "권리 안내 정상 로드"),
        # dispute-cases × 3
        ("/dispute-cases", "PB",           "이의 제기 목록 정상 로드"),
        ("/dispute-cases", "WM",           "이의 제기 목록 정상 로드"),
        ("/dispute-cases", "AUDIT_VIEWER", "이의 제기 목록 정상 로드"),
        # ai-model-cards × 3
        ("/ai-model-cards", "PB",           "AI 모델 카드 정상 로드"),
        ("/ai-model-cards", "AUDIT_VIEWER", "AI 모델 카드 정상 로드"),
        ("/ai-model-cards", "ADMIN",        "AI 모델 카드 정상 로드"),
        # ai-policy × 2
        ("/ai-policy", "PB", "AI 정책 정상 로드"),
        ("/ai-policy", "WM", "AI 정책 정상 로드"),
        # korean-ai-act × 2
        ("/korean-ai-act", "PB",           "한국 AI 기본법 정상 로드"),
        ("/korean-ai-act", "AUDIT_VIEWER", "한국 AI 기본법 정상 로드"),
        # ai-admin-dashboard × 1
        ("/ai-admin-dashboard", "ADMIN", "AI 관리 대시보드 정상 로드"),
        # autopilot-demo × 2
        ("/autopilot-demo", "PB", "자동화 데모 정상 로드"),
        ("/autopilot-demo", "WM", "자동화 데모 정상 로드"),
    ]

    if len(pass_specs) != 50:
        raise ValueError(f"PASS 셀 정의 오류: {len(pass_specs)}개 (50개 필요)")

    for route, role, content_state in pass_specs:
        n = len(cells) + 1
        cells.append({
            "cell_id": f"cal-{n:03d}",
            "route": route,
            "role": role,
            "content_state_guess": content_state,
            "expected_pass": True,
            "expected_reason": None,
            "defect_type": None,
            "inject_text": None,
        })

    # ── FAIL 셀 50개 (5 패턴 × 10 route×role 베이스) ─────────────────────────
    fail_bases = [
        ("/dashboard",     "PB"),
        ("/customers",     "WM"),
        ("/house-views",   "PB"),
        ("/nba",           "PB"),
        ("/email-drafts",  "WM"),
        ("/aftercare",     "BRANCH_MANAGER"),
        ("/rag",           "PB"),
        ("/rights-notice", "WM"),
        ("/dispute-cases", "AUDIT_VIEWER"),
        ("/ai-model-cards","PB"),
    ]

    defect_state_map = {
        "BANNED_PLACEHOLDER":  "안정화 후 로딩 메시지 잔존",
        "BANNED_ISO_MICRO":    "ISO 마이크로초 타임스탬프 원본 노출",
        "BANNED_ENGLISH":      "내부 영문 용어 PB 화면 노출",
        "BANNED_DASH":         "null 필드 단독 대시 렌더링",
        "BANNED_RAW_DB_FIELD": "DB 컬럼명 한국어 화면 노출",
    }

    for defect_type, content_state in defect_state_map.items():
        inj = BANNED_INJECTIONS[defect_type]
        for route, role in fail_bases:
            n = len(cells) + 1
            cells.append({
                "cell_id": f"cal-{n:03d}",
                "route": route,
                "role": role,
                "content_state_guess": content_state,
                "expected_pass": False,
                "expected_reason": inj["reason"],
                "defect_type": defect_type,
                "inject_text": inj["text"],
            })

    if len(cells) != 100:
        raise ValueError(f"셀 정의 오류: {len(cells)}개 (100개 필요)")

    return cells


def login(page: Page, role: str) -> None:
    """지정 역할로 로그인 (최대 3회 재시도)"""
    email = ACCOUNTS[role]
    try:
        page.goto("about:blank")
        page.context.clear_cookies()
    except Exception:
        pass

    for _attempt in range(1, 4):
        page.goto(f"{BASE_URL}/login", wait_until="load", timeout=15000)
        email_input = page.locator('input[type=email], input[name=email]').first
        if email_input.count() == 0:
            return  # 이미 로그인 상태
        email_input.fill(email)
        page.locator('input[type=password], input[name=password]').first.fill(PASSWORD)
        page.locator('button[type=submit], button:has-text("로그인")').first.click()
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        try:
            page.wait_for_url(lambda url: "/login" not in url.path, timeout=4000)
        except Exception:
            pass
        if "/login" not in page.url:
            return
        time.sleep(0.5)

    raise RuntimeError(f"[{role}] 로그인 실패 — {email}")


def get_visible_text(page: Page) -> str:
    """P1 SoT: TreeWalker — aria-hidden / display:none / visibility:hidden 제외"""
    try:
        return page.evaluate(_JS_VISIBLE_TEXT)
    except Exception:
        return ""


def inject_banned_text(page: Page, text: str) -> None:
    """금지 패턴 텍스트 주입 (textContent 전용, XSS-safe)"""
    try:
        page.evaluate(_JS_INJECT, text)
    except Exception:
        pass


def process_cell(page: Page, cell: dict[str, Any], current_role: list[Any]) -> dict[str, Any]:
    """단일 셀 처리: 네비게이션 → (주입) → 스크린샷 → 메타 저장"""
    cell_id = cell["cell_id"]
    route = cell["route"]
    role = cell["role"]

    # 역할 전환 필요 시 재로그인
    if current_role[0] != role:
        print(f"    → [{role}] 로그인 전환 중...")
        login(page, role)
        current_role[0] = role

    # 페이지 네비게이션
    url = f"{BASE_URL}{route}"
    try:
        page.goto(url, wait_until="load", timeout=20000)
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:
            pass

    time.sleep(1.2)  # 콘텐츠 안정화

    # FAIL 셀: 금지 패턴 텍스트 주입
    if cell.get("inject_text"):
        inject_banned_text(page, cell["inject_text"])
        time.sleep(0.3)

    # 가시적 텍스트 추출 (최대 500자)
    visible_text = get_visible_text(page)[:500]

    # 스크린샷 저장 (1440×900 viewport)
    page.set_viewport_size(VIEWPORT)
    screenshot_path = str(OUTPUT_DIR / f"{cell_id}.png")
    page.screenshot(path=screenshot_path, full_page=False)

    # 메타 JSON 저장 (8 필수 필드)
    meta = {
        "cell_id": cell_id,
        "route": route,
        "role": role,
        "content_state_guess": cell["content_state_guess"],
        "visible_text_snippet": visible_text,
        "expected_pass": cell["expected_pass"],
        "expected_reason": cell["expected_reason"],
        "screenshot_path": screenshot_path,
    }
    (OUTPUT_DIR / f"{cell_id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2)
    )
    return meta


def build_index_yaml(cells_meta: list[dict[str, Any]]) -> str:
    """candidates-index.yaml 생성 (100 entries × 8 fields)"""
    lines: list[str] = [
        "# v8-calibration-candidates-index.yaml",
        f"# 총 {len(cells_meta)}개 셀 | pass: 50 (cal-001~050) | fail: 50 (cal-051~100)",
        "cells:",
    ]
    for m in cells_meta:
        reason = (m.get("expected_reason") or "").replace('"', "'")
        snippet = m.get("visible_text_snippet", "").split("\n")[0][:120]
        lines += [
            f"  - cell_id: {m['cell_id']}",
            f'    route: "{m["route"]}"',
            f"    role: {m['role']}",
            f'    content_state_guess: "{m["content_state_guess"]}"',
            f'    visible_text_snippet: "{snippet}"',
            f"    expected_pass: {str(m['expected_pass']).lower()}",
            f'    expected_reason: "{reason}"',
            f'    screenshot_path: "{m["screenshot_path"]}"',
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="v8 LLM 비평가 보정 후보 셀 100개 생성기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""사용 예시:
  %(prog)s                     # 전체 100개 생성 (이미 완료 셀 건너뜀)
  %(prog)s --dry-run           # 셀 목록만 출력
  %(prog)s --start-from 51     # cal-051부터 재개
        """,
    )
    parser.add_argument("--start-from", type=int, default=1, metavar="N",
                        help="재개 시작 셀 번호 1-indexed (기본: 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="셀 목록만 출력하고 종료")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cells = build_cell_list()

    if args.dry_run:
        for c in cells:
            tag = "PASS" if c["expected_pass"] else f"FAIL({c['defect_type']})"
            print(f"{c['cell_id']}: {c['role']:<15} {c['route']:<55} [{tag}]")
        print(f"\n총 {len(cells)}개 (PASS: 50, FAIL: 50)")
        return

    # 완료 셀 스캔 (재개 지원)
    completed_metas: list[dict[str, Any]] = []
    run_cells: list[dict[str, Any]] = []

    for cell in cells:
        cell_num = int(cell["cell_id"].split("-")[1])
        png_path = OUTPUT_DIR / f"{cell['cell_id']}.png"
        json_path = OUTPUT_DIR / f"{cell['cell_id']}.json"

        if cell_num < args.start_from:
            if json_path.exists():
                try:
                    completed_metas.append(json.loads(json_path.read_text()))
                except Exception:
                    pass
            continue

        if png_path.exists() and json_path.exists():
            try:
                completed_metas.append(json.loads(json_path.read_text()))
                print(f"  ⏭  {cell['cell_id']} 이미 완료 — 건너뜀")
                continue
            except Exception:
                pass
        run_cells.append(cell)

    print(f"\n🚀 생성 대상: {len(run_cells)}개 / 이미 완료: {len(completed_metas)}개")

    if not run_cells:
        print("✅ 모든 셀 이미 완료")
        all_metas = sorted(completed_metas, key=lambda x: x["cell_id"])
        INDEX_PATH.write_text(build_index_yaml(all_metas))
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx = browser.new_context(viewport=VIEWPORT)
        page = ctx.new_page()
        current_role: list[Any] = [None]

        try:
            for cell in run_cells:
                cell_num = int(cell["cell_id"].split("-")[1])
                tag = "PASS" if cell["expected_pass"] else f"FAIL({cell['defect_type']})"
                print(
                    f"[{cell_num:3d}/100] {cell['cell_id']} | "
                    f"{cell['role']:<15} | {cell['route']:<52} | {tag}"
                )
                try:
                    meta = process_cell(page, cell, current_role)
                    completed_metas.append(meta)
                except Exception as exc:
                    print(f"  ⚠️  처리 오류: {exc}")
                    screenshot_path = str(OUTPUT_DIR / f"{cell['cell_id']}.png")
                    try:
                        page.screenshot(path=screenshot_path, full_page=False)
                    except Exception:
                        pass
                    meta = {
                        "cell_id": cell["cell_id"],
                        "route": cell["route"],
                        "role": cell["role"],
                        "content_state_guess": cell["content_state_guess"],
                        "visible_text_snippet": f"ERROR: {exc}",
                        "expected_pass": cell["expected_pass"],
                        "expected_reason": cell["expected_reason"],
                        "screenshot_path": screenshot_path,
                    }
                    (OUTPUT_DIR / f"{cell['cell_id']}.json").write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2)
                    )
                    completed_metas.append(meta)

                if cell_num % 10 == 0:
                    png_n = len(list(OUTPUT_DIR.glob("*.png")))
                    print(f"\n  📍 체크포인트 {cell_num}/100 — PNG {png_n}개 저장됨\n")

        finally:
            ctx.close()
            browser.close()

    all_metas = sorted(completed_metas, key=lambda x: x["cell_id"])
    INDEX_PATH.write_text(build_index_yaml(all_metas))

    png_n = len(list(OUTPUT_DIR.glob("*.png")))
    json_n = len(list(OUTPUT_DIR.glob("*.json")))
    print(f"\n{'='*60}")
    print(f"  ✅ 생성 완료  PNG: {png_n}개  JSON: {json_n}개")
    print(f"  📋 인덱스: {INDEX_PATH}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
