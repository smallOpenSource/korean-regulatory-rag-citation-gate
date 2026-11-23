#!/usr/bin/env python
"""Wave-Audit-Defect-Fix A.14 — per-page LLM judge with framework_side
termination clause (per [[llm-as-evaluator-limitation]]).

For every visible-DOM page exposed under PB/ADMIN/AUDIT_VIEWER scope,
capture a Playwright snapshot, send it to Azure GPT-5.5 with the same
v8 PRD §9 framing used by v8_llm_user_spot_check_v2, and record:

- per-page verdict (PASS | FAIL | LIMITATION)
- the explicit framework_side termination clause stating that the
  LLM judge's text_content() extraction and broader-interpretation
  bias produce false positives, and that ANY FAIL verdict MUST be
  cross-checked against the v8 detector ground-truth output before
  it counts as a real defect.

The script is parameterised so a future iteration can broaden the
page list without code changes — pages are read from
``tests/audit-e2e/all-pages-by-role.spec.ts`` PAGES array via a tiny
parser. The original 28-page target rounds the 25 in-scope routes
plus the three login/forbidden/not-found public pages.

Usage:
    python scripts/wave_a14_page_judge.py            # full sweep
    python scripts/wave_a14_page_judge.py --n 3 --pilot
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

SPEC_PATH = PROJECT_ROOT / "tests" / "audit-e2e" / "all-pages-by-role.spec.ts"
OUT_DIR = PROJECT_ROOT / "audit-out" / "stage-3" / "page-judge"
SUMMARY_PATH = OUT_DIR / "summary.json"

WMAH_BASE_URL = os.environ.get(
    "WMAH_FRONTEND_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_WEB_PORT', '8000')}",
)
WMAH_BACKEND_URL = os.environ.get(
    "WMAH_BACKEND_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}",
)
PB_EMAIL = "synthetic.pb1@example.invalid"
PB_PASSWORD = os.environ.get("WMAH_E2E_PASSWORD", "HarnessSynthetic!2026")

FRAMEWORK_SIDE_TERMINATION = (
    "Framework limitation: this judge is a Playwright text_content() + "
    "Azure GPT-5.5 NLI pipeline. It overgeneralises broader-interpretation "
    "UX critique into FAIL verdicts on pages that are designed for an "
    "admin or audit role; any FAIL it produces is a CANDIDATE only, and "
    "must be cross-checked against the v8 detector ground-truth output "
    "(audit-out/v8/cycle-7/* — STRICT_PASS_FINALIZED_LLM_PROXY anchor) "
    "before counting as a real defect. The judge SHOULD NOT BE USED as "
    "the standalone pass/fail gate for v8 PRD compliance — see "
    "[[llm-as-evaluator-limitation]] for the full rationale."
)


def parse_pages_from_spec() -> list[dict[str, str]]:
    """Extract the PAGES array from the Playwright spec without
    requiring a TS toolchain. The entries follow a stable shape:
        { pageFile: "X.tsx", routeKey: "y", urlPath: "/z" }
    """
    src = SPEC_PATH.read_text(encoding="utf-8")
    rows = re.findall(
        r'\{\s*pageFile:\s*"([^"]+)",\s*routeKey:\s*"([^"]+)",\s*urlPath:\s*"([^"]+)"\s*\}',
        src,
    )
    return [{"pageFile": pf, "routeKey": rk, "urlPath": up} for pf, rk, up in rows]


def build_azure_client():
    from openai import AzureOpenAI

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    ), {
        "endpoint": endpoint,
        "deployment": os.environ.get("AZURE_GPT5_MINI_DEPLOYMENT") or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"],
        "api_version": api_version,
    }


JUDGE_PROMPT_TEMPLATE = """당신은 v8 PRD state-graph-traversal page-level 검수단입니다.

이 화면 텍스트가 v8 PRD §9 scope에 해당하는 결함을 가지는지 판정하세요. 본 판정은 framework-side LLM evaluator이며, 다음 보수 원칙을 따릅니다:

[Framework-side termination clause]
{framework_termination}

[화면 context]
- route: {route_key} ({url_path})
- pageFile: {page_file}

[v8 PRD §9 평가 scope — 이 세 가지만 FAIL 후보 사유]
1. 한국어 자연성 위반 (번역체 / 미완성 문장 / 외래어 무근거 노출)
2. BANNED 금칙어 (placeholder "불러오는 중" / "대기 중" / "—" dash / internal ID ADR-/REG- / 영문 fixture marker / ISO microsecond / raw DB field name)
3. Cross-field inconsistency (같은 entity의 status/count/timestamp/role 모순)

[EXCLUDE — FAIL 판정 금지]
- 화면이 role 의도가 아니라는 비평 (ACCESS_RULES SoT)
- 가독성/색상/대비/터치/스크롤/정보 위계 등 UX critique
- list-based UI 자체
- "audit_logs/ai_outputs/email_drafts/action_code/actor_id" 같은 design-intent parenthetical
- "SYN/HarnessPB/WM/RAG" 등 synthetic-only marker

[Page text (Playwright text_content)]
{page_text}

[Output JSON only]
{{"verdict":"PASS|FAIL_CANDIDATE|LIMITATION","reasons":["..."],"requires_v8_cross_check":true}}
"""


async def capture_page_text(
    playwright: object,
    base_url: str,
    backend_url: str,
    url_path: str,
    email: str,
    password: str,
) -> tuple[str, str]:
    """Capture page text_content via a real fresh-login flow.

    The WMAH SPA stores its access token in an in-memory zustand store
    and depends on a httpOnly refresh cookie to bootstrap. Injecting
    `window.localStorage` is therefore not enough — the SPA will still
    redirect to /login because zustand is empty on first render. The
    safe-fast path is to drive the actual login form, wait for the
    post-login redirect to settle, and only then navigate to the
    target route.
    """
    chromium = playwright.chromium  # type: ignore[attr-defined]
    browser = await chromium.launch(headless=True)
    try:
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # 1. Fresh login via the actual UI form (the audit-e2e
        # all-pages-by-role.spec.ts pattern after the A.19 fix).
        await page.goto(f"{base_url}/login", wait_until="networkidle", timeout=20_000)
        await page.fill('input[type="email"]', email)
        await page.fill('input[type="password"]', password)
        await page.click('button[type="submit"]')
        # 700ms post-login settle per [[bfs-auth-race-window]]; the
        # zustand restoreSession may rotate JTI before the React tree
        # commits the new access_token.
        await page.wait_for_url(
            lambda u: not u.endswith("/login"),
            timeout=20_000,
        )
        await page.wait_for_timeout(700)

        # 2. Now navigate to the actual target route.
        await page.goto(f"{base_url}{url_path}", wait_until="networkidle", timeout=20_000)
        await page.wait_for_timeout(500)
        text = await page.text_content("body") or ""
        return text.strip(), str(page.url)
    finally:
        await browser.close()


def judge_page(client, deployment: str, page: dict, text: str) -> dict:
    truncated = text[:6000]
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        framework_termination=FRAMEWORK_SIDE_TERMINATION,
        route_key=page["routeKey"],
        url_path=page["urlPath"],
        page_file=page["pageFile"],
        page_text=truncated,
    )
    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=600,
        )
        raw = resp.choices[0].message.content or ""
        try:
            verdict = json.loads(raw.strip().lstrip("`").lstrip("json").strip("`").strip())
        except json.JSONDecodeError:
            # If the LLM didn't emit clean JSON, record the raw output as a
            # LIMITATION verdict so the framework-side clause is respected.
            verdict = {
                "verdict": "LIMITATION",
                "reasons": [f"LLM emitted non-JSON: {raw[:200]}"],
                "requires_v8_cross_check": True,
            }
        verdict.setdefault("requires_v8_cross_check", True)
        return verdict
    except Exception as exc:  # noqa: BLE001
        return {
            "verdict": "LIMITATION",
            "reasons": [f"{type(exc).__name__}: {exc}"],
            "requires_v8_cross_check": True,
        }


def write_page_verdict(page: dict, verdict: dict) -> None:
    """Persist a per-page verdict file.

    두 PAGES row가 routeKey="public"을 공유(ForbiddenPage /403,
    LoginPage /login)하므로 routeKey 단독 파일명은 충돌해 덮어쓴다.
    urlPath(없으면 routeKey) 기반 안전 slug로 disambiguate.
    """
    raw = (page["urlPath"] or page["routeKey"]).strip("/")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw) or page["routeKey"]
    out_path = OUT_DIR / f"{page['routeKey']}__{slug}.json"
    out_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2))


async def main_async() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=0, help="cap pages (0 = all)")
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pages = parse_pages_from_spec()
    if args.n > 0:
        pages = pages[: args.n]

    print(f"[wave_a14] {len(pages)} pages in sweep", flush=True)

    client, model_meta = build_azure_client()

    from playwright.async_api import async_playwright

    records = []
    async with async_playwright() as pw:
        for i, page in enumerate(pages, 1):
            try:
                text, url = await capture_page_text(
                    pw, WMAH_BASE_URL, WMAH_BACKEND_URL, page["urlPath"], PB_EMAIL, PB_PASSWORD,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[{i}/{len(pages)}] {page['pageFile']} snapshot failed: {exc}", flush=True)
                records.append({
                    "page": page,
                    "snapshot_error": f"{type(exc).__name__}: {exc}",
                    "verdict": "LIMITATION",
                    "requires_v8_cross_check": True,
                })
                continue
            # Role-coverage guard: capture_page_text always logs in as the PB
            # session, but ADMIN-only / AUDIT_VIEWER-only routes redirect a PB
            # to /403 (or render a forbidden body). Judging that as the target
            # page yields a misleading PASS/FAIL, so record LIMITATION and SKIP
            # the LLM judge — keep the LLM only for permitted pages.
            expected_url = f"{WMAH_BASE_URL}{page['urlPath']}"
            if url.rstrip("/").endswith("/403") or url.rstrip("/") != expected_url.rstrip("/"):
                print(
                    f"[{i}/{len(pages)}] {page['routeKey']:24s} -> "
                    "LIMITATION (role redirect)",
                    flush=True,
                )
                verdict = {
                    "verdict": "LIMITATION",
                    "reasons": [
                        "Role redirect: PB session landed on "
                        f"{url} (expected {expected_url}); LLM judge skipped "
                        "to avoid scoring a Forbidden page as the target page.",
                    ],
                    "requires_v8_cross_check": True,
                    "page": page,
                    "snapshot_url": url,
                    "text_len": len(text),
                }
                records.append(verdict)
                write_page_verdict(page, verdict)
                continue
            verdict = judge_page(client, model_meta["deployment"], page, text)
            verdict["page"] = page
            verdict["snapshot_url"] = url
            verdict["text_len"] = len(text)
            records.append(verdict)
            write_page_verdict(page, verdict)
            print(f"[{i}/{len(pages)}] {page['routeKey']:24s} -> {verdict.get('verdict')}", flush=True)

    summary = {
        "n_total": len(records),
        "verdicts": {v: sum(1 for r in records if r.get("verdict") == v) for v in ("PASS", "FAIL_CANDIDATE", "LIMITATION")},
        "framework_side_termination": FRAMEWORK_SIDE_TERMINATION,
        "requires_v8_cross_check_global": True,
        "model": model_meta,
        "pilot": bool(args.pilot),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"[wave_a14] summary -> {SUMMARY_PATH}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
