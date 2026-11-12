"""One database pool per process (OPEN-ITEMS #79, 11-11-26): every store
borrows the same engine on a loop, a store's own dispose leaves it alone, and
a new event loop gets a fresh one. No database is needed: an engine opens no
connection until it is used."""
import asyncio

import pytest

from core import store as core_store
from core.store import PostgresStore, dispose_shared_engines, shared_engine

URL = "postgresql://u:p@db.invalid:25060/app?sslmode=require"


@pytest.mark.asyncio
async def test_stores_share_one_engine_per_loop():
    a, b = PostgresStore(URL), shared_engine(URL)
    assert core_store._shared_for(a._engine.url) is core_store._shared_for(b.url)
    engine = core_store._shared_for(URL)
    assert engine.pool.size() == core_store.SHARED_POOL_SIZE
    assert engine.pool._max_overflow == core_store.SHARED_MAX_OVERFLOW
    await dispose_shared_engines()


@pytest.mark.asyncio
async def test_a_stores_dispose_leaves_the_shared_pool():
    s = PostgresStore(URL)
    before = core_store._shared_for(URL)
    await s.dispose()
    assert core_store._shared_for(URL) is before
    await dispose_shared_engines()
    assert core_store._shared == {}


def test_a_new_loop_gets_a_new_engine():
    async def grab():
        return core_store._shared_for(URL)

    first = asyncio.run(grab())
    second = asyncio.run(grab())
    assert first is not second


@pytest.mark.asyncio
async def test_dispose_with_nothing_open_is_safe():
    await dispose_shared_engines()
    await dispose_shared_engines()


def test_every_runtime_store_borrows_the_shared_engine():
    # A store that builds its own engine brings back one pool per store.
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    offenders = [
        str(p.relative_to(root)) for p in root.rglob("*.py")
        if ".venv" not in p.parts and p.parts[len(root.parts)] not in ("tests", "scripts", "alembic")
        and "self._engine = make_async_engine(" in p.read_text()
    ]
    assert offenders == []
