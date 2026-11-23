"""Stage 0.5 architecture-contract documentation gates."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_architecture_contract_validator_passes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "validate_architecture_contracts.py"),
            "--json",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert payload["errors"] == []
    assert set(payload["checks"]) >= {
        "required_docs",
        "contract_scope",
        "dependency_allowlist",
        "large_module_register",
        "ops_doc_sync",
    }


def test_websocket_and_email_contract_statuses_are_explicit() -> None:
    api_contract = (PROJECT_ROOT / "docs" / "api" / "API-01_contracts.yaml").read_text(
        encoding="utf-8"
    )
    websocket_contract = (PROJECT_ROOT / "docs" / "api" / "API-02_websocket.md").read_text(
        encoding="utf-8"
    )
    email_contract = (PROJECT_ROOT / "docs" / "integration" / "INT-03_email.md").read_text(
        encoding="utf-8"
    )

    assert "WebSocket push" in api_contract
    assert "email draft/send" in api_contract
    assert "backlog/not-current-contract" in websocket_contract
    assert "POST /email-drafts" in email_contract
    assert "POST /email-drafts/{draft_id}/send" in email_contract
    assert "BLOCKED_WITH_REDACTED_REASON" in email_contract
    assert "Refresh cookies" in websocket_contract
    assert "not WebSocket authorization credentials" in websocket_contract
    assert "ADMIN system authority is not PB/WM customer communication authority" in email_contract
    assert "email_draft_send" in email_contract
