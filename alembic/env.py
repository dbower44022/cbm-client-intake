"""Alembic environment — async, driven by DATABASE_URL.

Target metadata is the submission store's table (``core.store.metadata``), so a
single source of truth defines the schema. Run with::

    DATABASE_URL=postgresql://… uv run alembic upgrade head
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context

from core.store import _normalize_url, make_async_engine, metadata

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = metadata


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set to run migrations")
    return _normalize_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = make_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
