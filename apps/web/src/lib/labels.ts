const STATUS_LABELS: Record<string, string> = {
  ACKNOWLEDGED: "확인", // T3-3 F15: consultation_gates.gate_status (V023:43)
  ACTIVE: "활성",
  ACTIVATED: "활성",
  APPROVED: "승인",
  ARCHIVED: "보관",
  BLOCKED: "차단",
  CANCELLED: "취소",
  CLOSED: "종결",
  COMPLETED: "완료",
  DEGRADED: "주의",
  DISMISSED: "해제",
  DONE: "완료",
  DRAFT: "초안",
  EXPIRED: "기한 만료", // T3-3 F15: dispute_cases.status (V028:11)
  FAILED: "실패",
  GENERATED: "생성됨",
  IN_PROGRESS: "진행 중",
  LOADING: "불러오는 중",
  OPEN: "진행 필요",
  PASSED: "통과", // T3-3 F15: consultation_gates.gate_status (V023:43)
  PENDING: "대기",
  PENDING_APPROVAL: "승인 대기",
  PENDING_REVIEW: "검토 대기",
  READY: "준비 완료",
  RESOLVED: "해결",
  RESPONDED: "답변 완료", // T3-3 F15: dispute_cases.status (V028:11)
  REVIEWED: "검토",
  SAVED: "저장",
  SENT: "발송 완료",
  SIMULATED_EXECUTED: "모의 실행 완료",
  SKIPPED: "건너뜀",
  SNOOZED: "보류",
  SUCCEEDED: "성공",
  SUPERSEDED: "이전 버전",
  SYNTHETIC_ONLY: "합성 데이터",
  FRESH: "신선",
  STALE: "오래됨",
  MISSING: "상태 미확정",
  ACCEPTED: "검증 통과",
  UNVERIFIED: "검증 전",
  SYNTHETIC_HOLDING_VALUE: "합성 보유 평가액",
  PROVIDER_DONE: "공급자 완료",
  PROVIDER_NO_DATA: "공급자 무데이터",
  PROVIDER_SKIPPED_CONFIG: "공급자 설정 누락",
  PROVIDER_SKIPPED_DISABLED: "공급자 비활성",
  PROVIDER_FAILED_AUTH: "공급자 인증 실패",
  PROVIDER_FAILED_RATE_LIMIT: "공급자 한도 초과",
  PROVIDER_FAILED_SCHEMA: "공급자 응답 형식 실패",
  PROVIDER_FAILED_NETWORK: "공급자 네트워크 실패",
  OFFICIAL_KRX_APPROVED: "KRX 공식 정책 승인",
  PYKRX_AUXILIARY_APPROVED: "pykrx 보조 정책 승인",
  KRX_BLOCKED: "KRX/PYKRX 정책 차단",
};

const PRIORITY_LABELS: Record<string, string> = {
  P1: "P1 긴급",
  P2: "P2 높음",
  P3: "P3 보통",
  URGENT: "긴급",
  HIGH: "높음",
  MEDIUM: "보통",
  LOW: "낮음",
};

const SEGMENT_LABELS: Record<string, string> = {
  HNWI_CORE: "핵심 고액자산가",
  HNWI_ULTRA: "초고액자산가",
  EMERGING_HNWI: "성장 고액자산가",
};

const RISK_GRADE_LABELS: Record<string, string> = {
  "1": "1등급 안정형",
  "2": "2등급 안정추구형",
  "3": "3등급 균형형",
  "4": "4등급 적극투자형",
  "5": "5등급 고위험관리형",
};

const ACTION_TYPE_LABELS: Record<string, string> = {
  KI_FOLLOW_UP: "녹인 후속관리",
  MATURITY_CALL: "만기 안내",
  MATURITY_FOLLOW_UP: "만기 사후관리",
  NO_CONTACT: "장기 미접촉",
  PORTFOLIO_REBALANCE: "포트폴리오 리밸런싱",
  RISK_REVIEW: "위험 점검",
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  DRAWDOWN_BREACH: "손실 한도 점검",
  KI_TRIGGERED: "녹인 발생",
  MATURITY_DUE: "만기 도래",
  NO_CONTACT: "장기 미접촉",
  REVIEW_DUE: "정기 점검",
  KOREAN_PB_WM_SCENARIO: "PB/WM 표준 시나리오",
};

const JOB_TYPE_LABELS: Record<string, string> = {
  DERIVED_REFRESH: "파생 데이터 갱신",
  DOCUMENT_TRANSFORM: "문서 변환",
  EMBEDDING_REFRESH: "임베딩 갱신",
  HOUSE_VIEW_REFRESH: "하우스뷰 갱신",
  PROVIDER: "공급자 수집",
  PROVIDER_DART: "DART 수집",
  PROVIDER_DATA_GO_KR: "공공데이터 수집",
  PROVIDER_ECOS: "ECOS 수집",
  PROVIDER_BROKER: "증권사 API 수집",
  PROVIDER_KRX: "KRX 공식/pykrx 수집",
  SEED: "기초 데이터 적재",
  SEED_FULL_MVP: "Full MVP 시드",
};

const READINESS_CHECK_LABELS: Record<string, string> = {
  "house_view.active": "활성 하우스뷰",
  "provider.recent_batches": "최근 공급자 배치",
  "rag.embedded_chunks": "문서 청크 준비",
  "seed.active_customers": "고객 시드",
  "seed.portfolios": "포트폴리오 시드",
  "market.security_master": "국내 종목 마스터",
  "market.price_coverage": "국내 가격 커버리지",
  "market.freshness": "시장 데이터 신선도",
  "market.quality": "시장 데이터 품질",
  "market.dart_chunks": "OpenDART 청크",
  "market.embeddings": "시장 RAG 임베딩",
  "provider.krx_policy": "KRX 공식/PYKRX 출처 정책",
  "market.top200_universe": "시가총액 상위 200개 기업",
  "market.top200_30d_coverage": "상위 200개 30일 커버리지",
  "market.official_krx_freshness": "KRX 공식 데이터 신선도",
  "provider.opendart_30d_lineage": "OpenDART 30일 공시 근거",
  "provider.ecos_macro_window": "ECOS 거시지표 구간",
  "rag.dart_embedding_readiness": "OpenDART RAG 임베딩",
  "provider.strictness": "공급자 엄격 모드",
};

const SOURCE_LABELS: Record<string, string> = {
  DART: "OpenDART",
  DATA_GO_KR: "공공데이터포털",
  ECOS: "한국은행 ECOS",
  BROKER: "증권사 Open API",
  KRX: "KRX 공식 OpenAPI",
  MANUAL: "수동 기준",
  OPENDART: "OpenDART",
  PYKRX: "pykrx 비공식 보조 소스",
  PYKRX_AUXILIARY: "pykrx 비공식 보조 소스",
  PYKRX_AUXILIARY_APPROVED: "pykrx 비공식 보조 소스",
  OFFICIAL_KRX_APPROVED: "KRX 공식 정책 승인",
  KRX_BLOCKED: "KRX/PYKRX 정책 차단",
};

// DB column → Korean label mapping.
// Covers BANNED_RAW_DB_FIELD set: source_as_of | created_at | generated_at | observed_at.
// Use dbFieldLabel() wherever a raw column name must be shown as visible text.
const DB_FIELD_LABELS: Record<string, string> = {
  source_as_of: "기준 일자",
  created_at: "생성 시각",
  generated_at: "생성 일시",
  observed_at: "관측 시각",
};

function normalizeCode(code: string): string {
  return code.trim();
}

// Wave-Audit-Defect-Fix D-S2: the previously used banned-pattern suffixes were
// replaced with the canonical 미확정 suffix; unmapped-code branches preserve the
// raw code so PB users can copy/report it (e.g. "상태 미확정 (코드: ABC)").
function unmappedLabel(domain: string, code: string): string {
  return `${domain} 미확정 (코드: ${code})`;
}

export function statusLabel(code?: string | null): string {
  if (!code) {
    return "상태 미확정";
  }
  const normalized = normalizeCode(code);
  if (normalized.includes(":")) {
    const [checkCode, statusCode] = normalized.split(":", 2);
    return `${readinessCheckLabel(checkCode)} · ${statusLabel(statusCode)}`;
  }
  return STATUS_LABELS[normalized] ?? unmappedLabel("상태", normalized);
}

export function priorityLabel(code?: string | null): string {
  if (!code) {
    return "우선순위 미확정";
  }
  const normalized = normalizeCode(code);
  return PRIORITY_LABELS[normalized] ?? unmappedLabel("우선순위", normalized);
}

export function segmentLabel(code?: string | null): string {
  if (!code) {
    return "세그먼트 미확정";
  }
  const normalized = normalizeCode(code);
  return SEGMENT_LABELS[normalized] ?? unmappedLabel("세그먼트", normalized);
}

export function riskGradeLabel(code?: string | null): string {
  if (!code) {
    return "위험등급 미확정";
  }
  const normalized = normalizeCode(code);
  return RISK_GRADE_LABELS[normalized] ?? unmappedLabel("위험등급", normalized);
}

export function actionTypeLabel(code?: string | null): string {
  if (!code) {
    return "업무 유형 미확정";
  }
  const normalized = normalizeCode(code);
  return ACTION_TYPE_LABELS[normalized] ?? unmappedLabel("업무 유형", normalized);
}

export function eventTypeLabel(code?: string | null): string {
  if (!code) {
    return "사후관리 유형 미확정";
  }
  const normalized = normalizeCode(code);
  return EVENT_TYPE_LABELS[normalized] ?? unmappedLabel("사후관리 유형", normalized);
}

export function jobTypeLabel(code?: string | null): string {
  if (!code) {
    return "배치 유형 미확정";
  }
  const normalized = normalizeCode(code);
  return JOB_TYPE_LABELS[normalized] ?? unmappedLabel("배치 유형", normalized);
}

export function readinessCheckLabel(code?: string | null): string {
  if (!code) {
    return "준비 항목 미확정";
  }
  const normalized = normalizeCode(code);
  return READINESS_CHECK_LABELS[normalized] ?? unmappedLabel("준비 항목", normalized);
}

export function sourceLabel(code?: string | null): string {
  if (!code) {
    return "출처 미확정";
  }
  const normalized = normalizeCode(code);
  return SOURCE_LABELS[normalized] ?? unmappedLabel("출처", normalized);
}

export function dbFieldLabel(field: string): string {
  return DB_FIELD_LABELS[field] ?? field;
}
