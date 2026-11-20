"""The mentor match runs, kept in the application database (ruling BE28;
Doug's decision 4, A, 11-19-26): every run is kept, the tab shows the latest.

One row per run in ``mentor_match``. Training data on the sandbox: it points
at CRM engagements the restore takes away (``core/sandbox_reset.RESET_TABLES``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (BigInteger, Column, DateTime, Float, Integer, String, Table, insert,
                        select)
from sqlalchemy.dialects.postgresql import JSONB

from core.config import Settings
from core.store import metadata, shared_engine

mentor_match = Table(
    "mentor_match",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("engagement_id", String(32), nullable=False, index=True),
    Column("run_at", DateTime(timezone=True), nullable=False),
    Column("run_by_id", String(32)),
    Column("run_by_name", String(255)),
    Column("model", String(64)),
    Column("prompt_version", String(64)),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("cost", Float),
    Column("result", JSONB, nullable=False),
)


def _row(r: Any) -> dict[str, Any]:
    return {
        "id": r["id"],
        "engagementId": r["engagement_id"],
        "runAt": r["run_at"].isoformat() if r["run_at"] else None,
        "runByName": r["run_by_name"] or "",
        "model": r["model"] or "",
        "promptVersion": r["prompt_version"] or "",
        "cost": r["cost"],
        "result": r["result"] or {},
    }


class MatchStore:
    """One per process, built once in ``create_app``; borrows the shared pool."""

    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def add(self, *, engagement_id: str, run_by_id: str, run_by_name: str,
                  model: str, prompt_version: str, input_tokens: int, output_tokens: int,
                  cost: float, result: dict[str, Any],
                  run_at: Optional[datetime] = None) -> dict[str, Any]:
        row = {"engagement_id": engagement_id, "run_at": run_at or datetime.now(timezone.utc),
               "run_by_id": run_by_id or None, "run_by_name": run_by_name or None,
               "model": model, "prompt_version": prompt_version,
               "input_tokens": input_tokens, "output_tokens": output_tokens,
               "cost": cost, "result": result}
        async with self._engine.begin() as conn:
            new_id = (await conn.execute(
                insert(mentor_match).values(**row).returning(mentor_match.c.id))).scalar_one()
        return _row({**row, "id": new_id})

    async def latest(self, engagement_id: str) -> Optional[dict[str, Any]]:
        async with self._engine.begin() as conn:
            r = (await conn.execute(
                select(mentor_match).where(mentor_match.c.engagement_id == engagement_id)
                .order_by(mentor_match.c.run_at.desc(), mentor_match.c.id.desc()).limit(1)
            )).mappings().first()
        return _row(r) if r is not None else None

    async def count(self, engagement_id: str) -> int:
        from sqlalchemy import func

        async with self._engine.begin() as conn:
            return int((await conn.execute(
                select(func.count()).select_from(mentor_match)
                .where(mentor_match.c.engagement_id == engagement_id))).scalar_one())


def make_match_store(settings: Settings) -> Optional[MatchStore]:
    """A store when a database is configured, else None (runs are not kept)."""
    if not settings.store_enabled:
        return None
    return MatchStore(settings.database_url)
