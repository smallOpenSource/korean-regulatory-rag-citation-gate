/**
 * AIPolicyPage — AI 사용 정책 (직원 교육 초점)
 *
 * PB/WM 직원에게 보이는 카피는 한국어 평어체로 작성합니다.
 * 내부 식별자(ADR-, REG-, AI-, RUN-, 와 §- 참조)는 페이지 하단 footer에
 * DevReference 컴포넌트로만 모아서 ADMIN/AUDIT_VIEWER 역할에만 노출합니다.
 */
import { DevReference } from "../components/DevReference";

interface PolicySection {
  id: string;
  title: string;
  subtitle?: string;
  content: string;
  items?: string[];
  highlight?: string;
  badge?: string;
  badgeStyle?: string;
}

const POLICY_SECTIONS: PolicySection[] = [
  {
    id: "intro",
    title: "AI 사용 정책 개요",
    subtitle: "직원 교육용 · 내부 배포 전용",
    content:
      "이 문서는 Harness PB/WM AI 업무지원 시스템을 사용하는 모든 직원을 위한 AI 사용 정책입니다. AI는 의사결정 보조 도구이며, 최종 책임은 항상 담당 직원에게 있습니다.",
    highlight: "AI는 '결정 지원' 도구입니다. AI가 결정하지 않습니다.",
    badge: "필수 교육",
    badgeStyle: "border-blue-300 bg-blue-100 text-blue-800",
  },
  {
    id: "wave3-hardening",
    title: "AI 이중 격리 적용 (2026-05-17 시행)",
    subtitle: "신뢰하지 않는 외부 텍스트는 시스템 지시문과 분리해 처리합니다.",
    content:
      "2026년 5월 17일부터 다음 세 가지 AI 에이전트가 이중 격리 아키텍처로 강화되었습니다:",
    items: [
      "RAG 질의응답: 검색된 공급자 텍스트를 격리 레인에서만 처리",
      "이메일 초안: 업로드 메모·인라인 컨텍스트를 격리 레인에서만 처리",
      "상담 브리핑: 고객 메모·자유형식 노트를 격리 레인에서만 처리",
    ],
    highlight:
      "위 세 에이전트는 신뢰하지 않는 외부 텍스트를 시스템 프롬프트와 혼합하지 않습니다.",
  },
  {
    id: "dual-llm-contract",
    title: "이중 LLM 계약",
    subtitle: "특권 레인과 격리 레인의 분리",
    content:
      "이중 LLM 아키텍처는 두 개의 분리된 AI 호출로 구성됩니다. 외부 텍스트는 도구 접근 권한이 없는 격리 레인에서만 처리합니다:",
    items: [
      "특권 레인: 구조화된 입력과 도구 접근 권한이 있는 AI 호출. 데이터베이스 검증을 통과한 데이터만 포함합니다.",
      "격리 레인: 외부에서 입력된 텍스트(고객 메모, 공급자 자료 등)는 도구 접근 권한 없이 분리된 AI 호출로 처리합니다.",
      "검색 결과는 식별 태그로 감싸 특권 레인에 전달되며, 격리 레인의 출력은 정해진 스키마로만 받습니다.",
      "두 호출 모두 에이전트별 토큰 예산에 함께 계산됩니다.",
    ],
    highlight: "두 호출 모두 에이전트별 토큰 예산에 계산됩니다.",
  },
  {
    id: "azure-content-safety",
    title: "외부 콘텐츠 안전 검사",
    subtitle: "프롬프트 공격 자동 차단 (선택 활성화)",
    content:
      "Azure의 프롬프트 보호 훅을 선택적으로 활성화할 수 있습니다. PoC 환경에서는 기본 비활성화이며, 프로덕션에서는 활성화를 권장합니다.",
    items: [
      "사용자 프롬프트 공격 및 문서 공격 검사를 전체 질문과 검색 컨텍스트에 실행",
      "공격으로 판단되면 즉시 차단되고 감사 로그에 사유가 기록됩니다",
      "환경 변수로 활성·비활성을 제어합니다 (사전 승인 의존성 등록 완료)",
    ],
    badge: "PoC: 비활성 / 프로덕션: 활성 권장",
    badgeStyle: "border-amber-300 bg-amber-100 text-amber-800",
  },
  {
    id: "llm-prompt-leak",
    title: "시스템 프롬프트 누출 방지",
    subtitle: "AI 응답에 시스템 지시문이 포함되지 않도록 검사합니다.",
    content:
      "생성 후 자동 새니타이저가 모델 응답에서 시스템 프롬프트 에코를 검사합니다:",
    items: [
      "토큰 일치율이 임계값 이상이면 자동으로 가려서 보여주고 감사 로그를 남깁니다.",
      "응답에 시스템 지시문 표식이 나타나면 안전을 위해 응답을 자동으로 차단합니다.",
      "위 두 검사는 이중 격리 적용 에이전트(질의응답·이메일 초안·상담 브리핑) 모두에 동일하게 적용됩니다.",
    ],
    highlight: "AI 응답에 시스템 프롬프트 내용이 포함될 경우 자동으로 차단·가림 처리됩니다.",
  },
  {
    id: "token-budget",
    title: "AI 토큰 소비 관리",
    subtitle: "월별·직원별 사용량을 추적합니다.",
    content:
      "무제한 AI 소비를 방지하기 위해 토큰 예산 관리 체계가 적용됩니다:",
    items: [
      "월별 누적 한도가 설정되어 있으며, 한도 초과 시 새 요청이 차단됩니다.",
      "직원별·세션별 AI 호출 한도가 적용됩니다.",
      "이중 격리 에이전트는 두 번의 호출 모두 예산에 합산됩니다.",
      "하우스뷰 생성용 대형 모델은 별도 비용 항목으로 추적됩니다.",
      "비동기 작업(포트폴리오 분석, 하우스뷰)은 작업 러너 단위에서 한도가 적용됩니다.",
    ],
    highlight: "토큰 소비 원장은 관리자 AI 운영현황 대시보드에서 실시간 확인할 수 있습니다.",
  },
  {
    id: "employee-responsibility",
    title: "직원 책임 원칙",
    subtitle: "AI 보조수단성의 원칙",
    content:
      "Harness AI는 의사결정 보조 도구입니다. 다음 원칙을 반드시 준수해야 합니다:",
    items: [
      "AI 출력물은 결정을 지원하지, 대신하지 않습니다.",
      "AI 생성 문서(이메일 초안, 상담 브리핑 등)는 반드시 직원이 검토 후 사용합니다.",
      "고객에게 AI 출력물을 검토 없이 직접 전달하지 않습니다.",
      "모든 AI 생성 콘텐츠에는 'AI 생성' 배지가 표시됩니다.",
      "이상한 AI 출력(부적절한 내용, 프롬프트 반복 등)은 즉시 관리자에게 신고합니다.",
    ],
    highlight: "직원이 최종 책임자입니다. AI는 도구입니다.",
  },
  {
    id: "poc-notice",
    title: "PoC 환경 고지",
    subtitle: "시뮬레이션 전용 · 실제 고객 영향 없음",
    content:
      "현재 운영 환경은 개념 증명(PoC) 단계입니다:",
    items: [
      "모든 고객 데이터는 합성 데이터이며 실제 고객 정보와 무관합니다.",
      "PoC 자동 승인 모드: 시뮬레이션 목적으로 인간 검토자 필드가 면제될 수 있습니다.",
      "프로덕션 전환 시 PoC 전용 자동 승인 핸들러는 제거됩니다.",
      "외부 콘텐츠 안전 검사는 프로덕션에서 활성화를 권장합니다.",
    ],
    badge: "PoC 전용 환경",
    badgeStyle: "border-yellow-300 bg-yellow-100 text-yellow-800",
  },
  {
    id: "out-of-scope-t230",
    title: "본 PoC 범위 제외 (Out-of-Scope)",
    subtitle: "마이데이터 2.0 및 만 14세 미만 가입자 시나리오는 다루지 않습니다.",
    content:
      "본 PoC는 다음 영역을 명시적으로 다루지 않습니다. 데모 중 관련 질문/요청이 발생해도 시뮬레이션 처리하지 않으며, 실제 운영 도입 시 별도 단계로 검토합니다:",
    items: [
      "마이데이터 2.0 (개인정보 보호법 §40-2 등): 정보주체 권리 행사 흐름 + 마이데이터 사업자 자격 검증 부재. PoC 기간 동안 마이데이터 API 연동/송수신 시뮬레이션 0건.",
      "만 14세 미만 가입자: 법정대리인 동의 흐름 + 청소년 보호 정책 부재. 본 PoC 합성 페르소나는 모두 성인(만 19세 이상)으로 한정.",
      "법인/기관 고객: 자연인 PB/WM 시나리오 한정.",
      "비대면 실명확인 본인인증: KOFIA T236 메타데이터 schema만 검증; 실제 본인확인 API 호출 0건.",
    ],
    badge: "Out-of-Scope",
    badgeStyle: "border-rose-300 bg-rose-100 text-rose-800",
    highlight: "본 PoC 범위 외 시나리오는 운영 격상 시 별도 PRD로 재검토합니다.",
  },
];

export function AIPolicyPage() {
  return (
    <div className="grid gap-6">
      {/* Header */}
      <section className="rounded-3xl bg-gradient-to-r from-slate-700 to-blue-900 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-slate-300">
          AI 거버넌스
          <DevReference inline="REG-04" />
        </p>
        <h1 className="mt-3 text-3xl font-black">AI 사용 정책</h1>
        <p className="mt-2 text-slate-200 text-sm">
          직원 교육용 · AI 이중 격리 계약 · 시스템 프롬프트 누출 방지 · 토큰 예산 관리
        </p>
        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          <span className="rounded-full border border-white/30 bg-white/10 px-3 py-1">AI 이중 격리 계약</span>
          <span className="rounded-full border border-white/30 bg-white/10 px-3 py-1">프롬프트 누출 방지</span>
          <span className="rounded-full border border-white/30 bg-white/10 px-3 py-1">토큰 예산 관리</span>
        </div>
      </section>

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <strong className="font-bold">합성 데이터</strong> · 본 화면에 표시되는 정책 예시는 합성 데이터 기반 시뮬레이션 환경에 적용되는 내용입니다.
      </div>

      {/* Sections */}
      <div className="grid gap-5">
        {POLICY_SECTIONS.map((section) => (
          <section
            key={section.id}
            id={`policy-${section.id}`}
            className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
            aria-labelledby={`policy-heading-${section.id}`}
          >
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2
                  id={`policy-heading-${section.id}`}
                  className="text-base font-black text-slate-950"
                >
                  {section.title}
                </h2>
                {section.subtitle && (
                  <p className="text-xs font-medium text-slate-500 mt-0.5">{section.subtitle}</p>
                )}
              </div>
              {section.badge && (
                <span
                  className={`shrink-0 rounded-full border px-3 py-1 text-xs font-bold ${section.badgeStyle ?? "border-slate-200 bg-slate-100 text-slate-700"}`}
                >
                  {section.badge}
                </span>
              )}
            </div>

            <p className="text-sm leading-relaxed text-slate-800 mb-3">{section.content}</p>

            {section.items && section.items.length > 0 && (
              <ul className="grid gap-2 mb-3" role="list">
                {section.items.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                    <span className="mt-0.5 shrink-0 text-blue-600" aria-hidden="true">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            )}

            {section.highlight && (
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm font-semibold text-blue-900">
                💡 {section.highlight}
              </div>
            )}
          </section>
        ))}
      </div>

      {/* Footer — internal references, admin/audit only */}
      <DevReference
        className="block rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs leading-relaxed text-slate-600"
        inline="참고 문서 · AI-04 RAG Specification · AI-06 NIST AI RMF Mapping · ADR-005 Dual-LLM Quarantine · ADR-004 PoC Auto Approval · REG-04 AI Governance · REG-06 Simulation Governance · OBS-02 Audit Action Codes · RUN-11 Token Budget"
      />
    </div>
  );
}
