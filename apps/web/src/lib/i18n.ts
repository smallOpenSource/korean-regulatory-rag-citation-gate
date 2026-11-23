/**
 * Korean i18n keys for PB/WM workspace — REG-02 vocabulary, no jargon.
 * All copy follows 금융투자협회 표준 용어집 and in-house style guide.
 */

export const KO = {
  consultation: {
    workspace: "상담 워크스페이스",
    notes: "상담 노트",
    notesPlaceholder:
      "상담 기록을 입력합니다. 고객 개인정보 원문을 프롬프트/로그에 전송하지 않습니다.",
    complete: "상담 완료",
    completePending: "완료 조건을 충족해야 합니다.",
    aiBriefing: "AI 브리핑",
    generateBriefing: "브리핑 생성 요청",
    briefingPending: "브리핑 생성 대기 중…",
    auditTrail: "감사 추적",
    noAuditEvents: "감사 이벤트 없음",
    suitabilityChecked: "적합성 확인 완료",
    explanationChecked: "설명의무 확인 완료",
    customerSummary: "고객 360 요약",
    selectCustomer: "상단 고객 목록에서 고객을 선택하세요.",
    consultationId: "상담 ID",
    channelCode: "상담 채널",
    status: "상담 상태",
    createdAt: "개설 시각",
  },

  gate: {
    panel: "준법 4개 게이트",
    suitability: "적합성 검토",
    explanation: "설명의무",
    unfairSolicitation: "불공정 권유",
    marketing: "마케팅 심의",
    pass: "통과",
    block: "차단",
    pending: "대기",
    allPassed: "모든 게이트 통과",
    notAllPassed: "미완료 게이트 있음",
    acknowledgeGate: "게이트 확인",
    managerApprove: "관리자 승인",
    gateHelp: "게이트 상태가 '대기'인 경우 해당 체크를 먼저 수행하세요.",
    loadError: "게이트 상태를 불러오지 못했습니다.",
    notApplicable: "상담 ID 선택 후 확인 가능합니다.",
  },

  ai: {
    generatedAt: "생성 시각",
    model: "모델",
    confidence: "신뢰도",
    source: "출처",
    syntheticWatermark: "⚠ 합성 데이터 — 실제 고객 정보 아님",
    aiMetadata: "AI 출력 메타데이터",
    loading: "AI 메타데이터 불러오는 중…",
    noOutputId: "AI 출력 ID가 없습니다.",
    blocked: "AI 출력 차단됨",
    dataQualityNotice: "데이터 품질 고지",
    faithfulness: "근거 충실성",
    faithfulnessOk: "확인",
    faithfulnessReview: "검토 필요",
    faithfulnessMissingDisclosure: "데이터 품질 고지 누락",
    faithfulnessUngroundedFigures: "미근거 수치",
    piiMasked: "식별정보 자동 마스킹",
  },

  customer360: {
    overview: "개요",
    portfolio: "포트폴리오",
    actions: "후속 조치",
    household: "가족 관계",
  },

  household: {
    title: "가족 관계 및 세대간 자산이전",
    syntheticNotice: "합성 데이터 — 실제 가족 관계 정보 아님",
    members: "가족 구성원",
    transferHistory: "세대간 자산이전 이력",
    relation: "관계",
    name: "성명",
    age: "나이",
    assetShare: "자산 비중",
    transferDate: "이전일",
    amount: "금액",
    type: "유형",
    from: "이전자",
    to: "수령자",
    noMembers: "가족 구성원 정보 없음 (합성 데이터)",
    noTransfers: "자산이전 이력 없음 (합성 데이터)",
    giftTransfer: "증여",
    inheritanceTransfer: "상속",
    trustTransfer: "신탁 설정",
    policyNote:
      "세대간 자산이전 전략은 금융투자업 규정 §4-20 및 세법 검토 후 실행하십시오.",
  },
} as const;

export type I18nKey = typeof KO;
