"""Read-only brokerage Open API client with Redis token cache.

Endpoint paths and transaction ids are provider specific, so they come from
environment variables (``BROKER_*_PATH``, ``BROKER_*_TR_ID``) instead of code.
Configured paths are rejected when they look like order/mutation endpoints.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .http import ExternalProviderError, build_url, request_json

BROKER_TOKEN_CACHE_KEY = "broker:access_token"
BROKER_TOKEN_TTL_SECONDS = 23 * 60 * 60
_FORBIDDEN_PATH_WORDS = ("order", "cancel", "transfer")


def _require_read_only_path(name: str, path: str) -> str:
    if not path:
        raise ExternalProviderError(f"Missing BROKER configuration: {name}")
    lowered = path.lower()
    if any(word in lowered for word in _FORBIDDEN_PATH_WORDS):
        raise ExternalProviderError(f"BROKER configuration {name} must be a read-only endpoint")
    return path


@dataclass(frozen=True)
class BrokerConfig:
    base_url: str
    app_key: str
    app_secret: str
    account_no: str | None
    account_product_code: str | None
    is_virtual: bool
    timeout_seconds: float = 10.0
    token_path: str = ""
    quote_path: str = ""
    quote_tr_id: str = ""
    balance_path: str = ""
    balance_tr_id: str = ""

    @classmethod
    def from_env(cls) -> BrokerConfig:
        return cls(
            base_url=os.getenv("BROKER_BASE_URL", "").strip(),
            app_key=os.getenv("BROKER_APP_KEY", "").strip(),
            app_secret=os.getenv("BROKER_APP_SECRET", "").strip(),
            account_no=os.getenv("BROKER_ACCOUNT_NO", "").strip() or None,
            account_product_code=os.getenv("BROKER_ACCOUNT_PROD_CD", "").strip() or None,
            is_virtual=os.getenv("BROKER_IS_VIRTUAL", "false").strip().lower() == "true",
            timeout_seconds=float(os.getenv("BROKER_TIMEOUT_SECONDS", "10")),
            token_path=os.getenv("BROKER_TOKEN_PATH", "").strip(),
            quote_path=os.getenv("BROKER_QUOTE_PATH", "").strip(),
            quote_tr_id=os.getenv("BROKER_QUOTE_TR_ID", "").strip(),
            balance_path=os.getenv("BROKER_BALANCE_PATH", "").strip(),
            balance_tr_id=os.getenv("BROKER_BALANCE_TR_ID", "").strip(),
        )

    def require_core(self) -> None:
        missing = [
            name
            for name, value in {
                "BROKER_BASE_URL": self.base_url,
                "BROKER_APP_KEY": self.app_key,
                "BROKER_APP_SECRET": self.app_secret,
            }.items()
            if not value
        ]
        if missing:
            raise ExternalProviderError(f"Missing BROKER configuration: {', '.join(missing)}")


class BrokerReadOnlyClient:
    """BROKER OAuth, quote, and sandbox/test balance reader."""

    def __init__(self, config: BrokerConfig, redis_client: Any | None = None) -> None:
        self.config = config
        self.redis_client = redis_client

    def get_access_token(self) -> str:
        """Get a cached or freshly issued OAuth access token."""

        self.config.require_core()
        if self.redis_client is not None:
            cached = self.redis_client.get(BROKER_TOKEN_CACHE_KEY)
            if cached:
                return str(cached)
        token_path = _require_read_only_path("BROKER_TOKEN_PATH", self.config.token_path)
        token_url = build_url(self.config.base_url, token_path)
        response = request_json(
            method="POST",
            url=token_url,
            payload={
                "grant_type": "client_credentials",
                "appkey": self.config.app_key,
                "appsecret": self.config.app_secret,
            },
            timeout_seconds=self.config.timeout_seconds,
        ).payload
        token = response.get("access_token")
        if not isinstance(token, str) or not token:
            raise ExternalProviderError("BROKER token response missing access_token")
        if self.redis_client is not None:
            self.redis_client.set(BROKER_TOKEN_CACHE_KEY, token, ex=BROKER_TOKEN_TTL_SECONDS)
        return token

    def _headers(self, *, tr_id: str) -> dict[str, str]:
        token = self.get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def inquire_price(self, *, market_code: str, ticker: str) -> dict[str, Any]:
        """Read current domestic stock quote; does not mutate account state."""

        path = _require_read_only_path("BROKER_QUOTE_PATH", self.config.quote_path)
        if not self.config.quote_tr_id:
            raise ExternalProviderError("Missing BROKER configuration: BROKER_QUOTE_TR_ID")
        url = build_url(
            self.config.base_url,
            path,
            {"fid_cond_mrkt_div_code": market_code, "fid_input_iscd": ticker},
        )
        return request_json(
            method="GET",
            url=url,
            headers=self._headers(tr_id=self.config.quote_tr_id),
            timeout_seconds=self.config.timeout_seconds,
        ).payload

    def inquire_sandbox_balance(self) -> dict[str, Any]:
        """Read sandbox/test account balance only."""

        if not self.config.is_virtual:
            raise ExternalProviderError("BROKER balance reads require sandbox/test account mode")
        if not self.config.account_no or not self.config.account_product_code:
            raise ExternalProviderError("BROKER sandbox balance account config is missing")
        path = _require_read_only_path("BROKER_BALANCE_PATH", self.config.balance_path)
        if not self.config.balance_tr_id:
            raise ExternalProviderError("Missing BROKER configuration: BROKER_BALANCE_TR_ID")
        query: dict[str, str | int | None] = {
            "CANO": self.config.account_no,
            "ACNT_PRDT_CD": self.config.account_product_code,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        return request_json(
            method="GET",
            url=build_url(self.config.base_url, path, query),
            headers=self._headers(tr_id=self.config.balance_tr_id),
            timeout_seconds=self.config.timeout_seconds,
        ).payload
