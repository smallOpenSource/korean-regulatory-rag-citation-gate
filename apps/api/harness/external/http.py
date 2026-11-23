"""Small stdlib JSON HTTP client with redacted provider failures."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from apps.api.harness.core.logging import redact_secret_text


class ExternalProviderError(RuntimeError):
    """Provider call failed with a sanitized message."""


@dataclass(frozen=True)
class JsonHttpResponse:
    status_code: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class TextHttpResponse:
    status_code: int
    text: str


@dataclass(frozen=True)
class BytesHttpResponse:
    status_code: int
    content: bytes


def build_url(base_url: str, path: str, query: dict[str, str | int | None] | None = None) -> str:
    """Build a URL from env-provided base URL and endpoint path."""

    if not base_url:
        raise ValueError("base_url is required")
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    clean_query = {key: str(value) for key, value in (query or {}).items() if value is not None}
    if clean_query:
        url = f"{url}?{urllib.parse.urlencode(clean_query)}"
    return url


def request_json(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float,
) -> JsonHttpResponse:
    """Execute a JSON HTTP request without logging secrets or raw bodies."""

    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            if not isinstance(parsed, dict):
                raise ExternalProviderError("Provider returned non-object JSON")
            return JsonHttpResponse(status_code=response.status, payload=parsed)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:500]
        raise ExternalProviderError(
            f"HTTP {exc.code} from provider: {redact_secret_text(body_text)}"
        ) from exc
    except urllib.error.URLError as exc:
        message = redact_secret_text(str(exc))
        raise ExternalProviderError(f"Provider network error: {message}") from exc
    except json.JSONDecodeError as exc:
        raise ExternalProviderError("Provider returned invalid JSON") from exc


def request_text(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    timeout_seconds: float,
) -> TextHttpResponse:
    """Execute a text HTTP request without logging secrets or raw URLs."""

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/xml,text/xml,text/plain,*/*", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return TextHttpResponse(status_code=response.status, text=raw)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:500]
        raise ExternalProviderError(
            f"HTTP {exc.code} from provider: {redact_secret_text(body_text)}"
        ) from exc
    except urllib.error.URLError as exc:
        message = redact_secret_text(str(exc))
        raise ExternalProviderError(f"Provider network error: {message}") from exc


def request_bytes(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    timeout_seconds: float,
) -> BytesHttpResponse:
    """Execute a binary HTTP request without logging secrets or raw URLs."""

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/octet-stream,*/*", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return BytesHttpResponse(status_code=response.status, content=response.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:500]
        raise ExternalProviderError(
            f"HTTP {exc.code} from provider: {redact_secret_text(body_text)}"
        ) from exc
    except urllib.error.URLError as exc:
        message = redact_secret_text(str(exc))
        raise ExternalProviderError(f"Provider network error: {message}") from exc
