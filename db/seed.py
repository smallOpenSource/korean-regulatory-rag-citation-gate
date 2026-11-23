"""Custom raw-SQL seed runner for Harness deterministic data profiles.

Usage:
    /opt/conda/envs/wm_env/bin/python db/seed.py --profile full-mvp

The runner deliberately avoids ORM and migration frameworks. It validates every
fixture statement for a leading ``sql_id`` comment before execution.
"""

from __future__ import annotations

# ruff: noqa: E402,I001

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.migrator import (
    database_url_from_env,
    load_env_file,
    split_sql_statements,
    validate_statement,
)
FIXTURES_DIR = PROJECT_ROOT / "db" / "fixtures"


@dataclass(frozen=True)
class SeedProfile:
    name: str
    fixture_names: tuple[str, ...]
    description: str


PROFILES: dict[str, SeedProfile] = {
    "synthetic": SeedProfile(
        name="synthetic",
        fixture_names=("seed_synthetic.sql",),
        description="Compatibility seed containing the original minimal synthetic baseline.",
    ),
    "full-mvp": SeedProfile(
        name="full-mvp",
        fixture_names=(
            "seed_00_identity.sql",
            "seed_10_customers_risk.sql",
            "seed_20_products_portfolios.sql",
            "seed_30_workflows.sql",
            "seed_40_manual_rag.sql",
        ),
        description="Deterministic operational baseline for local MVP verification.",
    ),
}

READINESS_THRESHOLDS: dict[str, int] = {
    "branches": 2,
    "employees": 6,
    "customers": 20,
    "risk_assessments": 20,
    "products": 12,
    "portfolios": 20,
    "portfolio_holdings": 60,
    "house_views": 2,
    "consultations": 10,
    "consultation_notes": 10,
    "house_view_applications": 5,
    "nba_actions": 20,
    "aftercare_events": 20,
    "recommendation_simulations": 12,
    "order_simulations": 12,
    "audit_logs": 6,
    "email_drafts": 2,
    "ai_jobs": 2,
    "ai_outputs": 1,
    "raw_documents": 5,
    "documents": 5,
    "document_chunks": 30,
    "batch_job_logs": 5,
}

PROVIDER_OWNED_TABLES = (
    "market_price_bars",
    "market_prices",
    "financial_ratios",
    "investor_flows",
    "macro_indicators",
)


@dataclass(frozen=True)
class FixtureFile:
    path: Path
    statements: tuple[str, ...]


def profile_names() -> list[str]:
    """Return supported seed profile names."""

    return sorted(PROFILES)


def resolve_profile(profile_name: str) -> SeedProfile:
    """Resolve a profile or raise a deterministic operator error."""

    profile = PROFILES.get(profile_name)
    if profile is None:
        supported = ", ".join(profile_names())
        raise RuntimeError(
            f"Unknown seed profile '{profile_name}'. Supported profiles: {supported}"
        )
    return profile


def load_fixture_file(path: Path) -> FixtureFile:
    """Read and validate one fixture file."""

    statements = tuple(split_sql_statements(path.read_text(encoding="utf-8")))
    if not statements:
        raise RuntimeError(f"Empty seed fixture: {path}")
    for index, statement in enumerate(statements, start=1):
        validate_statement(statement, context=f"{path.name}:{index}")
    return FixtureFile(path=path, statements=statements)


def load_profile_fixtures(profile_name: str) -> list[FixtureFile]:
    """Load all fixture files for a profile in deterministic order."""

    profile = resolve_profile(profile_name)
    fixtures: list[FixtureFile] = []
    for fixture_name in profile.fixture_names:
        path = FIXTURES_DIR / fixture_name
        if not path.exists():
            raise RuntimeError(f"Missing seed fixture for profile {profile.name}: {fixture_name}")
        fixtures.append(load_fixture_file(path))
    return fixtures


async def apply_fixture_files(connection: Any, fixtures: list[FixtureFile]) -> int:
    """Execute fixture statements in the supplied order."""

    ai_model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip()
    if not ai_model_name:
        raise RuntimeError("AZURE_OPENAI_DEPLOYMENT_NAME is required for seed AI metadata")
    await connection.execute(
        "/* sql_id: set_seed_ai_model_name */\n"
        "SELECT set_config('harness.seed_ai_model_name', $1, true);",
        ai_model_name,
    )

    statement_count = 0
    for fixture in fixtures:
        for statement in fixture.statements:
            await connection.execute(statement)
            statement_count += 1
    return statement_count


async def apply_profile(connection: Any, profile_name: str) -> dict[str, Any]:
    """Apply one seed profile inside a transaction and return readiness evidence."""

    fixtures = load_profile_fixtures(profile_name)
    async with connection.transaction():
        statement_count = await apply_fixture_files(connection, fixtures)
        readiness = await collect_readiness(connection)
    return {
        "profile": profile_name,
        "fixture_files": [fixture.path.name for fixture in fixtures],
        "statements_executed": statement_count,
        "readiness": readiness,
    }


async def collect_readiness(connection: Any) -> dict[str, Any]:
    """Collect seed readiness counts without implying provider data success."""

    tables: dict[str, dict[str, Any]] = {}
    for table_name, minimum in READINESS_THRESHOLDS.items():
        row_count = await _count_table_rows(connection, table_name)
        tables[table_name] = {
            "row_count": row_count,
            "minimum": minimum,
            "ready": row_count >= minimum,
            "provenance": "synthetic_operational",
        }
    for table_name in PROVIDER_OWNED_TABLES:
        tables[table_name] = {
            "row_count": await _count_table_rows(connection, table_name),
            "minimum": 0,
            "ready": True,
            "provenance": "provider_owned_not_seeded",
            "blocked_semantics": "Run provider batch jobs; seed must not fabricate provider rows.",
        }
    return {"tables": tables, "ready": all(item["ready"] for item in tables.values())}


async def _count_table_rows(connection: Any, table_name: str) -> int:
    statement = (
        f"/* sql_id: seed_readiness_count_{table_name} */\n"
        f"SELECT count(*)::integer AS row_count FROM {table_name};"
    )
    validate_statement(statement, context=f"readiness:{table_name}")
    value = await connection.fetchval(statement)
    return int(value or 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply deterministic Harness seed fixtures.")
    parser.add_argument("--profile", default="full-mvp", choices=profile_names())
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate fixtures without DB writes.",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="Print supported profiles as JSON.",
    )
    return parser.parse_args()


async def run() -> None:
    args = parse_args()
    if args.list_profiles:
        profile_descriptions = {name: profile.description for name, profile in PROFILES.items()}
        print(json.dumps(profile_descriptions, indent=2))
        return

    fixtures = load_profile_fixtures(args.profile)
    if args.dry_run:
        payload = {
            "profile": args.profile,
            "fixture_files": [fixture.path.name for fixture in fixtures],
            "statements_validated": sum(len(fixture.statements) for fixture in fixtures),
        }
        print(json.dumps(payload, indent=2))
        return

    try:
        import asyncpg
    except ImportError as exc:
        raise RuntimeError("asyncpg is required to run db/seed.py") from exc

    load_env_file(PROJECT_ROOT / ".env")
    connection = await asyncpg.connect(database_url_from_env())
    try:
        result = await apply_profile(connection, args.profile)
        print(json.dumps(result, indent=2, default=str))
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(run())
