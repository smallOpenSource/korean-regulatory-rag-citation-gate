# FE-01 Frontend Spec

## Stack
- React 18 + TypeScript 5 + Vite 5
- 상태: Zustand (persist 금지, 메모리 전용)
- 서버 상태: TanStack Query v5
- 스타일: Tailwind CSS v4 + shadcn/ui
- 라우터: React Router v6
- 차트: Recharts
- WebSocket: future native WebSocket after ADR-001; current contract uses polling/refetch fallbacks

## Auth Flow
1. /login → POST /auth/login → access_token + employee만 메모리 저장. refresh_token은 HttpOnly cookie로만 수신한다.
   로그인 응답 JSON에 refresh_token을 기대하거나 저장하지 않는다.
2. 앱 boot/보호 라우트 진입/새로고침 시 메모리 세션이 없으면 POST /auth/refresh(credentials 포함,
   Authorization 헤더 없음)로 access_token + employee를 복구한다.
3. API 401 → POST /auth/refresh → 재시도.
4. 로그아웃은 POST /auth/logout으로 cookie를 삭제한 뒤 메모리 세션을 비운다.
5. localStorage, sessionStorage, Zustand persist에 token 저장 금지. access token은 메모리
   전용이고 refresh token은 HttpOnly cookie 전용이다.
6. 모든 `fetch` 호출은 session-aware 경계를 위해 `credentials: "include"`를 사용한다. protected
   API authorization은 여전히 Bearer access token으로만 수행하며 cookie fallback을 추가하지 않는다.

## Session Restore UX
- `useAuthStore`는 `isRestoring`과 `restoreAttempted`를 노출한다.
- `restoreSession()`은 동시 호출을 하나의 `/auth/refresh` 요청으로 합치고, 성공 시 employee
  metadata로 `user`를 재구성한다.
- `ProtectedRoute`는 restore가 끝나기 전에는 중립적인 "인증 세션 확인 중" 상태를 보여주고,
  restore 실패 후에만 `/login`으로 redirect한다.
- 이미 메모리 세션이 있거나 `/auth/refresh`로 세션이 복구된 직원이 `/login`에 도착하면
  로그인 양식을 다시 보여주지 않고 `location.state.from`의 보호 화면(없으면 `/dashboard`)으로
  되돌린다.
- refresh cookie가 만료/삭제되면 `/auth/refresh` 401을 정상 unauthenticated 상태로 처리하고
  브라우저 저장소에 대체 token을 만들지 않는다.

## Protected Routes
- role_code별 접근 권한: SEC-01 참조.
- 권한 없는 경로 접근 시 403 화면 표시.

## WebSocket
- WebSocket push is `backlog/not-current-contract` until ADR-001 is implemented by backend, frontend, tests, and runbooks together.
- Current screens must keep polling/refetch fallbacks through `/ai-jobs/{job_id}`, `/batch/status`, and `/data/readiness`.
- Future login-success connection uses the same-origin `/api/ws` browser path and access-token bootstrap only; refresh cookies are not WebSocket authorization credentials.
- Future `nba_created` event: 사이드바 후속 조치 뱃지 카운트 증가, 토스트 알림.
- Future `ai_job_done` event: 해당 화면 데이터 자동 refetch.
- Future reconnect target: 연결 끊김 시 5초 후 재연결 (최대 5회, 이후 수동 새로고침 안내).

## API Error Handling
- 400: 폼 필드 에러 표시.
- 401: 자동 토큰 갱신 후 재시도.
- 403: "권한이 없습니다" 인라인 표시.
- 500+: "서버 오류, 잠시 후 다시 시도" 토스트.

## Domestic Market / Synthetic Boundary UI
- Dashboard는 `/dashboard.domestic_market_status`를 표시해 국내 시장 데이터 기준시각(`source_as_of`),
  신선도, 품질, 출처/공급자 상태를 보여준다. 화면 라벨은 `기준시각(source_as_of)`처럼
  한국어를 먼저 표기한다. 값이 없으면 "미확인/검증 전"으로
  표시하고 준비 완료(READY)처럼 보이게 하지 않는다.
- Customer 360은 `synthetic_customer_notice`를 항상 노출하고, 포트폴리오/보유상품에는
  `portfolio_valuation` 및 각 holding의 `valuation_source`를 표시한다. 실제 국내 시세
  기준시각(`source_as_of`)이 없으면 합성 보유 평가액임을 명시한다.
- Batch Monitor는 `/batch/status.provider_mode`와 `/data/readiness.domestic_market.checks`를
  함께 표시한다. 로컬 프로필과 건너뜀(SKIPPED), 실패(FAILED), 차단(BLOCKED) 공급자 상태는 한국어 차단/주의
  상태로 노출한다.
- Serviceable 화면은 `/data/readiness.domestic_market.top200_coverage`의
  `DOMESTIC_TOP200_MARKET_CAP`, 선택 종목 수, 30일 커버리지, 누락 member-day, KRX 공식 정책
  상태를 한국어로 설명한다. raw `PROVIDER_DONE`, `READY`, `DONE` 같은 코드는 감사/개발 맥락이
  아니라면 한국어 라벨과 함께 표시한다.
- 프론트엔드 단위 테스트는 API 클라이언트를 mock하지 않는다. API/UI 연결성은 실제 local
  API/seed 데이터 기반 Playwright role E2E로 검증한다.
