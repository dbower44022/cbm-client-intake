"""Hand ticks on the setup checklists (prds/integrations-tab-plan.md § 4 and
§ 7), in the application's database (migration
``0045_integration_checklist_tick``).

The table is a log: every tick and every untick is one row, and a step's
current state is its latest row. That is what lets the History tab show each
one with who did it and when. Ticks are held for the whole deployment, keyed by
the guide's step number, so a step on two sub-tabs is ticked once for both;
``integration`` records the sub-tab it was ticked from.

Training data on the sandbox: the table is in ``RESET_TABLES``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, Column, DateTime, Index, String, Table, select

from core.config import Settings
from core.store import metadata, shared_engine

integration_checklist_tick = Table(
    "integration_checklist_tick",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("step_id", String(16), nullable=False),
    Column("integration", String(40), nullable=False),
    Column("ticked", Boolean, nullable=False),
    Column("actor_id", String(32)),
    Column("actor", String(128)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Index("ix_integration_checklist_tick_step", "step_id", "created_at"),
)


def _public(r: Any) -> dict[str, Any]:
    return {
        "stepId": r["step_id"],
        "integration": r["integration"],
        "ticked": bool(r["ticked"]),
        "by": r["actor"] or "",
        "at": r["created_at"].isoformat() if r["created_at"] else None,
    }


class TickStore:
    def __init__(self, database_url: str) -> None:
        self._engine = shared_engine(database_url)

    async def record(self, step_id: str, integration: str, ticked: bool, *,
                     actor_id: str = "", actor: str = "") -> dict[str, Any]:
        row = {
            "id": str(uuid.uuid4()),
            "step_id": step_id,
            "integration": integration,
            "ticked": bool(ticked),
            "actor_id": actor_id or None,
            "actor": actor or None,
            "created_at": datetime.now(timezone.utc),
        }
        async with self._engine.begin() as conn:
            await conn.execute(integration_checklist_tick.insert().values(**row))
        return _public(row)

    async def current(self) -> dict[str, dict[str, Any]]:
        """Each step's latest row, keyed by step number."""
        t = integration_checklist_tick
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(t).distinct(t.c.step_id)
                .order_by(t.c.step_id, t.c.created_at.desc())
            )).mappings().all()
        return {r["step_id"]: _public(r) for r in rows}

    async def history(self, limit: int = 50) -> list[dict[str, Any]]:
        t = integration_checklist_tick
        async with self._engine.begin() as conn:
            rows = (await conn.execute(
                select(t).order_by(t.c.created_at.desc()).limit(limit)
            )).mappings().all()
        return [_public(r) for r in rows]


def make_tick_store(settings: Settings) -> Optional[TickStore]:
    """A store when a database is configured, else None (no hand ticks)."""
    if not settings.store_enabled:
        return None
    return TickStore(settings.database_url)
