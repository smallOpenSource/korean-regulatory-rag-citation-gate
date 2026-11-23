/**
 * AIModelCardsPage — 7개 AI 에이전트 모델 카드
 *
 * PB/WM 직원에게 보이는 카피는 한국어 평어체로 작성합니다.
 * 내부 참조 식별자(ADR-/REG-/AI-/RUN-/W#-T#)는 DevReference로만 노출하여
 * ADMIN/AUDIT_VIEWER 역할에서만 표시됩니다.
 */

import { useState } from "react";

import { DevReference } from "../components/DevReference";

interface Metric {
  metric: string;
  threshold: string;
  measurement: string;
}

interface Risk {
  risk: string;
  mitigation: string;
}

interface ModelCard {
  agentId: string;
  agentLabel: string;
  endpoint: string;
  model: string;
  waveIntroduced: string;
  lastHardened: string;
  purpose: string;
  trainingData: string;
  architecture: string;
  humanInTheLoop: string;
  metrics: Metric[];
  risks: Risk[];
  refs: string;
}

const HARDENED_SHORT = "이중 격리·시스템 프롬프트 누출 방지·토큰 한도 적용";

const MODEL_CARDS: ModelCard[] = [
  {
    agentId: "consultation_briefing",
    agentLabel: "상담 브리핑",
    endpoint: "POST /consultations/{id}/briefing-job (비동기 응답)",
    model: "Azure GPT-5-mini",
    waveIntroduced: "2차 배포",
    lastHardened: HARDENED_SHORT,
    purpose:
      "PB/WM 직원의 고객 미팅 준비를 위한 사전 상담 브리핑 문서를 생성합니다. 고객 포트폴리오 현황, 후속 조치 추천, 사후관리 항목을 요약합니다. 출력은 직원용 열람 전용이며 검토 없이 고객 기록에 저장되지 않습니다.",
    trainingData: "합성 데이터 전용 (PoC 시나리오). 추가 미세조정 없음. Azure GPT-5-mini 기본 가중치 사용.",
    architecture:
      "이중 격리 아키텍처 적용: 신뢰 입력(데이터베이스 검증 데이터)과 외부 입력(고객 메모·자유형식 노트)을 분리된 호출로 처리. 신실성은 정보 제공 수준이며 인간 검토가 게이트 역할을 합니다.",
    humanInTheLoop:
      "PB/WM 직원이 상담 전 브리핑을 검토하며, 사용 여부를 선택합니다. 고객에게 직접 노출되지 않습니다.",
    metrics: [
      {
        metric: "필수 필드 존재",
        threshold: "고객 컨텍스트 요약·위험 노트 비어 있지 않음",
        measurement: "7개 에이전트 골든 스키마 회귀 테스트",
      },
      { metric: "PII 출력 포함", threshold: "0건", measurement: "PII 후처리 리댁터" },
      {
        metric: "적합성 데이터 존재",
        threshold: "준비 완료(READY) 조건 필수",
        measurement: "상담 파이프라인 게이트",
      },
    ],
    risks: [
      { risk: "메모 주입", mitigation: "외부 메모를 격리 레인에서만 처리해 시스템 지시문과 분리합니다." },
      { risk: "PII 누출", mitigation: "PII 정규식 후처리기로 식별자 출력 차단" },
      { risk: "적합성 데이터 누락", mitigation: "적합성 게이트가 데이터 없을 때 자동 차단" },
      { risk: "시스템 프롬프트 출력", mitigation: "응답 누출 리댁터로 시스템 지시문 표식 자동 가림" },
      { risk: "무제한 토큰 소비", mitigation: "에이전트별 토큰 한도 적용" },
    ],
    refs: "ADR-005, REG-04 §3, AI-03, AI-06, OBS-02",
  },
  {
    agentId: "compliance_check",
    agentLabel: "컴플라이언스 체크",
    endpoint: "POST /recommendation-simulations → gate_detail (동기)",
    model: "해당 없음 (규칙 기반 전용, LLM 미사용)",
    waveIntroduced: "2차 배포",
    lastHardened: "PoC 자동 승인 거버넌스 마커 적용 (LLM 변경 없음)",
    purpose:
      "상품 추천 시뮬레이션을 4게이트 컴플라이언스 프레임워크(적합성·설명의무·이해충돌·KYC/EDD)에 대해 평가합니다. 결과는 시뮬레이션 진행 여부를 결정합니다.",
    trainingData: "해당 없음 — 모델·훈련 데이터 없음. 데이터베이스 규칙과 파이썬 규칙 기반.",
    architecture:
      "구조화된 입력만 처리합니다(포트폴리오·상품·고객·게이트 코드). 자유형식 텍스트 주입 벡터가 존재하지 않습니다. PoC 자동 승인 모드에서는 인간 검토자 필드가 명시적으로 면제될 수 있습니다.",
    humanInTheLoop:
      "규칙 기반 게이트가 1차 결정을 내립니다. 프로덕션에서는 자동 승인이 아닌 거래 유형에 인간 컴플라이언스 검토자가 필수로 지정됩니다.",
    metrics: [
      {
        metric: "결정론적 출력",
        threshold: "100% 규칙 적용, 비결정론 0",
        measurement: "4게이트 컴플라이언스 회귀 테스트",
      },
      { metric: "토큰 소비", threshold: "0", measurement: "Azure 호출 없음" },
      {
        metric: "자동 승인 행 수",
        threshold: "직무 분리 증거 팩에서 별도 카운트",
        measurement: "직무 분리 증거 팩 생성기",
      },
    ],
    risks: [
      {
        risk: "규칙 공백 / 시나리오 누락",
        mitigation: "분기별 규칙 검토 절차 운영",
      },
      {
        risk: "자동 승인 모드 오용",
        mitigation: "거버넌스 마커 명시적 감사·증거 팩 별도 카운트",
      },
    ],
    refs: "ADR-004, REG-02, REG-03, AI-06, OBS-02",
  },
  {
    agentId: "email_draft",
    agentLabel: "이메일 초안",
    endpoint: "POST /email-drafts (동기 응답)",
    model: "Azure GPT-5-mini",
    waveIntroduced: "2차 배포",
    lastHardened: HARDENED_SHORT,
    purpose:
      "PB/WM 직원이 고객에게 발송할 이메일 초안을 생성합니다. 초안은 열람 전용으로, 직원이 명시적으로 승인하고 발송을 트리거해야 합니다(승인 대기 상태 머신). 에이전트가 이메일을 자율적으로 발송하지 않습니다.",
    trainingData:
      "테스트용 합성 데이터 전용 (합성 고객·포트폴리오 식별자, 가짜 도메인 수신자). 추가 미세조정 없음.",
    architecture:
      "이중 격리 적용: 업로드 메모·인라인 컨텍스트는 격리 레인에서만 처리하며, 구조화 필드와 격리 레인 요약만 특권 레인에 전달합니다. 인간 승인이 발송 게이트 역할을 합니다.",
    humanInTheLoop:
      "승인 대기 상태에서 직원이 명시적으로 초안을 승인해야 발송됩니다. 자율 발송이 불가합니다.",
    metrics: [
      { metric: "제목·본문 필드 존재", threshold: "100%", measurement: "7개 에이전트 골든 스키마 회귀 테스트" },
      {
        metric: "초안 내 PII 정규식 적중",
        threshold: "0건 (주민번호·계좌번호 금지)",
        measurement: "PII 후처리 리댁터",
      },
      { metric: "발송 전 인간 승인", threshold: "100%", measurement: "이메일 상태 머신 검증" },
    ],
    risks: [
      { risk: "메모 주입", mitigation: "외부 메모를 격리 레인에서만 처리하고 상태 머신으로 발송 차단" },
      { risk: "PII 누출", mitigation: "PII 정규식 후처리기" },
      { risk: "시스템 프롬프트 누출", mitigation: "응답 누출 리댁터" },
      {
        risk: "무제한 토큰 소비",
        mitigation: "토큰 한도와 승인 대기 단계로 폭주 차단",
      },
    ],
    refs: "ADR-002, ADR-005, REG-04 §3, AI-03, AI-06, OBS-02",
  },
  {
    agentId: "house_view_generation",
    agentLabel: "하우스뷰 생성",
    endpoint: "POST /house-views/{id}/generate (비동기 응답)",
    model: "Azure GPT-5 (대형 모델)",
    waveIntroduced: "2차 배포",
    lastHardened: "외부 리서치 식별 마커·시스템 프롬프트 누출 방지·토큰 한도 적용",
    purpose:
      "실제 공급자 데이터(공시 페이지·규정 문서·리서치 보고서)로부터 구조화된 하우스뷰 문서(자산군 견해, 모델 포트폴리오)를 생성합니다. 출력은 하우스뷰·자산뷰 테이블에 저장되고 후속 조치·상담 브리핑 에이전트가 소비합니다.",
    trainingData:
      "PoC 데모 픽스처에는 합성 데이터만 사용. 추론 시 입력: 공시 영수증·규정 페이지 URL·승인된 리서치 청크. 고객 PII 없음. 추가 미세조정 없음.",
    architecture:
      "외부 리서치를 식별 마커로 감싸 특권 레인에 전달합니다. 출력 새니타이저와 누출 리댁터가 활성화되어 있습니다.",
    humanInTheLoop:
      "리서치·전략팀이 활성화 전 검토합니다: 초안 → 검토 → 활성. 후속 조치·상담 에이전트는 활성 상태만 소비합니다.",
    metrics: [
      {
        metric: "필수 스키마 키 존재",
        threshold: "자산뷰·모델 포트폴리오·생성 시각·모델명",
        measurement: "7개 에이전트 골든 스키마 회귀 테스트",
      },
      {
        metric: "자산뷰 항목당 인용",
        threshold: "공시 영수증 또는 규정 페이지 URL 1개 이상",
        measurement: "스키마 회귀",
      },
      {
        metric: "주입 패턴 감지",
        threshold: "출력 내 0건",
        measurement: "출력 새니타이저",
      },
    ],
    risks: [
      { risk: "리서치 문서 주입", mitigation: "식별 마커 적용·주입 패턴 자동 스캔" },
      {
        risk: "허위정보",
        mitigation: "추출형 출력 전용·자산뷰 항목별 인용 또는 합성 가정 마커 필수",
      },
      { risk: "시스템 프롬프트 누출", mitigation: "응답 누출 리댁터" },
      {
        risk: "무제한 토큰 소비",
        mitigation: "토큰 한도·대형 모델 비용 별도 추적",
      },
    ],
    refs: "REG-04 §3, ADR-005 (스포트라이트 부분), AI-04, AI-06, OBS-02",
  },
  {
    agentId: "nba_script",
    agentLabel: "후속 조치 스크립트",
    endpoint: "POST /nba/{id}/generate-script (동기)",
    model: "Azure GPT-5-mini",
    waveIntroduced: "2차 배포",
    lastHardened: HARDENED_SHORT,
    purpose:
      "직원이 고객에게 후속 조치를 제안할 때 사용하는 대화 스크립트를 생성합니다. 스크립트는 권유 포인트이며 구속력 있는 금융 조언이 아닙니다.",
    trainingData: "합성 데이터 전용. 상품 마스터 데이터 기반. 추가 미세조정 없음.",
    architecture:
      "이중 격리 적용. 상품 식별자 인용을 강제하고 자유형식 주장을 금지합니다. 도구 호출 유도 패턴을 차단합니다.",
    humanInTheLoop:
      "스크립트는 직원이 고객과의 대화에서 사용하기 위해 검토합니다. 구속력 있는 추천이 아닙니다.",
    metrics: [
      { metric: "상품 식별자 인용", threshold: "스크립트 항목당 1개 이상", measurement: "스키마 회귀" },
      { metric: "자유형식 주장", threshold: "0건", measurement: "출력 검증" },
      { metric: "PII 적중", threshold: "0건", measurement: "PII 후처리 리댁터" },
    ],
    risks: [
      { risk: "도구 호출 유도", mitigation: "도구 호출 유도 패턴 자동 차단" },
      { risk: "허위정보", mitigation: "상품 식별자 인용 필수·자유형식 주장 금지" },
      { risk: "시스템 프롬프트 누출", mitigation: "응답 누출 리댁터" },
      { risk: "무제한 토큰 소비", mitigation: "직원별·세션별 토큰 한도" },
    ],
    refs: "REG-04 §3, ADR-005, AI-03, AI-06, OBS-02",
  },
  {
    agentId: "portfolio_analysis",
    agentLabel: "포트폴리오 분석",
    endpoint: "POST /portfolio-analysis (비동기 응답)",
    model: "Azure GPT-5-mini",
    waveIntroduced: "2차 배포",
    lastHardened: HARDENED_SHORT,
    purpose:
      "고객 포트폴리오에 대한 드리프트 분석 및 위험 신호를 생성합니다. 분석 결과는 직원 검토를 지원하며 추천을 지시하지 않습니다.",
    trainingData:
      "구조화된 포트폴리오 데이터; 원시 PII 없음. 합성 데이터 전용 (PoC). 추가 미세조정 없음.",
    architecture:
      "비동기 작업으로 실행되며 시작·실패 감사 쌍을 남깁니다. 평가 데이터 기준시각을 검사하고 포트폴리오 식별자만 참조하며 원시 PII는 사용하지 않습니다.",
    humanInTheLoop:
      "비동기 작업; 직원이 분석 완료 후 검토하고 추천 전에 결과를 확인합니다.",
    metrics: [
      {
        metric: "필수 스키마 키 존재",
        threshold: "드리프트 플래그·위험 플래그·기준시각",
        measurement: "7개 에이전트 골든 스키마 회귀 테스트",
      },
      {
        metric: "평가 데이터 신선도",
        threshold: "기준시각 검사·오래된 경우 STALE 표시",
        measurement: "신선도 검증기",
      },
      { metric: "PII 적중", threshold: "0건", measurement: "PII 후처리 리댁터" },
    ],
    risks: [
      { risk: "평가 데이터 오염", mitigation: "기준시각 신선도 검사 필수" },
      { risk: "PII 누출", mitigation: "포트폴리오 식별자만 사용·PII 후처리 리댁터" },
      { risk: "시스템 프롬프트 누출", mitigation: "응답 누출 리댁터" },
      { risk: "무제한 토큰 소비", mitigation: "비동기 작업·작업 러너 단위 토큰 한도" },
    ],
    refs: "REG-04 §3, ADR-005, AI-03, AI-06, OBS-02",
  },
  {
    agentId: "rag_qa",
    agentLabel: "RAG 질의응답",
    endpoint: "POST /rag/query (동기)",
    model: "Azure GPT-5-mini + 내부 BGE 임베딩",
    waveIntroduced: "2차 배포",
    lastHardened: "이중 격리·시스템 프롬프트 누출 방지·토큰 한도 적용",
    purpose:
      "공시·규정 페이지·리서치 문서로부터 근거 있는 질의응답을 제공합니다. 준비 완료(READY) 상태는 인용된 청크가 1개 이상일 때만 반환되며, 추출형 답변과 인용을 강제합니다.",
    trainingData: "내부 BGE API (공개 임베딩 제공자 없음). 공시·규정·리서치 청크(라이선스 승인 후). 합성 데이터 없음.",
    architecture:
      "이중 격리 적용: 신뢰하지 않는 공급자 텍스트는 격리 레인에서만 처리하며, 구조화 필터·도구 접근은 특권 레인이 담당합니다. 신실성 게이트와 식별 마커가 적용됩니다.",
    humanInTheLoop:
      "UI 배지·주의사항·피드백 루프를 제공합니다. 답변은 직원 의사결정 지원 전용이며 고객에게 직접 제공되지 않습니다.",
    metrics: [
      { metric: "신실성 게이트", threshold: "임계값 충족", measurement: "신실성 판사" },
      {
        metric: "인용 없는 READY 반환",
        threshold: "0건",
        measurement: "인용 필수 검증",
      },
      { metric: "PII 정규식 후처리기", threshold: "0건 적중", measurement: "PII 후처리 리댁터" },
    ],
    risks: [
      { risk: "프롬프트 주입", mitigation: "주입 감지 시 페일클로즈·격리 플래그" },
      { risk: "허위 인용", mitigation: "신실성 게이트·인용 없으면 자동 차단" },
      { risk: "시스템 프롬프트 누출", mitigation: "응답 누출 리댁터·식별 마커 에코 감지" },
      { risk: "무제한 토큰 소비", mitigation: "직원별 AI 호출 한도·신실성 판사 카운트 포함" },
    ],
    refs: "ADR-005, REG-04 §4, AI-04, AI-06, OBS-02",
  },
];

const MODEL_LABEL: Record<string, string> = {
  "해당 없음 (규칙 기반 전용, LLM 미사용)": "규칙 기반",
};

function modelBadgeStyle(model: string): string {
  if (model.includes("GPT-5-mini")) return "border-blue-200 bg-blue-50 text-blue-800";
  if (model.includes("GPT-5")) return "border-indigo-200 bg-indigo-50 text-indigo-800";
  if (model.includes("규칙") || model.includes("해당 없음"))
    return "border-slate-200 bg-slate-100 text-slate-700";
  return "border-slate-200 bg-slate-100 text-slate-600";
}

export function AIModelCardsPage() {
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const filtered = MODEL_CARDS.filter(
    (c) =>
      search === "" ||
      c.agentId.toLowerCase().includes(search.toLowerCase()) ||
      c.agentLabel.toLowerCase().includes(search.toLowerCase()),
  );

  function toggleCard(agentId: string) {
    setExpanded((prev) => (prev === agentId ? null : agentId));
  }

  return (
    <div className="grid gap-6">
      {/* Header */}
      <section className="rounded-3xl bg-gradient-to-r from-indigo-700 to-blue-900 p-8 text-white shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.3em] text-indigo-200">
          AI 거버넌스
          <DevReference inline="REG-03" />
        </p>
        <h1 className="mt-3 text-3xl font-black">AI 모델 카드</h1>
        <p className="mt-2 text-indigo-100 text-sm">
          7개 Harness AI 에이전트의 목적·훈련 데이터·성능 지표·위험 완화 방안
        </p>
      </section>

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <strong className="font-bold">합성 데이터</strong> · 본 모델 카드는 합성 데이터 기반 시뮬레이션 환경의 운영 사실을 요약합니다.
      </div>

      {/* Search filter */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <label htmlFor="card-search" className="mb-2 block text-xs font-semibold text-slate-600">
          에이전트 검색
        </label>
        <input
          id="card-search"
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="예: rag, 이메일, consultation…"
          className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-200"
          aria-label="AI 에이전트 모델 카드 검색"
        />
        <p className="mt-1.5 text-xs text-slate-400" aria-live="polite">
          {filtered.length}개 에이전트 표시 중
        </p>
      </div>

      {/* Cards */}
      <div className="grid gap-4" role="list" aria-label="AI 모델 카드 목록">
        {filtered.map((card) => {
          const isOpen = expanded === card.agentId;
          return (
            <article
              key={card.agentId}
              role="listitem"
              className="rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden"
            >
              {/* Card header — always visible */}
              <button
                type="button"
                onClick={() => toggleCard(card.agentId)}
                aria-expanded={isOpen}
                aria-controls={`card-body-${card.agentId}`}
                className="flex w-full items-start justify-between gap-4 p-5 text-left hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-700"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <code className="rounded bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-700">
                    {card.agentId}
                  </code>
                  <h2 className="text-base font-black text-slate-950">{card.agentLabel}</h2>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${modelBadgeStyle(card.model)}`}
                    aria-label={`모델: ${MODEL_LABEL[card.model] ?? card.model}`}
                  >
                    {MODEL_LABEL[card.model] ?? card.model.replace("Azure ", "").replace(" (대형 모델)", " ★")}
                  </span>
                </div>
                <span className="shrink-0 text-slate-400" aria-hidden="true">
                  {isOpen ? "▲" : "▼"}
                </span>
              </button>

              {/* Card body — expandable */}
              {isOpen && (
                <div id={`card-body-${card.agentId}`} className="border-t border-slate-100 p-5">
                  <div className="grid gap-5">
                    {/* Meta */}
                    <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
                      <div>
                        <span className="font-semibold text-slate-800">엔드포인트: </span>
                        <code>{card.endpoint}</code>
                      </div>
                      <div>
                        <span className="font-semibold text-slate-800">최초 도입: </span>
                        {card.waveIntroduced} · 최근 강화: {card.lastHardened}
                      </div>
                    </div>

                    {/* Purpose */}
                    <section aria-label="목적">
                      <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">목적</h3>
                      <p className="text-sm leading-relaxed text-slate-800">{card.purpose}</p>
                    </section>

                    {/* Training Data */}
                    <section aria-label="훈련 데이터">
                      <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">훈련 데이터 / 지식 소스</h3>
                      <p className="text-sm text-slate-700">{card.trainingData}</p>
                    </section>

                    {/* Architecture */}
                    <section aria-label="아키텍처">
                      <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">아키텍처 참고</h3>
                      <p className="text-sm text-slate-700">{card.architecture}</p>
                    </section>

                    {/* Human-in-the-loop */}
                    <section aria-label="인간 감독">
                      <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-500">인간 감독 게이트</h3>
                      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                        {card.humanInTheLoop}
                      </div>
                    </section>

                    {/* Metrics */}
                    <section aria-label="성능 지표">
                      <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">성능 지표</h3>
                      <div className="overflow-x-auto rounded-xl border border-slate-200">
                        <table className="min-w-full text-xs" aria-label={`${card.agentLabel} 성능 지표`}>
                          <thead className="bg-slate-50">
                            <tr>
                              <th scope="col" className="p-2.5 text-left font-bold text-slate-600">지표</th>
                              <th scope="col" className="p-2.5 text-left font-bold text-slate-600">기준값</th>
                              <th scope="col" className="p-2.5 text-left font-bold text-slate-600">측정 방법</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 bg-white">
                            {card.metrics.map((m, i) => (
                              <tr key={i}>
                                <td className="p-2.5 font-medium text-slate-800">{m.metric}</td>
                                <td className="p-2.5 text-slate-700">{m.threshold}</td>
                                <td className="p-2.5 text-slate-500">{m.measurement}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>

                    {/* Risks */}
                    <section aria-label="위험 및 완화">
                      <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">위험 및 완화 방안</h3>
                      <div className="overflow-x-auto rounded-xl border border-slate-200">
                        <table className="min-w-full text-xs" aria-label={`${card.agentLabel} 위험 및 완화`}>
                          <thead className="bg-slate-50">
                            <tr>
                              <th scope="col" className="p-2.5 text-left font-bold text-slate-600">위험</th>
                              <th scope="col" className="p-2.5 text-left font-bold text-slate-600">완화 방안</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 bg-white">
                            {card.risks.map((r, i) => (
                              <tr key={i}>
                                <td className="p-2.5 font-medium text-red-700">{r.risk}</td>
                                <td className="p-2.5 text-slate-700">{r.mitigation}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </section>

                    {/* Refs — admin/audit only */}
                    <DevReference
                      className="block border-t border-slate-100 pt-3 text-xs text-slate-500"
                      inline={`내부 참조 — ${card.refs}`}
                    />
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
