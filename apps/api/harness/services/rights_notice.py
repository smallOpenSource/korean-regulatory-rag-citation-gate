"""Rights notice service — REG-01 T225 / 금소법 §청약철회·위법계약해지·자료요구·분쟁조정."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Four kinds of statutory rights the investor must be notified of
NOTICE_KINDS: list[dict[str, Any]] = [
    {
        "kind_code": "청약철회_7d",
        "label": "청약철회권",
        "description": "금융상품 계약 체결일로부터 7일(보험 9일) 이내 청약 철회 가능 (금소법 §46).",
        "deadline_days": 7,
    },
    {
        "kind_code": "위법계약해지_1y_5y",
        "label": "위법계약해지권",
        "description": (
            "판매규제(적합성·설명의무·부당권유 등) 위반 시 계약 체결일로부터 5년 이내"
            " (또는 위반 사실 안 날부터 1년 이내) 해지 요구 가능 (금소법 §47)."
        ),
        "deadline_days": 1825,  # 5 years
    },
    {
        "kind_code": "자료요구_30d",
        "label": "자료요구권",
        "description": "상담·판매 관련 자료 열람 요구 가능; 금융회사는 10일 이내 제공 의무 (금소법 §28).",
        "deadline_days": 30,
    },
    {
        "kind_code": "분쟁조정_30d",
        "label": "분쟁조정신청권",
        "description": "금융감독원 분쟁조정위원회에 신청 가능; 조정 결정 30일 이내 수락 여부 통지 (금소법 §36).",
        "deadline_days": 30,
    },
]


@dataclass(frozen=True)
class RightsNoticeResult:
    notice_kinds: list[dict[str, Any]]
    consultation_id: str
    customer_id: str
    employee_id: str


def build_rights_notice(
    consultation_id: str,
    customer_id: str,
    employee_id: str,
) -> RightsNoticeResult:
    """Build rights notice payload for all four statutory rights (REG-01 T225).

    The notice must be issued at consultation end and persisted in
    ``rights_notices`` before the session is marked COMPLETED.
    """
    return RightsNoticeResult(
        notice_kinds=NOTICE_KINDS,
        consultation_id=consultation_id,
        customer_id=customer_id,
        employee_id=employee_id,
    )
