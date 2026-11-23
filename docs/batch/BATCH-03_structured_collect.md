# BATCH-03 Structured Collect

## Sources
| 데이터 | 라이브러리 | 대상 |
|---|---|---|
| 국내 주식 일별 시세 (OHLCV) | BROKER / DATA_GO_KR / pykrx | securities/product_underlyings에 등록된 KR 상장주식 |
| KRX 전종목 마스터/거래일 | KRX/pykrx | securities/trading_calendar 보강 |
| 채권 시세 | 공공데이터포털 API | 국고채 3·5·10년, DATA_GO_KR_SERVICE_KEY_ENCODING/DECODING 사용 |
| 거시지표 (금리·환율) | 한국은행 ECOS API | 무제한 |
| 펀드 수익률 | 금융투자협회 전자공시 | 보유 펀드 |
| 증권사 Open API (실시간 시세) | 운영자 증권사 Open API | INT-01 참조 |

## Insert Rule
- INSERT ... ON CONFLICT DO NOTHING (중복 날짜 건너뜀).
- 수집 완료 후 batch_job_logs.rows_collected 업데이트.


## Implemented Provider Boundary
- BROKER quote rows are persisted to `market_price_bars` only after `apps/api/harness/external/broker.py` returns a real read-only domestic quote payload; parsed rows use `source_code='BROKER'`.
- ECOS `StatisticSearch` rows are persisted to `macro_indicators` with `source_code='ECOS'`.
  `HARNESS_BATCH_ECOS_TARGETS_JSON` is the preferred target surface and supports item-code path
  segments plus `lookback_days`/`date_lag_days`; official `RESULT.CODE=INFO-200` no-data responses
  create `PROVIDER_NO_DATA` provider evidence and do not insert macro rows.
  Run `scripts/provider_discovery.sh --provider ecos --env-file <env> --report <path>` before
  changing ECOS targets; the gate calls official `KeyStatisticList`, `StatisticTableList`,
  `StatisticItemList`, and `StatisticSearch` endpoints and fails unless at least one selected target
  returns production-parser-ready rows.
- DATA_GO_KR market/public rows use the configured `/getStockPriceInfo` endpoint plus explicit
  `srtnCd`/`basDt`/`clpr`/`mkp`/`hipr`/`lopr`/`trqu` field mapping and persist with
  `source_code='DATA_GO_KR'`. The local PoC target set is 005930, 000660, 035420, 005380, and 068270
  via `HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON`; collected rows must come from live provider payloads.
- KRX-family OHLCV rows are collected only when `HARNESS_BATCH_KRX_ENABLED=true` and one explicit policy branch is configured. Official `HARNESS_BATCH_KRX_SOURCE=KRX` requires `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`, `KRX_API_BASE_URL`, and `KRX_API_KEY`; requests use `AUTH_KEY` and `/svc/apis/sto/stk_bydd_trd` plus `/svc/apis/sto/ksq_bydd_trd`, while parsed rows use `source_code='KRX'`. Auxiliary `HARNESS_BATCH_KRX_SOURCE=PYKRX` requires `PYKRX_AUXILIARY_APPROVED`; parsed rows use `source_code='PYKRX'` and are labeled `pykrx 비공식 보조 소스`. Date-range responses are persisted row-by-row to `market_price_bars`; official failure never auto-falls back to PYKRX
  until terms and credentials are approved, and disabled/missing policy/pykrx states remain visible
  in `batch_job_logs` plus
  `batch_provider_evidence.provider_detail_json`.
- Serviceable official mode sets `HARNESS_BATCH_KRX_UNIVERSE_CODE=DOMESTIC_TOP200_MARKET_CAP`
  with `HARNESS_BATCH_KRX_UNIVERSE_SIZE=200`. It ranks KOSPI/KOSDAQ common-company candidates by
  official KRX market capitalization, records exclusions, and evaluates a 30-calendar-day official
  expected-trading-day denominator; weekends/holidays are calendar evidence, not fabricated bars.
- `scripts/capture_krx_source_governance.py` probes only approved official KRX OpenAPI paths with
  `AUTH_KEY` held in memory and persists endpoint path, market/date, status, returned-row count, and
  redacted evidence hashes. It never persists headers or key values, and it does not refresh the
  canonical latest source-governance artifact when official rows are absent.
- `--lookback-days 30 --as-of-date YYYY-MM-DD` sets the default recent-window contract for ECOS,
  OpenDART, and KRX/PYKRX. Provider-specific env such as
  `HARNESS_BATCH_KRX_START_DATE`/`END_DATE`, `HARNESS_BATCH_DART_BEGIN_DATE`/`END_DATE`, and ECOS
  target JSON windows still override their own target windows.
- Source policy labels in reports are intentionally distinct: official KRX readiness evidence uses
  `OFFICIAL_KRX_APPROVED`, auxiliary PYKRX readiness evidence uses `PYKRX_AUXILIARY_APPROVED`, and
  provider-window purpose labels such as `AUXILIARY_HISTORICAL_DAILY_PRICE` must not be promoted to
  official top-200 readiness. BROKER=`CURRENT_SNAPSHOT`, DATA_GO_KR=`AS_OF_REFERENCE`,
  OpenDART=`DISCLOSURE_WINDOW`, and ECOS=`MACRO_OBSERVATION_WINDOW`.
- Provider OHLCV rows remain `RAW` until the shared market-price collector promotes rows passing the
  DB-level OHLC constraints to `VALID`; this is a quality state transition over real rows, not a data
  fabrication path.
- Missing credentials, provider rejection, malformed payloads, or unavailable endpoints are surfaced to the batch job boundary as sanitized SKIPPED/FAILED evidence. The collector layer does not synthesize provider-labelled success rows.
- Current verification evidence may be mixed: BROKER and DATA_GO_KR can produce real domestic market rows
  while ECOS/OpenDART/KRX may return `PROVIDER_NO_DATA`, FAILED, or SKIPPED evidence under the
  configured targets. Production strict mode must keep that provider incompleteness visible.

## V012 Market Data Guardrails
- `market_prices` is legacy/write-guarded; new collectors and readiness use `market_price_bars`.
- Repository valuation helpers join `product_underlyings` to latest VALID/RECONCILED `market_price_bars`; no valuation query reads `market_prices`.
- Quality and reconciliation evidence is stored in `market_data_quality_checks` and `market_data_evidence`.
