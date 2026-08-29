"""The store's Table objects must declare every column the migrations add.

SQLAlchemy Core refuses to COMPILE an insert that names a column the Table does
not declare (``CompileError: Unconsumed column names``) — before any database
is touched. On 2026-08-29 the first live save through the verified-settings
path returned HTTP 500 for exactly that reason: migration 0027 added
``encrypted`` to ``app_setting_history`` and ``SettingsStore.set`` wrote it, but
the Table never declared it. 1,894 tests were green because none of them
compiled the statement — the Postgres tests skip without ``TEST_DATABASE_URL``
and the router tests use a fake store. These two need no database.
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from core import settings_store

_VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"


class _RecordingOp:
    """Stands in for ``alembic.op`` and records the schema each migration adds."""

    def __init__(self) -> None:
        self.columns: list[tuple[str, str]] = []

    def add_column(self, table: str, column: sa.Column) -> None:
        self.columns.append((table, column.name))

    def create_index(self, *a, **k) -> None: ...
    def drop_index(self, *a, **k) -> None: ...
    def drop_column(self, *a, **k) -> None: ...
    def create_table(self, *a, **k) -> None: ...
    def drop_table(self, *a, **k) -> None: ...


def _columns_added_by(migration_glob: str) -> list[tuple[str, str]]:
    recorder = _RecordingOp()
    for path in sorted(_VERSIONS.glob(migration_glob)):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        mod.op = recorder
        mod.upgrade()
    return recorder.columns


def test_every_column_migration_0027_adds_is_declared_on_the_store_tables():
    added = _columns_added_by("0027_*.py")
    assert added, "migration 0027 should add columns"
    for table, column in added:
        declared = settings_store.metadata.tables[table].c
        assert column in declared, (
            f"migration 0027 adds {table}.{column} but core/settings_store.py "
            "does not declare it — every insert naming it will 500"
        )


def test_the_set_history_insert_compiles_for_postgres():
    """Mirrors the exact values ``SettingsStore.set`` writes to the history."""
    stmt = settings_store.app_setting_history.insert().values(
        id=str(uuid.uuid4()),
        key="setup_enabled",
        old_value="true",
        new_value="false",
        encrypted=False,
        action="set",
        reason="guard",
        created_at=datetime.now(timezone.utc),
        actor="test",
    )
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "encrypted" in sql
