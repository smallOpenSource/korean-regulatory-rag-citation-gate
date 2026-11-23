#!/usr/bin/env python3
"""Step 2 — AI output business-quality audit (service-readiness v2).

Programmatic checks against 5 random HouseViews and 5 random NBA
scripts. Pillars derived from REG-03 + ADR-005:

A. 부적합 유형 우선 표기 (leading-block markers): HV summary or
   asset_views_json must mention "손실" / "원금" / "변동성" / "부적합".
B. 자산군 수준 권고 (asset-class only): asset_views_json's
   `asset_class` field must reference broad classes (주식/채권/대체/
   현금 등) — no Korean stock ticker patterns (e.g. "삼성전자",
   "현대차").
C. 단정 수익률 금지: no "X% 보장" or "수익률 X%" claims in any HV
   text body.
D. 다양한 risk factors (≥3): risks_json must have at least 3 risks.
E. NBA script structure: 4-block (Opening/Key message/Product
   angle/Closing) — count "[Opening]" + "[Key message]" +
   "[Product angle]" + "[Closing]" markers.
F. NBA no specific tickers: script_text must not contain Korean
   stock names.

Output: audit-out/service-readiness/step2-ai-quality.json + summary.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env", override=True)

# Korean equity tickers/names that the model must NOT recommend by name.
BANNED_NAMES = [
    "삼성전자", "SK하이닉스", "현대차", "기아", "LG에너지솔루션",
    "POSCO홀딩스", "셀트리온", "카카오", "네이버",
]

# Speculative profit claims.
GUARANTEE_PATTERNS = [
    re.compile(r"수익률.*\d+\s*%.*보장"),
    re.compile(r"\d+\s*%.*수익.*확정"),
    re.compile(r"원금.*보장"),
    re.compile(r"손실.*없음"),
]

LEADING_KEYWORDS = ["손실", "원금", "변동성", "부적합", "위험"]
BROAD_ASSET_CLASSES = ["주식", "채권", "대체", "현금", "ETF", "펀드", "예금"]


async def main() -> int:
    db_url = (
        __import__("os").environ.get("DATABASE_URL", "")
        .replace("postgresql+asyncpg://", "postgresql://")
        .strip()
    )
    if not db_url:
        print("DATABASE_URL not set")
        return 2

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=4)
    findings: list[dict[str, Any]] = []
    samples_for_user: list[dict[str, Any]] = []

    try:
        # 5 random house_views with populated content
        hv_rows = await pool.fetch(
            """
            SELECT id, version_no, title, summary,
                   asset_views_json, model_portfolios_json, risks_json,
                   ai_model_name, prompt_tokens, completion_tokens
            FROM house_views
            WHERE asset_views_json::text != '{}'
              AND fail_closed_reason_code IS NULL
            ORDER BY random() LIMIT 5
            """,
        )
        for row in hv_rows:
            r = dict(row)
            hv_id = str(r["id"])
            summary = str(r["summary"] or "")
            assets = json.loads(r["asset_views_json"]) if isinstance(r["asset_views_json"], str) else r["asset_views_json"]
            portfolios = json.loads(r["model_portfolios_json"]) if isinstance(r["model_portfolios_json"], str) else r["model_portfolios_json"]
            risks = json.loads(r["risks_json"]) if isinstance(r["risks_json"], str) else r["risks_json"]

            full_text = json.dumps({"summary": summary, "assets": assets, "risks": risks}, ensure_ascii=False)

            check_a = any(kw in full_text for kw in LEADING_KEYWORDS)
            asset_classes = [a.get("asset_class", "") for a in (assets or [])] if isinstance(assets, list) else []
            check_b_broad = all(any(c in cls for c in BROAD_ASSET_CLASSES) for cls in asset_classes) if asset_classes else False
            check_b_no_ticker = all(name not in full_text for name in BANNED_NAMES)
            check_c_no_guarantee = all(not p.search(full_text) for p in GUARANTEE_PATTERNS)
            check_d_risks = isinstance(risks, list) and len(risks) >= 3

            verdict = {
                "hv_id": hv_id,
                "title": r["title"],
                "version_no": r["version_no"],
                "model": r["ai_model_name"],
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "A_leading_block_keywords": check_a,
                "B_asset_classes_broad": check_b_broad,
                "B_no_ticker_names": check_b_no_ticker,
                "C_no_guarantee_lang": check_c_no_guarantee,
                "D_risks_count": len(risks) if isinstance(risks, list) else 0,
                "D_risks_min3": check_d_risks,
                "asset_classes_seen": asset_classes,
            }
            all_pass = all([check_a, check_b_broad, check_b_no_ticker, check_c_no_guarantee, check_d_risks])
            verdict["pass"] = all_pass
            findings.append({"kind": "house_view", **verdict})

        # 5 random nba_actions with script_text
        nba_rows = await pool.fetch(
            """
            SELECT id, action_type_code, trigger_code, script_text, script_model_name
            FROM nba_actions
            WHERE script_text IS NOT NULL AND script_text != ''
            ORDER BY random() LIMIT 5
            """,
        )
        for row in nba_rows:
            r = dict(row)
            nba_id = str(r["id"])
            text = str(r["script_text"] or "")
            check_e_opening = "[Opening]" in text
            check_e_key = "[Key message]" in text
            check_e_product = "[Product angle]" in text
            check_e_closing = "[Closing]" in text
            check_f_no_ticker = all(name not in text for name in BANNED_NAMES)
            check_c_no_guarantee = all(not p.search(text) for p in GUARANTEE_PATTERNS)
            verdict = {
                "nba_id": nba_id,
                "action_type_code": r["action_type_code"],
                "trigger_code": r["trigger_code"],
                "model": r["script_model_name"],
                "script_length": len(text),
                "E_opening": check_e_opening,
                "E_key": check_e_key,
                "E_product": check_e_product,
                "E_closing": check_e_closing,
                "F_no_ticker_names": check_f_no_ticker,
                "C_no_guarantee_lang": check_c_no_guarantee,
            }
            all_pass = all([check_e_opening, check_e_key, check_e_product, check_e_closing,
                           check_f_no_ticker, check_c_no_guarantee])
            verdict["pass"] = all_pass
            findings.append({"kind": "nba_script", **verdict})

        # Pick first HV + first NBA as samples for user display
        def _to_list(v: Any) -> list:
            if isinstance(v, str):
                v = json.loads(v)
            if isinstance(v, dict):
                # asset_views or risks may be nested under their own key
                for k in ("asset_views", "risks", "items"):
                    if k in v:
                        return v[k] if isinstance(v[k], list) else []
                return []
            return v if isinstance(v, list) else []

        if hv_rows:
            r = dict(hv_rows[0])
            samples_for_user.append({
                "kind": "house_view_sample",
                "title": r["title"],
                "version_no": r["version_no"],
                "summary": r["summary"],
                "asset_views_first_3": _to_list(r["asset_views_json"])[:3],
                "risks_first_3": _to_list(r["risks_json"])[:3],
            })
        if nba_rows:
            r = dict(nba_rows[0])
            samples_for_user.append({
                "kind": "nba_script_sample",
                "action_type": r["action_type_code"],
                "trigger": r["trigger_code"],
                "script_text": r["script_text"],
            })
    finally:
        await pool.close()

    out_path = PROJECT_ROOT / "audit-out" / "service-readiness" / "step2-ai-quality.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"findings": findings, "samples_for_user": samples_for_user}, indent=2, ensure_ascii=False))

    passed = sum(1 for f in findings if f.get("pass"))
    print(f"\n=== Step 2 AI quality: {passed}/{len(findings)} samples PASS ===")
    print(f"{'kind':12s} {'A':>3s} {'B-broad':>8s} {'B-noTicker':>11s} {'C-noGuar':>9s} {'D-risks':>8s} {'E-4block':>9s}")
    for f in findings:
        if f["kind"] == "house_view":
            print(f"  hv     {f['hv_id'][:8]} A={f['A_leading_block_keywords']} "
                  f"Bbroad={f['B_asset_classes_broad']} BnoT={f['B_no_ticker_names']} "
                  f"CnoG={f['C_no_guarantee_lang']} risks={f['D_risks_count']} pass={f['pass']}")
        else:
            print(f"  nba    {f['nba_id'][:8]} Eopen={f['E_opening']} Ekey={f['E_key']} "
                  f"Eprod={f['E_product']} Eclose={f['E_closing']} FnoT={f['F_no_ticker_names']} "
                  f"CnoG={f['C_no_guarantee_lang']} pass={f['pass']}")
    print(f"\nSamples for user display saved to: {out_path}")
    return 0 if passed == len(findings) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
