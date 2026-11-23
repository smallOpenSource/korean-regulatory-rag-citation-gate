/**
 * PoCAutoApprovalBadge — REG-06
 *
 * Renders when system_flags.demo_mode.enabled = true.
 * Displays a sticky yellow banner on consultation pages.
 * Click opens ADR-004 reference info.
 */

import { useState } from "react";

interface Props {
  /** When false the badge is completely invisible (production guard). */
  enabled: boolean;
}

export function PoCAutoApprovalBadge({ enabled }: Props) {
  const [open, setOpen] = useState(false);

  if (!enabled) return null;

  return (
    <>
      <div
        role="banner"
        aria-label="PoC 자동 승인 모드 활성화 경고"
        className="sticky top-0 z-50 flex w-full items-center justify-between gap-3 border-b border-yellow-400 bg-yellow-300 px-4 py-2.5 text-yellow-950 shadow-sm"
      >
        <div className="flex items-center gap-2.5 text-sm font-semibold">
          <span aria-hidden="true" className="text-base">🟡</span>
          <span>PoC AUTO APPROVAL MODE — 프로덕션에서는 차단됩니다</span>
        </div>
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={open}
          className="shrink-0 rounded-lg border border-yellow-600 bg-yellow-200 px-3 py-1 text-xs font-bold text-yellow-900 hover:bg-yellow-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-yellow-700"
        >
          ADR-004 참조
        </button>
      </div>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="ADR-004 PoC 자동 승인 증명"
          className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/60 p-4"
        >
          <div className="w-full max-w-lg rounded-2xl border border-yellow-300 bg-white p-6 shadow-xl">
            <div className="mb-4 flex items-start justify-between gap-3">
              <h2 className="text-lg font-black text-slate-950">ADR-004: PoC 자동 승인 증명</h2>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="닫기"
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
              >
                ✕
              </button>
            </div>
            <div className="grid gap-3 text-sm text-slate-700">
              <p>
                <strong className="text-slate-900">governance_marker = PoC_AUTO_APPROVAL</strong>가
                설정된 상태입니다. 이 모드에서는 인간 검토자 필드가 시뮬레이션 목적으로 면제됩니다.
              </p>
              <div className="rounded-xl bg-yellow-50 p-3 text-xs font-medium text-yellow-900 border border-yellow-200">
                ⚠️ 프로덕션 빌드에서는 이 핸들러가 dead-code-eliminated 됩니다.
                ADR-004 §3 "프로덕션 게이트" 참조.
              </div>
              <ul className="grid gap-1.5 text-xs text-slate-600">
                <li>• 모든 PoC_AUTO_APPROVAL 행은 감사 로그에 기록됩니다</li>
                <li>• generate_sod_evidence_pack.py의 Bucket A에 계산됩니다</li>
                <li>• 규정 준수 검토자가 분기별로 검토합니다</li>
              </ul>
              <p className="text-xs text-slate-400 border-t border-slate-100 pt-2 mt-1">
                REF: ADR-004, REG-06, scripts/generate_sod_evidence_pack.py
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
