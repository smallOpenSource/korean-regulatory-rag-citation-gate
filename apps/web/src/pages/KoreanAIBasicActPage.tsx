/**
 * KoreanAIBasicActPage — 인공지능기본법 대응 체크리스트
 *
 * PB/WM 직원에게 보이는 카피는 한국어 평어체로 작성합니다.
 * 내부 식별자(ADR-/REG-/AI-/RUN-) 및 evidence path는 ADMIN/AUDIT_VIEWER 전용
 * DevReference 컴포넌트로만 노출합니다.
 */
import { DevReference } from "../components/DevReference";

interface AiActControl {
  id: string;
  function: "GOVERN" | "MAP" | "MEASURE" | "MANAGE";
  nistId: string;
  summary: string;
  harnessImplementation: string;
  evidencePath: string;
  status: "COMPLIANT" | "PARTIAL" | "PLANNED";
}

const CONTROLS: AiActControl[] = [
  {
    id: "KAI-01",
    function: "GOVERN",
    nistId: "GV-1.1",
    summary: "신뢰할 수 있는 AI를 위한 정책 수립 및 문서화",
    harnessImplementation:
      "AI 거버넌스 문서와 아키텍처 계약 7건, 금융 AI 7대 원칙 자체평가 보고서를 함께 유지합니다.",
    evidencePath: "docs/regulations/REG-04_ai_governance.md",
    status: "COMPLIANT",
  },
  {
    id: "KAI-02",
    function: "GOVERN",
    nistId: "GV-1.2",
    summary: "AI 위험에 대한 책임 구조 정의",
    harnessImplementation:
      "각 AI 에이전트는 시작·성공·실패 단계별 감사 로그를 남기고, 인간 검토자 필드를 보존합니다.",
    evidencePath: "apps/api/harness/core/audit.py",
    status: "COMPLIANT",
  },
  {
    id: "KAI-03",
    function: "MAP",
    nistId: "MP-2.1",
    summary: "AI 위험에 대한 과학적·기술적 지식 정렬",
    harnessImplementation:
      "OWASP LLM Top 10 2025 항목별 통제를 에이전트마다 매핑하고, 이중 격리 아키텍처로 프롬프트 주입 위험을 완화합니다.",
    evidencePath: "docs/architecture/ADR-005_dual_llm_quarantine.md",
    status: "COMPLIANT",
  },
  {
    id: "KAI-04",
    function: "MEASURE",
    nistId: "MS-2.1",
    summary: "배포 전 AI 시스템 테스트",
    harnessImplementation:
      "단위·통합·골든 스냅샷·적대적 시나리오 테스트를 모두 자동 실행하여 회귀를 차단합니다.",
    evidencePath: "tests/test_rag_adversarial.py, tests/test_seven_agents_golden.py",
    status: "COMPLIANT",
  },
  {
    id: "KAI-05",
    function: "MEASURE",
    nistId: "MS-2.5",
    summary: "AI 시스템 적대적 견고성 테스트",
    harnessImplementation:
      "프롬프트 주입·시스템 지시문 추출·격리 청크 추출 등 적대적 시나리오를 RAG 파이프라인에 반복 적용합니다.",
    evidencePath: "tests/test_rag_adversarial.py",
    status: "COMPLIANT",
  },
  {
    id: "KAI-06",
    function: "MANAGE",
    nistId: "MG-2.4",
    summary: "인간 감독 메커니즘 구현",
    harnessImplementation:
      "이메일 초안·컴플라이언스 검사·상담 브리핑 모두 직원 승인 게이트를 거친 뒤에만 사용·발송됩니다.",
    evidencePath: "docs/architecture/ADR-002_email_authority_and_schema_contract.md",
    status: "COMPLIANT",
  },
  {
    id: "KAI-07",
    function: "MANAGE",
    nistId: "MG-4.1",
    summary: "AI 위험 관리 잔여 위험 문서화",
    harnessImplementation:
      "PoC 전용 자동 승인 모드는 거버넌스 마커로 선언되며, 프로덕션 빌드에서 핸들러가 제거됩니다.",
    evidencePath: "docs/architecture/ADR-004_poc_auto_approval_attestation.md",
    status: "PARTIAL",
  },
];

const FUNCTION_STYLE: Record<AiActControl["function"], string> = {
  GOVERN: "border-blue-200 bg-blue-50 text-blue-800",
  MAP: "border-indigo-200 bg-indigo-50 text-indigo-800",
  MEASURE: "border-emerald-200 bg-emerald-50 text-emerald-800",
  MANAGE: "border-orange-200 bg-orange-50 text-orange-800",
};

const FUNCTION_LABEL: Record<AiActControl["function"], string> = {
  GOVERN: "거버넌스",
  MAP: "매핑",
  MEASURE: "측정",
  MANAGE: "관리",
};

const STATUS_STYLE: Record<AiActControl["status"], string> = {
  COMPLIANT: "border-emerald-300 bg-emerald-100 text-emerald-800",
  PARTIAL: "border-amber-300 bg-amber-100 text-amber-800",
  PLANNED: "border-slate-300 bg-slate-100 text-slate-700",
};

const STATUS_LABEL: Record<AiActControl["status"], string> = {
  COMPLIANT: "✅ 이행 완료",
  PARTIAL: "⚠️ 일부 이행",
  PLANNED: "📋 계획 중",
};

export function KoreanAIBasicActPage() {
  const compliantCount = CONTROLS.filter((c) => c.status === "COMPLIANT").length;
  const partialCount = CONTROLS.filter((c) => c.status === "PARTIAL").length;

  return (
    <div className="grid gap-6">
      {/* Header */}
      <section className="rounded-3xl bg-gradient-to-r from-slate-900 to-blue-950 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-blue-300">
          AI 거버넌스
          <DevReference inline="REG-04 · AI-06" />
        </p>
        <h1 className="mt-3 text-3xl font-black">인공지능기본법 대응 체크리스트</h1>
        <p className="mt-2 text-slate-200 text-sm">
          2026년 1월 시행 · 위험 기반 거버넌스 매핑 · Harness 통제 근거
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <div className="rounded-xl bg-white/10 px-4 py-2 text-center">
            <p className="text-2xl font-black">{compliantCount}</p>
            <p className="text-xs text-emerald-300">이행 완료</p>
          </div>
          <div className="rounded-xl bg-white/10 px-4 py-2 text-center">
            <p className="text-2xl font-black">{partialCount}</p>
            <p className="text-xs text-amber-300">일부 이행</p>
          </div>
          <div className="rounded-xl bg-white/10 px-4 py-2 text-center">
            <p className="text-2xl font-black">{CONTROLS.length}</p>
            <p className="text-xs text-slate-300">총 통제 항목</p>
          </div>
        </div>
      </section>

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <strong className="font-bold">합성 데이터</strong> · 본 체크리스트는 합성 데이터 기반 시뮬레이션 환경의 통제 적용 현황을 요약합니다.
      </div>

      {/* Law Context */}
      <section
        className="rounded-2xl border border-blue-200 bg-blue-50 p-5 shadow-sm"
        aria-label="인공지능기본법 개요"
      >
        <h2 className="text-base font-black text-blue-950 mb-2">인공지능기본법 (2026년 1월 시행)</h2>
        <div className="grid gap-2 text-sm text-blue-900">
          <p>
            대한민국 인공지능기본법은 AI 시스템의 개발·운영·이용에 관한 기본 원칙을 규정합니다.
            금융 AI 시스템에는 다음 의무가 적용됩니다:
          </p>
          <ul className="grid gap-1.5 text-xs text-blue-800 ml-3">
            <li>• 고위험 AI 시스템 사전 등록·신고 (제15조)</li>
            <li>• 인간 감독 메커니즘 구현 의무 (제17조)</li>
            <li>• AI 이용 사실 고지 의무 (제18조) · UI 'AI 생성' 배지로 이행</li>
            <li>• 투명성·설명가능성 확보 의무 (제19조)</li>
            <li>• 위험 기반 AI 거버넌스 체계 수립 (제20조)</li>
          </ul>
          <p className="text-xs text-blue-700 mt-1">
            Harness PoC는 "내부 직원용·합성 데이터 기반·결정 지원" 범주에 해당하며 고위험 AI 범주에서 제외됩니다.
            <DevReference inline="REG-04 §2" />
          </p>
        </div>
      </section>

      {/* Controls */}
      <div
        className="grid gap-4"
        role="list"
        aria-label="인공지능기본법 통제 체크리스트"
      >
        {CONTROLS.map((control) => (
          <article
            key={control.id}
            role="listitem"
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            aria-label={`통제 ${control.id}: ${control.summary}`}
          >
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <code className="rounded bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-700">
                  {control.id}
                </code>
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${FUNCTION_STYLE[control.function]}`}
                >
                  {FUNCTION_LABEL[control.function]}
                </span>
                <DevReference inline={control.nistId} />
              </div>
              <span
                className={`shrink-0 rounded-full border px-3 py-0.5 text-xs font-bold ${STATUS_STYLE[control.status]}`}
                aria-label={`이행 상태: ${STATUS_LABEL[control.status]}`}
              >
                {STATUS_LABEL[control.status]}
              </span>
            </div>

            <h2 className="text-base font-bold text-slate-950 mb-3">{control.summary}</h2>

            <div className="grid gap-2">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-slate-500 mb-1">
                  Harness 구현
                </p>
                <p className="text-sm text-slate-800">{control.harnessImplementation}</p>
              </div>
              <DevReference
                className="block"
                inline={`근거 경로 · ${control.evidencePath}`}
              />
            </div>
          </article>
        ))}
      </div>

      {/* Footer — internal references, admin/audit only */}
      <DevReference
        className="block rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-600"
        inline="참고 문서 · AI-06 NIST AI RMF / GAI Profile Mapping · NIST AI 600-1 (2024-07) · NIST AI RMF 1.0 (2023-01) · REG-04 AI Governance · ADR-001~007 아키텍처 계약"
      />
    </div>
  );
}
