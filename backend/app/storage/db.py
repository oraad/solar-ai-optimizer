"""Async database engine + session management."""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .orm import Base

# Lightweight, idempotent column additions for existing SQLite DBs (no Alembic).
# create_all only creates missing tables, never alters existing ones.
_TELEMETRY_MIGRATIONS: dict[str, str] = {
    "outdoor_temp": "ALTER TABLE telemetry ADD COLUMN outdoor_temp FLOAT",
}

_DECISION_MIGRATIONS: dict[str, str] = {
    "reserve_rationale": "ALTER TABLE decisions ADD COLUMN reserve_rationale TEXT DEFAULT ''",
    "shed_actions_json": "ALTER TABLE decisions ADD COLUMN shed_actions_json TEXT DEFAULT '[]'",
}

_SHED_MIGRATIONS: dict[str, str] = {
    "companion_audit_json": (
        "ALTER TABLE shed_executions ADD COLUMN companion_audit_json TEXT DEFAULT '{}'"
    ),
}

log = logging.getLogger("storage.db")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory for a file-backed SQLite DB if needed."""
    marker = "sqlite+aiosqlite:///"
    if database_url.startswith(marker):
        raw = database_url[len(marker):]
        # raw may start with an extra '/' for absolute paths.
        path = Path(raw.lstrip("/")) if not raw.startswith("/") else Path(raw)
        if str(path) not in {":memory:", ""}:
            path.parent.mkdir(parents=True, exist_ok=True)


async def init_db(database_url: str) -> None:
    """Initialise the engine and create tables."""
    global _engine, _sessionmaker
    _ensure_sqlite_dir(database_url)
    _engine = create_async_engine(database_url, future=True, echo=False)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_table(conn, "telemetry", _TELEMETRY_MIGRATIONS)
        await _migrate_table(conn, "decisions", _DECISION_MIGRATIONS)
        await _migrate_table(conn, "shed_executions", _SHED_MIGRATIONS)
    log.info("Database initialised at %s", database_url)


async def _migrate_table(conn, table: str, migrations: dict[str, str]) -> None:  # noqa: ANN001
    """Add any missing columns to a pre-existing table."""
    result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
    existing = {row[1] for row in result.fetchall()}
    for column, ddl in migrations.items():
        if column not in existing:
            await conn.execute(text(ddl))
            log.info("Migrated %s: added column %s", table, column)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("Database not initialised; call init_db() first.")
    return _sessionmaker


async def close_db() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
