# BIZ-11 처리방침 — 합성 고객 동의 및 신용정보 권리 (신용정보법 §32/§37/§38 + 금소법 §46/§47)

> **PoC 전용 문서.** 본 처리방침은 Harness WMAH PoC의 합성(Synthetic) 데이터 시뮬레이션에 적용된다.
> 실제 개인신용정보는 처리하지 않는다.

## 1. 동의 유형 (consent_type)

| 코드 | 설명 | 근거 조항 |
|---|---|---|
| `GENERAL_BUNDLE` | 자본시장법·신용정보법·금소법 의무 이행 일괄동의 | 신용정보법 §32, 자본시장법 §40 |
| `INFORMATION_USE` | 합성 고객 정보 내부 이용 동의 | 신용정보법 §33 |
| `MARKETING_CONTACT` | 마케팅·영업 목적 연락 동의 | 신용정보법 §37 |
| `DATA_SHARING_THIRD_PARTY` | 제3자 제공 동의 (시뮬레이션) | 신용정보법 §32 제3항 |

모든 동의 레코드는 `synthetic = true`로 저장되며 DB CHECK 제약으로 강제된다.

## 2. 동의 라이프사이클

```
grant_consent → [active] → withdraw_consent → [withdrawn]
                 ↑                                ↑
        POST /consents/grant          POST /consents/withdraw
                                   (MARKETING_CONTACT: /consents/marketing/stop)
```

- `withdrawn_at IS NULL` = 유효한 동의
- `withdrawn_at IS NOT NULL` = 철회됨 (신용정보법 §37 즉시 반영 원칙)
- 마케팅 연락중지(`MARKETING_CONTACT` 철회) 후 이메일 발송 차단: worker-hotel email_draft 서비스에서 동의 상태 확인 후 BLOCKED 처리

## 3. 일괄동의 처리방침 (T229, GENERAL_BUNDLE)

`POST /consents/general-bundle` 호출 시 `consent_scope`에 다음 법령이 포함된다:

- 자본시장법 §40 (적합성 정보 수집)
- 신용정보법 §32 (제공·활용 동의)
- 신용정보법 §33 (이용 제한 목적 범위)
- 금소법 §17 (적합성 원칙 이행)
- 금소법 §19 (설명의무 이행)

보유기간: 5년 (금소법 §28 기준).

## 4. 열람·정정 청구 (T216, 신용정보법 §38)

| 엔드포인트 | 동작 |
|---|---|
| `POST /info-access-requests` | ACCESS(열람) 또는 CORRECTION(정정) 요청 생성 |
| `POST /info-access-requests/{id}/respond` | 담당 직원이 요약·회신 등록 |

`response_summary_redacted`: 실제 운영에서는 PII를 마스킹 후 저장; PoC에서는 합성 응답 텍스트 사용.

## 5. 감사 코드 (OBS-02 연계)

| action_code | 발생 시점 |
|---|---|
| `consent_recorded` | 개별 동의 신규 등록 |
| `consent_withdrawn` | 비마케팅 동의 철회 |
| `marketing_consent_withdrawn` | MARKETING_CONTACT 철회 / 연락중지청구 |
| `info_access_requested` | 열람·정정 요청 생성 |
| `info_access_responded` | 열람·정정 요청 응답 등록 |
| `general_bundle_consent` | 일괄동의 등록 |

## 6. UI 안내문 (합성 데이터 워터마크)

모든 동의 관련 API 응답에 `"synthetic": true` 필드가 포함된다.
프론트엔드는 이 필드를 확인하여 다음 배너를 표시한다:

> **[합성 데이터 시뮬레이션]** 본 동의 흐름은 신용정보법 §32·§33·§37 준수 시뮬레이션이며,
> 실제 개인정보를 처리하지 않습니다.

## 7. 관련 문서

- `docs/regulations/REG-01_legal_impact_matrix.md` §5 T214-T217, T229
- `docs/regulations/REG-01_legal_impact_matrix.md` §2.3 신용정보법 §32/§37/§38
- `db/migrations/V027__consents_synthetic.sql`
- `apps/api/harness/services/consents.py`
- `apps/api/harness/api/routers/consents.py`
