# INT-01 Brokerage Open API Integration

## Overview
증권사 Open API (운영자 라이선스 필요).
실시간 국내 주식 시세, 잔고 조회 등에 활용.

## Authentication
- 토큰 방식: POST `${BROKER_TOKEN_PATH}` → access_token (유효 24시간).
- Redis 캐시: key=`broker:access_token`, TTL=23시간.
- 만료 전 자동 갱신 (백그라운드 스케줄러).

## Key Endpoints
- 주식 현재가: GET `${BROKER_QUOTE_PATH}` (거래 ID `${BROKER_QUOTE_TR_ID}`)
- 잔고 조회: GET `${BROKER_BALANCE_PATH}` (거래 ID `${BROKER_BALANCE_TR_ID}`, sandbox/test-account only; 실제 고객 계좌 조회 금지)

## Fallback
- Current implementation does not silently fall back from BROKER to local fixtures.
- If BROKER is unavailable, `broker_market_collector` records sanitized `SKIPPED`/`FAILED` evidence.
- KRX/pykrx is a separate explicit provider gate (`HARNESS_BATCH_KRX_ENABLED=true`) and writes
  `market_prices.source_code='PYKRX'`; it is not a hidden BROKER-success substitute.


## Allowed / Prohibited Calls
- 허용: OAuth token 발급/갱신, 국내 주식 현재가, sandbox/test-account-only 잔고 조회, read-only market data 조회.
- 금지: 주문, 정정, 취소, 이체 등 실제 계좌 상태를 변경하는 trading endpoint 호출.
- order_simulations는 BROKER 주문 API를 호출하지 않고 Harness DB에 시뮬레이션 상태만 기록한다.

## Implemented Client Boundary
- `apps/api/harness/external/broker.py` supports OAuth token caching with Redis key `broker:access_token` and 23-hour TTL.
- Implemented BROKER calls are limited to token issue, current quote inquiry, and sandbox/test-account-only balance inquiry.
- Endpoint paths and transaction ids come from `BROKER_*_PATH` / `BROKER_*_TR_ID` environment variables. The client rejects configured paths containing order/cancel/transfer words, and static tests fail if order/mutation endpoint strings appear in executable code.
