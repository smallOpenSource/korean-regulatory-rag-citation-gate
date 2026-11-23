# DB-04 Batch Tables

## source_licenses / securities / identifiers
- `source_licenses` records KRX/BROKER/DATA_GO_KR/PYKRX source status and constrains MVP sources to domestic equities.
- `securities` is the domestic Korea equity master: six-digit ticker, KR ISIN matching `^KR[0-9A-Z]{10}$`, KOSPI/KOSDAQ/KONEX, KRW, active flag. V018 normalizes this away from the old KR7-only assumption so official KRX `ISU_CD` rows such as KR8... listings are accepted without fabricating identifiers.
- `security_identifiers` maps TICKER/ISIN/KRX_SHORT_CODE values to `securities`.

## product_underlyings / trading_calendar
- `product_underlyings` links products to domestic `securities` for valuation/readiness from price bars only.
- `trading_calendar` stores KOSPI/KOSDAQ/KONEX trading days and holidays.

## market_universe_snapshots / candidates / members
- V017 adds the DB foundation for `DOMESTIC_TOP200_MARKET_CAP`: snapshot headers, all official KRX rank candidates, and selected top-200 members.
- Candidate rows retain `rank_before_filter`, `rank_after_filter`, `market_cap_krw`, `listed_shares`, `raw_payload_hash`, inclusion state, and exclusion reason so preferred-share or non-company filtering remains auditable.
- Member rows are selected official KRX equities only and enforce unique snapshot ranks, tickers, and securities.

## market_trading_calendar / market_universe_coverage_daily
- `market_trading_calendar` stores the official/observed KOSPI/KOSDAQ denominator for the 30 calendar-day window with `source_policy_code`; weekends and holidays are closed-day evidence rather than fabricated bars.
- `market_universe_coverage_daily` stores one member/date fact for each selected security and links valid expected trading days to `market_price_bars`; missing expected rows require `missing_reason_code`.

## market_data_evidence / market_data_quality_checks
- `market_data_evidence` stores source payload/backfill/reconciliation/quality evidence metadata by payload hash.
- `market_data_quality_checks` stores PASS/WARN/FAIL quality observations with JSON detail.

## market_price_bars
(id, security_id, source_code, price_date, timeframe_code, open_price, high_price, low_price,
 close_price, adjusted_close_price, volume, trading_value_krw, market_cap_krw, listed_shares,
 change_price, change_rate_pct, source_as_of, evidence_id, quality_status_code,
 quality_message, is_synthetic, created_at, updated_at)
- source_code: KRX | BROKER | DATA_GO_KR | PYKRX
- timeframe_code: 1D
- quality_status_code: RAW | VALID | WARN | REJECTED | RECONCILED
- unique: (security_id, price_date, source_code, timeframe_code)
- `is_synthetic` is constrained FALSE.

## market_prices (legacy)
(id, ticker, source_code, price_date, open_price, high_price, low_price, close_price, volume, created_at)
- V009 legacy table. V012 backfills eligible BROKER/DATA_GO_KR/PYKRX rows to `market_price_bars` and installs a write guard trigger.
- New repositories, readiness, valuation, and batch postconditions must not read or write this table.

## financial_ratios
(id, ticker, source_code, ratio_date, per, pbr, roe, debt_ratio, eps, dividend_yield, created_at)
- unique: (ticker, ratio_date, source_code)

## investor_flows
(id, fund_code, fund_name, fund_type_code, flow_date, net_flow_krw, aum_krw, source_code, created_at)
- unique: (fund_code, flow_date, source_code)

## macro_indicators
(id, indicator_code, indicator_name, reference_date, value, unit, source_code, created_at)
- source_code: ECOS; FRED/WORLDBANK는 미래 확장 source_code로 예약하며 MVP 수집 대상은 아니다.
- unique: (indicator_code, reference_date, source_code)

## raw_documents
(id, source_type_code, source_url, content_hash, raw_text, collected_at, is_processed, processed_at)
- unique: (content_hash, source_url)

## batch_job_logs
(id, job_name, job_type_code, status_code, started_at, finished_at,
 rows_collected, rows_skipped, rows_failed, error_message, created_at)
- status_code: RUNNING | DONE | FAILED | SKIPPED
- The local operator runner writes stage evidence with job names such as `seed_full_mvp`,
  `broker_market_collector`, `data_go_kr_market_collector`, `ecos_macro_collector`,
  `dart_disclosure_collector`, `krx_market_collector`, `raw_document_transform`,
  `bge_embedding_refresh`, `aftercare_nba_derived_refresh`, and
  `house_view_readiness_snapshot`.
- Current runner `job_type_code` values are operational strings (`SEED_FULL_MVP`,
  `PROVIDER_BROKER`, `PROVIDER_DATA_GO_KR`, `PROVIDER_ECOS`, `PROVIDER_DART`,
  `PROVIDER_KRX`, `DOCUMENT_TRANSFORM`, `EMBEDDING_REFRESH`, `DERIVED_REFRESH`,
  `HOUSE_VIEW_REFRESH`).

## batch_provider_evidence
(id, batch_job_log_id, provider_code, provider_status_code, target_ref,
 rows_collected, rows_skipped, rows_failed, reason_message, provider_detail_json,
 observed_at)
- V015 provider-detail table. It is intentionally separate from `batch_job_logs` so
  provider no-data/config/auth/rate-limit/schema/network states do not expand the stable
  job-status vocabulary.
- provider_status_code: PROVIDER_DONE | PROVIDER_NO_DATA | PROVIDER_SKIPPED_CONFIG |
  PROVIDER_SKIPPED_DISABLED | PROVIDER_FAILED_AUTH | PROVIDER_FAILED_RATE_LIMIT |
  PROVIDER_FAILED_SCHEMA | PROVIDER_FAILED_NETWORK
- `target_ref` must be deterministic and secret-free, for example
  `ECOS:722Y001:D:base_rate:0101000`, `DART:00126380:90d`,
  `PYKRX:005930:YYYYMMDD-YYYYMMDD`, or official KRX
  `KRX:{market}:{basDd}:{ticker_filter_hash12}`.
- unique: (batch_job_log_id, provider_code, target_ref)
- `/batch/status` includes these rows as `provider_evidence` for each job log; UI and
  readiness code must treat `PROVIDER_NO_DATA` as honest unavailable evidence, not as a
  parser failure and not as fabricated READY data.
- `/data/readiness.t55_provider_readiness` reads this table together with
  `macro_indicators`, `raw_documents`, `document_sources`, `document_chunks`, and
  `market_price_bars` so T55 READY can only come from persisted ECOS rows, OpenDART
  document/chunk evidence, and an explicit KRX/PYKRX policy branch. Official KRX READY requires
  official runtime policy, real `market_price_bars.source_code='KRX'` rows, `PROVIDER_KRX` DONE
  evidence, and `provider_detail_json.source_policy_code=OFFICIAL_KRX_APPROVED`; PYKRX rows cannot
  satisfy that branch.
- `scripts/t55_schema_preflight.py` is the read-only Stage 0 evidence command. It
  validates SQL_ID migration files, checks V012-V018 and required provider tables on
  the active PostgreSQL database, pings Redis, exercises an owner-value SETNX/release
  lock smoke, and writes a secret-free JSON report under
  `.omx/reports/t55/schema-preflight-*.json`. Its provider evidence counts split
  official `KRX` rows/trading days and `OFFICIAL_KRX_APPROVED` evidence from
  auxiliary `PYKRX` rows/trading days and `PYKRX_AUXILIARY_APPROVED` evidence.

## Seed / Provider Provenance
- `db/seed.py --profile full-mvp` may insert MANUAL `raw_documents`, `documents`, and `document_chunks` for baseline RAG readiness.
- The seed must not insert provider-owned rows into `market_prices`, `financial_ratios`, `investor_flows`, or `macro_indicators`.
- BROKER/ECOS/DATA_GO_KR/DART/KRX unavailable states are represented by sanitized
  `batch_job_logs` rows plus `batch_provider_evidence` rows with provider-detail status.
- Embeddings remain `NULL` and `is_embedded=false` until the internal BGE batch refresh succeeds.


## DART/RAG Evidence Tables
- DART provider collection writes raw XML to `raw_documents` and source lineage to `document_sources`; transform links that source row to `documents`.
- RAG responses that return READY must persist cited chunk evidence in `rag_answer_evidence`; BLOCKED responses do not fabricate evidence rows.
