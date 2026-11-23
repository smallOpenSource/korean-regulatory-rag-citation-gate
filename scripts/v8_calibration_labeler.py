#!/usr/bin/env python3
"""
v8_calibration_labeler.py
LLM 비평가 보정 셀 사용자 레이블링 CLI

Usage:
    /opt/conda/envs/wm_env/bin/python scripts/v8_calibration_labeler.py
    /opt/conda/envs/wm_env/bin/python scripts/v8_calibration_labeler.py --from-cell cal-050
    /opt/conda/envs/wm_env/bin/python scripts/v8_calibration_labeler.py --stats
    /opt/conda/envs/wm_env/bin/python scripts/v8_calibration_labeler.py --help

Output:
    .omc/state/v8-calibration-labels.yaml  (append-only)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

CANDIDATES_DIR = (Path(__file__).resolve().parents[1] / ".omc/state/v8-calibration-candidates")
LABELS_PATH = (Path(__file__).resolve().parents[1] / ".omc/state/v8-calibration-labels.yaml")


def load_candidates() -> list[dict[str, Any]]:
    """JSON 메타 파일 전부 로드 (cell_id 정렬)"""
    metas: list[dict[str, Any]] = []
    for f in sorted(CANDIDATES_DIR.glob("cal-*.json")):
        try:
            metas.append(json.loads(f.read_text()))
        except Exception as exc:
            print(f"  ⚠️  {f.name} 읽기 실패: {exc}", file=sys.stderr)
    return metas


def load_labels() -> dict[str, dict[str, Any]]:
    """기존 레이블 로드 → {cell_id: entry}.

    파일은 두 스키마 중 하나로 존재할 수 있다:
      - 사람 레이블러(이 스크립트): top-level `labels:` 리스트의 {cell_id, label, ...}
      - LLM proxy 레이블러(v8_llm_calibration_labeler.py): top-level `samples:`
        리스트의 {sample_id, ground_truth, ...}
    두 스키마를 모두 인식해야 --stats 진행률과 중복-레이블 가드가 proxy 산출
    파일에 대해서도 올바르게 동작한다(과거 line-parser는 proxy 파일을 0건으로 오인).
    """
    if not LABELS_PATH.exists():
        return {}

    try:
        data = yaml.safe_load(LABELS_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"  ⚠️  레이블 파일 파싱 실패({LABELS_PATH.name}): {exc}", file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}

    labels: dict[str, dict[str, Any]] = {}
    for entry in data.get("labels") or []:
        if isinstance(entry, dict) and entry.get("cell_id"):
            labels[str(entry["cell_id"])] = entry
    for entry in data.get("samples") or []:
        if isinstance(entry, dict) and entry.get("sample_id"):
            cid = str(entry["sample_id"])
            labels.setdefault(cid, {"cell_id": cid, "label": entry.get("ground_truth")})

    return labels


def append_label(cell_id: str, label: str, user_reason: str) -> None:
    """레이블 항목을 사람 `labels:` 스키마로 추가 (append-only).

    파일이 LLM proxy 레이블러의 `samples:` 스키마로 작성되어 있으면, 사람 형식
    블록을 그 아래 그대로 append 하는 순간 top-level mapping에 list 블록이 섞여
    YAML이 깨지고 calibration SoT + consumer(v8_l2_l5_calibration_batch.py 등)가
    손상된다. 그 경우 corrupt 대신 명확한 에러로 중단한다.
    """
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if LABELS_PATH.exists():
        try:
            existing = yaml.safe_load(LABELS_PATH.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            existing = {}
        if isinstance(existing, dict) and "labels" not in existing and "samples" in existing:
            raise SystemExit(
                f"{LABELS_PATH} 는 v8_llm_calibration_labeler.py 의 'samples:' 스키마로 "
                "작성되어 있어 사람 레이블을 직접 append 하면 YAML이 손상됩니다. 먼저 "
                "'labels:' 스키마로 마이그레이션하거나 별도 출력 파일을 사용하세요."
            )
    else:
        LABELS_PATH.write_text(
            "# v8-calibration-labels.yaml\n"
            "# 사용자 레이블 (PASS/FAIL)\n"
            "labels:\n",
            encoding="utf-8",
        )

    safe_reason = user_reason.replace('"', "'")
    entry = (
        f"  - cell_id: {cell_id}\n"
        f"    label: {label}\n"
        f'    user_reason: "{safe_reason}"\n'
        f"    labeled_at: {now}\n"
    )
    with LABELS_PATH.open("a", encoding="utf-8") as fh:
        fh.write(entry)


def show_stats(candidates: list[dict[str, Any]], existing_labels: dict[str, dict[str, Any]]) -> None:
    """레이블링 진행률 출력"""
    total = len(candidates)
    done = len(existing_labels)
    pass_count = sum(1 for v in existing_labels.values() if v.get("label") == "PASS")
    fail_count = sum(1 for v in existing_labels.values() if v.get("label") == "FAIL")
    pct = 100 * done // total if total else 0

    expected_pass = sum(1 for c in candidates if c.get("expected_pass"))
    expected_fail = total - expected_pass

    print(f"\n{'='*60}")
    print(f"  📊 레이블링 진행률: {done}/{total} ({pct}%)")
    print(f"     PASS 레이블: {pass_count}개  |  FAIL 레이블: {fail_count}개")
    print(f"     미완료: {total - done}개")
    print(f"  ─")
    print(f"  후보 셀 구성: 기대 PASS {expected_pass}개 / 기대 FAIL {expected_fail}개")
    print(f"  레이블 파일: {LABELS_PATH}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="v8 LLM 비평가 보정 셀 레이블링 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""사용 예시:
  %(prog)s                       # 처음부터 레이블링
  %(prog)s --from-cell cal-050   # cal-050부터 재개
  %(prog)s --stats               # 진행률 확인 후 종료

레이블 명령어:
  P  — 통과 (PASS)
  F  — 불합격 (FAIL, 이유 입력 가능)
  S  — 이 셀 건너뜀
  Q  — 저장 후 종료
        """,
    )
    parser.add_argument(
        "--from-cell",
        type=str,
        default=None,
        metavar="CELL_ID",
        help="시작 cell_id (예: cal-050) — 그 이전 셀은 건너뜀",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="레이블링 진행률을 표시하고 종료",
    )
    args = parser.parse_args()

    candidates = load_candidates()
    existing_labels = load_labels()

    if not candidates:
        print(
            "⚠️  후보 셀이 없습니다.\n"
            "    먼저 v8_calibration_generator.py를 실행하세요.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.stats:
        show_stats(candidates, existing_labels)
        return

    # 레이블링 대상 필터링
    todo: list[dict[str, Any]] = []
    for m in candidates:
        if m["cell_id"] in existing_labels:
            continue  # 이미 레이블됨
        if args.from_cell and m["cell_id"] < args.from_cell:
            continue  # 시작 셀 이전
        todo.append(m)

    if not todo:
        print("✅ 모든 셀이 이미 레이블링되었습니다.")
        show_stats(candidates, existing_labels)
        return

    # ── 레이블링 루프 ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  v8 LLM 비평가 보정 셀 레이블링")
    print("=" * 60)
    print("  명령어:  P = 통과(PASS)  |  F = 불합격(FAIL)  |  S = 건너뜀  |  Q = 종료")
    print("=" * 60 + "\n")

    for idx, meta in enumerate(todo, 1):
        total_all = len(candidates)
        done_all = len(existing_labels)
        cell_id = meta["cell_id"]

        print(f"{'─'*60}")
        print(f"  셀 ID    : {cell_id}  [{idx}/{len(todo)}]  (전체: {done_all}/{total_all} 완료)")
        print(f"  경로     : {meta['route']}")
        print(f"  역할     : {meta['role']}")
        print(f"  상태     : {meta['content_state_guess']}")
        print(f"  기대값   : {'✅ PASS' if meta.get('expected_pass') else '❌ FAIL'}")
        if not meta.get("expected_pass") and meta.get("expected_reason"):
            print(f"  결함 이유: {meta['expected_reason']}")
        print(f"  스크린샷 : {meta['screenshot_path']}")
        if meta.get("visible_text_snippet"):
            snippet = meta["visible_text_snippet"][:200].replace("\n", " │ ")
            print(f"  가시 텍스트: {snippet}")
        print()

        while True:
            try:
                raw = input("  레이블 [P=통과 / F=불합격 / S=건너뜀 / Q=종료]: ")
                choice = raw.strip().upper()
            except (EOFError, KeyboardInterrupt):
                print("\n\n⏹  레이블링 중단됨. 진행 상황이 저장되었습니다.")
                sys.exit(0)

            if choice == "Q":
                print("\n⏹  레이블링 종료.")
                show_stats(candidates, load_labels())
                sys.exit(0)

            elif choice == "S":
                print("  ⏭  건너뜀.")
                break

            elif choice == "P":
                append_label(cell_id, "PASS", "")
                existing_labels[cell_id] = {"cell_id": cell_id, "label": "PASS"}
                print(f"  ✅ PASS 레이블 저장 완료: {cell_id}")
                break

            elif choice == "F":
                try:
                    reason = input("  실패 이유를 입력하세요 (생략 가능, Enter 건너뜀): ").strip()
                except (EOFError, KeyboardInterrupt):
                    reason = ""
                append_label(cell_id, "FAIL", reason)
                existing_labels[cell_id] = {"cell_id": cell_id, "label": "FAIL"}
                print(f"  ❌ FAIL 레이블 저장 완료: {cell_id}")
                break

            else:
                print("  ⚠️  올바른 명령어를 입력하세요: P, F, S, Q")

    # ── 완료 ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  레이블링 세션 완료!")
    show_stats(candidates, load_labels())


if __name__ == "__main__":
    main()
