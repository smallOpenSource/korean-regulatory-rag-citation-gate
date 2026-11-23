# BATCH-02 Unstructured Collect

## Sources
| source_type_code | API | 무료 한도 |
|---|---|---|
| DART | api.dart.fss.or.kr OpenAPI | 10,000회/일 |
| REG_PAGE | FSS 웹 크롤링 | 제한 없음 |
| WEB_SEARCH | requests + BeautifulSoup | 제한 없음 |

## Deduplication
- content_hash (SHA-256) 기반 중복 확인.
- (content_hash, source_url) unique constraint 위반 시 스킵.

## DART Collection Target
- 문서 유형: 분기보고서, 사업보고서, 주요사항보고서, 대주주변동.
- 대상 종목: portfolio_holdings에 포함된 ticker 기준.
- 배치 실행은 `HARNESS_BATCH_DART_TARGETS_JSON`을 우선 사용한다. 각 대상은
  `corp_code` 또는 6자리 `stock_code`, 선택적 `report_type`, `lookback_days`,
  `page_count`를 가질 수 있다.
- 명시적 대상이 없으면 활성 국내 주식의 ticker를 읽고 OpenDART `/api/corpCode.xml`
  매핑을 잠금 보유 중 메모리에서만 해석한다. 로컬 corp-code 캐시 파일은 만들지 않는다.

## Storage
- raw_documents 테이블에 raw_text 저장.
- is_processed=false 초기값, transform 완료 시 true.


## Implemented Provider Boundary
- DART listing responses are converted by `apps/api/harness/batch/providers.py` into `raw_documents` with `source_type_code='DART'`, a source URL derived from the provider endpoint and receipt number, and a SHA-256 `content_hash`.
- Listing pagination uses `page_no`/`page_count` and `total_page`; `document.xml` is fetched only for
  real filing-list rows with `rcept_no`.
- Source URLs must not include `crtfc_key` or other provider credentials. Missing or malformed provider rows fail the batch job and are recorded as sanitized FAILED evidence instead of local success data.
- Official OpenDART `status=013` no-data responses are not parser failures: they create provider
  no-data evidence, increment skipped counters, and insert no `raw_documents`/`document_sources`
  rows.


## OpenDART Stage 4 Body Ingestion
- DART collection now downloads the real OpenDART `document.xml` body for each filing-list `rcept_no`; filing-list metadata alone is not enough for provider-labelled RAG evidence.
- Persisted citation URLs omit `crtfc_key`; source metadata is written to `document_sources` and chunks carry receipt_no/corp_code/section_path/parser_version.
- Missing credentials or provider errors remain sanitized SKIPPED/FAILED batch evidence, never locally fabricated DART rows.
