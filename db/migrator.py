"""Custom raw-SQL migration runner for Harness.

Usage:
    /opt/conda/envs/wm_env/bin/python db/migrator.py

The runner deliberately avoids ORM and migration frameworks. It validates every
statement for a leading ``sql_id`` comment before execution.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"
VERSION_RE = re.compile(r"^V(?P<version>\d{3})__(?P<name>[a-z0-9_]+)\.sql$")
SQL_ID_RE = re.compile(r"^\s*/\*\s*sql_id:\s*[a-z0-9_]+\s*\*/", re.IGNORECASE)
SELECT_STAR_RE = re.compile(r"\bSELECT\s+\*(?=\s|,|;|$)", re.IGNORECASE)


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def load_env_file(path: Path) -> None:
    """Populate missing environment variables from a dotenv file."""

    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def database_url_from_env() -> str:
    """Build the PostgreSQL connection URL from documented env variables."""

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url:
        if database_url.startswith("postgresql+asyncpg://"):
            raise RuntimeError("DATABASE_URL must not use SQLAlchemy postgresql+asyncpg scheme")
        return database_url
    required = ["POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise RuntimeError(f"Missing database environment variables: {', '.join(missing)}")
    host = os.environ["POSTGRES_HOST"]
    port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.environ["POSTGRES_DB"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    return f"postgresql://{user}:{password}@{host}:{port}/{db_name}"


def split_sql_statements(sql_text: str) -> list[str]:
    """Split PostgreSQL SQL text while preserving dollar-quoted function bodies."""

    statements: list[str] = []
    start = 0
    index = 0
    quote: str | None = None
    dollar_tag: str | None = None
    line_comment = False
    block_comment_depth = 0

    while index < len(sql_text):
        char = sql_text[index]
        nxt = sql_text[index : index + 2]

        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue

        if block_comment_depth:
            if nxt == "/*":
                block_comment_depth += 1
                index += 2
                continue
            if nxt == "*/":
                block_comment_depth -= 1
                index += 2
                continue
            index += 1
            continue

        if dollar_tag:
            if sql_text.startswith(dollar_tag, index):
                index += len(dollar_tag)
                dollar_tag = None
                continue
            index += 1
            continue

        if quote:
            if char == quote:
                if index + 1 < len(sql_text) and sql_text[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if nxt == "--":
            line_comment = True
            index += 2
            continue
        if nxt == "/*":
            block_comment_depth = 1
            index += 2
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "$":
            match = re.match(r"\$[A-Za-z0-9_]*\$", sql_text[index:])
            if match:
                dollar_tag = match.group(0)
                index += len(dollar_tag)
                continue
        if char == ";":
            statement = sql_text[start : index + 1].strip()
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1

    tail = sql_text[start:].strip()
    if tail:
        statements.append(tail)
    return statements


def validate_statement(statement: str, *, context: str) -> None:
    """Enforce Harness SQL conventions."""

    if not SQL_ID_RE.match(statement):
        raise RuntimeError(f"{context} must start with /* sql_id: short_name */")
    if SELECT_STAR_RE.search(statement):
        raise RuntimeError(f"{context} must not use SELECT *")


def discover_migrations() -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(MIGRATIONS_DIR.glob("V*.sql")):
        match = VERSION_RE.match(path.name)
        if not match:
            raise RuntimeError(f"Invalid migration filename: {path.name}")
        migrations.append(Migration(int(match.group("version")), match.group("name"), path))
    versions = [migration.version for migration in migrations]
    if versions != sorted(set(versions)):
        raise RuntimeError("Migration versions must be unique and sorted")
    expected = list(range(1, len(versions) + 1))
    if versions != expected:
        raise RuntimeError(f"Migration versions must be sequential from 001: {versions}")
    return migrations


async def ensure_version_table(connection) -> None:
    await connection.execute(
        """
        /* sql_id: create_migration_versions */
        CREATE TABLE IF NOT EXISTS migration_versions (
            version INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            checksum_sha256 VARCHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )


async def migration_applied(connection, version: int) -> bool:
    value = await connection.fetchval(
        """
        /* sql_id: find_migration_version */
        SELECT version FROM migration_versions WHERE version = $1;
        """,
        version,
    )
    return value is not None


async def record_migration(connection, migration: Migration, checksum: str) -> None:
    await connection.execute(
        """
        /* sql_id: insert_migration_version */
        INSERT INTO migration_versions(version, name, checksum_sha256)
        VALUES ($1, $2, $3)
        ON CONFLICT (version) DO NOTHING;
        """,
        migration.version,
        migration.name,
        checksum,
    )


def checksum_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def apply_migration(connection, migration: Migration) -> None:
    sql_text = migration.path.read_text()
    statements = split_sql_statements(sql_text)
    if not statements:
        raise RuntimeError(f"Empty migration: {migration.path}")
    for index, statement in enumerate(statements, start=1):
        validate_statement(statement, context=f"{migration.path.name}:{index}")

    async with connection.transaction():
        for statement in statements:
            await connection.execute(statement)
        await record_migration(connection, migration, checksum_text(sql_text))


async def run() -> None:
    try:
        import asyncpg
    except ImportError as exc:
        raise RuntimeError("asyncpg is required to run db/migrator.py") from exc

    load_env_file(PROJECT_ROOT / ".env")
    connection = await asyncpg.connect(database_url_from_env())
    try:
        await ensure_version_table(connection)
        for migration in discover_migrations():
            if await migration_applied(connection, migration.version):
                print(f"skip V{migration.version:03d} {migration.name}")
                continue
            await apply_migration(connection, migration)
            print(f"applied V{migration.version:03d} {migration.name}")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(run())
