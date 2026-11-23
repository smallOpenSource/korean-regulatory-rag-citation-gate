/**
 * DisputeCasePage — T251
 *
 * Customer-by-customer dispute list.
 * 30-day timer countdown per case.
 * Status pipeline: OPEN → RESPONDED → RESOLVED.
 * ADMIN can seed a synthetic dispute case.
 */

import { useEffect, useState } from "react";

// Wave-Audit-Defect-Fix D-S4: timestamps go through the canonical
// formatBankerTimestamp helper (page-level-consistency-grep).
import { formatBankerTimestamp } from "../lib/format";

// Wave-Audit-Defect-Fix C8: role-aware UI — AUDIT_VIEWER reads only, write
// buttons (advance / seed) hidden for non-mutating roles. Mirrors the C7
// backend role gate at routers/disputes.py.
import { useAuthStore } from "../store/auth";

// T3-3 (F15): DB SoT V028:11 CHECK (status IN ('OPEN','RESPONDED','RESOLVED','EXPIRED')).
// EXPIRED는 response_due_at 경과 후 DB가 emit하는 lifecycle 상태이므로 frontend
// type/label/style이 누락되면 raw enum이 노출되어 PB perspective 위반.
type DisputeStatus = "OPEN" | "RESPONDED" | "RESOLVED" | "EXPIRED";

interface DisputeCase {
  id: string;
  customer_id: string;
  customer_name: string;
  subject: string;
  status: DisputeStatus;
  opened_at: string;
  responded_at?: string;
  resolved_at?: string;
}

const SEED_CASES: DisputeCase[] = [
  {
    id: "DPC-001",
    customer_id: "CUST-SYNTH-001",
    customer_name: "합성고객 김○○",
    subject: "투자상품 설명의무 위반 이의",
    status: "OPEN",
    opened_at: "2026-04-25T09:12:00",
  },
  {
    id: "DPC-002",
    customer_id: "CUST-SYNTH-002",
    customer_name: "합성고객 이○○",
    subject: "RAG 문서 자료열람 요구 지연",
    status: "RESPONDED",
    opened_at: "2026-04-20T14:30:00",
    responded_at: "2026-04-28T11:00:00",
  },
  {
    id: "DPC-003",
    customer_id: "CUST-SYNTH-003",
    customer_name: "합성고객 박○○",
    subject: "적합성 평가 오류 이의신청",
    status: "RESOLVED",
    opened_at: "2026-04-10T10:00:00",
    responded_at: "2026-04-14T09:00:00",
    resolved_at: "2026-04-19T16:00:00",
  },
];

const STATUS_LABEL: Record<DisputeStatus, string> = {
  OPEN: "접수",
  RESPONDED: "답변 완료",
  RESOLVED: "해결",
  EXPIRED: "기한 만료",
};

const STATUS_STYLE: Record<DisputeStatus, string> = {
  OPEN: "border-red-200 bg-red-50 text-red-700",
  RESPONDED: "border-amber-200 bg-amber-50 text-amber-700",
  RESOLVED: "border-emerald-200 bg-emerald-50 text-emerald-700",
  EXPIRED: "border-rose-300 bg-rose-100 text-rose-800",
};

const PIPELINE: DisputeStatus[] = ["OPEN", "RESPONDED", "RESOLVED"];

function daysRemaining(openedAt: string): number {
  const opened = new Date(openedAt).getTime();
  const deadline = opened + 30 * 24 * 60 * 60 * 1000;
  const remaining = Math.ceil((deadline - Date.now()) / (24 * 60 * 60 * 1000));
  return remaining;
}

function TimerBadge({ openedAt, status }: { openedAt: string; status: DisputeStatus }) {
  if (status === "RESOLVED") {
    return <span className="text-xs text-slate-400">해결됨</span>;
  }
  const days = daysRemaining(openedAt);
  if (days < 0) {
    return (
      <span className="rounded-full border border-red-300 bg-red-100 px-2 py-0.5 text-xs font-bold text-red-800">
        기한 초과 {Math.abs(days)}일
      </span>
    );
  }
  const urgentClass = days <= 5 ? "border-red-300 bg-red-100 text-red-800" : days <= 10 ? "border-amber-300 bg-amber-100 text-amber-800" : "border-slate-300 bg-slate-100 text-slate-700";
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs font-bold ${urgentClass}`} aria-label={`마감까지 ${days}일 남음`}>
      D-{days}
    </span>
  );
}

function StatusPipeline({ current }: { current: DisputeStatus }) {
  return (
    <div className="flex items-center gap-1" role="progressbar" aria-label={`처리 단계: ${STATUS_LABEL[current]}`} aria-valuenow={PIPELINE.indexOf(current) + 1} aria-valuemin={1} aria-valuemax={3}>
      {PIPELINE.map((step, idx) => {
        const done = PIPELINE.indexOf(current) >= idx;
        return (
          <div key={step} className="flex items-center gap-1">
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-semibold ${done ? "bg-blue-700 text-white" : "bg-slate-200 text-slate-500"}`}
            >
              {STATUS_LABEL[step]}
            </span>
            {idx < PIPELINE.length - 1 && (
              <span className={`text-xs ${done && PIPELINE.indexOf(current) > idx ? "text-blue-400" : "text-slate-300"}`} aria-hidden="true">→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function DisputeCasePage() {
  const [cases, setCases] = useState<DisputeCase[]>(SEED_CASES);
  // Wave-Audit-Defect-Fix C8: derive role from the auth store; was hardcoded
  // false placeholder so the seed button never appeared even for ADMIN.
  const user = useAuthStore((s) => s.user);
  const roleCode = user?.roleCode ?? "";
  const isAdmin = roleCode === "ADMIN";
  const canMutate = roleCode === "PB" || roleCode === "WM" || roleCode === "ADMIN";
  const [now, setNow] = useState(Date.now());

  // Tick timer every minute
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  // Suppress unused variable lint warning
  void now;

  function advanceStatus(id: string) {
    setCases((prev) =>
      prev.map((c) => {
        if (c.id !== id) return c;
        const nextIdx = PIPELINE.indexOf(c.status) + 1;
        if (nextIdx >= PIPELINE.length) return c;
        const next = PIPELINE[nextIdx];
        return {
          ...c,
          status: next,
          responded_at: next === "RESPONDED" ? new Date().toISOString() : c.responded_at,
          resolved_at: next === "RESOLVED" ? new Date().toISOString() : c.resolved_at,
        };
      }),
    );
  }

  function seedSyntheticCase() {
    const newCase: DisputeCase = {
      id: `DPC-${String(cases.length + 1).padStart(3, "0")}`,
      customer_id: `CUST-SYNTH-${String(cases.length + 1).padStart(3, "0")}`,
      customer_name: `합성고객 합○○`,
      subject: "합성 분쟁 사례 (관리자 생성)",
      status: "OPEN",
      opened_at: new Date().toISOString(),
    };
    setCases((prev) => [newCase, ...prev]);
  }

  return (
    <div className="grid gap-6">
      {/* Header */}
      <section className="rounded-3xl bg-gradient-to-r from-orange-700 to-red-900 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-orange-200">거버넌스 · 분쟁</p>
        <h1 className="mt-3 text-3xl font-black">분쟁 조정 관리</h1>
        <p className="mt-2 text-orange-100 text-sm">
          고객별 분쟁 현황 · 30일 처리 기한 추적 · 상태 파이프라인
        </p>
      </section>

      {/* Admin seeding */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div>
          <p className="text-sm font-semibold text-slate-900">전체 {cases.length}건</p>
          <p className="text-xs text-slate-500">
            접수 {cases.filter((c) => c.status === "OPEN").length} · 답변완료 {cases.filter((c) => c.status === "RESPONDED").length} · 해결 {cases.filter((c) => c.status === "RESOLVED").length}
          </p>
        </div>
        {isAdmin && (
          <button
            type="button"
            onClick={seedSyntheticCase}
            className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-semibold text-amber-800 hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-700"
            aria-label="합성 분쟁 사례 시드 생성 (관리자 전용)"
          >
            🔧 합성 사례 생성 (ADMIN)
          </button>
        )}
      </div>

      {/* Case list */}
      <div
        className="grid gap-4"
        role="list"
        aria-label="분쟁 사례 목록"
      >
        {cases.map((c) => (
          <article
            key={c.id}
            role="listitem"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            aria-label={`분쟁 사례 ${c.id}: ${c.subject}`}
          >
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-600">{c.id}</code>
                  <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${STATUS_STYLE[c.status]}`}>
                    {STATUS_LABEL[c.status]}
                  </span>
                  <TimerBadge openedAt={c.opened_at} status={c.status} />
                </div>
                <h2 className="mt-1.5 text-base font-bold text-slate-950">{c.subject}</h2>
                <p className="text-xs text-slate-500">{c.customer_name} · {c.customer_id}</p>
              </div>
              {c.status !== "RESOLVED" && canMutate && (
                <button
                  type="button"
                  onClick={() => advanceStatus(c.id)}
                  aria-label={`${c.id} 상태 다음 단계로 진행`}
                  className="shrink-0 rounded-xl border border-blue-300 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-800 hover:bg-blue-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
                >
                  {c.status === "OPEN" ? "답변 처리" : "해결 처리"}
                </button>
              )}
            </div>

            <StatusPipeline current={c.status} />

            <div className="mt-3 grid gap-1 text-xs text-slate-500">
              <span>접수: {formatBankerTimestamp(c.opened_at)}</span>
              {c.responded_at && <span>답변: {formatBankerTimestamp(c.responded_at)}</span>}
              {c.resolved_at && <span>해결: {formatBankerTimestamp(c.resolved_at)}</span>}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
