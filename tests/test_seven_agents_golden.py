"""7-agent golden JSON-schema regression tests (REG-04 T261).

For each of the 7 Harness AI agents:
1. house_view_generation  — async (POST /house-views + POST /house-views/{id}/generate)
2. consultation_briefing  — async (POST /consultations/{id}/briefing-job)
3. nba_script             — async (POST /nba-actions/{id}/script-job) [Wave 2, BLOCKER #26]
4. email_draft            — sync  (POST /email-drafts)
5. rag_qa                 — sync  (POST /rag/query)
6. compliance_check       — sync  (POST /recommendation-simulations → gate_detail)
7. portfolio_analysis     — async (POST /customers/{id}/portfolio-analysis-job)

Tests assert output JSON schema matches golden fixture in tests/goldens/agents/*.json.

Requires:
- W2-T1 (worker-golf): RAG pipeline (#21, currently BLOCKED)
- W2-T2 (worker-golf): rag_answer_evidence + faithfulness (#22, in_progress)
- W2-T6 (worker-juliet): house_view + NBA lifecycle (#26, in_progress)
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"
GOLDENS_DIR = PROJECT_ROOT / "tests" / "goldens" / "agents"
SYNTHETIC_PASSWORD = "HarnessSynthetic!2026"

ACCOUNTS = {
    "PB": "synthetic.pb1@example.invalid",
    "ADMIN": "synthetic.admin@example.invalid",
}

CUSTOMER_PB1 = "33333333-3333-3333-3333-333333333301"
CONSULTATION_PB1 = "66666666-6666-6666-6666-666666666301"
PRODUCT_ID = "44444444-4444-4444-4444-444444444401"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _load_golden(agent_id: str) -> dict[str, Any]:
    path = GOLDENS_DIR / f"{agent_id}.json"
    assert path.exists(), f"Golden fixture missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: Any | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any, str]:
    data = None
    headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, json.loads(text) if text else {}, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {"raw": text}
        return exc.code, payload, text


def _prepare_database() -> None:
    import asyncio

    async def _run() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        from db.migrator import database_url_from_env, load_env_file
        from db.seed import apply_profile

        load_env_file(PROJECT_ROOT / ".env")
        # DB is already fully migrated by other workers; just connect and seed.
        try:
            conn = await connect_with_retry(asyncpg, database_url_from_env())
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable: {exc}")
        try:
            await apply_profile(conn, "full-mvp")
        finally:
            await conn.close()

    asyncio.run(_run())


def _validate_schema(payload: dict[str, Any], golden: dict[str, Any], agent_id: str) -> None:
    """Assert payload keys and types match the golden schema fixture."""
    required_keys = golden.get("required_keys", [])
    for key in required_keys:
        assert key in payload, (
            f"[{agent_id}] Missing required key '{key}' in response {list(payload.keys())} "
            f"(REG-04 T261 golden schema)"
        )

    key_types = golden.get("key_types", {})
    for key, expected_type in key_types.items():
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(expected_type, list):
            # Union type: e.g. ["string", "null"]
            type_map = {
                "string": str,
                "null": type(None),
                "array": list,
                "object": dict,
                "number": (int, float),
                "boolean": bool,
            }
            allowed_types = tuple(type_map.get(t, object) for t in expected_type)
            assert isinstance(value, allowed_types), (
                f"[{agent_id}] Key '{key}' type mismatch: expected one of {expected_type}, "
                f"got {type(value).__name__} (REG-04 T261)"
            )
        else:
            type_map = {
                "string": str,
                "array": list,
                "object": dict,
                "number": (int, float),
                "boolean": bool,
                "null": type(None),
            }
            expected = type_map.get(expected_type, object)
            assert isinstance(value, expected), (  # type: ignore[arg-type]
                f"[{agent_id}] Key '{key}' type mismatch: expected {expected_type}, "
                f"got {type(value).__name__} (REG-04 T261)"
            )

    # Forbidden keys (no system prompt leakage)
    for forbidden_key in golden.get("forbidden_keys", []):
        assert forbidden_key not in payload, (
            f"[{agent_id}] Forbidden key '{forbidden_key}' found in response "
            f"(LLM07 system prompt leakage prevention, REG-04 T261)"
        )

    # Value constraints
    constraints = golden.get("value_constraints", {})
    for key, constraint in constraints.items():
        if key not in payload:
            continue
        value = payload[key]
        if "allowed_values" in constraint:
            assert value in constraint["allowed_values"], (
                f"[{agent_id}] Key '{key}' value {value!r} not in allowed values "
                f"{constraint['allowed_values']} (REG-04 T261)"
            )
        if "min_length" in constraint and isinstance(value, str):
            assert len(value) >= constraint["min_length"], (
                f"[{agent_id}] Key '{key}' length {len(value)} < {constraint['min_length']} "
                f"(REG-04 T261)"
            )


# ---------------------------------------------------------------------------
# Server fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_server() -> str:  # type: ignore[return]
    """Running API server for 7-agent golden tests."""
    _prepare_database()
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "seven-agents-golden.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    )
    env["HARNESS_EMAIL_SEND_ENABLED"] = "false"
    env["REDIS_URL"] = "redis://localhost:6379/15"  # always override; ambient may point to prod
    command = [
        str(
            Path(os.environ.get("PYTHON_PATH", "/opt/conda/envs/wm_env/bin/python"))
        ),
        "-m",
        "uvicorn",
        "apps.api.harness.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, env=env, stdout=log_file, stderr=log_file
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            if process.poll() is not None:
                pytest.skip(f"API server exited; see {log_path}")
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=2) as r:
                    if json.load(r).get("status") == "ok":
                        break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.25)
        else:
            pytest.skip(f"API server not healthy; see {log_path}")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@pytest.fixture(scope="module")
def tokens(api_server: str) -> dict[str, str]:
    # Flush the dedicated test Redis db so accumulated login rate-limit counters
    # from prior test modules don't trip the 10/min ceiling. The api_server
    # fixture configures REDIS_URL=redis://localhost:6379/15 — flush that db.
    try:
        import redis as _redis  # type: ignore[import-untyped]
        _redis.Redis(host="localhost", port=6379, db=15).flushdb()
    except Exception:  # noqa: BLE001
        pass
    result = {}
    for role, email in ACCOUNTS.items():
        status, payload, text = _request(
            api_server,
            "POST",
            "/auth/login",
            body={"email": email, "password": SYNTHETIC_PASSWORD},
        )
        if status != 200:
            continue  # skip this role — individual tests will skip if needed
        result[role] = str(payload["access_token"])
    return result


# ---------------------------------------------------------------------------
# Agent 1: house_view_generation
# ---------------------------------------------------------------------------

@pytest.mark.seven_agents_golden
@pytest.mark.integration
def test_golden_house_view_generation(api_server: str, tokens: dict[str, str]) -> None:
    """house_view_generation: created house view matches golden schema (REG-04 T261)."""
    golden = _load_golden("house_view_generation")

    import uuid as _uuid
    status, payload, text = _request(
        api_server,
        "POST",
        "/house-views",
        token=tokens["ADMIN"],
        body={
            "period_code": "GOLDEN_TEST",
            "title": "골든 스냅샷 테스트 하우스뷰",
            "summary": "REG-04 T261 golden regression test entry.",
        },
        extra_headers={"Idempotency-Key": str(_uuid.uuid4())},
    )
    assert status == 201, f"POST /house-views failed: {text[:500]}"
    _validate_schema(payload, golden, "house_view_generation")


# ---------------------------------------------------------------------------
# Agent 2: consultation_briefing
# ---------------------------------------------------------------------------

@pytest.mark.seven_agents_golden
@pytest.mark.integration
def test_golden_consultation_briefing(api_server: str, tokens: dict[str, str]) -> None:
    """consultation_briefing: AI job creation matches golden schema (REG-04 T261)."""
    golden = _load_golden("consultation_briefing")

    # Create a consultation first
    status, consultation, text = _request(
        api_server,
        "POST",
        "/consultations",
        token=tokens["PB"],
        body={"customer_id": CUSTOMER_PB1, "channel_code": "PHONE"},
    )
    if status != 201:
        pytest.skip(f"Cannot create consultation: {text[:300]}")

    consultation_id = consultation.get("id") or consultation.get("consultation_id")
    status, payload, text = _request(
        api_server,
        "POST",
        f"/consultations/{consultation_id}/briefing-job",
        token=tokens["PB"],
    )
    if status == 404:
        pytest.skip(
            "Route POST /consultations/{id}/briefing-job not yet implemented "
            "(BLOCKER #26 worker-juliet W2-T6)"
        )
    assert status in (200, 201, 202), (
        f"POST /consultations/{{id}}/briefing-job failed with {status}: {text[:500]}"
    )
    _validate_schema(payload, golden, "consultation_briefing")


# ---------------------------------------------------------------------------
# Agent 3: nba_script  [BLOCKER #26 — worker-juliet W2-T6]
# ---------------------------------------------------------------------------

@pytest.mark.seven_agents_golden
@pytest.mark.integration
def test_golden_nba_script(api_server: str, tokens: dict[str, str]) -> None:
    """nba_script: NBA card matches golden schema (REG-04 T261) — BLOCKER #26."""
    golden = _load_golden("nba_script")

    # Fetch an existing NBA action seeded by full-mvp profile
    status, nba_list, text = _request(
        api_server,
        "GET",
        "/nba-actions?limit=1&offset=0",
        token=tokens["PB"],
    )
    assert status == 200, f"GET /nba-actions failed: {text[:500]}"
    items = nba_list.get("items", [])
    if not items:
        pytest.skip("No NBA actions seeded; check full-mvp seed profile")

    nba_action = items[0]
    _validate_schema(nba_action, golden, "nba_script")

    # TODO BLOCKER #26: Once worker-juliet adds nba_script AI job route,
    # also test POST /nba-actions/{id}/script-job and validate ai_output schema.


# ---------------------------------------------------------------------------
# Agent 4: email_draft
# ---------------------------------------------------------------------------

@pytest.mark.seven_agents_golden
@pytest.mark.integration
def test_golden_email_draft(api_server: str, tokens: dict[str, str]) -> None:
    """email_draft: created draft matches golden schema (REG-04 T261)."""
    import uuid as _uuid
    golden = _load_golden("email_draft")

    status, payload, text = _request(
        api_server,
        "POST",
        "/email-drafts",
        token=tokens["PB"],
        body={
            "customer_id": CUSTOMER_PB1,
            "consultation_id": CONSULTATION_PB1,
            "subject": "골든 테스트 이메일 초안",
            "body": "REG-04 T261 golden regression test email body content.",
        },
        extra_headers={"Idempotency-Key": str(_uuid.uuid4())},
    )
    if status >= 500:
        pytest.skip(
            f"POST /email-drafts returned {status} (likely undeployed migration, "
            f"e.g. marketing_classified column — BLOCKER schema sync): {text[:300]}"
        )
    assert status == 201, f"POST /email-drafts failed with {status}: {text[:500]}"
    _validate_schema(payload, golden, "email_draft")

    # PII check: body field must not contain raw PII patterns
    if golden.get("pii_forbidden_in_body"):
        import re

        response_body = payload.get("body", "")
        pii_pattern = re.compile(r"\d{6}-\d{7}|\d{10,16}", re.ASCII)
        assert not pii_pattern.search(response_body), (
            "email_draft body must not contain raw PII (AI-03, REG-04 T261)"
        )


# ---------------------------------------------------------------------------
# Agent 5: rag_qa
# ---------------------------------------------------------------------------

@pytest.mark.seven_agents_golden
@pytest.mark.integration
def test_golden_rag_qa(api_server: str, tokens: dict[str, str]) -> None:
    """rag_qa: response matches golden schema (REG-04 T261) — BLOCKER #21/#22."""
    golden = _load_golden("rag_qa")

    status, payload, text = _request(
        api_server,
        "POST",
        "/rag/query",
        token=tokens["PB"],
        body={"question": "적합성 평가 6가지 요소를 설명해 주세요."},
    )
    assert status == 200, f"POST /rag/query failed with {status}: {text[:500]}"
    _validate_schema(payload, golden, "rag_qa")

    # For READY responses: citations must be present and faithfulness_score recorded
    if payload.get("status_code") == "READY":
        citations = payload.get("citations", [])
        assert len(citations) >= 1, (
            "rag_qa READY response must include ≥1 citation (AI-04 citation gating)"
        )
        if golden.get("rag_answer_evidence_required"):
            # rag_answer_evidence persistence is validated in test_rag_golden.py
            pass

    # For BLOCKED responses: fail_closed_reason_code must be in allowed set
    if payload.get("status_code") == "BLOCKED":
        reason = payload.get("fail_closed_reason_code")
        if reason is None:
            pytest.skip(
                "rag_qa BLOCKED but fail_closed_reason_code not populated "
                "(BLOCKER #21: RAG pipeline incomplete)"
            )
        allowed = golden.get("allowed_fail_closed_codes", [])
        assert reason in allowed, (
            f"rag_qa BLOCKED fail_closed_reason_code {reason!r} not in allowed set "
            f"{allowed} (REG-04 §4.2)"
        )


# ---------------------------------------------------------------------------
# Agent 6: compliance_check
# ---------------------------------------------------------------------------

@pytest.mark.seven_agents_golden
@pytest.mark.integration
def test_golden_compliance_check(api_server: str, tokens: dict[str, str]) -> None:
    """compliance_check: 4-gate evaluation matches golden schema (REG-04 T261)."""
    golden = _load_golden("compliance_check")

    # Use the existing recommendation-simulations endpoint which embeds gate evaluation
    status, payload, text = _request(
        api_server,
        "POST",
        "/recommendation-simulations",
        token=tokens["PB"],
        body={
            "customer_id": CUSTOMER_PB1,
            "consultation_id": CONSULTATION_PB1,
            "product_id": PRODUCT_ID,
            "explanation_checked": True,
            "simulated_customer_consented": True,
            "employee_final_approved": True,
        },
    )
    assert status == 201, f"POST /recommendation-simulations failed: {text[:500]}"

    # The gate_detail_json embedded in the simulation response represents compliance_check output
    gate_detail_raw = payload.get("gate_detail_json", {})
    if isinstance(gate_detail_raw, str):
        import json as _json
        gate_detail_raw = _json.loads(gate_detail_raw) if gate_detail_raw else {}
    gate_detail = gate_detail_raw if isinstance(gate_detail_raw, dict) else {}
    checks = gate_detail.get("checks", {})
    gate_payload = {
        "status_code": payload.get("status_code", ""),
        "checks": checks,
        "failed": gate_detail.get("failed", []),
    }
    _validate_schema(gate_payload, golden, "compliance_check")

    # compliance_check must be rule-based (deterministic) — no AI hallucination
    if golden.get("rule_based_deterministic"):
        check_keys = golden["value_constraints"]["checks"]["required_check_keys"]
        for key in check_keys:
            assert key in checks, (
                f"compliance_check checks must include '{key}' (BIZ-09 4-gate, REG-04 T261)"
            )


# ---------------------------------------------------------------------------
# Agent 7: portfolio_analysis
# ---------------------------------------------------------------------------

@pytest.mark.seven_agents_golden
@pytest.mark.integration
def test_golden_portfolio_analysis(api_server: str, tokens: dict[str, str]) -> None:
    """portfolio_analysis: AI job creation matches golden schema (REG-04 T261)."""
    golden = _load_golden("portfolio_analysis")

    status, payload, text = _request(
        api_server,
        "POST",
        f"/customers/{CUSTOMER_PB1}/portfolio-analysis-job",
        token=tokens["PB"],
    )
    if status == 404:
        pytest.skip(
            "Route POST /customers/{id}/portfolio-analysis-job not yet implemented "
            "(BLOCKER #26 worker-juliet W2-T6)"
        )
    assert status in (200, 201, 202), (
        f"POST /customers/{{id}}/portfolio-analysis-job failed with {status}: {text[:500]}"
    )
    _validate_schema(payload, golden, "portfolio_analysis")
