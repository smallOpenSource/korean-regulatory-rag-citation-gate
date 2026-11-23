/**
 * banned-patterns.ts — 공유 금지 패턴 레지스트리 (v1.0, 2026-05-19)
 *
 * S4 — 결함 카탈로그 evolution 부재 대응:
 *   패턴 추가/변경은 이 파일에만 집중. 버전 주석으로 변경 이력 박제.
 *   월간 baseline diff: scripts/banned_pattern_baseline_diff.py
 *
 * Import: G6 (qa-audit-quality.spec.ts), G8 (visual-fullwalk.spec.ts)
 *
 * @version 1.0.0
 * @since   2026-05-19  초기 정의 (Visual Full-Walk Audit v7.1, PRD §7 Architecture)
 */

// ── BANNED 8종 (PRD §6 factual basis, qa-audit-quality.spec.ts:35-51 기준) ──

/** 영문 내부 용어 노출 (ADR/REG 문서 용어가 PB 화면에 노출) */
export const BANNED_ENGLISH =
  /\b(evidence|persisted|snapshot|universe|denominator|staff display)\b/i;

/**
 * 내부 분류체계 식별자 노출 (ADR-###, W#-T#, REG-0# 등).
 * ADMIN/AUDIT_VIEWER role-gated 표시가 필요한 식별자.
 */
export const BANNED_INTERNAL_ID = /\b(ADR-\d+|W\d-T\d+|REG-0\d)\b/;

/** 테스트 픽스처 마커 노출 (GOLDEN_TEST, RALPH-QA, Synthetic boundary 등) */
export const BANNED_TEST_FIXTURE =
  /(GOLDEN_TEST|RALPH(?:-?QA)?|Synthetic boundary|golden regression test)/;

/** ISO 마이크로초 타임스탬프 노출 (예: 2026-04-20T13:52:53.650391Z) */
export const BANNED_ISO_MICRO = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+/;

/**
 * PostgreSQL 텍스트 마이크로초 타임스탬프 노출 (예: 2026-05-16 14:52:16.847752+00).
 * banker UI는 formatBankerTimestamp 적용 후에만 표시해야 함.
 */
export const BANNED_PG_MICRO_TIMESTAMP = /\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+/;

/**
 * PostgreSQL UTC 오프셋 글리프 노출 (예: +00 without colon).
 * HH:MM[:SS][.fraction]+NN 패턴으로 범위 제한 — "+5%" / "-30일" 오탐 방지.
 */
export const BANNED_PG_SHORT_TZ = /\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?[+-]\d{2}(?!:)/;

/**
 * 로딩/placeholder 복사문이 페이지 안정 후에도 visible.
 * 데이터 경로 파손 또는 empty-state UX 미설계 신호.
 * v8 cycle 1 (2026-05-20): "불러오는 중" 단독 + "로딩 중" 패턴 추가
 * — HouseViewDetailPage / Consultation placeholder 사건
 * ([[2026-05-18-dashboard-incident]]) 재발 차단.
 */
export const BANNED_PLACEHOLDER =
  /응답을 기다리는 중|불러오는 중|로딩 중|최신 생성 정보 준비 중|생성 대기|모델 대기/;

/** 영문 DB 컬럼명이 한국어 본문에 노출 (source_as_of, created_at 등) */
export const BANNED_RAW_DB_FIELD =
  /\b(source_as_of|created_at|generated_at|observed_at)\b/;

// ── 신규 패턴 ───────────────────────────────────────────────────────────────

/**
 * AUDIT-% 픽스처 타이틀이 PB/WM 화면에 노출 (TF-4 defense-in-depth).
 * ADMIN + include_test_fixtures=true 로만 조회 가능해야 함.
 * multiline flag: 여러 줄 textContent에서도 줄 첫머리 매칭.
 */
export const BANNED_AUDIT_PREFIX = /^AUDIT-(NEG|POS)-\d+/m;

/**
 * 단독 대시 노출 (U+002D `-` + U+2014 `—`).
 * MetadataBlock에서 null 필드를 fallback `-`/`—` 로 렌더링하면 미완료 신호.
 * 패턴: 공백·따옴표 인접 단독 대시 — 합성어(-) / 부호(-5%) 오탐 최소화.
 *
 * PRD §6 dash occurrence: HouseViewDetailPage.tsx:86-94, 127-128 총 9건 기준.
 */
export const BANNED_DASH = /(?:^|\s|["'])[-—](?:\s|["']|$)/;

// ── 전체 목록 (iteration / batch assertion용) ───────────────────────────────

export const ALL_BANNED = [
  BANNED_ENGLISH,
  BANNED_INTERNAL_ID,
  BANNED_TEST_FIXTURE,
  BANNED_ISO_MICRO,
  BANNED_PG_MICRO_TIMESTAMP,
  BANNED_PG_SHORT_TZ,
  BANNED_PLACEHOLDER,
  BANNED_RAW_DB_FIELD,
  BANNED_AUDIT_PREFIX,
  BANNED_DASH,
] as const;
