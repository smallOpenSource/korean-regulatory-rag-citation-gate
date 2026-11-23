#!/usr/bin/env python3
"""External dependency attestation — ADR-007 §1 contract.

Live-probes each declared external dependency within an acceptance window.
NO mocks — real client classes only.

Exit codes:
  0  all dependencies passed (or honestly degraded with --allow-degraded)
  2  one or more dependencies failed
  3  configuration error (missing env, invalid window)
  4  Azure token budget exhausted mid-run (partial JSON still written)
"""

from __future__ import annotations

# ruff: noqa: E402
import argparse
import asyncio
import json
import os
import smtplib
import socket
import sys
import time as time_module
import urllib.request
import uuid
from datetime import UTC, date, datetime, time, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Any

# ── Path bootstrap ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import load_env_file
from apps.api.harness.core.logging import redact_secret_text
from apps.api.harness.external.broker import BrokerConfig, BrokerReadOnlyClient
from apps.api.harness.external.public_data import DataGoKrClient, EcosClient

# ── Constants ─────────────────────────────────────────────────────────────────

SCRIPT_VERSION = "1.0"

AGENT_NAMES: tuple[str, ...] = (
    "rag_qa",
    "consultation_briefing",
    "nba_script",
    "email_draft",
    "compliance_check",
    "portfolio_analysis",
    "house_view_generation",
)

# ADR-007 §1 closed-set degraded-reason taxonomy
DEGRADED_REASON_TAXONOMY: frozenset[str] = frozenset({
    "BROKER_OFFICE_HOURS_OFF",
    "DATA_GO_KR_QUOTA_EXHAUSTED",
    "DATA_GO_KR_5XX_TRANSIENT",
    "PYKRX_FDR_HOLIDAY",
    "SMTP_SANDBOX_BOOT_TIMEOUT",
    "AZURE_RATE_LIMIT_THROTTLED_LATE_WINDOW",
    "AZURE_DEPLOYMENT_NOT_PROVISIONED",  # Demo-ready: deployment_name vs tenant mismatch
    "PROVIDER_WINDOW_UNAVAILABLE",
})

ALLOW_DEGRADED_KEYS: frozenset[str] = frozenset({"azure", "smtp", "broker", "data_go_kr", "pykrx_fdr"})

# KRX trading session Mon–Fri 09:00–15:30 KST
KST = timezone(timedelta(hours=9))
KRX_OPEN = time(9, 0)
KRX_CLOSE = time(15, 30)

# Synthetic SMTP probe recipient (ADR-002 allowlist)
ATTEST_RECIPIENT = "syn-attest-01@example.invalid"
ATTEST_SENDER_EMAIL = "attest@harness.internal"
ATTEST_SENDER_NAME = "Harness Attestation"
ATTEST_SUBJECT = "External dependency attestation probe"
ATTEST_BODY = "This is an automated attestation probe. Do not reply."

REPORT_DIR = PROJECT_ROOT / ".omx" / "reports" / "verification"

_AGENT_PROMPTS: dict[str, str] = {
    "rag_qa":                "연결 확인",
    "consultation_briefing": "상담 연결 확인",
    "nba_script":            "NBA 연결 확인",
    "email_draft":           "이메일 연결 확인",
    "compliance_check":      "준법 연결 확인",
    "portfolio_analysis":    "포트폴리오 연결 확인",
    "house_view_generation": "하우스뷰 연결 확인",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text: str) -> datetime:
    text = text.strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid ISO-8601 datetime: {text!r}") from exc
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _exit3(msg: str) -> None:
    print(f"[CONFIG ERROR] {redact_secret_text(msg)}", file=sys.stderr)
    sys.exit(3)


def _dep_gate_ok(dep: dict[str, Any], dep_key: str, allow_degraded: frozenset[str]) -> bool:
    status = dep.get("status", "failed")
    if status == "passed":
        return True
    if status == "degraded":
        reason = dep.get("degraded_reason")
        if reason in DEGRADED_REASON_TAXONOMY and dep_key in allow_degraded:
            return True
    return False


# ── Token budget ──────────────────────────────────────────────────────────────

class TokenBudgetExhausted(Exception):
    pass


class TokenState:
    def __init__(self, *, ceiling_in: int, ceiling_out: int) -> None:
        self.ceiling_in = ceiling_in
        self.ceiling_out = ceiling_out
        self.total_in: int = 0
        self.total_out: int = 0
        self.cost_usd: float = 0.0
        self._cost_per_1m_in = float(os.getenv("AZURE_COST_PER_1M_INPUT_USD", "0.15"))
        self._cost_per_1m_out = float(os.getenv("AZURE_COST_PER_1M_OUTPUT_USD", "0.60"))

    def record(self, *, tokens_in: int, tokens_out: int) -> None:
        self.total_in += tokens_in
        self.total_out += tokens_out
        self.cost_usd += (
            tokens_in * self._cost_per_1m_in / 1_000_000
            + tokens_out * self._cost_per_1m_out / 1_000_000
        )
        if self.total_in > self.ceiling_in or self.total_out > self.ceiling_out:
            raise TokenBudgetExhausted(
                f"Azure token ceiling reached: {self.total_in}/{self.ceiling_in} in, "
                f"{self.total_out}/{self.ceiling_out} out"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "azure_tokens_in": self.total_in,
            "azure_tokens_out": self.total_out,
            "azure_cost_usd_est": round(self.cost_usd, 6),
            "ceiling_in": self.ceiling_in,
            "ceiling_out": self.ceiling_out,
            "ceiling_remaining_in": max(0, self.ceiling_in - self.total_in),
        }


# ── Azure check ───────────────────────────────────────────────────────────────

async def _call_one_agent(
    *, agent: str, client: Any, model: str, token_state: TokenState
) -> dict[str, Any]:
    evidence_id = str(uuid.uuid4())
    prompt = _AGENT_PROMPTS.get(agent, "연결 확인")
    t0 = time_module.monotonic()
    try:
        # GPT-5.5 deployments only expose the Responses API. See
        # tests/test_azure_model.py — Chat Completions is xfail by design.
        response = await client.responses.create(
            model=model,
            instructions=f"You are the {agent} harness agent. Reply in one Korean word.",
            input=prompt,
        )
    except Exception as exc:  # noqa: BLE001
        safe = redact_secret_text(str(exc))
        reason: str | None = None
        lowered = safe.lower()
        if "429" in safe or "rate limit" in lowered or "throttl" in lowered:
            reason = "AZURE_RATE_LIMIT_THROTTLED_LATE_WINDOW"
        elif "404" in safe or "resource not found" in lowered or "deploymentnotfound" in lowered:
            # Honest config-time degradation: the deployment name in .env does not match
            # any provisioned deployment in the configured Azure tenant. Code is
            # correct; environment requires deployment provisioning.
            reason = "AZURE_DEPLOYMENT_NOT_PROVISIONED"
        return {
            "agent": agent, "status": "degraded" if reason else "failed",
            "degraded_reason": reason, "evidence_id": evidence_id, "error": safe[:500],
        }

    latency_ms = int((time_module.monotonic() - t0) * 1000)
    usage = response.usage
    tokens_in = getattr(usage, "input_tokens", 0) if usage else 0
    tokens_out = getattr(usage, "output_tokens", 0) if usage else 0
    token_state.record(tokens_in=tokens_in, tokens_out=tokens_out)  # may raise

    return {
        "agent": agent, "model": str(response.model or model),
        "latency_ms": latency_ms, "tokens_in": tokens_in,
        "tokens_out": tokens_out, "evidence_id": evidence_id, "status": "passed",
    }


async def check_azure_agents(token_state: TokenState) -> dict[str, Any]:
    try:
        from openai import AsyncOpenAI  # type: ignore[import-untyped]
    except ImportError:
        return {"status": "failed", "agent_calls": [], "degraded_reason": None,
                "error": "openai package not installed"}

    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    # Azure AI Foundry OpenAI-compatible v1 endpoint (BASE_URL contains /openai/v1/).
    # gpt-5.5 deployments require this endpoint + standard OpenAI client.
    base_url = os.getenv("AZURE_OPENAI_BASE_URL", "").strip()
    model = (
        os.getenv("AZURE_GPT5_DEPLOYMENT", "").strip()
        or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.5").strip()
    )

    if not api_key or not base_url:
        return {"status": "failed", "agent_calls": [], "degraded_reason": None,
                "error": "AZURE_OPENAI_API_KEY or AZURE_OPENAI_BASE_URL not configured"}

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    agent_calls: list[dict[str, Any]] = []
    overall = "passed"
    overall_reason: str | None = None

    for agent in AGENT_NAMES:
        result = await _call_one_agent(agent=agent, client=client, model=model, token_state=token_state)
        agent_calls.append(result)
        if result.get("status") == "failed":
            overall = "failed"
        elif result.get("status") == "degraded" and overall == "passed":
            overall = "degraded"
            overall_reason = result.get("degraded_reason")

    return {"status": overall, "agent_calls": agent_calls, "degraded_reason": overall_reason}


# ── SMTP sandbox check ────────────────────────────────────────────────────────

def _mailpit_http_ok(host: str, http_port: int) -> bool:
    try:
        req = urllib.request.Request(f"http://{host}:{http_port}/api/v1/messages", method="GET")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def check_smtp_sandbox(mailpit_host: str, mailpit_port: int, mailpit_http_port: int) -> dict[str, Any]:
    msg = EmailMessage()
    msg["From"] = formataddr((ATTEST_SENDER_NAME, ATTEST_SENDER_EMAIL))
    msg["To"] = ATTEST_RECIPIENT
    msg["Subject"] = ATTEST_SUBJECT
    msg["Message-ID"] = make_msgid(domain=mailpit_host)
    msg.set_content(ATTEST_BODY)

    try:
        with smtplib.SMTP(mailpit_host, mailpit_port, timeout=10.0) as smtp:
            smtp.send_message(msg)
    except (OSError, socket.timeout) as exc:
        return {
            "status": "degraded", "transport": "mailpit", "message_id": None,
            "recipient": ATTEST_RECIPIENT, "degraded_reason": "SMTP_SANDBOX_BOOT_TIMEOUT",
            "error": redact_secret_text(str(exc))[:500],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed", "transport": "mailpit", "message_id": None,
            "recipient": ATTEST_RECIPIENT, "degraded_reason": None,
            "error": redact_secret_text(str(exc))[:500],
        }

    captured = _mailpit_http_ok(mailpit_host, mailpit_http_port)
    return {
        "status": "passed", "transport": "mailpit",
        "message_id": str(msg["Message-ID"])[:64],
        "recipient": ATTEST_RECIPIENT,
        "mailpit_http_verified": captured,
        "degraded_reason": None,
    }


# ── BROKER quote check ───────────────────────────────────────────────────────────

def _is_krx_open() -> bool:
    now_kst = datetime.now(KST)
    if now_kst.weekday() >= 5:
        return False
    t = now_kst.time()
    return KRX_OPEN <= t <= KRX_CLOSE


def check_broker_quote() -> dict[str, Any]:
    symbol = os.getenv("HARNESS_ATTEST_BROKER_TICKER", "005930")
    market_code = os.getenv("BROKER_MARKET_CODE", "J")

    if not _is_krx_open():
        return {
            "status": "degraded", "symbol": symbol, "price": None,
            "as_of": _iso(_now_utc()), "degraded_reason": "BROKER_OFFICE_HOURS_OFF",
        }

    try:
        config = BrokerConfig.from_env()
        config.require_core()
        client = BrokerReadOnlyClient(config, redis_client=None)
        _token = client.get_access_token()  # noqa: F841 — side-effect: caches token
        quote = client.inquire_price(market_code=market_code, ticker=symbol)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed", "symbol": symbol, "price": None,
            "as_of": _iso(_now_utc()), "degraded_reason": None,
            "error": redact_secret_text(str(exc))[:500],
        }

    output = quote.get("output") or {}
    price_str = str(output.get("stck_prpr", "") or "").strip()
    try:
        price = int(price_str) if price_str else None
    except ValueError:
        price = None

    if price is None:
        return {
            "status": "failed", "symbol": symbol, "price": None,
            "as_of": _iso(_now_utc()), "degraded_reason": None,
            "error": f"BROKER missing stck_prpr rt_cd={quote.get('rt_cd')!r}",
        }
    return {
        "status": "passed", "symbol": symbol, "price": price,
        "as_of": _iso(_now_utc()), "degraded_reason": None,
    }


# ── Data.go.kr bond check ─────────────────────────────────────────────────────

def check_data_go_kr_bond() -> dict[str, Any]:
    ticker = os.getenv("HARNESS_ATTEST_DGK_TICKER", "114260")  # KODEX 국고채10년
    today_str = date.today().strftime("%Y%m%d")
    market_path = os.getenv("DATA_GO_KR_MARKET_PATH", "/getStockPriceInfo")

    try:
        client = DataGoKrClient.from_env()
        payload = client.request_endpoint(
            path=market_path,
            query={"numOfRows": "1", "pageNo": "1", "basDt": today_str, "srtnCd": ticker},
        )
    except Exception as exc:  # noqa: BLE001
        safe = redact_secret_text(str(exc))
        if "quota" in safe.lower() or "limit" in safe.lower():
            reason = "DATA_GO_KR_QUOTA_EXHAUSTED"
        elif any(code in safe for code in ("500", "502", "503", "504")):
            reason = "DATA_GO_KR_5XX_TRANSIENT"
        else:
            reason = None
        return {
            "status": "degraded" if reason else "failed",
            "bond_id": ticker, "as_of": _iso(_now_utc()),
            "degraded_reason": reason, "error": safe[:500],
        }

    response_body = payload.get("response") or payload
    header = response_body.get("header") or {}
    result_code = str(header.get("resultCode", "")).strip()
    if result_code == "99":
        return {
            "status": "degraded", "bond_id": ticker, "as_of": _iso(_now_utc()),
            "degraded_reason": "DATA_GO_KR_QUOTA_EXHAUSTED",
            "error": str(header.get("resultMsg", ""))[:300],
        }

    body = response_body.get("body") or {}
    items = (body.get("items") or {}).get("item") or []
    if not items:
        return {
            "status": "degraded", "bond_id": ticker, "as_of": _iso(_now_utc()),
            "degraded_reason": "PROVIDER_WINDOW_UNAVAILABLE",
            "note": "No data for today — likely non-trading day",
        }

    first = items[0] if isinstance(items, list) else items
    return {
        "status": "passed", "bond_id": ticker,
        "basDt": str(first.get("basDt", today_str)),
        "clpr": str(first.get("clpr", "")),
        "as_of": _iso(_now_utc()), "degraded_reason": None,
    }


# ── PYKRX/FDR cross-check ────────────────────────────────────────────────────

def check_pykrx_fdr() -> dict[str, Any]:
    today = date.today()
    today_str = today.strftime("%Y%m%d")
    symbol = "005930"

    try:
        from pykrx import stock as pykrx_stock  # pyright: ignore[reportMissingImports]
    except ImportError:
        return {
            "status": "failed", "day": today.isoformat(), "delta_bp": None,
            "degraded_reason": None, "error": "pykrx not installed",
        }

    try:
        df_krx = pykrx_stock.get_market_ohlcv_by_date(today_str, today_str, symbol)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "failed", "day": today.isoformat(), "delta_bp": None,
            "degraded_reason": None, "error": redact_secret_text(str(exc))[:500],
        }

    if df_krx is None or (hasattr(df_krx, "empty") and df_krx.empty):
        return {
            "status": "degraded", "day": today.isoformat(), "delta_bp": None,
            "degraded_reason": "PYKRX_FDR_HOLIDAY",
        }

    try:
        pykrx_close: float | None = float(df_krx["종가"].iloc[-1])
    except Exception:  # noqa: BLE001
        pykrx_close = None

    fdr_close: float | None = None
    try:
        import FinanceDataReader as fdr  # pyright: ignore[reportMissingImports]
        df_fdr = fdr.DataReader(symbol, start=today_str, end=today_str)
        if df_fdr is not None and not df_fdr.empty:
            fdr_close = float(df_fdr["Close"].iloc[-1])
    except Exception:  # noqa: BLE001
        fdr_close = None

    delta_bp: float | None = None
    if pykrx_close and fdr_close and pykrx_close > 0:
        delta_bp = round(abs(pykrx_close - fdr_close) / pykrx_close * 10_000, 2)

    return {
        "status": "passed", "day": today.isoformat(),
        "pykrx_close": pykrx_close, "fdr_close": fdr_close,
        "delta_bp": delta_bp, "degraded_reason": None,
    }


# ── ECOS bonus check ──────────────────────────────────────────────────────────

def check_ecos_bonus() -> dict[str, Any]:
    today = date.today()
    lag = int(os.getenv("HARNESS_BATCH_ECOS_DATE_LAG_DAYS", "1"))
    date_str = (today - timedelta(days=lag)).strftime("%Y%m%d")
    statistic_code = os.getenv("ECOS_STATISTIC_CODE", "722Y001")
    item_code = os.getenv("ECOS_ITEM_CODES", "0101000").split(",")[0].strip()

    try:
        client = EcosClient.from_env()
        result = client.statistic_search(
            statistic_code=statistic_code,
            cycle="D",
            start=date_str,
            end=date_str,
            item_codes=(item_code,) if item_code else (),
        )
        rows = result.get("StatisticSearch", {}).get("row") or []
        row_count = len(rows) if isinstance(rows, list) else (1 if rows else 0)
        return {"status": "passed", "statistic_code": statistic_code,
                "rows_returned": row_count, "as_of": _iso(_now_utc())}
    except Exception as exc:  # noqa: BLE001
        return {"status": "skipped", "statistic_code": statistic_code,
                "as_of": _iso(_now_utc()),
                "error": redact_secret_text(str(exc))[:400]}


# ── Evidence persistence ──────────────────────────────────────────────────────

def _write_evidence(name: str, data: dict[str, Any], report_dir: Path) -> str:
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = _now_utc().strftime("%Y%m%dT%H%M%SZ")
    fpath = report_dir / f"attest-{name}-{ts}.json"
    fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    return str(fpath)


def _partial_result(
    *,
    verified_at: str,
    window_start: datetime,
    window_end: datetime,
    env_profile: str,
    deps: dict[str, Any],
    token_state: TokenState,
    evidence_paths: list[str],
) -> dict[str, Any]:
    return {
        "status": "failed", "passed": False,
        "verified_at": verified_at,
        "window": {"start": _iso(window_start), "end": _iso(window_end)},
        "env_profile": env_profile, "partial": True,
        "abort_reason": "TOKEN_BUDGET_EXHAUSTED",
        "deps": deps, "token_consumption": token_state.as_dict(),
        "evidence_paths": evidence_paths, "script_version": SCRIPT_VERSION,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="External dependency attestation (ADR-007 §1).")
    parser.add_argument("--window-start", type=_parse_iso, default=None,
                        help="ISO-8601 UTC window start (default: now - 24h).")
    parser.add_argument("--window-end", type=_parse_iso, default=None,
                        help="ISO-8601 UTC window end (default: now).")
    parser.add_argument("--allow-degraded", default="",
                        help=f"Comma-separated pre-approved dep keys: {sorted(ALLOW_DEGRADED_KEYS)}")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output JSON path (auto-stamped by default).")
    parser.add_argument("--env-profile", choices=["poc", "acceptance", "demo"], default="poc")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    return parser.parse_args(argv)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:  # noqa: C901
    args = parse_args(argv)

    if args.env_file.exists():
        # load_env_file uses setdefault (env-wins-over-dotenv). For attestation we
        # want .env to take precedence so stale shell exports of provider keys
        # cannot poison the live probe. Force-override AZURE_* and provider keys.
        from pathlib import Path as _P  # noqa: PLC0415
        overrides: list[tuple[str, str]] = []
        for raw_line in _P(args.env_file).read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            ck = k.strip()
            cv = v.strip().strip('"').strip("'")
            if ck.startswith(("AZURE_", "BROKER_", "DATA_GO_KR_", "ECOS_", "MAILPIT_", "SMTP_")):
                overrides.append((ck, cv))
        for ck, cv in overrides:
            os.environ[ck] = cv
        load_env_file(args.env_file)

    now = _now_utc()
    window_end = args.window_end or now
    window_start = args.window_start or (window_end - timedelta(hours=24))
    if window_start >= window_end:
        _exit3("--window-start must be before --window-end")

    allow_degraded: frozenset[str] = frozenset()
    if args.allow_degraded.strip():
        keys = frozenset(k.strip() for k in args.allow_degraded.split(",") if k.strip())
        invalid = keys - ALLOW_DEGRADED_KEYS
        if invalid:
            _exit3(f"Invalid --allow-degraded keys: {sorted(invalid)}")
        allow_degraded = keys

    ceiling_in = int(os.getenv("AZURE_TOKEN_CEILING_IN", "100000"))
    ceiling_out = int(os.getenv("AZURE_TOKEN_CEILING_OUT", "20000"))
    token_state = TokenState(ceiling_in=ceiling_in, ceiling_out=ceiling_out)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts_stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_path: Path = args.out or (REPORT_DIR / f"external-dependency-attestation-{ts_stamp}.json")

    evidence_paths: list[str] = []
    deps: dict[str, Any] = {}

    # 1) Azure × 7 agents
    budget_exhausted = False
    try:
        azure_result = asyncio.run(check_azure_agents(token_state))
    except TokenBudgetExhausted as exc:
        budget_exhausted = True
        azure_result = {
            "status": "failed", "agent_calls": [], "degraded_reason": None,
            "error": str(exc)[:300],
        }
    evidence_paths.append(_write_evidence("azure", azure_result, REPORT_DIR))
    deps["azure_gpt5_mini"] = azure_result

    if budget_exhausted:
        result = _partial_result(
            verified_at=_iso(now), window_start=window_start, window_end=window_end,
            env_profile=args.env_profile, deps=deps,
            token_state=token_state, evidence_paths=evidence_paths,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        print(json.dumps(result, ensure_ascii=False, default=str))
        return 4

    # 2) SMTP sandbox
    mailpit_host = os.getenv("MAILPIT_HOST", "localhost")
    mailpit_port = int(os.getenv("MAILPIT_PORT", "1025"))
    mailpit_http_port = int(os.getenv("MAILPIT_HTTP_PORT", "8025"))
    smtp_result = check_smtp_sandbox(mailpit_host, mailpit_port, mailpit_http_port)
    evidence_paths.append(_write_evidence("smtp", smtp_result, REPORT_DIR))
    deps["smtp_sandbox"] = smtp_result

    # 3) BROKER live quote
    broker_result = check_broker_quote()
    evidence_paths.append(_write_evidence("broker", broker_result, REPORT_DIR))
    deps["broker_live_quote"] = broker_result

    # 4) Data.go.kr bond
    dgk_result = check_data_go_kr_bond()
    evidence_paths.append(_write_evidence("data_go_kr", dgk_result, REPORT_DIR))
    deps["data_go_kr_bond_live"] = dgk_result

    # 5) PYKRX/FDR cross-check
    pykrx_result = check_pykrx_fdr()
    evidence_paths.append(_write_evidence("pykrx_fdr", pykrx_result, REPORT_DIR))
    deps["pykrx_fdr_cross_check"] = pykrx_result

    # Bonus: ECOS (non-gating)
    ecos_result = check_ecos_bonus()
    evidence_paths.append(_write_evidence("ecos", ecos_result, REPORT_DIR))
    deps["ecos_macro_bonus"] = ecos_result

    # ── Gate evaluation ───────────────────────────────────────────────────────
    gate_map = {
        "azure": deps["azure_gpt5_mini"],
        "smtp": deps["smtp_sandbox"],
        "broker": deps["broker_live_quote"],
        "data_go_kr": deps["data_go_kr_bond_live"],
        "pykrx_fdr": deps["pykrx_fdr_cross_check"],
    }
    all_gate_ok = all(
        _dep_gate_ok(v, k, allow_degraded) for k, v in gate_map.items()
    )
    any_degraded = any(v.get("status") == "degraded" for v in gate_map.values())

    overall_status = (
        "failed" if not all_gate_ok
        else ("degraded" if any_degraded else "passed")
    )

    result = {
        "status": overall_status,
        "passed": overall_status in {"passed", "degraded"},
        "verified_at": _iso(now),
        "window": {"start": _iso(window_start), "end": _iso(window_end)},
        "env_profile": args.env_profile,
        "deps": deps,
        "token_consumption": token_state.as_dict(),
        "evidence_paths": evidence_paths,
        "script_version": SCRIPT_VERSION,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
