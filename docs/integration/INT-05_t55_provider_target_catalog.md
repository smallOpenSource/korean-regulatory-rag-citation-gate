# INT-05 T55 Provider Target Catalog

This catalog records non-secret live-provider targets for the T55 readiness gate.
Provider keys stay only in the operator environment; target codes, item codes,
and policy labels are safe to commit.

## ECOS target discovery — 2026-05-16

Discovery command:

```bash
scripts/provider_discovery.sh --provider ecos --env-file /path/to/.env \
  --lookback-days 14 --date-lag-days 1 --max-targets 2 --min-parseable-targets 1
```

Official endpoints used by the gate:

- `KeyStatisticList` — metadata smoke/checkpoint.
- `StatisticTableList` — confirms `STAT_CODE`, `CYCLE`, and `SRCH_YN`.
- `StatisticItemList` — confirms `ITEM_CODE`, unit, freshness, and data count.
- `StatisticSearch` — must return rows parseable by the production ECOS parser.

Live discovery evidence captured on 2026-05-16:

| Role | Statistic code | Cycle | Item code | Indicator name | Official item name | Unit | Freshness observed | Target ref |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Primary | `722Y001` | `D` | `0101000` | `base_rate` | 한국은행 기준금리 | 연% | `END_TIME=20260514`, parseable rows in a 14-day window | `ECOS:722Y001:D:base_rate:0101000` |
| Fallback | `731Y001` | `D` | `0000001` | `usd_krw_reference_rate` | 원/미국달러(매매기준율) | 원 | `END_TIME=20260515`, parseable rows in a 14-day window | `ECOS:731Y001:D:usd_krw_reference_rate:0000001` |

Recommended environment value:

```bash
HARNESS_BATCH_ECOS_TARGETS_JSON='[{"statistic_code":"722Y001","cycle":"D","indicator_name":"base_rate","unit":"연%","item_codes":["0101000"],"lookback_days":14,"date_lag_days":1},{"statistic_code":"731Y001","cycle":"D","indicator_name":"usd_krw_reference_rate","unit":"원","item_codes":["0000001"],"lookback_days":14,"date_lag_days":1}]'
```

Acceptance gate:

- At least one selected ECOS target must return parseable `StatisticSearch.row`
  entries.
- Persisted rows must come only from provider payloads and use
  `macro_indicators.source_code='ECOS'`.
- No `INFO-200`/no-data response can close T55; it remains honest
  `PROVIDER_NO_DATA` evidence.

## OpenDART and KRX policy status

OpenDART and KRX/PYKRX target-policy decisions are tracked by their respective
team lanes. T55 cannot close on ECOS alone; this ECOS catalog only satisfies the
ECOS parseable-row slice of the live-provider readiness plan.
