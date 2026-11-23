# INT-06 PYKRX Auxiliary Source Policy

## Decision
`pykrx` is allowed only as `PYKRX_AUXILIARY` evidence for the internal PoC profile. It is not an
official KRX production source, and it must not be displayed or reported as official KRX coverage.

## Operating gate
The batch KRX-family lane may run the pykrx fallback only when all of these are true:

1. `HARNESS_BATCH_KRX_ENABLED=true`
2. `HARNESS_BATCH_KRX_SOURCE=PYKRX`
3. `HARNESS_BATCH_KRX_POLICY=PYKRX_AUXILIARY_APPROVED`
4. the declared `pykrx>=1.2.8` runtime package imports successfully in `wm_env`
5. outbound provider access is available for the approved internal PoC environment

If any gate is missing, the provider stage records sanitized `PROVIDER_SKIPPED_DISABLED` or
`PROVIDER_FAILED_*` evidence instead of fabricating rows.

## Evidence contract
- Persisted market rows from this lane use `market_price_bars.source_code='PYKRX'`.
- `batch_provider_evidence.provider_code` remains `KRX` because the job lane is KRX-family, but
  `provider_detail_json.source_code` must be `PYKRX`.
- `provider_detail_json.source_policy_code` must be `PYKRX_AUXILIARY_APPROVED` before readiness can
  mark the KRX-family policy gate `READY`.
- T55 readiness requires both the explicit runtime policy
  `HARNESS_BATCH_KRX_POLICY=PYKRX_AUXILIARY_APPROVED` and persisted
  `PYKRX_AUXILIARY_APPROVED` provider evidence; PYKRX rows or KRX provider `DONE` evidence alone do
  not close the gate.
- API/UI labels must render `PYKRX` or `PYKRX_AUXILIARY_APPROVED` as
  `pykrx 비공식 보조 소스`.
- T55 closure text for this branch must say
  `T55 internal PoC READY with PYKRX_AUXILIARY`.

## Explicit non-goals
- Official `source_code='KRX'` persistence is separate and requires `HARNESS_BATCH_KRX_SOURCE=KRX`, `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`, `KRX_API_BASE_URL`, and `KRX_API_KEY` via the `AUTH_KEY` header. Do not route official failures into PYKRX fallback;
  retention/display rules, credentials, and approval owner are documented.
- Do not install or enable pykrx silently as a production dependency.
- Do not treat `PROVIDER_NO_DATA`, `SKIPPED`, or missing pykrx as READY.

## Relationship to official KRX OpenAPI

The official branch is distinct from this auxiliary policy. It requires
`HARNESS_BATCH_KRX_SOURCE=KRX`, `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`,
`KRX_API_BASE_URL`, secret `KRX_API_KEY`, the official source-code migration, a KRX OpenAPI
client/parser, and live `market_price_bars.source_code='KRX'` rows with provider evidence carrying
`source_official=true` and `source_policy_code=OFFICIAL_KRX_APPROVED`. Official KRX failures must
record sanitized failed/skipped/no-data evidence and must not automatically retry or close readiness
with PYKRX rows. Keep API/UI labels separate: official KRX is `KRX 공식 OpenAPI` / `KRX 공식 정책 승인`,
while this auxiliary branch remains `pykrx 비공식 보조 소스`.
