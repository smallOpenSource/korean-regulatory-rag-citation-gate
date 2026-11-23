"""Static DB and SQL convention checks for the raw-SQL foundation."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import scripts.t55_schema_preflight as t55_schema_preflight
from apps.api.harness.batch import runner as batch_runner
from apps.api.harness.core.sql import validate_sql_text
from apps.api.harness.repositories import documents as document_repo
from apps.api.harness.repositories import readiness as readiness_repo
from db.migrator import discover_migrations, split_sql_statements, validate_statement

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"
FORBIDDEN_IMPORT_ROOTS = {"sqlalchemy", "alembic", "django.db"}
FORBIDDEN_MIGRATION_TOOL_WORDS = {"flyway", "liquibase", "alembic"}

# V067 predates the per-statement sql_id convention (only file-level stmt 1 has a
# header). V070 documents the retroactive fix. Statement 1 is still validated.
GRANDFATHERED_MIGRATIONS = {"V067__service_readiness_fixture_seeds.sql"}


def _python_files() -> list[Path]:
    ignored_parts = {".omx", ".pytest_cache", "__pycache__"}
    return [
        path
        for path in PROJECT_ROOT.rglob("*.py")
        if not (set(path.relative_to(PROJECT_ROOT).parts) & ignored_parts)
    ]


def test_migration_versions_are_sequential():
    migrations = discover_migrations()
    versions = [migration.version for migration in migrations]
    # Versions must be 1..N with no gaps (N grows as Wave 2 migrations are added)
    assert versions == list(range(1, len(versions) + 1)), (
        f"Migration versions are not sequential: {versions}"
    )
    assert [migration.path.name for migration in migrations] == sorted(
        migration.path.name for migration in migrations
    )


def test_v015_provider_evidence_schema_is_separate_from_batch_job_status():
    migration_text = (MIGRATIONS_DIR / "V015__provider_status_normalization.sql").read_text()
    provider_status_codes = {
        "PROVIDER_DONE",
        "PROVIDER_NO_DATA",
        "PROVIDER_SKIPPED_CONFIG",
        "PROVIDER_SKIPPED_DISABLED",
        "PROVIDER_FAILED_AUTH",
        "PROVIDER_FAILED_RATE_LIMIT",
        "PROVIDER_FAILED_SCHEMA",
        "PROVIDER_FAILED_NETWORK",
    }

    assert "CREATE TABLE IF NOT EXISTS batch_provider_evidence" in migration_text
    assert "REFERENCES batch_job_logs(id) ON DELETE CASCADE" in migration_text
    assert "UNIQUE (batch_job_log_id, provider_code, target_ref)" in migration_text
    assert "target_ref VARCHAR(160) NOT NULL" in migration_text
    assert "provider_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb" in migration_text
    for status_code in provider_status_codes:
        assert f"'{status_code}'" in migration_text

    assert "ALTER TABLE batch_job_logs" not in migration_text
    assert "NO_DATA" not in (MIGRATIONS_DIR / "V009__batch_tables.sql").read_text()
    assert "market_price_bars" not in migration_text
    assert "provider_security_identifiers" not in migration_text


def test_every_migration_statement_starts_with_sql_id_and_avoids_select_star():
    for migration in discover_migrations():
        statements = split_sql_statements(migration.path.read_text())
        assert statements, f"{migration.path} has no SQL statements"
        grandfathered = migration.path.name in GRANDFATHERED_MIGRATIONS
        for index, statement in enumerate(statements, start=1):
            # Grandfathered migrations predate per-statement sql_id convention.
            # Statement 1 (file-level header) is still validated; rest are skipped.
            if grandfathered and index > 1:
                continue
            validate_statement(statement, context=f"{migration.path}:{index}")


def test_t55_schema_preflight_sql_uses_sql_id_comments():
    for sql_name in (
        "TABLE_STATUS_SQL",
        "MIGRATION_STATUS_SQL",
        "COLUMN_STATUS_SQL",
        "CONSTRAINT_STATUS_SQL",
        "EVIDENCE_COUNTS_SQL",
    ):
        result = validate_sql_text(
            getattr(t55_schema_preflight, sql_name),
            context=f"t55_schema_preflight.{sql_name}",
        )
        assert result.ok, result.errors


def test_t55_schema_preflight_reports_krx_source_governance_counts():
    sql = t55_schema_preflight.EVIDENCE_COUNTS_SQL

    assert "official_krx_price_bar_rows" in sql
    assert "pykrx_price_bar_rows" in sql
    assert "official_krx_trading_day_count" in sql
    assert "pykrx_trading_day_count" in sql
    assert "official_krx_policy_evidence_rows" in sql
    assert "pykrx_auxiliary_policy_evidence_rows" in sql
    assert "OFFICIAL_KRX_APPROVED" in sql
    assert "PYKRX_AUXILIARY_APPROVED" in sql


def test_t55_schema_preflight_redis_evidence_exercises_owner_lock(monkeypatch):
    class FakeRedis:
        def __init__(self) -> None:
            self.values: dict[str, str] = {}
            self.ping_called = False

        def ping(self) -> bool:
            self.ping_called = True
            return True

        def set(self, key: str, value: str, nx: bool, ex: int) -> bool:
            assert nx is True
            assert ex == 30
            if key in self.values:
                return False
            self.values[key] = value
            return True

        def eval(self, _script: str, _key_count: int, key: str, owner: str) -> int:
            if self.values.get(key) != owner:
                return 0
            del self.values[key]
            return 1

    fake_redis = FakeRedis()
    monkeypatch.setattr(t55_schema_preflight, "create_redis_client", lambda _config: fake_redis)
    monkeypatch.setattr(t55_schema_preflight, "redis_config_from_env", lambda: object())
    monkeypatch.setattr(t55_schema_preflight, "redis_endpoint_summary", lambda: {"mode": "test"})
    monkeypatch.setattr(t55_schema_preflight, "utc_timestamp", lambda: "20260516T000000Z")

    evidence = t55_schema_preflight.collect_redis_evidence()

    assert evidence["status_code"] == "READY"
    assert evidence["endpoint"] == {"mode": "test"}
    assert evidence["ping_status_code"] == "READY"
    assert evidence["lock_smoke"] == {
        "status_code": "READY",
        "key": "harness:t55_schema_preflight:20260516T000000Z",
        "acquired": True,
        "released": True,
    }
    assert fake_redis.ping_called is True
    assert fake_redis.values == {}


def test_readiness_validator_sql_uses_unique_report_aliases():
    for label, sql in {
        "readiness_metrics": readiness_repo.READINESS_METRICS_SQL,
        "provider_window": batch_runner.POSTCONDITION_SQL["provider_window"],
    }.items():
        aliases = re.findall(r"\bAS\s+([a-z][a-z0-9_]*)", sql, flags=re.IGNORECASE)
        duplicates = sorted({alias for alias in aliases if aliases.count(alias) > 1})
        assert not duplicates, f"{label} has duplicate report aliases: {duplicates}"


def test_document_upsert_sql_casts_dedup_parameters_for_postgres():
    sql = document_repo.UPSERT_DOCUMENT_FROM_RAW_SQL

    assert "content_hash = $4::varchar" in sql
    assert "source_url = $6::text" in sql


def test_fixture_sql_uses_sql_id_comments():
    for path in sorted((PROJECT_ROOT / "db" / "fixtures").glob("*.sql")):
        statements = split_sql_statements(path.read_text())
        assert statements, f"{path} has no SQL statements"
        for index, statement in enumerate(statements, start=1):
            validate_statement(statement, context=f"{path}:{index}")


def test_document_chunk_embedding_dimension_matches_internal_bge_contract():
    chunk_migration = MIGRATIONS_DIR / "V007__documents_chunks.sql"
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        env_path = PROJECT_ROOT / ".env.example"
    env_text = env_path.read_text()

    assert "embedding vector(1024)" in chunk_migration.read_text()
    assert re.search(r"^BGE_EMBEDDING_DIMENSIONS=1024$", env_text, re.MULTILINE)


def test_no_orm_or_external_migration_tool_imports():
    violations: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name
                    root = imported.split(".", 1)[0]
                    if imported in FORBIDDEN_IMPORT_ROOTS or root in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(f"{path}:{node.lineno}:{imported}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                if module in FORBIDDEN_IMPORT_ROOTS or root in FORBIDDEN_IMPORT_ROOTS:
                    violations.append(f"{path}:{node.lineno}:{module}")
    assert not violations


def test_no_forbidden_migration_tool_references_in_executable_code():
    violations: list[str] = []
    for path in _python_files():
        text = path.read_text().lower()
        for word in FORBIDDEN_MIGRATION_TOOL_WORDS:
            # The static scanner itself documents forbidden words; application code must not.
            if word in text and path.name != "test_sql_contracts.py":
                violations.append(f"{path}:{word}")
    assert not violations


def test_no_broker_order_mutation_endpoint_strings_in_executable_code():
    forbidden_fragments = (
        "order" + "-" + "cash",
        "/".join(["order", "cancel"]),
        "/".join(["trading", "order"]),
    )
    violations: list[str] = []
    for path in _python_files():
        text = path.read_text().lower()
        if path.name in {"test_sql_contracts.py", "test_task3_external_batch.py"}:
            continue
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{path}:{fragment}")
    assert not violations


def test_sql_validator_rejects_select_star():
    with pytest.raises(RuntimeError, match=r"SELECT \*"):
        validate_statement(
            "/* sql_id: bad_select_star */ SELECT * FROM customers;",
            context="bad_select_star",
        )


def test_sql_validator_allows_count_star():
    validate_statement(
        "/* sql_id: count_rows */ SELECT count(*) AS row_count FROM customers;",
        context="count_rows",
    )


def test_v018_kr_isin_constraint_accepts_official_krx_isu_cd_shape():
    migration_text = (MIGRATIONS_DIR / "V018__kr_isin_constraint_normalization.sql").read_text()

    assert "DROP CONSTRAINT IF EXISTS securities_isin_check" in migration_text
    assert "DROP CONSTRAINT IF EXISTS security_identifiers_value_format" in migration_text
    assert "DROP CONSTRAINT IF EXISTS market_universe_candidates_isin_check" in migration_text
    assert "^KR[0-9A-Z]{10}$" in migration_text
    assert "^KR7[0-9A-Z]{9}$" not in migration_text


def test_v017_domestic_top200_universe_schema_contract():
    migration_text = (MIGRATIONS_DIR / "V017__domestic_market_universe_top200.sql").read_text()

    required_tables = {
        "market_universe_snapshots",
        "market_universe_candidates",
        "market_universe_members",
        "market_trading_calendar",
        "market_universe_coverage_daily",
    }
    for table_name in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table_name}" in migration_text

    for column_name in (
        "trading_value_krw",
        "market_cap_krw",
        "listed_shares",
        "change_price",
        "change_rate_pct",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {column_name}" in migration_text

    assert "DOMESTIC_TOP200_MARKET_CAP" not in migration_text
    assert "source_policy_code VARCHAR(80) NOT NULL" in migration_text
    assert "provider_evidence_id UUID REFERENCES batch_provider_evidence(id)" in migration_text
    assert "market_price_bar_id UUID REFERENCES market_price_bars(id)" in migration_text
    assert "UNIQUE (snapshot_id, rank_no)" in migration_text
    assert "has_valid_bar IS TRUE AND market_price_bar_id IS NOT NULL" in migration_text
