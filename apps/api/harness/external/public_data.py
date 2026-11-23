"""Read-only public data clients for batch collectors."""

from __future__ import annotations

import hashlib
import os
import urllib.parse
from dataclasses import dataclass
from typing import Any

from .http import ExternalProviderError, build_url, request_bytes, request_json, request_text


@dataclass(frozen=True)
class ProviderEndpointConfig:
    base_url: str
    api_key: str
    timeout_seconds: float = 10.0

    def require(self, *, provider: str) -> None:
        missing = []
        if not self.base_url:
            missing.append(f"{provider}_BASE_URL")
        if not self.api_key:
            missing.append(f"{provider}_API_KEY")
        if missing:
            raise ExternalProviderError(f"Missing provider configuration: {', '.join(missing)}")


class DartClient:
    """DART disclosure collector using env-configured endpoint and key."""

    def __init__(self, config: ProviderEndpointConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls) -> DartClient:
        return cls(
            ProviderEndpointConfig(
                base_url=os.getenv("DART_API_BASE_URL", "").strip(),
                api_key=os.getenv("DART_API_KEY", "").strip(),
                timeout_seconds=float(os.getenv("DART_TIMEOUT_SECONDS", "10")),
            )
        )

    def list_filings(
        self,
        *,
        corp_code: str,
        begin_date: str,
        end_date: str,
        page_no: int = 1,
        page_count: int = 100,
        report_type: str | None = None,
    ) -> dict[str, Any]:
        self.config.require(provider="DART")
        query: dict[str, str | int | None] = {
            "crtfc_key": self.config.api_key,
            "corp_code": corp_code,
            "bgn_de": begin_date,
            "end_de": end_date,
            "page_no": page_no,
            "page_count": page_count,
        }
        if report_type:
            query["pblntf_ty"] = report_type
        url = build_url(self.config.base_url, "/api/list.json", query)
        return request_json(
            method="GET", url=url, timeout_seconds=self.config.timeout_seconds
        ).payload

    def corp_code_zip(self) -> bytes:
        """Download the OpenDART corpCode ZIP payload for in-memory discovery."""

        self.config.require(provider="DART")
        url = build_url(
            self.config.base_url,
            "/api/corpCode.xml",
            {"crtfc_key": self.config.api_key},
        )
        return request_bytes(
            method="GET", url=url, timeout_seconds=self.config.timeout_seconds
        ).content

    def document_xml(self, *, receipt_no: str) -> str:
        """Download one OpenDART original report XML body for a receipt number."""

        self.config.require(provider="DART")
        clean_receipt = receipt_no.strip()
        if not clean_receipt.isdigit():
            raise ExternalProviderError("DART receipt_no must contain digits only")
        url = build_url(
            self.config.base_url,
            "/api/document.xml",
            {"crtfc_key": self.config.api_key, "rcept_no": clean_receipt},
        )
        return request_text(method="GET", url=url, timeout_seconds=self.config.timeout_seconds).text

    def canonical_document_url(self, *, receipt_no: str) -> str:
        """Return a non-secret canonical OpenDART document URL for persistence/citation."""

        clean_receipt = receipt_no.strip()
        if not clean_receipt.isdigit():
            raise ExternalProviderError("DART receipt_no must contain digits only")
        return build_url(self.config.base_url, "/api/document.xml", {"rcept_no": clean_receipt})


class EcosClient:
    """ECOS macro indicator reader using env-configured endpoint and key."""

    def __init__(self, config: ProviderEndpointConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls) -> EcosClient:
        return cls(
            ProviderEndpointConfig(
                base_url=os.getenv("ECOS_API_BASE_URL", "").strip(),
                api_key=os.getenv("ECOS_API_KEY", "").strip(),
                timeout_seconds=float(os.getenv("ECOS_TIMEOUT_SECONDS", "10")),
            )
        )

    def statistic_search(
        self,
        *,
        statistic_code: str,
        cycle: str,
        start: str,
        end: str,
        item_codes: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        self.config.require(provider="ECOS")
        path_segments = [
            "StatisticSearch",
            self.config.api_key,
            "json",
            "kr",
            "1",
            "100",
            statistic_code,
            cycle,
            start,
            end,
            *item_codes,
        ]
        path = "/" + "/".join(urllib.parse.quote(segment, safe="") for segment in path_segments)
        return request_json(
            method="GET",
            url=build_url(self.config.base_url, path),
            timeout_seconds=self.config.timeout_seconds,
        ).payload

    def _api_payload(
        self,
        *,
        endpoint: str,
        start_row: int = 1,
        end_row: int = 100,
        path_args: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Call one read-only ECOS metadata/list endpoint without exposing the API key."""

        self.config.require(provider="ECOS")
        if start_row < 1 or end_row < start_row:
            raise ExternalProviderError("ECOS row window must satisfy 1 <= start_row <= end_row")
        path_segments = [
            endpoint,
            self.config.api_key,
            "json",
            "kr",
            str(start_row),
            str(end_row),
            *path_args,
        ]
        path = "/" + "/".join(urllib.parse.quote(segment, safe="") for segment in path_segments)
        return request_json(
            method="GET",
            url=build_url(self.config.base_url, path),
            timeout_seconds=self.config.timeout_seconds,
        ).payload

    def key_statistic_list(self, *, start_row: int = 1, end_row: int = 100) -> dict[str, Any]:
        """Return the official ECOS KeyStatisticList metadata payload."""

        return self._api_payload(
            endpoint="KeyStatisticList",
            start_row=start_row,
            end_row=end_row,
        )

    def statistic_table_list(self, *, start_row: int = 1, end_row: int = 1000) -> dict[str, Any]:
        """Return official ECOS statistic table metadata."""

        return self._api_payload(
            endpoint="StatisticTableList",
            start_row=start_row,
            end_row=end_row,
        )

    def statistic_item_list(
        self, *, statistic_code: str, start_row: int = 1, end_row: int = 1000
    ) -> dict[str, Any]:
        """Return official ECOS item metadata for one statistic code."""

        return self._api_payload(
            endpoint="StatisticItemList",
            start_row=start_row,
            end_row=end_row,
            path_args=(statistic_code,),
        )


class DataGoKrClient:
    """DATA_GO_KR collector using env-configured endpoint and service key."""

    def __init__(self, *, base_url: str, service_key: str, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url
        self.service_key = service_key
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> DataGoKrClient:
        encoded_key = os.getenv("DATA_GO_KR_SERVICE_KEY_ENCODING", "").strip()
        decoded_key = os.getenv("DATA_GO_KR_SERVICE_KEY_DECODING", "").strip()
        return cls(
            base_url=os.getenv("DATA_GO_KR_API_BASE_URL", "").strip(),
            service_key=decoded_key or urllib.parse.unquote(encoded_key),
            timeout_seconds=float(os.getenv("DATA_GO_KR_TIMEOUT_SECONDS", "10")),
        )

    def request_endpoint(self, *, path: str, query: dict[str, str | int | None]) -> dict[str, Any]:
        if not self.base_url or not self.service_key:
            raise ExternalProviderError("Missing DATA_GO_KR endpoint or service key configuration")
        full_query = {**query, "serviceKey": self.service_key}
        full_query.setdefault("resultType", "json")
        return request_json(
            method="GET",
            url=build_url(self.base_url, path, full_query),
            timeout_seconds=self.timeout_seconds,
        ).payload


class KrxOfficialClient:
    """Official KRX OpenAPI reader using AUTH_KEY header authentication."""

    DAILY_TRADING_PATHS: dict[str, str] = {
        "KOSPI": "/svc/apis/sto/stk_bydd_trd",
        "KOSDAQ": "/svc/apis/sto/ksq_bydd_trd",
        "KONEX": "/svc/apis/sto/knx_bydd_trd",
    }
    BASIC_INFO_PATHS: dict[str, str] = {
        "KOSPI": "/svc/apis/sto/stk_isu_base_info",
        "KOSDAQ": "/svc/apis/sto/ksq_isu_base_info",
        "KONEX": "/svc/apis/sto/knx_isu_base_info",
    }

    def __init__(self, config: ProviderEndpointConfig) -> None:
        self.config = config

    @classmethod
    def from_env(cls) -> KrxOfficialClient:
        return cls(
            ProviderEndpointConfig(
                base_url=os.getenv("KRX_API_BASE_URL", "").strip(),
                api_key=os.getenv("KRX_API_KEY", "").strip(),
                timeout_seconds=float(os.getenv("KRX_API_TIMEOUT_SECONDS", "20")),
            )
        )

    def _request(self, *, path: str, bas_dd: str) -> dict[str, Any]:
        missing = []
        if not self.config.base_url:
            missing.append("KRX_API_BASE_URL")
        if not self.config.api_key:
            missing.append("KRX_API_KEY")
        if missing:
            raise ExternalProviderError(f"Missing provider configuration: {', '.join(missing)}")
        return request_json(
            method="GET",
            url=build_url(self.config.base_url, path, {"basDd": bas_dd}),
            headers={"AUTH_KEY": self.config.api_key},
            timeout_seconds=self.config.timeout_seconds,
        ).payload

    def daily_trading(self, *, market_code: str, bas_dd: str) -> dict[str, Any]:
        market = market_code.strip().upper()
        path = self.DAILY_TRADING_PATHS.get(market)
        if path is None:
            raise ExternalProviderError(f"Unsupported KRX market code: {market}")
        return self._request(path=path, bas_dd=bas_dd)

    def basic_info(self, *, market_code: str, bas_dd: str) -> dict[str, Any]:
        market = market_code.strip().upper()
        path = self.BASIC_INFO_PATHS.get(market)
        if path is None:
            raise ExternalProviderError(f"Unsupported KRX market code: {market}")
        return self._request(path=path, bas_dd=bas_dd)


def content_hash(text: str) -> str:
    """Stable SHA-256 content hash for raw document deduplication."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
