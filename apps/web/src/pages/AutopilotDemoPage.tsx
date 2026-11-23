/**
 * AutopilotDemoPage — REG-03 T254
 *
 * 자율 시연 시나리오: 온보딩 → 적합성 → 4-gate → 추천 시뮬레이션 → NBA dispatch
 * → 사후관리 분기 통지의 6-step 1-click 데모. ≤30s SLO 측정 harness 포함.
 *
 * Stage 3+4+5 backend services (T235 readability, T200 pii_masking, T246
 * quarterly_report, T257 quarterly_notification, T258 four_eyes,
 * T245 drift_alarm, T269 ai_output_feedback) 를 PoC 프론트엔드에서
 * 시뮬레이션 단계로 호출. 실제 backend 연동은 Wave 6 caller-integration
 * wave 에서 진행한다.
 */

import { useState, useEffect } from "react";

interface DemoStep {
  id: string;
  label: string;
  description: string;
  serviceRef: string;
  estimatedMs: number;
}

const DEMO_STEPS: DemoStep[] = [
  {
    id: "step-1-customer-select",
    label: "1. 합성 고객 선택",
    description: "SYN-FAM-001 (김가족, HIGH 세그먼트) 자동 선택",
    serviceRef: "T256 seed_50_family_personas.sql",
    estimatedMs: 1500,
  },
  {
    id: "step-2-suitability",
    label: "2. 적합성 자동 평가",
    description: "위험 등급 5 + 자산 85억 → MODERATE_AGGRESSIVE 적합 판정",
    serviceRef: "T221 suitability_update_notice.classify",
    estimatedMs: 2500,
  },
  {
    id: "step-3-four-gate",
    label: "3. 4-gate 자동 통과",
    description: "적합성·설명·부당권유·광고 4개 게이트 PASS, 4-eyes drafted",
    serviceRef: "T258 four_eyes.request_approval → first → second",
    estimatedMs: 4000,
  },
  {
    id: "step-4-recommendation",
    label: "4. AI 추천 시뮬레이션",
    description: "GPT5/mini briefing + readability (≥60) + reasoning-lint clean",
    serviceRef: "T235 readability.evaluate_ai_output + T205 reasoning_lint",
    estimatedMs: 8000,
  },
  {
    id: "step-5-nba-dispatch",
    label: "5. NBA 인박스 dispatch",
    description: "분기 리포트 초안 NBA 카드 P2 우선순위로 dispatch",
    serviceRef: "T246 quarterly_report.compose_draft",
    estimatedMs: 3000,
  },
  {
    id: "step-6-aftercare-notice",
    label: "6. 사후관리 분기 통지 시뮬",
    description: "이메일 초안 → PII mask (외부) → 4-gate → 4-eyes → SENT_SIMULATION",
    serviceRef: "T257 quarterly_notification (T200/T205/T221/T235/T258 통합)",
    estimatedMs: 5500,
  },
];

const SLO_BUDGET_MS = 30_000;
const TOTAL_ESTIMATED_MS = DEMO_STEPS.reduce((s, x) => s + x.estimatedMs, 0);

type StepState = "pending" | "running" | "completed" | "failed";

export function AutopilotDemoPage() {
  const [stepStates, setStepStates] = useState<Record<string, StepState>>(
    Object.fromEntries(DEMO_STEPS.map((s) => [s.id, "pending"])),
  );
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [completedAt, setCompletedAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  useEffect(() => {
    if (!running || startedAt === null) return;
    const id = window.setInterval(() => {
      setElapsedMs(Date.now() - startedAt);
    }, 100);
    return () => window.clearInterval(id);
  }, [running, startedAt]);

  const start = async () => {
    if (running) return;
    setRunning(true);
    setCompletedAt(null);
    setElapsedMs(0);
    const now = Date.now();
    setStartedAt(now);
    setStepStates(Object.fromEntries(DEMO_STEPS.map((s) => [s.id, "pending"])));

    for (const step of DEMO_STEPS) {
      setStepStates((prev) => ({ ...prev, [step.id]: "running" }));
      await new Promise((resolve) => setTimeout(resolve, step.estimatedMs));
      setStepStates((prev) => ({ ...prev, [step.id]: "completed" }));
    }

    setCompletedAt(Date.now());
    setRunning(false);
  };

  const reset = () => {
    if (running) return;
    setStepStates(Object.fromEntries(DEMO_STEPS.map((s) => [s.id, "pending"])));
    setStartedAt(null);
    setCompletedAt(null);
    setElapsedMs(0);
  };

  const finalDurationMs = completedAt && startedAt ? completedAt - startedAt : elapsedMs;
  const sloMet = completedAt !== null && finalDurationMs <= SLO_BUDGET_MS;
  const sloProgressPct = Math.min(100, (finalDurationMs / SLO_BUDGET_MS) * 100);

  return (
    <div className="grid gap-6">
      <section className="rounded-3xl bg-gradient-to-r from-indigo-700 to-purple-800 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-indigo-200">Autopilot 데모</p>
        <h1 className="mt-3 text-3xl font-black">자율 시연 · 1-click 시나리오</h1>
        <p className="mt-2 text-indigo-100 text-sm">
          온보딩 → 적합성 → 4-gate → 추천 → NBA → 사후관리 (≤{Math.floor(SLO_BUDGET_MS / 1000)}초 SLO)
        </p>
        <div className="mt-3 inline-block rounded-full bg-yellow-400 px-3 py-1 text-xs font-bold text-yellow-900">
          시뮬레이션 · 실제 주문 아님
        </div>
      </section>

      <section
        aria-label="자율 시연 컨트롤"
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">시나리오 컨트롤</h2>
            <p className="mt-1 text-xs text-slate-500">
              예상 소요 {Math.floor(TOTAL_ESTIMATED_MS / 1000)}초 / SLO {Math.floor(SLO_BUDGET_MS / 1000)}초
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={start}
              disabled={running}
              aria-label="자율 시연 시작"
              className="rounded-xl bg-indigo-700 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-300 disabled:text-slate-500"
            >
              {running ? "실행 중…" : "▶ 시연 시작"}
            </button>
            <button
              type="button"
              onClick={reset}
              disabled={running}
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 disabled:opacity-50"
            >
              초기화
            </button>
          </div>
        </div>

        {(running || completedAt) && (
          <div className="mt-4">
            <div
              role="progressbar"
              aria-label="SLO 진행률"
              aria-valuenow={Math.floor(sloProgressPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
            >
              <div
                className={`h-full transition-all ${
                  sloProgressPct > 100 ? "bg-red-600" : sloProgressPct > 80 ? "bg-amber-500" : "bg-emerald-500"
                }`}
                style={{ width: `${sloProgressPct}%` }}
              />
            </div>
            <p className="mt-2 text-xs font-mono text-slate-600 tabular-nums">
              {(finalDurationMs / 1000).toFixed(1)}s / {Math.floor(SLO_BUDGET_MS / 1000)}s
              {completedAt && (
                <span className={`ml-3 font-bold ${sloMet ? "text-emerald-700" : "text-red-700"}`}>
                  {sloMet ? "✓ SLO 충족" : "✗ SLO 초과"}
                </span>
              )}
            </p>
          </div>
        )}
      </section>

      <section
        aria-label="자율 시연 단계 목록"
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <h2 className="mb-4 text-base font-semibold text-slate-900">시나리오 단계</h2>
        <ol className="grid gap-3">
          {DEMO_STEPS.map((step) => {
            const state = stepStates[step.id] ?? "pending";
            const stateLabel = {
              pending: "대기",
              running: "진행 중",
              completed: "완료",
              failed: "실패",
            }[state];
            const stateCls = {
              pending: "border-slate-200 bg-slate-50 text-slate-500",
              running: "border-indigo-300 bg-indigo-50 text-indigo-800 animate-pulse",
              completed: "border-emerald-300 bg-emerald-50 text-emerald-800",
              failed: "border-red-300 bg-red-50 text-red-800",
            }[state];
            return (
              <li
                key={step.id}
                aria-label={`${step.label} — ${stateLabel}`}
                className={`rounded-xl border p-4 ${stateCls}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold">{step.label}</p>
                    <p className="mt-0.5 text-xs">{step.description}</p>
                  </div>
                  <span className="shrink-0 rounded-full border border-slate-300 bg-white px-2.5 py-0.5 text-xs font-bold">
                    {stateLabel}
                  </span>
                </div>
                <p className="mt-2 font-mono text-xs text-slate-400">{step.serviceRef}</p>
              </li>
            );
          })}
        </ol>
      </section>

      {completedAt && (
        <section
          aria-label="자율 시연 결과 요약"
          className={`rounded-2xl border p-5 shadow-sm ${
            sloMet ? "border-emerald-300 bg-emerald-50" : "border-red-300 bg-red-50"
          }`}
        >
          <h2 className="text-base font-semibold text-slate-900">시연 결과 요약</h2>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs font-bold text-slate-500">총 소요</dt>
              <dd className="font-mono tabular-nums">{(finalDurationMs / 1000).toFixed(1)}초</dd>
            </div>
            <div>
              <dt className="text-xs font-bold text-slate-500">SLO 충족</dt>
              <dd className={`font-bold ${sloMet ? "text-emerald-700" : "text-red-700"}`}>
                {sloMet ? `✓ ≤${Math.floor(SLO_BUDGET_MS / 1000)}초` : `✗ >${Math.floor(SLO_BUDGET_MS / 1000)}초`}
              </dd>
            </div>
            <div>
              <dt className="text-xs font-bold text-slate-500">완료 단계</dt>
              <dd>{Object.values(stepStates).filter((s) => s === "completed").length} / {DEMO_STEPS.length}</dd>
            </div>
            <div>
              <dt className="text-xs font-bold text-slate-500">audit_action_code</dt>
              <dd className="font-mono text-xs">autopilot_demo_simulation_completed</dd>
            </div>
          </dl>
        </section>
      )}
    </div>
  );
}
